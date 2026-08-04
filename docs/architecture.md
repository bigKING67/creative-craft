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

Execution surfaces live under `providers/surfaces/` and distinguish the model
from the UI/API used to execute it. A surface declares availability, compatible
provider profiles, supported modes, and surface-specific limitations.

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

## Why no direct model adapter in v0.2.0

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
