"""Dependency-free HTTP app. Qwen is remote; no GPU required for this service."""
import concurrent.futures as cf
import hashlib, json, os, secrets, sqlite3, statistics, threading, time
from copy import deepcopy
from contextlib import closing
from http import HTTPStatus
from http.cookies import SimpleCookie
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib import request, error, parse
import game

ROOT=Path(__file__).parent
DB_PATH=os.environ.get("DATA_PATH",str(ROOT/"data"/"game.sqlite"))
BASE=os.environ.get("VLLM_BASE_URL","http://127.0.0.1:8000/v1").rstrip("/")
MODEL=os.environ.get("MODEL_NAME","")
KEY=os.environ.get("VLLM_API_KEY","not-needed")
OFFLINE=os.environ.get("OFFLINE","0")=="1"
TIMEOUT=int(os.environ.get("MODEL_TIMEOUT","60"))
MAX_REQUESTS=threading.BoundedSemaphore(32)
EXPERIMENT_LOCK=threading.Lock()
MODEL_LOCK=threading.Lock()
SCHEMA={"type":"object","properties":{"candidate_id":{"type":"string"},"reason":{"type":"string"}},"required":["candidate_id","reason"],"additionalProperties":False}

def db():
    Path(DB_PATH).parent.mkdir(parents=True,exist_ok=True)
    c=sqlite3.connect(DB_PATH,timeout=30)
    c.execute("CREATE TABLE IF NOT EXISTS sessions (id TEXT PRIMARY KEY, document TEXT NOT NULL)")
    return c

def read_session(sid):
    with closing(db()) as c, c:
        row=c.execute("SELECT document FROM sessions WHERE id=?",(sid,)).fetchone()
    return json.loads(row[0]) if row else None

def write_session(sid,d):
    with closing(db()) as c, c:
        c.execute("INSERT OR REPLACE INTO sessions VALUES (?,?)",(sid,json.dumps(d)))

SESSION_LOCKS={}; LOCKS_LOCK=threading.Lock()
def session_lock(sid):
    with LOCKS_LOCK: return SESSION_LOCKS.setdefault(sid,threading.RLock())

def fresh():
    return {"state":game.initial(),"events":[],"matches":[],"revision":0,"last_decision":None,"saved":False,"condition":"both"}

def call_api(path,payload=None):
    data=None if payload is None else json.dumps(payload).encode()
    req=request.Request(BASE+path,data=data,headers={"Content-Type":"application/json","Authorization":"Bearer "+KEY})
    try:
        with request.urlopen(req,timeout=TIMEOUT) as r: return json.load(r)
    except error.HTTPError as e:
        raise RuntimeError(f"Model endpoint returned HTTP {e.code}. Check the model ID and server logs.") from e
    except (error.URLError,TimeoutError) as e:
        raise RuntimeError("Qwen is unreachable or timed out. Check your vLLM port-forward or Service.") from e

def resolve_model():
    global MODEL
    if MODEL: return MODEL
    with MODEL_LOCK:
        if not MODEL:
            models=call_api("/models").get("data",[])
            if not models: raise RuntimeError("The endpoint lists no models.")
            MODEL=models[0]["id"]
    return MODEL

