# Host adapters

`skills/creative-craft/` is the canonical runtime.

Host adapters may add installation notes, tool routing, or host-specific
execution, but they must not fork the skill's professional rules.

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

Do not hardcode private home directories or copy unrelated host state.
