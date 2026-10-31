# Sable-01 Runbook

**Created by Parth Patel, founder of BenchBrex.com** (BeGuardit / BenchBrex).

Operational playbook for the local Sable-01 stack: envelope guard (127.0.0.1:8001)
in front of mlx_lm.server (127.0.0.1:8002, base + LoRA ckpt r16).

## Daily operation

```bash
~/sable-01/serve.sh start      # mlx → guard; both health-checked; ~3 GB RAM
~/sable-01/serve.sh status     # guard health, backend, zombie marker state
~/sable-01/serve.sh test       # short fact + over-envelope 413 + follow-up battery
~/sable-01/serve.sh stop       # drains in-flight (≤30 s), then stops both
```

- The server holds **~2.4-2.5 GB measured footprint** while running (weights are
  memory-mapped — RSS understates it); `stop` releases it. colima/BG Lab should
  stay stopped while serving (memory constraint). Selection record:
  `designs/model-selection.md`.
- Everything binds **127.0.0.1 only**. Never expose 8001/8002.

## Symptom → fix

| Symptom | Cause | Fix |
|---|---|---|
| `503` + `X-Sable-Zombie: true` | generation thread died (verified KV-spike class) | `serve.sh restart` — the startup generation-probe clears the marker only if the thread is actually alive |
| `504 generation timeout` | backend accepted but didn't answer in 180 s | retry once; if persistent → `serve.sh restart` |
| `502 mlx server not running` | backend down | `serve.sh start` |
| `413 prompt is N tokens` | prompt over the 8,192-token envelope | send a short, self-contained question (this is the guard working — the alternative is a crashed thread) |
| `429 rate limit exceeded` | > 60 requests/min | wait ≤ 60 s (sliding window) |
| `503 server busy` | > 2 in-flight + 4 queued | retry after ~5 s (Retry-After header) |
| `400 …` | malformed request | fix the field named in the error |
| Tool says "Sable-01 timed out after 120 s" | the bridge gave up before the guard's 180 s | retry once; the model may be thinking long |

## Recovery ladder

1. `serve.sh restart` — fixes zombie/thread states (the startup probe verifies the
   thread with a real 8-token generation; a naive /v1/models probe would false-clear).
2. `serve.sh stop && serve.sh start` — full reload.
3. `hermes -p sable config get model_aliases.sable-01` — if the profile lost its alias,
   re-set it (model `default_model`, provider `custom`, base_url `http://127.0.0.1:8001/v1`).
4. Last resort: re-verify the adapter is intact (`ls adapters/r16/`) and re-run
   `tests/test_guard.py` (21 unit tests) to isolate guard vs backend.

## Known envelope (verified)

- Prompts ≤ ~5,500 tokens: correct answers in 3–16 s. 8,192-token hard gate.
- One 28K-token thread death observed 2026-10-29 under memory pressure; a 28,016-token
  retry on 2026-10-31 did NOT reproduce it — treat large prompts as
  memory-state-dependent and always use the guard.
- LoRA run 2 (tool-format) FAILED its gate (1/10 tool emission) and is NOT served;
  run-1 (r16) is the production adapter. Run-3 would need tool-context-aware training.

## Test suite

```bash
venv/bin/python3 tests/test_guard.py   # 21 unit tests — run after any guard change
```

Covers: validation matrix, model rewrite, envelope 413, zombie marker write/clear,
504 branch, 502 branch, busy 503, rate 429, shutdown rejection, oversized body,
content coercion, health shape.


## v2 additions (2026-10-31)

- **`bgx` command center** (`~/bin/bgx`): `bgx status` (all systems), `bgx doctor`
  (deep check incl. 23-test unit suite), `bgx report` (JSON to status_report.json),
  plus dispatch: `bgx recon posture|scan|baseline-save|baseline-diff|report`,
  `bgx redteam list|run|trend OLD NEW`, `bgx lab up|down|status|sqli|cmdi|xss|brute`,
  `bgx sable start|stop|status|test`. Aggregate exit 0 healthy / 1 attention.
- **Posture baseline monitoring**: `bgx recon baseline-save` snapshots the listener
  state; `bgx recon baseline-diff` flags added/removed/new-LAN-exposed services
  (verified in both directions); `bgx recon report` writes an HTML assessment.
- **Guard /metrics**: `curl 127.0.0.1:8001/metrics` -> uptime, request counts by
  status, generation latency p50/p95 (last 200). Use for capacity and health trends.
- **Production adapter is `adapters/r16-run4`** (promoted 2026-10-31): tool gate
  9/10, frozen eval 27/28 (96%), refusals 10/10. Rollback: serve.sh ADAPTER line
  back to `adapters/r16`.
- **Tool-emission gate**: `venv/bin/python3 eval/run_tool_gate.py <adapter>` runs
  the frozen 10-case suite (bar >= 7/10). Known residual T-10: unauthorized-target
  request inside a tool context gets a tool call instead of a refusal.
- **Rank truth**: all adapters train at LoRA rank 8, scale 20 (mlx-lm reads
  `lora_parameters`, ignoring top-level `rank:`); verified from safetensors
  headers. "r16" is a directory name, not a parameter. Measured stack residency:
  ~1.3 GB total (mlx 1008 MB + guard 297 MB).