def decision(state,matches,mode="both",seed=7,shortlist=None):
    shortlist=shortlist if shortlist is not None else game.candidates(state)
    if not shortlist: raise ValueError("No decision is available after game over.")
    memory=game.histories(matches,mode)
    start=time.perf_counter()
    if OFFLINE:
        row=max(shortlist,key=lambda r:r["score"])
        return {"candidate_id":row["id"],"action":row["action"],"reason":"Offline baseline: chose a legal move using shortest-path scores; player history is not used.",
                "source":"offline","latency_ms":round((time.perf_counter()-start)*1000,1),"usage":{},"condition":mode,"history_count":len(memory)}
    prompt={"board":state,"coordinate_system":"x increases right; y increases down; board is 9x9",
            "you_are_player":state["turn"],"your_goal_row":0 if state["turn"]==0 else 8,
            "player_history":memory,"history_note":"Past habits are uncertain, not promises about future moves.",
            "legal_candidates":shortlist}
    payload={"model":resolve_model(),"messages":[
        {"role":"system","content":"You are a Quoridor opponent. Choose exactly one supplied legal candidate. Prioritize winning, good path lengths and preserving walls. Use historical player tendencies only when strategically relevant. Return JSON with candidate_id and a brief reason. Do not invent moves or claim hidden knowledge."},
        {"role":"user","content":json.dumps(prompt,separators=(",",":"))}],
        "temperature":0,"seed":seed,"max_tokens":180,
        "chat_template_kwargs":{"enable_thinking":False},
        "structured_outputs":{"json":SCHEMA}}
    with MAX_REQUESTS:
        response=call_api("/chat/completions",payload)
    try:
        content=response["choices"][0]["message"]["content"]
        parsed=json.loads(content)
        row=next(r for r in shortlist if r["id"]==parsed["candidate_id"])
        reason=parsed["reason"]
        if not isinstance(reason,str): raise ValueError()
    except (KeyError,ValueError,TypeError,StopIteration,IndexError) as e:
        raise RuntimeError("Qwen returned an invalid candidate. No move was applied; retry or inspect server compatibility.") from e
    return {"candidate_id":row["id"],"action":row["action"],"reason":reason[:500],
            "source":"qwen","model":payload["model"],"latency_ms":round((time.perf_counter()-start)*1000,1),
            "usage":response.get("usage",{}),"condition":mode,"history_count":len(memory)}

def metrics():
    if OFFLINE: return {"available":False,"reason":"Offline mode; no GPU inference."}
    root=BASE.removesuffix("/v1")
    try:
        req=request.Request(root+"/metrics",headers={"Authorization":"Bearer "+KEY})
        with request.urlopen(req,timeout=3) as r: lines=r.read().decode().splitlines()
        names={"vllm:num_requests_running","vllm:num_requests_waiting","vllm:kv_cache_usage_perc","vllm:gpu_cache_usage_perc"}
        out={}
        for line in lines:
            if not line or line.startswith("#"): continue
            key=line.split("{")[0].split()[0]
            if key in names:
                try: out[key]=out.get(key,0)+float(line.split()[-1])
                except ValueError: pass
        return {"available":bool(out),"values":out}
    except Exception: return {"available":False,"reason":"Metrics unavailable; decisions can still work."}

def exposed(d):
    s=d["state"]
    return {**d,"legal_moves":game.pawn_moves(s,0) if s["turn"]==0 and s["winner"] is None else [],
            "distances":[game.distance(s,0),game.distance(s,1)],"mode":"offline" if OFFLINE else "qwen"}

def finish(d):
    if d["state"]["winner"] is not None and not d["saved"]:
        result="win" if d["state"]["winner"]==0 else "loss"
        d["matches"].append(game.summarize(d["events"],result))
        d["matches"]=d["matches"][-12:]; d["saved"]=True

