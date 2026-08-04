# Roadmap

The roadmap protects the creative method from premature provider coupling and
separates contract maturity from claims about creative quality.

## 0.1 — foundation

Implemented the canonical skill, authority files, provider profiles, v1 jobs,
prompt compilation, local validation, scoring, tests, and fictional example.

## 0.2 — evidence-bound production graph

Implemented:

- project manifest with safe project-relative paths and SHA-256 binding;
- formal Creative Direction, Image/Video Job v2, Execution Receipt, Output
  Inspection, Revision Lineage, Evaluation v2, and Delivery v2;
- JSON Schema structural truth plus runtime/reference parity checks;
- cross-artifact reference, Provider, Surface, rights, digest, and state
  validation;
- derived job lifecycle rather than generated/approved self-declaration;
- evidence coverage, strength, distribution, confidence, uncertainty, and gate
  projection;
- draft inspection/revision CLI, atomic installer, install provenance, Pi/Codex
  package discovery contracts, and GitHub CI.

This version includes synthetic lifecycle fixtures but no real provider output
claim.

## 0.2.2 — portable brand authority

Implemented without changing the `0.3` Golden Eval milestone:

- generic Brand Pack and project Brand Binding contracts;
- separate private Brand Skill initialization with placeholder-only authority;
- content, digest, path, symlink, rights, consent, source, and approval checks;
- immutable project snapshots with `BRAND.md` projection and Asset Ledger merge;
- explicit snapshot update, previous-binding lineage, backup, full validation,
  and rollback;
- backward compatibility for projects that do not bind a Brand Pack.

No company-specific knowledge or asset is included in the public package.

## 0.2.3 — portable reference intelligence

Implemented without weakening Primary Brand authority:

- generic non-authoritative Reference Pack and multi-binding contracts;
- separate private Reference Skill initialization with empty draft content;
- evidence-classed observations, transferable principles, explicit
  non-transferable elements, source identity, and asset-use policy;
- `0..N` immutable project snapshots with selected-entity asset merge;
- scoped snapshot update, previous-binding lineage, backup, full validation,
  and rollback without changing other packs;
- hard `may_override_primary_brand: false`, revoked-pack rejection, and draft
  warnings that do not block Ready Jobs;
- installed-runtime and package-boundary coverage for the new contracts.

Partner/co-brand federation remains intentionally unimplemented until a real
joint-authority workflow supplies concrete requirements and evidence.

## 0.2.4 — reference evidence and filesystem hardening

Implemented before the `0.3` Golden Eval milestone:

- symlink-safe, project-contained Brand and Reference write destinations;
- exact-tree rollback cleanup for failed snapshot operations;
- copied and digest-verified source snapshots for reviewed Reference Packs;
- registered immutable Reference Binding history with complete chain validation;
- explicit superseded-pack behavior for new and historical bindings;
- installed leaf-runtime bind, update, validation, and rollback E2E coverage;
- safe extraction and the same Reference lifecycle E2E against the exact release
  `.tgz` rather than only the source checkout;
- public release receipts with normalized rather than local absolute paths.

## 0.3 — real creative evals

Planned:

- high-fidelity product edit case;
- exact-copy commercial key visual and adaptation case;
- 15-30 second Seedance product film, extension, and timestamp-edit case;
- immutable actual outputs, human inspections, failed revisions, comparisons,
  and model-version regression baselines.

## 0.4 — Seedance guide internalization

Planned after the owner-supplied official guides are exported and reviewable:

- Jimeng and Doubao Pro surface-specific rules;
- prompt grammar, reference, editing, and extension fixtures;
- official example/source mapping and dated regression tests.

Do not infer an API contract from UI behavior.

## 0.5 — optional provider adapters

Planned only when credentials, cost consent, moderation, errors, receipts,
snapshot identity, and rollback behavior can be tested:

- optional GPT Image 2 Image API / Responses Image Tool adapter;
- Seedance API adapter only after stable official API availability;
- multi-turn and extension receipt lineage.

## 1.0 — operational evidence

Requires several real end-to-end projects, current Provider/Surface profiles,
cross-host verification, output inspection evidence, controlled comparisons,
stable migrations, and reproducible release artifacts.

Version numbers indicate contract maturity, not a universal creative-quality
score.
