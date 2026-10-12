import unittest
import game
from copy import deepcopy

class RulesTests(unittest.TestCase):
    def test_initial_distances(self):
        s=game.initial()
        self.assertEqual([game.distance(s,p) for p in (0,1)],[8,8])
        self.assertEqual(len(game.pawn_moves(s,0)),3)
    def test_illegal_move_and_wrong_turn(self):
        s=game.initial()
        with self.assertRaises(ValueError): game.apply(s,{"type":"move","x":4,"y":4})
        with self.assertRaises(ValueError): game.apply(s,{"type":"move","x":4,"y":1},1)
        self.assertEqual(s,game.initial())
    def test_wall_edges_and_resource(self):
        s=game.apply(game.initial(),{"type":"wall","x":4,"y":7,"orientation":"h"})
        self.assertEqual(s["remaining"],[9,10])
        self.assertNotIn({"type":"move","x":4,"y":7},game.pawn_moves(s,0))
        self.assertEqual(len(game.blocked_edges(s["walls"])),2)
    def test_overlap_cross_and_bounds(self):
        s=game.initial();s["walls"]=[{"x":3,"y":3,"orientation":"h"}]
        for a in [
            {"type":"wall","x":3,"y":3,"orientation":"h"},
            {"type":"wall","x":2,"y":3,"orientation":"h"},
            {"type":"wall","x":4,"y":3,"orientation":"h"},
            {"type":"wall","x":3,"y":3,"orientation":"v"},
            {"type":"wall","x":8,"y":3,"orientation":"h"}]:
            self.assertFalse(game.wall_legal(s,a,0))
        self.assertTrue(game.wall_legal(s,{"type":"wall","x":5,"y":3,"orientation":"h"},0))
    def test_path_cannot_be_closed(self):
        s=game.initial();s["pawns"][1]=[0,0]
        s["walls"]=[{"x":1,"y":0,"orientation":"v"}]
        self.assertIsNotNone(game.distance(s,1))
        self.assertFalse(game.wall_legal(s,{"type":"wall","x":0,"y":0,"orientation":"h"},0))
    def test_jump(self):
        s=game.initial();s["pawns"]=[[4,4],[4,3]]
        self.assertIn({"type":"move","x":4,"y":2},game.pawn_moves(s,0))
        self.assertNotIn({"type":"move","x":4,"y":3},game.pawn_moves(s,0))
        self.assertNotIn({"type":"move","x":3,"y":3},game.pawn_moves(s,0))
    def test_diagonal_when_jump_blocked(self):
        s=game.initial();s["pawns"]=[[4,4],[4,3]]
        s["walls"]=[{"x":4,"y":2,"orientation":"h"}]
        moves=game.pawn_moves(s,0)
        self.assertIn({"type":"move","x":3,"y":3},moves)
        self.assertIn({"type":"move","x":5,"y":3},moves)
        self.assertNotIn({"type":"move","x":4,"y":2},moves)
    def test_jump_at_board_edge(self):
        s=game.initial();s["pawns"]=[[4,1],[4,0]]
        self.assertIn({"type":"move","x":3,"y":0},game.pawn_moves(s,0))
        self.assertIn({"type":"move","x":5,"y":0},game.pawn_moves(s,0))
    def test_win_and_game_over(self):
        s=game.initial();s["pawns"]=[[3,1],[4,3]]
        s=game.apply(s,{"type":"move","x":3,"y":0})
        self.assertEqual(s["winner"],0)
        with self.assertRaises(ValueError): game.apply(s,{"type":"move","x":4,"y":4})
        self.assertEqual(game.candidates(s),[])
    def test_candidates_all_legal_and_memory_independent(self):
        s=game.initial();s["turn"]=1
        before=deepcopy(s)
        rows=game.candidates(s)
        self.assertEqual(s,before)
        self.assertEqual(len(set(r["id"] for r in rows)),len(rows))
        self.assertTrue(all(game.apply(s,r["action"],1) for r in rows))
    def test_memory_conditions(self):
        a={"preferred_lane":"left"};b={"preferred_lane":"right"}
        self.assertEqual(game.histories([a,b],"none"),[])
        self.assertEqual(game.histories([a,b],"one"),[a])
        self.assertEqual(game.histories([a,b],"two"),[b])
        self.assertEqual(game.histories([a,b],"both"),[a,b])
        self.assertEqual(game.histories([a],"two"),[])
    def test_history_summary(self):
        events=[{"before":[4,8],"action":{"type":"move","x":3,"y":8}},
                {"before":[3,8],"action":{"type":"wall","x":3,"y":3,"orientation":"h"}}]
        h=game.summarize(events,"unfinished")
        self.assertEqual(h["left_moves"],1)
        self.assertEqual(h["preferred_lane"],"left")
        self.assertEqual(h["first_wall_turn"],2)
        self.assertEqual(h["result"],"unfinished")
