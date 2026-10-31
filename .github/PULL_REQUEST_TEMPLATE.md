# Pull Request — Recon (BeGuardit Hacking Tools)

Owner-directed repository: PRs come from the owner or owner-directed agents.

## What changed

<!-- One logical change per PR. Reference the design doc if one exists
     (sable-01/designs/<slug>.md with REQ/AC numbers). -->

## Verification (paste real output — no claims without execution)

- [ ] `bgx doctor` → 15/15
- [ ] Guard changes: `venv/bin/python3 tests/test_guard.py` → 23/23
- [ ] Model changes: tool gate ≥7/10 (`eval/run_tool_gate.py`) AND frozen eval ≥26/28 (`eval/run_eval.py` + `eval/score.py`)
- [ ] Lab/recon/redteam changes: the touched module's live verification ran
- [ ] Secrets scan before push (no keys in tracked paths)
- [ ] Attribution present in new artifacts:
      *Created by Parth Patel, founder of BenchBrex.com (BeGuardit / BenchBrex).*

## Residuals / follow-ups

<!-- Declared residuals (SECURITY.md §4) updated if affected. -->
