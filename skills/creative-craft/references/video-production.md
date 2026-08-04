# Video production

Video production is the coordination of story, performance, blocking, camera,
motion, sound, references, continuity, and editability over time.

Read the matching dated Seedance provider profile before using current limits or
features.

## Task types

- `text_to_video`;
- `image_to_video`;
- `reference_to_video`;
- `extend_video`;
- `edit_video`.

Choose the smallest task type that preserves the best existing evidence.

## Video job fields

A production-ready job contains:

- job ID and schema version;
- intended use;
- provider, model, platform, and execution mode;
- duration, ratio, resolution target, and language;
- creative premise and end state;
- subject, scene, props, style, camera, motion, and audio references;
- reference role map;
- continuity locks;
- timestamped beats;
- performance and blocking;
- camera and transition plan;
- environment, materials, lighting, weather, and physics;
- dialogue, voice, ambience, effects, and music;
- edit changes and preserved invariants;
- exclusions and failure conditions;
- extension boundary;
- inspection checklist;
- rights and approval state.

## Prompt architecture

```text
FORMAT AND INTENDED USE
CREATIVE PREMISE AND END STATE
REFERENCE MAP BY ASSET AND ROLE
CONTINUITY LOCKS
TIMESTAMPED BEATS
ENVIRONMENT / MATERIAL / LIGHT / PHYSICS
DIALOGUE / VOICE / AMBIENCE / EFFECTS / MUSIC
EDIT-ONLY CHANGES
PRESERVE
EXCLUSIONS / FAILURE CONDITIONS
```

## Timeline

Use a timestamped plan when timing, cuts, actions, or edits matter.

Example:

```text
0–3s
- close product macro;
- condensation slides down the bottle;
- slow push-in;
- quiet room tone and one soft glass click.

3–8s
- talent lifts the product into frame;
- camera arcs 30 degrees while the background opens;
- music enters with restrained percussion.
```

Each beat should state only feasible concurrent actions. Preserve enough time
for transitions and physical completion.

## Reference map

Give each reference a department-like responsibility:

- character identity;
- product geometry;
- scene;
- prop;
- composition;
- storyboard;
- camera language;
- subject motion;
- lighting;
- material;
- visual style;
- pacing;
- dialogue/voice;
- ambience;
- effects;
- music.

Example:

```text
@Image 1 — product geometry and label.
@Image 2 — talent identity and wardrobe.
@Video 1 — camera path and reveal timing, not character identity.
@Audio 1 — ambience density and energy arc, not direct reuse.
```

## Continuity lock

State invariants:

- subject appearance and voice;
- product geometry and label;
- wardrobe;
- environment and time of day;
- color and lighting logic;
- spatial relationships;
- motion direction;
- sound bed;
- narrative state at the extension boundary.

For an extension, restate the final state of the source and the exact next
action.

## Camera

Describe:

- shot size;
- angle;
- camera path;
- speed and acceleration;
- stabilization character;
- transition or occlusion;
- subject relationship;
- final framing.

Avoid stacking incompatible movements. Use a few purposeful moves instead of
continuous spectacle.

## Performance and physics

Describe behavior, not only appearance:

- gaze;
- facial temperature;
- body orientation;
- hand-object contact;
- weight transfer;
- pace;
- clothing and hair response;
- prop interaction;
- environmental forces;
- start and completed end state.

Physical plausibility must be inspected in the actual output.

## Audio

Separate:

- dialogue;
- voice character and delivery;
- ambience;
- synchronized sound effects;
- music function and energy arc;
- silence;
- rights or replacement status.

Do not assume a generated track is cleared for every commercial use. Record
provider and rights state.

## Editing

For targeted edits:

```text
EDIT
- exact time range;
- exact character, action, camera, background, or audio change.

PRESERVE
- all unchanged subjects;
- action timing outside the range;
- visual style;
- lighting continuity;
- audio continuity;
- first and final boundary frames.
```

A localized edit should not become an implicit full redesign.

## Extension

Specify:

- source video;
- continuity locks;
- source final frame/state;
- next action;
- narrative purpose;
- duration;
- ending state;
- whether later extension is expected.

## Inspection

Review actual video for:

- prompt/brief adherence;
- subject and product consistency;
- multi-subject identity separation;
- movement and physical plausibility;
- blocking and spatial continuity;
- camera path and transitions;
- lighting and material continuity;
- accidental text or subtitles;
- dialogue, voice, effects, music, and sync;
- edit boundary integrity;
- start/end states;
- technical delivery;
- rights/provenance.

## Retry diagnosis

- identity drift: simplify subject count, strengthen reference roles and
  continuity locks;
- action failure: reduce concurrent actions and specify start/end states;
- camera confusion: use fewer movements and timestamp them;
- physics defects: make forces, contact, weight, and completion explicit;
- audio mismatch: separate dialogue, ambience, effects, and music;
- edit bleed: narrow the time range and repeat preserved invariants;
- narrative compression: remove a beat or extend in a second pass;
- inconsistent continuation: restate source end state and audiovisual locks.
