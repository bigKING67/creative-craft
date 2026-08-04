#!/usr/bin/env python3
"""Portable tooling for Creative Craft.

The CLI intentionally uses only the Python standard library. It validates and
compiles creative artifacts but never calls a provider or incurs generation
costs.
"""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import math
import re
import shutil
import sys
from collections.abc import Callable, Iterable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

SCRIPT_PATH = Path(__file__).resolve()
SKILL_ROOT = SCRIPT_PATH.parents[1]
REPO_ROOT = SCRIPT_PATH.parents[3]
TEMPLATES_DIR = SKILL_ROOT / "templates"
PROVIDERS_DIR = SKILL_ROOT / "providers"
SURFACES_DIR = PROVIDERS_DIR / "surfaces"

EVIDENCE_STATES = {
    "SPECIFIED",
    "OBSERVED",
    "INFERRED",
    "HYPOTHESIZED",
    "UNVERIFIED",
}
IMAGE_PROFILE_ID = "openai.gpt-image-2.2026-04-21"
VIDEO_PROFILE_ID = "bytedance.seedance-2.5.2026-07-31"

ARTIFACT_REGISTRY: dict[str, dict[str, Any]] = {
    "creative-craft.brief.v1": {
        "kind": "brief", "schema": "creative-brief.schema.json",
        "template": "creative-brief.json", "legacy": False,
    },
    "creative-craft.asset-ledger.v1": {
        "kind": "asset-ledger", "schema": "asset-ledger.schema.json",
        "template": "asset-ledger.json", "legacy": False,
    },
    "creative-craft.concept-routes.v1": {
        "kind": "concept-routes", "schema": "concept-routes.schema.json",
        "template": "concept-routes.json", "legacy": False,
    },
    "creative-craft.critique.v1": {
        "kind": "critique", "schema": "critique.schema.json",
        "template": "critique.json", "legacy": False,
    },
    "creative-craft.image-job.v1": {
        "kind": "image", "schema": "image-job.schema.json",
        "template": None, "legacy": True,
    },
    "creative-craft.video-job.v1": {
        "kind": "video", "schema": "video-job.schema.json",
        "template": None, "legacy": True,
    },
    "creative-craft.evaluation.v1": {
        "kind": "evaluation", "schema": "evaluation.schema.json",
        "template": None, "legacy": True,
    },
    "creative-craft.delivery.v1": {
        "kind": "delivery", "schema": "delivery-manifest.schema.json",
        "template": None, "legacy": True,
    },
    "creative-craft.project-manifest.v1": {
        "kind": "project-manifest", "schema": "project-manifest.schema.json",
        "template": "project-manifest.json", "legacy": False,
    },
    "creative-craft.creative-direction.v1": {
        "kind": "creative-direction", "schema": "creative-direction.schema.json",
        "template": "creative-direction.json", "legacy": False,
    },
    "creative-craft.image-job.v2": {
        "kind": "image", "schema": "image-job-v2.schema.json",
        "template": "image-job.json", "legacy": False,
    },
    "creative-craft.video-job.v2": {
        "kind": "video", "schema": "video-job-v2.schema.json",
        "template": "video-job.json", "legacy": False,
    },
    "creative-craft.execution-receipt.v1": {
        "kind": "execution-receipt", "schema": "execution-receipt.schema.json",
        "template": "execution-receipt.json", "legacy": False,
    },
    "creative-craft.output-inspection.v1": {
        "kind": "output-inspection", "schema": "output-inspection.schema.json",
        "template": "output-inspection.json", "legacy": False,
    },
    "creative-craft.revision-lineage.v1": {
        "kind": "revision-lineage", "schema": "revision-lineage.schema.json",
        "template": "revision-lineage.json", "legacy": False,
    },
    "creative-craft.evaluation.v2": {
        "kind": "evaluation", "schema": "evaluation-v2.schema.json",
        "template": "evaluation.json", "legacy": False,
    },
    "creative-craft.delivery.v2": {
        "kind": "delivery", "schema": "delivery-manifest-v2.schema.json",
        "template": "delivery-manifest.json", "legacy": False,
    },
}

METADATA_SCHEMAS = {
    "creative-craft.provider.v1": "provider-profile.schema.json",
    "creative-craft.surface.v1": "surface-profile.schema.json",
    "creative-craft.sources.v1": "source-lock.schema.json",
}


@dataclass(frozen=True)
class ValidationContext:
    skill_root: Path = SKILL_ROOT

    @property
    def schemas_dir(self) -> Path:
        return self.skill_root / "schemas"

    @property
    def providers_dir(self) -> Path:
        return self.skill_root / "providers"

    @property
    def surfaces_dir(self) -> Path:
        return self.providers_dir / "surfaces"


@dataclass
class Result:
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.errors

    def extend(self, other: Result) -> None:
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
        raise ValueError(f"top-level JSON value must be an object: {path}")  # noqa: TRY004
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


def _schema_type_matches(value: Any, expected: str) -> bool:
    checks = {
        "object": lambda item: isinstance(item, dict),
        "array": lambda item: isinstance(item, list),
        "string": lambda item: isinstance(item, str),
        "number": lambda item: isinstance(item, (int, float)) and not isinstance(item, bool),
        "integer": lambda item: isinstance(item, int) and not isinstance(item, bool),
        "boolean": lambda item: isinstance(item, bool),
        "null": lambda item: item is None,
    }
    checker = checks.get(expected)
    return bool(checker and checker(value))


def _json_path(parts: tuple[Any, ...]) -> str:
    if not parts:
        return "<root>"
    return ".".join(str(part) for part in parts)


def _resolve_local_ref(root_schema: dict[str, Any], reference: str) -> dict[str, Any]:
    if not reference.startswith("#/"):
        raise ValueError(f"only local JSON Schema references are supported: {reference}")
    current: Any = root_schema
    for raw_part in reference[2:].split("/"):
        part = raw_part.replace("~1", "/").replace("~0", "~")
        if not isinstance(current, dict) or part not in current:
            raise ValueError(f"unresolved local JSON Schema reference: {reference}")
        current = current[part]
    if not isinstance(current, dict):
        raise ValueError(  # noqa: TRY004
            f"JSON Schema reference is not an object: {reference}"
        )
    return current


def _validate_schema_node(
    value: Any,
    schema: dict[str, Any],
    root_schema: dict[str, Any],
    path: tuple[Any, ...],
    result: Result,
) -> None:
    if "$ref" in schema:
        try:
            target = _resolve_local_ref(root_schema, str(schema["$ref"]))
        except ValueError as exc:
            result.errors.append(str(exc))
            return
        _validate_schema_node(value, target, root_schema, path, result)
        return

    expected = schema.get("type")
    expected_types = [expected] if isinstance(expected, str) else expected
    if isinstance(expected_types, list) and not any(
        isinstance(item, str) and _schema_type_matches(value, item)
        for item in expected_types
    ):
        label = " or ".join(str(item) for item in expected_types)
        result.errors.append(f"{_json_path(path)} must be {label}")
        return

    if "const" in schema and value != schema["const"]:
        result.errors.append(
            f"{_json_path(path)} must equal {schema['const']!r}"
        )
    if "enum" in schema and value not in schema["enum"]:
        result.errors.append(
            f"{_json_path(path)} must be one of {schema['enum']!r}"
        )

    if isinstance(value, dict):
        required = schema.get("required", [])
        if isinstance(required, list):
            for key in required:
                if key not in value:
                    result.errors.append(f"{_json_path(path + (key,))} is required")
        properties = schema.get("properties", {})
        if isinstance(properties, dict):
            for key, child_value in value.items():
                child_schema = properties.get(key)
                if isinstance(child_schema, dict):
                    _validate_schema_node(
                        child_value, child_schema, root_schema, path + (key,), result
                    )
                elif schema.get("additionalProperties") is False:
                    result.errors.append(
                        f"{_json_path(path + (key,))} is not allowed"
                    )

    if isinstance(value, list):
        minimum = schema.get("minItems")
        if isinstance(minimum, int) and len(value) < minimum:
            result.errors.append(
                f"{_json_path(path)} must contain at least {minimum} items"
            )
        maximum = schema.get("maxItems")
        if isinstance(maximum, int) and len(value) > maximum:
            result.errors.append(
                f"{_json_path(path)} must contain at most {maximum} items"
            )
        item_schema = schema.get("items")
        if isinstance(item_schema, dict):
            for index, child_value in enumerate(value):
                _validate_schema_node(
                    child_value, item_schema, root_schema, path + (index,), result
                )

    if isinstance(value, str):
        minimum = schema.get("minLength")
        if isinstance(minimum, int) and len(value) < minimum:
            result.errors.append(
                f"{_json_path(path)} must contain at least {minimum} characters"
            )
        pattern = schema.get("pattern")
        if isinstance(pattern, str) and re.search(pattern, value) is None:
            result.errors.append(
                f"{_json_path(path)} does not match pattern {pattern!r}"
            )

    if isinstance(value, (int, float)) and not isinstance(value, bool):
        minimum = schema.get("minimum")
        if isinstance(minimum, (int, float)) and value < minimum:
            result.errors.append(f"{_json_path(path)} must be >= {minimum}")
        maximum = schema.get("maximum")
        if isinstance(maximum, (int, float)) and value > maximum:
            result.errors.append(f"{_json_path(path)} must be <= {maximum}")
        exclusive_minimum = schema.get("exclusiveMinimum")
        if isinstance(exclusive_minimum, (int, float)) and value <= exclusive_minimum:
            result.errors.append(
                f"{_json_path(path)} must be > {exclusive_minimum}"
            )
        exclusive_maximum = schema.get("exclusiveMaximum")
        if isinstance(exclusive_maximum, (int, float)) and value >= exclusive_maximum:
            result.errors.append(
                f"{_json_path(path)} must be < {exclusive_maximum}"
            )


