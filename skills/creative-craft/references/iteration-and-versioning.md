# Iteration and versioning

Iteration should reduce uncertainty, not create untraceable drift.

## Revision unit

Every revision records:

- source version;
- primary variable changed;
- reason;
- change instructions;
- preserved invariants;
- provider/model or production method;
- output version;
- observed result;
- decision;
- next action.

## Edit strategy

Use the smallest valid intervention:

1. copy or metadata correction;
2. local edit;
3. composition or timing edit;
4. regeneration with stronger constraints;
5. route-level rework;
6. new concept;
7. live reshoot or manual production.

Do not regenerate an entire asset to fix a local issue when a reliable local
edit exists. Do not keep patching a fundamentally wrong concept.

## Single-change rule

Default to one primary change per iteration. Supporting changes may be required
for integration, but name them.

Example:

```text
Primary change: reduce foreground hand scale by 40%.
Preserve: jewelry geometry, stone texture, cord knots, bead count, lighting,
crop, background, copy, and all other subjects.
Integration: reconstruct only the newly revealed background.
```

## Naming

Recommended:

```text
<project>_<route>_<asset>_<channel>_<ratio>_v###.<ext>
```

Example:

```text
northstar_motion-is-proof_hero_douyin_9x16_v004.mp4
```

Do not encode approval solely in a filename. Approval belongs in the manifest.

## Status

- `exploration`;
- `candidate`;
- `selected`;
- `needs_revision`;
- `approved`;
- `delivered`;
- `superseded`;
- `rejected`;
- `archived`.

## Prompt lineage

Record:

- prompt text or hash;
- reference asset IDs and roles;
- provider/model/snapshot when available;
- output parameters;
- generation or edit time;
- operator/host;
- output asset ID/checksum;
- moderation or provider error;
- review decision.

When a host does not expose seed or internal settings, record `not_exposed`
rather than inventing them.

## Adaptation

An adaptation remains the same concept only if its mechanism and proposition
survive. Mark `concept_changed: true` when a channel version introduces a new
mechanism, claim, or narrative.

## Rollback

Keep the selected source and prior approved output until the replacement is
validated. Destructive cleanup follows delivery, not experimentation.
