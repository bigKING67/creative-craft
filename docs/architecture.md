# Architecture

Creative Craft separates timeless creative method from changing provider
capabilities and from organization-specific authority.

## Repository boundary

Creative Craft is the public protocol. Company or client authority belongs in
a separate private Brand Skill; campaign evidence belongs in a separate project.

```text
public Creative Craft -> private Brand Skill -> immutable project snapshot
```

The public core must not contain proprietary claims, internal links, brand
assets, or organization-specific rules. A thin Brand Skill calls the generic
method instead of copying it. This lets any team install the same Creative Craft
runtime while supplying its own governed authority.

## Layers

### 1. Canonical skill

`skills/creative-craft/SKILL.md`

Owns:

- scope and authority;
- evidence states;
- modes and routing;
- end-to-end workflow;
- non-negotiable behavior;
- delivery boundary.

It must not accumulate volatile API parameters.

### 2. References

`skills/creative-craft/references/`

Own reusable professional methods:

- brief and strategy;
- concept development;
- creative direction;
- image and video production;
- existing-asset analysis;
- evaluation/testing;
- iteration/versioning;
- rights/provenance;
- delivery.

References are loaded by task, not all at once.

### 3. Provider profiles

`skills/creative-craft/providers/`

Own dated facts:

- model/version;
- current capabilities;
- limits;
- availability;
- official sources;
- known limitations;
- compatibility notes.

A provider update should not require rewriting the creative method.

Execution surfaces live under `providers/surfaces/` and distinguish the model
from the UI/API used to execute it. A surface declares availability, compatible
provider profiles, supported modes, and surface-specific limitations.

### Private Brand Skills (external)

A Brand Skill is not a directory inside this repository. It owns only curated
brand, product, claims, visual, verbal, channel, rights, source, and Asset Ledger
authority. Large media stays in DAM/object storage; the ledger binds stable URIs
to SHA-256, rights, consent, and allowed use.

`creative-craft.brand-pack.v1` registers the exact authority files and digests.
`creative-craft.brand-binding.v1` records which pack/version/source was copied
into a project. Binding copies registered files and safe local assets into
`.creative-craft/brand-snapshot/`; no live symlink or implicit refresh is
allowed. Updating a snapshot creates a backup and lineage record, then validates
the complete project or rolls back.

### 4. Versioned artifacts and schemas

`skills/creative-craft/templates/`
`skills/creative-craft/schemas/`

Own contracts between strategy, direction, production, review, and delivery.
Artifacts are both human-readable and machine-validatable.

### 5. Portable tooling

`skills/creative-craft/scripts/creative_craft.py`

Standard-library CLI:

- checks repository integrity;
- seeds project authority;
- initializes and validates private Brand Skills;
- binds and explicitly updates immutable project Brand Pack snapshots;
- validates JSON Schema structure and cross-field semantics;
- validates a content-bound project graph and derives lifecycle status;
- compiles provider-aware prompts;
- calculates evidence-bound coverage, strength, confidence, and scores;
- hashes assets.

It does not call providers or incur costs.

### 6. Examples and evals

`examples/`
`tests/`

Prove that contracts and compilation work. A future evaluation layer should add
real generated outputs, human judgments, and controlled comparisons without
promoting historical results to current model guarantees.

## Data flow

```text
private Brand Skill -- source ref/commit and reviewed authority
        |
        v
immutable Brand Pack snapshot -> project BRAND.md / project asset ledger
        |
        v
user / project authority
        |
        v
project manifest -- content hashes and artifact registry
        |
        v
creative brief ---- asset ledger
        |
        v
concept routes -> selected route -> creative direction
        |                                |
        |                                v
        |                     image job / video job
        |                                |
        |                        provider execution
        |                                |
        v                                v
evaluation <------ actual output inspection
        |
        v
revision lineage -> adaptation -> delivery manifest -> learning
```

The declared state inside image/video Job v2 is intentionally limited to
`draft`, `ready`, and `superseded`. The resolver projects `generated`,
`inspected`, `revision_required`, `approved`, and `delivered` only when the
corresponding receipt, output file, digest, inspection, approval, and delivery
evidence exists.

## Why no direct model adapter in v0.2

The first failure mode of a creative system is usually not API syntax. It is a
missing brief, collapsed concept/execution thinking, vague reference use,
uncontrolled edits, unobserved output claims, or absent rights.

The current release therefore stabilizes the end-to-end evidence contracts. Direct adapters
can be added later as opt-in integrations with explicit credentials, cost,
network, moderation, receipt, and provider-version handling.

## Compatibility principle

Artifacts use versioned `schema_version` values. A future version may add
fields without changing the meaning of existing fields. Breaking semantic
changes require a new schema version and migration notes.

JSON Schema is the structural source of truth. The installed standard-library
runtime interprets the schema keyword subset used by this repository; CI compares
that result with the `jsonschema` Draft 2020-12 reference implementation. Python
semantic validators are limited to Provider/Surface capability rules,
cross-field constraints, digests, references, rights, and lifecycle evidence.
