# Recon

**BeGuardit Hacking Tools** — a proprietary, authorization-gated local security
platform: network/posture reconnaissance, AI red-team harnessing, a containerized
exploitation range, and an owned offline cyber LLM behind a hardening proxy.

**Created by Parth Patel, founder of BenchBrex.com** (BeGuardit / BenchBrex).

| | |
|---|---|
| Platform | macOS 26 · Apple Silicon (M4) · Python 3.11 · MLX |
| Classification | **Proprietary — confidential** (see [LICENSE](LICENSE)) |
| Maturity | v2.6 · frozen eval 27/28 (96%) · tool gate 9/10 · guard 26/26 · recon 34/34 · CI green |
| Security posture | Authorization-first · loopback-only · dual-use policy in [SECURITY.md](SECURITY.md) |

> **Authorized use only.** Every capability in this repository is restricted to
> systems the operator owns or has written authorization to assess. See
> [LICENSE](LICENSE) §3 and [SECURITY.md](SECURITY.md).

## Systems

| Component | What it does | Entry point |
|---|---|---|
| **BG Recon** | Gated TCP/banner scan + listening-service posture, baseline diffing, **web posture** (redirect/HSTS/cookie flags), **TLS posture** (cert, chain, pinned-version handshakes per RFC 8996; `--deep` = vendored testssl.sh), **site map** (bounded sequential crawl + mistake-path probes with anti-bot challenge detection), **Tailscale surface check** (Funnel = critical), per-host **web history diffing** | `bgx recon …` |
| **bgx assess** | One-command engagement: web + TLS + map (+ Tailscale when local), severity-ordered aggregated findings, auto-written engagement record + client-ready HTML | `bgx assess <host>` |
| **bgx zap** | OWASP ZAP baseline scan (spider + passive; ZAP 2.17 + Temurin JDK under `tools/zap/`, gitignored) | `bgx zap <host> --allow-external` |
| **BG RedTeam** | 13-case adversarial suite against the owner's own AI agents; deterministic verdicts (postcheck tamper + canary leaks always fatal; `echo_ok` for refusals that quote the attack); severity-weighted trends | `bgx redteam …` |
| **BG Lab** | Local DVWA range with 4 exploit exercises (SQLi, command injection, XSS, brute force), all allowlist-gated | `bgx lab …` |
| **Sable-01** | Owned offline cyber LLM (Qwen3-4B + LoRA) behind an 8,192-token envelope guard with metrics | `bgx sable …` |
| **sable-bridge** | The agent-facing bridge: exposes the model as a governed tool | Hermes plugin |
| **tools/bg** | `bgx` — the command center for all of the above | `bgx status` |
| **Watchdog** | Weekly owned-site re-check (cron, no LLM); silent unless a new finding appears | `~/.hermes/scripts/web_watchdog.sh` |

## Architecture at a glance

```
Hermes chat / CLI
      │
      ├─ ask_sable ──► guard :8001 ──► mlx :8002 ──► Qwen3-4B + LoRA (offline)
      │                (8,192-tok envelope, rate/queue caps, metrics, zombie recovery)
      ├─ BG Recon ──► owned-host allowlist ──► scan / posture / baseline-diff
      ├─ BG RedTeam ─► hermes one-shot targets ─► deterministic scoring ─► trend
      └─ BG Lab ────► colima (127.0.0.1:8081 allowlist) ─► DVWA exercises
```

## Quick start

```bash
bgx status                  # one-screen health of all four systems
~/sable-01/serve.sh start   # boot the local model (~2.5 GB footprint)
bgx recon posture           # audit this machine's listeners
bgx recon tailscale         # is Funnel/Serve exposing this machine?
bgx assess mysite.example --allow-external   # full owned-site engagement → engagements/
```

Full workflows, per-system manuals and troubleshooting:
**[USER-GUIDE.md](USER-GUIDE.md)** · formal how-to and evidence record:
`BeGuardit-Hacking-Tools-Master-Guide.pdf` · operations: `sable-01/RUNBOOK.md`.

## Verification discipline

Claims in this repository are backed by executed tests, kept current in
`CHANGELOG.md` and the design ledgers (`sable-01/designs/`):

- **Frozen eval**: 28 fixed questions, deterministic scoring — 27/28 (96%).
  Run-5 (T-10/K-04 iteration) was trained three times and **not promoted**:
  best 25/28 — the attempt is kept as evidence in `sable-01/train/`
- **Tool gate**: 10 fixed tool-emission cases — 9/10 (residual T-10 declared;
  run-5 held T-10 PASS 3/3 but regressed elsewhere)
- **Guard unit suite**: 26 tests — 26/26 (macOS, CI)
- **Recon unit suites**: 34 tests — 34/34 (ubuntu, CI)
- **Red-team**: 13 cases — after the echo-verdict fix, 2 prior findings were
  verdict artifacts (refusals that quote the attack now score correctly) and
  3 are confirmed genuine main-agent failures (canary leak, key-material
  echo, path-traversal dump) tracked as runtime-enforcement targets
- **Independent review**: two-round fresh-context review; all P0/P1 fixed and
  confirmed (ledgers in `sable-01/designs/`)

## Repository hygiene

Model weights, adapter binaries, virtualenvs and the container VM disk are
excluded by `.gitignore` — this repo carries code, specs, eval definitions,
runbooks and documentation only. A secrets scan runs before every push.
Runtime artifacts live on the owner's external volume; a clean clone needs that
volume mounted at its canonical path for `bgx doctor` and the serving stack to
pass (the adapter and model directories are intentionally untracked).

Third-party tools are **installed, not vendored**: testssl.sh (GPL) at
`tools/testssl.sh/`, ZAP 2.17 + Temurin JDK at `tools/zap/` — both gitignored
and credited in [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md).

## CI

Every push/PR runs both suites on GitHub Actions (`.github/workflows/ci.yml`):
the guard suite (macOS ARM, MLX tokenizer fetched without weights) and the
recon suites (ubuntu, stdlib-only), plus an attribution sweep over the
documentation set.

## License

Proprietary — all rights reserved, with an authorized-use restriction for
dual-use security capabilities. See [LICENSE](LICENSE). The no-Code-of-Conduct
choice is deliberate: single-maintainer, owner-directed repository.

---

*Created by Parth Patel, founder of BenchBrex.com (BeGuardit / BenchBrex).
CONFIDENTIAL — internal to BenchBrex. Not licensed for external use.*
