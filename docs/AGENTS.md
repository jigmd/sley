# Documentation

## Purpose

- Teach Sley from first successful run through exact runtime semantics.
- Serve humans and coding agents from one accurate Markdown source.

## Ownership

- Owns the public GitBook content, navigation, examples catalog, redirects,
  writing standards, and documentation checks.
- The RFC, conformance fixtures, tests, and public facades remain semantic
  authorities; documentation explains them without redefining them.

## Local Contracts

- Keep the public journey within Start, Learn, Guides, Patterns, Reference,
  Examples, and About. A new page must earn its place by reducing reader effort
  or owning a distinct contract.
- The Quickstart is provider-free, dependency-free beyond Sley, runnable in one
  file, and reaches visible output in under five minutes.
- Teach shared behavior once with paired Python and TypeScript examples. Keep
  language-specific signatures in their own reference pages.
- Every page starts with a concise `description` frontmatter value, defines new
  terms at first use, exposes prerequisites through sequence or prose, and ends
  with the next useful action when one exists.
- Learn pages build the mental model in dependency order. Guides solve one task.
  Reference pages state exact contracts. Examples demonstrate complete uses.
- Show observable output for primary examples. Put important sharp edges beside
  their first relevant use instead of collecting surprises at the end.
- State application-owned concerns and intentional limitations plainly. Do not
  imply built-in schema validation, payload typing, tracing, cancellation,
  persistence, distributed execution, provider timeouts, or shared rate limits.
- Keep provider-specific and generic AI utility instruction in cookbook projects,
  not the core runtime journey.
- GitBook owns published per-page Markdown, `llms.txt`, `llms-full.txt`, and MCP.
  Do not maintain duplicate machine-documentation bundles in the repository.

## Work Guidance

- Resolve semantic conflicts in this order: accepted RFC, conformance and tests,
  then public facades. Treat Git history as non-authoritative source material.
- Prefer one causal example over several disconnected fragments. Diagrams must
  explain topology or settlement rather than decorate a page.
- Keep paragraphs short, headings descriptive, link text meaningful, and code
  blocks directly usable. Avoid marketing claims, undefined jargon, and
  framework internals before the reader needs them.
- Preserve valuable public URLs with `.gitbook.yaml` redirects when pages move.
- Treat the Python and TypeScript ports as peers. Explain genuine host-language
  differences without forcing artificial syntax parity.

## Verification

- Run `node .github/scripts/check-docs.js` for navigation, frontmatter,
  published-path, redirect, local-link, and public-export integrity.
- Run `node .github/scripts/check-doc-examples.js` to execute and type-check the
  complete teaching programs extracted from the documentation.
- Run `node .github/scripts/generate-examples.js` after cookbook README changes;
  a second run must leave no diff.
- Run primary documentation examples in both languages and check their shown
  output.
- Run Prettier and `git diff --check` over changed documentation and scripts.
- Apply the documentation benchmark rubric before acceptance: clarity, flow,
  simplicity, coverage, understanding, task completion, findability, correctness
  and trust, progressive disclosure, and accessibility and retrievability.
- A major documentation rebuild requires independent review: every rubric item
  must score at least 4/5, the mean at least 4.6, and newcomer clarity,
  simplicity, understanding, and task completion must score 5/5.

## Child DOX Index

- No child AGENTS.md files are currently required.