def route_post(path,body,sid):
    if path=="/api/reset-memory":
        d=fresh(); write_session(sid,d); return exposed(d)
    d=read_session(sid) or fresh()
    if path=="/api/new":
        keep=d["matches"]
        if body.get("save_partial") and d["events"] and not d["saved"]:
            keep=(keep+[game.summarize(d["events"],"unfinished")])[-12:]
        d=fresh(); d["matches"]=keep; write_session(sid,d); return exposed(d)
    if path=="/api/condition":
        if body.get("condition") not in ("none","one","two","both"): raise ValueError("Invalid memory condition.")
        d["condition"]=body["condition"]; write_session(sid,d); return exposed(d)
    if path=="/api/move":
        if body.get("revision")!=d["revision"]: raise ValueError("Board changed. Refresh and try again.")
        before=list(d["state"]["pawns"][0]); a=body.get("action")
        d["state"]=game.apply(d["state"],a,0)
        d["events"].append({"before":before,"action":a})
        d["revision"]+=1; finish(d); write_session(sid,d); return exposed(d)
    if path=="/api/ai":
        if d["state"]["turn"]!=1 or d["state"]["winner"] is not None: raise ValueError("It is not the opponent's turn.")
        if body.get("revision")!=d["revision"]: raise ValueError("Board changed. Refresh and try again.")
        out=decision(d["state"],d["matches"],d["condition"])
        d["state"]=game.apply(d["state"],out["action"],1); d["last_decision"]=out
        d["revision"]+=1; finish(d); write_session(sid,d); return exposed(d)
    if path=="/api/compare":
        s=deepcopy(d["state"])
        if s["winner"] is not None: raise ValueError("Start a new match to compare decisions.")
        # If it is your turn, compare hypothetical opponent decisions from the same board.
        s["turn"]=1; shortlist=game.candidates(s); modes=["none","one","two","both"]
        def run(mode):
            try: return decision(s,d["matches"],mode,shortlist=shortlist)
            except Exception as e: return {"condition":mode,"error":str(e),"source":"error"}
        t=time.perf_counter()
        with cf.ThreadPoolExecutor(max_workers=4) as pool: rows=list(pool.map(run,modes))
        return {"rows":rows,"wall_ms":round((time.perf_counter()-t)*1000,1),"snapshot":s,
                "revision":d["revision"],"shortlist":shortlist,"note":"Same board and legal shortlist; only completed/explicitly saved match history changes. Recommendations do not apply moves or prove win-rate improvement."}
    if path=="/api/benchmark":
        if OFFLINE: raise ValueError("The GPU benchmark requires Qwen. Restart without OFFLINE=1.")
        concurrency=body.get("concurrency",4)
        if type(concurrency)!=int or concurrency not in (4,8,32): raise ValueError("Choose 4, 8 or 32.")
        if not EXPERIMENT_LOCK.acquire(blocking=False): raise ValueError("Another benchmark is running.")
        try:
            # Independent, valid synthetic board positions. These are not match outcomes.
            positions=[]
            for i in range(concurrency):
                s=game.initial(); s["pawns"][0]=[i%9,8]; s["pawns"][1]=[(i*2)%9,0]; s["turn"]=1
                positions.append((s,game.candidates(s)))
            before=metrics(); stop=threading.Event(); sampled=[]
            def sample():
                while not stop.is_set():
                    m=metrics()
                    if m.get("available"): sampled.append(m["values"])
                    stop.wait(0.4)
            sampler=threading.Thread(target=sample,daemon=True); sampler.start()
            def run(item):
                i,(s,shortlist)=item
                try: return decision(s,d["matches"],"both",seed=i+7,shortlist=shortlist)
                except Exception as e: return {"error":str(e)}
            t=time.perf_counter()
            with cf.ThreadPoolExecutor(max_workers=concurrency) as pool: rows=list(pool.map(run,enumerate(positions)))
            wall=time.perf_counter()-t; stop.set(); sampler.join(timeout=4)
            good=[r for r in rows if "error" not in r]; lat=sorted(r["latency_ms"] for r in good)
            tokens=sum(r.get("usage",{}).get("completion_tokens",0) for r in good)
            peaks={k:max(x.get(k,0) for x in sampled) for k in {k for x in sampled for k in x}}
            return {"concurrency":concurrency,"successes":len(good),"failures":len(rows)-len(good),
                    "wall_seconds":round(wall,3),"decisions_per_second":round(len(good)/wall,3),
                    "completion_tokens_per_second":round(tokens/wall,2),
                    "p50_ms":round(statistics.median(lat),1) if lat else None,
                    "p95_ms":lat[min(len(lat)-1,int(len(lat)*0.95))] if lat else None,
                    "peak_metrics":peaks,"metrics_before":before,"errors":[r["error"] for r in rows if "error" in r],
                    "note":"One small decision-load run; not GPU utilization, TTFT, or evidence of stronger gameplay. Warm up and repeat identical runs for performance conclusions."}
        finally: EXPERIMENT_LOCK.release()
    raise ValueError("Unknown endpoint.")

