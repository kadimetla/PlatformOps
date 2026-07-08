---
last_updated: 2026-07-08
owner: platformops-agent maintainers
scope: Claude Code specifically
reviewed_by: unreviewed (first draft)
---

Read `AGENTS.md` first — it's the shared, cross-tool foundation (stack,
conventions, hard rules, workflow, skills catalog). This file adds
Claude-Code-specific detail on top; it never repeats or contradicts
`AGENTS.md`. See `docs/repo_layout_references.md` for every source
behind why both files are shaped this way.

## The repeatable process this project uses for design work
This repo has a consistent habit, established over many design
sessions: **analyze/research before designing, design before building,
and capture every non-trivial design decision as a doc before code
touches it.** Concretely, the loop:

1. **Ground before designing.** Read the actual code (`grep`, not
   assumption) before claiming something is or isn't implemented. For
   third-party services/tools (AWS, MCP servers, other clouds), verify
   against current docs — don't rely on training-data recall for
   fast-moving integrations.
2. **Write the design as a new doc under `docs/`**, not inline chat only,
   when it's substantial enough to matter later. Every doc gets:
   - A `## Status` line at the top stating plainly what's real vs.
     designed-only.
   - A real-vs-designed table for anything with meaningful build status.
   - A `## Sources` section with markdown links, if the doc used web
     research.
   - A `## How this relates to the existing docs` footer — link to
     what it extends or repeats, don't duplicate content that already
     exists elsewhere.
3. **Cross-link it from `docs/HARNESS_DESIGN.md`'s document map** —
   that file is the entry point; a doc that isn't listed there is easy
   to lose.
4. **Correct prior docs in place, with a note, not silently.** When new
   research contradicts an earlier doc (e.g., the IAM tier count, the
   `deploy-to-eks` → `deploy-to-k8s` rename), edit the original with an
   explicit "corrected by X" note rather than deleting the history of
   why the earlier version said what it said.
5. **Only commit when asked. Only push when asked.** Every session in
   this repo has kept those as separate, explicit steps — don't
   collapse them into "wrote the doc" being treated as permission to
   commit.

**Anti-patterns to avoid (Preferred vs. Avoid):**
```
Preferred: edit the original doc, add a note explaining what changed
and why ("corrected by X — AWS's EKS docs split this into two roles"),
leave the rest of the doc's history legible.

Avoid: silently rewriting a section to match new findings, or deleting
the part that turned out to be wrong — that erases the reasoning trail
this whole project depends on.
```
```
Preferred: "Committed as <hash>. Not pushed — say the word."

Avoid: pushing (or committing) as the natural next step after writing
a doc, without being asked — writing content and publishing it are two
separate permissions in this repo.
```

## Skills, concretely — what "Agent Skills" means here
Per Day 3 course material (`docs/course_concepts_and_project_structure.md`
has the full mapping), a Skill is a folder anchored by `SKILL.md`, loaded
via **progressive disclosure**: `name`+`description` are always resident
in context; the full body loads only when `description` matches the
task; bundled `scripts/`/`references/`/`assets/` load strictly on
demand. The `description` field is the entire routing mechanism — it
must state what the skill does *and* when to use it *and* when not to,
front-loaded with trigger keywords.

**Before extending `harness/` to hand-build a `load_skill()` mechanism**:
verify whether ADK's `SkillToolset` class already provides this
natively (per the same course material) — installing `google-adk` and
checking its actual API surface, not re-deriving it from a course PDF's
description. This project's own established habit (see Hard rules in
`AGENTS.md`) is not to build something that already exists unverified.

## This project's document-writing style, if you're adding to `docs/`
Terse, grounded, file:line-referenced. No filler summaries. State the
finding, then the implication, then what it changes about prior design
— in that order. Tables over prose where there's more than three
things being compared. Don't restate a whole prior doc's reasoning;
link to it.