def validate_against_schema(data: dict[str, Any], schema_path: Path) -> Result:
    result = Result()
    try:
        schema = load_json(schema_path)
    except ValueError as exc:
        result.errors.append(str(exc))
        return result
    _validate_schema_node(data, schema, schema, (), result)
    return result


def provider_profiles(providers_dir: Path | None = None) -> dict[str, dict[str, Any]]:
    root = providers_dir or PROVIDERS_DIR
    profiles: dict[str, dict[str, Any]] = {}
    for path in sorted(root.glob("*.json")):
        data = load_json(path)
        profile_id = data.get("profile_id")
        if isinstance(profile_id, str):
            if profile_id in profiles:
                raise ValueError(f"duplicate provider profile_id: {profile_id}")
            profiles[profile_id] = data
    return profiles


def surface_profiles(surfaces_dir: Path | None = None) -> dict[str, dict[str, Any]]:
    root = surfaces_dir or SURFACES_DIR
    profiles: dict[str, dict[str, Any]] = {}
    for path in sorted(root.glob("*.json")):
        data = load_json(path)
        surface_id = data.get("surface_id")
        if isinstance(surface_id, str):
            if surface_id in profiles:
                raise ValueError(f"duplicate execution surface_id: {surface_id}")
            profiles[surface_id] = data
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


def validate_image_job(
    data: dict[str, Any], context: ValidationContext | None = None
) -> Result:
    context = context or ValidationContext()
    r = Result()
    version = data.get("schema_version")
    r.require(version in {"creative-craft.image-job.v1", "creative-craft.image-job.v2"},
              "schema_version must be creative-craft.image-job.v1 or v2")
    for key in ("job_id", "brief_id", "provider_profile", "intended_use"):
        require_string(r, data, key)
    r.require(data.get("task_type") in {"generate", "edit"}, "task_type is invalid")
    r.require(data.get("execution_mode") in {"single_turn", "multi_turn"},
              "execution_mode is invalid")
    if version == "creative-craft.image-job.v1":
        r.require(data.get("status") in {
            "draft", "ready", "executed", "inspected", "approved", "superseded"
        }, "status is invalid")
    else:
        for key in ("direction_id", "selected_route_id", "execution_surface"):
            require_string(r, data, key)
        require_list(r, data, "asset_refs")
        asset_refs = data.get("asset_refs", [])
        if isinstance(asset_refs, list):
            r.require(len(asset_refs) == len(set(asset_refs)),
                      "asset_refs must not contain duplicates")
        r.require(data.get("declared_status") in {"draft", "ready", "superseded"},
                  "declared_status is invalid")

    try:
        profiles = provider_profiles(context.providers_dir)
        surfaces = surface_profiles(context.surfaces_dir)
    except ValueError as exc:
        r.errors.append(str(exc))
        profiles = {}
        surfaces = {}
    profile_id = data.get("provider_profile")
    profile = profiles.get(profile_id)
    r.require(profile is not None, f"unknown provider_profile: {profile_id!r}")
    if version == "creative-craft.image-job.v2":
        surface_id = data.get("execution_surface")
        surface = surfaces.get(surface_id)
        r.require(surface is not None, f"unknown execution_surface: {surface_id!r}")
        if surface:
            r.require(surface.get("available") is True,
                      f"execution_surface is not currently available: {surface_id!r}")
            r.require(profile_id in surface.get("provider_profiles", []),
                      "execution_surface does not support provider_profile")
            r.require(data.get("execution_mode") in surface.get("modes", []),
                      "execution_surface does not support execution_mode")
            r.require(data.get("task_type") in surface.get("modes", []),
                      "execution_surface does not support task_type")

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


def validate_video_job(
    data: dict[str, Any], context: ValidationContext | None = None
) -> Result:
    context = context or ValidationContext()
    r = Result()
    version = data.get("schema_version")
    r.require(version in {"creative-craft.video-job.v1", "creative-craft.video-job.v2"},
              "schema_version must be creative-craft.video-job.v1 or v2")
    for key in ("job_id", "brief_id", "provider_profile", "intended_use", "premise", "end_state"):
        require_string(r, data, key)
    r.require(data.get("task_type") in {
        "text_to_video", "image_to_video", "reference_to_video", "extend_video", "edit_video"
    }, "task_type is invalid")
    r.require(data.get("execution_mode") in {"single_pass", "extension", "edit"},
              "execution_mode is invalid")
    if version == "creative-craft.video-job.v1":
        r.require(data.get("status") in {
            "draft", "ready", "executed", "inspected", "approved", "superseded"
        }, "status is invalid")
    else:
        for key in ("direction_id", "selected_route_id", "execution_surface"):
            require_string(r, data, key)
        require_list(r, data, "asset_refs")
        asset_refs = data.get("asset_refs", [])
        if isinstance(asset_refs, list):
            r.require(len(asset_refs) == len(set(asset_refs)),
                      "asset_refs must not contain duplicates")
        r.require(data.get("declared_status") in {"draft", "ready", "superseded"},
                  "declared_status is invalid")

    try:
        profiles = provider_profiles(context.providers_dir)
        surfaces = surface_profiles(context.surfaces_dir)
    except ValueError as exc:
        r.errors.append(str(exc))
        profiles = {}
        surfaces = {}
    profile_id = data.get("provider_profile")
    profile = profiles.get(profile_id)
    r.require(profile is not None, f"unknown provider_profile: {profile_id!r}")
    if version == "creative-craft.video-job.v2":
        surface_id = data.get("execution_surface")
        surface = surfaces.get(surface_id)
        r.require(surface is not None, f"unknown execution_surface: {surface_id!r}")
        if surface:
            r.require(surface.get("available") is True,
                      f"execution_surface is not currently available: {surface_id!r}")
            r.require(profile_id in surface.get("provider_profiles", []),
                      "execution_surface does not support provider_profile")
            r.require(data.get("execution_mode") in surface.get("modes", []),
                      "execution_surface does not support execution_mode")

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
        for key, count in counts.items():
            r.require(count <= limits[key],
                      f"{key} reference count {count} exceeds provider profile limit {limits[key]}")

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
        if (isinstance(duration, (int, float)) and not isinstance(duration, bool)
                and timeline and last_end < duration):
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


def validate_project_manifest(data: dict[str, Any]) -> Result:
    r = Result()
    seen_ids: set[tuple[str, str]] = set()
    seen_paths: set[str] = set()
    for index, artifact in enumerate(data.get("artifacts", [])):
        if not isinstance(artifact, dict):
            continue
        key = (str(artifact.get("artifact_type")), str(artifact.get("artifact_id")))
        r.require(key not in seen_ids, f"artifacts[{index}] duplicates artifact identity {key}")
        seen_ids.add(key)
        path = str(artifact.get("path", ""))
        r.require(path not in seen_paths, f"artifacts[{index}] duplicates path {path!r}")
        seen_paths.add(path)
        r.require(artifact.get("schema_version") in ARTIFACT_REGISTRY,
                  f"artifacts[{index}] has unsupported schema_version")
    return r


def validate_creative_direction(data: dict[str, Any]) -> Result:
    r = Result()
    approval = data.get("approval", {})
    if data.get("status") == "approved":
        r.require(approval.get("status") == "approved",
                  "approved direction requires approval.status=approved")
        for key in ("approved_by", "approved_at", "basis"):
            r.require(nonempty(approval.get(key)), f"approved direction requires approval.{key}")
    if data.get("status") == "locked":
        for key in ("message_hierarchy", "visual_world", "invariants", "deliverables"):
            r.require(bool(data.get(key)), f"locked direction requires {key}")
        r.require(bool(data.get("image_art_direction") or data.get("video_treatment")),
                  "locked direction requires image_art_direction or video_treatment")
    seen: set[str] = set()
    for index, ref in enumerate(data.get("reference_roles", [])):
        if isinstance(ref, dict):
            asset_id = ref.get("asset_id")
            if isinstance(asset_id, str):
                r.require(asset_id not in seen,
                          f"reference_roles[{index}] duplicates asset_id {asset_id}")
                seen.add(asset_id)
    return r