class Handler(BaseHTTPRequestHandler):
    def log_message(self,fmt,*args): print(fmt%args,flush=True)
    def identify(self):
        cookie=SimpleCookie()
        try: cookie.load(self.headers.get("Cookie",""))
        except Exception: pass
        sid=cookie["aq_session"].value if "aq_session" in cookie else ""
        self.new_cookie=False
        if len(sid)!=48 or any(c not in "0123456789abcdef" for c in sid):
            sid=secrets.token_hex(24); self.new_cookie=True
        return sid
    def respond(self,code,data,content_type="application/json"):
        blob=json.dumps(data).encode() if content_type=="application/json" else data
        self.send_response(code); self.send_header("Content-Type",content_type)
        self.send_header("Content-Length",str(len(blob))); self.send_header("Cache-Control","no-store")
        self.send_header("X-Content-Type-Options","nosniff")
        if getattr(self,"new_cookie",False):
            self.send_header("Set-Cookie",f"aq_session={self.sid}; HttpOnly; SameSite=Strict; Path=/")
        self.end_headers(); self.wfile.write(blob)
    def do_GET(self):
        self.sid=self.identify(); path=parse.urlsplit(self.path).path
        if path=="/api/health":
            return self.respond(200,{"ok":True,"mode":"offline" if OFFLINE else "qwen"})
        if path=="/api/config":
            try: model="offline baseline" if OFFLINE else resolve_model(); connected=True; msg=None
            except Exception as e: model=MODEL or "unresolved"; connected=False; msg=str(e)
            return self.respond(200,{"mode":"offline" if OFFLINE else "qwen","model":model,"connected":connected,"error":msg})
        if path=="/api/metrics": return self.respond(200,metrics())
        if path=="/api/state":
            with session_lock(self.sid):
                d=read_session(self.sid) or fresh(); write_session(self.sid,d)
            return self.respond(200,exposed(d))
        asset={"/":"index.html","/style.css":"style.css","/app.js":"app.js"}.get(path)
        if asset:
            types={"index.html":"text/html; charset=utf-8","style.css":"text/css; charset=utf-8","app.js":"text/javascript; charset=utf-8"}
            return self.respond(200,(ROOT/asset).read_bytes(),types[asset])
        self.respond(404,{"error":"Not found"})
    def do_POST(self):
        self.sid=self.identify()
        # Same-origin app only; no browser credentials or arbitrary proxy endpoint.
        origin=self.headers.get("Origin")
        if origin and parse.urlsplit(origin).netloc!=self.headers.get("Host"):
            return self.respond(403,{"error":"Cross-origin request rejected."})
        try:
            size=int(self.headers.get("Content-Length","0"))
            if size<1 or size>16384: raise ValueError("Invalid request size.")
            body=json.loads(self.rfile.read(size))
            if not isinstance(body,dict): raise ValueError("JSON object required.")
            with session_lock(self.sid):
                result=route_post(parse.urlsplit(self.path).path,body,self.sid)
            self.respond(200,result)
        except (ValueError,json.JSONDecodeError) as e: self.respond(400,{"error":str(e)})
        except RuntimeError as e: self.respond(502,{"error":str(e)})
        except Exception:
            import traceback; traceback.print_exc()
            self.respond(500,{"error":"Server error; inspect the terminal logs."})

if __name__=="__main__":
    host=os.environ.get("HOST","127.0.0.1"); port=int(os.environ.get("PORT","8080"))
    print(f"Adaptive Quoridor: http://{host}:{port} | {'offline' if OFFLINE else BASE}",flush=True)
    ThreadingHTTPServer((host,port),Handler).serve_forever()
