#!/usr/bin/env python3
"""Verify GitHub package discovery contracts for Pi and Codex-compatible hosts."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", default=str(ROOT))
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    root = Path(args.root).resolve()
    errors: list[str] = []
    checks: list[str] = []

    package = json.loads((root / "package.json").read_text(encoding="utf-8"))
    pi_skills = package.get("pi", {}).get("skills", [])
    if pi_skills != ["skills/creative-craft"]:
        errors.append("package.json pi.skills must contain only skills/creative-craft")
    else:
        checks.append("pi-package-discovery")
    if package.get("private") is not True:
        errors.append("package.json must remain private because npm distribution is unsupported")
    else:
        checks.append("github-only-distribution")

    plugin = json.loads((root / ".codex-plugin/plugin.json").read_text(encoding="utf-8"))
    skill_pointer = plugin.get("skills")
    if skill_pointer != "./skills/":
        errors.append(".codex-plugin/plugin.json skills must equal ./skills/")
    elif not (root / str(skill_pointer) / "creative-craft/SKILL.md").is_file():
        errors.append("Codex plugin skill pointer does not resolve to creative-craft/SKILL.md")
    else:
        checks.append("codex-plugin-discovery")

    with tempfile.TemporaryDirectory() as directory:
        completed = subprocess.run(
            [
                sys.executable,
                str(root / "scripts/install_skill.py"),
                "--target",
                directory,
            ],
            cwd=root,
            text=True,
            capture_output=True,
            check=False,
        )
        installed = Path(directory) / "creative-craft"
        if completed.returncode != 0:
            errors.append(f"atomic installer failed: {completed.stderr.strip()}")
        elif not (installed / "INSTALL_PROVENANCE.json").is_file():
            errors.append("atomic installer did not write INSTALL_PROVENANCE.json")
        else:
            checks.append("atomic-skill-install")
        if installed.is_dir():
            validation = subprocess.run(
                [
                    sys.executable,
                    str(installed / "scripts/creative_craft.py"),
                    "validate",
                    "--file",
                    str(installed / "templates/image-job.json"),
                ],
                text=True,
                capture_output=True,
                check=False,
            )
            if validation.returncode != 0:
                errors.append(f"installed runtime validation failed: {validation.stdout.strip()}")
            else:
                checks.append("installed-runtime")

    payload = {"valid": not errors, "checks": checks, "errors": errors}
    if args.json:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        print("PASS host package smoke" if not errors else "FAIL host package smoke")
        for check in checks:
            print(f"  PASS: {check}")
        for error in errors:
            print(f"  ERROR: {error}")
    return 0 if not errors else 1


if __name__ == "__main__":
    raise SystemExit(main())
