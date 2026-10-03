# Codex adapter

Codex is a Tier 1 host. The repository exposes `./skills/` through
`.codex-plugin/plugin.json`; the canonical runtime remains
`../../skills/creative-craft/`.

Use Codex's built-in `skill-installer` with repository
`bigKING67/creative-craft`, ref `v0.3.0`, and path `skills/creative-craft`, or:

```bash
python3 ~/.codex/skills/.system/skill-installer/scripts/install-skill-from-github.py \
  --repo bigKING67/creative-craft \
  --ref v0.3.0 \
  --path skills/creative-craft
```

`v0.3.0` is the latest published immutable tag. The installed Skill becomes
discoverable on the next turn or session.

For a local multi-host setup whose Codex runtime discovers the shared Agents
Skill root, a repository candidate can instead be installed once for Codex and
Grok:

```bash
python3 scripts/install_skill.py --target ~/.agents/skills
```

Treat this as a candidate install until its provenance resolves to a published
immutable tag. Verify Codex discovery on the next turn or session rather than
inferring it from a successful file copy.

Provider execution still depends on available host tools and explicit
authorization; Creative Craft itself includes no network adapter.

Diagnose the installed leaf runtime without repository-only files:

```bash
python3 ~/.codex/skills/creative-craft/scripts/creative_craft.py self-test --json
```

For the shared installation, run:

```bash
python3 ~/.agents/skills/creative-craft/scripts/creative_craft.py self-test --json
```
