# Changelog

All notable changes are documented here.

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
