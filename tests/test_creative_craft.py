from __future__ import annotations

import copy
import contextlib
import io
import importlib.util
import json
import tempfile
import unittest
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CLI_PATH = ROOT / "skills" / "creative-craft" / "scripts" / "creative_craft.py"
SPEC = importlib.util.spec_from_file_location("creative_craft_cli", CLI_PATH)
assert SPEC and SPEC.loader
cc = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = cc
SPEC.loader.exec_module(cc)


def load(rel: str) -> dict:
    return json.loads((ROOT / rel).read_text(encoding="utf-8"))


class DoctorTests(unittest.TestCase):
    def test_doctor_passes(self) -> None:
        result = cc.doctor(ROOT)
        self.assertEqual([], result.errors, result.errors)

    def test_package_self_test_passes(self) -> None:
        args = type("Args", (), {"root": str(ROOT), "json": False})()
        stdout = io.StringIO()
        with contextlib.redirect_stdout(stdout):
            self.assertEqual(0, cc.cmd_self_test(args))
        self.assertIn("PASS package self-test", stdout.getvalue())


class ImageJobTests(unittest.TestCase):
    def setUp(self) -> None:
        self.data = load("examples/premium-haircare-launch/image-job.json")

    def test_valid_image_job(self) -> None:
        result = cc.validate_image_job(self.data)
        self.assertTrue(result.ok, result.errors)

    def test_transparent_background_rejected(self) -> None:
        data = copy.deepcopy(self.data)
        data["canvas"]["background"] = "transparent"
        result = cc.validate_image_job(data)
        self.assertFalse(result.ok)
        self.assertTrue(any("background" in item for item in result.errors))

    def test_invalid_size_rejected(self) -> None:
        data = copy.deepcopy(self.data)
        data["canvas"]["size"] = "1000x1000"
        result = cc.validate_image_job(data)
        self.assertFalse(result.ok)
        self.assertTrue(any("multiples" in item for item in result.errors))

    def test_png_compression_rejected(self) -> None:
        data = copy.deepcopy(self.data)
        data["canvas"]["compression"] = 50
        result = cc.validate_image_job(data)
        self.assertFalse(result.ok)
        self.assertTrue(any("only for jpeg or webp" in item for item in result.errors))

    def test_webp_compression_accepted(self) -> None:
        data = copy.deepcopy(self.data)
        data["canvas"]["format"] = "webp"
        data["canvas"]["compression"] = 50
        result = cc.validate_image_job(data)
        self.assertTrue(result.ok, result.errors)

    def test_compiler_contains_reference_and_preserve(self) -> None:
        text = cc.compile_image_markdown(self.data)
        self.assertIn("REFERENCE MAP", text)
        self.assertIn("@product-pack-001", text)
        self.assertIn("PRESERVE EXACTLY", text)
        self.assertIn("prompt_ready", text)


class VideoJobTests(unittest.TestCase):
    def setUp(self) -> None:
        self.data = load("examples/premium-haircare-launch/video-job.json")

    def test_valid_video_job(self) -> None:
        result = cc.validate_video_job(self.data)
        self.assertTrue(result.ok, result.errors)

    def test_overlap_rejected(self) -> None:
        data = copy.deepcopy(self.data)
        data["timeline"][1]["start"] = 2
        result = cc.validate_video_job(data)
        self.assertFalse(result.ok)
        self.assertTrue(any("overlaps" in item for item in result.errors))

    def test_reference_limit_rejected(self) -> None:
        data = copy.deepcopy(self.data)
        data["references"] = [
            {"asset_id": f"image-{i}", "kind": "image", "role": "test"}
            for i in range(31)
        ]
        result = cc.validate_video_job(data)
        self.assertFalse(result.ok)
        self.assertTrue(any("reference count" in item for item in result.errors))

    def test_compiler_contains_timeline_and_audio(self) -> None:
        text = cc.compile_video_markdown(self.data)
        self.assertIn("TIMESTAMPED BEATS", text)
        self.assertIn("0–3s", text)
        self.assertIn("DIALOGUE / VOICE", text)
        self.assertIn("prompt_ready", text)


class EvaluationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.data = load("examples/premium-haircare-launch/evaluation.json")

    def test_scored(self) -> None:
        result = cc.score_evaluation(self.data)
        self.assertEqual("scored", result["status"])
        self.assertEqual(100.0, result["coverage"])
        self.assertGreater(result["score"], 80)

    def test_blocked_gate(self) -> None:
        data = copy.deepcopy(self.data)
        data["gates"]["rights_clear"] = False
        result = cc.score_evaluation(data)
        self.assertEqual("blocked", result["status"])
        self.assertIn("rights_clear", result["failed_gates"])

    def test_withheld_for_low_coverage(self) -> None:
        data = copy.deepcopy(self.data)
        for dim in data["dimensions"][2:]:
            dim["evidence_state"] = "UNVERIFIED"
        result = cc.score_evaluation(data)
        self.assertEqual("withheld", result["status"])
        self.assertLess(result["coverage"], 80)


class SeedTests(unittest.TestCase):
    def test_seed_and_refuse_overwrite(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            args = type("Args", (), {"target": directory, "force": False})()
            stdout = io.StringIO()
            stderr = io.StringIO()
            with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
                self.assertEqual(0, cc.cmd_seed(args))
                self.assertTrue((Path(directory) / "BRAND.md").is_file())
                self.assertEqual(1, cc.cmd_seed(args))
            self.assertIn("refusing to overwrite", stderr.getvalue())


if __name__ == "__main__":
    unittest.main()
