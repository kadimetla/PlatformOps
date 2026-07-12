# Contributing to PlatformOps

This repo uses [OpenSpec](https://github.com/Fission-AI/OpenSpec) to track
**going-forward implementation work** — proposing, designing, and
implementing concrete code changes. It does **not** replace this repo's
existing design-documentation habit; see "How this relates to `docs/`"
below before you reach for it on something that isn't ready to be built
yet.

## Setup

OpenSpec requires **Node.js 20.19.0+**. Check your version first
(`node --version`) — this repo's default system Node may be older; if so,
use a version manager (Volta, nvm, fnm) to get a compatible one rather
than upgrading system Node globally.

```bash
npm install -g @fission-ai/openspec@latest   # or: volta install @fission-ai/openspec
openspec --version                            # confirm it's on PATH
```

Already initialized in this repo for **Claude Code, Codex, and Gemini
CLI** — `openspec/config.yaml` and the tool-specific integration files
(`.claude/`, `.codex/`, `.gemini/`) are checked in, so no setup is needed
to start using `/opsx:*` with any of those three. Each tool gets its own
integration in its own convention (Claude Code and Gemini CLI both get
skills plus slash-command files; Codex gets skills only, no separate
command files) — but all three read and write the same `openspec/`
source of truth, so it doesn't matter which tool a given contributor
uses for a shared change.

If you're setting this up somewhere it isn't yet, or want to add another
tool from OpenSpec's supported list (`amazon-q`, `antigravity`, `auggie`,
`cursor`, `github-copilot`, `windsurf`, and others — run `openspec init
--help` for the full list):

```bash
openspec init --tools claude,codex,gemini   # re-running with the full
                                              # desired set is additive —
                                              # confirmed: it "refreshes"
                                              # tools already set up
                                              # rather than dropping them
```

**Known gotcha**: `openspec` commands print a PostHog telemetry error
(`ReferenceError: Blob is not defined`) on every invocation in some Node
environments. It's cosmetic — the command still completes and the output
below it is real. Ignore it.

Also make sure the Python side is set up per `README.md` (`uv sync
--extra dev`) — OpenSpec tracks the work, it doesn't replace running the
actual test suite before you consider a task done.

## The workflow

Every unit of implementation work is a **change**, living in
`openspec/changes/<kebab-case-name>/`, with four artifacts built in
dependency order:

```
proposal.md  →  design.md + specs/**/*.md  →  tasks.md  →  (implement)  →  archive
   (why)            (how)      (what)         (checklist)
```

**1. Propose.** Either type `/opsx:propose "<what you want to build>"` in
chat, or run the CLI directly:
```bash
openspec new change "<kebab-case-name>"
openspec status --change "<name>" --json      # shows what's next, in order
```
`proposal.md` states *why* — the problem, what changes, and which
**capabilities** (kebab-case, one per `specs/<capability>/spec.md`) are
new or modified. Get this artifact's exact template with:
```bash
openspec instructions proposal --change "<name>" --json
```
Do the same for `design`, `specs`, and `tasks` once their dependencies
are satisfied (`openspec status` tells you when each is `ready` vs.
`blocked`).

- `design.md` — the *how*: context, goals/non-goals, decisions with
  alternatives considered, risks with mitigations, migration plan, open
  questions. Skip it for trivial changes (the schema's own instructions
  say when it's warranted).
- `specs/<capability>/spec.md` — the *what*, as testable requirements.
  Use `### Requirement:` + SHALL/MUST language, and `#### Scenario:`
  blocks (exactly four hashtags — three silently fails to parse) with
  **WHEN**/**THEN** bullets. Every requirement needs at least one
  scenario.
- `tasks.md` — a dependency-ordered checklist, `- [ ] N.M description`.
  This is what `/opsx:apply` parses to track progress — don't use any
  other checkbox format.

**2. Validate before implementing.**
```bash
openspec validate --changes
```
Catches malformed scenario headers and missing requirement/scenario
pairs before you write code against them.

**3. Implement.** `/opsx:apply [change-name]` (omit the name if only one
change is active) reads all four artifacts, works through `tasks.md` in
order, and checks off each task as it's completed. **If implementation
reveals the design was wrong, it pauses and asks rather than silently
diverging from the spec** — this happened for real on the first change in
this repo (`wire-plan-request-envelope`): the spec claimed a guarantee
the actual agent tool wiring didn't support yet, and the right move was
to stop and flag it, not quietly narrow scope or overclaim in the spec.
Expect this to happen; it's the workflow working as intended, not a
failure.

**4. Archive.** Once all tasks are done and verified (tests pass, the
behavior matches the specs), `/opsx:archive` moves the change to
`openspec/changes/archive/<date>-<name>/` and merges its capability specs
into `openspec/specs/` — the persistent, cross-change source of truth for
"what does this system currently do." Future proposals that touch an
already-archived capability create a **delta spec** (`## MODIFIED
Requirements`, copying the full existing requirement block and editing
it) against that source of truth, not a fresh one.

**Explore first, if the shape of the work isn't clear yet.**
`/opsx:explore` is a thinking-partner mode for working through options
before committing to a proposal — use it the same way this repo already
uses a research-before-designing pass for bigger architectural questions
(see `CLAUDE.md`), just scoped to one concrete feature instead of a whole
subsystem.

## How this relates to `docs/`

`docs/*.md` and OpenSpec serve **different phases**, not the same one:

| | `docs/*.md` | OpenSpec |
|---|---|---|
| Question it answers | "What should this system do, and why?" | "How do I implement something already decided?" |
| Scope | Whole subsystems, architecture, cross-cutting design | One concrete, implementable change |
| Lifecycle | Living documents, corrected in place with a note when superseded | Proposed → implemented → archived |
| Audience | Anyone trying to understand a design decision | Whoever's about to write the code |

**Don't use OpenSpec to reorganize the existing `docs/` corpus** — it's
built for tracking new, incremental proposals, not restructuring ~70
files of already-completed design work. And don't skip `docs/` for a
genuinely new architectural question just because OpenSpec is faster to
reach for — if the answer isn't already designed somewhere in `docs/`,
that's still a research-and-design pass first, the same as always.
A proposal's `design.md` should *cite* the relevant `docs/*.md` files
(see `wire-plan-request-envelope/design.md` for a worked example — it
consolidates three already-completed design docs into one implementation
plan) rather than re-deriving decisions that already exist.

## Commit and push discipline

Unchanged from the rest of this repo: only commit when asked, only push
when asked (`CLAUDE.md`). Creating or updating an OpenSpec proposal is a
"write it up" step like any other doc — pause for confirmation before
committing, same as everything else in this repo's history.
