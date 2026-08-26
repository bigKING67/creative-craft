"""Tests for the repository-only Agent quality evaluation harness."""

from __future__ import annotations

import importlib.util
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from support import ROOT

EVAL_PATH = ROOT / "scripts" / "evaluate_agent_quality.py"
SPEC = importlib.util.spec_from_file_location("creative_craft_agent_eval", EVAL_PATH)
assert SPEC and SPEC.loader
agent_eval = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = agent_eval
SPEC.loader.exec_module(agent_eval)


def score(label: str, *, total_offset: int, scope: int = 10) -> dict:
    values = {
        "label": label,
        "strategic_fit": 12 + total_offset,
        "distinctiveness": 9,
        "execution_readiness": 12,
        "evidence_honesty": 8,
        "reference_change_preserve": 8,
        "scope_proportionality": scope,
        "clarity_usefulness": 8,
        "traceability_integrity": True,
        "notes": "Synthetic judge fixture.",
    }
    values["total"] = sum(values[field] for field in agent_eval.SCORE_FIELDS)
    return values


class EvalConfigurationTests(unittest.TestCase):
    def test_fixed_suite_has_seven_quality_and_four_routing_cases(self) -> None:
        quality = agent_eval.load_cases()
        routing = agent_eval.load_routing_cases()
        self.assertEqual(7, len(quality))
        self.assertEqual(4, len(routing))
        self.assertEqual(
            {"quick", "traceable"}, {case["expected_mode"] for case in quality}
        )

    def test_skill_entrypoint_stays_below_context_budget(self) -> None:
        skill = (ROOT / "skills/creative-craft/SKILL.md").read_text(encoding="utf-8")
        self.assertLessEqual(len(skill.split()), 2000)
        self.assertIn("Quick Craft - default", skill)
        self.assertIn("references/traceable-project.md", skill)

    def test_codex_command_is_ephemeral_and_read_only(self) -> None:
        command = agent_eval.build_codex_command(
            "codex",
            model="gpt-5.6-sol",
            reasoning="high",
            output_file=Path("/tmp/result"),
            output_schema=Path("/tmp/schema"),
        )
        self.assertIn("--ephemeral", command)
        self.assertIn("--ignore-user-config", command)
        self.assertIn("--ignore-rules", command)
        self.assertEqual("read-only", command[command.index("--sandbox") + 1])
        self.assertEqual("-", command[-1])
        self.assertNotIn("--dangerously-bypass-approvals-and-sandbox", command)

    def test_public_receipt_contains_no_auth_or_absolute_paths(self) -> None:
        receipt = agent_eval.public_command_receipt(
            kind="quality",
            model="gpt-5.6-sol",
            reasoning="high",
            has_schema=True,
            has_skill=True,
        )
        serialized = " ".join(receipt)
        self.assertNotIn(str(Path.home()), serialized)
        self.assertNotIn("auth.json", serialized)
        self.assertIn("<isolated-output>", serialized)
        self.assertIn("<repo-schema>", serialized)

    def test_provider_config_extracts_only_allowlisted_transport_fields(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            config = Path(directory) / "config.toml"
            config.write_text(
                'model_provider = "fixture"\n'
                '[model_providers.fixture]\n'
                'name = "Fixture"\n'
                'base_url = "http://127.0.0.1:8317/v1"\n'
                'wire_api = "responses"\n'
                'requires_openai_auth = true\n'
                'supports_websockets = true\n'
                'experimental_bearer_token = "must-not-escape"\n',
                encoding="utf-8",
            )

            transport = agent_eval.load_provider_transport(config)

            assert transport is not None
            self.assertEqual("fixture", transport["id"])
            self.assertEqual("responses", transport["wire_api"])
            self.assertNotIn("experimental_bearer_token", transport)
            command = agent_eval.build_codex_command(
                "codex",
                model="gpt-5.6-sol",
                reasoning="high",
                output_file=Path("/tmp/result"),
                provider_transport=transport,
            )
            self.assertNotIn("must-not-escape", " ".join(command))

    def test_run_directory_must_stay_under_ignored_eval_root(self) -> None:
        with (
            tempfile.TemporaryDirectory() as directory,
            self.assertRaises(agent_eval.EvalError),
        ):
            agent_eval.ensure_output_run_dir(Path(directory) / "run")


class IsolatedCodexTests(unittest.TestCase):
    def test_auth_is_symlinked_without_becoming_command_or_output_data(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            auth = root / "auth.json"
            auth.write_text("secret-fixture", encoding="utf-8")
            output = root / "result.md"
            events = root / "events.jsonl"
            stderr = root / "events.stderr"

            def fake_run(command: list[str], **kwargs: object) -> subprocess.CompletedProcess:
                environment = kwargs["env"]
                assert isinstance(environment, dict)
                codex_home = Path(environment["CODEX_HOME"])
                isolated_auth = codex_home / "auth.json"
                self.assertTrue(isolated_auth.is_symlink())
                self.assertTrue(os.path.samefile(auth, isolated_auth))
                self.assertTrue(
                    (codex_home / "skills/creative-craft/SKILL.md").is_file()
                )
                self.assertNotIn(str(auth), command)
                isolated_output = Path(command[command.index("--output-last-message") + 1])
                isolated_output.write_text("creative result", encoding="utf-8")
                return subprocess.CompletedProcess(command, 0, "{\"type\":\"done\"}\n", "")

            with mock.patch.object(agent_eval.subprocess, "run", side_effect=fake_run):
                result = agent_eval.run_codex(
                    prompt="fixture prompt",
                    skill_source=ROOT / "skills/creative-craft",
                    output_file=output,
                    events_file=events,
                    stderr_file=stderr,
                    output_schema=None,
                    auth_file=auth,
                    codex_bin="codex",
                    model="gpt-5.6-sol",
                    reasoning="high",
                    timeout_seconds=10,
                    provider_transport=None,
                )

            self.assertEqual(0, result["returncode"])
            self.assertEqual("creative result", output.read_text(encoding="utf-8"))
            self.assertNotIn("secret-fixture", events.read_text(encoding="utf-8"))

    def test_timeout_preserves_byte_streams_and_raises_eval_error(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            auth = root / "auth.json"
            auth.write_text("secret-fixture", encoding="utf-8")
            events = root / "events.jsonl"
            stderr = root / "events.stderr"
            timeout = subprocess.TimeoutExpired(
                cmd=["codex"],
                timeout=10,
                output=b'{"type":"partial"}\n',
                stderr=b"provider still running\n",
            )

            with (
                mock.patch.object(agent_eval.subprocess, "run", side_effect=timeout),
                self.assertRaisesRegex(agent_eval.EvalError, "timed out after 10s"),
            ):
                agent_eval.run_codex(
                    prompt="fixture prompt",
                    skill_source=None,
                    output_file=root / "result.md",
                    events_file=events,
                    stderr_file=stderr,
                    output_schema=None,
                    auth_file=auth,
                    codex_bin="codex",
                    model="gpt-5.6-sol",
                    reasoning="high",
                    timeout_seconds=10,
                    provider_transport=None,
                )

            self.assertEqual('{"type":"partial"}\n', events.read_text(encoding="utf-8"))
            self.assertEqual("provider still running\n", stderr.read_text(encoding="utf-8"))


class ReportTests(unittest.TestCase):
    def test_rendered_report_names_comparison_without_implying_installed_copy(
        self,
    ) -> None:
        aggregate = {field: 1 for field in agent_eval.SCORE_FIELDS}
        aggregate["total"] = len(agent_eval.SCORE_FIELDS)
        report = {
            "status": "PASS",
            "aggregates": {
                variant: dict(aggregate) for variant in agent_eval.VARIANTS
            },
            "acceptance_checks": {},
            "per_case": {
                "fixture": {
                    "scores": {
                        variant: {"total": aggregate["total"]}
                        for variant in agent_eval.VARIANTS
                    }
                }
            },
            "limitations": [],
        }
        manifest = {
            "model": "fixture-model",
            "reasoning": "high",
            "codex_version": "fixture-codex",
            "current_revision": "abc123",
            "candidate_skill_sha256": "def456",
            "calls": [],
        }

        rendered = agent_eval.render_report(report, manifest)

        self.assertIn("Comparison revision: `abc123`", rendered)
        self.assertIn("| no Skill |", rendered)
        self.assertIn("| comparison |", rendered)
        self.assertIn("| Case | No Skill | Comparison | Candidate |", rendered)
        self.assertNotIn("Current revision:", rendered)

    def test_acceptance_report_is_computed_from_blind_label_mapping(self) -> None:
        quality_cases = agent_eval.load_cases()
        judge_index = {"schema_version": 1, "cases": {}}
        for case in quality_cases:
            judge_index["cases"][case["id"]] = {
                "label_map": {"A": "baseline", "B": "current", "C": "candidate"},
                "scores": [
                    score("A", total_offset=0, scope=9),
                    score("B", total_offset=1, scope=10),
                    score("C", total_offset=3, scope=12),
                ],
                "summary": "Synthetic blind comparison.",
            }
        route_index = {
            "schema_version": 1,
            "cases": {
                case["id"]: {
                    "expected": case["expect_creative_craft"],
                    "actual": case["expect_creative_craft"],
                    "passed": True,
                    "reason": "Synthetic route result.",
                }
                for case in agent_eval.load_routing_cases()
            },
        }

        report = agent_eval.compute_report(quality_cases, judge_index, route_index)

        self.assertEqual("PASS", report["status"])
        self.assertTrue(all(report["acceptance_checks"].values()))
        self.assertEqual(7, report["counts"]["candidate_beats_baseline"])

    def test_routing_failure_keeps_claim_at_partial(self) -> None:
        quality_cases = agent_eval.load_cases()
        judge_index = {"schema_version": 1, "cases": {}}
        for case in quality_cases:
            judge_index["cases"][case["id"]] = {
                "label_map": {"A": "baseline", "B": "current", "C": "candidate"},
                "scores": [
                    score("A", total_offset=0, scope=9),
                    score("B", total_offset=1, scope=10),
                    score("C", total_offset=3, scope=12),
                ],
                "summary": "Synthetic blind comparison.",
            }
        route_index = {
            "schema_version": 1,
            "cases": {
                "broken": {
                    "expected": False,
                    "actual": True,
                    "passed": False,
                    "reason": "Synthetic failure.",
                }
            },
        }

        report = agent_eval.compute_report(quality_cases, judge_index, route_index)

        self.assertEqual("PARTIAL", report["status"])
        self.assertFalse(report["acceptance_checks"]["routing_all_correct"])
