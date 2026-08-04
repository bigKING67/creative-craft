#!/usr/bin/env python3
"""Portable tooling for Creative Craft.

The CLI intentionally uses only the Python standard library. It validates and
compiles creative artifacts but never calls a provider or incurs generation
costs.
"""

from __future__ import annotations

import argparse
import copy
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
    "creative-craft.brand-pack.v1": {
        "kind": "brand-pack", "schema": "brand-pack.schema.json",
        "template": "brand-pack.json", "legacy": False,
    },
    "creative-craft.brand-binding.v1": {
        "kind": "brand-binding", "schema": "brand-binding.schema.json",
        "template": "brand-binding.json", "legacy": False,
    },
    "creative-craft.reference-pack.v1": {
        "kind": "reference-pack", "schema": "reference-pack.schema.json",
        "template": "reference-pack.json", "legacy": False,
    },
    "creative-craft.reference-binding.v1": {
        "kind": "reference-binding", "schema": "reference-binding.schema.json",
        "template": "reference-binding.json", "legacy": False,
    },
}

# Brand artifacts are opt-in. Keeping an explicit project inventory prevents a
# generic seed from silently acquiring empty brand authority templates.
PROJECT_SEED_SCHEMA_VERSIONS = {
    "creative-craft.brief.v1",
    "creative-craft.asset-ledger.v1",
    "creative-craft.concept-routes.v1",
    "creative-craft.critique.v1",
    "creative-craft.project-manifest.v1",
    "creative-craft.creative-direction.v1",
    "creative-craft.image-job.v2",
    "creative-craft.video-job.v2",
    "creative-craft.execution-receipt.v1",
    "creative-craft.output-inspection.v1",
    "creative-craft.revision-lineage.v1",
    "creative-craft.evaluation.v2",
    "creative-craft.delivery.v2",
}
PROJECT_MANIFEST_SEED_SCHEMA_VERSIONS = {
    "creative-craft.brief.v1",
    "creative-craft.asset-ledger.v1",
    "creative-craft.concept-routes.v1",
    "creative-craft.creative-direction.v1",
    "creative-craft.image-job.v2",
    "creative-craft.video-job.v2",
    "creative-craft.evaluation.v2",
    "creative-craft.delivery.v2",
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


def validate_brand_pack_artifact(data: dict[str, Any]) -> Result:
    r = Result()
    roles: set[str] = set()
    paths: set[str] = set()
    brand_roles = 0
    for index, item in enumerate(data.get("authority_files", [])):
        if not isinstance(item, dict):
            continue
        role = item.get("role")
        path = item.get("path")
        if isinstance(role, str):
            r.require(role not in roles, f"authority_files[{index}] duplicates role {role!r}")
            roles.add(role)
            if role == "brand":
                brand_roles += 1
        if isinstance(path, str):
            r.require(path not in paths, f"authority_files[{index}] duplicates path {path!r}")
            paths.add(path)
    r.require(brand_roles == 1, "brand pack requires exactly one authority file with role='brand'")
    ledger = data.get("asset_ledger", {})
    if isinstance(ledger, dict):
        r.require(ledger.get("path") not in paths,
                  "asset_ledger.path must not duplicate an authority file path")
    source_ids: set[str] = set()
    for index, source in enumerate(data.get("source_references", [])):
        if not isinstance(source, dict):
            continue
        source_id = source.get("source_id")
        if isinstance(source_id, str):
            r.require(source_id not in source_ids,
                      f"source_references[{index}] duplicates source_id {source_id!r}")
            source_ids.add(source_id)
    if data.get("status") == "approved":
        r.require(nonempty(data.get("approved_at")), "approved brand pack requires approved_at")
        r.require(bool(data.get("source_references")),
                  "approved brand pack requires at least one source reference")
        for index, source in enumerate(data.get("source_references", [])):
            if isinstance(source, dict):
                r.require(nonempty(source.get("reviewed_at")),
                          f"approved brand pack requires source_references[{index}].reviewed_at")
                if nonempty(source.get("reviewed_at")):
                    try:
                        dt.datetime.fromisoformat(
                            str(source.get("reviewed_at")).replace("Z", "+00:00")
                        )
                    except ValueError:
                        r.errors.append(
                            f"source_references[{index}].reviewed_at must be ISO-8601"
                        )
        if nonempty(data.get("approved_at")):
            try:
                dt.datetime.fromisoformat(str(data.get("approved_at")).replace("Z", "+00:00"))
            except ValueError:
                r.errors.append("approved_at must be ISO-8601")
        r.warn(nonempty(data.get("review_after")),
               "approved brand pack has no review_after date")
    return r


def validate_brand_binding(data: dict[str, Any]) -> Result:
    r = Result()
    try:
        dt.datetime.fromisoformat(str(data.get("imported_at")).replace("Z", "+00:00"))
    except ValueError:
        r.errors.append("imported_at must be an ISO-8601 timestamp")
    source = data.get("source", {})
    if isinstance(source, dict) and source.get("commit") is not None:
        r.require(nonempty(source.get("repository_or_uri")),
                  "source.commit requires source.repository_or_uri")
    return r


def validate_reference_pack_artifact(data: dict[str, Any]) -> Result:
    r = Result()
    for field_name in ("reviewed_at", "review_after"):
        value = data.get(field_name)
        if value is None:
            continue
        try:
            dt.datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        except ValueError:
            r.errors.append(f"{field_name} must be ISO-8601 or null")
    source_ids: set[str] = set()
    for index, source in enumerate(data.get("source_references", [])):
        if not isinstance(source, dict):
            continue
        source_id = source.get("source_id")
        if isinstance(source_id, str):
            r.require(source_id not in source_ids,
                      f"source_references[{index}] duplicates source_id {source_id!r}")
            source_ids.add(source_id)
        captured_at = source.get("captured_at")
        if captured_at is not None:
            try:
                dt.datetime.fromisoformat(str(captured_at).replace("Z", "+00:00"))
            except ValueError:
                r.errors.append(f"source_references[{index}].captured_at must be ISO-8601")

    reference_ids: set[str] = set()
    observation_ids: set[str] = set()
    principle_ids: set[str] = set()
    for index, entity in enumerate(data.get("entities", [])):
        if not isinstance(entity, dict):
            continue
        reference_id = entity.get("reference_id")
        if isinstance(reference_id, str):
            r.require(reference_id not in reference_ids,
                      f"entities[{index}] duplicates reference_id {reference_id!r}")
            reference_ids.add(reference_id)
        for source_ref in entity.get("source_refs", []):
            r.require(source_ref in source_ids,
                      f"entities[{index}] references unknown source {source_ref!r}")
        entity_observation_ids: set[str] = set()
        for observation in entity.get("observations", []):
            if not isinstance(observation, dict):
                continue
            observation_id = observation.get("observation_id")
            if isinstance(observation_id, str):
                r.require(observation_id not in observation_ids,
                          f"duplicate observation_id {observation_id!r}")
                observation_ids.add(observation_id)
                entity_observation_ids.add(observation_id)
            if observation.get("evidence_state") == "UNVERIFIED":
                r.require(not observation.get("evidence_refs"),
                          f"observation {observation_id!r} is UNVERIFIED and must not cite evidence")
            else:
                r.require(bool(observation.get("evidence_refs")),
                          f"observation {observation_id!r} requires evidence_refs")
        for principle in entity.get("transferable_principles", []):
            if not isinstance(principle, dict):
                continue
            principle_id = principle.get("principle_id")
            if isinstance(principle_id, str):
                r.require(principle_id not in principle_ids,
                          f"duplicate principle_id {principle_id!r}")
                principle_ids.add(principle_id)
            for observation_id in principle.get("derived_from", []):
                r.require(observation_id in entity_observation_ids,
                          f"principle {principle_id!r} derives from unknown observation {observation_id!r}")
        r.require(entity.get("may_override_primary_brand") is False,
                  f"entities[{index}] must not override the primary brand")

    if data.get("status") == "reviewed":
        r.require(nonempty(data.get("reviewed_at")), "reviewed reference pack requires reviewed_at")
        r.require(bool(data.get("source_references")),
                  "reviewed reference pack requires source_references")
        r.require(bool(data.get("entities")), "reviewed reference pack requires entities")
        for index, source in enumerate(data.get("source_references", [])):
            if isinstance(source, dict):
                r.require(nonempty(source.get("captured_at")),
                          f"reviewed reference pack requires source_references[{index}].captured_at")
        for entity in data.get("entities", []):
            if not isinstance(entity, dict):
                continue
            for observation in entity.get("observations", []):
                if isinstance(observation, dict):
                    r.require(observation.get("evidence_state") != "UNVERIFIED",
                              "reviewed reference pack cannot contain UNVERIFIED observations")
        r.warn(nonempty(data.get("review_after")),
               "reviewed reference pack has no review_after date")
    return r


def validate_reference_binding(data: dict[str, Any]) -> Result:
    r = Result()
    try:
        dt.datetime.fromisoformat(str(data.get("imported_at")).replace("Z", "+00:00"))
    except ValueError:
        r.errors.append("imported_at must be an ISO-8601 timestamp")
    source = data.get("source", {})
    if isinstance(source, dict) and source.get("commit") is not None:
        r.require(nonempty(source.get("repository_or_uri")),
                  "source.commit requires source.repository_or_uri")
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
        "creative-craft.brand-pack.v1": validate_brand_pack_artifact,
        "creative-craft.brand-binding.v1": validate_brand_binding,
        "creative-craft.reference-pack.v1": validate_reference_pack_artifact,
        "creative-craft.reference-binding.v1": validate_reference_binding,
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
    "brand-pack": "pack_id",
    "brand-binding": "binding_id",
    "reference-pack": "reference_pack_id",
    "reference-binding": "binding_id",
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


def _safe_relative_path(
    root: Path, value: Any, *, label: str = "path"
) -> tuple[Path | None, str | None]:
    if not isinstance(value, str) or not value:
        return None, f"{label} must be a non-empty string"
    relative = Path(value)
    if relative.is_absolute() or ".." in relative.parts:
        return None, f"unsafe root-relative {label}: {value!r}"
    candidate = root / relative
    current = root
    for part in relative.parts:
        current = current / part
        if current.is_symlink():
            return None, f"{label} must not use a symlink: {value!r}"
    try:
        resolved = candidate.resolve(strict=False)
        resolved.relative_to(root.resolve())
    except (OSError, ValueError):
        return None, f"{label} escapes root: {value!r}"
    return candidate, None


def _safe_project_path(root: Path, value: Any) -> tuple[Path | None, str | None]:
    path, error = _safe_relative_path(root, value, label="project-relative path")
    if error and error.startswith("unsafe root-relative"):
        return path, error.replace("unsafe root-relative project-relative path",
                                   "unsafe project-relative path", 1)
    return path, error


def tree_sha256(root: Path) -> str:
    if not root.is_dir():
        raise ValueError(f"tree root is not a directory: {root}")
    files: list[Path] = []
    for path in root.rglob("*"):
        relative = path.relative_to(root).as_posix()
        if path.is_symlink():
            raise ValueError(f"tree contains a symlink: {relative}")
        if path.is_file():
            files.append(path)
    digest = hashlib.sha256()
    for path in sorted(files, key=lambda item: item.relative_to(root).as_posix()):
        relative = path.relative_to(root).as_posix()
        digest.update(relative.encode("utf-8"))
        digest.update(b"\0")
        digest.update(sha256_file(path).encode("ascii"))
        digest.update(b"\n")
    return digest.hexdigest()


def _is_external_asset_uri(value: str) -> bool:
    match = re.match(r"^([A-Za-z][A-Za-z0-9+.-]*)://", value)
    return bool(match and match.group(1).lower() != "file")


@dataclass
class BrandPackGraph:
    root: Path
    manifest_path: Path
    manifest: dict[str, Any]
    ledger_path: Path | None = None
    ledger: dict[str, Any] = field(default_factory=dict)
    authority_paths: dict[str, Path] = field(default_factory=dict)
    result: Result = field(default_factory=Result)


def validate_brand_pack(
    root: Path, context: ValidationContext | None = None
) -> BrandPackGraph:
    source_root = Path(root).expanduser()
    root_is_symlink = source_root.is_symlink()
    resolved_root = source_root.resolve()
    manifest_path = resolved_root / "brand-pack.json"
    graph = BrandPackGraph(resolved_root, manifest_path, {})
    graph.result.require(not root_is_symlink, "brand pack root must not be a symlink")
    graph.result.require(resolved_root.is_dir(), f"brand pack root is not a directory: {resolved_root}")
    if not resolved_root.is_dir():
        return graph
    if manifest_path.is_symlink():
        graph.result.errors.append("brand-pack.json must not be a symlink")
        return graph
    try:
        manifest = load_json(manifest_path)
    except ValueError as exc:
        graph.result.errors.append(str(exc))
        return graph
    graph.manifest = manifest
    _, manifest_result = validate_data(manifest, "brand-pack", context)
    graph.result.extend(manifest_result)
    if not manifest_result.ok:
        return graph

    for index, item in enumerate(manifest.get("authority_files", [])):
        if not isinstance(item, dict):
            continue
        path, error = _safe_relative_path(
            resolved_root, item.get("path"), label=f"authority_files[{index}].path"
        )
        if error:
            graph.result.errors.append(error)
            continue
        if path is None or not path.is_file():
            graph.result.errors.append(
                f"authority_files[{index}] file does not exist: {item.get('path')!r}"
            )
            continue
        graph.result.require(
            sha256_file(path) == item.get("sha256"),
            f"authority_files[{index}] sha256 mismatch: {item.get('path')}",
        )
        graph.authority_paths[str(item.get("role"))] = path
        if manifest.get("status") == "approved":
            try:
                authority_text = path.read_text(encoding="utf-8")
            except UnicodeDecodeError:
                graph.result.errors.append(
                    f"approved authority file must be UTF-8 text: {item.get('path')}"
                )
            else:
                graph.result.require(
                    not re.search(r"\bTBD\b", authority_text),
                    f"approved authority file still contains TBD: {item.get('path')}",
                )
                graph.result.require(
                    not re.search(
                        r"(?im)^\s*Status:\s*`?UNVERIFIED`?\s*$", authority_text
                    ),
                    f"approved authority file still declares UNVERIFIED: {item.get('path')}",
                )

    ledger_ref = manifest.get("asset_ledger", {})
    if isinstance(ledger_ref, dict):
        ledger_path, error = _safe_relative_path(
            resolved_root, ledger_ref.get("path"), label="asset_ledger.path"
        )
        if error:
            graph.result.errors.append(error)
        elif ledger_path is None or not ledger_path.is_file():
            graph.result.errors.append(
                f"asset ledger file does not exist: {ledger_ref.get('path')!r}"
            )
        else:
            graph.ledger_path = ledger_path
            graph.result.require(
                sha256_file(ledger_path) == ledger_ref.get("sha256"),
                f"asset ledger sha256 mismatch: {ledger_ref.get('path')}",
            )
            try:
                graph.ledger = load_json(ledger_path)
            except ValueError as exc:
                graph.result.errors.append(str(exc))
            else:
                _, ledger_result = validate_data(graph.ledger, "asset-ledger", context)
                graph.result.errors.extend(
                    f"asset ledger: {message}" for message in ledger_result.errors
                )
                graph.result.warnings.extend(
                    f"asset ledger: {message}" for message in ledger_result.warnings
                )
                expected_project_id = f"brand:{manifest.get('brand_id')}"
                graph.result.require(
                    graph.ledger.get("project_id") == expected_project_id,
                    f"asset ledger project_id must be {expected_project_id!r}",
                )
                for index, asset in enumerate(graph.ledger.get("assets", [])):
                    if not isinstance(asset, dict):
                        continue
                    path_or_uri = str(asset.get("path_or_uri", ""))
                    digest = asset.get("sha256")
                    graph.result.require(
                        isinstance(digest, str) and bool(re.fullmatch(r"[0-9a-f]{64}", digest)),
                        f"asset ledger assets[{index}] requires a lowercase SHA-256 digest",
                    )
                    if not _is_external_asset_uri(path_or_uri):
                        asset_path, asset_error = _safe_relative_path(
                            resolved_root,
                            path_or_uri,
                            label=f"asset ledger assets[{index}].path_or_uri",
                        )
                        if asset_error:
                            graph.result.errors.append(asset_error)
                        elif asset_path is None or not asset_path.is_file():
                            graph.result.errors.append(
                                f"asset ledger assets[{index}] local file does not exist: {path_or_uri!r}"
                            )
                        elif isinstance(digest, str):
                            graph.result.require(
                                sha256_file(asset_path) == digest,
                                f"asset ledger assets[{index}] sha256 mismatch: {path_or_uri}",
                            )
                    if manifest.get("status") == "approved":
                        graph.result.require(
                            asset.get("rights_status") in {"CLEARED", "LIMITED"},
                            f"approved brand pack asset {asset.get('asset_id')!r} has unresolved rights",
                        )
                        graph.result.require(
                            asset.get("consent_status")
                            in {"CLEARED", "LIMITED", "NOT_APPLICABLE"},
                            f"approved brand pack asset {asset.get('asset_id')!r} has unresolved consent",
                        )
    return graph


@dataclass
class ReferencePackGraph:
    root: Path
    manifest_path: Path
    manifest: dict[str, Any]
    ledger_path: Path | None = None
    ledger: dict[str, Any] = field(default_factory=dict)
    result: Result = field(default_factory=Result)


def validate_reference_pack(
    root: Path, context: ValidationContext | None = None
) -> ReferencePackGraph:
    source_root = Path(root).expanduser()
    root_is_symlink = source_root.is_symlink()
    resolved_root = source_root.resolve()
    manifest_path = resolved_root / "reference-pack.json"
    graph = ReferencePackGraph(resolved_root, manifest_path, {})
    graph.result.require(not root_is_symlink, "reference pack root must not be a symlink")
    graph.result.require(
        resolved_root.is_dir(), f"reference pack root is not a directory: {resolved_root}"
    )
    if not resolved_root.is_dir():
        return graph
    if manifest_path.is_symlink():
        graph.result.errors.append("reference-pack.json must not be a symlink")
        return graph
    try:
        manifest = load_json(manifest_path)
    except ValueError as exc:
        graph.result.errors.append(str(exc))
        return graph
    graph.manifest = manifest
    _, manifest_result = validate_data(manifest, "reference-pack", context)
    graph.result.extend(manifest_result)
    if not manifest_result.ok:
        return graph

    ledger_ref = manifest.get("asset_ledger", {})
    if not isinstance(ledger_ref, dict):
        return graph
    ledger_path, error = _safe_relative_path(
        resolved_root, ledger_ref.get("path"), label="asset_ledger.path"
    )
    if error:
        graph.result.errors.append(error)
        return graph
    if ledger_path is None or not ledger_path.is_file():
        graph.result.errors.append(
            f"asset ledger file does not exist: {ledger_ref.get('path')!r}"
        )
        return graph
    graph.ledger_path = ledger_path
    graph.result.require(
        sha256_file(ledger_path) == ledger_ref.get("sha256"),
        f"asset ledger sha256 mismatch: {ledger_ref.get('path')}",
    )
    try:
        graph.ledger = load_json(ledger_path)
    except ValueError as exc:
        graph.result.errors.append(str(exc))
        return graph
    _, ledger_result = validate_data(graph.ledger, "asset-ledger", context)
    graph.result.errors.extend(f"asset ledger: {message}" for message in ledger_result.errors)
    graph.result.warnings.extend(
        f"asset ledger: {message}" for message in ledger_result.warnings
    )
    expected_project_id = f"reference:{manifest.get('reference_pack_id')}"
    graph.result.require(
        graph.ledger.get("project_id") == expected_project_id,
        f"asset ledger project_id must be {expected_project_id!r}",
    )

    assets: dict[str, dict[str, Any]] = {}
    for index, asset in enumerate(graph.ledger.get("assets", [])):
        if not isinstance(asset, dict):
            continue
        asset_id = str(asset.get("asset_id"))
        graph.result.require(
            asset_id not in assets,
            f"asset ledger assets[{index}] duplicates asset_id {asset_id!r}",
        )
        assets[asset_id] = asset
        path_or_uri = str(asset.get("path_or_uri", ""))
        digest = asset.get("sha256")
        graph.result.require(
            isinstance(digest, str) and bool(re.fullmatch(r"[0-9a-f]{64}", digest)),
            f"asset ledger assets[{index}] requires a lowercase SHA-256 digest",
        )
        if not _is_external_asset_uri(path_or_uri):
            asset_path, asset_error = _safe_relative_path(
                resolved_root,
                path_or_uri,
                label=f"asset ledger assets[{index}].path_or_uri",
            )
            if asset_error:
                graph.result.errors.append(asset_error)
            elif asset_path is None or not asset_path.is_file():
                graph.result.errors.append(
                    f"asset ledger assets[{index}] local file does not exist: {path_or_uri!r}"
                )
            elif isinstance(digest, str):
                graph.result.require(
                    sha256_file(asset_path) == digest,
                    f"asset ledger assets[{index}] sha256 mismatch: {path_or_uri}",
                )

    source_ids = {
        str(source.get("source_id"))
        for source in manifest.get("source_references", [])
        if isinstance(source, dict)
    }
    for entity_index, entity in enumerate(manifest.get("entities", [])):
        if not isinstance(entity, dict):
            continue
        entity_assets: list[dict[str, Any]] = []
        for asset_id in entity.get("asset_refs", []):
            graph.result.require(
                asset_id in assets,
                f"entities[{entity_index}] references unknown asset {asset_id!r}",
            )
            if asset_id in assets:
                entity_assets.append(assets[str(asset_id)])
        for observation in entity.get("observations", []):
            if not isinstance(observation, dict):
                continue
            for evidence_ref in observation.get("evidence_refs", []):
                graph.result.require(
                    evidence_ref in source_ids or evidence_ref in assets,
                    f"observation {observation.get('observation_id')!r} references unknown evidence {evidence_ref!r}",
                )
        if entity.get("rights_policy") == "approved_reference_input":
            graph.result.require(
                bool(entity_assets),
                f"entities[{entity_index}] approved_reference_input requires asset_refs",
            )
            for asset in entity_assets:
                graph.result.require(
                    asset.get("rights_status") in {"CLEARED", "LIMITED"},
                    f"approved reference input {asset.get('asset_id')!r} has unresolved rights",
                )
                graph.result.require(
                    asset.get("consent_status")
                    in {"CLEARED", "LIMITED", "NOT_APPLICABLE"},
                    f"approved reference input {asset.get('asset_id')!r} has unresolved consent",
                )
    return graph


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


def _project_brand_cross_checks(graph: ProjectGraph) -> None:
    packs = [record for (kind, _), record in graph.records.items() if kind == "brand-pack"]
    bindings = [record for (kind, _), record in graph.records.items() if kind == "brand-binding"]
    if not packs and not bindings:
        return
    graph.result.require(len(packs) == 1, "project must register exactly one brand-pack artifact")
    graph.result.require(len(bindings) == 1,
                         "project must register exactly one brand-binding artifact")
    if len(packs) != 1 or len(bindings) != 1:
        return
    pack_record = packs[0]
    binding_record = bindings[0]
    pack = pack_record["data"]
    binding = binding_record["data"]
    graph.result.require(
        binding_record["path"] == graph.root / ".creative-craft" / "brand-binding.json",
        "brand-binding artifact must use .creative-craft/brand-binding.json",
    )
    graph.result.require(binding.get("project_id") == graph.manifest.get("project_id"),
                         "brand binding project_id differs from project manifest")
    graph.result.require(binding.get("brand_id") == pack.get("brand_id"),
                         "brand binding brand_id differs from brand pack")
    graph.result.require(binding.get("pack_id") == pack.get("pack_id"),
                         "brand binding pack_id differs from brand pack")
    graph.result.require(binding.get("pack_version") == pack.get("version"),
                         "brand binding pack_version differs from brand pack")
    graph.result.require(pack.get("status") != "revoked",
                         "project must not bind a revoked brand pack")

    snapshot = binding.get("snapshot", {})
    snapshot_value = snapshot.get("path") if isinstance(snapshot, dict) else None
    graph.result.require(snapshot_value == ".creative-craft/brand-snapshot",
                         "brand binding snapshot.path must be .creative-craft/brand-snapshot")
    snapshot_path, snapshot_error = _safe_project_path(graph.root, snapshot_value)
    graph.result.require(snapshot_error is None, f"brand binding snapshot: {snapshot_error}")
    if snapshot_path is None or not snapshot_path.is_dir():
        graph.result.errors.append("brand binding snapshot directory does not exist")
        return
    expected_pack_path = snapshot_path / "brand-pack.json"
    graph.result.require(pack_record["path"] == expected_pack_path,
                         "registered brand-pack artifact is not the bound snapshot manifest")
    snapshot_graph = validate_brand_pack(snapshot_path)
    graph.result.errors.extend(
        f"brand snapshot: {message}" for message in snapshot_graph.result.errors
    )
    graph.result.warnings.extend(
        f"brand snapshot: {message}" for message in snapshot_graph.result.warnings
    )
    try:
        actual_tree_sha = tree_sha256(snapshot_path)
    except ValueError as exc:
        graph.result.errors.append(str(exc))
    else:
        graph.result.require(
            actual_tree_sha == snapshot.get("tree_sha256"),
            "brand binding snapshot tree_sha256 mismatch",
        )
    source = binding.get("source", {})
    graph.result.require(
        isinstance(source, dict) and source.get("pack_sha256") == pack_record["sha256"],
        "brand binding source.pack_sha256 differs from snapshot brand-pack.json",
    )

    project_brand = binding.get("project_brand", {})
    project_brand_value = project_brand.get("path") if isinstance(project_brand, dict) else None
    graph.result.require(project_brand_value == "BRAND.md",
                         "brand binding project_brand.path must be BRAND.md")
    brand_path, brand_error = _safe_project_path(graph.root, project_brand_value)
    graph.result.require(brand_error is None, f"brand binding project_brand: {brand_error}")
    if brand_path is None or not brand_path.is_file():
        graph.result.errors.append("bound project BRAND.md does not exist")
        return
    brand_digest = sha256_file(brand_path)
    graph.result.require(brand_digest == project_brand.get("sha256"),
                         "brand binding project_brand.sha256 mismatch")
    brand_authority = next(
        (item for item in pack.get("authority_files", [])
         if isinstance(item, dict) and item.get("role") == "brand"),
        None,
    )
    if isinstance(brand_authority, dict):
        graph.result.require(brand_digest == brand_authority.get("sha256"),
                             "project BRAND.md differs from snapshot brand authority")


def _project_reference_cross_checks(graph: ProjectGraph) -> None:
    pack_records = [
        record for (kind, _), record in graph.records.items() if kind == "reference-pack"
    ]
    binding_records = [
        record for (kind, _), record in graph.records.items() if kind == "reference-binding"
    ]
    if not pack_records and not binding_records:
        return

    packs: dict[str, dict[str, Any]] = {}
    for record in pack_records:
        pack_id = str(record["data"].get("reference_pack_id"))
        graph.result.require(pack_id not in packs,
                             f"duplicate reference-pack artifact for {pack_id!r}")
        packs[pack_id] = record
    bindings: dict[str, dict[str, Any]] = {}
    for record in binding_records:
        pack_id = str(record["data"].get("reference_pack_id"))
        graph.result.require(pack_id not in bindings,
                             f"duplicate reference binding for {pack_id!r}")
        bindings[pack_id] = record
    graph.result.require(
        set(packs) == set(bindings),
        "every reference pack must have exactly one matching reference binding",
    )

    project_ledgers = [
        record for (kind, _), record in graph.records.items() if kind == "asset-ledger"
    ]
    project_assets = {
        str(asset.get("asset_id")): asset
        for record in project_ledgers
        for asset in record["data"].get("assets", [])
        if isinstance(asset, dict)
    }
    for pack_id in sorted(set(packs).intersection(bindings)):
        pack_record = packs[pack_id]
        binding_record = bindings[pack_id]
        pack = pack_record["data"]
        binding = binding_record["data"]
        expected_binding_path = (
            graph.root / ".creative-craft" / "reference-bindings" / f"{pack_id}.json"
        )
        graph.result.require(
            binding_record["path"] == expected_binding_path,
            f"reference binding {pack_id!r} uses a non-canonical path",
        )
        graph.result.require(
            binding.get("project_id") == graph.manifest.get("project_id"),
            f"reference binding {pack_id!r} project_id differs from project manifest",
        )
        graph.result.require(
            binding.get("pack_version") == pack.get("version"),
            f"reference binding {pack_id!r} pack_version differs from reference pack",
        )
        graph.result.require(
            pack.get("status") != "revoked",
            f"project must not bind revoked reference pack {pack_id!r}",
        )
        if pack.get("status") == "draft":
            graph.result.warnings.append(
                f"reference pack {pack_id!r} is draft; treat its contents as exploratory evidence"
            )

        snapshot = binding.get("snapshot", {})
        snapshot_value = snapshot.get("path") if isinstance(snapshot, dict) else None
        expected_snapshot_value = f".creative-craft/reference-snapshots/{pack_id}"
        graph.result.require(
            snapshot_value == expected_snapshot_value,
            f"reference binding {pack_id!r} snapshot.path must be {expected_snapshot_value}",
        )
        snapshot_path, snapshot_error = _safe_project_path(graph.root, snapshot_value)
        graph.result.require(
            snapshot_error is None,
            f"reference binding {pack_id!r} snapshot: {snapshot_error}",
        )
        if snapshot_path is None or not snapshot_path.is_dir():
            graph.result.errors.append(
                f"reference binding {pack_id!r} snapshot directory does not exist"
            )
            continue
        graph.result.require(
            pack_record["path"] == snapshot_path / "reference-pack.json",
            f"registered reference pack {pack_id!r} is not the bound snapshot manifest",
        )
        snapshot_graph = validate_reference_pack(snapshot_path)
        graph.result.errors.extend(
            f"reference snapshot {pack_id!r}: {message}"
            for message in snapshot_graph.result.errors
        )
        graph.result.warnings.extend(
            f"reference snapshot {pack_id!r}: {message}"
            for message in snapshot_graph.result.warnings
        )
        try:
            actual_tree_sha = tree_sha256(snapshot_path)
        except ValueError as exc:
            graph.result.errors.append(str(exc))
        else:
            graph.result.require(
                actual_tree_sha == snapshot.get("tree_sha256"),
                f"reference binding {pack_id!r} snapshot tree_sha256 mismatch",
            )
        source = binding.get("source", {})
        graph.result.require(
            isinstance(source, dict) and source.get("pack_sha256") == pack_record["sha256"],
            f"reference binding {pack_id!r} source.pack_sha256 differs from snapshot",
        )

        entities = {
            str(entity.get("reference_id")): entity
            for entity in pack.get("entities", [])
            if isinstance(entity, dict)
        }
        selected_ids = binding.get("selected_reference_ids", [])
        for reference_id in selected_ids:
            graph.result.require(
                reference_id in entities,
                f"reference binding {pack_id!r} selects unknown reference {reference_id!r}",
            )
            entity = entities.get(str(reference_id), {})
            for asset_id in entity.get("asset_refs", []):
                graph.result.require(
                    asset_id in project_assets,
                    f"reference binding {pack_id!r} selected asset {asset_id!r} is absent from project ledger",
                )
                source_asset = next(
                    (
                        asset for asset in snapshot_graph.ledger.get("assets", [])
                        if isinstance(asset, dict) and asset.get("asset_id") == asset_id
                    ),
                    None,
                )
                project_asset = project_assets.get(str(asset_id))
                if source_asset and project_asset:
                    source_value = str(source_asset.get("path_or_uri"))
                    expected_value = (
                        source_value
                        if _is_external_asset_uri(source_value)
                        else f"{expected_snapshot_value}/{Path(source_value).as_posix()}"
                    )
                    graph.result.require(
                        project_asset.get("path_or_uri") == expected_value,
                        f"reference binding {pack_id!r} asset {asset_id!r} path differs from snapshot",
                    )
                    graph.result.require(
                        project_asset.get("sha256") == source_asset.get("sha256"),
                        f"reference binding {pack_id!r} asset {asset_id!r} digest differs from snapshot",
                    )


def _project_cross_checks(graph: ProjectGraph) -> None:
    _project_brand_cross_checks(graph)
    _project_reference_cross_checks(graph)
    bound_brand_packs = [
        record["data"] for (kind, _), record in graph.records.items() if kind == "brand-pack"
    ]
    has_brand_binding = any(kind == "brand-binding" for kind, _ in graph.records)
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
                if has_brand_binding:
                    graph.result.require(
                        len(bound_brand_packs) == 1
                        and bound_brand_packs[0].get("status") == "approved",
                        f"ready job {artifact_id} requires an approved bound brand pack",
                    )
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

    ignored_parts = {".git", ".venv", "__pycache__", "dist", "node_modules"}
    for path in sorted(root.rglob("*.json")):
        if any(part in ignored_parts for part in path.parts):
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
        if any(part in ignored_parts for part in path.parts):
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


def _json_text(data: dict[str, Any]) -> str:
    return json.dumps(data, ensure_ascii=False, indent=2) + "\n"


def _brand_authority_documents(brand_name: str) -> list[tuple[str, str, str]]:
    return [
        ("brand", "references/brand.md", f"""# {brand_name} Brand Authority

Status: `UNVERIFIED`

This draft contains no approved brand facts. Replace every `TBD` only from a reviewed source.

## Identity

- Working brand name: {brand_name}
- Legal entity: TBD
- Purpose: TBD
- Positioning: TBD
- Audience: TBD

## Non-negotiables

- TBD

## Source boundary

- Approved source references: none
"""),
        ("products", "references/products.md", f"""# {brand_name} Product Authority

Status: `UNVERIFIED`

No product fact, SKU specification, ingredient, performance statement, price, or availability is approved in this draft.

## Approved products

- TBD

## Source boundary

- Approved source references: none
"""),
        ("claims", "references/claims.md", f"""# {brand_name} Claims Authority

Status: `UNVERIFIED`

No marketing, efficacy, comparative, sustainability, certification, safety, or compliance claim is approved in this draft.

## Approved claims

- None

## Prohibited until approved

- Any claim without a source, owner, scope, market, and approval record
"""),
        ("visual", "references/visual-system.md", f"""# {brand_name} Visual System

Status: `UNVERIFIED`

## Approved marks and lockups

- TBD

## Color, typography, composition, and image rules

- TBD

## Prohibited treatments

- TBD
"""),
        ("verbal", "references/verbal-system.md", f"""# {brand_name} Verbal System

Status: `UNVERIFIED`

## Voice and tone

- TBD

## Exact terminology

- TBD

## Prohibited language

- TBD
"""),
        ("channels", "references/channels.md", f"""# {brand_name} Channel Rules

Status: `UNVERIFIED`

## Markets and channels

- TBD

## Format and adaptation rules

- TBD

## Required disclosures

- TBD
"""),
        ("rights", "references/rights-and-approvals.md", f"""# {brand_name} Rights and Approvals

Status: `UNVERIFIED`

No asset, person, music, font, claim, or market use is approved by this draft.

## Approval owners

- Brand: TBD
- Legal or compliance: TBD
- Asset rights: TBD

## Approved exceptions

- None
"""),
    ]


def _brand_skill_text(brand_id: str, brand_name: str) -> str:
    description = (
        f"Private {brand_name} brand authority router. Use only when the user or active project "
        f"explicitly identifies brand_id '{brand_id}'. Load reviewed brand references and then "
        "apply the generic creative-craft workflow."
    )
    return f"""---
name: {brand_id}-brand
description: {json.dumps(description, ensure_ascii=False)}
---

# {brand_name} Brand Authority Router

Use this skill only when the request or bound project explicitly identifies `{brand_id}`.

1. Read `brand-pack.json` and reject `revoked` authority.
2. Read only the authority files needed for the task.
3. Treat `TBD` and `UNVERIFIED` as unknown; never turn them into facts or approvals.
4. Resolve assets through `asset-ledger.json`; do not infer rights from file possession.
5. Use the generic `creative-craft` skill for briefs, routes, direction, jobs, inspection, revision, evaluation, and delivery.
6. For project work, use the project's immutable Brand Pack snapshot instead of this live checkout.

This skill contains brand authority only. It does not replace or duplicate Creative Craft schemas, provider profiles, or production methods.
"""


def cmd_init_brand_pack(args: argparse.Namespace) -> int:
    requested_target = Path(args.target).expanduser()
    if requested_target.is_symlink():
        print("ERROR: Brand Pack target must not be a symlink", file=sys.stderr)
        return 1
    target = requested_target.resolve()
    brand_id = str(args.brand_id).strip()
    brand_name = str(args.brand_name).strip()
    owner = str(args.owner).strip()
    if not re.fullmatch(r"[a-z0-9][a-z0-9-]*", brand_id):
        print("ERROR: --brand-id must be a lowercase slug", file=sys.stderr)
        return 1
    if not brand_name or not owner:
        print("ERROR: --brand-name and --owner must be non-empty", file=sys.stderr)
        return 1
    known_paths = [
        target / "SKILL.md",
        target / "VERSION",
        target / "brand-pack.json",
        target / "asset-ledger.json",
        *(target / path for _, path, _ in _brand_authority_documents(brand_name)),
    ]
    conflicts = [path for path in known_paths if path.exists()]
    if conflicts and not args.force:
        print("ERROR: refusing to overwrite existing Brand Pack files:", file=sys.stderr)
        for path in conflicts:
            print(f"  {path}", file=sys.stderr)
        print("Use --force only after reviewing the existing authority.", file=sys.stderr)
        return 1
    if target.exists() and any(target.iterdir()) and args.force:
        suffix = dt.datetime.now(dt.timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
        backup = target.with_name(f"{target.name}.bak.{suffix}")
        shutil.copytree(target, backup, symlinks=True)
        print(f"Backup: {backup}")
    try:
        target.mkdir(parents=True, exist_ok=True)
        documents = _brand_authority_documents(brand_name)
        for _, relative, content in documents:
            write_atomic(target / relative, content)
        ledger = {
            "schema_version": "creative-craft.asset-ledger.v1",
            "project_id": f"brand:{brand_id}",
            "assets": [],
        }
        ledger_path = target / "asset-ledger.json"
        write_atomic(ledger_path, _json_text(ledger))
        manifest = {
            "schema_version": "creative-craft.brand-pack.v1",
            "brand_id": brand_id,
            "brand_name": brand_name,
            "pack_id": f"{brand_id}-brand-pack",
            "version": "0.1.0",
            "status": "draft",
            "classification": "internal",
            "owner": owner,
            "approved_at": None,
            "review_after": None,
            "supersedes": None,
            "authority_files": [
                {"role": role, "path": relative, "sha256": sha256_file(target / relative)}
                for role, relative, _ in documents
            ],
            "asset_ledger": {
                "path": "asset-ledger.json",
                "sha256": sha256_file(ledger_path),
            },
            "source_references": [],
        }
        write_atomic(target / "brand-pack.json", _json_text(manifest))
        write_atomic(target / "SKILL.md", _brand_skill_text(brand_id, brand_name))
        write_atomic(target / "VERSION", "0.1.0\n")
        approved_dir = target / "assets" / "approved"
        approved_dir.mkdir(parents=True, exist_ok=True)
        write_atomic(approved_dir / ".gitkeep", "")
        graph = validate_brand_pack(target)
        if not graph.result.ok:
            raise ValueError("; ".join(graph.result.errors))
    except (OSError, ValueError) as exc:
        print(f"ERROR: failed to initialize Brand Pack: {exc}", file=sys.stderr)
        return 1
    print(target)
    return 0


def cmd_validate_brand_pack(args: argparse.Namespace) -> int:
    graph = validate_brand_pack(Path(args.root))
    payload = {
        "root": str(graph.root),
        "manifest": str(graph.manifest_path),
        "brand_id": graph.manifest.get("brand_id"),
        "pack_id": graph.manifest.get("pack_id"),
        "version": graph.manifest.get("version"),
        "status": graph.manifest.get("status"),
        "classification": graph.manifest.get("classification"),
        "valid": graph.result.ok,
        "authority_roles": sorted(graph.authority_paths),
        "asset_count": len(graph.ledger.get("assets", [])),
        "errors": graph.result.errors,
        "warnings": graph.result.warnings,
    }
    if args.json:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        print(f"{'PASS' if graph.result.ok else 'FAIL'} brand pack: {graph.root}")
        print(f"  Brand: {payload['brand_id']}")
        print(f"  Pack: {payload['pack_id']}@{payload['version']} ({payload['status']})")
        print(f"  Authority files: {len(payload['authority_roles'])}")
        print(f"  Assets: {payload['asset_count']}")
        for message in graph.result.errors:
            print(f"  ERROR: {message}")
        for message in graph.result.warnings:
            print(f"  WARN:  {message}")
    return 0 if graph.result.ok else 1


def _reference_skill_text(reference_pack_id: str, name: str) -> str:
    description = (
        f"Private {name} creative reference router. Use only when the user or active project "
        f"explicitly needs reference_pack_id '{reference_pack_id}'. Load relevant observations "
        "and transferable principles, then apply the generic creative-craft workflow."
    )
    return f"""---
name: {reference_pack_id}
description: {json.dumps(description, ensure_ascii=False)}
---

# {name} Reference Router

Use this skill only when the request or bound project explicitly needs `{reference_pack_id}`.

1. Read `reference-pack.json` and reject a `revoked` pack.
2. Load only the selected reference entities needed for the task.
3. Keep `OBSERVED`, `INFERRED`, `HYPOTHESIZED`, and `UNVERIFIED` distinct.
4. Treat references as research, not as brand authority or permission to imitate.
5. Never override the project's Primary Brand Pack, Brief, exact copy, rights, claims, or product invariants.
6. Resolve assets through `asset-ledger.json`; public visibility does not grant generation-input rights.
7. Use the generic `creative-craft` skill for briefs, routes, direction, jobs, inspection, revision, evaluation, and delivery.
8. For project work, use the immutable project snapshot instead of this live checkout.

This skill contains non-authoritative creative reference intelligence only. It does not replace or duplicate Creative Craft schemas, provider profiles, production methods, or a Primary Brand Pack.
"""


def cmd_init_reference_pack(args: argparse.Namespace) -> int:
    requested_target = Path(args.target).expanduser()
    if requested_target.is_symlink():
        print("ERROR: Reference Pack target must not be a symlink", file=sys.stderr)
        return 1
    target = requested_target.resolve()
    reference_pack_id = str(args.pack_id).strip()
    name = str(args.name).strip()
    owner = str(args.owner).strip()
    if not re.fullmatch(r"[a-z0-9][a-z0-9-]*", reference_pack_id):
        print("ERROR: --pack-id must be a lowercase slug", file=sys.stderr)
        return 1
    if not name or not owner:
        print("ERROR: --name and --owner must be non-empty", file=sys.stderr)
        return 1
    known_paths = [
        target / "SKILL.md",
        target / "VERSION",
        target / "reference-pack.json",
        target / "asset-ledger.json",
    ]
    conflicts = [path for path in known_paths if path.exists()]
    if conflicts and not args.force:
        print("ERROR: refusing to overwrite existing Reference Pack files:", file=sys.stderr)
        for path in conflicts:
            print(f"  {path}", file=sys.stderr)
        print("Use --force only after reviewing the existing research library.", file=sys.stderr)
        return 1
    if target.exists() and any(target.iterdir()) and args.force:
        suffix = dt.datetime.now(dt.timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
        backup = target.with_name(f"{target.name}.bak.{suffix}")
        shutil.copytree(target, backup, symlinks=True)
        print(f"Backup: {backup}")
    try:
        target.mkdir(parents=True, exist_ok=True)
        ledger = {
            "schema_version": "creative-craft.asset-ledger.v1",
            "project_id": f"reference:{reference_pack_id}",
            "assets": [],
        }
        ledger_path = target / "asset-ledger.json"
        write_atomic(ledger_path, _json_text(ledger))
        manifest = {
            "schema_version": "creative-craft.reference-pack.v1",
            "reference_pack_id": reference_pack_id,
            "name": name,
            "version": "0.1.0",
            "status": "draft",
            "classification": "internal",
            "owner": owner,
            "purpose": "TBD",
            "reviewed_at": None,
            "review_after": None,
            "supersedes": None,
            "entities": [],
            "asset_ledger": {
                "path": "asset-ledger.json",
                "sha256": sha256_file(ledger_path),
            },
            "source_references": [],
        }
        write_atomic(target / "reference-pack.json", _json_text(manifest))
        write_atomic(target / "SKILL.md", _reference_skill_text(reference_pack_id, name))
        write_atomic(target / "VERSION", "0.1.0\n")
        approved_dir = target / "assets" / "approved"
        approved_dir.mkdir(parents=True, exist_ok=True)
        write_atomic(approved_dir / ".gitkeep", "")
        graph = validate_reference_pack(target)
        if not graph.result.ok:
            raise ValueError("; ".join(graph.result.errors))
    except (OSError, ValueError) as exc:
        print(f"ERROR: failed to initialize Reference Pack: {exc}", file=sys.stderr)
        return 1
    print(target)
    return 0


def cmd_validate_reference_pack(args: argparse.Namespace) -> int:
    graph = validate_reference_pack(Path(args.root))
    payload = {
        "root": str(graph.root),
        "manifest": str(graph.manifest_path),
        "reference_pack_id": graph.manifest.get("reference_pack_id"),
        "name": graph.manifest.get("name"),
        "version": graph.manifest.get("version"),
        "status": graph.manifest.get("status"),
        "classification": graph.manifest.get("classification"),
        "valid": graph.result.ok,
        "entity_count": len(graph.manifest.get("entities", [])),
        "asset_count": len(graph.ledger.get("assets", [])),
        "errors": graph.result.errors,
        "warnings": graph.result.warnings,
    }
    if args.json:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        print(f"{'PASS' if graph.result.ok else 'FAIL'} reference pack: {graph.root}")
        print(f"  Pack: {payload['reference_pack_id']}@{payload['version']} ({payload['status']})")
        print(f"  Entities: {payload['entity_count']}")
        print(f"  Assets: {payload['asset_count']}")
        for message in graph.result.errors:
            print(f"  ERROR: {message}")
        for message in graph.result.warnings:
            print(f"  WARN:  {message}")
    return 0 if graph.result.ok else 1


def _copy_snapshot_files(source: BrandPackGraph, target: Path) -> None:
    target.mkdir(parents=True, exist_ok=False)
    relative_files: set[str] = {"brand-pack.json"}
    relative_files.update(
        str(item["path"]) for item in source.manifest.get("authority_files", [])
        if isinstance(item, dict)
    )
    ledger_relative = str(source.manifest.get("asset_ledger", {}).get("path"))
    relative_files.add(ledger_relative)
    for asset in source.ledger.get("assets", []):
        if not isinstance(asset, dict):
            continue
        value = str(asset.get("path_or_uri", ""))
        if not _is_external_asset_uri(value):
            relative_files.add(value)
    for relative in sorted(relative_files):
        source_path, error = _safe_relative_path(source.root, relative, label="snapshot source path")
        if error or source_path is None or not source_path.is_file():
            raise ValueError(error or f"snapshot source file does not exist: {relative!r}")
        destination = target / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source_path, destination)


def _project_ledger_record(graph: ProjectGraph) -> dict[str, Any]:
    records = [record for (kind, _), record in graph.records.items() if kind == "asset-ledger"]
    if len(records) != 1:
        raise ValueError("project must register exactly one project asset ledger")
    return records[0]


def _snapshot_asset_ids(snapshot_path: Path | None) -> set[str]:
    if snapshot_path is None or not snapshot_path.is_dir():
        return set()
    graph = validate_brand_pack(snapshot_path)
    if not graph.result.ok:
        raise ValueError("existing brand snapshot is invalid: " + "; ".join(graph.result.errors))
    return {
        str(item.get("asset_id")) for item in graph.ledger.get("assets", [])
        if isinstance(item, dict)
    }


def _merged_project_ledger(
    project_ledger: dict[str, Any], source: BrandPackGraph, old_asset_ids: set[str]
) -> dict[str, Any]:
    merged = copy.deepcopy(project_ledger)
    existing = [
        item for item in merged.get("assets", [])
        if isinstance(item, dict) and str(item.get("asset_id")) not in old_asset_ids
    ]
    ids = {str(item.get("asset_id")) for item in existing}
    for source_asset in source.ledger.get("assets", []):
        if not isinstance(source_asset, dict):
            continue
        asset = copy.deepcopy(source_asset)
        asset_id = str(asset.get("asset_id"))
        if asset_id in ids:
            raise ValueError(f"brand asset_id collides with a project asset: {asset_id}")
        ids.add(asset_id)
        value = str(asset.get("path_or_uri", ""))
        if not _is_external_asset_uri(value):
            asset["path_or_uri"] = f".creative-craft/brand-snapshot/{Path(value).as_posix()}"
        existing.append(asset)
    merged["assets"] = existing
    return merged


def _backup_brand_state(root: Path, paths: list[Path]) -> tuple[Path, dict[Path, bool]]:
    suffix = dt.datetime.now(dt.timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    backup = root / ".creative-craft" / "brand-backups" / suffix
    backup.mkdir(parents=True, exist_ok=False)
    existed: dict[Path, bool] = {}
    for path in paths:
        path = path.resolve(strict=False)
        present = path.exists()
        existed[path] = present
        if not present:
            continue
        relative = path.relative_to(root)
        destination = backup / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        if path.is_dir():
            shutil.copytree(path, destination)
        else:
            shutil.copy2(path, destination)
    return backup, existed


def _remove_path(path: Path) -> None:
    if path.is_symlink() or path.is_file():
        path.unlink(missing_ok=True)
    elif path.is_dir():
        shutil.rmtree(path)


def _restore_brand_state(
    root: Path, backup: Path, existed: dict[Path, bool]
) -> None:
    for path, was_present in existed.items():
        _remove_path(path)
        if not was_present:
            continue
        source = backup / path.relative_to(root)
        path.parent.mkdir(parents=True, exist_ok=True)
        if source.is_dir():
            shutil.copytree(source, path)
        else:
            shutil.copy2(source, path)


def _brand_source_value(args: argparse.Namespace, name: str) -> Any:
    return getattr(args, name, None)


def _install_brand_snapshot(
    project_root: Path,
    source_root: Path,
    args: argparse.Namespace,
    *,
    require_existing_binding: bool,
    retain_backup: bool,
) -> Path:
    project_root = project_root.resolve()
    graph = validate_project(project_root)
    if not graph.result.ok:
        raise ValueError("project is invalid before Brand Pack update: " + "; ".join(graph.result.errors))
    existing_binding_records = [
        record for (kind, _), record in graph.records.items() if kind == "brand-binding"
    ]
    if require_existing_binding and len(existing_binding_records) != 1:
        raise ValueError("update-brand-snapshot requires exactly one existing brand binding")
    if not require_existing_binding and existing_binding_records:
        raise ValueError("project already has a brand binding; use update-brand-snapshot")

    source = validate_brand_pack(source_root)
    if not source.result.ok:
        raise ValueError("Brand Pack is invalid: " + "; ".join(source.result.errors))
    if source.manifest.get("status") == "revoked":
        raise ValueError("cannot bind a revoked Brand Pack")
    source_uri = _brand_source_value(args, "brand_source_uri")
    source_commit = _brand_source_value(args, "brand_source_commit")
    if source_commit and not source_uri:
        raise ValueError("--brand-source-commit requires --brand-source-uri")
    reason = str(_brand_source_value(args, "reason") or "Initial Brand Pack import").strip()
    imported_by = str(_brand_source_value(args, "imported_by") or "TBD").strip()
    if not reason or not imported_by:
        raise ValueError("reason and imported_by must be non-empty")

    creative_root = project_root / ".creative-craft"
    suffix = dt.datetime.now(dt.timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    staging = creative_root / f".brand-snapshot.staging-{suffix}"
    snapshot_path = creative_root / "brand-snapshot"
    binding_path = creative_root / "brand-binding.json"
    project_brand_path = project_root / "BRAND.md"
    manifest_path = graph.manifest_path
    ledger_record = _project_ledger_record(graph)
    ledger_path = Path(ledger_record["path"])
    old_snapshot = snapshot_path if existing_binding_records else None
    old_asset_ids = _snapshot_asset_ids(old_snapshot)
    previous_binding_id = (
        str(existing_binding_records[0]["data"].get("binding_id"))
        if existing_binding_records else None
    )

    try:
        _copy_snapshot_files(source, staging)
        staged_validation = validate_brand_pack(staging)
        if not staged_validation.result.ok:
            raise ValueError(
                "staged Brand Pack is invalid: "
                + "; ".join(staged_validation.result.errors)
            )
        staged_tree_sha = tree_sha256(staging)
        merged_ledger = _merged_project_ledger(ledger_record["data"], source, old_asset_ids)
        brand_authority = source.authority_paths.get("brand")
        if brand_authority is None:
            raise ValueError("Brand Pack has no brand authority file")
        tracked_paths = [
            snapshot_path, binding_path, project_brand_path, ledger_path, manifest_path
        ]
        backup, existed = _backup_brand_state(project_root, tracked_paths)
    except Exception:
        _remove_path(staging)
        raise
    try:
        _remove_path(snapshot_path)
        staging.replace(snapshot_path)
        shutil.copy2(snapshot_path / brand_authority.relative_to(source.root), project_brand_path)
        write_atomic(ledger_path, _json_text(merged_ledger))
        imported_at = dt.datetime.now(dt.timezone.utc).isoformat().replace("+00:00", "Z")
        binding = {
            "schema_version": "creative-craft.brand-binding.v1",
            "binding_id": (
                f"binding-{graph.manifest.get('project_id')}-{source.manifest.get('brand_id')}-"
                f"{suffix}"
            ),
            "project_id": str(graph.manifest.get("project_id")),
            "brand_id": str(source.manifest.get("brand_id")),
            "pack_id": str(source.manifest.get("pack_id")),
            "pack_version": str(source.manifest.get("version")),
            "source": {
                "repository_or_uri": source_uri,
                "ref": _brand_source_value(args, "brand_source_ref"),
                "commit": source_commit,
                "pack_sha256": sha256_file(snapshot_path / "brand-pack.json"),
            },
            "snapshot": {
                "path": ".creative-craft/brand-snapshot",
                "tree_sha256": staged_tree_sha,
            },
            "project_brand": {
                "path": "BRAND.md",
                "sha256": sha256_file(project_brand_path),
            },
            "imported_at": imported_at,
            "imported_by": imported_by,
            "previous_binding_id": previous_binding_id,
            "reason": reason,
        }
        write_atomic(binding_path, _json_text(binding))

        manifest = copy.deepcopy(graph.manifest)
        manifest["artifacts"] = [
            item for item in manifest.get("artifacts", [])
            if isinstance(item, dict)
            and item.get("artifact_type") not in {"brand-pack", "brand-binding"}
        ]
        for item in manifest["artifacts"]:
            if item.get("artifact_type") == "asset-ledger" and Path(
                str(item.get("path"))
            ) == ledger_path.relative_to(project_root):
                item["sha256"] = sha256_file(ledger_path)
        manifest["artifacts"].extend([
            {
                "artifact_type": "brand-pack",
                "artifact_id": str(source.manifest.get("pack_id")),
                "schema_version": "creative-craft.brand-pack.v1",
                "path": ".creative-craft/brand-snapshot/brand-pack.json",
                "sha256": sha256_file(snapshot_path / "brand-pack.json"),
            },
            {
                "artifact_type": "brand-binding",
                "artifact_id": str(binding["binding_id"]),
                "schema_version": "creative-craft.brand-binding.v1",
                "path": ".creative-craft/brand-binding.json",
                "sha256": sha256_file(binding_path),
            },
        ])
        write_atomic(manifest_path, _json_text(manifest))
        validated = validate_project(project_root)
        if not validated.result.ok:
            raise ValueError("updated project is invalid: " + "; ".join(validated.result.errors))
    except Exception:
        _remove_path(staging)
        _restore_brand_state(project_root, backup, existed)
        raise
    if not retain_backup:
        _remove_path(backup)
        parent = backup.parent
        if parent.is_dir() and not any(parent.iterdir()):
            parent.rmdir()
    return backup


def _copy_reference_snapshot_files(source: ReferencePackGraph, target: Path) -> None:
    target.mkdir(parents=True, exist_ok=False)
    relative_files: set[str] = {"reference-pack.json"}
    ledger_relative = str(source.manifest.get("asset_ledger", {}).get("path"))
    relative_files.add(ledger_relative)
    for asset in source.ledger.get("assets", []):
        if not isinstance(asset, dict):
            continue
        value = str(asset.get("path_or_uri", ""))
        if not _is_external_asset_uri(value):
            relative_files.add(value)
    for relative in sorted(relative_files):
        source_path, error = _safe_relative_path(
            source.root, relative, label="reference snapshot source path"
        )
        if error or source_path is None or not source_path.is_file():
            raise ValueError(
                error or f"reference snapshot source file does not exist: {relative!r}"
            )
        destination = target / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source_path, destination)


def _selected_reference_ids(
    source: ReferencePackGraph, requested: Any
) -> list[str]:
    available = {
        str(entity.get("reference_id"))
        for entity in source.manifest.get("entities", [])
        if isinstance(entity, dict)
    }
    selected = (
        [str(item).strip() for item in requested]
        if isinstance(requested, list) and requested
        else sorted(available)
    )
    if not selected:
        raise ValueError("Reference Pack binding requires at least one reference entity")
    if any(not item for item in selected):
        raise ValueError("--select values must be non-empty")
    if len(selected) != len(set(selected)):
        raise ValueError("--select must not repeat a reference_id")
    unknown = sorted(set(selected).difference(available))
    if unknown:
        raise ValueError("selected reference_id does not exist: " + ", ".join(unknown))
    return selected


def _reference_asset_ids(
    source: ReferencePackGraph, selected_reference_ids: Iterable[str]
) -> set[str]:
    selected = set(selected_reference_ids)
    asset_ids: set[str] = set()
    for entity in source.manifest.get("entities", []):
        if not isinstance(entity, dict) or entity.get("reference_id") not in selected:
            continue
        asset_ids.update(str(item) for item in entity.get("asset_refs", []))
    return asset_ids


def _merged_reference_project_ledger(
    project_ledger: dict[str, Any],
    source: ReferencePackGraph,
    selected_asset_ids: set[str],
    old_asset_ids: set[str],
) -> dict[str, Any]:
    merged = copy.deepcopy(project_ledger)
    existing = [
        item
        for item in merged.get("assets", [])
        if isinstance(item, dict) and str(item.get("asset_id")) not in old_asset_ids
    ]
    ids = {str(item.get("asset_id")) for item in existing}
    pack_id = str(source.manifest.get("reference_pack_id"))
    source_assets = {
        str(item.get("asset_id")): item
        for item in source.ledger.get("assets", [])
        if isinstance(item, dict)
    }
    for asset_id in sorted(selected_asset_ids):
        source_asset = source_assets.get(asset_id)
        if source_asset is None:
            raise ValueError(f"selected reference asset does not exist: {asset_id}")
        if asset_id in ids:
            raise ValueError(
                f"reference asset_id collides with a project or another pack asset: {asset_id}"
            )
        ids.add(asset_id)
        asset = copy.deepcopy(source_asset)
        value = str(asset.get("path_or_uri", ""))
        if not _is_external_asset_uri(value):
            asset["path_or_uri"] = (
                f".creative-craft/reference-snapshots/{pack_id}/{Path(value).as_posix()}"
            )
        existing.append(asset)
    merged["assets"] = existing
    return merged


def _backup_reference_state(
    root: Path, reference_pack_id: str, paths: list[Path]
) -> tuple[Path, dict[Path, bool]]:
    suffix = dt.datetime.now(dt.timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    backup = (
        root
        / ".creative-craft"
        / "reference-backups"
        / reference_pack_id
        / suffix
    )
    backup.mkdir(parents=True, exist_ok=False)
    existed: dict[Path, bool] = {}
    for path in paths:
        resolved = path.resolve(strict=False)
        present = resolved.exists()
        existed[resolved] = present
        if not present:
            continue
        relative = resolved.relative_to(root)
        destination = backup / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        if resolved.is_dir():
            shutil.copytree(resolved, destination)
        else:
            shutil.copy2(resolved, destination)
    return backup, existed


def _existing_reference_binding(
    graph: ProjectGraph, reference_pack_id: str
) -> dict[str, Any] | None:
    matches = [
        record
        for (kind, _), record in graph.records.items()
        if kind == "reference-binding"
        and record["data"].get("reference_pack_id") == reference_pack_id
    ]
    if len(matches) > 1:
        raise ValueError(
            f"project has multiple bindings for Reference Pack {reference_pack_id!r}"
        )
    return matches[0] if matches else None


def _install_reference_snapshot(
    project_root: Path,
    source_root: Path,
    args: argparse.Namespace,
    *,
    require_existing_binding: bool,
    retain_backup: bool,
) -> Path:
    project_root = project_root.resolve()
    graph = validate_project(project_root)
    if not graph.result.ok:
        raise ValueError(
            "project is invalid before Reference Pack update: "
            + "; ".join(graph.result.errors)
        )
    source = validate_reference_pack(source_root)
    if not source.result.ok:
        raise ValueError("Reference Pack is invalid: " + "; ".join(source.result.errors))
    if source.manifest.get("status") == "revoked":
        raise ValueError("cannot bind a revoked Reference Pack")

    reference_pack_id = str(source.manifest.get("reference_pack_id"))
    existing_binding = _existing_reference_binding(graph, reference_pack_id)
    if require_existing_binding and existing_binding is None:
        raise ValueError(
            "update-reference-snapshot requires an existing binding for "
            f"{reference_pack_id!r}"
        )
    if not require_existing_binding and existing_binding is not None:
        raise ValueError(
            f"project already binds {reference_pack_id!r}; use update-reference-snapshot"
        )

    source_uri = getattr(args, "reference_source_uri", None)
    source_commit = getattr(args, "reference_source_commit", None)
    if source_commit and not source_uri:
        raise ValueError("--reference-source-commit requires --reference-source-uri")
    reason = str(
        getattr(args, "reason", None) or "Initial Reference Pack import"
    ).strip()
    imported_by = str(getattr(args, "imported_by", None) or "TBD").strip()
    if not reason or not imported_by:
        raise ValueError("reason and imported_by must be non-empty")
    selected_ids = _selected_reference_ids(source, getattr(args, "select", None))
    selected_asset_ids = _reference_asset_ids(source, selected_ids)

    creative_root = project_root / ".creative-craft"
    suffix = dt.datetime.now(dt.timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    snapshot_parent = creative_root / "reference-snapshots"
    staging = snapshot_parent / f".{reference_pack_id}.staging-{suffix}"
    snapshot_path = snapshot_parent / reference_pack_id
    binding_path = (
        creative_root / "reference-bindings" / f"{reference_pack_id}.json"
    )
    manifest_path = graph.manifest_path
    ledger_record = _project_ledger_record(graph)
    ledger_path = Path(ledger_record["path"])
    old_asset_ids: set[str] = set()
    previous_binding_id: str | None = None
    if existing_binding is not None:
        previous_binding_id = str(existing_binding["data"].get("binding_id"))
        old_snapshot = validate_reference_pack(snapshot_path)
        if not old_snapshot.result.ok:
            raise ValueError(
                "existing Reference Pack snapshot is invalid: "
                + "; ".join(old_snapshot.result.errors)
            )
        old_asset_ids = _reference_asset_ids(
            old_snapshot, existing_binding["data"].get("selected_reference_ids", [])
        )

    try:
        _copy_reference_snapshot_files(source, staging)
        staged_validation = validate_reference_pack(staging)
        if not staged_validation.result.ok:
            raise ValueError(
                "staged Reference Pack is invalid: "
                + "; ".join(staged_validation.result.errors)
            )
        staged_tree_sha = tree_sha256(staging)
        merged_ledger = _merged_reference_project_ledger(
            ledger_record["data"], source, selected_asset_ids, old_asset_ids
        )
        tracked_paths = [snapshot_path, binding_path, ledger_path, manifest_path]
        backup, existed = _backup_reference_state(
            project_root, reference_pack_id, tracked_paths
        )
    except Exception:
        _remove_path(staging)
        raise

    try:
        _remove_path(snapshot_path)
        snapshot_path.parent.mkdir(parents=True, exist_ok=True)
        staging.replace(snapshot_path)
        write_atomic(ledger_path, _json_text(merged_ledger))
        imported_at = dt.datetime.now(dt.timezone.utc).isoformat().replace("+00:00", "Z")
        binding = {
            "schema_version": "creative-craft.reference-binding.v1",
            "binding_id": (
                f"reference-binding-{graph.manifest.get('project_id')}-"
                f"{reference_pack_id}-{suffix}"
            ),
            "project_id": str(graph.manifest.get("project_id")),
            "reference_pack_id": reference_pack_id,
            "pack_version": str(source.manifest.get("version")),
            "source": {
                "repository_or_uri": source_uri,
                "ref": getattr(args, "reference_source_ref", None),
                "commit": source_commit,
                "pack_sha256": sha256_file(snapshot_path / "reference-pack.json"),
            },
            "snapshot": {
                "path": f".creative-craft/reference-snapshots/{reference_pack_id}",
                "tree_sha256": staged_tree_sha,
            },
            "selected_reference_ids": selected_ids,
            "imported_at": imported_at,
            "imported_by": imported_by,
            "previous_binding_id": previous_binding_id,
            "reason": reason,
        }
        write_atomic(binding_path, _json_text(binding))

        relative_binding_path = binding_path.relative_to(project_root).as_posix()
        manifest = copy.deepcopy(graph.manifest)
        manifest["artifacts"] = [
            item
            for item in manifest.get("artifacts", [])
            if isinstance(item, dict)
            and not (
                item.get("artifact_type") == "reference-pack"
                and item.get("artifact_id") == reference_pack_id
            )
            and not (
                item.get("artifact_type") == "reference-binding"
                and (
                    item.get("artifact_id") == previous_binding_id
                    or item.get("path") == relative_binding_path
                )
            )
        ]
        for item in manifest["artifacts"]:
            if item.get("artifact_type") == "asset-ledger" and Path(
                str(item.get("path"))
            ) == ledger_path.relative_to(project_root):
                item["sha256"] = sha256_file(ledger_path)
        manifest["artifacts"].extend(
            [
                {
                    "artifact_type": "reference-pack",
                    "artifact_id": reference_pack_id,
                    "schema_version": "creative-craft.reference-pack.v1",
                    "path": (
                        f".creative-craft/reference-snapshots/{reference_pack_id}/"
                        "reference-pack.json"
                    ),
                    "sha256": sha256_file(snapshot_path / "reference-pack.json"),
                },
                {
                    "artifact_type": "reference-binding",
                    "artifact_id": str(binding["binding_id"]),
                    "schema_version": "creative-craft.reference-binding.v1",
                    "path": relative_binding_path,
                    "sha256": sha256_file(binding_path),
                },
            ]
        )
        write_atomic(manifest_path, _json_text(manifest))
        validated = validate_project(project_root)
        if not validated.result.ok:
            raise ValueError(
                "updated project is invalid: " + "; ".join(validated.result.errors)
            )
    except Exception:
        _remove_path(staging)
        _restore_brand_state(project_root, backup, existed)
        raise

    if not retain_backup:
        _remove_path(backup)
        parent = backup.parent
        while parent != creative_root and parent.is_dir() and not any(parent.iterdir()):
            parent.rmdir()
            parent = parent.parent
    return backup


def cmd_bind_reference_pack(args: argparse.Namespace) -> int:
    try:
        _install_reference_snapshot(
            Path(args.target).expanduser(),
            Path(args.reference_pack).expanduser(),
            args,
            require_existing_binding=False,
            retain_backup=False,
        )
    except (OSError, ValueError) as exc:
        print(f"ERROR: failed to bind Reference Pack: {exc}", file=sys.stderr)
        return 1
    reference_pack_id = load_json(
        Path(args.reference_pack).expanduser().resolve() / "reference-pack.json"
    )["reference_pack_id"]
    print(
        Path(args.target).expanduser().resolve()
        / ".creative-craft"
        / "reference-bindings"
        / f"{reference_pack_id}.json"
    )
    return 0


def cmd_update_reference_snapshot(args: argparse.Namespace) -> int:
    try:
        backup = _install_reference_snapshot(
            Path(args.target).expanduser(),
            Path(args.reference_pack).expanduser(),
            args,
            require_existing_binding=True,
            retain_backup=True,
        )
    except (OSError, ValueError) as exc:
        print(f"ERROR: failed to update Reference Pack snapshot: {exc}", file=sys.stderr)
        return 1
    reference_pack_id = load_json(
        Path(args.reference_pack).expanduser().resolve() / "reference-pack.json"
    )["reference_pack_id"]
    print(f"Backup: {backup}")
    print(
        Path(args.target).expanduser().resolve()
        / ".creative-craft"
        / "reference-bindings"
        / f"{reference_pack_id}.json"
    )
    return 0


def cmd_seed(args: argparse.Namespace) -> int:
    target = Path(args.target).expanduser().resolve()
    brand_pack = getattr(args, "brand_pack", None)
    if brand_pack:
        source = validate_brand_pack(Path(str(brand_pack)).expanduser())
        if not source.result.ok:
            print(
                "ERROR: Brand Pack is invalid: " + "; ".join(source.result.errors),
                file=sys.stderr,
            )
            return 1
        if source.manifest.get("status") == "revoked":
            print("ERROR: cannot bind a revoked Brand Pack", file=sys.stderr)
            return 1
        if getattr(args, "brand_source_commit", None) and not getattr(
            args, "brand_source_uri", None
        ):
            print("ERROR: --brand-source-commit requires --brand-source-uri", file=sys.stderr)
            return 1
    target.mkdir(parents=True, exist_ok=True)
    copies: dict[Path, Path] = {
        TEMPLATES_DIR / "CREATIVE.md": target / "CREATIVE.md",
        TEMPLATES_DIR / "DELIVERABLES.md": target / "DELIVERABLES.md",
    }
    if not brand_pack:
        copies[TEMPLATES_DIR / "BRAND.md"] = target / "BRAND.md"
    for schema_version, entry in ARTIFACT_REGISTRY.items():
        template = entry.get("template")
        if template and schema_version in PROJECT_SEED_SCHEMA_VERSIONS:
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
    fallback_ids = {
        "asset-ledger": "asset-ledger-tbd",
        "concept-routes": "routes-tbd",
    }
    for schema_version, entry in ARTIFACT_REGISTRY.items():
        template = entry.get("template")
        artifact_type = str(entry["kind"])
        if not template or schema_version not in PROJECT_MANIFEST_SEED_SCHEMA_VERSIONS:
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
    if brand_pack:
        try:
            _install_brand_snapshot(
                target,
                Path(str(brand_pack)).expanduser(),
                args,
                require_existing_binding=False,
                retain_backup=False,
            )
        except (OSError, ValueError) as exc:
            print(f"ERROR: failed to bind Brand Pack: {exc}", file=sys.stderr)
            return 1
    return 0


def cmd_update_brand_snapshot(args: argparse.Namespace) -> int:
    try:
        backup = _install_brand_snapshot(
            Path(args.target).expanduser(),
            Path(args.brand_pack).expanduser(),
            args,
            require_existing_binding=True,
            retain_backup=True,
        )
    except (OSError, ValueError) as exc:
        print(f"ERROR: failed to update Brand Pack snapshot: {exc}", file=sys.stderr)
        return 1
    print(f"Backup: {backup}")
    print(Path(args.target).expanduser().resolve() / ".creative-craft" / "brand-binding.json")
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

    init_brand_parser = sub.add_parser(
        "init-brand-pack", help="initialize a private draft Brand Skill authority pack"
    )
    init_brand_parser.add_argument("--target", required=True)
    init_brand_parser.add_argument("--brand-id", required=True)
    init_brand_parser.add_argument("--brand-name", required=True)
    init_brand_parser.add_argument("--owner", required=True)
    init_brand_parser.add_argument("--force", action="store_true")
    init_brand_parser.set_defaults(func=cmd_init_brand_pack)

    validate_brand_parser = sub.add_parser(
        "validate-brand-pack", help="validate Brand Pack authority, files, digests, and rights"
    )
    validate_brand_parser.add_argument("--root", required=True)
    validate_brand_parser.add_argument("--json", action="store_true")
    validate_brand_parser.set_defaults(func=cmd_validate_brand_pack)

    init_reference_parser = sub.add_parser(
        "init-reference-pack",
        help="initialize a private draft non-authoritative creative Reference Pack",
    )
    init_reference_parser.add_argument("--target", required=True)
    init_reference_parser.add_argument("--pack-id", required=True)
    init_reference_parser.add_argument("--name", required=True)
    init_reference_parser.add_argument("--owner", required=True)
    init_reference_parser.add_argument("--force", action="store_true")
    init_reference_parser.set_defaults(func=cmd_init_reference_pack)

    validate_reference_parser = sub.add_parser(
        "validate-reference-pack",
        help="validate Reference Pack evidence, files, digests, and input rights",
    )
    validate_reference_parser.add_argument("--root", required=True)
    validate_reference_parser.add_argument("--json", action="store_true")
    validate_reference_parser.set_defaults(func=cmd_validate_reference_pack)

    seed_parser = sub.add_parser("seed", help="seed authority and job templates into a project")
    seed_parser.add_argument("--target", required=True)
    seed_parser.add_argument("--brand-pack")
    seed_parser.add_argument("--brand-source-uri")
    seed_parser.add_argument("--brand-source-ref")
    seed_parser.add_argument("--brand-source-commit")
    seed_parser.add_argument("--imported-by", default="TBD")
    seed_parser.add_argument("--force", action="store_true")
    seed_parser.set_defaults(func=cmd_seed)

    update_brand_parser = sub.add_parser(
        "update-brand-snapshot",
        help="replace a project Brand Pack snapshot with backup, lineage, and rollback",
    )
    update_brand_parser.add_argument("--target", required=True)
    update_brand_parser.add_argument("--brand-pack", required=True)
    update_brand_parser.add_argument("--reason", required=True)
    update_brand_parser.add_argument("--brand-source-uri")
    update_brand_parser.add_argument("--brand-source-ref")
    update_brand_parser.add_argument("--brand-source-commit")
    update_brand_parser.add_argument("--imported-by", default="TBD")
    update_brand_parser.set_defaults(func=cmd_update_brand_snapshot)

    bind_reference_parser = sub.add_parser(
        "bind-reference-pack",
        help="add an immutable Reference Pack snapshot without changing brand authority",
    )
    bind_reference_parser.add_argument("--target", required=True)
    bind_reference_parser.add_argument("--reference-pack", required=True)
    bind_reference_parser.add_argument("--select", action="append")
    bind_reference_parser.add_argument("--reference-source-uri")
    bind_reference_parser.add_argument("--reference-source-ref")
    bind_reference_parser.add_argument("--reference-source-commit")
    bind_reference_parser.add_argument("--imported-by", default="TBD")
    bind_reference_parser.add_argument("--reason")
    bind_reference_parser.set_defaults(func=cmd_bind_reference_pack)

    update_reference_parser = sub.add_parser(
        "update-reference-snapshot",
        help="replace one Reference Pack snapshot with backup, lineage, and rollback",
    )
    update_reference_parser.add_argument("--target", required=True)
    update_reference_parser.add_argument("--reference-pack", required=True)
    update_reference_parser.add_argument("--select", action="append")
    update_reference_parser.add_argument("--reference-source-uri")
    update_reference_parser.add_argument("--reference-source-ref")
    update_reference_parser.add_argument("--reference-source-commit")
    update_reference_parser.add_argument("--imported-by", default="TBD")
    update_reference_parser.add_argument("--reason", required=True)
    update_reference_parser.set_defaults(func=cmd_update_reference_snapshot)

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
