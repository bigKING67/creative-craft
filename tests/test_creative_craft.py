from __future__ import annotations

import contextlib
import copy
import importlib.util
import io
import json
import shutil
import subprocess
import sys
import tarfile
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

BUILD_RELEASE_PATH = ROOT / "scripts" / "build_release.py"
BUILD_RELEASE_SPEC = importlib.util.spec_from_file_location(
    "creative_craft_build_release", BUILD_RELEASE_PATH
)
assert BUILD_RELEASE_SPEC and BUILD_RELEASE_SPEC.loader
build_release = importlib.util.module_from_spec(BUILD_RELEASE_SPEC)
sys.modules[BUILD_RELEASE_SPEC.name] = build_release
BUILD_RELEASE_SPEC.loader.exec_module(build_release)

PACKAGE_SMOKE_PATH = ROOT / "scripts" / "package_smoke.py"
PACKAGE_SMOKE_SPEC = importlib.util.spec_from_file_location(
    "creative_craft_package_smoke", PACKAGE_SMOKE_PATH
)
assert PACKAGE_SMOKE_SPEC and PACKAGE_SMOKE_SPEC.loader
package_smoke = importlib.util.module_from_spec(PACKAGE_SMOKE_SPEC)
sys.modules[PACKAGE_SMOKE_SPEC.name] = package_smoke
PACKAGE_SMOKE_SPEC.loader.exec_module(package_smoke)


def load(rel: str) -> dict:
    return json.loads((ROOT / rel).read_text(encoding="utf-8"))


def write_json(path: Path, data: dict) -> None:
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def tree_snapshot(root: Path) -> dict[str, tuple[str, bytes | str | None]]:
    snapshot: dict[str, tuple[str, bytes | str | None]] = {}
    for path in sorted(root.rglob("*"), key=lambda item: item.relative_to(root).as_posix()):
        relative = path.relative_to(root).as_posix()
        if path.is_symlink():
            snapshot[relative] = ("symlink", str(path.readlink()))
        elif path.is_dir():
            snapshot[relative] = ("dir", None)
        else:
            snapshot[relative] = ("file", path.read_bytes())
    return snapshot


def refresh_manifest(root: Path) -> dict:
    manifest_path = root / "project-manifest.json"
    if not manifest_path.is_file():
        manifest_path = root / ".creative-craft" / "project-manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    for entry in manifest["artifacts"]:
        entry["sha256"] = cc.sha256_file(root / entry["path"])
    write_json(manifest_path, manifest)
    return manifest


def init_brand_pack(root: Path, brand_id: str = "acme", brand_name: str = "Acme") -> Path:
    skill_root = root / f"{brand_id}-brand"
    args = type("Args", (), {
        "target": str(skill_root),
        "brand_id": brand_id,
        "brand_name": brand_name,
        "owner": "fixture-owner",
        "force": False,
    })()
    with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
        if cc.cmd_init_brand_pack(args) != 0:
            raise AssertionError("Brand Pack fixture initialization failed")
    return skill_root


def approve_brand_pack(
    skill_root: Path, version: str = "0.1.0", *, require_valid: bool = True
) -> dict:
    manifest_path = skill_root / "brand-pack.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest.update({
        "version": version,
        "status": "approved",
        "approved_at": "2026-08-04T00:00:00Z",
        "review_after": "2027-08-04T00:00:00Z",
        "source_references": [{
            "source_id": "fixture-authority",
            "uri": "https://brand.invalid/authority",
            "version": version,
            "reviewed_at": "2026-08-04T00:00:00Z",
            "notes": "Synthetic test authority only.",
        }],
    })
    for item in manifest["authority_files"]:
        authority_path = skill_root / item["path"]
        authority_path.write_text(
            f"# Reviewed {item['role']} authority\n\n"
            "Status: `APPROVED`\n\nSynthetic fixture authority; no real brand claim.\n",
            encoding="utf-8",
        )
        item["sha256"] = cc.sha256_file(authority_path)
    write_json(manifest_path, manifest)
    graph = cc.validate_brand_pack(skill_root)
    if require_valid and not graph.result.ok:
        raise AssertionError(graph.result.errors)
    return manifest


def bind_brand_pack(project: Path, skill_root: Path) -> None:
    args = type("Args", (), {
        "brand_source_uri": "https://git.invalid/acme-brand-pack.git",
        "brand_source_ref": "main",
        "brand_source_commit": "1" * 40,
        "imported_by": "fixture-operator",
        "reason": "Initial fixture binding",
    })()
    cc._install_brand_snapshot(
        project,
        skill_root,
        args,
        require_existing_binding=False,
        retain_backup=False,
    )


def init_reference_pack(
    root: Path,
    pack_id: str = "reference-fixture",
    name: str = "Reference Fixture",
) -> Path:
    skill_root = root / pack_id
    args = type("Args", (), {
        "target": str(skill_root),
        "pack_id": pack_id,
        "name": name,
        "owner": "fixture-owner",
        "force": False,
    })()
    with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
        if cc.cmd_init_reference_pack(args) != 0:
            raise AssertionError("Reference Pack fixture initialization failed")
    return skill_root


def add_reference_entity(
    skill_root: Path,
    reference_id: str,
    *,
    with_asset: bool = False,
    rights_status: str = "CLEARED",
    rights_policy: str | None = None,
) -> dict:
    manifest_path = skill_root / "reference-pack.json"
    ledger_path = skill_root / "asset-ledger.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    ledger = json.loads(ledger_path.read_text(encoding="utf-8"))
    source_id = f"source-{reference_id}"
    asset_refs: list[str] = []
    if with_asset:
        asset_id = f"asset-{reference_id}"
        asset_path = skill_root / "assets" / "approved" / f"{reference_id}.bin"
        asset_path.parent.mkdir(parents=True, exist_ok=True)
        asset_path.write_bytes(f"synthetic-{reference_id}".encode())
        asset_refs.append(asset_id)
        ledger["assets"].append({
            "asset_id": asset_id,
            "path_or_uri": asset_path.relative_to(skill_root).as_posix(),
            "mime_type": "application/octet-stream",
            "sha256": cc.sha256_file(asset_path),
            "creator": "fixture",
            "owner": "fixture",
            "rights_status": rights_status,
            "consent_status": "NOT_APPLICABLE",
            "allowed_use": ["synthetic-tests"],
            "expires_at": None,
            "reference_roles": ["research"],
            "parent_assets": [],
            "notes": "Synthetic test asset only.",
        })
    manifest["source_references"].append({
        "source_id": source_id,
        "authority": "research",
        "uri": f"https://reference.invalid/{reference_id}",
        "captured_at": "2026-08-04T00:00:00Z",
        "snapshot_path": None,
        "sha256": None,
        "notes": "Synthetic test source only.",
    })
    manifest["entities"].append({
        "reference_id": reference_id,
        "entity_type": "other",
        "name": f"Synthetic {reference_id}",
        "relationship": "reference",
        "summary": "Synthetic test reference only.",
        "source_refs": [source_id],
        "observations": [{
            "observation_id": f"observation-{reference_id}",
            "dimension": "synthetic-test",
            "evidence_state": "OBSERVED",
            "statement": "Synthetic observation for contract testing.",
            "evidence_refs": [source_id],
        }],
        "transferable_principles": [{
            "principle_id": f"principle-{reference_id}",
            "derived_from": [f"observation-{reference_id}"],
            "statement": "Adapt the abstract principle; do not copy expression.",
            "application_scope": ["synthetic-tests"],
            "adaptation_required": True,
            "must_preserve_primary_brand": ["identity", "claims", "rights"],
        }],
        "non_transferable_elements": ["identity", "distinctive expression"],
        "applicable_to": ["synthetic-tests"],
        "reference_roles": ["principle"],
        "rights_policy": rights_policy or (
            "approved_reference_input" if with_asset else "principle_only"
        ),
        "prohibited_use": ["identity imitation"],
        "asset_refs": asset_refs,
        "may_override_primary_brand": False,
    })
    write_json(ledger_path, ledger)
    manifest["asset_ledger"]["sha256"] = cc.sha256_file(ledger_path)
    write_json(manifest_path, manifest)
    graph = cc.validate_reference_pack(skill_root)
    if not graph.result.ok:
        raise AssertionError(graph.result.errors)
    return manifest


def bind_reference_source_snapshot(skill_root: Path, manifest: dict, index: int = 0) -> dict:
    source = manifest["source_references"][index]
    source_path = skill_root / "sources" / f"{source['source_id']}.md"
    source_path.parent.mkdir(parents=True, exist_ok=True)
    source_path.write_text(
        f"Synthetic content-bound evidence for {source['source_id']}.\n",
        encoding="utf-8",
    )
    source["snapshot_path"] = source_path.relative_to(skill_root).as_posix()
    source["sha256"] = cc.sha256_file(source_path)
    write_json(skill_root / "reference-pack.json", manifest)
    return manifest


