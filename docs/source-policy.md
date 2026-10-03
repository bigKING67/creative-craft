# Source policy

Content-production engineering references are tracked separately in
[Upstream absorption](upstream-absorption.md). That register distinguishes
reviewed sources, integration candidates, implemented behavior, and verified
outputs. It does not turn a reference into a runtime dependency or Provider
authority. See [Content production architecture](content-production-architecture.md)
for the core/integration/host boundary and the limited local-production MVP
evidence. Limited DataHub integration has local isolated-test evidence; live
provider quality and full production acceptance remain pending. Consult the
register for scope instead of treating all integrations as uniformly complete.

Creative Craft depends on changing model capabilities and stable creative
principles. Treat them differently.

## Source priority

1. current official API/model documentation;
2. current official capability or launch article;
3. project-owner supplied official guide;
4. current product UI behavior observed directly;
5. primary technical paper;
6. high-quality secondary analysis, explicitly labeled;
7. generic practice.

## Verification

Every provider profile records:

- `verified_at`;
- official source list;
- current availability;
- capability limits;
- known limitations.

Reverify when:

- a model alias or version changes;
- a provider announces a new release;
- a UI or API rejects a previously valid job;
- a capability affects cost, rights, or delivery;
- more than 90 days have passed for an active provider.

## Change protocol

1. inspect official source;
2. update profile;
3. update validation logic;
4. add or update tests;
5. update examples;
6. document migration and behavior change;
7. avoid rewriting model-agnostic guidance unless the underlying professional
   principle changed.

## Uncertainty

When official sources conflict or omit detail:

- keep the stricter compatible behavior;
- record the conflict;
- avoid hard validation for uncertain UI-only behavior;
- use a warning instead of a false error;
- do not promote third-party claims into canonical limits.
