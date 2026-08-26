# Pi adapter

Pi is a Tier 1 host. `package.json.pi.skills` points to the canonical runtime;
the adapter does not copy or fork core rules.

Install the immutable GitHub release globally or for one project:

```bash
pi install git:github.com/bigKING67/creative-craft@v0.3.0
pi install -l git:github.com/bigKING67/creative-craft@v0.3.0
```

These commands remain pinned to the latest published immutable tag. Pi package
discovery and installed-runtime behavior are covered by the release gates.

Validate discovery with `pi list`, then run the installed
`skills/creative-craft/scripts/creative_craft.py self-test --json` command when
diagnosing a package copy. No npm registry package is published.