def validate_execution_receipt(
    data: dict[str, Any], context: ValidationContext | None = None
) -> Result:
    context = context or ValidationContext()
    r = Result()
    try:
        profiles = provider_profiles(context.providers_dir)
        surfaces = surface_profiles(context.surfaces_dir)
    except ValueError as exc:
        r.errors.append(str(exc))
        return r
    profile_id = data.get("provider_profile")
    surface_id = data.get("execution_surface")
    r.require(profile_id in profiles, f"unknown provider_profile: {profile_id!r}")
    r.require(surface_id in surfaces, f"unknown execution_surface: {surface_id!r}")
    if profile_id in profiles:
        profile = profiles[profile_id]
        r.require(data.get("model") == profile.get("model"),
                  "receipt model differs from provider profile")
        expected_snapshot = profile.get("snapshot")
        if expected_snapshot is not None:
            r.require(data.get("snapshot") == expected_snapshot,
                      "receipt snapshot differs from provider profile")
    if surface_id in surfaces:
        r.require(profile_id in surfaces[surface_id].get("provider_profiles", []),
                  "execution_surface does not support provider_profile")
    if data.get("outcome") in {"succeeded", "partial"}:
        r.require(bool(data.get("outputs")),
                  f"{data.get('outcome')} receipt requires at least one output")
    if data.get("outcome") in {"failed", "cancelled"}:
        r.require(not data.get("outputs"),
                  f"{data.get('outcome')} receipt must not claim outputs; use partial")
    try:
        started = dt.datetime.fromisoformat(str(data.get("started_at")).replace("Z", "+00:00"))
        completed = dt.datetime.fromisoformat(str(data.get("completed_at")).replace("Z", "+00:00"))
        r.require(completed >= started, "completed_at must be at or after started_at")
    except ValueError:
        r.errors.append("started_at and completed_at must be ISO-8601 timestamps")
    seen: set[str] = set()
    seen_paths: set[str] = set()
    for index, output in enumerate(data.get("outputs", [])):
        if isinstance(output, dict):
            asset_id = output.get("asset_id")
            if isinstance(asset_id, str):
                r.require(asset_id not in seen,
                          f"outputs[{index}] duplicates asset_id {asset_id}")
                seen.add(asset_id)
            path = output.get("path")
            if isinstance(path, str):
                r.require(path not in seen_paths, f"outputs[{index}] duplicates path {path}")
                seen_paths.add(path)
    return r


def validate_output_inspection(data: dict[str, Any]) -> Result:
    r = Result()
    approval = data.get("approval", {})
    check_ids: set[str] = set()
    for group in ("findings", "invariant_checks", "copy_checks", "technical_checks", "rights_checks"):
        for index, check in enumerate(data.get(group, [])):
            if isinstance(check, dict) and isinstance(check.get("id"), str):
                r.require(check["id"] not in check_ids,
                          f"{group}[{index}] duplicates check id {check['id']}")
                check_ids.add(check["id"])
    if data.get("decision") == "approved":
        for group in ("invariant_checks", "technical_checks", "rights_checks"):
            r.require(bool(data.get(group)), f"approved inspection requires {group}")
        for key in ("approved_by", "approved_at", "approval_basis"):
            r.require(nonempty(approval.get(key)),
                      f"approved inspection requires approval.{key}")
        for group in ("invariant_checks", "copy_checks", "technical_checks", "rights_checks"):
            failed = [item for item in data.get(group, [])
                      if isinstance(item, dict) and item.get("status") in {"fail", "unknown"}]
            r.require(not failed, f"approved inspection has unresolved {group}")
        try:
            inspected_at = dt.datetime.fromisoformat(
                str(data.get("inspected_at")).replace("Z", "+00:00")
            )
            approved_at = dt.datetime.fromisoformat(
                str(approval.get("approved_at")).replace("Z", "+00:00")
            )
            r.require(approved_at >= inspected_at,
                      "approval.approved_at must be at or after inspected_at")
        except ValueError:
            r.errors.append("inspected_at and approval.approved_at must be ISO-8601 timestamps")
    return r


def validate_revision_lineage(data: dict[str, Any]) -> Result:
    r = Result()
    if data.get("decision") != "draft":
        for key in ("new_job_ref", "new_receipt_ref", "new_output_ref",
                    "observed_result", "comparison"):
            r.require(nonempty(data.get(key)), f"completed revision requires {key}")
    r.warn(len(data.get("integration_changes", [])) <= 3,
           "revision has many integration changes; verify that one primary variable remains isolated")
    return r


def validate_evaluation_v2(data: dict[str, Any]) -> Result:
    r = Result()
    seen: set[str] = set()
    total_weight = 0.0
    for index, dimension in enumerate(data.get("dimensions", [])):
        if not isinstance(dimension, dict):
            continue
        dimension_id = dimension.get("id")
        if isinstance(dimension_id, str):
            r.require(dimension_id not in seen, f"duplicate dimension id: {dimension_id}")
            seen.add(dimension_id)
        weight = dimension.get("weight")
        if isinstance(weight, (int, float)) and not isinstance(weight, bool):
            total_weight += float(weight)
        refs = dimension.get("evidence_refs", [])
        if dimension.get("evidence_state") == "UNVERIFIED":
            r.require(not refs, f"dimensions[{index}] UNVERIFIED evidence must not cite refs")
        else:
            r.require(bool(refs), f"dimensions[{index}] evidence_refs must not be empty")
    r.warn(math.isclose(total_weight, 100.0, rel_tol=0, abs_tol=0.001),
           f"dimension weights sum to {total_weight:g}, not 100")
    return r


def validate_delivery_v2(data: dict[str, Any]) -> Result:
    r = Result()
    asset_ids = [item.get("asset_id") for item in data.get("files", []) if isinstance(item, dict)]
    r.require(len(asset_ids) == len(set(asset_ids)), "delivery files must not duplicate asset_id")
    if data.get("status") == "delivered":
        r.require(bool(data.get("files")), "delivered manifest requires files")
        for key in ("job_refs", "receipt_refs", "inspection_refs"):
            r.require(bool(data.get(key)), f"delivered manifest requires {key}")
        for index, item in enumerate(data.get("files", [])):
            if isinstance(item, dict):
                r.require(item.get("rights_status") in {"CLEARED", "LIMITED"},
                          f"files[{index}] has unresolved rights")
    return r


def _no_semantic_validation(data: dict[str, Any]) -> Result:
    del data
    return Result()


def _call_semantic_validator(
    schema_version: str, data: dict[str, Any], context: ValidationContext
) -> Result:
    simple: dict[str, Callable[[dict[str, Any]], Result]] = {
        "creative-craft.brief.v1": validate_brief,
        "creative-craft.asset-ledger.v1": validate_asset_ledger,
        "creative-craft.concept-routes.v1": validate_concept_routes,
        "creative-craft.critique.v1": validate_critique,
        "creative-craft.evaluation.v1": validate_evaluation,
        "creative-craft.delivery.v1": validate_delivery,
        "creative-craft.project-manifest.v1": validate_project_manifest,
        "creative-craft.creative-direction.v1": validate_creative_direction,
        "creative-craft.output-inspection.v1": validate_output_inspection,
        "creative-craft.revision-lineage.v1": validate_revision_lineage,
        "creative-craft.evaluation.v2": validate_evaluation_v2,
        "creative-craft.delivery.v2": validate_delivery_v2,
    }
    if schema_version in {"creative-craft.image-job.v1", "creative-craft.image-job.v2"}:
        return validate_image_job(data, context)
    if schema_version in {"creative-craft.video-job.v1", "creative-craft.video-job.v2"}:
        return validate_video_job(data, context)
    if schema_version == "creative-craft.execution-receipt.v1":
        return validate_execution_receipt(data, context)
    return simple.get(schema_version, _no_semantic_validation)(data)


SCHEMA_TO_KIND = {
    schema_version: entry["kind"] for schema_version, entry in ARTIFACT_REGISTRY.items()
}


def validate_data(
    data: dict[str, Any], kind: str = "auto", context: ValidationContext | None = None
) -> tuple[str, Result]:
    context = context or ValidationContext()
    schema_version = str(data.get("schema_version"))
    entry = ARTIFACT_REGISTRY.get(schema_version)
    if entry is None:
        return "unknown", Result(errors=[
            f"cannot infer kind from schema_version {data.get('schema_version')!r}"
        ])
    resolved = str(entry["kind"])
    if kind != "auto" and kind != resolved:
        return resolved, Result(errors=[
            f"artifact kind {resolved!r} does not match requested kind {kind!r}"
        ])
    structural = validate_against_schema(data, context.schemas_dir / str(entry["schema"]))
    if not structural.ok:
        return resolved, structural
    structural.extend(_call_semantic_validator(schema_version, data, context))
    return resolved, structural


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


ARTIFACT_ID_FIELDS = {
    "brief": "brief_id",
    "concept-routes": None,
    "creative-direction": "direction_id",
    "image": "job_id",
    "video": "job_id",
    "execution-receipt": "receipt_id",
    "output-inspection": "inspection_id",
    "revision-lineage": "revision_id",
    "evaluation": "evaluation_id",
    "delivery": "delivery_id",
    "project-manifest": "manifest_id",
    "critique": "critique_id",
    "asset-ledger": None,
}


@dataclass
class ProjectGraph:
    root: Path
    manifest_path: Path
    manifest: dict[str, Any]
    records: dict[tuple[str, str], dict[str, Any]] = field(default_factory=dict)
    result: Result = field(default_factory=Result)
    job_statuses: dict[str, str] = field(default_factory=dict)

    def record(self, artifact_type: str, artifact_id: str) -> dict[str, Any] | None:
        return self.records.get((artifact_type, artifact_id))


def _project_manifest_path(root: Path) -> Path:
    nested = root / ".creative-craft" / "project-manifest.json"
    direct = root / "project-manifest.json"
    if nested.is_file():
        return nested
    return direct


