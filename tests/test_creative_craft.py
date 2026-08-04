from __future__ import annotations

import contextlib
import copy
import importlib.util
import io
import json
import shutil
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
CLI_PATH = ROOT / "skills" / "creative-craft" / "scripts" / "creative_craft.py"
SPEC = importlib.util.spec_from_file_location("creative_craft_cli", CLI_PATH)
assert SPEC and SPEC.loader
cc = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = cc
SPEC.loader.exec_module(cc)

INSTALLER_PATH = ROOT / "scripts" / "install_skill.py"
INSTALLER_SPEC = importlib.util.spec_from_file_location("creative_craft_installer", INSTALLER_PATH)
assert INSTALLER_SPEC and INSTALLER_SPEC.loader
installer = importlib.util.module_from_spec(INSTALLER_SPEC)
sys.modules[INSTALLER_SPEC.name] = installer
INSTALLER_SPEC.loader.exec_module(installer)


def load(rel: str) -> dict:
    return json.loads((ROOT / rel).read_text(encoding="utf-8"))


def write_json(path: Path, data: dict) -> None:
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def refresh_manifest(root: Path) -> dict:
    manifest_path = root / "project-manifest.json"
    if not manifest_path.is_file():
        manifest_path = root / ".creative-craft" / "project-manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    for entry in manifest["artifacts"]:
        entry["sha256"] = cc.sha256_file(root / entry["path"])
    write_json(manifest_path, manifest)
    return manifest


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

    def test_doctor_uses_profiles_from_requested_root(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            copied = Path(directory) / "repo"
            shutil.copytree(
                ROOT,
                copied,
                ignore=shutil.ignore_patterns(".git", "__pycache__", "*.pyc"),
            )
            profile_path = copied / "skills/creative-craft/providers/openai-gpt-image-2.json"
            profile = json.loads(profile_path.read_text(encoding="utf-8"))
            profile["profile_id"] = "copied-root.invalid-profile"
            write_json(profile_path, profile)
            result = cc.doctor(copied)
            self.assertFalse(result.ok)
            self.assertTrue(any(cc.IMAGE_PROFILE_ID in item for item in result.errors))


class ImageJobTests(unittest.TestCase):
    def setUp(self) -> None:
        self.data = load("examples/premium-haircare-launch/image-job.json")

    def test_valid_image_job(self) -> None:
        result = cc.validate_image_job(self.data)
        self.assertTrue(result.ok, result.errors)

    def test_public_validation_rejects_additional_property(self) -> None:
        data = copy.deepcopy(self.data)
        data["unexpected_field"] = True
        _, result = cc.validate_data(data)
        self.assertFalse(result.ok)
        self.assertTrue(any("not allowed" in item for item in result.errors))

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
        self.assertIn("declared status `ready`", text)


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

    def test_unavailable_execution_surface_rejected(self) -> None:
        data = copy.deepcopy(self.data)
        data["execution_surface"] = "byteplus.modelark_api"
        result = cc.validate_video_job(data)
        self.assertFalse(result.ok)
        self.assertTrue(any("not currently available" in item for item in result.errors))

    def test_compiler_contains_timeline_and_audio(self) -> None:
        text = cc.compile_video_markdown(self.data)
        self.assertIn("TIMESTAMPED BEATS", text)
        self.assertIn("0–3s", text)
        self.assertIn("DIALOGUE / VOICE", text)
        self.assertIn("declared status `ready`", text)


class EvaluationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.data = load("examples/premium-haircare-launch/evaluation.json")
        self.graph = cc.validate_project(ROOT / "examples/premium-haircare-launch")

    def test_scored(self) -> None:
        result = cc.score_evaluation(self.data, self.graph)
        self.assertEqual("scored", result["status"])
        self.assertEqual(100.0, result["coverage"])
        self.assertGreater(result["score"], 80)

    def test_blocked_gate(self) -> None:
        ledger = self.graph.record("asset-ledger", "northstar-assets-v1")
        ledger["data"]["assets"][0]["rights_status"] = "UNVERIFIED"
        result = cc.score_evaluation(self.data, self.graph)
        self.assertEqual("blocked", result["status"])
        self.assertIn("rights_clear", result["failed_gates"])

    def test_withheld_for_low_coverage(self) -> None:
        data = copy.deepcopy(self.data)
        for dim in data["dimensions"][2:]:
            dim["evidence_state"] = "UNVERIFIED"
            dim["evidence_refs"] = []
        result = cc.score_evaluation(data, self.graph)
        self.assertEqual("withheld", result["status"])
        self.assertLess(result["coverage"], 80)

    def test_v2_hypotheses_reduce_strength_and_confidence(self) -> None:
        data = load("examples/premium-haircare-launch/evaluation.json")
        graph = cc.validate_project(ROOT / "examples/premium-haircare-launch")
        for dimension in data["dimensions"]:
            dimension["evidence_state"] = "HYPOTHESIZED"
        result = cc.score_evaluation(data, graph)
        self.assertEqual("scored", result["status"])
        self.assertEqual(100.0, result["coverage"])
        self.assertEqual(40.0, result["evidence_strength"])
        self.assertEqual("WEAK", result["confidence"])

    def test_v2_gate_is_derived_from_project_evidence(self) -> None:
        data = load("examples/premium-haircare-launch/evaluation.json")
        graph = cc.validate_project(ROOT / "examples/premium-haircare-launch")
        graph.record("brief", "northstar-airlift-launch-v1")["data"]["status"] = "draft"
        result = cc.score_evaluation(data, graph)
        self.assertEqual("blocked", result["status"])
        self.assertIn("brief_locked", result["failed_gates"])


class SeedTests(unittest.TestCase):
    def test_seed_and_refuse_overwrite(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            args = type("Args", (), {"target": directory, "force": False})()
            stdout = io.StringIO()
            stderr = io.StringIO()
            with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
                self.assertEqual(0, cc.cmd_seed(args))
                self.assertTrue((Path(directory) / "BRAND.md").is_file())
                self.assertTrue((Path(directory) / ".creative-craft/critique.json").is_file())
                self.assertTrue(cc.validate_project(Path(directory)).result.ok)
                self.assertEqual(1, cc.cmd_seed(args))
            self.assertIn("refusing to overwrite", stderr.getvalue())


class ArtifactSemanticTests(unittest.TestCase):
    def test_legacy_contracts_remain_readable(self) -> None:
        for name in ("image-job-v1", "video-job-v1", "evaluation-v1", "delivery-v1"):
            data = load(f"tests/fixtures/legacy/{name}.json")
            _, result = cc.validate_data(data)
            self.assertTrue(result.ok, f"{name}: {result.errors}")

    def test_approved_inspection_requires_decisive_checks(self) -> None:
        inspection = load("skills/creative-craft/templates/output-inspection.json")
        inspection.update({
            "decision": "approved",
            "inspector": "reviewer",
            "inspected_at": "2026-08-04T00:00:00Z",
            "approval": {
                "approved_by": "owner",
                "approved_at": "2026-08-04T00:01:00Z",
                "approval_basis": "Reviewed output.",
            },
        })
        _, result = cc.validate_data(inspection)
        self.assertFalse(result.ok)
        self.assertTrue(any("requires invariant_checks" in item for item in result.errors))


class ProjectGraphTests(unittest.TestCase):
    def copy_example(self, directory: str) -> Path:
        target = Path(directory) / "project"
        shutil.copytree(ROOT / "examples/premium-haircare-launch", target)
        return target

    def test_valid_example_graph(self) -> None:
        graph = cc.validate_project(ROOT / "examples/premium-haircare-launch")
        self.assertTrue(graph.result.ok, graph.result.errors)
        self.assertEqual("ready", graph.job_statuses["northstar-motion-proof-hero-image-v1"])

    def test_missing_brief_reference_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            project = self.copy_example(directory)
            job_path = project / "image-job.json"
            job = json.loads(job_path.read_text(encoding="utf-8"))
            job["brief_id"] = "missing-brief"
            write_json(job_path, job)
            refresh_manifest(project)
            graph = cc.validate_project(project)
            self.assertFalse(graph.result.ok)
            self.assertTrue(any("missing brief_id" in item for item in graph.result.errors))

    def test_manifest_digest_drift_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            project = self.copy_example(directory)
            path = project / "image-job.json"
            path.write_text(path.read_text(encoding="utf-8") + "\n", encoding="utf-8")
            graph = cc.validate_project(project)
            self.assertFalse(graph.result.ok)
            self.assertTrue(any("sha256 mismatch" in item for item in graph.result.errors))

    def test_manifest_path_traversal_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            project = self.copy_example(directory)
            manifest_path = project / "project-manifest.json"
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            manifest["artifacts"][0]["path"] = "../creative-brief.json"
            write_json(manifest_path, manifest)
            graph = cc.validate_project(project)
            self.assertFalse(graph.result.ok)
            self.assertTrue(any("unsafe project-relative path" in item
                                for item in graph.result.errors))

    def test_ready_job_requires_cleared_referenced_assets(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            project = self.copy_example(directory)
            ledger_path = project / "asset-ledger.json"
            ledger = json.loads(ledger_path.read_text(encoding="utf-8"))
            ledger["assets"][0]["rights_status"] = "UNVERIFIED"
            write_json(ledger_path, ledger)
            refresh_manifest(project)
            graph = cc.validate_project(project)
            self.assertFalse(graph.result.ok)
            self.assertTrue(any("has unresolved rights" in item
                                for item in graph.result.errors))

    def test_receipt_and_inspection_project_status_is_derived(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            project = self.copy_example(directory)
            output_path = project / "outputs/hero.bin"
            output_path.parent.mkdir()
            output_path.write_bytes(b"synthetic-output")
            job_path = project / "image-job.json"
            receipt = {
                "schema_version": "creative-craft.execution-receipt.v1",
                "receipt_id": "receipt-hero-1",
                "job_id": "northstar-motion-proof-hero-image-v1",
                "job_sha256": cc.sha256_file(job_path),
                "provider_profile": cc.IMAGE_PROFILE_ID,
                "execution_surface": "openai.image_api",
                "model": "gpt-image-2",
                "snapshot": "gpt-image-2-2026-04-21",
                "host": "synthetic-test",
                "operator": "unittest",
                "started_at": "2026-08-04T00:00:00Z",
                "completed_at": "2026-08-04T00:00:01Z",
                "outcome": "succeeded",
                "request_or_prompt_sha256": "1" * 64,
                "parameters": {},
                "provider_execution_id": "synthetic-1",
                "outputs": [{
                    "asset_id": "hero-output-1",
                    "path": "outputs/hero.bin",
                    "sha256": cc.sha256_file(output_path),
                    "mime_type": "application/octet-stream",
                    "bytes": output_path.stat().st_size,
                }],
                "provider_errors": [],
                "moderation_result": None,
                "limitations": ["Synthetic fixture; not a provider output."],
            }
            receipt_path = project / "execution-receipt.json"
            write_json(receipt_path, receipt)
            manifest = refresh_manifest(project)
            manifest["artifacts"].append({
                "artifact_type": "execution-receipt",
                "artifact_id": "receipt-hero-1",
                "schema_version": "creative-craft.execution-receipt.v1",
                "path": "execution-receipt.json",
                "sha256": cc.sha256_file(receipt_path),
            })
            write_json(project / "project-manifest.json", manifest)
            graph = cc.validate_project(project)
            self.assertTrue(graph.result.ok, graph.result.errors)
            self.assertEqual("generated", graph.job_statuses["northstar-motion-proof-hero-image-v1"])

            inspection_path = project / "output-inspection.json"
            args = type("Args", (), {
                "job": str(job_path),
                "receipt": str(receipt_path),
                "file": str(output_path),
                "output": str(inspection_path),
                "inspector": "unittest",
                "force": False,
            })()
            with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
                self.assertEqual(0, cc.cmd_inspect_output(args))
            inspection = json.loads(inspection_path.read_text(encoding="utf-8"))
            self.assertEqual("deferred", inspection["decision"])
            self.assertIn("not been completed", inspection["remaining_unknowns"][0])
            inspection.update({
                "inspection_id": "inspection-hero-1",
                "job_id": receipt["job_id"],
                "receipt_id": receipt["receipt_id"],
                "output_asset_id": "hero-output-1",
                "output_sha256": cc.sha256_file(output_path),
                "inspector": "unittest",
                "inspected_at": "2026-08-04T00:01:00Z",
                "decision": "approved",
                "invariant_checks": [{
                    "id": "synthetic-invariant",
                    "status": "pass",
                    "observation": "Synthetic fixture invariant passed.",
                    "interpretation": "Lifecycle projection test only.",
                }],
                "rights_checks": [{
                    "id": "synthetic-rights",
                    "status": "pass",
                    "observation": "Synthetic fixture rights passed.",
                    "interpretation": "Lifecycle projection test only.",
                }],
                "approval": {
                    "approved_by": "fixture-owner",
                    "approved_at": "2026-08-04T00:02:00Z",
                    "approval_basis": "Synthetic lifecycle test only.",
                },
                "remaining_unknowns": [],
            })
            write_json(inspection_path, inspection)
            manifest["artifacts"].append({
                "artifact_type": "output-inspection",
                "artifact_id": "inspection-hero-1",
                "schema_version": "creative-craft.output-inspection.v1",
                "path": "output-inspection.json",
                "sha256": cc.sha256_file(inspection_path),
            })
            write_json(project / "project-manifest.json", manifest)
            graph = cc.validate_project(project)
            self.assertTrue(graph.result.ok, graph.result.errors)
            self.assertEqual("approved", graph.job_statuses["northstar-motion-proof-hero-image-v1"])

            delivery_path = project / "delivery-manifest.json"
            delivery = json.loads(delivery_path.read_text(encoding="utf-8"))
            delivery.update({
                "status": "delivered",
                "receipt_refs": ["cc://execution-receipt/receipt-hero-1#"],
                "inspection_refs": ["cc://output-inspection/inspection-hero-1#"],
                "files": [{
                    "asset_id": "hero-output-1",
                    "path": "outputs/hero.bin",
                    "sha256": cc.sha256_file(output_path),
                    "mime_type": "application/octet-stream",
                    "bytes": output_path.stat().st_size,
                    "job_id": receipt["job_id"],
                    "receipt_id": receipt["receipt_id"],
                    "inspection_id": inspection["inspection_id"],
                    "rights_status": "CLEARED",
                    "known_limitations": ["Synthetic lifecycle fixture only."],
                }],
            })
            write_json(delivery_path, delivery)
            refresh_manifest(project)
            graph = cc.validate_project(project)
            self.assertTrue(graph.result.ok, graph.result.errors)
            self.assertEqual("delivered", graph.job_statuses["northstar-motion-proof-hero-image-v1"])
            args = type("Args", (), {
                "root": str(project),
                "file": str(delivery_path),
                "json": True,
            })()
            with contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(0, cc.cmd_verify_delivery(args))


class InstallerTests(unittest.TestCase):
    def test_atomic_install_writes_provenance(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            destination, backup = installer.install(Path(directory), False)
            self.assertIsNone(backup)
            self.assertTrue((destination / "SKILL.md").is_file())
            self.assertTrue((destination / "INSTALL_PROVENANCE.json").is_file())

    def test_failed_force_install_preserves_existing_destination(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            destination = Path(directory) / "creative-craft"
            destination.mkdir()
            marker = destination / "marker.txt"
            marker.write_text("preserve", encoding="utf-8")
            with (
                mock.patch.object(installer, "validate_staging", side_effect=RuntimeError("boom")),
                self.assertRaises(RuntimeError),
            ):
                installer.install(Path(directory), True)
            self.assertEqual("preserve", marker.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
