---
name: ship
description: Verify, sync state, and commit the current work with a granular message on dev. Only runs when the user invokes it.
disable-model-invocation: true
allowed-tools: Bash(git add *) Bash(git commit *) Bash(git status *) Bash(git diff *)
---

1. Run the `check` skill. Stop if anything fails and report it.
2. Inspect `git diff HEAD` for secrets, `.env` content, `data/` files, real protocol data, debug prints and
   leftover scratch files. Stop and report if any are found.
3. Run the `sync-state` skill and show its diff of `docs/ai` and `CLAUDE.md`.
4. Propose logically scoped commits (one per coherent unit: `feat(scope): ...`, `fix(...)`, `chore(...)`).
   Stage files explicitly by path (never `git add -A`). Confirm the split with the user, then commit on `dev`.
5. Do NOT push unless the user asks. Optionally draft a PR description if requested.
