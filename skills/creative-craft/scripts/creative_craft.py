#!/usr/bin/env python3
"""Portable tooling for Creative Craft.

The CLI intentionally uses only the Python standard library. It validates and
compiles creative artifacts but never calls a provider or incurs generation
costs.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import re
import shutil
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Iterable

SCRIPT_PATH = Path(__file__).resolve()
SKILL_ROOT = SCRIPT_PATH.parents[1]
REPO_ROOT = SCRIPT_PATH.parents[3]
TEMPLATES_DIR = SKILL_ROOT / "templates"
PROVIDERS_DIR = SKILL_ROOT / "providers"

EVIDENCE_STATES = {
    "SPECIFIED",
    "OBSERVED",
    "INFERRED",
    "HYPOTHESIZED",
    "UNVERIFIED",
}
IMAGE_PROFILE_ID = "openai.gpt-image-2.2026-04-21"
VIDEO_PROFILE_ID = "bytedance.seedance-2.5.2026-07-31"


@dataclass
class Result:
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.errors

    def extend(self, other: "Result") -> None:
        self.errors.extend(other.errors)
        self.warnings.extend(other.warnings)

    def require(self, condition: bool, message: str) -> None:
        if not condition:
            self.errors.append(message)

    def warn(self, condition: bool, message: str) -> None:
        if not condition:
            self.warnings.append(message)


def load_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise ValueError(f"file not found: {path}") from exc
    except json.JSONDecodeError as exc:
        raise ValueError(
            f"invalid JSON in {path}: line {exc.lineno}, column {exc.colno}: {exc.msg}"
        ) from exc
    if not isinstance(value, dict):
        raise ValueError(f"top-level JSON value must be an object: {path}")
    return value


def write_atomic(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(text, encoding="utf-8")
    tmp.replace(path)


def nonempty(value: Any) -> bool:
    return isinstance(value, str) and bool(value.strip())


def require_string(result: Result, data: dict[str, Any], key: str, prefix: str = "") -> None:
    result.require(nonempty(data.get(key)), f"{prefix}{key} must be a non-empty string")


def require_list(result: Result, data: dict[str, Any], key: str, prefix: str = "") -> None:
    result.require(isinstance(data.get(key), list), f"{prefix}{key} must be an array")


def provider_profiles() -> dict[str, dict[str, Any]]:
    profiles: dict[str, dict[str, Any]] = {}
    for path in sorted(PROVIDERS_DIR.glob("*.json")):
        data = load_json(path)
        profile_id = data.get("profile_id")
        if isinstance(profile_id, str):
            profiles[profile_id] = data
    return profiles


def validate_brief(data: dict[str, Any]) -> Result:
    r = Result()
    r.require(data.get("schema_version") == "creative-craft.brief.v1",
              "schema_version must be creative-craft.brief.v1")
    require_string(r, data, "brief_id")
    r.require(data.get("status") in {"draft", "working", "locked", "superseded"},
              "status is invalid")
    project = data.get("project")
    r.require(isinstance(project, dict), "project must be an object")
    if isinstance(project, dict):
        require_string(r, project, "name", "project.")
        require_string(r, project, "owner", "project.")
    objective = data.get("objective")
    r.require(isinstance(objective, dict), "objective must be an object")
    if isinstance(objective, dict):
        require_string(r, objective, "business", "objective.")
        require_string(r, objective, "communication", "objective.")
    audience = data.get("audience")
    r.require(isinstance(audience, dict), "audience must be an object")
    if isinstance(audience, dict):
        require_string(r, audience, "primary", "audience.")
        require_string(r, audience, "context", "audience.")
    for key in ("tension", "insight"):
        item = data.get(key)
        r.require(isinstance(item, dict), f"{key} must be an object")
        if isinstance(item, dict):
            require_string(r, item, "statement", f"{key}.")
            r.require(item.get("evidence_state") in EVIDENCE_STATES,
                      f"{key}.evidence_state is invalid")
    require_string(r, data, "proposition")
    response = data.get("desired_response")
    r.require(isinstance(response, dict), "desired_response must be an object")
    if isinstance(response, dict):
        for key in ("feel", "think", "do"):
            require_string(r, response, key, "desired_response.")
    constraints = data.get("constraints")
    r.require(isinstance(constraints, dict), "constraints must be an object")
    if isinstance(constraints, dict):
        require_list(r, constraints, "must", "constraints.")
        require_list(r, constraints, "must_not", "constraints.")
    if data.get("status") == "locked":
        r.warn(bool(data.get("channels")), "locked brief has no channels")
        r.warn(bool(data.get("deliverables")), "locked brief has no deliverables")
        insight = data.get("insight", {})
        r.warn(insight.get("evidence_state") != "UNVERIFIED",
               "locked brief still has an unverified insight")
    return r


def validate_asset_ledger(data: dict[str, Any]) -> Result:
    r = Result()
    r.require(data.get("schema_version") == "creative-craft.asset-ledger.v1",
              "schema_version must be creative-craft.asset-ledger.v1")
    require_string(r, data, "project_id")
    assets = data.get("assets")
    r.require(isinstance(assets, list), "assets must be an array")
    seen: set[str] = set()
    if isinstance(assets, list):
        for i, asset in enumerate(assets):
            p = f"assets[{i}]."
            r.require(isinstance(asset, dict), f"assets[{i}] must be an object")
            if not isinstance(asset, dict):
                continue
            asset_id = asset.get("asset_id")
            r.require(nonempty(asset_id), p + "asset_id must be a non-empty string")
            if isinstance(asset_id, str):
                r.require(asset_id not in seen, p + f"duplicate asset_id: {asset_id}")
                seen.add(asset_id)
            for key in ("path_or_uri", "mime_type", "creator", "owner"):
                require_string(r, asset, key, p)
            r.require(asset.get("rights_status") in {
                "CLEARED", "LIMITED", "EXPIRED", "REJECTED", "UNVERIFIED"
            }, p + "rights_status is invalid")
            r.require(asset.get("consent_status") in {
                "CLEARED", "LIMITED", "REJECTED", "UNVERIFIED", "NOT_APPLICABLE"
            }, p + "consent_status is invalid")
            require_list(r, asset, "allowed_use", p)
            require_list(r, asset, "reference_roles", p)
            digest = asset.get("sha256")
            if digest is not None:
                r.require(isinstance(digest, str) and bool(re.fullmatch(r"[0-9a-fA-F]{64}", digest)),
                          p + "sha256 must be null or a 64-character hex digest")
    return r


def parse_image_size(size: str) -> tuple[int, int] | None:
    if size == "auto":
        return None
    match = re.fullmatch(r"(\d+)x(\d+)", size)
    if not match:
        raise ValueError("size must be auto or WIDTHxHEIGHT")
    return int(match.group(1)), int(match.group(2))


def validate_image_job(data: dict[str, Any]) -> Result:
    r = Result()
    r.require(data.get("schema_version") == "creative-craft.image-job.v1",
              "schema_version must be creative-craft.image-job.v1")
    for key in ("job_id", "brief_id", "provider_profile", "intended_use"):
        require_string(r, data, key)
    r.require(data.get("task_type") in {"generate", "edit"}, "task_type is invalid")
    r.require(data.get("execution_mode") in {"single_turn", "multi_turn"},
              "execution_mode is invalid")
    r.require(data.get("status") in {
        "draft", "ready", "executed", "inspected", "approved", "superseded"
    }, "status is invalid")

    profiles = provider_profiles()
    profile_id = data.get("provider_profile")
    profile = profiles.get(profile_id)
    r.require(profile is not None, f"unknown provider_profile: {profile_id!r}")

    canvas = data.get("canvas")
    r.require(isinstance(canvas, dict), "canvas must be an object")
    if isinstance(canvas, dict):
        for key in ("size", "quality", "format", "background"):
            require_string(r, canvas, key, "canvas.")
        r.require(canvas.get("quality") in {"low", "medium", "high", "auto"},
                  "canvas.quality is invalid")
        r.require(canvas.get("format") in {"png", "jpeg", "webp"},
                  "canvas.format is invalid")
        compression = canvas.get("compression")
        r.require(
            compression is None or (
                isinstance(compression, int) and not isinstance(compression, bool)
                and 0 <= compression <= 100
            ),
            "canvas.compression must be null or an integer from 0 to 100",
        )
        if compression is not None:
            r.require(
                canvas.get("format") in {"jpeg", "webp"},
                "canvas.compression is supported only for jpeg or webp",
            )
        r.require(canvas.get("background") in {"opaque", "auto"},
                  "canvas.background is invalid for the current GPT Image 2 profile")
        variants = canvas.get("variants")
        r.require(isinstance(variants, int) and variants >= 1,
                  "canvas.variants must be an integer >= 1")
        size = canvas.get("size")
        if isinstance(size, str) and profile:
            try:
                parsed = parse_image_size(size)
            except ValueError as exc:
                r.errors.append(f"canvas.size: {exc}")
            else:
                if parsed is not None:
                    width, height = parsed
                    caps = profile["capabilities"]["size"]
                    r.require(max(width, height) <= caps["max_edge_px"],
                              f"canvas.size maximum edge exceeds {caps['max_edge_px']}px")
                    r.require(width % caps["edge_multiple_px"] == 0 and
                              height % caps["edge_multiple_px"] == 0,
                              f"canvas.size edges must be multiples of {caps['edge_multiple_px']}px")
                    ratio = max(width, height) / min(width, height)
                    r.require(ratio <= caps["max_aspect_ratio"],
                              f"canvas.size aspect ratio exceeds {caps['max_aspect_ratio']}:1")
                    pixels = width * height
                    r.require(caps["min_total_pixels"] <= pixels <= caps["max_total_pixels"],
                              "canvas.size total pixels are outside the provider profile")
                    if pixels > caps["experimental_above_total_pixels"]:
                        r.warnings.append(
                            "canvas.size is above the provider profile's experimental reliability boundary"
                        )

    prompt = data.get("prompt")
    r.require(isinstance(prompt, dict), "prompt must be an object")
    if isinstance(prompt, dict):
        for key in ("scene", "subject", "composition", "lighting", "materials_style"):
            require_string(r, prompt, key, "prompt.")
        for key in ("exact_text", "references", "change", "preserve", "constraints", "exclude"):
            require_list(r, prompt, key, "prompt.")
        if data.get("task_type") == "edit":
            r.warn(bool(prompt.get("change")), "edit job has no explicit change list")
            r.warn(bool(prompt.get("preserve")), "edit job has no explicit preserve list")
        seen_refs: set[str] = set()
        for i, ref in enumerate(prompt.get("references", []) if isinstance(prompt.get("references"), list) else []):
            if not isinstance(ref, dict):
                r.errors.append(f"prompt.references[{i}] must be an object")
                continue
            asset_id = ref.get("asset_id")
            role = ref.get("role")
            r.require(nonempty(asset_id), f"prompt.references[{i}].asset_id is required")
            r.require(nonempty(role), f"prompt.references[{i}].role is required")
            if isinstance(asset_id, str):
                r.require(asset_id not in seen_refs,
                          f"prompt.references[{i}] duplicates asset_id {asset_id}")
                seen_refs.add(asset_id)
    require_list(r, data, "inspection")
    rights = data.get("rights")
    r.require(isinstance(rights, dict), "rights must be an object")
    if isinstance(rights, dict):
        r.require(rights.get("status") in {"CLEARED", "LIMITED", "REJECTED", "UNVERIFIED"},
                  "rights.status is invalid")
        if data.get("status") in {"approved"}:
            r.require(rights.get("status") in {"CLEARED", "LIMITED"},
                      "approved image job cannot have rejected or unverified rights")
    return r


def validate_video_job(data: dict[str, Any]) -> Result:
    r = Result()
    r.require(data.get("schema_version") == "creative-craft.video-job.v1",
              "schema_version must be creative-craft.video-job.v1")
    for key in ("job_id", "brief_id", "provider_profile", "intended_use", "premise", "end_state"):
        require_string(r, data, key)
    r.require(data.get("task_type") in {
        "text_to_video", "image_to_video", "reference_to_video", "extend_video", "edit_video"
    }, "task_type is invalid")
    r.require(data.get("execution_mode") in {"single_pass", "extension", "edit"},
              "execution_mode is invalid")
    r.require(data.get("status") in {
        "draft", "ready", "executed", "inspected", "approved", "superseded"
    }, "status is invalid")

    profiles = provider_profiles()
    profile_id = data.get("provider_profile")
    profile = profiles.get(profile_id)
    r.require(profile is not None, f"unknown provider_profile: {profile_id!r}")

    duration = data.get("duration_seconds")
    r.require(isinstance(duration, (int, float)) and not isinstance(duration, bool) and duration > 0,
              "duration_seconds must be a positive number")
    if isinstance(duration, (int, float)) and not isinstance(duration, bool) and profile:
        maximum = profile["capabilities"]["single_pass_max_seconds"]
        r.require(duration <= maximum,
                  f"duration_seconds exceeds the current per-job limit of {maximum}s; use extension jobs")

    fmt = data.get("format")
    r.require(isinstance(fmt, dict), "format must be an object")
    if isinstance(fmt, dict):
        for key in ("aspect_ratio", "resolution_target", "language"):
            require_string(r, fmt, key, "format.")

    refs = data.get("references")
    r.require(isinstance(refs, list), "references must be an array")
    counts = {"images": 0, "videos": 0, "audio": 0}
    seen_refs: set[str] = set()
    if isinstance(refs, list):
        for i, ref in enumerate(refs):
            if not isinstance(ref, dict):
                r.errors.append(f"references[{i}] must be an object")
                continue
            asset_id = ref.get("asset_id")
            kind = ref.get("kind")
            role = ref.get("role")
            r.require(nonempty(asset_id), f"references[{i}].asset_id is required")
            r.require(kind in {"image", "video", "audio", "clay_render"},
                      f"references[{i}].kind is invalid")
            r.require(nonempty(role), f"references[{i}].role is required")
            if isinstance(asset_id, str):
                r.require(asset_id not in seen_refs,
                          f"references[{i}] duplicates asset_id {asset_id}")
                seen_refs.add(asset_id)
            if kind in {"image", "clay_render"}:
                counts["images"] += 1
            elif kind == "video":
                counts["videos"] += 1
            elif kind == "audio":
                counts["audio"] += 1
    if profile:
        limits = profile["capabilities"]["reference_limits"]
        for key in counts:
            r.require(counts[key] <= limits[key],
                      f"{key} reference count {counts[key]} exceeds provider profile limit {limits[key]}")

    require_list(r, data, "continuity_locks")
    timeline = data.get("timeline")
    r.require(isinstance(timeline, list) and bool(timeline), "timeline must be a non-empty array")
    last_end = 0.0
    if isinstance(timeline, list):
        for i, beat in enumerate(timeline):
            if not isinstance(beat, dict):
                r.errors.append(f"timeline[{i}] must be an object")
                continue
            start = beat.get("start")
            end = beat.get("end")
            numeric = all(isinstance(v, (int, float)) and not isinstance(v, bool)
                          for v in (start, end))
            r.require(numeric, f"timeline[{i}] start/end must be numbers")
            if numeric:
                r.require(0 <= start < end, f"timeline[{i}] must satisfy 0 <= start < end")
                if isinstance(duration, (int, float)) and not isinstance(duration, bool):
                    r.require(end <= duration, f"timeline[{i}].end exceeds duration_seconds")
                r.require(start >= last_end,
                          f"timeline[{i}] overlaps or is out of chronological order")
                if start > last_end:
                    r.warnings.append(f"timeline has an uncovered gap from {last_end:g}s to {start:g}s")
                last_end = max(last_end, float(end))
            for key in ("visual", "action", "camera", "audio"):
                require_string(r, beat, key, f"timeline[{i}].")
        if isinstance(duration, (int, float)) and not isinstance(duration, bool) and timeline:
            if last_end < duration:
                r.warnings.append(
                    f"timeline ends at {last_end:g}s but duration_seconds is {duration:g}s"
                )

    env = data.get("environment")
    r.require(isinstance(env, dict), "environment must be an object")
    if isinstance(env, dict):
        for key in ("lighting", "materials", "physics"):
            require_string(r, env, key, "environment.")
    audio = data.get("dialogue_audio")
    r.require(isinstance(audio, dict), "dialogue_audio must be an object")
    if isinstance(audio, dict):
        require_list(r, audio, "dialogue", "dialogue_audio.")
        require_list(r, audio, "effects", "dialogue_audio.")
        for key in ("voice", "ambience", "music"):
            if not isinstance(audio.get(key), str):
                r.errors.append(f"dialogue_audio.{key} must be a string")

    edit = data.get("edit")
    r.require(isinstance(edit, dict), "edit must be an object")
    if isinstance(edit, dict):
        require_list(r, edit, "change", "edit.")
        require_list(r, edit, "preserve", "edit.")
        if data.get("task_type") == "edit_video" or data.get("execution_mode") == "edit":
            r.warn(nonempty(edit.get("range")), "edit job has no explicit time range")
            r.warn(bool(edit.get("change")), "edit job has no change list")
            r.warn(bool(edit.get("preserve")), "edit job has no preserve list")
    if data.get("task_type") == "extend_video":
        r.warn(bool(data.get("continuity_locks")),
               "extension job has no continuity locks")
        r.warn(any(ref.get("kind") == "video" for ref in refs if isinstance(ref, dict)) if isinstance(refs, list) else False,
               "extension job has no source video reference")

    require_list(r, data, "exclude")
    require_list(r, data, "inspection")
    rights = data.get("rights")
    r.require(isinstance(rights, dict), "rights must be an object")
    if isinstance(rights, dict):
        r.require(rights.get("status") in {"CLEARED", "LIMITED", "REJECTED", "UNVERIFIED"},
                  "rights.status is invalid")
        if data.get("status") == "approved":
            r.require(rights.get("status") in {"CLEARED", "LIMITED"},
                      "approved video job cannot have rejected or unverified rights")
    return r


def validate_evaluation(data: dict[str, Any]) -> Result:
    r = Result()
    r.require(data.get("schema_version") == "creative-craft.evaluation.v1",
              "schema_version must be creative-craft.evaluation.v1")
    for key in ("evaluation_id", "target_id", "brief_id", "recommendation"):
        require_string(r, data, key)
    r.require(data.get("stage") in {"route", "direction", "output", "delivery"},
              "stage is invalid")
    gates = data.get("gates")
    r.require(isinstance(gates, dict), "gates must be an object")
    if isinstance(gates, dict):
        for key in ("rights_clear", "brief_locked", "deliverable_specified"):
            r.require(isinstance(gates.get(key), bool), f"gates.{key} must be boolean")
        r.require(isinstance(gates.get("actual_output_observed"), (bool, type(None))),
                  "gates.actual_output_observed must be boolean or null")
    dims = data.get("dimensions")
    r.require(isinstance(dims, list) and bool(dims), "dimensions must be a non-empty array")
    seen: set[str] = set()
    if isinstance(dims, list):
        for i, dim in enumerate(dims):
            if not isinstance(dim, dict):
                r.errors.append(f"dimensions[{i}] must be an object")
                continue
            dim_id = dim.get("id")
            r.require(nonempty(dim_id), f"dimensions[{i}].id is required")
            if isinstance(dim_id, str):
                r.require(dim_id not in seen, f"duplicate dimension id: {dim_id}")
                seen.add(dim_id)
            weight = dim.get("weight")
            score = dim.get("score")
            r.require(isinstance(weight, (int, float)) and not isinstance(weight, bool) and weight > 0,
                      f"dimensions[{i}].weight must be > 0")
            r.require(isinstance(score, (int, float)) and not isinstance(score, bool) and 0 <= score <= 5,
                      f"dimensions[{i}].score must be between 0 and 5")
            r.require(dim.get("evidence_state") in EVIDENCE_STATES,
                      f"dimensions[{i}].evidence_state is invalid")
            r.require(isinstance(dim.get("evidence"), str),
                      f"dimensions[{i}].evidence must be a string")
            r.require(dim.get("confidence") in {"low", "medium", "high"},
                      f"dimensions[{i}].confidence is invalid")
        total_weight = sum(float(d.get("weight", 0)) for d in dims
                           if isinstance(d, dict) and isinstance(d.get("weight"), (int, float)))
        r.warn(math.isclose(total_weight, 100.0, rel_tol=0, abs_tol=0.001),
               f"dimension weights sum to {total_weight:g}, not 100")
    require_list(r, data, "remaining_unknowns")
    return r


def validate_concept_routes(data: dict[str, Any]) -> Result:
    r = Result()
    r.require(data.get("schema_version") == "creative-craft.concept-routes.v1",
              "schema_version must be creative-craft.concept-routes.v1")
    require_string(r, data, "brief_id")
    routes = data.get("routes")
    r.require(isinstance(routes, list) and bool(routes), "routes must be a non-empty array")
    seen: set[str] = set()
    if isinstance(routes, list):
        mechanisms: list[str] = []
        for i, route in enumerate(routes):
            if not isinstance(route, dict):
                r.errors.append(f"routes[{i}] must be an object")
                continue
            for key in ("route_id", "name", "premise", "mechanism", "hook",
                        "architecture", "visual_world", "hero_moment", "why_it_may_win"):
                require_string(r, route, key, f"routes[{i}].")
            route_id = route.get("route_id")
            if isinstance(route_id, str):
                r.require(route_id not in seen, f"duplicate route_id: {route_id}")
                seen.add(route_id)
            mechanism = route.get("mechanism")
            if isinstance(mechanism, str):
                mechanisms.append(mechanism.strip().lower())
            r.require(route.get("decision") in {
                "SELECT", "SELECT_FOR_TEST", "HOLD", "MERGE_ELEMENT", "REWORK", "REJECT"
            }, f"routes[{i}].decision is invalid")
        if len(mechanisms) > 1:
            r.warn(len(set(mechanisms)) == len(mechanisms),
                   "two or more routes use identical mechanism text; verify real distinctness")
    return r


def validate_critique(data: dict[str, Any]) -> Result:
    r = Result()
    r.require(data.get("schema_version") == "creative-craft.critique.v1",
              "schema_version must be creative-craft.critique.v1")
    require_string(r, data, "critique_id")
    require_string(r, data, "asset_id")
    for key in ("observations", "interpretations", "performance_hypotheses",
                "decisions", "unknowns"):
        require_list(r, data, key)
    allowed = {
        "KEEP", "AMPLIFY", "POLISH", "SIMPLIFY", "RECOMPOSE", "REWRITE",
        "REGENERATE", "RE_EDIT", "RE_SHOOT", "REPLACE", "DROP", "TEST",
        "DEFER", "DOCUMENT"
    }
    for i, decision in enumerate(data.get("decisions", []) if isinstance(data.get("decisions"), list) else []):
        r.require(isinstance(decision, dict), f"decisions[{i}] must be an object")
        if isinstance(decision, dict):
            r.require(decision.get("decision") in allowed,
                      f"decisions[{i}].decision is invalid")
    return r


def validate_delivery(data: dict[str, Any]) -> Result:
    r = Result()
    r.require(data.get("schema_version") == "creative-craft.delivery.v1",
              "schema_version must be creative-craft.delivery.v1")
    for key in ("delivery_id", "project_id", "selected_route"):
        require_string(r, data, key)
    r.require(data.get("status") in {
        "planned", "prompt_ready", "generated", "inspected", "needs_revision",
        "approved", "delivered", "published", "superseded"
    }, "status is invalid")
    files = data.get("files")
    r.require(isinstance(files, list), "files must be an array")
    seen: set[str] = set()
    if isinstance(files, list):
        for i, item in enumerate(files):
            if not isinstance(item, dict):
                r.errors.append(f"files[{i}] must be an object")
                continue
            asset_id = item.get("asset_id")
            r.require(nonempty(asset_id), f"files[{i}].asset_id is required")
            if isinstance(asset_id, str):
                r.require(asset_id not in seen, f"duplicate delivery asset_id: {asset_id}")
                seen.add(asset_id)
            for key in ("path_or_uri", "role", "channel", "placement", "aspect_ratio",
                        "format", "language", "source"):
                require_string(r, item, key, f"files[{i}].")
            r.require(item.get("rights_status") in {"CLEARED", "LIMITED", "REJECTED", "UNVERIFIED"},
                      f"files[{i}].rights_status is invalid")
            if data.get("status") in {"approved", "delivered", "published"}:
                r.require(item.get("rights_status") in {"CLEARED", "LIMITED"},
                          f"files[{i}] cannot be {data.get('status')} with unresolved rights")
                r.require(nonempty(item.get("sha256")),
                          f"files[{i}] needs sha256 for {data.get('status')} delivery")
    require_list(r, data, "validation")
    require_list(r, data, "remaining_risks")
    return r


VALIDATORS: dict[str, Callable[[dict[str, Any]], Result]] = {
    "brief": validate_brief,
    "asset-ledger": validate_asset_ledger,
    "image": validate_image_job,
    "video": validate_video_job,
    "evaluation": validate_evaluation,
    "concept-routes": validate_concept_routes,
    "critique": validate_critique,
    "delivery": validate_delivery,
}

SCHEMA_TO_KIND = {
    "creative-craft.brief.v1": "brief",
    "creative-craft.asset-ledger.v1": "asset-ledger",
    "creative-craft.image-job.v1": "image",
    "creative-craft.video-job.v1": "video",
    "creative-craft.evaluation.v1": "evaluation",
    "creative-craft.concept-routes.v1": "concept-routes",
    "creative-craft.critique.v1": "critique",
    "creative-craft.delivery.v1": "delivery",
}


def validate_data(data: dict[str, Any], kind: str = "auto") -> tuple[str, Result]:
    resolved = kind
    if kind == "auto":
        resolved = SCHEMA_TO_KIND.get(str(data.get("schema_version")), "")
        if not resolved:
            return "unknown", Result(errors=[
                f"cannot infer kind from schema_version {data.get('schema_version')!r}"
            ])
    validator = VALIDATORS.get(resolved)
    if validator is None:
        return resolved, Result(errors=[f"unsupported validation kind: {resolved}"])
    return resolved, validator(data)


def render_result(path: Path, kind: str, result: Result, as_json: bool) -> int:
    payload = {
        "file": str(path),
        "kind": kind,
        "valid": result.ok,
        "errors": result.errors,
        "warnings": result.warnings,
    }
    if as_json:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        status = "PASS" if result.ok else "FAIL"
        print(f"{status} {kind}: {path}")
        for message in result.errors:
            print(f"  ERROR: {message}")
        for message in result.warnings:
            print(f"  WARN:  {message}")
    return 0 if result.ok else 1


def bullet_lines(items: Iterable[Any]) -> list[str]:
    values = [str(item).strip() for item in items if str(item).strip()]
    return [f"- {value}" for value in values]


def section(title: str, lines: Iterable[str]) -> list[str]:
    values = [line for line in lines if line.strip()]
    if not values:
        return []
    return [f"### {title}", *values, ""]


def compile_image_markdown(data: dict[str, Any]) -> str:
    canvas = data["canvas"]
    prompt = data["prompt"]
    out: list[str] = [
        f"# Image execution pack — {data['job_id']}",
        "",
        f"- Provider profile: `{data['provider_profile']}`",
        f"- Task: `{data['task_type']}`",
        f"- Execution mode: `{data['execution_mode']}`",
        f"- Status: `{data['status']}`",
        f"- Size: `{canvas['size']}`",
        f"- Quality: `{canvas['quality']}`",
        f"- Format: `{canvas['format']}`",
        f"- Compression: `{canvas['compression'] if canvas['compression'] is not None else 'provider default'}`",
        f"- Background: `{canvas['background']}`",
        f"- Variants: `{canvas['variants']}`",
        "",
        "## Prompt",
        "",
    ]
    prompt_lines: list[str] = []
    prompt_lines += section("INTENDED USE AND OUTPUT", [
        data["intended_use"],
        f"Create {canvas['variants']} output variant(s) at {canvas['size']}, "
        f"{canvas['quality']} quality, {canvas['format']} format, "
        f"{canvas['background']} background."
    ])
    prompt_lines += section("BACKGROUND / SCENE", [prompt["scene"]])
    prompt_lines += section("SUBJECT", [prompt["subject"]])
    prompt_lines += section("ACTION / EXPRESSION", [prompt.get("action", "")])
    prompt_lines += section("COMPOSITION / CAMERA / NEGATIVE SPACE", [prompt["composition"]])
    prompt_lines += section("LIGHTING", [prompt["lighting"]])
    prompt_lines += section("MATERIALS / MEDIUM / STYLE", [prompt["materials_style"]])

    exact_text_lines: list[str] = []
    for item in prompt.get("exact_text", []):
        if not isinstance(item, dict):
            continue
        text = item.get("text", "")
        placement = item.get("placement", "")
        typography = item.get("typography", "")
        suffix = "; ".join(part for part in (placement, typography) if part)
        exact_text_lines.append(f'- "{text}"' + (f" — {suffix}" if suffix else ""))
    if exact_text_lines:
        exact_text_lines.append("- Include no other text unless explicitly listed.")
    prompt_lines += section("EXACT TEXT / TYPOGRAPHY", exact_text_lines)

    reference_lines: list[str] = []
    for ref in prompt.get("references", []):
        if not isinstance(ref, dict):
            continue
        line = f"- @{ref.get('asset_id')}: {ref.get('role')}"
        preserve = ref.get("preserve", [])
        if preserve:
            line += f" Preserve: {', '.join(str(x) for x in preserve)}."
        reference_lines.append(line)
    prompt_lines += section("REFERENCE MAP", reference_lines)
    prompt_lines += section("CHANGE ONLY", bullet_lines(prompt.get("change", [])))
    prompt_lines += section("PRESERVE EXACTLY", bullet_lines(prompt.get("preserve", [])))
    prompt_lines += section("CONSTRAINTS", bullet_lines(prompt.get("constraints", [])))
    prompt_lines += section("DO NOT ADD / EXCLUDE", bullet_lines(prompt.get("exclude", [])))

    out.extend(["```text", *prompt_lines, "```", "", "## Post-generation inspection", ""])
    out.extend(bullet_lines(data.get("inspection", [])))
    out.extend([
        "",
        f"Rights status: `{data.get('rights', {}).get('status', 'UNVERIFIED')}`",
        "",
        "This pack is `prompt_ready`; it is not evidence that an image was generated or approved.",
    ])
    return "\n".join(out).rstrip() + "\n"


def compile_video_markdown(data: dict[str, Any]) -> str:
    fmt = data["format"]
    out: list[str] = [
        f"# Video execution pack — {data['job_id']}",
        "",
        f"- Provider profile: `{data['provider_profile']}`",
        f"- Task: `{data['task_type']}`",
        f"- Execution mode: `{data['execution_mode']}`",
        f"- Status: `{data['status']}`",
        f"- Duration: `{data['duration_seconds']}s`",
        f"- Aspect ratio: `{fmt['aspect_ratio']}`",
        f"- Resolution target: `{fmt['resolution_target']}`",
        f"- Language: `{fmt['language']}`",
        "",
        "## Prompt",
        "",
    ]
    prompt_lines: list[str] = []
    prompt_lines += section("FORMAT AND INTENDED USE", [
        data["intended_use"],
        f"{data['duration_seconds']}-second audiovisual video, "
        f"{fmt['aspect_ratio']}, {fmt['resolution_target']}, language {fmt['language']}."
    ])
    prompt_lines += section("CREATIVE PREMISE", [data["premise"]])
    prompt_lines += section("END STATE", [data["end_state"]])

    reference_lines: list[str] = []
    for ref in data.get("references", []):
        if isinstance(ref, dict):
            reference_lines.append(
                f"- @{ref.get('asset_id')} ({ref.get('kind')}): {ref.get('role')}"
            )
    prompt_lines += section("REFERENCE MAP", reference_lines)
    prompt_lines += section("CONTINUITY LOCKS", bullet_lines(data.get("continuity_locks", [])))

    beat_lines: list[str] = []
    for beat in data.get("timeline", []):
        if not isinstance(beat, dict):
            continue
        beat_lines.extend([
            f"{beat.get('start'):g}–{beat.get('end'):g}s",
            f"- Visual: {beat.get('visual')}",
            f"- Action/performance: {beat.get('action')}",
            f"- Camera: {beat.get('camera')}",
            f"- Audio: {beat.get('audio')}",
            "",
        ])
    prompt_lines += section("TIMESTAMPED BEATS", beat_lines)

    env = data.get("environment", {})
    prompt_lines += section("ENVIRONMENT / MATERIAL / LIGHT / PHYSICS", [
        f"- Lighting: {env.get('lighting', '')}",
        f"- Materials: {env.get('materials', '')}",
        f"- Physics: {env.get('physics', '')}",
    ])
    audio = data.get("dialogue_audio", {})
    audio_lines: list[str] = []
    for dialogue in audio.get("dialogue", []):
        audio_lines.append(f'- Dialogue: "{dialogue}"')
    audio_lines.extend([
        f"- Voice: {audio.get('voice', '')}",
        f"- Ambience: {audio.get('ambience', '')}",
    ])
    audio_lines.extend(f"- Effect: {x}" for x in audio.get("effects", []))
    audio_lines.append(f"- Music: {audio.get('music', '')}")
    prompt_lines += section("DIALOGUE / VOICE / AMBIENCE / EFFECTS / MUSIC", audio_lines)

    edit = data.get("edit", {})
    edit_lines: list[str] = []
    if edit.get("range"):
        edit_lines.append(f"- Time range: {edit['range']}")
    edit_lines += bullet_lines(edit.get("change", []))
    prompt_lines += section("EDIT ONLY", edit_lines)
    prompt_lines += section("PRESERVE", bullet_lines(edit.get("preserve", [])))
    prompt_lines += section("EXCLUDE / FAILURE CONDITIONS", bullet_lines(data.get("exclude", [])))

    out.extend(["```text", *prompt_lines, "```", "", "## Post-generation inspection", ""])
    out.extend(bullet_lines(data.get("inspection", [])))
    out.extend([
        "",
        f"Rights status: `{data.get('rights', {}).get('status', 'UNVERIFIED')}`",
        "",
        "This pack is `prompt_ready`; it is not evidence that a video was generated or approved.",
    ])
    return "\n".join(out).rstrip() + "\n"


def score_evaluation(data: dict[str, Any]) -> dict[str, Any]:
    kind, validation = validate_data(data, "evaluation")
    if not validation.ok:
        return {
            "status": "invalid",
            "errors": validation.errors,
            "warnings": validation.warnings,
        }

    gates = data["gates"]
    required_gates = {
        "rights_clear": gates["rights_clear"],
        "brief_locked": gates["brief_locked"],
        "deliverable_specified": gates["deliverable_specified"],
    }
    if data["stage"] in {"output", "delivery"}:
        required_gates["actual_output_observed"] = bool(gates["actual_output_observed"])
    failed = [name for name, value in required_gates.items() if not value]
    if failed:
        return {
            "status": "blocked",
            "score": None,
            "coverage": None,
            "failed_gates": failed,
            "warnings": validation.warnings,
        }

    dimensions = data["dimensions"]
    total_weight = sum(float(d["weight"]) for d in dimensions)
    covered = [
        d for d in dimensions
        if d["evidence_state"] != "UNVERIFIED" and str(d.get("evidence", "")).strip()
    ]
    covered_weight = sum(float(d["weight"]) for d in covered)
    coverage = 100.0 * covered_weight / total_weight if total_weight else 0.0

    if coverage < 80.0:
        return {
            "status": "withheld",
            "score": None,
            "coverage": round(coverage, 2),
            "reason": "evidence coverage is below 80%",
            "warnings": validation.warnings,
        }

    numerator = sum((float(d["score"]) / 5.0) * float(d["weight"]) for d in covered)
    score = 100.0 * numerator / covered_weight if covered_weight else 0.0
    if coverage >= 100:
        coverage_confidence = "high"
    elif coverage >= 90:
        coverage_confidence = "medium"
    else:
        coverage_confidence = "low"
    explicit_conf = [d["confidence"] for d in covered]
    rank = {"low": 0, "medium": 1, "high": 2}
    min_dim = min(explicit_conf, key=lambda x: rank[x]) if explicit_conf else "low"
    confidence = min((coverage_confidence, min_dim), key=lambda x: rank[x])
    return {
        "status": "scored",
        "score": round(score, 2),
        "coverage": round(coverage, 2),
        "confidence": confidence,
        "stage": data["stage"],
        "recommendation": data["recommendation"],
        "warnings": validation.warnings,
        "dimensions": [
            {
                "id": d["id"],
                "weight": d["weight"],
                "score": d["score"],
                "evidence_state": d["evidence_state"],
                "confidence": d["confidence"],
            }
            for d in dimensions
        ],
    }


def markdown_local_links(path: Path) -> Iterable[tuple[str, Path]]:
    text = path.read_text(encoding="utf-8")
    for target in re.findall(r"\]\(([^)]+)\)", text):
        target = target.split("#", 1)[0].strip()
        if not target or re.match(r"^[a-zA-Z][a-zA-Z0-9+.-]*:", target):
            continue
        yield target, (path.parent / target).resolve()


def doctor(root: Path = REPO_ROOT) -> Result:
    r = Result()
    required = [
        "README.md",
        "README.zh-CN.md",
        "LICENSE",
        "VERSION",
        "package.json",
        ".codex-plugin/plugin.json",
        "sources.lock.json",
        "skills/creative-craft/SKILL.md",
        "skills/creative-craft/VERSION",
        "skills/creative-craft/providers/openai-gpt-image-2.json",
        "skills/creative-craft/providers/bytedance-seedance-2.5.json",
        "skills/creative-craft/scripts/creative_craft.py",
    ]
    for rel in required:
        r.require((root / rel).is_file(), f"missing required file: {rel}")

    if (root / "VERSION").is_file():
        version = (root / "VERSION").read_text(encoding="utf-8").strip()
        if (root / "skills/creative-craft/VERSION").is_file():
            r.require(
                (root / "skills/creative-craft/VERSION").read_text(encoding="utf-8").strip() == version,
                "root and skill VERSION do not match",
            )
        for rel, field_path in [
            ("package.json", ("version",)),
            (".codex-plugin/plugin.json", ("version",)),
        ]:
            path = root / rel
            if path.is_file():
                try:
                    data = load_json(path)
                    actual: Any = data
                    for field_name in field_path:
                        actual = actual[field_name]
                    r.require(actual == version, f"{rel} version {actual!r} does not match {version!r}")
                except (ValueError, KeyError) as exc:
                    r.errors.append(str(exc))

    for path in sorted(root.rglob("*.json")):
        if any(part in {".git", "node_modules"} for part in path.parts):
            continue
        try:
            load_json(path)
        except ValueError as exc:
            r.errors.append(str(exc))

    profiles = provider_profiles()
    r.require(IMAGE_PROFILE_ID in profiles, f"missing provider profile {IMAGE_PROFILE_ID}")
    r.require(VIDEO_PROFILE_ID in profiles, f"missing provider profile {VIDEO_PROFILE_ID}")
    for profile_id, profile in profiles.items():
        r.require(nonempty(profile.get("verified_at")), f"{profile_id} has no verified_at")
        r.require(bool(profile.get("sources")), f"{profile_id} has no sources")

    for path in sorted(root.rglob("*.md")):
        if any(part in {".git", "node_modules"} for part in path.parts):
            continue
        for target, resolved in markdown_local_links(path):
            r.require(resolved.exists(), f"broken local link in {path.relative_to(root)}: {target}")

    return r


def cmd_doctor(args: argparse.Namespace) -> int:
    root = Path(args.root).resolve() if args.root else REPO_ROOT
    result = doctor(root)
    return render_result(root, "repository", result, args.json)


def cmd_self_test(args: argparse.Namespace) -> int:
    """Run package-contained smoke tests without network or dev dependencies."""
    root = Path(args.root).resolve() if args.root else REPO_ROOT
    repository = doctor(root)
    checks: list[dict[str, Any]] = []
    errors = list(repository.errors)
    warnings = list(repository.warnings)

    templates_dir = root / "skills" / "creative-craft" / "templates"
    for path in sorted(templates_dir.glob("*.json")):
        try:
            data = load_json(path)
        except ValueError as exc:
            errors.append(str(exc))
            checks.append({"file": str(path), "kind": "unknown", "valid": False})
            continue
        kind, result = validate_data(data, "auto")
        errors.extend(f"{path.name}: {message}" for message in result.errors)
        warnings.extend(f"{path.name}: {message}" for message in result.warnings)
        checks.append({
            "file": str(path.relative_to(root)),
            "kind": kind,
            "valid": result.ok,
        })

    # Exercise deterministic compilers and the evidence-aware scoring path.
    try:
        image_data = load_json(templates_dir / "image-job.json")
        image_pack = compile_image_markdown(image_data)
        if "# Image execution pack" not in image_pack:
            errors.append("image compiler did not produce an execution pack")

        video_data = load_json(templates_dir / "video-job.json")
        video_pack = compile_video_markdown(video_data)
        if "# Video execution pack" not in video_pack:
            errors.append("video compiler did not produce an execution pack")

        evaluation_data = load_json(templates_dir / "evaluation.json")
        score = score_evaluation(evaluation_data)
        if score.get("status") not in {"scored", "withheld", "blocked"}:
            errors.append("evaluation scorer returned an invalid status")
    except (KeyError, TypeError, ValueError) as exc:
        errors.append(f"package smoke path failed: {exc}")

    payload = {
        "valid": not errors,
        "repository_valid": repository.ok,
        "artifact_checks": checks,
        "errors": errors,
        "warnings": warnings,
    }
    if args.json:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        print("PASS package self-test" if not errors else "FAIL package self-test")
        print(f"  Artifact templates: {len(checks)}")
        for message in errors:
            print(f"  ERROR: {message}")
        for message in warnings:
            print(f"  WARN:  {message}")
    return 0 if not errors else 1


def cmd_validate(args: argparse.Namespace) -> int:
    path = Path(args.file).resolve()
    try:
        data = load_json(path)
    except ValueError as exc:
        result = Result(errors=[str(exc)])
        return render_result(path, args.kind, result, args.json)
    kind, result = validate_data(data, args.kind)
    return render_result(path, kind, result, args.json)


def output_text(text: str, output: str | None) -> None:
    if output:
        path = Path(output).resolve()
        write_atomic(path, text)
        print(path)
    else:
        print(text, end="")


def cmd_compile_image(args: argparse.Namespace) -> int:
    path = Path(args.file).resolve()
    try:
        data = load_json(path)
    except ValueError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    result = validate_image_job(data)
    if not result.ok:
        render_result(path, "image", result, False)
        return 1
    for warning in result.warnings:
        print(f"WARN: {warning}", file=sys.stderr)
    output_text(compile_image_markdown(data), args.output)
    return 0


def cmd_compile_video(args: argparse.Namespace) -> int:
    path = Path(args.file).resolve()
    try:
        data = load_json(path)
    except ValueError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    result = validate_video_job(data)
    if not result.ok:
        render_result(path, "video", result, False)
        return 1
    for warning in result.warnings:
        print(f"WARN: {warning}", file=sys.stderr)
    output_text(compile_video_markdown(data), args.output)
    return 0


def cmd_score(args: argparse.Namespace) -> int:
    path = Path(args.file).resolve()
    try:
        data = load_json(path)
    except ValueError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    result = score_evaluation(data)
    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        print(f"Status: {result['status']}")
        if result.get("score") is not None:
            print(f"Score: {result['score']:.2f}/100")
        if result.get("coverage") is not None:
            print(f"Evidence coverage: {result['coverage']:.2f}%")
        if result.get("confidence"):
            print(f"Confidence: {result['confidence']}")
        if result.get("failed_gates"):
            print("Failed gates: " + ", ".join(result["failed_gates"]))
        if result.get("reason"):
            print("Reason: " + result["reason"])
        if result.get("recommendation"):
            print("Recommendation: " + result["recommendation"])
        for warning in result.get("warnings", []):
            print(f"WARN: {warning}")
        for error in result.get("errors", []):
            print(f"ERROR: {error}")
    return 0 if result["status"] in {"scored", "withheld", "blocked"} else 1


def cmd_hash(args: argparse.Namespace) -> int:
    path = Path(args.file).resolve()
    if not path.is_file():
        print(f"ERROR: file not found: {path}", file=sys.stderr)
        return 1
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    if args.json:
        print(json.dumps({
            "file": str(path),
            "bytes": path.stat().st_size,
            "sha256": digest.hexdigest(),
        }, indent=2))
    else:
        print(digest.hexdigest())
    return 0


def cmd_seed(args: argparse.Namespace) -> int:
    target = Path(args.target).expanduser().resolve()
    target.mkdir(parents=True, exist_ok=True)
    copies = {
        TEMPLATES_DIR / "BRAND.md": target / "BRAND.md",
        TEMPLATES_DIR / "CREATIVE.md": target / "CREATIVE.md",
        TEMPLATES_DIR / "DELIVERABLES.md": target / "DELIVERABLES.md",
        TEMPLATES_DIR / "creative-brief.json": target / ".creative-craft" / "creative-brief.json",
        TEMPLATES_DIR / "concept-routes.json": target / ".creative-craft" / "concept-routes.json",
        TEMPLATES_DIR / "asset-ledger.json": target / ".creative-craft" / "asset-ledger.json",
        TEMPLATES_DIR / "image-job.json": target / ".creative-craft" / "image-job.json",
        TEMPLATES_DIR / "video-job.json": target / ".creative-craft" / "video-job.json",
        TEMPLATES_DIR / "evaluation.json": target / ".creative-craft" / "evaluation.json",
        TEMPLATES_DIR / "delivery-manifest.json": target / ".creative-craft" / "delivery-manifest.json",
    }
    conflicts = [dst for dst in copies.values() if dst.exists() and not args.force]
    if conflicts:
        print("ERROR: refusing to overwrite existing files:", file=sys.stderr)
        for path in conflicts:
            print(f"  {path}", file=sys.stderr)
        print("Use --force only after reviewing the existing authority.", file=sys.stderr)
        return 1
    for src, dst in copies.items():
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dst)
        print(dst)
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="creative-craft",
        description="Validate and compile Creative Craft artifacts without calling providers.",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    doctor_parser = sub.add_parser("doctor", help="check repository integrity")
    doctor_parser.add_argument("--root")
    doctor_parser.add_argument("--json", action="store_true")
    doctor_parser.set_defaults(func=cmd_doctor)

    self_test_parser = sub.add_parser(
        "self-test", help="run package-contained validation and compiler smoke tests"
    )
    self_test_parser.add_argument("--root")
    self_test_parser.add_argument("--json", action="store_true")
    self_test_parser.set_defaults(func=cmd_self_test)

    validate_parser = sub.add_parser("validate", help="validate a versioned artifact")
    validate_parser.add_argument("--file", required=True)
    validate_parser.add_argument(
        "--kind",
        default="auto",
        choices=["auto", *sorted(VALIDATORS)],
    )
    validate_parser.add_argument("--json", action="store_true")
    validate_parser.set_defaults(func=cmd_validate)

    image_parser = sub.add_parser("compile-image", help="compile an image job into a prompt pack")
    image_parser.add_argument("--file", required=True)
    image_parser.add_argument("--output")
    image_parser.set_defaults(func=cmd_compile_image)

    video_parser = sub.add_parser("compile-video", help="compile a video job into a prompt pack")
    video_parser.add_argument("--file", required=True)
    video_parser.add_argument("--output")
    video_parser.set_defaults(func=cmd_compile_video)

    score_parser = sub.add_parser("score", help="calculate an evidence-aware comparative score")
    score_parser.add_argument("--file", required=True)
    score_parser.add_argument("--json", action="store_true")
    score_parser.set_defaults(func=cmd_score)

    hash_parser = sub.add_parser("hash", help="calculate an asset SHA-256")
    hash_parser.add_argument("--file", required=True)
    hash_parser.add_argument("--json", action="store_true")
    hash_parser.set_defaults(func=cmd_hash)

    seed_parser = sub.add_parser("seed", help="seed authority and job templates into a project")
    seed_parser.add_argument("--target", required=True)
    seed_parser.add_argument("--force", action="store_true")
    seed_parser.set_defaults(func=cmd_seed)
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())