def _safe_project_path(root: Path, value: Any) -> tuple[Path | None, str | None]:
    if not isinstance(value, str) or not value:
        return None, "path must be a non-empty string"
    relative = Path(value)
    if relative.is_absolute() or ".." in relative.parts:
        return None, f"unsafe project-relative path: {value!r}"
    candidate = root / relative
    try:
        resolved = candidate.resolve(strict=False)
        resolved.relative_to(root.resolve())
    except (OSError, ValueError):
        return None, f"path escapes project root: {value!r}"
    if candidate.is_symlink():
        return None, f"artifact path must not be a symlink: {value!r}"
    return candidate, None


def _json_pointer(value: Any, pointer: str) -> tuple[bool, Any]:
    if pointer in {"", "/"}:
        return True, value
    if not pointer.startswith("/"):
        return False, None
    current = value
    for raw_part in pointer[1:].split("/"):
        part = raw_part.replace("~1", "/").replace("~0", "~")
        if isinstance(current, dict) and part in current:
            current = current[part]
        elif isinstance(current, list) and part.isdigit() and int(part) < len(current):
            current = current[int(part)]
        else:
            return False, None
    return True, current


CC_REF_PATTERN = re.compile(r"^cc://([a-z0-9-]+)/([^#]+)#(.*)$")


def resolve_evidence_ref(graph: ProjectGraph, reference: Any) -> tuple[bool, Any, str]:
    if not isinstance(reference, str):
        return False, None, "reference must be a string"
    match = CC_REF_PATTERN.fullmatch(reference)
    if not match:
        return False, None, f"invalid Creative Craft reference: {reference!r}"
    artifact_type, artifact_id, pointer = match.groups()
    record = graph.record(artifact_type, artifact_id)
    if record is None:
        return False, None, f"reference target does not exist: {reference!r}"
    found, value = _json_pointer(record["data"], pointer)
    if not found:
        return False, None, f"reference JSON pointer does not exist: {reference!r}"
    return True, value, ""


def _require_record(
    graph: ProjectGraph, artifact_type: str, artifact_id: Any, message: str
) -> dict[str, Any] | None:
    record = graph.record(artifact_type, str(artifact_id))
    graph.result.require(record is not None, message)
    return record


def _project_cross_checks(graph: ProjectGraph) -> None:
    assets: dict[str, dict[str, Any]] = {}
    for (artifact_type, _), record in graph.records.items():
        if artifact_type == "asset-ledger":
            for asset in record["data"].get("assets", []):
                if isinstance(asset, dict) and isinstance(asset.get("asset_id"), str):
                    asset_id = asset["asset_id"]
                    graph.result.require(asset_id not in assets,
                                         f"duplicate asset_id across ledgers: {asset_id}")
                    assets[asset_id] = asset

    routes_by_brief: dict[str, dict[str, dict[str, Any]]] = {}
    for (artifact_type, _), record in graph.records.items():
        data = record["data"]
        if artifact_type == "asset-ledger":
            graph.result.require(data.get("project_id") == graph.manifest.get("project_id"),
                                 "asset ledger project_id differs from project manifest")
        if artifact_type == "concept-routes":
            brief_id = data.get("brief_id")
            _require_record(graph, "brief", brief_id,
                            f"concept routes references missing brief_id {brief_id!r}")
            route_map = routes_by_brief.setdefault(str(brief_id), {})
            for route in data.get("routes", []):
                if isinstance(route, dict) and isinstance(route.get("route_id"), str):
                    graph.result.require(route["route_id"] not in route_map,
                                         f"duplicate route_id across route artifacts: {route['route_id']}")
                    route_map[route["route_id"]] = route

    for (artifact_type, artifact_id), record in graph.records.items():
        data = record["data"]
        if artifact_type == "creative-direction":
            brief_id = data.get("brief_id")
            route_id = data.get("selected_route_id")
            _require_record(graph, "brief", brief_id,
                            f"direction {artifact_id} references missing brief_id {brief_id!r}")
            graph.result.require(route_id in routes_by_brief.get(str(brief_id), {}),
                                 f"direction {artifact_id} selected_route_id does not belong to its brief")
            selected_route = routes_by_brief.get(str(brief_id), {}).get(str(route_id))
            if selected_route:
                graph.result.require(
                    selected_route.get("decision") in {"SELECT", "SELECT_FOR_TEST"},
                    f"direction {artifact_id} selected route is not selected for production",
                )
            for ref in data.get("reference_roles", []):
                if isinstance(ref, dict):
                    graph.result.require(ref.get("asset_id") in assets,
                                         f"direction {artifact_id} references unknown asset {ref.get('asset_id')!r}")

        if artifact_type in {"image", "video"} and data.get("schema_version", "").endswith(".v2"):
            brief_id = data.get("brief_id")
            direction = _require_record(
                graph, "creative-direction", data.get("direction_id"),
                f"job {artifact_id} references missing direction_id {data.get('direction_id')!r}",
            )
            brief = _require_record(graph, "brief", brief_id,
                                    f"job {artifact_id} references missing brief_id {brief_id!r}")
            if direction:
                graph.result.require(direction["data"].get("brief_id") == brief_id,
                                     f"job {artifact_id} brief_id differs from direction")
                graph.result.require(
                    direction["data"].get("selected_route_id") == data.get("selected_route_id"),
                    f"job {artifact_id} selected_route_id differs from direction",
                )
            referenced_assets = set(data.get("asset_refs", []))
            if artifact_type == "image":
                referenced_assets.update(
                    ref.get("asset_id") for ref in data.get("prompt", {}).get("references", [])
                    if isinstance(ref, dict)
                )
            else:
                referenced_assets.update(
                    ref.get("asset_id") for ref in data.get("references", [])
                    if isinstance(ref, dict)
                )
            for asset_id_ref in referenced_assets:
                graph.result.require(asset_id_ref in assets,
                                     f"job {artifact_id} references unknown asset {asset_id_ref!r}")
            if data.get("declared_status") == "ready":
                graph.result.require(bool(brief and brief["data"].get("status") == "locked"),
                                     f"ready job {artifact_id} requires a locked brief")
                graph.result.require(
                    bool(direction and direction["data"].get("status") in {"locked", "approved"}),
                    f"ready job {artifact_id} requires a locked or approved direction",
                )
                graph.result.require(data.get("rights", {}).get("status") in {"CLEARED", "LIMITED"},
                                     f"ready job {artifact_id} has unresolved rights")
                for asset_id_ref in referenced_assets:
                    asset = assets.get(str(asset_id_ref), {})
                    graph.result.require(asset.get("rights_status") in {"CLEARED", "LIMITED"},
                                         f"ready job {artifact_id} asset {asset_id_ref!r} has unresolved rights")
                    graph.result.require(
                        asset.get("consent_status") in {"CLEARED", "LIMITED", "NOT_APPLICABLE"},
                        f"ready job {artifact_id} asset {asset_id_ref!r} has unresolved consent",
                    )

        if artifact_type == "execution-receipt":
            job = graph.record("image", str(data.get("job_id"))) or graph.record(
                "video", str(data.get("job_id"))
            )
            graph.result.require(job is not None,
                                 f"receipt {artifact_id} references missing job_id {data.get('job_id')!r}")
            if job:
                graph.result.require(job["data"].get("schema_version") in {
                    "creative-craft.image-job.v2", "creative-craft.video-job.v2"
                }, f"receipt {artifact_id} requires a v2 job")
                graph.result.require(data.get("job_sha256") == job["sha256"],
                                     f"receipt {artifact_id} job_sha256 does not match job artifact")
                graph.result.require(data.get("provider_profile") == job["data"].get("provider_profile"),
                                     f"receipt {artifact_id} provider_profile differs from job")
                graph.result.require(data.get("execution_surface") == job["data"].get("execution_surface"),
                                     f"receipt {artifact_id} execution_surface differs from job")
            for output in data.get("outputs", []):
                if not isinstance(output, dict):
                    continue
                output_path, error = _safe_project_path(graph.root, output.get("path"))
                graph.result.require(error is None, f"receipt {artifact_id}: {error}")
                if output_path and output_path.is_file():
                    graph.result.require(sha256_file(output_path) == output.get("sha256"),
                                         f"receipt {artifact_id} output digest mismatch: {output.get('path')}")
                    graph.result.require(output_path.stat().st_size == output.get("bytes"),
                                         f"receipt {artifact_id} output byte size mismatch: {output.get('path')}")
                else:
                    graph.result.errors.append(
                        f"receipt {artifact_id} output file does not exist: {output.get('path')!r}"
                    )

        if artifact_type == "output-inspection":
            receipt = _require_record(
                graph, "execution-receipt", data.get("receipt_id"),
                f"inspection {artifact_id} references missing receipt_id {data.get('receipt_id')!r}",
            )
            if receipt:
                graph.result.require(receipt["data"].get("job_id") == data.get("job_id"),
                                     f"inspection {artifact_id} job_id differs from receipt")
                matching = [output for output in receipt["data"].get("outputs", [])
                            if isinstance(output, dict)
                            and output.get("asset_id") == data.get("output_asset_id")]
                graph.result.require(bool(matching),
                                     f"inspection {artifact_id} output_asset_id is absent from receipt")
                if matching:
                    graph.result.require(matching[0].get("sha256") == data.get("output_sha256"),
                                         f"inspection {artifact_id} output_sha256 differs from receipt")

        if artifact_type == "revision-lineage":
            for key in ("parent_output_ref", "parent_inspection_ref"):
                ok, _, message = resolve_evidence_ref(graph, data.get(key))
                graph.result.require(ok, f"revision {artifact_id}: {message}")
            for key in ("new_job_ref", "new_receipt_ref", "new_output_ref"):
                reference = data.get(key)
                if reference:
                    ok, _, message = resolve_evidence_ref(graph, reference)
                    graph.result.require(ok, f"revision {artifact_id}: {message}")

        if artifact_type == "evaluation" and data.get("schema_version") == "creative-craft.evaluation.v2":
            ok, _, message = resolve_evidence_ref(graph, data.get("target_ref"))
            graph.result.require(ok, f"evaluation {artifact_id}: {message}")
            _require_record(graph, "brief", data.get("brief_id"),
                            f"evaluation {artifact_id} references missing brief_id")
            for dimension in data.get("dimensions", []):
                if isinstance(dimension, dict):
                    for reference in dimension.get("evidence_refs", []):
                        ok, _, message = resolve_evidence_ref(graph, reference)
                        graph.result.require(ok, f"evaluation {artifact_id}: {message}")

        if artifact_type == "delivery" and data.get("schema_version") == "creative-craft.delivery.v2":
            graph.result.require(data.get("project_id") == graph.manifest.get("project_id"),
                                 f"delivery {artifact_id} project_id differs from manifest")
            direction = _require_record(
                graph, "creative-direction", data.get("direction_id"),
                f"delivery {artifact_id} references missing direction_id",
            )
            if direction:
                graph.result.require(direction["data"].get("brief_id") == data.get("brief_id"),
                                     f"delivery {artifact_id} brief_id differs from direction")
                graph.result.require(direction["data"].get("selected_route_id") == data.get("selected_route_id"),
                                     f"delivery {artifact_id} selected_route_id differs from direction")
            for ref_key in ("job_refs", "receipt_refs", "inspection_refs", "revision_refs", "evaluation_refs"):
                for reference in data.get(ref_key, []):
                    ok, _, message = resolve_evidence_ref(graph, reference)
                    graph.result.require(ok, f"delivery {artifact_id}: {message}")
            for index, item in enumerate(data.get("files", [])):
                if not isinstance(item, dict):
                    continue
                job = graph.record("image", str(item.get("job_id"))) or graph.record(
                    "video", str(item.get("job_id"))
                )
                receipt = graph.record("execution-receipt", str(item.get("receipt_id")))
                graph.result.require(job is not None,
                                     f"delivery {artifact_id} files[{index}] job does not exist")
                graph.result.require(receipt is not None,
                                     f"delivery {artifact_id} files[{index}] receipt does not exist")
                if job:
                    job_type = str(job["entry"].get("artifact_type"))
                    graph.result.require(
                        f"cc://{job_type}/{item.get('job_id')}#" in data.get("job_refs", []),
                        f"delivery {artifact_id} files[{index}] job is absent from job_refs",
                    )
                graph.result.require(
                    f"cc://execution-receipt/{item.get('receipt_id')}#" in data.get("receipt_refs", []),
                    f"delivery {artifact_id} files[{index}] receipt is absent from receipt_refs",
                )
                graph.result.require(
                    f"cc://output-inspection/{item.get('inspection_id')}#" in data.get("inspection_refs", []),
                    f"delivery {artifact_id} files[{index}] inspection is absent from inspection_refs",
                )
                if receipt:
                    graph.result.require(receipt["data"].get("job_id") == item.get("job_id"),
                                         f"delivery {artifact_id} files[{index}] receipt/job mismatch")
                    matching_output = next(
                        (output for output in receipt["data"].get("outputs", [])
                         if isinstance(output, dict) and output.get("asset_id") == item.get("asset_id")),
                        None,
                    )
                    graph.result.require(matching_output is not None,
                                         f"delivery {artifact_id} files[{index}] asset is absent from receipt")
                    if matching_output:
                        graph.result.require(matching_output.get("sha256") == item.get("sha256"),
                                             f"delivery {artifact_id} files[{index}] digest differs from receipt")
                output_path, error = _safe_project_path(graph.root, item.get("path"))
                graph.result.require(error is None, f"delivery {artifact_id}: {error}")
                if output_path and output_path.is_file():
                    graph.result.require(sha256_file(output_path) == item.get("sha256"),
                                         f"delivery {artifact_id} files[{index}] digest mismatch")
                    graph.result.require(output_path.stat().st_size == item.get("bytes"),
                                         f"delivery {artifact_id} files[{index}] byte size mismatch")
                elif data.get("status") == "delivered":
                    graph.result.errors.append(
                        f"delivery {artifact_id} file does not exist: {item.get('path')!r}"
                    )
                inspection = graph.record("output-inspection", str(item.get("inspection_id")))
                graph.result.require(inspection is not None,
                                     f"delivery {artifact_id} files[{index}] inspection does not exist")
                if inspection:
                    graph.result.require(inspection["data"].get("job_id") == item.get("job_id"),
                                         f"delivery {artifact_id} files[{index}] inspection/job mismatch")
                    graph.result.require(inspection["data"].get("receipt_id") == item.get("receipt_id"),
                                         f"delivery {artifact_id} files[{index}] inspection/receipt mismatch")
                    graph.result.require(inspection["data"].get("output_asset_id") == item.get("asset_id"),
                                         f"delivery {artifact_id} files[{index}] inspection/asset mismatch")
                    graph.result.require(inspection["data"].get("decision") == "approved",
                                         f"delivery {artifact_id} files[{index}] inspection is not approved")
                    graph.result.require(inspection["data"].get("output_sha256") == item.get("sha256"),
                                         f"delivery {artifact_id} files[{index}] digest differs from inspection")


