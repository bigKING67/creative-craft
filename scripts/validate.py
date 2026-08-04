#!/usr/bin/env python3
"""Run Creative Craft's portable source, artifact, and unit-test gates."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CLI = ROOT / "skills" / "creative-craft" / "scripts" / "creative_craft.py"


def run(*args: str) -> None:
    subprocess.run([sys.executable, *args], cwd=ROOT, check=True)


def main() -> int:
    run(str(CLI), "doctor")
    run(str(CLI), "validate-project", "--root", str(ROOT / "examples/premium-haircare-launch"))

    artifact_dirs = [
        ROOT / "skills" / "creative-craft" / "templates",
        ROOT / "examples",
        ROOT / "tests" / "fixtures",
    ]
    for directory in artifact_dirs:
        for path in sorted(directory.rglob("*.json")):
            # Provider profiles and source locks are repository metadata, not job artifacts.
            if "providers" in path.parts or path.name == "sources.lock.json":
                continue
            run(str(CLI), "validate", "--file", str(path))

    run("-m", "unittest", "discover", "-s", "tests", "-p", "test_*.py")
    print("Creative Craft validation passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
