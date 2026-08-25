# Documentation

## Purpose

- Use Sley to teach graph construction from a first successful path through
  advanced, transferable design judgment and exact runtime semantics.
- Serve humans and coding agents from one accurate Markdown source.

## Ownership

- Owns the public GitBook content, navigation, examples catalog, redirects,
  writing standards, and documentation checks.
- The RFC, conformance fixtures, tests, and public facades remain semantic
  authorities; documentation explains them without redefining them.

## Audience and Communication

- The primary reader is a Python or TypeScript application developer whose
  once-linear workflow now branches, loops, fans out, joins, or recovers from
  failure. They want readable in-process orchestration without adopting a
  platform or hiding their code behind framework roles.
- Assume the reader can install a package, read functions, and follow ordinary
  async code. Do not assume graph-runtime vocabulary, prior Sley knowledge, or
  patience for learning abstractions before seeing their payoff.
- Begin from first principles without talking down to the reader. Define every
  graph concept in the early journey, keep examples concrete, and remove
  scaffolding as understanding grows. By the end, expect the reader to reason
  as an advanced graph author rather than continue repeating beginner recipes.
- Secondary readers are experienced graph-runtime users evaluating exact
  behavior and PocketFlow or Caskada users migrating existing work. Serve them
  through Guides, Reference, and About after the newcomer path stays clear.
- The reader is reasonably skeptical: a graph library might add more ceremony
  than it removes, obscure execution, or claim ownership of their application.
  Show the small model in code, explain behavior at the moment it matters, and
  state boundaries without apology or sales jargon.
- Speak like one experienced engineer helping another: direct, warm, concrete,
  and respectful. Address the reader as `you`, acknowledge the problem that
  brought them to the page, and prefer consequences over abstract definitions.
  Never sound like a catalog, standards document, or generic AI-generated tour
  outside Reference pages that require that precision.
- The communication goals are for the reader to recognize their pain on the
  landing page, reach useful output without ceremony, hold the core model in
  working memory, add one concept at a time to the same evolving workflow,
  understand Sley's boundaries, and always know the next useful action. The
  completed journey must also teach transferable graph construction: choosing
  node boundaries, designing topology and data flow, placing fan-in and scope
  boundaries, containing cycles and failures, and testing observable behavior.
- Success is reader independence, not API recall. Use Sley as the concrete
  vehicle for teaching how to model, explain, test, diagnose, and evolve graph
  systems. A reader who finishes Learn should be able to defend a graph design,
  recognise unnecessary complexity, and carry that judgment to other runtimes.

## Local Contracts

- Keep the public journey within Start, Learn, Guides, Patterns, Reference,
  Examples, and About. A new page must earn its place by reducing reader effort
  or owning a distinct contract.
- The Quickstart is provider-free, dependency-free beyond Sley, runnable in one
  file, and takes the shortest clear path to visible output.
- Keep the first-run path free of compatibility trivia and implementation
  commentary that does not change the reader's next action. Put supported
  runtime versions and packaging detail in the language references.
- Keep distribution names explicit: Python installs and imports `sley`, while
  TypeScript installs and imports `@jigging/sley`.
- Teach shared behavior once with paired Python and TypeScript examples. Keep
  language-specific signatures in their own reference pages.
- Every page starts with a concise `description` frontmatter value, defines new
  terms at first use, exposes prerequisites through sequence or prose, and ends
  with the next useful action when one exists.
- Learn pages build the mental model in dependency order. Guides solve one task.
  Reference pages state exact contracts. Examples demonstrate complete uses.
- Start and Learn use one evolving release workflow. Each lesson begins with a
  problem created by the previous version, changes only what that problem
  requires, and reconnects the new mechanism to the reader's working model.
- Teach why a graph is designed a certain way, not only how to spell it in
  Sley. Name alternatives, tradeoffs, and graph smells once the reader has the
  concepts needed to judge them.
- Give each Learn lesson an observable mechanism, the design judgment behind
  it, one failure mode or misconception to recognise, and a small experiment
  that lets the reader change the graph and predict the result.
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
- Lead the landing page with the user pain Sley removes, one credible promise,
  and compact working code. Sell the resulting status and simpler mental model
  before listing capabilities. Bridge changes of context explicitly, and avoid
  estimated completion times. Put boundaries after the value is clear.
- Prefer one causal example over several disconnected fragments. Prefer graph
  definition code over a diagram when it communicates the topology as clearly;
  every remaining diagram must make a flow easier to understand than the same
  code or prose. Never use a diagram as proof, decoration, or a compulsory
  restatement of a concept; omit it unless its teaching purpose is explicit.
- Open a Learn page with why the next concept is needed, a Guide with the
  concrete situation that sends a reader there, and a Reference page with the
  fastest path to the exact contract. Do not begin with "This page" narration.
- End teaching pages by naming what the reader can now do and why the next page
  is the natural next problem, rather than attaching a mechanical next link.
- Keep paragraphs short, headings descriptive, link text meaningful, and code
  blocks directly usable. Avoid unsupported claims, undefined jargon, and
  framework internals before the reader needs them.
- Preserve valuable public URLs with `.gitbook.yaml` redirects when pages move.
- Treat the Python and TypeScript ports as peers. Explain genuine host-language
  differences without forcing artificial syntax parity.

## Verification

- Run `node .github/scripts/check-docs.js` for navigation, frontmatter,
  published-path, redirect, local-link, and public-export integrity.
- Run `node .github/scripts/check-doc-examples.js` to execute and type-check
  every Sley-importing Python and TypeScript block on its teaching-page list.
  An import on those pages marks a block as a complete runnable example; keep
  explanatory excerpts import-free.
- Run `node .github/scripts/generate-examples.js` after cookbook README changes;
  a second run must leave no diff.
- Run primary documentation examples in both languages and check their shown
  output.
- Run Prettier and `git diff --check` over changed documentation and scripts.
- Apply the documentation benchmark rubric before acceptance: clarity, flow,
  simplicity, coverage, understanding, task completion, findability, correctness
  and trust, progressive disclosure, and accessibility and retrievability.
- A major documentation rebuild requires independent review: every rubric item
  on every page must score at least 4.5/5, correctness and trust must score 5/5,
  the corpus mean must reach 4.8, and newcomer clarity, simplicity,
  understanding, and task completion must score 5/5.

## Child DOX Index

- No child AGENTS.md files are currently required.
