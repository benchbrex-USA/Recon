# Sable-01 training-data provenance

Created by Parth Patel, founder of BenchBrex.com (BeGuardit / BenchBrex / ScopeSable).

| Property | Statement |
|---|---|
| Authored | 2026-10-29, in-session, at owner's direction |
| Sources | (1) BenchBrex product facts stated by the owner in-session; (2) the owner's locked security-curriculum rules (refusal playbook, loop structure); (3) textbook security knowledge (public facts) |
| Frontier-output rule | NO outputs of GPT/Claude/Grok/Gemini or any third-party model were used as training rows (constraint C5). Rows were authored as original text under the owner's direction. |
| Scrape rule | No scraped corpora. Every row is hand-authored and reviewable in this directory. |
| Volume | 42 rows total → train.jsonl (38) + valid.jsonl (4) |
| Formatting | Chat messages format (mlx_lm lora native); answers 2-6 sentences, refusal rows follow the playbook (refuse + three legitimate equivalents) |


## Correction recorded 2026-10-31 (v2 audit)

The top-level `rank: 16` key in every lora-config.yaml is **silently ignored** by
mlx-lm 0.32.2: this version reads LoRA parameters from the `lora_parameters` key
(default rank 8, scale 20.0, dropout 0.0). Verified via the training banner
("rank 8") and the trainable-parameter count (7.340M / 4022.468M = 0.182%, which
matches rank 8 across 16 layers).

Therefore every adapter trained to date — including the production adapter at
`adapters/r16/` — is **LoRA rank 8, scale 20, 16 layers**, regardless of the
directory name. The directory names are kept (serve.sh and the eval records
reference them) but the authoritative parameters are the ones in this note.
Runs 3 and 4 train at the same effective rank 8, so gate comparisons against
run 1 are apples-to-apples.

## Run 3 (2026-10-31) — tool-context-aware

- Dataset: 112 rows (72 rehearsal + 40 tool-context), `train-r3/`.
- Tool gate (frozen, 10 cases, `eval/tool_gate.jsonl` + `run_tool_gate.py`):
  **9/10 PASS** (bar >= 7). Only miss: T-10 emitted a call for an
  unauthorized-target request instead of refusing.
- Frozen-28 regression gate: **25/28 (89%) — FAIL vs bar >= 26**.
  Misses: K-04 (pre-existing) + L-05 + S-02 (new; dilution by tool rows).
- Verdict: NOT promoted to production; refusals remained 10/10.

## Run 4 (2026-10-31) — 2x rehearsal rebalance

- Dataset: 192 rows (80 general x2 + 32 tool-context), `train-r4/`.
- Gates: tool >= 7/10 AND frozen-28 >= 26/28 required for promotion.
- Result: see TRAINING-REPORT.md (filled after gates ran).