def _project_job_statuses(graph: ProjectGraph) -> None:
    receipts_by_job: dict[str, list[dict[str, Any]]] = {}
    inspections_by_job: dict[str, list[dict[str, Any]]] = {}
    delivered_jobs: set[str] = set()
    for (artifact_type, _), record in graph.records.items():
        if artifact_type == "execution-receipt":
            receipts_by_job.setdefault(str(record["data"].get("job_id")), []).append(record)
        elif artifact_type == "output-inspection":
            inspections_by_job.setdefault(str(record["data"].get("job_id")), []).append(record)
        elif artifact_type == "delivery" and record["data"].get("status") == "delivered":
            delivered_jobs.update(
                str(item.get("job_id")) for item in record["data"].get("files", [])
                if isinstance(item, dict)
            )
    for (artifact_type, job_id), record in graph.records.items():
        if artifact_type not in {"image", "video"}:
            continue
        declared = record["data"].get("declared_status", record["data"].get("status", "draft"))
        status = str(declared)
        if status == "superseded":
            graph.job_statuses[job_id] = status
            continue
        successful_receipts = [receipt for receipt in receipts_by_job.get(job_id, [])
                               if receipt["data"].get("outcome") in {"succeeded", "partial"}
                               and receipt["data"].get("outputs")]
        if successful_receipts:
            status = "generated"
        inspections = inspections_by_job.get(job_id, [])
        if inspections:
            decisions = {item["data"].get("decision") for item in inspections}
            if "approved" in decisions:
                status = "approved"
            elif "needs_revision" in decisions:
                status = "revision_required"
            else:
                status = "inspected"
        if job_id in delivered_jobs:
            status = "delivered"
        graph.job_statuses[job_id] = status


def validate_project(root: Path, context: ValidationContext | None = None) -> ProjectGraph:
    root = root.resolve()
    context = context or ValidationContext()
    manifest_path = _project_manifest_path(root)
    try:
        manifest = load_json(manifest_path)
    except ValueError as exc:
        return ProjectGraph(root, manifest_path, {}, result=Result(errors=[str(exc)]))
    graph = ProjectGraph(root, manifest_path, manifest)
    _, manifest_result = validate_data(manifest, "project-manifest", context)
    graph.result.extend(manifest_result)
    if not manifest_result.ok:
        return graph
    for index, entry in enumerate(manifest.get("artifacts", [])):
        if not isinstance(entry, dict):
            continue
        artifact_path, error = _safe_project_path(root, entry.get("path"))
        if error:
            graph.result.errors.append(f"artifacts[{index}]: {error}")
            continue
        if artifact_path is None or not artifact_path.is_file():
            graph.result.errors.append(
                f"artifacts[{index}] file does not exist: {entry.get('path')!r}"
            )
            continue
        actual_sha = sha256_file(artifact_path)
        graph.result.require(actual_sha == entry.get("sha256"),
                             f"artifacts[{index}] sha256 mismatch: {entry.get('path')}")
        try:
            data = load_json(artifact_path)
        except ValueError as exc:
            graph.result.errors.append(str(exc))
            continue
        schema_version = str(data.get("schema_version"))
        graph.result.require(schema_version == entry.get("schema_version"),
                             f"artifacts[{index}] schema_version differs from file")
        registry_entry = ARTIFACT_REGISTRY.get(schema_version)
        if registry_entry is None:
            graph.result.errors.append(f"artifacts[{index}] has unsupported schema_version")
            continue
        expected_type = str(registry_entry["kind"])
        graph.result.require(entry.get("artifact_type") == expected_type,
                             f"artifacts[{index}] artifact_type must be {expected_type!r}")
        _, artifact_result = validate_data(data, expected_type, context)
        graph.result.errors.extend(
            f"{entry.get('path')}: {message}" for message in artifact_result.errors
        )
        graph.result.warnings.extend(
            f"{entry.get('path')}: {message}" for message in artifact_result.warnings
        )
        artifact_id = str(entry.get("artifact_id"))
        id_field = ARTIFACT_ID_FIELDS.get(expected_type)
        if id_field:
            graph.result.require(data.get(id_field) == artifact_id,
                                 f"artifacts[{index}] artifact_id differs from file {id_field}")
        key = (expected_type, artifact_id)
        graph.result.require(key not in graph.records,
                             f"artifacts[{index}] duplicates artifact identity {key}")
        graph.records[key] = {
            "data": data,
            "path": artifact_path,
            "sha256": actual_sha,
            "entry": entry,
        }
    _project_cross_checks(graph)
    _project_job_statuses(graph)
    return graph


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
    declared_status = data.get("declared_status", data.get("status", "unknown"))
    out: list[str] = [
        f"# Image execution pack — {data['job_id']}",
        "",
        f"- Provider profile: `{data['provider_profile']}`",
        f"- Execution surface: `{data.get('execution_surface', 'legacy-unspecified')}`",
        f"- Task: `{data['task_type']}`",
        f"- Execution mode: `{data['execution_mode']}`",
        f"- Declared status: `{declared_status}`",
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
        (
            f"Create {canvas['variants']} output variant(s) at {canvas['size']}, "
            f"{canvas['quality']} quality, {canvas['format']} format, "
            f"{canvas['background']} background."
        )
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
        (
            f"This pack was compiled from declared status `{declared_status}`; compilation is not "
            "evidence that an image was generated or approved."
        ),
    ])
    return "\n".join(out).rstrip() + "\n"


