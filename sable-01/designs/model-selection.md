# Sable-01 Model Selection Record

**Created by Parth Patel, founder of BenchBrex.com** (BeGuardit / BenchBrex).
Applied: ml-model-selection procedure, 2026-11-01, on production state (run-4 adapter live).

## Step 1 — Memory budget

| Measurement | Value | Method |
|---|---|---|
| Model server footprint, idle | **2,356 MB** | `footprint <mlx-pid>` (private + wired pages) |
| Model server footprint, under generation | **2,480 MB** | same, during a live 128-token generation |
| Guard process | ~20-30 MB | RSS (no model weights) |
| **Selection-rule budget** | **3,000 MB resident** | ml-model-selection skill |

Note on method: `ps` RSS understates MLX residency because model weights are
memory-mapped; footprint is the honest measure. An earlier v2 note claiming
"~1.3 GB total" used RSS and is corrected by this record.

Budget context: 16 GB machine; macOS + Hermes desktop + gateway consume the
majority; the container lab (colima, ~3-4 GB) must be able to coexist or run
immediately after serving stops. The 3 GB selection rule preserves that
coexistence and leaves headroom for KV-cache growth bounded by the guard's
8,192-token envelope (the historical 28K-token thread death is the
unbounded-context failure mode the envelope exists to prevent).

## Step 2 — Selection

| Candidate | Est. footprint | Decision |
|---|---|---|
| **Qwen3-4B, 4-bit (g64)** — 36 layers, hidden 2560 | **2.36-2.48 GB measured** | **SELECTED** — under budget, headroom for load |
| Qwen3-8B, 4-bit | ~4.7-5 GB | REJECTED — exceeds the 3 GB rule; breaks lab coexistence; swap risk under load |
| Larger / fp16 variants | ≥ 8 GB | REJECTED — same, and no quantized headroom |

LoRA adapter cost: rank 8, 7.34M params, 28 MB file — negligible against the budget.

## Conclusion

**Qwen3-4B-4bit is the correct selection under the 3 GB rule, with measured
evidence (2.36-2.48 GB footprint).** The capability ceiling this implies is
compensated by the LoRA domain training (frozen eval 27/28, tool gate 9/10).
Selection is re-checked whenever: the base model changes, the adapter rank
changes materially, or the envelope is raised.
