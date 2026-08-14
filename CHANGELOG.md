# Changelog

All notable changes are documented here.

## 0.3.0 — Unreleased candidate

Copy authority, runtime modularity, and validated-boundary candidate:

- add first-class `creative-craft.copy-sheet.v1` with strategy, audience
  tension, proposition, voice, proof hierarchy, mandatory/prohibited/legal
  copy, distinct copy routes, selected units, evidence refs, render method,
  approval, and unknowns;
- add `creative-craft.project-manifest.v2` with `copy_policy=required`, bind v2
  Image/Video Jobs to explicit Copy Sheets and units, and require reviewed copy
  for internal readiness plus approved public copy with a named owner for
  public delivery;
- preserve Project Manifest v1 and legacy copy-unbound projects as readable
  compatibility inputs without silently upgrading or approving them;
- replace the 5,491-line runtime entrypoint with a compatibility facade over
  domain modules for contracts, project graph, evaluation, pack transactions,
  project operations, runtime checks, and CLI parsing; split the test suite by
  the same ownership boundaries;
- replace fixed sibling temporary files with random same-directory exclusive
  files, fsync before atomic replace, reject symlink destinations/parents, and
  reject Brand/Reference write transactions through symlink Project roots;
- replace quadratic `uniqueItems` scanning with typed canonical indexing plus
  collision verification, preserving JSON Schema equality while gating the
  1,600-to-3,200 item median-time ratio at `<=2.5`;
- declare Python `>=3.10`, add Python 3.10 to the CI matrix, lint all runtime
  modules, and include the benchmark and new files in release/package gates.

This candidate is not a published GitHub tag or npm release. Its public fixture
is fictional and internally reviewed only; it does not include real Provider
output, a real owner approval, private company evidence, or a Creative Golden
Eval.

## 0.2.6 — 2026-08-05

Review evidence and transaction hardening release:

- bind output and delivery Evaluation gates to a stage-compatible target and a
  matching Job, Receipt, Output, and Inspection chain instead of accepting an
  unrelated project-global Inspection;
- make `seed` a symlink-safe, same-filesystem staged-tree transaction covering
  force backups, generated Manifest content, optional Brand binding, full
  validation, commit, and exact-tree failure recovery;
- reject symlink Project roots and Manifests, and make `doctor-project` report
  unsafe top-level JSON symlinks without following snapshot trees;
- implement JSON Schema `uniqueItems` with JSON deep-equality in the portable
  runtime and add keyword-complete parity mutations for all 12 public uses;
- require timezone-bearing Receipt and approved-Inspection timestamps and
  compare their UTC-normalized values without leaking mixed-datetime errors;
- synchronize immutable Pi and Codex install snippets with `v0.2.6`, gate future
  adapter tag drift, and add repository-local Review Craft E3 commands for the
  exact packaged runtime.

This release remains GitHub-only, contains no private company content, does not
call provider networks, and does not claim real Creative Golden Evals.

## 0.2.5 — 2026-08-05

Evidence-safe seed and project diagnostics release:

- separate descriptive evidence about current or historical assets from the
  approved Brand Pack and locked project authority that govern future work;
- prevent `seed` from creating placeholder Execution Receipt, Output
  Inspection, or Revision Lineage files before the corresponding real event;
- register seeded Critique in the Project Manifest and require its target
  `asset_id` to resolve to the project Asset Ledger;
- add the read-only `doctor-project` command, distinguishing a valid manifest
  graph from a healthy project directory and reporting known unregistered
  Creative Craft artifacts;
- classify byte-identical unregistered templates as `seed_template_residue`
  without automatically registering or deleting them;
- verify that project diagnosis leaves the complete project tree unchanged and
  exercise `doctor-project` through the installed leaf runtime;
- synchronize the new lifecycle boundary across English and Chinese install and
  operating documentation.

This release remains GitHub-only, contains no private company content, does not
call provider networks, and does not claim real Creative Golden Evals.

## 0.2.4 — 2026-08-04

Reference evidence and filesystem hardening release:

- reject symlinks and project-root escapes across Brand and Reference staging,
  snapshot, binding, lineage, and retained-backup write destinations;
- remove failed-operation backups and newly created empty directories after a
  successful rollback, restoring the exact pre-operation project tree;
- require every source in a `reviewed` Reference Pack to use a non-placeholder
  URI plus a local, symlink-free source snapshot whose SHA-256 matches;
- add `creative-craft.reference-binding-history.v1` and register an immutable,
  content-bound predecessor artifact for every successful Reference update;
- resolve the complete predecessor chain during project validation and reject
  fictional, cyclic, cross-project, cross-pack, or orphan lineage records;
- reject new bindings and updates from `superseded` Reference Packs while
  preserving already-bound snapshots as historical evidence with a warning;
- expand installed leaf-runtime smoke through seed, reviewed source validation,
  bind, update, project validation, and exact-tree rollback;
- safely unpack the exact generated `.tgz` in CI and release builds, then repeat
  leaf self-test plus
  Reference bind, update, validation, and exact-tree rollback against its
  packaged runtime;
- normalize public release command receipts so local user and workspace paths
  are not written into `release-validation.json`.

This release remains GitHub-only, contains no private brand/reference content,
does not call provider networks, and does not claim real Creative Golden Evals.

