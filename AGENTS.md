# DOX framework

- DOX is highly performant AGENTS.md hierarchy installed here
- Agent must follow DOX instructions across any edits

## Core Contract

- AGENTS.md files are binding work contracts for their subtrees
- Work products, source materials, instructions, records, assets, and durable docs must stay understandable from the nearest applicable AGENTS.md plus every parent AGENTS.md above it

## Read Before Editing

1. Read the root AGENTS.md
2. Identify every file or folder you expect to touch
3. Walk from the repository root to each target path
4. Read every AGENTS.md found along each route
5. If a parent AGENTS.md lists a child AGENTS.md whose scope contains the path, read that child and continue from there
6. Use the nearest AGENTS.md as the local contract and parent docs for repo-wide rules
7. If docs conflict, the closer doc controls local work details, but no child doc may weaken DOX

Do not rely on memory. Re-read the applicable DOX chain in the current session before editing.

## Update After Editing

Every meaningful change requires a DOX pass before the task is done.

Update the closest owning AGENTS.md when a change affects:

- purpose, scope, ownership, or responsibilities
- durable structure, contracts, workflows, or operating rules
- required inputs, outputs, permissions, constraints, side effects, or artifacts
- user preferences about behavior, communication, process, organization, or quality
- AGENTS.md creation, deletion, move, rename, or index contents

Update parent docs when parent-level structure, ownership, workflow, or child index changes. Update child docs when parent changes alter local rules. Remove stale or contradictory text immediately. Small edits that do not change behavior or contracts may leave docs unchanged, but the DOX pass still must happen.

## Hierarchy

- Root AGENTS.md is the DOX rail: project-wide instructions, global preferences, durable workflow rules, and the top-level Child DOX Index
- Child AGENTS.md files own domain-specific instructions and their own Child DOX Index
- Each parent explains what its direct children cover and what stays owned by the parent
- The closer a doc is to the work, the more specific and practical it must be

## Child Doc Shape

- Create a child AGENTS.md when a folder becomes a durable boundary with its own purpose, rules, responsibilities, workflow, materials, or quality standards
- Work Guidance must reflect the current standards of the project or user instructions; if there are no specific standards or instructions yet, leave it empty
- Verification must reflect an existing check; if no verification framework exists yet, leave it empty and update it when one exists

Default section order:

- Purpose
- Ownership
- Local Contracts
- Work Guidance
- Verification
- Child DOX Index

## Style

- Keep docs concise, current, and operational
- Document stable contracts, not diary entries
- Put broad rules in parent docs and concrete details in child docs
- Prefer direct bullets with explicit names
- Do not duplicate rules across many files unless each scope needs a local version
- Delete stale notes instead of explaining history
- Trim obvious statements, repeated rules, misplaced detail, and warnings for risks that no longer exist

## Closeout

1. Re-check changed paths against the DOX chain
2. Update nearest owning docs and any affected parents or children
3. Refresh every affected Child DOX Index
4. Remove stale or contradictory text
5. Run existing verification when relevant
6. Report any docs intentionally left unchanged and why

## Workspace Contract

- The product is Sley. Published packages, import roots, and the reserved CLI
  name are `sley`; the canonical repository is `github.com/jigmd/sley`.
- Sley is a fork of Caskada. Preserve Caskada names, versions, and descriptions
  in historical records; distinguish that history from current Sley surfaces.
- The public website is undecided. Use the canonical repository rather than
  inventing or committing a website URL until that decision is made.
- The root pnpm workspace links matching local package versions during repository
  development. Example package manifests must retain publishable semver ranges so
  they also install correctly outside the workspace.
- `docs/cookbook/` catalogs are curated navigation. Update them with relevant
  cookbook changes instead of regenerating them from project README content.
- `shell.nix` provides Python Playwright and Chromium so the TypeScript browser
  snapshot runs directly inside the development shell.

## User Preferences

When the user requests a durable behavior change, record it here or in the relevant child AGENTS.md

- Design and implementation must fit in a reader's head: prefer simple, modular,
  explicit code with clear ownership and low cognitive load.
- Add abstractions only when they remove real complexity. Keep control flow and
  failure behavior easy to trace from the public API into the implementation.
- Fail fast on invalid input, violated contracts, and impossible internal states
  when recovery would hide a defect or make behavior ambiguous.
- Default coding work to full Ponytail mode: apply YAGNI and KISS, reuse existing
  code and standard-library features, prefer deletion, and stop at the smallest
  correct implementation of explicitly requested behavior.
- Do not add speculative abstractions, optimizations, dependencies, or tests for
  hypothetical requirements. Add complexity only after a real requirement or
  measured limitation justifies it.
- Apply the strongest simplicity budget to shipped runtime code, especially the
  graph runner; keep the public API thinner still, limited to contracts and
  delegation into the core.
- Do not treat thorough verification or pedagogical cookbook detail as runtime
  bloat. Tests may be extensive, and cookbook examples may retain deliberate
  detail when it teaches the intended lesson.

## Child DOX Index

- `conformance/AGENTS.md` owns language-neutral executable contracts,
  reference interpreters, and cross-port snapshot verification.
- `cookbook/AGENTS.md` owns instructional examples, cookbook project structure,
  and pedagogy-first quality rules.
- `architecture/AGENTS.md` owns normative specifications, decision records,
  implementation baselines, release-readiness evidence, and prototype audits.
- `python/AGENTS.md` owns the Python runtime, package surface, and Python-side
  conformance verification.
- `tests/AGENTS.md` owns repository-level integration tests and cookbook smoke
  contracts.
- `typescript/AGENTS.md` owns the TypeScript runtime, package surface, and
  TypeScript-side conformance verification.
- Documentation outside an indexed child subtree, including `docs/`, remains
  root-owned.
- Root-owned files include `README.md` and `LICENSE`.
