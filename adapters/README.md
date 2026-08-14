# Host adapters

`skills/creative-craft/` is the canonical runtime.

Host adapters may add installation notes, tool routing, or host-specific
execution, but they must not fork the skill's professional rules.

Tier 1 in `0.2.0` means package/discovery and isolated installation are tested
for Pi and Codex. Claude and Cursor adapters remain documentation-only and must
not be described as runtime-verified.

The repository currently contains an unreleased `0.3.0` candidate. Its local
source/package gates do not change the published `v0.2.6` install baseline or
upgrade any host to remotely verified `0.3.0` support.

A host adapter should declare:

- supported host/version;
- installation target;
- available image/video tools;
- whether network and cost-bearing actions require confirmation;
- artifact locations;
- unsupported capabilities;
- validation performed.

Use the generic installer with an explicit destination:

```bash
python3 scripts/install_skill.py --target /path/to/host/skills
```

The installer uses same-filesystem staging, validates the copied runtime,
writes install provenance, atomically replaces the destination, and retains a
backup during `--force` upgrades.

Do not hardcode private home directories or copy unrelated host state.
