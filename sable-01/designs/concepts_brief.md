# Concept brief: Sable-01 agent integration (minimal-profile persona)

Status: EXPLORING
Source context inspected: `sable-01/PROGRAM.md` (gate ledger), `sable-01/TRAINING-REPORT.md`,
`sable-01/serve.sh`, `sable-01/serve.log` (thread-death traceback), frozen-eval results
(`eval/predictions-*.jsonl`), Hermes profile-isolation behavior (user's environment notes),
`hermes-agent` skill providers reference (`model_aliases` schema). All facts below were
verified in-session 2026-10-29/30 unless tagged UNVERIFIED.

## Problem and outcome

- **Who is affected:** the owner (Parth) — Sable-01 (Qwen3-4B-4bit + LoRA, gates 0–10 complete)
  serves trained BenchBrex facts on 127.0.0.1:8001 but could not participate in Hermes
  agent turns (as-built: it now does — `sable` profile + `ask_sable` bridge tool).
- **Concrete pain:** the full Hermes agent system prompt is **28,308 tokens**; its KV cache
  spikes ≈4.1 GB on top of 2.7 GB weights and kills the mlx_lm.server generation thread
  (verified: serve.log traceback + 20.5-minute one-shot failure). Short prompts (293–5,518 tok)
  answer correctly in 3–16 s (verified envelope probe).
- **Measurable outcome:** a supported path where Sable-01 answers agent-driven questions
  reliably, in seconds not minutes, without crashing the server, and without breaching the
  owner's memory constraint ("make sure my MacBook's memory doesn't get used up too much").

## Constraints and boundaries

- 16 GB M4 Air; GPU wired limit ≈10.7 GB shared with the desktop stack. Sable server ≈3 GB
  resident. colima + lab containers must stay stopped while serving (verified practice).
- Serving is **localhost-only** by design; no external binding.
- Sable-01's refusal policy is *trained* (soft), not enforced — any tool access must be gated
  at the tool layer (the `check_target` authorization-gate pattern), never by trusting the model.
- 4B tool-calling reliability: **VERIFIED 2026-11-01** — frozen tool gate 9/10 on
  `adapters/r16-run4` (residual T-10: unauthorized-target emission).
- mlx_lm.server quirks (verified): `default_model` is the only request id that maps to the
  adapter; after a generation-thread death the server becomes a zombie until restarted.
- External volume dependency: all artifacts live under `/Volumes/Parth Patel/BeGuardit Hacking
  Tools/`; unmounted drive = dangling paths.

## Candidate approaches

| Option | Mechanics | Advantages | Costs/risks | Status |
|---|---|---|---|---|
| **A. Dedicated minimal Hermes profile** | `sable` profile with a tiny SOUL (few hundred tokens), restricted/zero toolsets, alias → mlx server | real agent loop driven by the owned model; profile isolation (own skills/memories/cron); no 28K prompt | profile plumbing; 4B tool-calling reliability UNVERIFIED; tool misuse risk if tools are granted; ~3 GB resident while serving | candidate |
| **B. Knowledge-microservice tool** | main (cloud) agent gains a tool/plugin `ask_sable(question)` that calls localhost:8001 with the bare question; orchestration stays on the cloud model | 28K prompt never reaches Sable-01; smallest memory delta; no profile machinery; cloud quality drives reasoning | Sable-01 never drives; adds a plugin/tool to the main profile; answer quality bounded by the 4B | candidate |
| **C. Envelope guard** | server-side rejection of prompts > N tokens with a clean 413-class error instead of thread death + zombie | robustness against any caller; removes the crash-then-zombie failure mode; cheap | does not enable agent turns by itself | complementary |

## Edge cases and risks

- **Server zombie after thread death** (verified failure mode): retries hit a dead thread returning
  404s. Option C converts this to a clean rejection; a watchdog restart is a possible add-on.
- **Dual-use exposure (option A):** a cyber-trained model inside an agent loop with terminal/file
  tools could execute harmful actions despite trained refusals. Tool-level authorization gates are
  mandatory if A is chosen with tools; zero-tool variant avoids the class entirely.
- **External volume unmounted:** model paths and serve.sh dangle; server must fail loudly.
- **Concurrency:** mlx server behavior under parallel requests is UNVERIFIED (likely serial).
- **Memory contention:** serving (~3 GB) alongside the desktop stack is verified OK; adding a
  second resident model or colima simultaneously is not. (As-built footprint:
  2.36 GB idle / 2.48 GB under generation.)
- **Data:** training rows are owned material (PROVENANCE.md); privacy exposure is minimal.

## Decisions and unknowns

| ID | Question / decision | Recommendation | Owner | Status |
|---|---|---|---|---|
| D1 | Architecture: A (agent profile) vs B (microservice tool) vs defer | **Owner chose ALL, phased (2026-10-30):** Phase 1 = C (envelope guard); Phase 2 = B (ask_sable microservice tool for the main agent); Phase 3 = A (minimal `sable` profile, zero tools); A-with-tools only after U2 probe | Parth | DECIDED — phased |
| D2 | Include envelope guard (C) regardless of D1? | Yes — it fixes a verified crash-zombie failure mode | Parth | OPEN (bundled with D1) |
| D3 | If A ever chosen: which tools, under what gates? | Zero tools first; tool-level authorization gates mandatory later | Parth | OPEN |
| U1 | Minimal achievable Hermes system-prompt size for a `sable` profile | Measure before choosing A | Elephant | UNVERIFIED |
| U2 | Qwen3-4B tool-call format compliance under mlx_lm | Probe test required | Elephant | UNVERIFIED |
| U3 | mlx server concurrency behavior | Probe or accept serial | Elephant | UNVERIFIED |

## Next step

Draft a spec (`docs/designs/sable-agent-integration.md`) after the architecture owner picks
D1. The environment supports genuine fresh-context subagent review, so the Goldfish pass can
be truly INDEPENDENT (delegate_task with a bounded packet).
