# Provider profiles

Provider profiles isolate current model facts from the model-agnostic creative
method.

Each profile must contain:

- stable profile schema;
- provider and model;
- verification date;
- official sources;
- current capabilities and limits;
- known limitations;
- execution availability;
- migration notes.

A profile is evidence, not permission. The user, project authority, rights,
channel rules, and provider policy remain higher constraints.

Do not hardcode a provider fact in `SKILL.md` unless it is timeless. Update the
profile, CLI validation, tests, examples, and changelog together.
