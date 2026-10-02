"""Video Harness v1: shared-contract semantics and production stage gates."""

from __future__ import annotations

import copy
import json
import os
import tempfile
import unittest
from pathlib import Path

from support import ROOT, cc, load, write_json
from video_support import (
    build_talking_head_production,
    edit_document,
    generate_beat,
    production,
    production_plan,
    render_qa,
    run_cli,
    stage,
    write_doc,
    write_generation,
)

FIXTURES = ROOT / "tests/fixtures"


def errors(data: dict) -> list[str]:
    return cc.validate_data(data)[1].errors


class EditDocumentContractTests(unittest.TestCase):
    def test_shared_valid_fixture_passes(self) -> None:
        self.assertEqual(
            [], errors(load("tests/fixtures/edit-document-v2/valid/multitrack.json"))
        )

    def test_every_shared_invalid_fixture_is_rejected_for_its_rule(self) -> None:
        expected = {
            "audio-only-asset-on-video-track": "requires an asset with video",
            "caption-link-reversed-range": "source_to must be greater",
            "caption-link-unknown-item": "link must reference a media item",
            "caption-on-video-track": "must be on a caption track",
            "duplicate-item-id": "duplicates id",
            "first-revision-with-parent": "revision 1 must have parent_sha256 null",
            "free-caption-missing-timing": "caption without link requires start_frame",
            "media-missing-source-in": "requires source_in_seconds",
            "same-track-overlap": "overlap",
            "source-range-exceeds-asset": "beyond asset duration",
            "unknown-asset": "unknown asset",
            "unknown-track": "unknown track",
            "media-with-caption-field": "media item must not set text",
            "caption-with-media-field": "caption item must not set volume",
            "linked-caption-with-timing": "linked caption must not set start_frame",
            "later-revision-without-parent": "revision > 1 requires parent_sha256",
        }
        paths = sorted((FIXTURES / "edit-document-v2/invalid").glob("*.json"))
        self.assertEqual(set(expected), {path.stem for path in paths})
        for path in paths:
            with self.subTest(path.stem):
                found = errors(json.loads(path.read_text(encoding="utf-8")))
                self.assertTrue(
                    any(expected[path.stem] in message for message in found), found
                )

    def test_later_revision_requires_parent_and_duration_limit(self) -> None:
        doc = edit_document(2, None)
        self.assertIn("revision > 1 requires parent_sha256", errors(doc))
        doc = edit_document(1)
        doc["items"] = [
            item
            for item in doc["items"]
            if item["kind"] == "caption" and "link" not in item
        ]
        self.assertIn("edit duration must be at least one frame", errors(doc))

    def test_timeline_helpers(self) -> None:
        doc = edit_document(2, "f" * 64, generated=True)
        self.assertEqual(450, cc.edit_document_duration_frames(doc))
        self.assertAlmostEqual(90 / 450, cc.edit_document_generated_share(doc))
        frames = cc.edit_document_item_frames(doc)
        self.assertEqual((0, 90), frames["cap1"])
        self.assertEqual((300, 390), frames["cap2"])


class RenderQaContractTests(unittest.TestCase):
    def setUp(self) -> None:
        self.qa = load("tests/fixtures/render-qa/sample.json")

    def test_sample_passes(self) -> None:
        self.assertEqual([], errors(self.qa))

    def test_review_rules(self) -> None:
        cases = {
            "completed review requires reviewer": lambda qa: qa["review"].update(
                reviewer=None
            ),
            "completed review requires a decision": lambda qa: qa["review"].update(
                decision="pending"
            ),
            "pending decision requires review.status pending": lambda qa: (
                qa["review"].update(status="pending", decision="pending", reviewer="x")
                or qa["review"].update(status="done")
            ),
            "contradicts checks": lambda qa: qa.update(verdict="pass"),
            "critical finding requires fix": lambda qa: (
                qa["review"]["findings"][0].update(severity="critical")
                or qa["review"]["findings"][0].pop("fix")
            ),
            "unknown sample": lambda qa: qa["checks"][3]["refs"][0].update(
                sample_id="ghost"
            ),
        }
        for message, mutate in cases.items():
            with self.subTest(message):
                qa = copy.deepcopy(self.qa)
                mutate(qa)
                self.assertTrue(
                    any(message in error for error in errors(qa)), errors(qa)
                )

    def test_verdict_derivation(self) -> None:
        qa = copy.deepcopy(self.qa)
        qa["checks"][2]["status"] = "fail"
        qa["verdict"] = "fail"
        self.assertEqual([], errors(qa))
        qa["checks"][2]["status"] = "pass"
        qa["verdict"] = "pass"
        self.assertEqual([], errors(qa))


