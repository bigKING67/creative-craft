# Pi adapter

Pi is a Tier 1 host. `package.json.pi.skills` points to the canonical runtime;
the adapter does not copy or fork core rules.

Install the immutable GitHub release globally or for one project:

```bash
pi install git:github.com/bigKING67/creative-craft@v0.2.6
pi install -l git:github.com/bigKING67/creative-craft@v0.2.6
```

These commands remain pinned to the latest published tag. The repository's
`0.3.0` source state is an unreleased candidate and is not claimed as a Pi
release.

Validate discovery with `pi list`, then run the installed
`skills/creative-craft/scripts/creative_craft.py self-test --json` command when
diagnosing a package copy. No npm registry package is published.