## 0.2.3 — 2026-08-04

Reference intelligence portability release:

- added non-authoritative `creative-craft.reference-pack.v1` and
  `creative-craft.reference-binding.v1` contracts without adding any private
  brand, competitor, team, source, or asset data to the public package;
- added `init-reference-pack` and `validate-reference-pack` for thin private
  Reference Skills with evidence classes, source links, transferable
  principles, non-transferable elements, content digests, safe paths, and
  input-rights checks;
- added `bind-reference-pack` with `0..N` immutable project snapshots,
  selected-entity bindings, selected-asset ledger merge, and source lineage;
- added `update-reference-snapshot` with per-pack previous-binding lineage,
  scoped retained backup, complete project validation, and rollback on failure;
- enforced `may_override_primary_brand: false`, kept the existing `0..1`
  Primary Brand Pack invariant, rejected revoked references, and made draft
  references warning-only so they cannot block an otherwise Ready Job;
- added installed-runtime, package-boundary, multiple-pack, snapshot-drift,
  selection, rights, update-isolation, and rollback regression coverage.

This release intentionally does not implement Partner/co-brand authority,
contain company-specific private reference data, publish to npm, call provider
networks, or claim real Creative Golden Evals.

## 0.2.2 — 2026-08-04

Brand authority portability release:

- added generic `creative-craft.brand-pack.v1` and
  `creative-craft.brand-binding.v1` contracts without adding any private brand
  content to the public package;
- added `init-brand-pack` and `validate-brand-pack` for thin private Brand
  Skills with placeholder-only authority, content digests, safe paths, source
  review, asset rights, and consent checks;
- extended `seed` with opt-in Brand Pack binding that copies an immutable
  project snapshot, projects `BRAND.md`, merges Asset Ledger entries, and binds
  source/ref/commit plus SHA-256 identity;
- added `update-brand-snapshot` with previous-binding lineage, retained backup,
  complete project validation, and rollback on failure;
- blocked `ready` Jobs when a bound Brand Pack is not approved while preserving
  backward compatibility for unbound projects;
- added installed-runtime Brand Pack smoke coverage and regression tests for
  traversal, symlinks, digest drift, unresolved rights, snapshot drift,
  binding mismatches, updates, and rollback.

This release does not contain company-specific knowledge, real brand assets,
approved claims, provider network adapters, or real Creative Golden Evals.

## 0.2.1 — 2026-08-04

Installed-runtime verification patch:

- split repository integrity checks from canonical Skill runtime checks;
- made `self-test` automatically select repository scope in a checkout and
  runtime scope in a Pi, Codex, or generic leaf Skill installation;
- added explicit `scope`, `repository_valid`, and `runtime_valid` JSON evidence;
- made the atomic installer validate its staged leaf copy through the same
  installed-runtime self-test used after installation;
- added isolated leaf-install regression coverage and a Host smoke gate for the
  installed-runtime self-test.

## 0.2.0 — 2026-08-04

Evidence-bound production-contract release:

- added Project Manifest, Creative Direction, Image/Video Job v2, Execution
  Receipt, Output Inspection, Revision Lineage, Evaluation v2, and Delivery v2;
- made JSON Schema the public structural validation source of truth, with a
  standard-library runtime evaluator and `jsonschema` mutation parity gate;
- added safe project-relative path, SHA-256, cross-artifact reference,
  Provider/Surface, rights, and lifecycle validation;
- replaced Job-generated/approved self-declaration with evidence-derived
  `generated`, `inspected`, `revision_required`, `approved`, and `delivered`
  projections;
- split evaluation coverage from evidence strength, distribution, confidence,
  uncertainty, and project-derived gates;
- added OpenAI Image API / Responses Image Tool and ByteDance Jimeng / Doubao
  Pro Surface Profiles; ModelArk remains explicitly unavailable;
- added `validate-project`, `project-status`, `inspect-output`,
  `start-revision`, and `verify-delivery` CLI commands;
- made seed inventory registry-derived and included Critique plus a generated,
  content-bound project manifest;
- fixed `doctor --root` Provider isolation and duplicate metadata ID handling;
- replaced destructive installation with validated same-filesystem staging,
  atomic replacement, rollback, backup, and install provenance;
- documented GitHub-only distribution and Tier 1 Pi/Codex installation;
- added real GitHub CI, Schema/reference parity, host package smoke, atomic
  installer failure tests, and a v2 fictional example.

This release does not include provider network adapters or claim real image or
video Golden Evals.

## 0.1.0 — 2026-08-04

Initial public foundation:

- canonical Creative Craft skill and authority model;
- CRAFT operating loop and task modes;
- creative brief, concept, direction, asset-analysis, image, video, evaluation,
  provenance, iteration, and delivery references;
- provider-scoped profiles for OpenAI GPT Image 2 and ByteDance Seedance 2.5;
- versioned JSON artifacts and Draft 2020-12 JSON Schemas;
- GPT Image 2 single/multi-turn execution mode, output compression, and masked-edit guidance;
- standard-library CLI for doctoring, package self-testing, seeding, validation,
  prompt compilation, scoring, and hashing;
- fictional premium haircare example;
- cross-platform unit tests, full schema validation, publish-boundary smoke tests, and CI.
