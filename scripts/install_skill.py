#!/usr/bin/env python3
"""Install the canonical Creative Craft skill into an explicit skills directory."""

from __future__ import annotations

import argparse
import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "skills" / "creative-craft"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--target", required=True,
                        help="Host skills directory; creative-craft/ will be created inside it.")
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()

    target_root = Path(args.target).expanduser().resolve()
    destination = target_root / "creative-craft"
    if destination.exists():
        if not args.force:
            parser.error(f"destination exists: {destination}; use --force after review")
        shutil.rmtree(destination)
    target_root.mkdir(parents=True, exist_ok=True)
    shutil.copytree(SOURCE, destination, ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
    print(destination)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
