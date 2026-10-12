"""Quoridor rules and history features. Coordinates: x right, y down."""
from collections import deque
from copy import deepcopy
N = 9
DIRECTIONS = ((0,-1),(1,0),(0,1),(-1,0))

def initial():
    return {"pawns":[[4,8],[4,0]],"walls":[],"remaining":[10,10],"turn":0,"winner":None,"ply":0}

def blocked_edges(walls):
    edges=set()
    for w in walls:
        x,y=w["x"],w["y"]
        if w["orientation"]=="h":
            pairs=[((x,y),(x,y+1)),((x+1,y),(x+1,y+1))]
        else:
            pairs=[((x,y),(x+1,y)),((x,y+1),(x+1,y+1))]
        edges.update(frozenset(p) for p in pairs)
    return edges

def inside(p): return 0<=p[0]<N and 0<=p[1]<N
def open_edge(a,b,edges): return inside(b) and frozenset((tuple(a),tuple(b))) not in edges

def distance(state,player):
    start=tuple(state["pawns"][player]); goal=0 if player==0 else N-1
    edges=blocked_edges(state["walls"]); q=deque([(start,0)]); seen={start}
    while q:
        p,d=q.popleft()
        if p[1]==goal: return d
        for dx,dy in DIRECTIONS:
            n=(p[0]+dx,p[1]+dy)
            if open_edge(p,n,edges) and n not in seen:
                seen.add(n); q.append((n,d+1))
    return None

def pawn_moves(state,player):
    p=tuple(state["pawns"][player]); other=tuple(state["pawns"][1-player])
    edges=blocked_edges(state["walls"]); destinations=set()
    for dx,dy in DIRECTIONS:
        n=(p[0]+dx,p[1]+dy)
        if not open_edge(p,n,edges): continue
        if n!=other:
            destinations.add(n); continue
        beyond=(n[0]+dx,n[1]+dy)
        if open_edge(n,beyond,edges):
            destinations.add(beyond)
        else:
            for sx,sy in ((-dy,dx),(dy,-dx)):
                side=(n[0]+sx,n[1]+sy)
                if open_edge(n,side,edges): destinations.add(side)
    return [{"type":"move","x":x,"y":y} for x,y in sorted(destinations)]

def wall_legal(state,action,player):
    x,y=action.get("x"),action.get("y"); o=action.get("orientation")
    if type(x)!=int or type(y)!=int or not (0<=x<N-1 and 0<=y<N-1): return False
    if o not in ("h","v") or state["remaining"][player]<=0: return False
    for w in state["walls"]:
        if w["x"]==x and w["y"]==y: return False
        if w["orientation"]==o:
            if o=="h" and w["y"]==y and abs(w["x"]-x)<=1: return False
            if o=="v" and w["x"]==x and abs(w["y"]-y)<=1: return False
    s=deepcopy(state); s["walls"].append({"x":x,"y":y,"orientation":o})
    return all(distance(s,p) is not None for p in (0,1))

def apply(state,action,player=None):
    player=state["turn"] if player is None else player
    if state["winner"] is not None: raise ValueError("This match has finished.")
    if state["turn"]!=player: raise ValueError("It is not this player's turn.")
    if not isinstance(action,dict): raise ValueError("Invalid move.")
    if action.get("type")=="move":
        clean={"type":"move","x":action.get("x"),"y":action.get("y")}
        if type(clean["x"])!=int or type(clean["y"])!=int or clean not in pawn_moves(state,player):
            raise ValueError("That pawn move is not legal.")
    elif action.get("type")=="wall":
        if not wall_legal(state,action,player):
            raise ValueError("Walls cannot overlap, cross, or close every route.")
        clean={"type":"wall","x":action["x"],"y":action["y"],"orientation":action["orientation"]}
    else: raise ValueError("Unknown action.")
    s=deepcopy(state)
    if clean["type"]=="move":
        s["pawns"][player]=[clean["x"],clean["y"]]
        if clean["y"]==(0 if player==0 else N-1): s["winner"]=player
    else:
        s["walls"].append({k:clean[k] for k in ("x","y","orientation")})
        s["remaining"][player]-=1
    s["turn"]=1-player; s["ply"]+=1
    return s

def candidates(state,player=None):
    """Memory-independent shortlist: all pawn moves + top 6 legal walls."""
    player=state["turn"] if player is None else player
    if state["winner"] is not None: return []
    base_self=distance(state,player); base_other=distance(state,1-player)
    moves=pawn_moves(state,player)
    walls=[]
    if state["remaining"][player]:
        for o in ("h","v"):
            for y in range(N-1):
                for x in range(N-1):
                    a={"type":"wall","x":x,"y":y,"orientation":o}
                    if wall_legal(state,a,player): walls.append(a)
    def describe(a):
        nxt=apply(state,a,player)
        ds,do=distance(nxt,player),distance(nxt,1-player)
        win=nxt["winner"]==player
        score=1000 if win else 1.25*(do-base_other)-(ds-base_self)-(0.22 if a["type"]=="wall" else 0)
        return {"action":a,"self_distance":ds,"opponent_distance":do,"score":round(score,3),"winning":win}
    descriptions=[describe(a) for a in moves]
    wall_rows=sorted((describe(a) for a in walls),key=lambda r:r["score"],reverse=True)[:6]
    descriptions+=wall_rows
    for i,row in enumerate(descriptions): row["id"]=f"c{i}"
    return descriptions

def summarize(events,result):
    moves=[e for e in events if e["action"]["type"]=="move"]
    walls=[e for e in events if e["action"]["type"]=="wall"]
    left=sum(e["action"]["x"]<e["before"][0] for e in moves)
    right=sum(e["action"]["x"]>e["before"][0] for e in moves)
    cols=[e["action"]["x"] for e in moves]
    lane="left" if sum(x<4 for x in cols)>sum(x>4 for x in cols) else "right" if sum(x>4 for x in cols)>sum(x<4 for x in cols) else "center / mixed"
    return {"player_turns":len(events),"pawn_moves":len(moves),"left_moves":left,"right_moves":right,
            "preferred_lane":lane,"walls_placed":len(walls),
            "first_wall_turn":events.index(walls[0])+1 if walls else None,"result":result,
            "move_trace":[e["action"] for e in events][-24:]}

def histories(matches,mode):
    recent=matches[-2:]
    if mode=="none": return []
    if mode=="one": return recent[:1]
    if mode=="two": return recent[1:2]
    if mode=="both": return recent
    raise ValueError("Unknown memory condition.")