class ProductionPlanContractTests(unittest.TestCase):
    def test_plan_rules(self) -> None:
        self.assertEqual([], errors(production_plan()))
        cases = {
            "duplicates id": lambda plan: plan["beats"].append(
                copy.deepcopy(plan["beats"][0])
            ),
            "outside the selected source range": lambda plan: plan["beats"][0][
                "selection"
            ]["evidence"][0].update(start_seconds=40, end_seconds=41),
            "selection end must be after start": lambda plan: plan["beats"][0][
                "selection"
            ].update(source_end_seconds=1.0),
            "duration_range requires min and max": lambda plan: plan[
                "delivery_promises"
            ][0]["check"].pop("max"),
            "max between 0 and 1": lambda plan: plan["delivery_promises"][2][
                "check"
            ].update(max=1.5),
            "generation_ref requires source_kind generate": lambda plan: plan["beats"][
                0
            ].update(generation_ref={"job_path": "j.json", "receipt_path": None}),
            "must not set min or max": lambda plan: plan["delivery_promises"][1][
                "check"
            ].update(min=1),
        }
        for message, mutate in cases.items():
            with self.subTest(message):
                plan = production_plan()
                mutate(plan)
                self.assertTrue(
                    any(message in error for error in errors(plan)), errors(plan)
                )

    def test_production_state_rules(self) -> None:
        data = load("skills/creative-craft/templates/video-production.json")
        self.assertEqual([], errors(data))
        capped = copy.deepcopy(data)
        capped["policy"]["budget"]["mode"] = "cap"
        self.assertIn("budget mode cap requires a numeric cap", errors(capped))
        reordered = copy.deepcopy(data)
        reordered["stages"].reverse()
        self.assertTrue(any("in order" in error for error in errors(reordered)))


class VideoGateTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name) / "prod"
        self.r = str(self.root)

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def cli(self, *argv: str, code: int = 0) -> str:
        actual, out, err = run_cli(*argv[:1], "--root", self.r, *argv[1:])
        self.assertEqual(code, actual, out + err)
        return out + err

    def init(self, *extra: str) -> None:
        self.cli("video-init", "--production-id", "gates", *extra)

    def plan_ready(self, plan: dict | None = None, *, approve: bool = False) -> None:
        self.init(*([] if approve else ["--approval-required", "none"]))
        self.cli("video-skip", "--stage", "brief", "--reason", "brief given in chat")
        self.cli("video-skip", "--stage", "reference", "--reason", "no references")
        write_doc(self.root, "plan.json", plan or production_plan())
        self.cli(
            "video-record",
            "--stage",
            "plan",
            "--kind",
            "production-plan",
            "--artifact",
            "plan.json",
        )

    def assembled(self) -> str:
        self.plan_ready()
        self.cli("video-complete", "--stage", "plan")
        self.cli("video-complete", "--stage", "select")
        self.cli("video-skip", "--stage", "generate", "--reason", "footage only")
        sha = write_doc(self.root, "rev/000001.json", edit_document(1))
        self.cli(
            "video-record",
            "--stage",
            "assemble",
            "--kind",
            "edit-document",
            "--artifact",
            "rev/000001.json",
        )
        self.cli("video-complete", "--stage", "assemble")
        return sha

    def inspect(self, rel: str, qa: dict, code: int = 0) -> str:
        write_doc(self.root, rel, qa)
        self.cli(
            "video-record",
            "--stage",
            "inspect",
            "--kind",
            "render-qa",
            "--artifact",
            rel,
        )
        return self.cli("video-complete", "--stage", "inspect", code=code)

    def test_init_refuses_existing_production(self) -> None:
        self.init()
        self.cli("video-init", "--production-id", "again", code=1)

    def test_predecessors_block_later_stages(self) -> None:
        self.init()
        out = self.cli("video-complete", "--stage", "select", code=1)
        self.assertIn("preceding stage brief is not completed or skipped", out)
        self.assertEqual("blocked", stage(self.root, "select")["status"])
        self.cli("video-complete", "--stage", "brief", code=1)  # no artifact recorded

    def test_plan_awaits_approval_then_completes(self) -> None:
        self.plan_ready(approve=True)
        self.assertIn(
            "awaiting_approval", self.cli("video-complete", "--stage", "plan")
        )
        self.cli("video-complete", "--stage", "select", code=1)
        self.cli("video-approve", "--stage", "select", "--by", "x", code=1)
        self.cli("video-approve", "--stage", "plan", "--by", "producer")
        plan_stage = stage(self.root, "plan")
        self.assertEqual("completed", plan_stage["status"])
        self.assertEqual("producer", plan_stage["approval"]["by"])

    def test_select_blocks_tbd_and_shows_candidates(self) -> None:
        plan = production_plan()
        plan["beats"].append(
            {**plan["beats"][0], "id": "open", "source_kind": "tbd", "selection": None}
        )
        self.plan_ready(plan)
        self.cli("video-complete", "--stage", "plan")
        self.assertIn(
            "beat open source is still tbd",
            self.cli("video-complete", "--stage", "select", code=1),
        )
        self.cli("video-skip", "--stage", "select", "--reason", "x", code=1)
        write_doc(self.root, "plan.json", production_plan())
        self.cli(
            "video-record",
            "--stage",
            "select",
            "--kind",
            "production-plan",
            "--artifact",
            "plan.json",
        )
        self.cli("video-complete", "--stage", "select")
        status = json.loads(self.cli("video-status", "--json"))
        self.assertEqual(["broll"], status["candidates"])
        self.assertEqual("generate", status["current_stage"])

    def test_generate_requires_bound_job_and_receipt(self) -> None:
        self.plan_ready(production_plan(extra_beats=[generate_beat()]))
        self.cli("video-complete", "--stage", "plan")
        self.cli("video-complete", "--stage", "select")
        self.cli("video-skip", "--stage", "generate", "--reason", "later", code=1)
        out = self.cli("video-complete", "--stage", "generate", code=1)
        self.assertIn("is not bound as video-job", out)
        write_generation(self.root, outcome="failed")
        self.cli(
            "video-record",
            "--stage",
            "generate",
            "--kind",
            "video-job",
            "--artifact",
            "jobs/gen-job.json",
        )
        self.cli(
            "video-record",
            "--stage",
            "generate",
            "--kind",
            "execution-receipt",
            "--artifact",
            "jobs/gen-receipt.json",
        )
        self.assertIn(
            "receipt outcome is failed",
            self.cli("video-complete", "--stage", "generate", code=1),
        )
        write_generation(self.root)
        self.cli(
            "video-record",
            "--stage",
            "generate",
            "--kind",
            "execution-receipt",
            "--artifact",
            "jobs/gen-receipt.json",
        )
        self.cli("video-complete", "--stage", "generate")

    def test_generate_completes_without_generate_beats(self) -> None:
        self.plan_ready()
        self.cli("video-complete", "--stage", "plan")
        self.cli("video-complete", "--stage", "select")
        self.cli("video-complete", "--stage", "generate")

    def test_record_rejects_unsafe_and_invalid_artifacts(self) -> None:
        self.init()
        outside = Path(self.tmp.name) / "outside.md"
        outside.write_text("x", encoding="utf-8")
        for value in ("../outside.md", str(outside)):
            self.cli(
                "video-record",
                "--stage",
                "brief",
                "--kind",
                "brief",
                "--artifact",
                value,
                code=1,
            )
        os.symlink(outside, self.root / "link.md")
        self.cli(
            "video-record",
            "--stage",
            "brief",
            "--kind",
            "brief",
            "--artifact",
            "link.md",
            code=1,
        )
        write_doc(self.root, "bad.json", {**production_plan(), "beats": []})
        self.cli(
            "video-record",
            "--stage",
            "plan",
            "--kind",
            "production-plan",
            "--artifact",
            "bad.json",
            code=1,
        )
        self.cli(
            "video-record",
            "--stage",
            "brief",
            "--kind",
            "edit-document",
            "--artifact",
            "bad.json",
            code=1,
        )
        self.cli(
            "video-record",
            "--stage",
            "brief",
            "--kind",
            "note",
            "--artifact",
            "production.json",
            code=1,
        )
        self.assertEqual(
            [],
            stage(self.root, "brief")["artifacts"]
            + stage(self.root, "plan")["artifacts"],
        )

    def test_drift_is_reported_and_blocks_completion(self) -> None:
        self.plan_ready()
        plan = production_plan()
        plan["title"] = "edited out of band"
        write_json(self.root / "plan.json", plan)
        status = self.cli("video-status", code=1)
        self.assertIn("DRIFT: plan.json", status)
        self.assertIn(
            "artifact drift: plan.json is modified",
            self.cli("video-complete", "--stage", "plan", code=1),
        )
        (self.root / "plan.json").unlink()
        self.assertEqual(
            "missing",
            json.loads(self.cli("video-status", "--json", code=1))["drift"][0]["state"],
        )

    def test_inspect_requires_current_revision_digest_and_review(self) -> None:
        sha = self.assembled()
        doc = edit_document(1)
        out = self.inspect("qa/stale.json", render_qa(doc, "0" * 64), code=1)
        self.assertIn("is not bound to current revision", out)
        out = self.inspect(
            "qa/pending.json", render_qa(doc, sha, review_status="pending"), code=1
        )
        self.assertIn("review is pending", out)
        self.inspect(
            "qa/fail.json", render_qa(doc, sha, decision="accept", status="fail")
        )
        self.assertEqual("in_progress", stage(self.root, "revise")["status"])
        self.assertEqual(
            "revise", json.loads(self.cli("video-status", "--json"))["current_stage"]
        )
        self.cli("video-complete", "--stage", "export", code=1)

    def test_accept_skips_revise_and_export_checks_revision_and_promises(self) -> None:
        sha = self.assembled()
        doc = edit_document(1)
        self.inspect(
            "qa/r1.json", render_qa(doc, sha, decision="accept", status="warn")
        )
        self.assertEqual("skipped", stage(self.root, "revise")["status"])
        self.cli(
            "video-record",
            "--stage",
            "revise",
            "--kind",
            "edit-document",
            "--artifact",
            "rev/000001.json",
            code=1,
        )
        other = write_doc(self.root, "rev/other.json", edit_document(2, sha))
        self.assertNotEqual(sha, other)
        self.cli(
            "video-record",
            "--stage",
            "export",
            "--kind",
            "edit-document",
            "--artifact",
            "rev/other.json",
        )
        out = self.cli("video-complete", "--stage", "export", code=1)
        self.assertIn("differs from the last accepted inspection", out)
        self.cli(
            "video-record",
            "--stage",
            "export",
            "--kind",
            "edit-document",
            "--artifact",
            "rev/000001.json",
        )
        out = self.cli("video-complete", "--stage", "export", code=1)
        self.assertIn("delivery promise length failed: observed 20.0", out)

    def test_revise_round_limit_blocks(self) -> None:
        sha1 = self.assembled()
        data = production(self.root)
        data["policy"]["max_revision_rounds"] = 1
        write_json(self.root / "production.json", data)
        self.inspect("qa/r1.json", render_qa(edit_document(1), sha1, decision="revise"))
        self.cli("video-complete", "--stage", "revise", code=1)  # nothing recorded yet
        doc2 = edit_document(2, sha1)
        sha2 = write_doc(self.root, "rev/000002.json", doc2)
        self.cli(
            "video-record",
            "--stage",
            "revise",
            "--kind",
            "edit-document",
            "--artifact",
            "rev/000001.json",
            code=1,
        )  # not newer than current revision
        self.cli(
            "video-record",
            "--stage",
            "revise",
            "--kind",
            "edit-document",
            "--artifact",
            "rev/000002.json",
        )
        self.cli("video-complete", "--stage", "revise")
        self.assertEqual(1, production(self.root)["revision_rounds"])
        self.assertEqual("pending", stage(self.root, "inspect")["status"])
        out = self.inspect(
            "qa/r2.json", render_qa(doc2, sha2, decision="reject"), code=1
        )
        self.assertIn("round limit 1 is reached", out)
        self.assertEqual("blocked", stage(self.root, "revise")["status"])
        sha3 = write_doc(self.root, "rev/000003.json", edit_document(3, sha2))
        self.assertTrue(sha3)
        self.cli(
            "video-record",
            "--stage",
            "revise",
            "--kind",
            "edit-document",
            "--artifact",
            "rev/000003.json",
        )
        self.assertIn(
            "revision round limit 1 reached",
            self.cli("video-complete", "--stage", "revise", code=1),
        )

    def test_unskippable_stages(self) -> None:
        self.init()
        for stage_id in ("assemble", "inspect", "revise", "export"):
            self.cli("video-skip", "--stage", stage_id, "--reason", "x", code=1)

    def test_budget_ledger(self) -> None:
        self.init("--budget-mode", "cap", "--budget-cap", "10")
        self.cli(
            "video-ledger",
            "reserve",
            "--id",
            "g1",
            "--stage",
            "generate",
            "--description",
            "shot",
            "--estimate",
            "6",
            "--provider-job-id",
            "job-1",
        )
        self.cli(
            "video-ledger",
            "reserve",
            "--id",
            "g2",
            "--stage",
            "generate",
            "--description",
            "retry",
            "--estimate",
            "1",
            code=1,
        )  # unknown outcome of job-1
        self.cli(
            "video-ledger",
            "reserve",
            "--id",
            "a1",
            "--stage",
            "assemble",
            "--description",
            "render",
            "--estimate",
            "5",
            code=1,
        )  # over cap
        self.cli("video-ledger", "settle", "--id", "g1", "--actual", "4")
        self.cli("video-ledger", "settle", "--id", "g1", "--actual", "4", code=1)
        self.cli(
            "video-ledger",
            "reserve",
            "--id",
            "a1",
            "--stage",
            "assemble",
            "--description",
            "render",
            "--estimate",
            "5",
        )
        self.cli("video-ledger", "release", "--id", "a1")
        budget = json.loads(self.cli("video-status", "--json"))["budget"]
        self.assertEqual(
            (0, 4, 4), (budget["reserved"], budget["settled"], budget["committed"])
        )
        self.assertTrue(all(event["at"] for event in production(self.root)["events"]))