def bind_reference_pack(
    project: Path,
    skill_root: Path,
    selected: list[str] | None = None,
) -> None:
    args = type("Args", (), {
        "reference_source_uri": "https://git.invalid/reference-pack.git",
        "reference_source_ref": "main",
        "reference_source_commit": "3" * 40,
        "imported_by": "fixture-operator",
        "reason": "Initial synthetic reference binding",
        "select": selected,
    })()
    cc._install_reference_snapshot(
        project,
        skill_root,
        args,
        require_existing_binding=False,
        retain_backup=False,
    )


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

    def test_checkout_self_test_can_force_leaf_runtime_scope(self) -> None:
        args = type("Args", (), {
            "root": str(ROOT / "skills/creative-craft"),
            "scope": "runtime",
            "json": True,
        })()
        stdout = io.StringIO()
        with contextlib.redirect_stdout(stdout):
            self.assertEqual(0, cc.cmd_self_test(args))
        payload = json.loads(stdout.getvalue())
        self.assertEqual("runtime", payload["scope"])
        self.assertIsNone(payload["repository_valid"])
        self.assertTrue(payload["runtime_valid"])

    def test_leaf_install_self_test_uses_runtime_scope(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            installed = Path(directory) / "skills" / "creative-craft"
            shutil.copytree(
                ROOT / "skills/creative-craft",
                installed,
                ignore=shutil.ignore_patterns("__pycache__", "*.pyc"),
            )
            completed = subprocess.run(
                [
                    sys.executable,
                    str(installed / "scripts/creative_craft.py"),
                    "self-test",
                    "--json",
                ],
                text=True,
                capture_output=True,
                check=False,
            )
            self.assertEqual(0, completed.returncode, completed.stderr or completed.stdout)
            payload = json.loads(completed.stdout)
            self.assertTrue(payload["valid"])
            self.assertEqual("runtime", payload["scope"])
            self.assertIsNone(payload["repository_valid"])
            self.assertTrue(payload["runtime_valid"])

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

    def test_doctor_rejects_stale_tier_one_adapter_install_tags(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            copied = Path(directory) / "repo"
            shutil.copytree(
                ROOT,
                copied,
                ignore=shutil.ignore_patterns(".git", ".venv", "__pycache__", "*.pyc"),
            )
            adapter = copied / "adapters/pi/README.md"
            adapter.write_text(
                adapter.read_text(encoding="utf-8").replace("v0.2.5", "v0.2.1"),
                encoding="utf-8",
            )

            result = cc.doctor(copied)

            self.assertFalse(result.ok)
            self.assertTrue(any("adapters/pi/README.md" in item for item in result.errors))


class ReleaseReceiptTests(unittest.TestCase):
    def test_release_receipt_argv_redacts_local_absolute_paths(self) -> None:
        outside = Path.home() / "private-workspace" / "artifact.tgz"
        normalized = build_release.normalize_receipt_argv(
            [
                sys.executable,
                str(ROOT / "scripts/validate.py"),
                str(outside),
                "--json",
            ]
        )
        self.assertEqual("<python>", normalized[0])
        self.assertEqual("<repo>/scripts/validate.py", normalized[1])
        self.assertEqual("<absolute>/artifact.tgz", normalized[2])
        self.assertEqual("--json", normalized[3])
        serialized = json.dumps(normalized)
        self.assertNotIn(str(Path.home()), serialized)
        self.assertNotIn(str(ROOT), serialized)


class PackageSmokeTests(unittest.TestCase):
    @staticmethod
    def write_tar_member(
        archive: tarfile.TarFile,
        name: str,
        payload: bytes = b"fixture\n",
        *,
        member_type: bytes = tarfile.REGTYPE,
        linkname: str = "",
    ) -> None:
        member = tarfile.TarInfo(name)
        member.type = member_type
        member.linkname = linkname
        if member_type == tarfile.REGTYPE:
            member.size = len(payload)
            archive.addfile(member, io.BytesIO(payload))
        else:
            archive.addfile(member)

    def test_safe_extract_package_accepts_regular_package_tree(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            package = root / "fixture.tgz"
            with tarfile.open(package, "w:gz") as archive:
                self.write_tar_member(
                    archive,
                    "package/skills/creative-craft/SKILL.md",
                )
            destination = root / "extracted"
            package_smoke.safe_extract_package(package, destination)
            self.assertEqual(
                b"fixture\n",
                (destination / "package/skills/creative-craft/SKILL.md").read_bytes(),
            )

    def test_safe_extract_package_rejects_escape_and_link_members(self) -> None:
        cases = (
            ("../escape", tarfile.REGTYPE, ""),
            ("/absolute", tarfile.REGTYPE, ""),
            ("package/link", tarfile.SYMTYPE, "../../escape"),
            ("package/hardlink", tarfile.LNKTYPE, "package/target"),
        )
        for name, member_type, linkname in cases:
            with self.subTest(name=name), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                package = root / "unsafe.tgz"
                with tarfile.open(package, "w:gz") as archive:
                    self.write_tar_member(
                        archive,
                        name,
                        member_type=member_type,
                        linkname=linkname,
                    )
                with self.assertRaisesRegex(ValueError, "unsafe|links are not allowed"):
                    package_smoke.safe_extract_package(package, root / "extracted")
                self.assertFalse((root / "escape").exists())


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

    @staticmethod
    def add_output_chain(
        graph: cc.ProjectGraph,
        *,
        job_id: str,
        receipt_id: str,
        inspection_id: str,
        asset_id: str,
    ) -> None:
        output_sha = "a" * 64
        graph.records[("execution-receipt", receipt_id)] = {
            "data": {
                "schema_version": "creative-craft.execution-receipt.v1",
                "receipt_id": receipt_id,
                "job_id": job_id,
                "outcome": "succeeded",
                "outputs": [{"asset_id": asset_id, "sha256": output_sha}],
            }
        }
        graph.records[("output-inspection", inspection_id)] = {
            "data": {
                "schema_version": "creative-craft.output-inspection.v1",
                "inspection_id": inspection_id,
                "job_id": job_id,
                "receipt_id": receipt_id,
                "output_asset_id": asset_id,
                "output_sha256": output_sha,
                "decision": "approved",
            }
        }

    def test_output_gate_does_not_borrow_another_jobs_inspection(self) -> None:
        data = copy.deepcopy(self.data)
        data["stage"] = "output"
        data["target_ref"] = "cc://video/northstar-motion-proof-vertical-15s-v1#"
        self.add_output_chain(
            self.graph,
            job_id="northstar-motion-proof-hero-image-v1",
            receipt_id="receipt-unrelated-image",
            inspection_id="inspection-unrelated-image",
            asset_id="output-unrelated-image",
        )

        result = cc.score_evaluation(data, self.graph)

        self.assertEqual("blocked", result["status"])
        self.assertFalse(result["gate_status"]["actual_output_observed"])
        self.assertIn("actual_output_observed", result["failed_gates"])

    def test_output_gate_accepts_only_matching_job_receipt_output_inspection_chain(self) -> None:
        data = copy.deepcopy(self.data)
        data["stage"] = "output"
        data["target_ref"] = "cc://video/northstar-motion-proof-vertical-15s-v1#"
        self.add_output_chain(
            self.graph,
            job_id="northstar-motion-proof-vertical-15s-v1",
            receipt_id="receipt-target-video",
            inspection_id="inspection-target-video",
            asset_id="output-target-video",
        )

        result = cc.score_evaluation(data, self.graph)

        self.assertEqual("scored", result["status"])
        self.assertTrue(result["gate_status"]["target_compatible"])
        self.assertTrue(result["gate_status"]["actual_output_observed"])

    def test_delivery_gate_rejects_job_target_as_incompatible(self) -> None:
        data = copy.deepcopy(self.data)
        data["stage"] = "delivery"
        data["target_ref"] = "cc://video/northstar-motion-proof-vertical-15s-v1#"
        self.add_output_chain(
            self.graph,
            job_id="northstar-motion-proof-vertical-15s-v1",
            receipt_id="receipt-target-video",
            inspection_id="inspection-target-video",
            asset_id="output-target-video",
        )

        result = cc.score_evaluation(data, self.graph)

        self.assertEqual("blocked", result["status"])
        self.assertIn("target_compatible", result["failed_gates"])


class SeedTests(unittest.TestCase):
    @staticmethod
    def args(target: Path, *, force: bool = False, brand_pack: Path | None = None) -> object:
        return type("Args", (), {
            "target": str(target),
            "force": force,
            "brand_pack": str(brand_pack) if brand_pack else None,
            "brand_source_uri": "https://git.invalid/acme-brand-pack.git" if brand_pack else None,
            "brand_source_ref": "main" if brand_pack else None,
            "brand_source_commit": "1" * 40 if brand_pack else None,
            "imported_by": "fixture-operator",
            "reason": "Seed fixture",
        })()

    def test_seed_and_refuse_overwrite(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            args = type("Args", (), {"target": directory, "force": False})()
            stdout = io.StringIO()
            stderr = io.StringIO()
            with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
                self.assertEqual(0, cc.cmd_seed(args))
                self.assertTrue((Path(directory) / "BRAND.md").is_file())
                self.assertTrue((Path(directory) / ".creative-craft/critique.json").is_file())
                self.assertFalse(
                    (Path(directory) / ".creative-craft/execution-receipt.json").exists()
                )
                self.assertFalse(
                    (Path(directory) / ".creative-craft/output-inspection.json").exists()
                )
                self.assertFalse(
                    (Path(directory) / ".creative-craft/revision-lineage.json").exists()
                )
                self.assertFalse((Path(directory) / ".creative-craft/brand-pack.json").exists())
                self.assertFalse((Path(directory) / ".creative-craft/brand-binding.json").exists())
                self.assertFalse(
                    (Path(directory) / ".creative-craft/reference-bindings").exists()
                )
                self.assertFalse(
                    (Path(directory) / ".creative-craft/reference-snapshots").exists()
                )
                graph = cc.validate_project(Path(directory))
                self.assertTrue(graph.result.ok, graph.result.errors)
                self.assertIsNotNone(graph.record("critique", "critique-tbd"))
                self.assertEqual(1, cc.cmd_seed(args))
            self.assertIn("refusing to overwrite", stderr.getvalue())

    def test_seed_rejects_dangling_destination_symlink_without_external_write(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            project = root / "project"
            project.mkdir()
            outside = root / "outside-brand.md"
            (project / "BRAND.md").symlink_to(outside)
            before = tree_snapshot(project)

            with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(
                io.StringIO()
            ):
                self.assertEqual(1, cc.cmd_seed(self.args(project)))

            self.assertEqual(before, tree_snapshot(project))
            self.assertFalse(outside.exists())

    def test_seed_rejects_symlink_or_file_parent_without_partial_writes(self) -> None:
        for unsafe_parent in ("symlink", "file"):
            with self.subTest(unsafe_parent=unsafe_parent), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                project = root / "project"
                project.mkdir()
                if unsafe_parent == "symlink":
                    outside = root / "outside"
                    outside.mkdir()
                    (project / ".creative-craft").symlink_to(outside, target_is_directory=True)
                else:
                    (project / ".creative-craft").write_text("collision", encoding="utf-8")
                before = tree_snapshot(project)

                with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(
                    io.StringIO()
                ):
                    self.assertEqual(1, cc.cmd_seed(self.args(project)))

                self.assertEqual(before, tree_snapshot(project))

    def test_seed_copy_failure_restores_exact_tree(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            project = Path(directory) / "project"
            project.mkdir()
            (project / "keep.txt").write_text("unchanged", encoding="utf-8")
            before = tree_snapshot(project)
            real_copy2 = shutil.copy2
            calls = 0

            def fail_second_copy(source: Path, target: Path, *args: object, **kwargs: object) -> Path:
                nonlocal calls
                calls += 1
                if calls == 2:
                    raise OSError("injected seed copy failure")
                return real_copy2(source, target, *args, **kwargs)

            with mock.patch.object(cc.shutil, "copy2", side_effect=fail_second_copy), \
                    contextlib.redirect_stdout(io.StringIO()), \
                    contextlib.redirect_stderr(io.StringIO()):
                self.assertEqual(1, cc.cmd_seed(self.args(project)))

            self.assertEqual(before, tree_snapshot(project))

    def test_seed_brand_binding_failure_restores_exact_tree(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            project = root / "project"
            project.mkdir()
            (project / "keep.txt").write_text("unchanged", encoding="utf-8")
            brand_pack = init_brand_pack(root)
            approve_brand_pack(brand_pack)
            before = tree_snapshot(project)

            with mock.patch.object(
                cc, "_install_brand_snapshot", side_effect=OSError("injected brand bind failure")
            ), contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
                self.assertEqual(1, cc.cmd_seed(self.args(project, brand_pack=brand_pack)))

            self.assertEqual(before, tree_snapshot(project))

    def test_seed_force_preserves_replaced_files_as_transactional_backups(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            project = Path(directory)
            with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
                self.assertEqual(0, cc.cmd_seed(self.args(project)))
            old_brand = "# User authority\n"
            (project / "BRAND.md").write_text(old_brand, encoding="utf-8")

            with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
                self.assertEqual(0, cc.cmd_seed(self.args(project, force=True)))

            backups = list(project.glob("BRAND.md.bak.*"))
            self.assertEqual(1, len(backups))
            self.assertEqual(old_brand, backups[0].read_text(encoding="utf-8"))

    def test_seed_cli_path_error_is_stable_without_traceback(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            project = Path(directory) / "project"
            project.mkdir()
            (project / ".creative-craft").write_text("collision", encoding="utf-8")

            completed = subprocess.run(
                [sys.executable, str(CLI_PATH), "seed", "--target", str(project)],
                text=True,
                capture_output=True,
                check=False,
            )

            self.assertEqual(1, completed.returncode)
            self.assertIn("ERROR:", completed.stderr)
            self.assertNotIn("Traceback", completed.stderr)

    def test_project_rejects_critique_with_unknown_asset(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            args = type("Args", (), {"target": directory, "force": False})()
            with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(
                io.StringIO()
            ):
                self.assertEqual(0, cc.cmd_seed(args))
            critique_path = Path(directory) / ".creative-craft/critique.json"
            critique = json.loads(critique_path.read_text(encoding="utf-8"))
            critique["asset_id"] = "missing-asset"
            write_json(critique_path, critique)
            refresh_manifest(Path(directory))

            graph = cc.validate_project(Path(directory))

            self.assertFalse(graph.result.ok)
            self.assertIn(
                "critique critique-tbd references unknown asset 'missing-asset'",
                graph.result.errors,
            )

    def test_project_doctor_detects_unregistered_seed_residue(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            args = type("Args", (), {"target": directory, "force": False})()
            with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(
                io.StringIO()
            ):
                self.assertEqual(0, cc.cmd_seed(args))

            doctor_args = type("Args", (), {"root": directory, "json": True})()
            before_doctor = tree_snapshot(Path(directory))
            stdout = io.StringIO()
            with contextlib.redirect_stdout(stdout):
                self.assertEqual(0, cc.cmd_doctor_project(doctor_args))
            self.assertTrue(json.loads(stdout.getvalue())["healthy"])
            self.assertEqual(before_doctor, tree_snapshot(Path(directory)))

            project_dir = Path(directory) / ".creative-craft"
            residue_names = {
                "execution-receipt.json",
                "output-inspection.json",
                "revision-lineage.json",
            }
            for name in residue_names:
                shutil.copy2(cc.TEMPLATES_DIR / name, project_dir / name)

            before_doctor = tree_snapshot(Path(directory))
            stdout = io.StringIO()
            with contextlib.redirect_stdout(stdout):
                self.assertEqual(1, cc.cmd_doctor_project(doctor_args))
            payload = json.loads(stdout.getvalue())
            self.assertTrue(payload["valid"])
            self.assertFalse(payload["healthy"])
            self.assertEqual(
                residue_names,
                {Path(item["path"]).name for item in payload["unregistered_artifacts"]},
            )
            self.assertTrue(
                all(
                    item["classification"] == "seed_template_residue"
                    and item["matches_bundled_template"]
                    for item in payload["unregistered_artifacts"]
                )
            )
            self.assertEqual(before_doctor, tree_snapshot(Path(directory)))

    def test_project_doctor_detects_unregistered_critique(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            args = type("Args", (), {"target": directory, "force": False})()
            with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(
                io.StringIO()
            ):
                self.assertEqual(0, cc.cmd_seed(args))
            manifest_path = Path(directory) / ".creative-craft/project-manifest.json"
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            manifest["artifacts"] = [
                item for item in manifest["artifacts"] if item["artifact_type"] != "critique"
            ]
            write_json(manifest_path, manifest)

            doctor_args = type("Args", (), {"root": directory, "json": True})()
            stdout = io.StringIO()
            with contextlib.redirect_stdout(stdout):
                self.assertEqual(1, cc.cmd_doctor_project(doctor_args))
            payload = json.loads(stdout.getvalue())
            self.assertTrue(payload["valid"])
            self.assertEqual(1, len(payload["unregistered_artifacts"]))
            self.assertEqual(
                "critique", payload["unregistered_artifacts"][0]["artifact_type"]
            )


class BrandPackTests(unittest.TestCase):
    def copy_example(self, directory: str) -> Path:
        target = Path(directory) / "project"
        shutil.copytree(ROOT / "examples/premium-haircare-launch", target)
        return target

    def test_init_brand_pack_is_draft_unverified_and_valid(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            skill_root = init_brand_pack(Path(directory))
            graph = cc.validate_brand_pack(skill_root)
            self.assertTrue(graph.result.ok, graph.result.errors)
            self.assertEqual("draft", graph.manifest["status"])
            self.assertEqual("internal", graph.manifest["classification"])
            self.assertEqual([], graph.ledger["assets"])
            self.assertIn("UNVERIFIED", (skill_root / "references/claims.md").read_text())
            self.assertNotIn("creative-craft.brand-pack.v1", (skill_root / "SKILL.md").read_text())

    def test_brand_pack_path_traversal_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            skill_root = init_brand_pack(Path(directory))
            manifest_path = skill_root / "brand-pack.json"
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            manifest["authority_files"][0]["path"] = "../outside.md"
            write_json(manifest_path, manifest)
            graph = cc.validate_brand_pack(skill_root)
            self.assertFalse(graph.result.ok)
            self.assertTrue(any("unsafe root-relative" in item for item in graph.result.errors))

    def test_brand_pack_symlink_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            skill_root = init_brand_pack(Path(directory))
            brand_path = skill_root / "references/brand.md"
            content = brand_path.read_text(encoding="utf-8")
            real_path = skill_root / "references/brand-real.md"
            real_path.write_text(content, encoding="utf-8")
            brand_path.unlink()
            brand_path.symlink_to(real_path.name)
            graph = cc.validate_brand_pack(skill_root)
            self.assertFalse(graph.result.ok)
            self.assertTrue(any("must not use a symlink" in item for item in graph.result.errors))

    def test_authority_digest_drift_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            skill_root = init_brand_pack(Path(directory))
            with (skill_root / "references/brand.md").open("a", encoding="utf-8") as handle:
                handle.write("\nDrift.\n")
            graph = cc.validate_brand_pack(skill_root)
            self.assertFalse(graph.result.ok)
            self.assertTrue(any("sha256 mismatch" in item for item in graph.result.errors))

    def test_approved_pack_requires_approval_and_reviewed_source(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            skill_root = init_brand_pack(Path(directory))
            manifest_path = skill_root / "brand-pack.json"
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            manifest["status"] = "approved"
            write_json(manifest_path, manifest)
            graph = cc.validate_brand_pack(skill_root)
            self.assertFalse(graph.result.ok)
            self.assertTrue(any("requires approved_at" in item for item in graph.result.errors))
            self.assertTrue(any("requires at least one source" in item
                                for item in graph.result.errors))

    def test_approved_pack_rejects_placeholder_authority(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            skill_root = init_brand_pack(Path(directory))
            manifest_path = skill_root / "brand-pack.json"
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            manifest.update({
                "status": "approved",
                "approved_at": "2026-08-04T00:00:00Z",
                "source_references": [{
                    "source_id": "fixture",
                    "uri": "https://brand.invalid/authority",
                    "version": "0.1.0",
                    "reviewed_at": "2026-08-04T00:00:00Z",
                    "notes": "Synthetic fixture.",
                }],
            })
            write_json(manifest_path, manifest)
            graph = cc.validate_brand_pack(skill_root)
            self.assertFalse(graph.result.ok)
            self.assertTrue(any("still contains TBD" in item for item in graph.result.errors))

    def test_approved_pack_rejects_unresolved_asset_rights(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            skill_root = init_brand_pack(Path(directory))
            ledger_path = skill_root / "asset-ledger.json"
            ledger = json.loads(ledger_path.read_text(encoding="utf-8"))
            ledger["assets"].append({
                "asset_id": "acme-dam-001",
                "path_or_uri": "dam://acme/asset-001",
                "mime_type": "image/png",
                "sha256": "1" * 64,
                "creator": "fixture",
                "owner": "fixture",
                "rights_status": "UNVERIFIED",
                "consent_status": "NOT_APPLICABLE",
                "allowed_use": [],
                "expires_at": None,
                "reference_roles": ["brand"],
                "parent_assets": [],
                "notes": "Synthetic fixture.",
            })
            write_json(ledger_path, ledger)
            manifest_path = skill_root / "brand-pack.json"
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            manifest["asset_ledger"]["sha256"] = cc.sha256_file(ledger_path)
            write_json(manifest_path, manifest)
            approve_brand_pack(skill_root, require_valid=False)
            graph = cc.validate_brand_pack(skill_root)
            self.assertFalse(graph.result.ok)
            self.assertTrue(any("unresolved rights" in item for item in graph.result.errors))

    def test_seed_creates_content_bound_snapshot_without_live_drift(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            skill_root = init_brand_pack(root)
            project = root / "project"
            args = type("Args", (), {
                "target": str(project),
                "force": False,
                "brand_pack": str(skill_root),
                "brand_source_uri": "https://git.invalid/acme.git",
                "brand_source_ref": "main",
                "brand_source_commit": "1" * 40,
                "imported_by": "fixture",
            })()
            with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
                self.assertEqual(0, cc.cmd_seed(args))
            snapshot_brand = project / ".creative-craft/brand-snapshot/references/brand.md"
            before = snapshot_brand.read_bytes()
            source_brand = skill_root / "references/brand.md"
            source_brand.write_text("Source changed after binding.\n", encoding="utf-8")
            self.assertEqual(before, snapshot_brand.read_bytes())
            self.assertFalse(snapshot_brand.is_symlink())
            self.assertTrue(cc.validate_project(project).result.ok)

    def test_draft_brand_pack_blocks_ready_job(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            skill_root = init_brand_pack(root)
            project = root / "project"
            args = type("Args", (), {
                "target": str(project),
                "force": False,
                "brand_pack": str(skill_root),
                "brand_source_uri": None,
                "brand_source_ref": None,
                "brand_source_commit": None,
                "imported_by": "fixture",
            })()
            with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
                self.assertEqual(0, cc.cmd_seed(args))
            job_path = project / ".creative-craft/image-job.json"
            job = json.loads(job_path.read_text(encoding="utf-8"))
            job["declared_status"] = "ready"
            write_json(job_path, job)
            refresh_manifest(project)
            graph = cc.validate_project(project)
            self.assertFalse(graph.result.ok)
            self.assertTrue(any("requires an approved bound brand pack" in item
                                for item in graph.result.errors))

    def test_approved_brand_pack_allows_existing_ready_project(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            skill_root = init_brand_pack(Path(directory))
            approve_brand_pack(skill_root)
            project = self.copy_example(directory)
            bind_brand_pack(project, skill_root)
            graph = cc.validate_project(project)
            self.assertTrue(graph.result.ok, graph.result.errors)

    def test_binding_identity_mismatch_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            skill_root = init_brand_pack(Path(directory))
            approve_brand_pack(skill_root)
            project = self.copy_example(directory)
            bind_brand_pack(project, skill_root)
            binding_path = project / ".creative-craft/brand-binding.json"
            binding = json.loads(binding_path.read_text(encoding="utf-8"))
            binding["pack_version"] = "9.9.9"
            write_json(binding_path, binding)
            refresh_manifest(project)
            graph = cc.validate_project(project)
            self.assertFalse(graph.result.ok)
            self.assertTrue(any("pack_version differs" in item for item in graph.result.errors))

    def test_binding_source_digest_mismatch_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            skill_root = init_brand_pack(Path(directory))
            approve_brand_pack(skill_root)
            project = self.copy_example(directory)
            bind_brand_pack(project, skill_root)
            binding_path = project / ".creative-craft/brand-binding.json"
            binding = json.loads(binding_path.read_text(encoding="utf-8"))
            binding["source"]["pack_sha256"] = "f" * 64
            write_json(binding_path, binding)
            refresh_manifest(project)
            graph = cc.validate_project(project)
            self.assertFalse(graph.result.ok)
            self.assertTrue(any("source.pack_sha256 differs" in item
                                for item in graph.result.errors))

    def test_snapshot_tree_digest_mismatch_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            skill_root = init_brand_pack(Path(directory))
            approve_brand_pack(skill_root)
            project = self.copy_example(directory)
            bind_brand_pack(project, skill_root)
            path = project / ".creative-craft/brand-snapshot/references/brand.md"
            path.write_text(path.read_text(encoding="utf-8") + "\nDrift.\n", encoding="utf-8")
            graph = cc.validate_project(project)
            self.assertFalse(graph.result.ok)
            self.assertTrue(any("tree_sha256 mismatch" in item for item in graph.result.errors))

    def test_project_brand_digest_mismatch_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            skill_root = init_brand_pack(Path(directory))
            approve_brand_pack(skill_root)
            project = self.copy_example(directory)
            bind_brand_pack(project, skill_root)
            (project / "BRAND.md").write_text("Drift.\n", encoding="utf-8")
            graph = cc.validate_project(project)
            self.assertFalse(graph.result.ok)
            self.assertTrue(any("project_brand.sha256 mismatch" in item
                                for item in graph.result.errors))

    def test_update_brand_snapshot_creates_backup_and_lineage(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            first = init_brand_pack(root / "first")
            approve_brand_pack(first)
            project = self.copy_example(directory)
            bind_brand_pack(project, first)
            old_binding = json.loads(
                (project / ".creative-craft/brand-binding.json").read_text(encoding="utf-8")
            )
            second = root / "second/acme-brand"
            shutil.copytree(first, second)
            brand_path = second / "references/brand.md"
            brand_path.write_text(brand_path.read_text(encoding="utf-8") + "\nVersion 0.2.0.\n",
                                  encoding="utf-8")
            manifest_path = second / "brand-pack.json"
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            manifest["version"] = "0.2.0"
            for item in manifest["authority_files"]:
                if item["role"] == "brand":
                    item["sha256"] = cc.sha256_file(brand_path)
            write_json(manifest_path, manifest)
            args = type("Args", (), {
                "target": str(project),
                "brand_pack": str(second),
                "reason": "Adopt approved authority 0.2.0",
                "brand_source_uri": "https://git.invalid/acme.git",
                "brand_source_ref": "v0.2.0",
                "brand_source_commit": "2" * 40,
                "imported_by": "fixture",
            })()
            with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
                self.assertEqual(0, cc.cmd_update_brand_snapshot(args))
            binding = json.loads(
                (project / ".creative-craft/brand-binding.json").read_text(encoding="utf-8")
            )
            self.assertEqual(old_binding["binding_id"], binding["previous_binding_id"])
            self.assertEqual("0.2.0", binding["pack_version"])
            backups = list((project / ".creative-craft/brand-backups").iterdir())
            self.assertEqual(1, len(backups))
            self.assertTrue(cc.validate_project(project).result.ok)

    def test_update_failure_rolls_back_project_state(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            first = init_brand_pack(root / "first")
            approve_brand_pack(first)
            project = self.copy_example(directory)
            bind_brand_pack(project, first)
            second = root / "second/acme-brand"
            shutil.copytree(first, second)
            manifest_path = second / "brand-pack.json"
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            manifest["version"] = "0.2.0"
            write_json(manifest_path, manifest)
            binding_path = project / ".creative-craft/brand-binding.json"
            before_binding = binding_path.read_bytes()
            before_brand = (project / "BRAND.md").read_bytes()
            before_tree = tree_snapshot(project)
            original_validate = cc.validate_project
            calls = 0

            def fail_final_validation(root_path: Path) -> cc.ProjectGraph:
                nonlocal calls
                calls += 1
                if calls == 1:
                    return original_validate(root_path)
                graph = original_validate(root_path)
                graph.result.errors.append("synthetic post-write failure")
                return graph

            args = type("Args", (), {
                "target": str(project),
                "brand_pack": str(second),
                "reason": "Synthetic rollback test",
                "brand_source_uri": "https://git.invalid/acme.git",
                "brand_source_ref": "v0.2.0",
                "brand_source_commit": "2" * 40,
                "imported_by": "fixture",
            })()
            with (
                mock.patch.object(cc, "validate_project", side_effect=fail_final_validation),
                contextlib.redirect_stdout(io.StringIO()),
                contextlib.redirect_stderr(io.StringIO()),
            ):
                self.assertEqual(1, cc.cmd_update_brand_snapshot(args))
            self.assertEqual(before_binding, binding_path.read_bytes())
            self.assertEqual(before_brand, (project / "BRAND.md").read_bytes())
            self.assertEqual(before_tree, tree_snapshot(project))
            self.assertTrue(original_validate(project).result.ok)

    def test_brand_backup_destination_symlink_is_rejected_before_write(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            first = init_brand_pack(root / "first")
            approve_brand_pack(first)
            project = self.copy_example(directory)
            bind_brand_pack(project, first)
            second = root / "second/acme-brand"
            shutil.copytree(first, second)
            manifest_path = second / "brand-pack.json"
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            manifest["version"] = "0.2.0"
            write_json(manifest_path, manifest)
            outside = root / "outside-brand-backups"
            outside.mkdir()
            backup_link = project / ".creative-craft/brand-backups"
            backup_link.symlink_to(outside, target_is_directory=True)
            args = type("Args", (), {
                "target": str(project),
                "brand_pack": str(second),
                "reason": "Reject destination symlink",
                "brand_source_uri": None,
                "brand_source_ref": None,
                "brand_source_commit": None,
                "imported_by": "fixture",
            })()
            stderr = io.StringIO()
            with contextlib.redirect_stderr(stderr):
                self.assertEqual(1, cc.cmd_update_brand_snapshot(args))
            self.assertIn("must not use a symlink", stderr.getvalue())
            self.assertEqual([], list(outside.iterdir()))
            self.assertTrue(cc.validate_project(project).result.ok)


class ReferencePackTests(unittest.TestCase):
    def copy_example(self, directory: str) -> Path:
        target = Path(directory) / "project"
        shutil.copytree(ROOT / "examples/premium-haircare-launch", target)
        return target

    def test_binding_content_digest_is_key_order_independent(self) -> None:
        binding = load("skills/creative-craft/templates/reference-binding.json")
        reordered = dict(reversed(list(binding.items())))
        self.assertEqual(
            cc.json_content_sha256(binding),
            cc.json_content_sha256(reordered),
        )

    def test_reference_staging_collision_is_preserved(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            skill_root = init_reference_pack(root / "source")
            add_reference_entity(skill_root, "reference-a")
            source = cc.validate_reference_pack(skill_root)
            staging = root / "existing-staging"
            staging.mkdir()
            marker = staging / "owner-data.txt"
            marker.write_text("preserve\n", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "staging path already exists"):
                cc._copy_reference_snapshot_files(source, staging)
            self.assertEqual("preserve\n", marker.read_text(encoding="utf-8"))

    def test_failed_backup_copy_removes_only_operation_residue(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "project"
            root.mkdir()
            tracked = root / "tracked.json"
            tracked.write_text("{}\n", encoding="utf-8")
            before = tree_snapshot(root)
            with (
                mock.patch.object(cc.shutil, "copy2", side_effect=OSError("copy failed")),
                self.assertRaisesRegex(OSError, "copy failed"),
            ):
                cc._backup_project_state(
                    root,
                    ".creative-craft/reference-backups/reference-a/fixed",
                    [tracked],
                    label="reference backup path",
                )
            self.assertEqual(before, tree_snapshot(root))

    def test_init_reference_pack_is_empty_draft_and_non_authoritative(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            skill_root = init_reference_pack(Path(directory))
            graph = cc.validate_reference_pack(skill_root)
            self.assertTrue(graph.result.ok, graph.result.errors)
            self.assertEqual("draft", graph.manifest["status"])
            self.assertEqual("internal", graph.manifest["classification"])
            self.assertEqual([], graph.manifest["entities"])
            self.assertEqual([], graph.ledger["assets"])
            skill_text = (skill_root / "SKILL.md").read_text(encoding="utf-8")
            self.assertIn("non-authoritative", skill_text)
            self.assertIn("Never override", skill_text)

    def test_reference_pack_path_traversal_and_digest_drift_are_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            skill_root = init_reference_pack(Path(directory))
            add_reference_entity(skill_root, "reference-a", with_asset=True)
            ledger_path = skill_root / "asset-ledger.json"
            ledger = json.loads(ledger_path.read_text(encoding="utf-8"))
            ledger["assets"][0]["path_or_uri"] = "../outside.bin"
            write_json(ledger_path, ledger)
            manifest_path = skill_root / "reference-pack.json"
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            manifest["asset_ledger"]["sha256"] = cc.sha256_file(ledger_path)
            write_json(manifest_path, manifest)
            graph = cc.validate_reference_pack(skill_root)
            self.assertFalse(graph.result.ok)
            self.assertTrue(any("unsafe root-relative" in item for item in graph.result.errors))

            ledger["assets"][0]["path_or_uri"] = "assets/approved/reference-a.bin"
            ledger["assets"][0]["sha256"] = "f" * 64
            write_json(ledger_path, ledger)
            manifest["asset_ledger"]["sha256"] = cc.sha256_file(ledger_path)
            write_json(manifest_path, manifest)
            graph = cc.validate_reference_pack(skill_root)
            self.assertFalse(graph.result.ok)
            self.assertTrue(any("sha256 mismatch" in item for item in graph.result.errors))

    def test_reference_pack_symlink_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            skill_root = init_reference_pack(Path(directory))
            add_reference_entity(skill_root, "reference-a", with_asset=True)
            asset_path = skill_root / "assets/approved/reference-a.bin"
            real_path = skill_root / "assets/approved/reference-a-real.bin"
            real_path.write_bytes(asset_path.read_bytes())
            asset_path.unlink()
            asset_path.symlink_to(real_path.name)
            graph = cc.validate_reference_pack(skill_root)
            self.assertFalse(graph.result.ok)
            self.assertTrue(any("must not use a symlink" in item for item in graph.result.errors))

    def test_reference_evidence_and_authority_semantics_are_enforced(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            skill_root = init_reference_pack(Path(directory))
            manifest = add_reference_entity(skill_root, "reference-a")
            manifest["entities"][0]["observations"][0]["evidence_refs"] = []
            _, result = cc.validate_data(manifest, "reference-pack")
            self.assertFalse(result.ok)
            self.assertTrue(any("requires evidence_refs" in item for item in result.errors))

            manifest = add_reference_entity(skill_root, "reference-b")
            manifest["entities"][0]["may_override_primary_brand"] = True
            _, result = cc.validate_data(manifest, "reference-pack")
            self.assertFalse(result.ok)
            self.assertTrue(any("must equal False" in item for item in result.errors))

    def test_reviewed_pack_requires_review_evidence_and_no_unverified_observation(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            skill_root = init_reference_pack(Path(directory))
            manifest = add_reference_entity(skill_root, "reference-a")
            manifest["status"] = "reviewed"
            manifest["reviewed_at"] = None
            observation = manifest["entities"][0]["observations"][0]
            observation["evidence_state"] = "UNVERIFIED"
            observation["evidence_refs"] = []
            write_json(skill_root / "reference-pack.json", manifest)
            graph = cc.validate_reference_pack(skill_root)
            self.assertFalse(graph.result.ok)
            self.assertTrue(any("requires reviewed_at" in item for item in graph.result.errors))
            self.assertTrue(any("cannot contain UNVERIFIED" in item
                                for item in graph.result.errors))

    def test_reviewed_pack_requires_content_bound_source_snapshot(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            skill_root = init_reference_pack(Path(directory))
            manifest = add_reference_entity(skill_root, "reference-a")
            manifest.update({
                "status": "reviewed",
                "reviewed_at": "2026-08-04T00:00:00Z",
                "review_after": "2027-08-04T00:00:00Z",
            })
            manifest["source_references"][0]["uri"] = "TBD"
            write_json(skill_root / "reference-pack.json", manifest)
            graph = cc.validate_reference_pack(skill_root)
            self.assertFalse(graph.result.ok)
            self.assertTrue(any("must not be a placeholder" in item
                                for item in graph.result.errors))
            self.assertTrue(any("requires a content SHA-256" in item
                                for item in graph.result.errors))
            self.assertTrue(any("requires snapshot_path" in item
                                for item in graph.result.errors))

            manifest["source_references"][0]["uri"] = (
                "urn:creative-craft:reference-a-source"
            )
            bind_reference_source_snapshot(skill_root, manifest)
            graph = cc.validate_reference_pack(skill_root)
            self.assertTrue(graph.result.ok, graph.result.errors)
            snapshot_path = skill_root / manifest["source_references"][0]["snapshot_path"]
            snapshot_path.write_text("drifted source evidence\n", encoding="utf-8")
            graph = cc.validate_reference_pack(skill_root)
            self.assertFalse(graph.result.ok)
            self.assertTrue(any("snapshot sha256 mismatch" in item
                                for item in graph.result.errors))

    def test_approved_reference_input_requires_resolved_rights(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            skill_root = init_reference_pack(Path(directory))
            manifest = add_reference_entity(
                skill_root,
                "reference-a",
                with_asset=True,
                rights_status="UNVERIFIED",
                rights_policy="research_only",
            )
            manifest["entities"][0]["rights_policy"] = "approved_reference_input"
            write_json(skill_root / "reference-pack.json", manifest)
            graph = cc.validate_reference_pack(skill_root)
            self.assertFalse(graph.result.ok)
            self.assertTrue(any("unresolved rights" in item for item in graph.result.errors))

    def test_draft_reference_pack_does_not_block_ready_job_and_snapshot_does_not_drift(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            skill_root = init_reference_pack(root)
            add_reference_entity(skill_root, "reference-a")
            project = self.copy_example(directory)
            bind_reference_pack(project, skill_root)
            snapshot_path = (
                project
                / ".creative-craft/reference-snapshots/reference-fixture/reference-pack.json"
            )
            before = snapshot_path.read_bytes()
            source_path = skill_root / "reference-pack.json"
            source_path.write_text(source_path.read_text(encoding="utf-8") + "\n",
                                   encoding="utf-8")
            self.assertEqual(before, snapshot_path.read_bytes())
            self.assertFalse(snapshot_path.is_symlink())
            graph = cc.validate_project(project)
            self.assertTrue(graph.result.ok, graph.result.errors)
            self.assertEqual("ready", graph.job_statuses["northstar-motion-proof-hero-image-v1"])
            self.assertTrue(any("exploratory evidence" in item
                                for item in graph.result.warnings))

    def test_multiple_reference_packs_can_coexist(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            first = init_reference_pack(root / "first", "reference-one", "Reference One")
            second = init_reference_pack(root / "second", "reference-two", "Reference Two")
            add_reference_entity(first, "reference-a")
            add_reference_entity(second, "reference-b")
            project = self.copy_example(directory)
            bind_reference_pack(project, first)
            bind_reference_pack(project, second)
            graph = cc.validate_project(project)
            self.assertTrue(graph.result.ok, graph.result.errors)
            self.assertEqual(
                2,
                sum(1 for kind, _ in graph.records if kind == "reference-pack"),
            )
            self.assertEqual(
                2,
                sum(1 for kind, _ in graph.records if kind == "reference-binding"),
            )

    def test_binding_merges_only_selected_entity_assets(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            skill_root = init_reference_pack(root)
            add_reference_entity(skill_root, "reference-a", with_asset=True)
            add_reference_entity(skill_root, "reference-b", with_asset=True)
            project = self.copy_example(directory)
            bind_reference_pack(project, skill_root, ["reference-a"])
            ledger = json.loads((project / "asset-ledger.json").read_text(encoding="utf-8"))
            assets = {asset["asset_id"]: asset for asset in ledger["assets"]}
            self.assertIn("asset-reference-a", assets)
            self.assertNotIn("asset-reference-b", assets)
            self.assertEqual(
                ".creative-craft/reference-snapshots/reference-fixture/"
                "assets/approved/reference-a.bin",
                assets["asset-reference-a"]["path_or_uri"],
            )
            self.assertTrue(cc.validate_project(project).result.ok)

    def test_unknown_selection_and_revoked_pack_are_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            skill_root = init_reference_pack(root)
            manifest = add_reference_entity(skill_root, "reference-a")
            project = self.copy_example(directory)
            with self.assertRaisesRegex(ValueError, "does not exist"):
                bind_reference_pack(project, skill_root, ["missing-reference"])
            bind_reference_pack(project, skill_root)

            manifest["status"] = "revoked"
            write_json(skill_root / "reference-pack.json", manifest)
            with self.assertRaisesRegex(ValueError, "revoked"):
                bind_reference_pack(project, skill_root)

            manifest["status"] = "superseded"
            write_json(skill_root / "reference-pack.json", manifest)
            with self.assertRaisesRegex(ValueError, "superseded"):
                bind_reference_pack(project, skill_root)
            update_args = type("Args", (), {
                "target": str(project),
                "reference_pack": str(skill_root),
                "reason": "Reject superseded update source",
                "reference_source_uri": None,
                "reference_source_ref": None,
                "reference_source_commit": None,
                "imported_by": "fixture-operator",
                "select": ["reference-a"],
            })()
            stderr = io.StringIO()
            with contextlib.redirect_stderr(stderr):
                self.assertEqual(1, cc.cmd_update_reference_snapshot(update_args))
            self.assertIn("superseded", stderr.getvalue())
            self.assertTrue(cc.validate_project(project).result.ok)

    def test_already_bound_superseded_snapshot_remains_historical_evidence(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            skill_root = init_reference_pack(root)
            add_reference_entity(skill_root, "reference-a")
            project = self.copy_example(directory)
            bind_reference_pack(project, skill_root)

            snapshot_root = (
                project / ".creative-craft/reference-snapshots/reference-fixture"
            )
            snapshot_manifest_path = snapshot_root / "reference-pack.json"
            snapshot_manifest = json.loads(
                snapshot_manifest_path.read_text(encoding="utf-8")
            )
            snapshot_manifest["status"] = "superseded"
            write_json(snapshot_manifest_path, snapshot_manifest)

            binding_path = (
                project / ".creative-craft/reference-bindings/reference-fixture.json"
            )
            binding = json.loads(binding_path.read_text(encoding="utf-8"))
            binding["source"]["pack_sha256"] = cc.sha256_file(snapshot_manifest_path)
            binding["snapshot"]["tree_sha256"] = cc.tree_sha256(snapshot_root)
            write_json(binding_path, binding)
            refresh_manifest(project)

            graph = cc.validate_project(project)
            self.assertTrue(graph.result.ok, graph.result.errors)
            self.assertTrue(
                any("historical evidence" in warning for warning in graph.result.warnings)
            )

    def test_snapshot_and_binding_digest_drift_are_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            skill_root = init_reference_pack(root)
            add_reference_entity(skill_root, "reference-a")
            project = self.copy_example(directory)
            bind_reference_pack(project, skill_root)
            binding_path = (
                project / ".creative-craft/reference-bindings/reference-fixture.json"
            )
            binding = json.loads(binding_path.read_text(encoding="utf-8"))
            original_selection = binding["selected_reference_ids"]
            binding["selected_reference_ids"] = ["missing-reference"]
            write_json(binding_path, binding)
            refresh_manifest(project)
            graph = cc.validate_project(project)
            self.assertFalse(graph.result.ok)
            self.assertTrue(any("selects unknown reference" in item
                                for item in graph.result.errors))

            binding["selected_reference_ids"] = original_selection
            binding["source"]["pack_sha256"] = "f" * 64
            write_json(binding_path, binding)
            refresh_manifest(project)
            graph = cc.validate_project(project)
            self.assertFalse(graph.result.ok)
            self.assertTrue(any("source.pack_sha256 differs" in item
                                for item in graph.result.errors))

            binding["source"]["pack_sha256"] = cc.sha256_file(
                project
                / ".creative-craft/reference-snapshots/reference-fixture/reference-pack.json"
            )
            binding["snapshot"]["tree_sha256"] = "e" * 64
            write_json(binding_path, binding)
            refresh_manifest(project)
            graph = cc.validate_project(project)
            self.assertFalse(graph.result.ok)
            self.assertTrue(any("tree_sha256 mismatch" in item
                                for item in graph.result.errors))

    def test_reference_binding_predecessor_must_resolve_to_history(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            skill_root = init_reference_pack(root)
            add_reference_entity(skill_root, "reference-a")
            project = self.copy_example(directory)
            bind_reference_pack(project, skill_root)
            binding_path = (
                project / ".creative-craft/reference-bindings/reference-fixture.json"
            )
            binding = json.loads(binding_path.read_text(encoding="utf-8"))
            binding["previous_binding_id"] = "reference-binding-does-not-exist"
            write_json(binding_path, binding)
            refresh_manifest(project)
            graph = cc.validate_project(project)
            self.assertFalse(graph.result.ok)
            self.assertTrue(any("has unresolved predecessor" in item
                                for item in graph.result.errors))

    def test_multiple_reference_updates_extend_one_resolvable_lineage(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = init_reference_pack(root / "v1")
            add_reference_entity(source, "reference-a")
            project = self.copy_example(directory)
            bind_reference_pack(project, source)
            expected_history_ids: list[str] = []

            for version in ("0.2.0", "0.3.0"):
                current_binding_path = (
                    project / ".creative-craft/reference-bindings/reference-fixture.json"
                )
                current_binding = json.loads(
                    current_binding_path.read_text(encoding="utf-8")
                )
                expected_history_ids.append(current_binding["binding_id"])
                updated = root / f"v{version}/reference-fixture"
                updated.parent.mkdir()
                shutil.copytree(source, updated)
                manifest_path = updated / "reference-pack.json"
                manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
                manifest["version"] = version
                write_json(manifest_path, manifest)
                args = type("Args", (), {
                    "target": str(project),
                    "reference_pack": str(updated),
                    "reason": f"Adopt {version}",
                    "reference_source_uri": None,
                    "reference_source_ref": None,
                    "reference_source_commit": None,
                    "imported_by": "fixture-operator",
                    "select": ["reference-a"],
                })()
                with (
                    contextlib.redirect_stdout(io.StringIO()),
                    contextlib.redirect_stderr(io.StringIO()),
                ):
                    self.assertEqual(0, cc.cmd_update_reference_snapshot(args))
                source = updated

            graph = cc.validate_project(project)
            self.assertTrue(graph.result.ok, graph.result.errors)
            histories = {
                artifact_id
                for artifact_type, artifact_id in graph.records
                if artifact_type == "reference-binding-history"
            }
            self.assertEqual(set(expected_history_ids), histories)
            current_binding = json.loads(
                (project / ".creative-craft/reference-bindings/reference-fixture.json")
                .read_text(encoding="utf-8")
            )
            self.assertEqual(expected_history_ids[-1], current_binding["previous_binding_id"])

    def test_update_one_reference_pack_preserves_other_pack_and_lineage(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            first = init_reference_pack(root / "first", "reference-one", "Reference One")
            second = init_reference_pack(root / "second", "reference-two", "Reference Two")
            add_reference_entity(first, "reference-a", with_asset=True)
            add_reference_entity(second, "reference-b", with_asset=True)
            project = self.copy_example(directory)
            bind_reference_pack(project, first)
            bind_reference_pack(project, second)
            old_binding = json.loads(
                (project / ".creative-craft/reference-bindings/reference-one.json")
                .read_text(encoding="utf-8")
            )
            second_snapshot_digest = cc.tree_sha256(
                project / ".creative-craft/reference-snapshots/reference-two"
            )

            updated = root / "updated/reference-one"
            updated.parent.mkdir()
            shutil.copytree(first, updated)
            add_reference_entity(updated, "reference-c", with_asset=True)
            updated_manifest_path = updated / "reference-pack.json"
            updated_manifest = json.loads(updated_manifest_path.read_text(encoding="utf-8"))
            updated_manifest["version"] = "0.2.0"
            write_json(updated_manifest_path, updated_manifest)
            args = type("Args", (), {
                "target": str(project),
                "reference_pack": str(updated),
                "reason": "Adopt synthetic reference revision",
                "reference_source_uri": "https://git.invalid/reference-one.git",
                "reference_source_ref": "v0.2.0",
                "reference_source_commit": "4" * 40,
                "imported_by": "fixture-operator",
                "select": ["reference-c"],
            })()
            with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
                self.assertEqual(0, cc.cmd_update_reference_snapshot(args))
            binding = json.loads(
                (project / ".creative-craft/reference-bindings/reference-one.json")
                .read_text(encoding="utf-8")
            )
            self.assertEqual(old_binding["binding_id"], binding["previous_binding_id"])
            history_path = (
                project
                / ".creative-craft/reference-lineage/reference-one"
                / cc.reference_history_filename(old_binding["binding_id"])
            )
            history = json.loads(history_path.read_text(encoding="utf-8"))
            self.assertEqual(old_binding["binding_id"], history["history_id"])
            self.assertEqual(old_binding, history["binding"])
            self.assertEqual(
                cc.json_content_sha256(old_binding), history["binding_sha256"]
            )
            self.assertEqual("0.2.0", binding["pack_version"])
            self.assertEqual(
                second_snapshot_digest,
                cc.tree_sha256(project / ".creative-craft/reference-snapshots/reference-two"),
            )
            ledger = json.loads((project / "asset-ledger.json").read_text(encoding="utf-8"))
            asset_ids = {asset["asset_id"] for asset in ledger["assets"]}
            self.assertNotIn("asset-reference-a", asset_ids)
            self.assertIn("asset-reference-b", asset_ids)
            self.assertIn("asset-reference-c", asset_ids)
            backups = list(
                (project / ".creative-craft/reference-backups/reference-one").iterdir()
            )
            self.assertEqual(1, len(backups))
            self.assertTrue(cc.validate_project(project).result.ok)

    def test_update_failure_rolls_back_only_target_reference_pack(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            skill_root = init_reference_pack(root / "first")
            add_reference_entity(skill_root, "reference-a", with_asset=True)
            project = self.copy_example(directory)
            bind_reference_pack(project, skill_root)
            updated = root / "updated/reference-fixture"
            updated.parent.mkdir()
            shutil.copytree(skill_root, updated)
            manifest_path = updated / "reference-pack.json"
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            manifest["version"] = "0.2.0"
            write_json(manifest_path, manifest)
            binding_path = (
                project / ".creative-craft/reference-bindings/reference-fixture.json"
            )
            before_binding = binding_path.read_bytes()
            before_ledger = (project / "asset-ledger.json").read_bytes()
            before_snapshot = cc.tree_sha256(
                project / ".creative-craft/reference-snapshots/reference-fixture"
            )
            before_tree = tree_snapshot(project)
            original_validate = cc.validate_project
            calls = 0

            def fail_final_validation(root_path: Path) -> cc.ProjectGraph:
                nonlocal calls
                calls += 1
                graph = original_validate(root_path)
                if calls > 1:
                    graph.result.errors.append("synthetic post-write failure")
                return graph

            args = type("Args", (), {
                "target": str(project),
                "reference_pack": str(updated),
                "reason": "Synthetic rollback test",
                "reference_source_uri": None,
                "reference_source_ref": None,
                "reference_source_commit": None,
                "imported_by": "fixture-operator",
                "select": ["reference-a"],
            })()
            with (
                mock.patch.object(cc, "validate_project", side_effect=fail_final_validation),
                contextlib.redirect_stdout(io.StringIO()),
                contextlib.redirect_stderr(io.StringIO()),
            ):
                self.assertEqual(1, cc.cmd_update_reference_snapshot(args))
            self.assertEqual(before_binding, binding_path.read_bytes())
            self.assertEqual(before_ledger, (project / "asset-ledger.json").read_bytes())
            self.assertEqual(
                before_snapshot,
                cc.tree_sha256(
                    project / ".creative-craft/reference-snapshots/reference-fixture"
                ),
            )
            self.assertEqual(before_tree, tree_snapshot(project))
            self.assertTrue(original_validate(project).result.ok)

    def test_reference_backup_destination_symlink_is_rejected_before_write(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            skill_root = init_reference_pack(root / "first")
            add_reference_entity(skill_root, "reference-a", with_asset=True)
            project = self.copy_example(directory)
            bind_reference_pack(project, skill_root)
            updated = root / "updated/reference-fixture"
            updated.parent.mkdir()
            shutil.copytree(skill_root, updated)
            manifest_path = updated / "reference-pack.json"
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            manifest["version"] = "0.2.0"
            write_json(manifest_path, manifest)

            outside = root / "outside-backups"
            outside.mkdir()
            backup_link = project / ".creative-craft/reference-backups"
            backup_link.symlink_to(outside, target_is_directory=True)
            before = cc.tree_sha256(
                project / ".creative-craft/reference-snapshots/reference-fixture"
            )
            args = type("Args", (), {
                "target": str(project),
                "reference_pack": str(updated),
                "reason": "Reject destination symlink",
                "reference_source_uri": None,
                "reference_source_ref": None,
                "reference_source_commit": None,
                "imported_by": "fixture-operator",
                "select": ["reference-a"],
            })()
            stderr = io.StringIO()
            with contextlib.redirect_stderr(stderr):
                self.assertEqual(1, cc.cmd_update_reference_snapshot(args))
            self.assertIn("must not use a symlink", stderr.getvalue())
            self.assertEqual([], list(outside.iterdir()))
            self.assertEqual(
                before,
                cc.tree_sha256(
                    project / ".creative-craft/reference-snapshots/reference-fixture"
                ),
            )
            self.assertTrue(cc.validate_project(project).result.ok)

    def test_failed_initial_reference_bind_restores_exact_project_tree(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            skill_root = init_reference_pack(root)
            add_reference_entity(skill_root, "reference-a", with_asset=True)
            project = self.copy_example(directory)
            before_tree = tree_snapshot(project)
            original_validate = cc.validate_project
            calls = 0

            def fail_final_validation(root_path: Path) -> cc.ProjectGraph:
                nonlocal calls
                calls += 1
                graph = original_validate(root_path)
                if calls > 1:
                    graph.result.errors.append("synthetic post-write failure")
                return graph

            args = type("Args", (), {
                "target": str(project),
                "reference_pack": str(skill_root),
                "reason": "Synthetic failed initial binding",
                "reference_source_uri": None,
                "reference_source_ref": None,
                "reference_source_commit": None,
                "imported_by": "fixture-operator",
                "select": ["reference-a"],
            })()
            with (
                mock.patch.object(cc, "validate_project", side_effect=fail_final_validation),
                contextlib.redirect_stdout(io.StringIO()),
                contextlib.redirect_stderr(io.StringIO()),
            ):
                self.assertEqual(1, cc.cmd_bind_reference_pack(args))
            self.assertEqual(before_tree, tree_snapshot(project))
            self.assertTrue(original_validate(project).result.ok)

    def test_reference_pack_cannot_replace_primary_brand_authority(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            brand = init_brand_pack(root / "brand")
            approve_brand_pack(brand)
            reference = init_reference_pack(root / "reference")
            add_reference_entity(reference, "reference-a")
            project = self.copy_example(directory)
            bind_brand_pack(project, brand)
            before_brand = (project / "BRAND.md").read_bytes()
            bind_reference_pack(project, reference)
            self.assertEqual(before_brand, (project / "BRAND.md").read_bytes())
            graph = cc.validate_project(project)
            self.assertTrue(graph.result.ok, graph.result.errors)
            self.assertEqual(
                1,
                sum(1 for kind, _ in graph.records if kind == "brand-pack"),
            )


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

    def test_unique_items_uses_json_deep_equality(self) -> None:
        schema = {
            "type": "array",
            "uniqueItems": True,
        }
        result = cc.Result()
        cc._validate_schema_node(
            [{"nested": [1]}, {"nested": [1.0]}], schema, schema, (), result
        )
        self.assertFalse(result.ok)
        self.assertTrue(any("unique items" in item for item in result.errors))

        distinct = cc.Result()
        cc._validate_schema_node([True, 1], schema, schema, (), distinct)
        self.assertTrue(distinct.ok, distinct.errors)

    def test_reference_binding_duplicate_selection_is_structurally_rejected(self) -> None:
        binding = load("skills/creative-craft/templates/reference-binding.json")
        binding["selected_reference_ids"] = ["reference-tbd", "reference-tbd"]

        _, result = cc.validate_data(binding)

        self.assertFalse(result.ok)
        self.assertTrue(any("unique items" in item for item in result.errors))

    def test_receipt_timestamps_require_timezone_and_never_raise_for_mixed_values(self) -> None:
        receipt = load("skills/creative-craft/templates/execution-receipt.json")
        cases = (
            ("2026-08-05T00:00:00Z", "2026-08-05T00:00:01"),
            ("2026-08-05T00:00:00", "2026-08-05T00:00:01Z"),
            ("not-a-time", "2026-08-05T00:00:01Z"),
            ("2026-08-05T00:00:02Z", "2026-08-05T00:00:01Z"),
        )
        for started_at, completed_at in cases:
            with self.subTest(started_at=started_at, completed_at=completed_at):
                specimen = copy.deepcopy(receipt)
                specimen["started_at"] = started_at
                specimen["completed_at"] = completed_at
                _, result = cc.validate_data(specimen)
                self.assertFalse(result.ok)

    def test_timestamp_offsets_are_normalized_to_utc_before_ordering(self) -> None:
        receipt = load("skills/creative-craft/templates/execution-receipt.json")
        receipt["started_at"] = "2026-08-05T08:00:00+08:00"
        receipt["completed_at"] = "2026-08-05T00:00:01Z"

        _, result = cc.validate_data(receipt)

        self.assertTrue(result.ok, result.errors)

    def test_approved_inspection_rejects_naive_or_reverse_approval_timestamp(self) -> None:
        check = {
            "id": "check-1",
            "status": "pass",
            "observation": "Synthetic observation.",
            "interpretation": "Synthetic interpretation.",
        }
        inspection = load("skills/creative-craft/templates/output-inspection.json")
        inspection.update({
            "decision": "approved",
            "inspector": "reviewer",
            "inspected_at": "2026-08-05T00:00:02Z",
            "invariant_checks": [check],
            "technical_checks": [{**check, "id": "check-2"}],
            "rights_checks": [{**check, "id": "check-3"}],
            "approval": {
                "approved_by": "owner",
                "approved_at": "2026-08-05T00:00:01",
                "approval_basis": "Synthetic review.",
            },
        })

        _, naive = cc.validate_data(inspection)
        self.assertFalse(naive.ok)

        inspection["approval"]["approved_at"] = "2026-08-05T00:00:01Z"
        _, reverse = cc.validate_data(inspection)
        self.assertFalse(reverse.ok)
        self.assertTrue(any("at or after" in item for item in reverse.errors))


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

    def test_manifest_symlink_outside_project_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            project = self.copy_example(directory)
            manifest_path = project / "project-manifest.json"
            outside_manifest = root / "outside-manifest.json"
            manifest_path.replace(outside_manifest)
            manifest_path.symlink_to(outside_manifest)

            graph = cc.validate_project(project)

            self.assertFalse(graph.result.ok)
            self.assertTrue(any("manifest" in item and "symlink" in item
                                for item in graph.result.errors))

    def test_nested_manifest_symlink_outside_project_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            project = root / "project"
            with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
                self.assertEqual(0, cc.cmd_seed(SeedTests.args(project)))
            manifest_path = project / ".creative-craft/project-manifest.json"
            outside_manifest = root / "outside-manifest.json"
            manifest_path.replace(outside_manifest)
            manifest_path.symlink_to(outside_manifest)

            graph = cc.validate_project(project)

            self.assertFalse(graph.result.ok)
            self.assertTrue(any("manifest" in item and "symlink" in item
                                for item in graph.result.errors))

    def test_symlink_project_root_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            project = self.copy_example(directory)
            project_link = root / "project-link"
            project_link.symlink_to(project, target_is_directory=True)

            graph = cc.validate_project(project_link)

            self.assertFalse(graph.result.ok)
            self.assertTrue(any("project root must not be a symlink" in item
                                for item in graph.result.errors))

    def test_project_doctor_reports_unregistered_symlink_without_following_it(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            project = Path(directory) / "project"
            with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
                self.assertEqual(0, cc.cmd_seed(SeedTests.args(project)))
            unsafe = project / ".creative-craft/execution-receipt.json"
            unsafe.symlink_to(cc.TEMPLATES_DIR / "execution-receipt.json")
            nested_snapshot = project / ".creative-craft/reference-snapshots/example"
            nested_snapshot.mkdir(parents=True)
            (nested_snapshot / "ignored.json").symlink_to(
                cc.TEMPLATES_DIR / "execution-receipt.json"
            )
            before = tree_snapshot(project)
            args = type("Args", (), {"root": str(project), "json": True})()
            stdout = io.StringIO()

            with contextlib.redirect_stdout(stdout):
                self.assertEqual(1, cc.cmd_doctor_project(args))

            payload = json.loads(stdout.getvalue())
            self.assertFalse(payload["healthy"])
            unsafe_findings = [
                item for item in payload["unregistered_artifacts"]
                if item["classification"] == "unsafe_symlink"
            ]
            self.assertEqual([".creative-craft/execution-receipt.json"],
                             [item["path"] for item in unsafe_findings])
            self.assertEqual(before, tree_snapshot(project))

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
