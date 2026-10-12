import concurrent.futures as cf
import http.cookiejar
import json
import tempfile
import threading
import time
import unittest
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
from urllib import request,error
from pathlib import Path
import app,game

class FakeModel(BaseHTTPRequestHandler):
    calls=[]; lock=threading.Lock(); active=0; peak=0; invalid=False
    def log_message(self,*args): pass
    def send_json(self,d):
        b=json.dumps(d).encode();self.send_response(200);self.send_header("Content-Length",str(len(b)));self.end_headers();self.wfile.write(b)
    def do_GET(self):
        if self.path=="/v1/models": return self.send_json({"data":[{"id":"test-qwen"}]})
        if self.path=="/metrics":
            b=b'vllm:num_requests_running 4\nvllm:kv_cache_usage_perc 0.12\n'
            self.send_response(200);self.end_headers();self.wfile.write(b);return
        self.send_error(404)
    def do_POST(self):
        d=json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        prompt=json.loads(d["messages"][1]["content"])
        with self.lock:
            FakeModel.calls.append(d);FakeModel.active+=1;FakeModel.peak=max(self.peak,self.active)
        time.sleep(0.08)
        with self.lock: FakeModel.active-=1
        choice="invalid" if self.invalid else prompt["legal_candidates"][0]["id"]
        self.send_json({"choices":[{"message":{"content":json.dumps({"candidate_id":choice,"reason":"Mock decision"})}}],
                        "usage":{"prompt_tokens":100,"completion_tokens":20}})

class APITests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp=tempfile.TemporaryDirectory()
        app.DB_PATH=str(Path(cls.tmp.name)/"game.sqlite")
        cls.model=ThreadingHTTPServer(("127.0.0.1",0),FakeModel)
        cls.server=ThreadingHTTPServer(("127.0.0.1",0),app.Handler)
        app.BASE=f"http://127.0.0.1:{cls.model.server_port}/v1";app.MODEL="";app.OFFLINE=False
        cls.url=f"http://127.0.0.1:{cls.server.server_port}"
        for s in (cls.model,cls.server): threading.Thread(target=s.serve_forever,daemon=True).start()
    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown();cls.model.shutdown();cls.server.server_close();cls.model.server_close();cls.tmp.cleanup()
    def setUp(self):
        self.client=request.build_opener(request.HTTPCookieProcessor(http.cookiejar.CookieJar()))
        FakeModel.calls=[];FakeModel.peak=0;FakeModel.invalid=False
    def api(self,path,body=None):
        req=request.Request(self.url+"/api/"+path,data=None if body is None else json.dumps(body).encode(),headers={"Content-Type":"application/json"})
        with self.client.open(req) as r: return json.load(r)
    def test_model_discovery_and_live_move(self):
        self.assertTrue(self.api("config")["connected"])
        d=self.api("state")
        d=self.api("move",{"action":{"type":"move","x":4,"y":7},"revision":d["revision"]})
        d=self.api("ai",{"revision":d["revision"]})
        self.assertEqual(d["state"]["turn"],0)
        self.assertEqual(d["last_decision"]["source"],"qwen")
        self.assertEqual(FakeModel.calls[0]["model"],"test-qwen")
        self.assertFalse(FakeModel.calls[0]["chat_template_kwargs"]["enable_thinking"])
    def test_four_conditions_are_concurrent_and_controlled(self):
        self.api("state")
        for x in (3,5):
            d=self.api("new",{})
            self.api("move",{"action":{"type":"move","x":x,"y":8},"revision":d["revision"]})
            self.api("new",{"save_partial":True})
        result=self.api("compare",{})
        self.assertEqual([r["history_count"] for r in result["rows"]],[0,1,1,2])
        self.assertEqual(len(FakeModel.calls),4)
        prompts=[json.loads(d["messages"][1]["content"]) for d in FakeModel.calls]
        self.assertTrue(all(p["board"]==prompts[0]["board"] for p in prompts))
        self.assertTrue(all(p["legal_candidates"]==prompts[0]["legal_candidates"] for p in prompts))
        self.assertGreaterEqual(FakeModel.peak,4)
    def test_invalid_model_does_not_move(self):
        d=self.api("state")
        d=self.api("move",{"action":{"type":"move","x":4,"y":7},"revision":d["revision"]})
        FakeModel.invalid=True
        with self.assertRaises(error.HTTPError) as ctx: self.api("ai",{"revision":d["revision"]})
        self.assertEqual(ctx.exception.code,502)
        self.assertEqual(self.api("state")["state"],d["state"])
    def test_revision_and_session_isolation(self):
        d=self.api("state")
        with self.assertRaises(error.HTTPError):self.api("move",{"action":{"type":"move","x":4,"y":7},"revision":100})
        other=request.build_opener(request.HTTPCookieProcessor(http.cookiejar.CookieJar()))
        self.api("move",{"action":{"type":"move","x":4,"y":7},"revision":d["revision"]})
        with other.open(self.url+"/api/state") as r: other_d=json.load(r)
        self.assertEqual(other_d["state"]["ply"],0)
    def test_benchmark_four_requests(self):
        self.api("state")
        for level in (4,8,32):
            r=self.api("benchmark",{"concurrency":level})
            self.assertEqual(r["successes"],level);self.assertEqual(r["failures"],0)
            self.assertGreater(r["completion_tokens_per_second"],0)
            self.assertGreaterEqual(FakeModel.peak,4)
            self.assertEqual(r["peak_metrics"]["vllm:kv_cache_usage_perc"],0.12)
    def test_offline_is_explicit_and_benchmark_disabled(self):
        app.OFFLINE=True
        try:
            d=self.api("state")
            d=self.api("move",{"action":{"type":"move","x":4,"y":7},"revision":d["revision"]})
            d=self.api("ai",{"revision":d["revision"]})
            self.assertEqual(d["last_decision"]["source"],"offline")
            with self.assertRaises(error.HTTPError):self.api("benchmark",{"concurrency":4})
        finally: app.OFFLINE=False
    def test_cross_origin_rejected(self):
        req=request.Request(self.url+"/api/new",data=b'{}',headers={"Origin":"https://example.org","Content-Type":"application/json"})
        with self.assertRaises(error.HTTPError) as ctx:self.client.open(req)
        self.assertEqual(ctx.exception.code,403)
    def test_static_and_missing_path(self):
        for p in ("/","/style.css","/app.js"):
            with self.client.open(self.url+p) as r:self.assertEqual(r.status,200)
        with self.assertRaises(error.HTTPError):self.client.open(self.url+"/../app.py")