def compile_video_markdown(data: dict[str, Any]) -> str:
    fmt = data["format"]
    declared_status = data.get("declared_status", data.get("status", "unknown"))
    out: list[str] = [
        f"# Video execution pack — {data['job_id']}",
        "",
        f"- Provider profile: `{data['provider_profile']}`",
        f"- Execution surface: `{data.get('execution_surface', 'legacy-unspecified')}`",
        f"- Task: `{data['task_type']}`",
        f"- Execution mode: `{data['execution_mode']}`",
        f"- Declared status: `{declared_status}`",
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
        (
            f"{data['duration_seconds']}-second audiovisual video, "
            f"{fmt['aspect_ratio']}, {fmt['resolution_target']}, language {fmt['language']}."
        )
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
        f"- Voice: {audio.get('voice') or '(none)'}",
        f"- Ambience: {audio.get('ambience') or '(none)'}",
    ])
    audio_lines.extend(f"- Effect: {x}" for x in audio.get("effects", []))
    audio_lines.append(f"- Music: {audio.get('music') or '(none)'}")
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
        (
            f"This pack was compiled from declared status `{declared_status}`; compilation is not "
            "evidence that a video was generated or approved."
        ),
    ])
    return "\n".join(out).rstrip() + "\n"


def _score_evaluation_v1(data: dict[str, Any]) -> dict[str, Any]:
    _, validation = validate_data(data, "evaluation")
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


EVIDENCE_STRENGTH = {
    "OBSERVED": 1.0,
    "SPECIFIED": 0.9,
    "INFERRED": 0.7,
    "HYPOTHESIZED": 0.4,
    "UNVERIFIED": 0.0,
}


def _evaluation_gates(data: dict[str, Any], graph: ProjectGraph) -> dict[str, bool]:
    brief = graph.record("brief", str(data.get("brief_id")))
    brief_locked = bool(brief and brief["data"].get("status") == "locked")
    target_ok, target, _ = resolve_evidence_ref(graph, data.get("target_ref"))
    deliverable_specified = bool(brief and brief["data"].get("deliverables"))
    if target_ok and isinstance(target, dict):
        if target.get("schema_version") == "creative-craft.creative-direction.v1":
            deliverable_specified = bool(target.get("deliverables"))
        elif target.get("schema_version") == "creative-craft.delivery.v2":
            deliverable_specified = bool(target.get("files") or target.get("validation"))

    relevant_asset_ids: set[str] = set()
    relevant_job_rights: list[str] = []
    if target_ok and isinstance(target, dict):
        for ref in target.get("reference_roles", []):
            if isinstance(ref, dict) and isinstance(ref.get("asset_id"), str):
                relevant_asset_ids.add(ref["asset_id"])
    for (artifact_type, _), record in graph.records.items():
        if artifact_type in {"image", "video"} and record["data"].get("brief_id") == data.get("brief_id"):
            relevant_job_rights.append(str(record["data"].get("rights", {}).get("status")))
            relevant_asset_ids.update(
                str(asset_id) for asset_id in record["data"].get("asset_refs", [])
            )
    rights_values: list[str] = list(relevant_job_rights)
    consent_values: list[str] = []
    for (artifact_type, _), record in graph.records.items():
        if artifact_type != "asset-ledger":
            continue
        for asset in record["data"].get("assets", []):
            if isinstance(asset, dict) and asset.get("asset_id") in relevant_asset_ids:
                rights_values.append(str(asset.get("rights_status")))
                consent_values.append(str(asset.get("consent_status")))
    rights_clear = bool(rights_values) and all(
        value in {"CLEARED", "LIMITED"} for value in rights_values
    ) and all(value in {"CLEARED", "LIMITED", "NOT_APPLICABLE"}
              for value in consent_values)

    actual_output_observed = False
    if target_ok and isinstance(target, dict):
        schema_version = target.get("schema_version")
        if schema_version == "creative-craft.output-inspection.v1":
            actual_output_observed = True
        elif schema_version == "creative-craft.delivery.v2":
            actual_output_observed = bool(target.get("inspection_refs"))
    if data.get("stage") in {"output", "delivery"} and not actual_output_observed:
        actual_output_observed = any(
            artifact_type == "output-inspection"
            for artifact_type, _ in graph.records
        )
    return {
        "rights_clear": rights_clear,
        "brief_locked": brief_locked,
        "deliverable_specified": deliverable_specified,
        "actual_output_observed": actual_output_observed,
    }


def _score_evaluation_v2(data: dict[str, Any], graph: ProjectGraph | None) -> dict[str, Any]:
    context = ValidationContext()
    _, validation = validate_data(data, "evaluation", context)
    if not validation.ok:
        return {
            "status": "invalid",
            "errors": validation.errors,
            "warnings": validation.warnings,
        }
    if graph is None:
        return {
            "status": "blocked",
            "score": None,
            "gate_status": {"project_evidence_bound": False},
            "failed_gates": ["project_evidence_bound"],
            "coverage": 0.0,
            "evidence_strength": 0.0,
            "evidence_distribution": {},
            "confidence": "INSUFFICIENT",
            "uncertainty": ["Evaluation v2 requires --root and a valid project manifest."],
            "warnings": validation.warnings,
        }
    if not graph.result.ok:
        return {
            "status": "invalid",
            "errors": graph.result.errors,
            "warnings": graph.result.warnings,
        }

    gates = _evaluation_gates(data, graph)
    required_gates = ["rights_clear", "brief_locked", "deliverable_specified"]
    if data["stage"] in {"output", "delivery"}:
        required_gates.append("actual_output_observed")
    failed_gates = [name for name in required_gates if not gates[name]]
    dimensions = data["dimensions"]
    total_weight = sum(float(item["weight"]) for item in dimensions)
    covered = [item for item in dimensions
               if item["evidence_state"] != "UNVERIFIED" and item["evidence_refs"]]
    covered_weight = sum(float(item["weight"]) for item in covered)
    coverage = 100.0 * covered_weight / total_weight if total_weight else 0.0
    distribution = {
        state: round(100.0 * sum(float(item["weight"]) for item in dimensions
                                 if item["evidence_state"] == state) / total_weight, 2)
        if total_weight else 0.0
        for state in EVIDENCE_STRENGTH
    }
    strength = 100.0 * sum(
        float(item["weight"]) * EVIDENCE_STRENGTH[item["evidence_state"]]
        for item in dimensions
    ) / total_weight if total_weight else 0.0
    strong_weight = distribution["OBSERVED"] + distribution["SPECIFIED"]
    hypothesized_weight = distribution["HYPOTHESIZED"]
    if not failed_gates and coverage == 100.0 and strong_weight >= 80.0 and hypothesized_weight == 0:
        confidence = "STRONG"
    elif not failed_gates and coverage >= 90.0 and hypothesized_weight <= 20.0:
        confidence = "MIXED"
    elif not failed_gates and coverage >= 80.0:
        confidence = "WEAK"
    else:
        confidence = "INSUFFICIENT"
    score = None
    if coverage >= 80.0 and not failed_gates:
        score = 100.0 * sum(
            (float(item["score"]) / 5.0) * float(item["weight"])
            for item in covered
        ) / covered_weight if covered_weight else None
    uncertainty = list(data.get("remaining_unknowns", []))
    uncertainty.extend(
        f"{item['id']} is {item['evidence_state']}"
        for item in dimensions
        if item["evidence_state"] in {"HYPOTHESIZED", "UNVERIFIED"}
    )
    if failed_gates:
        status = "blocked"
    elif coverage < 80.0:
        status = "withheld"
    else:
        status = "scored"
    return {
        "status": status,
        "score": round(score, 2) if score is not None else None,
        "gate_status": gates,
        "failed_gates": failed_gates,
        "coverage": round(coverage, 2),
        "evidence_strength": round(strength, 2),
        "evidence_distribution": distribution,
        "confidence": confidence,
        "uncertainty": uncertainty,
        "stage": data["stage"],
        "recommendation": data["recommendation"],
        "warnings": validation.warnings,
    }


