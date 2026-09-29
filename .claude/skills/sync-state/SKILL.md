---
name: sync-state
description: End-of-session maintenance of docs/ai (STATE, PLANS, DECISIONS, archive) and minimal CLAUDE.md upkeep, within size caps.
---

1. Overwrite `docs/ai/STATE.md` (never append; max 60 lines): current objective, completed this session,
   in progress, modified files, test status, known failures, next exact action.
2. In `docs/ai/PLANS.md`, move finished items to `docs/ai/archive/YYYY-MM.md` (one line: date, ID, commit
   hash) and move their plan file into `archive/`. Promote Next to Now. Add newly found tasks under Later as
   one-liners. Caps: Now 3, Next 7, Later 15, file 60 lines. Index lines only, no prose.
3. Add real architectural decisions to the top of `docs/ai/DECISIONS.md` (date, decision, reason, alternatives
   rejected, plan ID). Never delete; mark superseded. Above 40 entries move the oldest to
   `archive/decisions-YYYY.md`.
4. If a command, convention or structure changed, make the minimal edit to `CLAUDE.md` or the relevant
   `.claude/rules/` file.
5. Enforce caps: CLAUDE.md 150 lines, STATE.md 60, PLANS.md 60, DECISIONS.md 40 entries.
6. There is no external tracker. Note which PLAN.md / DEVPLAN.md item moved, if any, and remind the user to
   update it by hand.
7. Show the diff of `docs/ai` and `CLAUDE.md` changes. Do not commit.
