# Sable-01 — Master Program Document

**Created by Parth Patel, founder of BenchBrex.com** (BeGuardit / BenchBrex / ScopeSable).

Sable-01 is the **owned, offline cybersecurity LLM** for the ScopeSable product
house: TTP explanation on owned lab targets, BenchBrex domain language, and an
enforced refusal policy. It is not a frontier-model replacement — the cloud
default stays stronger; Sable-01 exists for ownership, offline use, domain
slang, and refusal-policy control.

## Locked constraints (from the security-tools skill)

| # | Constraint |
|---|---|
| C1 | Backbone: **Qwen3-4B, Apache-2.0, 4-bit, MLX format** — no from-scratch pretraining. *(Amended 2026-10-29 by owner instruction: original lock was Qwen3-8B; owner delegated backbone choice with a hard memory constraint — "make sure my MacBook's memory doesn't get used up too much" — so 8B→4B, ≈6 GB→≈3 GB resident. Intelligence loss is acceptable: the goal is domain slang + refusal policy, not frontier IQ.)* |
| C2 | Hardware: 16 GB M4 Air → LoRA only, **rank 8–16, 4-bit, batch 1** — no 14B+ |
| C3 | **Eval exists before weights move** — `eval/holdout.jsonl` frozen before any pull/train |
| C4 | **Approval before ~5 GB pulls** — HF id, size, destination named; owner approves |
| C5 | **No frontier-teacher distillation** — no training on GPT/Claude/Grok (or other providers') outputs |
| C6 | Serving goes through local-llm-wiring (oMLX/OpenAI-compatible local endpoint) |

## Refusal policy the model must learn

Any named real third-party target → refuse, then offer exactly three
legitimate equivalents: (1) defensive mirror of the same kill chain, (2) legal
offense on owned lab VMs (Metasploitable/DVWA), (3) the gate curriculum.
Own-lab / written-scope framing → help fully.

## Gate ledger

| Gate | State |
|---|---|
| 0. Program doc | ✅ this file |
| 1. Ownership vs quality decided | ✅ owned backbone, Sable-01 brand |
| 2. Specialize (not pretrain) | ✅ locked: Qwen3-8B + LoRA |
| 3. Hardware budget | ✅ 8B 4-bit LoRA batch 1 |
| 4. **Eval set frozen** | ✅ `eval/holdout.jsonl` — 28 cases (10 refusal, 8 knowledge, 6 lab-ttp, 4 slang) — frozen 2026-10-29, do NOT edit after baselines run |
| 5. Toolchain | ✅ `venv/` + mlx-lm 0.32.2 (GPU backend verified) |
| 6. Base-weight pull | ✅ **approved with delegation** (2026-10-29: "handle it however you see fit, just make sure my MacBook's memory doesn't get used up too much") → `mlx-community/Qwen3-4B-4bit`, ≈2.6 GB → `~/sable-01/base/` |
| 7. Baseline eval (untuned) | ✅ 27/28 (96%) honest baseline — after harness fix (thinking stripped, 3072 tokens); the only real gap was S-03 brand facts |
| 8. Train-data collection | ✅ 42 authored rows → train.jsonl (38) + valid.jsonl (4), provenance in `train/PROVENANCE.md` — buckets: refusal 12, own-lab 10, knowledge 12, brand 8; no frontier outputs (C5) |
| 9. LoRA train + teacher loop | ✅ run 1 done — ckpt 300 selected (frozen eval 27/28, brand gap closed, refusals 10/10 held; see TRAINING-REPORT.md) |
| 10. Serve via local-llm-wiring | ✅ `serve.sh` → mlx_lm.server on 127.0.0.1:8001 (base+adapter, `default_model` id); verified trained answers at 293/2,218/5,518-token prompts (3-16 s). **Envelope:** the full Hermes agent prompt (28,308 tok) kills the generation thread — KV cache ≈4.1 GB spike past the 16 GB GPU wired limit alongside the desktop stack. Supported use: direct API / short prompts; full-agent turns need a dedicated minimal profile (future). Alias `model_aliases.sable-01` wired but only safe for small-prompt contexts. |
| 11. EGM implementation (spec r3, APPROVED) | ✅ Phase 1: envelope guard (`serving/guard.py` on 8001, mlx on 8002) — template-exact 8,192-token gate, model rewrite, 180 s gen timeout, atomic self-clearing zombie marker, queue/rate caps; AC-011 battery passed (413 at 12,816 tok, thread alive). Phase 2: `sable-bridge` plugin (ask_sable, doctor --ci, 1 tool registered); agent turn returns trained fact (AC-005), graceful degradation (AC-006). Phase 3: minimal `sable` profile — 243/15-token prefill (vs 28,308), 5-62 s turns, trained facts (AC-008/009). Design: `designs/sable-agent-integration.md` r3 + review ledger. |

## Directory map

**Physical location since 2026-10-29:** everything lives on the external
volume at `/Volumes/Parth Patel/BeGuardit Hacking Tools/sable-01/`;
`~/sable-01` is a symlink. The volume must be mounted for training/eval —
if symlinks dangle, remount the drive. Same layout as before:

```
sable-01/
├── PROGRAM.md          ← this file
├── eval/
│   ├── holdout.jsonl   ← FROZEN eval set (28 cases)
│   ├── score.py        ← deterministic scorer
│   ├── run_eval.py     ← loads MLX model once, runs all cases, writes predictions
│   └── predictions-baseline.jsonl  ← untuned baseline (17/28 PASS, 61%)
├── base/               ← Qwen3-4B-4bit weights (2.1 GB)
├── train/              ← training data (gate 8 — provenance-tagged)
├── adapters/           ← LoRA adapters + their scores
└── venv/               ← mlx toolchain (mlx_lm 0.32.2, GPU backend)
```