def score_evaluation(
    data: dict[str, Any], graph: ProjectGraph | None = None
) -> dict[str, Any]:
    if data.get("schema_version") == "creative-craft.evaluation.v2":
        return _score_evaluation_v2(data, graph)
    return _score_evaluation_v1(data)


def markdown_local_links(path: Path) -> Iterable[tuple[str, Path]]:
    text = path.read_text(encoding="utf-8")
    for target in re.findall(r"\]\(([^)]+)\)", text):
        target = target.split("#", 1)[0].strip()
        if not target or re.match(r"^[a-zA-Z][a-zA-Z0-9+.-]*:", target):
            continue
        yield target, (path.parent / target).resolve()


def validate_skill_runtime(skill_root: Path) -> Result:
    """Validate the canonical Skill without requiring repository-only files."""
    r = Result()
    context = ValidationContext(skill_root)
    required = [
        "SKILL.md",
        "VERSION",
        "providers/openai-gpt-image-2.json",
        "providers/bytedance-seedance-2.5.json",
        "providers/surfaces/openai-image-api.json",
        "providers/surfaces/bytedance-jimeng-web.json",
        "scripts/creative_craft.py",
    ]
    for rel in required:
        r.require((skill_root / rel).is_file(), f"skill runtime missing required file: {rel}")

    for schema_version, entry in ARTIFACT_REGISTRY.items():
        r.require(
            (context.schemas_dir / str(entry["schema"])).is_file(),
            f"missing schema for {schema_version}: {entry['schema']}",
        )
        template = entry.get("template")
        if template:
            r.require(
                (skill_root / "templates" / str(template)).is_file(),
                f"missing template for {schema_version}: {template}",
            )
    for schema_version, filename in METADATA_SCHEMAS.items():
        r.require(
            (context.schemas_dir / filename).is_file(),
            f"missing metadata schema for {schema_version}: {filename}",
        )

    try:
        profiles = provider_profiles(context.providers_dir)
        surfaces = surface_profiles(context.surfaces_dir)
    except ValueError as exc:
        r.errors.append(str(exc))
        profiles = {}
        surfaces = {}
    r.require(IMAGE_PROFILE_ID in profiles, f"missing provider profile {IMAGE_PROFILE_ID}")
    r.require(VIDEO_PROFILE_ID in profiles, f"missing provider profile {VIDEO_PROFILE_ID}")
    for profile_id, profile in profiles.items():
        metadata_result = validate_against_schema(
            profile, context.schemas_dir / METADATA_SCHEMAS["creative-craft.provider.v1"]
        )
        r.errors.extend(f"provider {profile_id}: {message}" for message in metadata_result.errors)
    for surface_id, surface in surfaces.items():
        metadata_result = validate_against_schema(
            surface, context.schemas_dir / METADATA_SCHEMAS["creative-craft.surface.v1"]
        )
        r.errors.extend(f"surface {surface_id}: {message}" for message in metadata_result.errors)
        for profile_id in surface.get("provider_profiles", []):
            r.require(
                profile_id in profiles,
                f"surface {surface_id} references unknown provider_profile {profile_id}",
            )
    return r


def is_repository_checkout(root: Path) -> bool:
    sentinels = [
        "package.json",
        ".codex-plugin/plugin.json",
        "sources.lock.json",
        "skills/creative-craft/SKILL.md",
    ]
    return all((root / rel).is_file() for rel in sentinels)


def doctor(root: Path = REPO_ROOT) -> Result:
    r = Result()
    skill_root = root / "skills" / "creative-craft"
    context = ValidationContext(skill_root)
    required = [
        "README.md",
        "README.zh-CN.md",
        "LICENSE",
        "VERSION",
        "package.json",
        ".codex-plugin/plugin.json",
        "sources.lock.json",
    ]
    for rel in required:
        r.require((root / rel).is_file(), f"missing required file: {rel}")
    r.extend(validate_skill_runtime(skill_root))

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

    source_lock = root / "sources.lock.json"
    if source_lock.is_file():
        source_data = load_json(source_lock)
        metadata_result = validate_against_schema(
            source_data, context.schemas_dir / METADATA_SCHEMAS["creative-craft.sources.v1"]
        )
        r.errors.extend(f"sources.lock.json: {message}" for message in metadata_result.errors)
        source_ids: set[str] = set()
        for source in source_data.get("sources", []):
            if isinstance(source, dict) and isinstance(source.get("id"), str):
                r.require(source["id"] not in source_ids,
                          f"sources.lock.json has duplicate source id {source['id']}")
                source_ids.add(source["id"])

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
    """Run repository or installed-runtime smoke tests without network access."""
    requested_root = Path(args.root).resolve() if args.root else None
    repository_scope = requested_root is not None or is_repository_checkout(REPO_ROOT)
    if repository_scope:
        root = requested_root or REPO_ROOT
        skill_root = root / "skills" / "creative-craft"
        preflight = doctor(root)
        runtime_valid = validate_skill_runtime(skill_root).ok
        label = "package self-test"
    else:
        root = SKILL_ROOT
        skill_root = SKILL_ROOT
        preflight = validate_skill_runtime(skill_root)
        runtime_valid = preflight.ok
        label = "installed runtime self-test"
    context = ValidationContext(skill_root)
    checks: list[dict[str, Any]] = []
    errors = list(preflight.errors)
    warnings = list(preflight.warnings)

    templates_dir = skill_root / "templates"
    for path in sorted(templates_dir.glob("*.json")):
        try:
            data = load_json(path)
        except ValueError as exc:
            errors.append(str(exc))
            checks.append({"file": str(path), "kind": "unknown", "valid": False})
            continue
        kind, result = validate_data(data, "auto", context)
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
    except (KeyError, OSError, TypeError, ValueError) as exc:
        errors.append(f"package smoke path failed: {exc}")

    payload = {
        "valid": not errors,
        "scope": "repository" if repository_scope else "runtime",
        "root": str(root),
        "repository_valid": preflight.ok if repository_scope else None,
        "runtime_valid": runtime_valid,
        "artifact_checks": checks,
        "errors": errors,
        "warnings": warnings,
    }
    if args.json:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        print(f"PASS {label}" if not errors else f"FAIL {label}")
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
    _, result = validate_data(data, "image")
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
    _, result = validate_data(data, "video")
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
    graph = validate_project(Path(args.root)) if args.root else None
    result = score_evaluation(data, graph)
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
    digest = sha256_file(path)
    if args.json:
        print(json.dumps({
            "file": str(path),
            "bytes": path.stat().st_size,
            "sha256": digest,
        }, indent=2))
    else:
        print(digest)
    return 0


