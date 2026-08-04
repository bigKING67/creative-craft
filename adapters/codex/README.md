# Codex adapter

Codex is a Tier 1 host. The repository exposes `./skills/` through
`.codex-plugin/plugin.json`; the canonical runtime remains
`../../skills/creative-craft/`.

Use Codex's built-in `skill-installer` with repository
`bigKING67/creative-craft`, ref `v0.2.1`, and path `skills/creative-craft`, or:

```bash
python3 ~/.codex/skills/.system/skill-installer/scripts/install-skill-from-github.py \
  --repo bigKING67/creative-craft \
  --ref v0.2.1 \
  --path skills/creative-craft
```

The installed skill becomes discoverable on the next turn/session. Provider
execution still depends on available host tools and explicit authorization;
Creative Craft itself includes no network adapter.

Diagnose the installed leaf runtime without repository-only files:

```bash
python3 ~/.codex/skills/creative-craft/scripts/creative_craft.py self-test --json
```