class VideoEndToEndTests(unittest.TestCase):
    def test_talking_head_broll_captions_with_one_revision_round(self) -> None:
        for generated in (False, True):
            with (
                self.subTest(generated=generated),
                tempfile.TemporaryDirectory() as tmp,
            ):
                root = Path(tmp)
                digests = build_talking_head_production(root, generated=generated)
                data = production(root)
                self.assertTrue(
                    all(
                        item["status"] in {"completed", "skipped"}
                        for item in data["stages"]
                    )
                )
                self.assertEqual(
                    (1, 2), (data["revision_rounds"], data["current_revision"])
                )
                exported = stage(root, "export")["artifacts"][-1]
                self.assertEqual(digests["doc2"], exported["sha256"])
                code, out, _ = run_cli("video-status", "--root", tmp, "--json")
                self.assertEqual(0, code)
                status = json.loads(out)
                self.assertEqual([], status["drift"])
                promises = {
                    item["id"]: item
                    for item in status["delivery_promises_on_current_revision"]
                }
                self.assertEqual(15.0, promises["length"]["observed"])
                self.assertIsNone(promises["tone"]["passed"])
                share = promises["generated"]["observed"]
                self.assertEqual(0.2 if generated else 0.0, share)
                actions = [
                    (event["stage"], event["action"]) for event in data["events"]
                ]
                self.assertIn(("revise", "complete"), actions)
                self.assertIn(("inspect", "reopen"), actions)


class VideoExampleTests(unittest.TestCase):
    def test_example_production_has_no_drift_and_is_exported(self) -> None:
        root = ROOT / "examples/talking-head-broll-cut"
        code, out, err = run_cli("video-status", "--root", str(root), "--json")
        self.assertEqual(0, code, err)
        status = json.loads(out)
        self.assertIsNone(status["current_stage"])
        self.assertEqual([], status["drift"])


if __name__ == "__main__":
    unittest.main()