def cmd_seed(args: argparse.Namespace) -> int:
    target = Path(args.target).expanduser().resolve()
    target.mkdir(parents=True, exist_ok=True)
    copies: dict[Path, Path] = {
        TEMPLATES_DIR / "BRAND.md": target / "BRAND.md",
        TEMPLATES_DIR / "CREATIVE.md": target / "CREATIVE.md",
        TEMPLATES_DIR / "DELIVERABLES.md": target / "DELIVERABLES.md",
    }
    for entry in ARTIFACT_REGISTRY.values():
        template = entry.get("template")
        if template and not entry.get("legacy"):
            copies[TEMPLATES_DIR / str(template)] = target / ".creative-craft" / str(template)
    conflicts = [dst for dst in copies.values() if dst.exists() and not args.force]
    if conflicts:
        print("ERROR: refusing to overwrite existing files:", file=sys.stderr)
        for path in conflicts:
            print(f"  {path}", file=sys.stderr)
        print("Use --force only after reviewing the existing authority.", file=sys.stderr)
        return 1
    backup_suffix = dt.datetime.now(dt.timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    for src, dst in copies.items():
        dst.parent.mkdir(parents=True, exist_ok=True)
        if dst.exists() and args.force:
            backup = dst.with_name(f"{dst.name}.bak.{backup_suffix}")
            shutil.copy2(dst, backup)
            print(backup)
        shutil.copy2(src, dst)
        print(dst)
    manifest_entries: list[dict[str, Any]] = []
    seed_types = {
        "brief", "asset-ledger", "concept-routes", "creative-direction",
        "image", "video", "evaluation", "delivery",
    }
    fallback_ids = {
        "asset-ledger": "asset-ledger-tbd",
        "concept-routes": "routes-tbd",
    }
    for schema_version, entry in ARTIFACT_REGISTRY.items():
        template = entry.get("template")
        artifact_type = str(entry["kind"])
        if not template or artifact_type not in seed_types or entry.get("legacy"):
            continue
        path = target / ".creative-craft" / str(template)
        data = load_json(path)
        id_field = ARTIFACT_ID_FIELDS.get(artifact_type)
        artifact_id = str(data.get(id_field)) if id_field else fallback_ids[artifact_type]
        manifest_entries.append({
            "artifact_type": artifact_type,
            "artifact_id": artifact_id,
            "schema_version": schema_version,
            "path": str(path.relative_to(target)),
            "sha256": sha256_file(path),
        })
    manifest_path = target / ".creative-craft" / "project-manifest.json"
    manifest = {
        "schema_version": "creative-craft.project-manifest.v1",
        "project_id": "project-tbd",
        "manifest_id": "manifest-tbd",
        "artifacts": manifest_entries,
    }
    write_atomic(manifest_path, json.dumps(manifest, ensure_ascii=False, indent=2) + "\n")
    return 0


def _write_json_artifact(path: Path, data: dict[str, Any], force: bool) -> None:
    if path.exists() and not force:
        raise ValueError(f"refusing to overwrite existing file: {path}; use --force after review")
    if path.exists():
        suffix = dt.datetime.now(dt.timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
        backup = path.with_name(f"{path.name}.bak.{suffix}")
        shutil.copy2(path, backup)
        print(f"Backup: {backup}")
    write_atomic(path, json.dumps(data, ensure_ascii=False, indent=2) + "\n")


def _project_payload(graph: ProjectGraph) -> dict[str, Any]:
    counts: dict[str, int] = {}
    for artifact_type, _ in graph.records:
        counts[artifact_type] = counts.get(artifact_type, 0) + 1
    return {
        "root": str(graph.root),
        "manifest": str(graph.manifest_path),
        "project_id": graph.manifest.get("project_id"),
        "valid": graph.result.ok,
        "artifact_counts": counts,
        "job_statuses": graph.job_statuses,
        "errors": graph.result.errors,
        "warnings": graph.result.warnings,
    }


def cmd_validate_project(args: argparse.Namespace) -> int:
    graph = validate_project(Path(args.root))
    payload = _project_payload(graph)
    if args.json:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        print(f"{'PASS' if graph.result.ok else 'FAIL'} project: {graph.root}")
        print(f"  Manifest: {graph.manifest_path}")
        print(f"  Artifacts: {sum(payload['artifact_counts'].values())}")
        for job_id, status in sorted(graph.job_statuses.items()):
            print(f"  Job {job_id}: {status}")
        for message in graph.result.errors:
            print(f"  ERROR: {message}")
        for message in graph.result.warnings:
            print(f"  WARN:  {message}")
    return 0 if graph.result.ok else 1


def cmd_project_status(args: argparse.Namespace) -> int:
    graph = validate_project(Path(args.root))
    payload = _project_payload(graph)
    payload["status"] = "valid" if graph.result.ok else "invalid"
    if args.json:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        print(f"Project status: {payload['status']}")
        print(f"Project ID: {payload['project_id']}")
        for artifact_type, count in sorted(payload["artifact_counts"].items()):
            print(f"  {artifact_type}: {count}")
        for job_id, status in sorted(graph.job_statuses.items()):
            print(f"  {job_id}: {status}")
        for message in graph.result.errors:
            print(f"ERROR: {message}")
    return 0 if graph.result.ok else 1


def cmd_inspect_output(args: argparse.Namespace) -> int:
    job_path = Path(args.job).resolve()
    receipt_path = Path(args.receipt).resolve()
    file_path = Path(args.file).resolve()
    output_path = Path(args.output).resolve()
    try:
        job = load_json(job_path)
        receipt = load_json(receipt_path)
        _, job_result = validate_data(job, "auto")
        _, receipt_result = validate_data(receipt, "execution-receipt")
        if not job_result.ok or not receipt_result.ok:
            raise ValueError("job or receipt is structurally invalid")
        if receipt.get("job_id") != job.get("job_id"):
            raise ValueError("receipt.job_id does not match job.job_id")
        if receipt.get("job_sha256") != sha256_file(job_path):
            raise ValueError("receipt.job_sha256 does not match the job file")
        if not file_path.is_file():
            raise ValueError(f"output file not found: {file_path}")
        digest = sha256_file(file_path)
        matches = [item for item in receipt.get("outputs", [])
                   if isinstance(item, dict) and item.get("sha256") == digest]
        if not matches:
            raise ValueError("output file digest is not present in the execution receipt")
        receipt_output = matches[0]
        now = dt.datetime.now(dt.timezone.utc).isoformat().replace("+00:00", "Z")
        inspection = {
            "schema_version": "creative-craft.output-inspection.v1",
            "inspection_id": f"inspection-{receipt_output['asset_id']}",
            "job_id": str(job["job_id"]),
            "receipt_id": str(receipt["receipt_id"]),
            "output_asset_id": str(receipt_output["asset_id"]),
            "output_sha256": digest,
            "inspector": args.inspector,
            "inspected_at": now,
            "findings": [],
            "invariant_checks": [],
            "copy_checks": [],
            "technical_checks": [{
                "id": "file-digest",
                "status": "pass",
                "observation": "The inspected file exists and its SHA-256 matches the execution receipt.",
                "interpretation": "File identity is bound; creative quality has not been inspected.",
            }],
            "rights_checks": [],
            "decision": "deferred",
            "approval": {"approved_by": None, "approved_at": None, "approval_basis": ""},
            "remaining_unknowns": [
                "Visual or audiovisual inspection has not been completed.",
                "Invariants, exact copy, technical quality, and rights still require explicit checks.",
            ],
        }
        _write_json_artifact(output_path, inspection, args.force)
    except (KeyError, OSError, ValueError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    print(output_path)
    return 0


def cmd_start_revision(args: argparse.Namespace) -> int:
    inspection_path = Path(args.inspection).resolve()
    output_path = Path(args.output).resolve()
    try:
        inspection = load_json(inspection_path)
        _, result = validate_data(inspection, "output-inspection")
        if not result.ok:
            raise ValueError("inspection artifact is invalid: " + "; ".join(result.errors))
        revision = {
            "schema_version": "creative-craft.revision-lineage.v1",
            "revision_id": f"revision-{inspection['inspection_id']}",
            "parent_output_ref": (
                f"cc://output-inspection/{inspection['inspection_id']}#/output_asset_id"
            ),
            "parent_inspection_ref": f"cc://output-inspection/{inspection['inspection_id']}#",
            "primary_variable": args.primary_variable,
            "reason": args.reason,
            "change": [],
            "preserve": [],
            "integration_changes": [],
            "new_job_ref": None,
            "new_receipt_ref": None,
            "new_output_ref": None,
            "observed_result": None,
            "comparison": None,
            "decision": "draft",
            "next_action": "Create one new job that changes the primary variable and preserves all locked invariants.",
        }
        _write_json_artifact(output_path, revision, args.force)
    except (KeyError, OSError, ValueError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    print(output_path)
    return 0


def cmd_verify_delivery(args: argparse.Namespace) -> int:
    graph = validate_project(Path(args.root))
    delivery_path = Path(args.file).resolve()
    delivery_record = next(
        (record for (artifact_type, _), record in graph.records.items()
         if artifact_type == "delivery" and record["path"] == delivery_path),
        None,
    )
    if delivery_record is None:
        graph.result.errors.append("delivery file is not registered in project-manifest.json")
    elif delivery_record["data"].get("schema_version") != "creative-craft.delivery.v2":
        graph.result.errors.append("verify-delivery requires creative-craft.delivery.v2")
    elif delivery_record["data"].get("status") != "delivered":
        graph.result.errors.append("delivery status is not delivered")
    return render_result(delivery_path, "delivery", graph.result, args.json)


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
        "self-test", help="run repository or installed-runtime validation and compiler smoke tests"
    )
    self_test_parser.add_argument("--root")
    self_test_parser.add_argument("--json", action="store_true")
    self_test_parser.set_defaults(func=cmd_self_test)

    validate_parser = sub.add_parser("validate", help="validate a versioned artifact")
    validate_parser.add_argument("--file", required=True)
    validate_parser.add_argument(
        "--kind",
        default="auto",
        choices=["auto", *sorted(set(SCHEMA_TO_KIND.values()))],
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
    score_parser.add_argument("--root", help="project root required for evidence-bound evaluation v2")
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

    project_parser = sub.add_parser(
        "validate-project", help="validate a project manifest, digests, and cross-artifact graph"
    )
    project_parser.add_argument("--root", required=True)
    project_parser.add_argument("--json", action="store_true")
    project_parser.set_defaults(func=cmd_validate_project)

    status_parser = sub.add_parser(
        "project-status", help="project evidence and derived job status summary"
    )
    status_parser.add_argument("--root", required=True)
    status_parser.add_argument("--json", action="store_true")
    status_parser.set_defaults(func=cmd_project_status)

    inspection_parser = sub.add_parser(
        "inspect-output", help="create a digest-bound draft inspection skeleton"
    )
    inspection_parser.add_argument("--job", required=True)
    inspection_parser.add_argument("--receipt", required=True)
    inspection_parser.add_argument("--file", required=True)
    inspection_parser.add_argument("--output", required=True)
    inspection_parser.add_argument("--inspector", default="TBD")
    inspection_parser.add_argument("--force", action="store_true")
    inspection_parser.set_defaults(func=cmd_inspect_output)

    revision_parser = sub.add_parser(
        "start-revision", help="create a draft one-variable revision lineage artifact"
    )
    revision_parser.add_argument("--inspection", required=True)
    revision_parser.add_argument("--output", required=True)
    revision_parser.add_argument("--primary-variable", default="TBD")
    revision_parser.add_argument("--reason", default="TBD")
    revision_parser.add_argument("--force", action="store_true")
    revision_parser.set_defaults(func=cmd_start_revision)

    delivery_parser = sub.add_parser(
        "verify-delivery", help="verify a delivered v2 manifest against project evidence"
    )
    delivery_parser.add_argument("--root", required=True)
    delivery_parser.add_argument("--file", required=True)
    delivery_parser.add_argument("--json", action="store_true")
    delivery_parser.set_defaults(func=cmd_verify_delivery)
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())
