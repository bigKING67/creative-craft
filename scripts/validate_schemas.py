#!/usr/bin/env python3
"""Validate Creative Craft JSON Schemas and all versioned sample artifacts."""

from __future__ import annotations

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
)


def load_object(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError(
            f"invalid JSON in {path.relative_to(ROOT)} at "
            f"line {exc.lineno}, column {exc.colno}: {exc.msg}"
        ) from exc
    if not isinstance(value, dict):
        raise ValueError(f"top-level JSON must be an object: {path.relative_to(ROOT)}")
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
        except Exception as exc:  # jsonschema exposes several schema error types.
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

    if errors:
        print("JSON Schema validation failed:")
        for message in errors:
            print(f"  ERROR: {message}")
        return 1

    print(
        f"JSON Schema validation passed: {len(validators)} schemas; "
        f"{validated} artifacts."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
