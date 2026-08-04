# creative-craft

Creative strategy, direction, generative image and video production,
evaluation, iteration, and delivery governance for real creative work.

```text
context -> routes -> direction -> production -> evaluation -> delivery -> learning
```

> 中文定位：面向真实创意任务的创意策略、创意导演、生成式图像与视频生产、评估迭代和交付治理系统。

Creative Craft is not a prompt collection. It turns a vague idea, an incomplete
brief, or an existing asset into an explicit creative system:

- what the work must achieve;
- who it is for and what tension it should unlock;
- which genuinely different creative routes are worth pursuing;
- how the selected route should look, move, sound, and communicate;
- how to produce image and video assets with provider-aware execution packs;
- what was observed, inferred, hypothesized, accepted, rejected, or left unknown;
- how variants are evaluated, refined, adapted, packaged, and learned from.

## Status

Version `0.2.0` is the evidence-bound production-contract release. It adds a
content-bound project manifest, formal creative direction, v2 image/video jobs,
execution receipts, output inspections, revision lineage, derived lifecycle
status, cross-artifact validation, evidence-strength scoring, execution-surface
profiles, atomic installation, and real CI.

The package deliberately does **not** make network calls or incur generation
costs. It prepares and validates production jobs. Direct provider adapters are
separate, opt-in roadmap items so the creative method remains portable and
provider changes do not destabilize the core.

## Product boundary

Use Creative Craft for:

- creative briefs, campaign territories, concepts, big ideas, hooks, and
  communication systems;
- art direction, visual worlds, copy hierarchy, narrative structures, motion
  language, sound direction, treatments, storyboards, and shot plans;
- generation and editing plans for images, especially OpenAI GPT Image 2;
- generation, reference, extension, and editing plans for video, especially
  ByteDance Seedance;
- analysis and critique of existing images, videos, campaigns, moodboards,
  scripts, storyboards, and prompt packs;
- controlled iteration, channel adaptation, delivery specifications, asset
  provenance, and creative learning.

Do not use Creative Craft as a replacement for:

- `design-craft` when the target is product UI/UX, interaction design, design
  systems, frontend implementation, or product presentation quality;
- `review-craft` when the target is software engineering quality;
- media-buying attribution, legal advice, model safety bypassing, deepfake
  impersonation, or unlicensed use of third-party likeness, brands, music, or
  copyrighted material;
- a full nonlinear editor, compositing suite, color-grading tool, DAM, or
  production management system.

## What makes it different

Creative Craft requires:

1. **Authority before aesthetics.** `BRAND.md`, `CREATIVE.md`, source assets,
   rights, channel constraints, and live output evidence outrank generic taste.
2. **Strategy before style.** Objective, audience, tension, insight,
   proposition, and desired response are separated from execution.
3. **Distinct routes, not cosmetic variants.** Concepts must differ in creative
   mechanism, not merely color, camera, or art style.
4. **Model-agnostic core, provider-specific execution.** Current capabilities
   live in dated provider profiles instead of leaking into timeless rules.
5. **Reference roles.** Every reference states what it controls: identity,
   geometry, composition, lighting, material, motion, sound, typography, or
   continuity.
6. **Change/preserve contracts.** Editing instructions explicitly separate what
   may change from what must remain invariant.
7. **Evidence-aware critique.** Observation, interpretation, performance
   hypothesis, decision, and remaining unknowns are never collapsed together.
8. **Controlled iteration.** A revision changes one primary variable unless a
   deliberate rebuild is authorized.
9. **Evidence-gated evaluation.** Scores are comparative aids, not objective
   truth, and are withheld when rights, brief, deliverable, or evidence coverage
   is inadequate.
10. **Provenance and delivery integrity.** Source rights, model/provider,
    prompt, input roles, output specifications, versions, and checksums remain
    traceable.

## The CRAFT operating loop

`CRAFT` is the compact operating model:

- **C — Context:** understand the objective, audience, product, evidence,
  constraints, source assets, rights, and distribution environment.
- **R — Routes:** develop genuinely different creative mechanisms, then select
  with an explicit rationale.
- **A — Art direction:** lock message hierarchy, visual world, narrative,
  performance, motion, sound, references, invariants, and deliverables.
