"""Layout-adapter contract: equivalent geometry or a closed failure."""
import copy
import json
import subprocess
import unittest

from support import ROOT


class LayoutFormats(unittest.TestCase):
    legacy = "100x30,0,0{65x30,0,0,0,34x30,66,0,1}"

    def snapshot(self):
        return {"V": 2, "L": {"t": "h", "w": 100, "h": 30, "x": 0, "y": 0, "c": [
            {"t": "p", "w": 65, "h": 30, "x": 0, "y": 0, "a": True, "i": 0, "I": "%0"},
            {"t": "p", "w": 34, "h": 30, "x": 66, "y": 0, "l": 0, "i": 1, "I": "%1"}]}}

    def adapt(self, value, pane=None):
        args = ["awk"]
        if pane is not None:
            args.extend(["-v", "pane=" + str(pane)])
        args.extend(["-f", str(ROOT / "scripts" / "layout-remove.awk")])
        return subprocess.run(args, input=value + "\n", text=True, capture_output=True, timeout=5)

    def test_legacy_and_json_have_identical_geometry(self):
        for value in ("0000," + self.legacy, json.dumps(self.snapshot())):
            with self.subTest(value=value):
                result = self.adapt(value)
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertEqual(result.stdout.strip(), self.legacy)

    def test_legacy_and_json_predict_the_same_edge_removal(self):
        for value in ("0000," + self.legacy, json.dumps(self.snapshot())):
            with self.subTest(value=value):
                result = self.adapt(value, pane=1)
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertEqual(result.stdout.strip(), "100x30,0,0,0")

    def test_nested_vertical_json_matches_legacy(self):
        root = self.snapshot()
        root["L"]["c"][0] = {"t": "v", "w": 65, "h": 30, "x": 0, "y": 0, "c": [
            {"t": "p", "w": 65, "h": 14, "x": 0, "y": 0, "i": 0, "I": "%0"},
            {"t": "p", "w": 65, "h": 15, "x": 0, "y": 15, "i": 2, "I": "%2"}]}
        expected = "100x30,0,0{65x30,0,0[65x14,0,0,0,65x15,0,15,2],34x30,66,0,1}"
        for value in ("0000," + expected, json.dumps(root)):
            result = self.adapt(value)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(result.stdout.strip(), expected)

    def test_unsupported_or_inconsistent_snapshots_fail_closed(self):
        cases = []
        for change in ("version", "floating", "singleton", "width", "offset", "height", "duplicate"):
            data = copy.deepcopy(self.snapshot())
            root = data["L"]
            if change == "version": data["V"] = 3
            elif change == "floating": root["c"][0]["z"] = 1
            elif change == "singleton": root["c"] = root["c"][:1]
            elif change == "width": root["w"] = 99
            elif change == "offset": root["c"][1]["x"] = 65
            elif change == "height": root["c"][1]["h"] = 29
            elif change == "duplicate": root["c"][1]["I"] = "%0"
            cases.append((change, json.dumps(data)))
        cases.extend([
            ("legacy singleton", "100x30,0,0{100x30,0,0,0}"),
            ("legacy width", "99x30,0,0{65x30,0,0,0,34x30,66,0,1}"),
            ("legacy offset", "100x30,0,0{65x30,0,0,0,34x30,65,0,1}"),
            ("legacy height", "100x30,0,0{65x30,0,0,0,34x29,66,0,1}"),
            ("legacy duplicate", "100x30,0,0{65x30,0,0,0,34x30,66,0,0}"),
            ("legacy zero", "100x30,0,0{0x30,0,0,0,99x30,1,0,1}"),
            ("legacy origin", "100x30,1,0{65x30,1,0,0,34x30,67,0,1}"),
            ("truncated", '{"V":2,"L":'),
        ])
        for name, value in cases:
            with self.subTest(name=name):
                result = self.adapt(value)
                self.assertNotEqual(result.returncode, 0)
                self.assertEqual(result.stdout, "")
