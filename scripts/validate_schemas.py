#!/usr/bin/env python3
"""Validate Creative Craft JSON Schemas and all versioned sample artifacts."""

from __future__ import annotations

import copy
import importlib.util
import json
import sys
from pathlib import Path
from typing import Any

try:
    from jsonschema import Draft202012Validator
except ImportError:
    print(
        "ERROR: jsonschema is required. Run: python -m pip install -r requirements-dev.txt",
        file=sys.stderr,
    )
    raise SystemExit(2)

ROOT = Path(__file__).resolve().parents[1]
SCHEMA_DIR = ROOT / "skills" / "creative-craft" / "schemas"
ARTIFACT_ROOTS = (
    ROOT / "skills" / "creative-craft" / "templates",
    ROOT / "examples",
    ROOT / "tests" / "fixtures",
)
METADATA_PATHS = (
    ROOT / "sources.lock.json",
    *sorted((ROOT / "skills" / "creative-craft" / "providers").glob("*.json")),
    *sorted((ROOT / "skills" / "creative-craft" / "providers" / "surfaces").glob("*.json")),
)
CLI_PATH = ROOT / "skills" / "creative-craft" / "scripts" / "creative_craft.py"


def load_object(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError(
            f"invalid JSON in {path.relative_to(ROOT)} at "
            f"line {exc.lineno}, column {exc.colno}: {exc.msg}"
        ) from exc
    if not isinstance(value, dict):
        raise ValueError(  # noqa: TRY004
            f"top-level JSON must be an object: {path.relative_to(ROOT)}"
        )
    return value


def main() -> int:
    validators: dict[str, tuple[Path, Draft202012Validator]] = {}
    errors: list[str] = []

    for path in sorted(SCHEMA_DIR.glob("*.json")):
        try:
            schema = load_object(path)
            Draft202012Validator.check_schema(schema)
            schema_version = (
                schema.get("properties", {})
                .get("schema_version", {})
                .get("const")
            )
            if not isinstance(schema_version, str) or not schema_version:
                raise ValueError(
                    f"schema_version.const is missing: {path.relative_to(ROOT)}"
                )
            if schema_version in validators:
                prior = validators[schema_version][0].relative_to(ROOT)
                raise ValueError(
                    f"duplicate schema_version {schema_version!r}: "
                    f"{prior} and {path.relative_to(ROOT)}"
                )
            validators[schema_version] = (path, Draft202012Validator(schema))
        except Exception as exc:  # noqa: BLE001 - jsonschema exposes multiple schema errors.
            errors.append(str(exc))

    validated = 0
    for directory in ARTIFACT_ROOTS:
        for path in sorted(directory.rglob("*.json")):
            try:
                artifact = load_object(path)
                schema_version = artifact.get("schema_version")
                if schema_version not in validators:
                    raise ValueError(
                        f"no JSON Schema for {path.relative_to(ROOT)}: "
                        f"{schema_version!r}"
                    )
                schema_path, validator = validators[str(schema_version)]
                validation_errors = sorted(
                    validator.iter_errors(artifact),
                    key=lambda error: [str(part) for part in error.absolute_path],
                )
                for error in validation_errors:
                    location = ".".join(str(part) for part in error.absolute_path) or "<root>"
                    errors.append(
                        f"{path.relative_to(ROOT)} [{location}] against "
                        f"{schema_path.name}: {error.message}"
                    )
                if not validation_errors:
                    validated += 1
            except ValueError as exc:
                errors.append(str(exc))

    for path in METADATA_PATHS:
        try:
            artifact = load_object(path)
            schema_version = artifact.get("schema_version")
            if schema_version not in validators:
                raise ValueError(
                    f"no JSON Schema for {path.relative_to(ROOT)}: {schema_version!r}"
                )
            schema_path, validator = validators[str(schema_version)]
            validation_errors = list(validator.iter_errors(artifact))
            for error in validation_errors:
                location = ".".join(str(part) for part in error.absolute_path) or "<root>"
                errors.append(
                    f"{path.relative_to(ROOT)} [{location}] against {schema_path.name}: {error.message}"
                )
            if not validation_errors:
                validated += 1
        except ValueError as exc:
            errors.append(str(exc))

    spec = importlib.util.spec_from_file_location("creative_craft_schema_runtime", CLI_PATH)
    if spec is None or spec.loader is None:
        errors.append("cannot import Creative Craft runtime for schema parity")
    else:
        runtime = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = runtime
        spec.loader.exec_module(runtime)
        parity_cases = 0
        specimen_paths = list(METADATA_PATHS)
        for directory in ARTIFACT_ROOTS:
            specimen_paths.extend(sorted(directory.rglob("*.json")))
        specimens: dict[str, Path] = {}
        for path in specimen_paths:
            artifact = load_object(path)
            specimens.setdefault(str(artifact.get("schema_version")), path)
        missing_specimens = sorted(set(validators).difference(specimens))
        for schema_version in missing_specimens:
            errors.append(f"no parity specimen for schema_version {schema_version}")
        for schema_version, path in sorted(specimens.items()):
            artifact = load_object(path)
            schema_path, reference = validators[schema_version]
            schema = load_object(schema_path)
            required = schema.get("required", [])
            mutations: list[dict[str, Any]] = [copy.deepcopy(artifact)]
            unexpected = copy.deepcopy(artifact)
            unexpected["unexpected_field"] = True
            mutations.append(unexpected)
            if required:
                missing = copy.deepcopy(artifact)
                missing.pop(str(required[0]), None)
                mutations.append(missing)
            wrong_version = copy.deepcopy(artifact)
            wrong_version["schema_version"] = "creative-craft.invalid.v0"
            mutations.append(wrong_version)
            for index, mutation in enumerate(mutations):
                reference_valid = not list(reference.iter_errors(mutation))
                runtime_valid = runtime.validate_against_schema(mutation, schema_path).ok
                if reference_valid != runtime_valid:
                    errors.append(
                        f"schema parity mismatch for {path.relative_to(ROOT)} mutation {index}: "
                        f"jsonschema={reference_valid}, runtime={runtime_valid}"
                    )
                parity_cases += 1

    if errors:
        print("JSON Schema validation failed:")
        for message in errors:
            print(f"  ERROR: {message}")
        return 1

    print(
        f"JSON Schema validation passed: {len(validators)} schemas; "
        f"{validated} artifacts; {parity_cases} parity cases."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