- **F — Fabrication:** produce provider-aware image and video jobs, generate or
  edit assets, inspect actual outputs, and record receipts.
- **T — Testing:** critique, compare, refine, adapt, package, measure, and feed
  learning back into the next brief.

The full workflow is:

```text
frame -> inspect -> research -> brief -> diverge -> select -> direct
      -> produce -> inspect output -> refine -> adapt -> deliver -> learn
```

A task may enter at any stage. The agent must reconstruct the missing upstream
authority before making downstream claims.

## Modes

- `understand`: analyze an idea, brief, reference set, or existing asset.
- `brief`: create or repair creative authority.
- `concept`: generate, separate, compare, and select creative routes.
- `direct`: produce a treatment, art direction, storyboard, shot plan, copy
  hierarchy, motion language, or sound direction.
- `image`: prepare a GPT Image 2 generation or editing job.
- `video`: prepare a Seedance generation, reference, extension, or editing job.
- `campaign`: orchestrate a cross-format creative system and variant matrix.
- `critique`: perform a read-only creative review.
- `refine`: improve an authorized existing direction or output.
- `adapt`: resize, reframe, localize, version, or translate a locked direction.
- `deliver`: validate files, provenance, manifests, and handoff completeness.

Choose the smallest mode that covers the request. Combined production follows
one causal order: understand, lock authority, develop/select, direct, fabricate,
inspect actual output, refine, validate, then deliver.

## Canonical authority files

A project may seed:

- `BRAND.md` — durable brand identity, audience, voice, visual codes, proof,
  claims boundaries, and non-negotiables;
- `CREATIVE.md` — current job objective, audience tension, proposition,
  selected concept, creative direction, invariants, and approval state;
- `DELIVERABLES.md` — channel slots, ratios, sizes, durations, languages,
  variants, copy, safe areas, naming, deadlines, and owners;
- `asset-ledger.json` — source identity, role, rights, consent, checksum, and
  allowed use.

These are optional for a small task, but unresolved authority must be named as
an assumption rather than silently invented.

## Versioned artifacts

The current contracts are:

- `creative-craft.brief.v1`
- `creative-craft.asset-ledger.v1`
- `creative-craft.concept-routes.v1`
- `creative-craft.critique.v1`
- `creative-craft.project-manifest.v1`
- `creative-craft.creative-direction.v1`
- `creative-craft.image-job.v2`
- `creative-craft.video-job.v2`
- `creative-craft.execution-receipt.v1`
- `creative-craft.output-inspection.v1`
- `creative-craft.revision-lineage.v1`
- `creative-craft.evaluation.v2`
- `creative-craft.delivery.v2`

The v1 job, evaluation, and delivery contracts remain readable for migration,
but new projects seed v2 contracts. Job v2 can declare only `draft`, `ready`,
or `superseded`; generated, inspected, approved, and delivered states are
derived from receipts, files, digests, inspections, and delivery evidence.

Schemas live under `skills/creative-craft/schemas/`. Human-oriented templates
live under `skills/creative-craft/templates/`.

## Provider profiles

Provider facts are dated and isolated:

- `providers/openai-gpt-image-2.json`
- `providers/bytedance-seedance-2.5.json`
- `providers/surfaces/*.json`

The core skill may say “use a low-cost draft pass before a final pass.” Only a
provider profile may state current model names, size limits, reference counts,
background support, or API availability.

## Repository layout

```text
creative-craft/
├── .codex-plugin/
├── .github/workflows/
├── adapters/
├── docs/
├── examples/
├── scripts/
├── skills/creative-craft/
│   ├── SKILL.md
│   ├── providers/
│   ├── references/
│   ├── schemas/
│   ├── scripts/
│   └── templates/
├── tests/
├── package.json
├── sources.lock.json
└── VERSION
```

`skills/creative-craft/` is the canonical installable runtime. Repository-root
files provide governance, CI, examples, and release support.

## Install as an Agent Skill

Distribution is **GitHub-only**. The npm package name is reserved for package
metadata and Pi discovery, but this project is private-to-npm and is not
published to the npm registry.

Pi is a Tier 1 host. Install the immutable release globally or for one project:

