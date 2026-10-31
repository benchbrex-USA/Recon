# Contributing to Recon (BeGuardit Hacking Tools)

**Development model:** owner-directed. This is a single-maintainer proprietary
repository — there is no public contribution path. Changes are made by the
owner directly or by agents acting under explicit owner direction.

## Change rules

1. **Substantial changes get an independent review.** Design documents live in
   `sable-01/designs/` with numbered requirements (REQ-xxx) and acceptance
   criteria (AC-xxx). Reviews are run in a fresh context (the Elephant-Goldfish
   process) before implementation; findings are dispositioned in a ledger.
2. **Gates before "done".** A change is complete only when its verification
   ran for real:
   - guard changes: `sable-01: venv/bin/python3 tests/test_guard.py` (23 tests)
   - model changes: tool gate ≥7/10 AND frozen eval ≥26/28
     (`eval/run_tool_gate.py`, `eval/run_eval.py` + `eval/score.py`)
   - recon/redteam/lab changes: the touched module's live verification
   - all: `bgx doctor` reports 15/15
3. **Attribution is mandatory.** Every new artifact carries:
   *Created by Parth Patel, founder of BenchBrex.com (BeGuardit / BenchBrex).*
4. **No secrets in the repo.** Keys live outside the tree. A secrets scan runs
   before every push (see .gitignore for the excluded artifact classes).
5. **Honest reporting.** Never claim a test that did not run. Declared
   residuals (see SECURITY.md §4) are updated, not hidden.

## Commit style

Imperative, specific, one logical change:
`recon v2: unify exposure field name (Goldfish P0-1)`
