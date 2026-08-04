# Architecture

Creative Craft separates timeless creative method from changing provider
capabilities.

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
- validates jobs;
- compiles provider-aware prompts;
- calculates evidence-aware comparative scores;
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
user / project authority
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

## Why no direct model adapter in v0.1.0

The first failure mode of a creative system is usually not API syntax. It is a
missing brief, collapsed concept/execution thinking, vague reference use,
uncontrolled edits, unobserved output claims, or absent rights.

The first release therefore stabilizes the upstream contracts. Direct adapters
can be added later as opt-in integrations with explicit credentials, cost,
network, moderation, receipt, and provider-version handling.

## Compatibility principle

Artifacts use versioned `schema_version` values. A future version may add
fields without changing the meaning of existing fields. Breaking semantic
changes require a new schema version and migration notes.
