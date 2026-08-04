# Image production

Image production begins with a job specification, not a decorative prompt.

Read the matching dated provider profile before using model-specific features.

## Choose the workflow

### Generate

Use when the image is created from a brief, concept, or reference system.

### Edit

Use when a supplied image must remain recognizable and only selected elements
may change.

### Single-turn

Use for one prompt and one generation/edit decision.

### Multi-turn

Use when the work requires iterative visual conversation, several constrained
edits, or reference continuity. Maintain a revision ledger and repeat
invariants in every turn.

## Image job fields

A production-ready image job contains:

- job ID and schema version;
- intended use;
- task type;
- provider and model;
- execution mode;
- output size, quality, format, JPEG/WebP compression, background, and variant count;
- scene/background;
- subject;
- action or expression;
- composition, viewpoint, framing, and negative space;
- lighting;
- materials, medium, texture, and style;
- exact text and typography;
- reference assets and roles;
- change list;
- preserve list;
- constraints and exclusions;
- inspection checklist;
- rights and approval state.

## Prompt architecture

Use a stable, skimmable order:

```text
INTENDED USE AND OUTPUT
BACKGROUND / SCENE
SUBJECT
ACTION / EXPRESSION
COMPOSITION / CAMERA / NEGATIVE SPACE
LIGHTING
MATERIALS / MEDIUM / STYLE
EXACT TEXT / TYPOGRAPHY
REFERENCE MAP
CHANGE
PRESERVE
CONSTRAINTS / EXCLUSIONS
```

A production prompt should be precise enough to execute but not overloaded with
irrelevant adjectives.

## Specificity

Prefer concrete control:

- brushed aluminum, translucent amber liquid, uncoated paper;
- centered three-quarter product view, camera slightly above label height;
- soft directional light from upper left, restrained specular highlights;
- 18% empty space above the cap for headline;
- warm white background, no visible horizon line.

Avoid empty quality stacks:

> premium, stunning, cinematic, 8K, masterpiece, elegant, high-end

Use quality cues only when they translate into visible choices.

## Exact text

- quote exact text;
- specify capitalization, line breaks, hierarchy, alignment, and placement;
- state that no other text may appear;
- inspect spelling and glyphs after generation;
- use a separate typesetting step when pixel-accurate typography is critical.

## Reference roles

Map by asset, not by vague similarity:

```text
@Image 1 — preserve product geometry, label, cap, and liquid color.
@Image 2 — lighting direction and shadow softness only.
@Image 3 — composition and negative-space proportion only.
```

Do not ask the model to infer which parts of a reference matter.

## Edit contract

Use:

```text
CHANGE ONLY
- ...

PRESERVE EXACTLY
- ...

INTEGRATION
- reconstruct only what is revealed;
- match existing light, perspective, grain, and depth of field.

DO NOT ADD
- ...
```

For identity-, product-, packaging-, or logo-sensitive work, repeat invariants
on every edit.

## Mask-guided edits

For a masked edit, identify the source image and mask as separate assets and
state their roles explicitly. The source and mask must use the same dimensions
and format, and the mask needs an alpha channel. Treat the mask as guidance,
not a pixel-exact selection boundary. Keep the change/preserve contract even
when a mask is present.

## Iteration ladder

1. low-cost composition draft;
2. direction selection;
3. identity/product fidelity pass;
4. text and detail pass;
5. local corrections;
6. final-size generation or upscale when appropriate;
7. delivery validation.

A high-resolution first pass may waste cost when the route is still uncertain.

## Inspection

Check actual outputs for:

- objective and proposition;
- subject and product fidelity;
- anatomy and object geometry;
- label, logo, and exact text;
- composition and safe area;
- lighting, material, reflection, shadow, and transparency;
- accidental objects, text, watermarks, or duplicated details;
- crop and requested dimensions;
- visual consistency across variants;
- rights and delivery state.

## Retry diagnosis

Change the smallest causal variable:

- wrong subject: strengthen identity/reference role;
- product drift: expand preserve contract and reduce competing references;
- wrong composition: state positions, scale, framing, and negative space;
- weak hierarchy: simplify elements and clarify focal order;
- text error: shorten copy, isolate exact text, or typeset afterward;
- style drift: state medium/material rules and remove conflicting style cues;
- local defect: use a localized edit rather than full regeneration.

Record the failed output and diagnosis. Do not erase unsuccessful lineage.