```bash
pi install git:github.com/bigKING67/creative-craft@v0.2.0
pi install -l git:github.com/bigKING67/creative-craft@v0.2.0
```

Codex is a Tier 1 host. Ask the built-in `skill-installer` to install
`bigKING67/creative-craft`, path `skills/creative-craft`, ref `v0.2.0`, or run:

```bash
python3 ~/.codex/skills/.system/skill-installer/scripts/install-skill-from-github.py \
  --repo bigKING67/creative-craft \
  --ref v0.2.0 \
  --path skills/creative-craft
```

The skill becomes available to Codex on the next turn/session. A generic Agent
host can clone the repository and use the atomic installer:

```bash
python3 scripts/install_skill.py --target /path/to/host/skills
```

The installer stages on the target filesystem, validates the copy, writes
`INSTALL_PROVENANCE.json`, atomically swaps it into place, and preserves the
previous installation as a backup when `--force` is used. Claude and Cursor
directories currently document thin-adapter expectations; they are not Tier 1
runtime claims.

## Quick start

Run the portable repository checks:

```bash
python3 scripts/validate.py
```

Run the full JSON Schema gate used by CI:

```bash
python3 -m pip install -r requirements-dev.txt
python3 scripts/validate_schemas.py
```

Validate only the installable package runtime:

```bash
python3 skills/creative-craft/scripts/creative_craft.py self-test
```

Inspect the CLI:

```bash
python3 skills/creative-craft/scripts/creative_craft.py --help
```

Seed creative authority into a project without overwriting existing files:

```bash
python3 skills/creative-craft/scripts/creative_craft.py seed \
  --target /path/to/project
```

Validate and compile an image job:

```bash
python3 skills/creative-craft/scripts/creative_craft.py validate \
  --file examples/premium-haircare-launch/image-job.json

python3 skills/creative-craft/scripts/creative_craft.py compile-image \
  --file examples/premium-haircare-launch/image-job.json \
  --output /tmp/image-prompt.md
```

Validate and compile a video job:

```bash
python3 skills/creative-craft/scripts/creative_craft.py compile-video \
  --file examples/premium-haircare-launch/video-job.json \
  --output /tmp/video-prompt.md
```

Evaluate a route or output:

```bash
python3 skills/creative-craft/scripts/creative_craft.py score \
  --file examples/premium-haircare-launch/evaluation.json \
  --root examples/premium-haircare-launch
```

Validate the content-bound project graph and inspect derived state:

```bash
python3 skills/creative-craft/scripts/creative_craft.py validate-project \
  --root examples/premium-haircare-launch

python3 skills/creative-craft/scripts/creative_craft.py project-status \
  --root examples/premium-haircare-launch --json
```

Hash a source or output for the asset ledger:

```bash
python3 skills/creative-craft/scripts/creative_craft.py hash \
  --file path/to/asset.png
```

## Relationship to the Craft family

- `design-craft` asks: **Is this product surface right, usable, coherent,
  tasteful, accessible, and well implemented?**
- `review-craft` asks: **Is this codebase correct, maintainable, performant,
  testable, and supported by reproducible evidence?**
- `creative-craft` asks: **Is this communication idea strategically right,
  creatively distinctive, executable in image/video, faithful to its
  references, and ready to learn from?**

The packages may cooperate, but none should become a catch-all. Creative Craft
can hand a campaign landing-page direction to Design Craft; Design Craft can
hand implementation quality to Review Craft.

## Release philosophy

A repository score is not shipped. Release readiness is represented by
independent gates:

- source and schema integrity;
- provider-profile freshness;
- example and test validity;
- rights and provenance coverage;
- current generation-output evidence;
- host portability;
- delivery completeness.

`0.2.0` proves the planning-to-evidence graph and synthetic lifecycle fixtures.
It still does not claim that unobserved image or video output is production
quality, that real Golden Evals are complete, or that provider network adapters
exist.

Maintainers build one release candidate from a clean commit after installing
`requirements-dev.txt`:

```bash
python3 scripts/build_release.py
```

The ignored `dist/release/` directory contains the `.tgz`, its SHA-256 file,
and a command-bound validation summary for the GitHub Release. It is not an npm
publication workflow.
