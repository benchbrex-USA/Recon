# Recon

**BeGuardit Hacking Tools** — a proprietary, authorization-gated local security
platform: network/posture reconnaissance, AI red-team harnessing, a containerized
exploitation range, and an owned offline cyber LLM behind a hardening proxy.

**Created by Parth Patel, founder of BenchBrex.com** (BeGuardit / BenchBrex).

| | |
|---|---|
| Platform | macOS 26 · Apple Silicon (M4) · Python 3.11 · MLX |
| Classification | **Proprietary — confidential** (see [LICENSE](LICENSE)) |
| Maturity | v2.1 · frozen eval 27/28 (96%) · tool gate 9/10 · guard suite 23/23 |
| Security posture | Authorization-first · loopback-only · dual-use policy in [SECURITY.md](SECURITY.md) |

> **Authorized use only.** Every capability in this repository is restricted to
> systems the operator owns or has written authorization to assess. See
> [LICENSE](LICENSE) §3 and [SECURITY.md](SECURITY.md).

## Systems

| Component | What it does | Entry point |
|---|---|---|
| **BG Recon** | Gated TCP/banner scan of owned hosts + listening-service posture audit, baseline diffing, HTML assessment reports | `bgx recon …` |
| **BG RedTeam** | 13-case adversarial suite against the owner's own AI agents; severity-weighted regression trends | `bgx redteam …` |
| **BG Lab** | Local DVWA range with 4 exploit exercises (SQLi, command injection, XSS, brute force), all allowlist-gated | `bgx lab …` |
| **Sable-01** | Owned offline cyber LLM (Qwen3-4B + LoRA) behind an 8,192-token envelope guard with metrics | `bgx sable …` |
| **sable-bridge** | The agent-facing bridge: exposes the model as a governed tool | Hermes plugin |
| **tools/bg** | `bgx` — the command center for all of the above | `bgx status` |

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
```

Full workflows, per-system manuals and troubleshooting:
**[USER-GUIDE.md](USER-GUIDE.md)** · formal how-to and evidence record:
`BeGuardit-Hacking-Tools-Master-Guide.pdf` · operations: `sable-01/RUNBOOK.md`.

## Verification discipline

Claims in this repository are backed by executed tests, kept current in
`CHANGELOG.md` and the design ledgers (`sable-01/designs/`):

- **Frozen eval**: 28 fixed questions, deterministic scoring — 27/28 (96%)
- **Tool gate**: 10 fixed tool-emission cases — 9/10 (residual T-10 declared)
- **Guard unit suite**: 23 tests — 23/23
- **Red-team live baseline**: 13 cases — 8 pass / 5 agent-safety findings
  tracked as the owner's hardening backlog
- **Independent review**: two-round fresh-context review; all P0/P1 fixed and
  confirmed (ledgers in `sable-01/designs/`)

## Repository hygiene

Model weights, adapter binaries, virtualenvs and the container VM disk are
excluded by `.gitignore` — this repo carries code, specs, eval definitions,
runbooks and documentation only. A secrets scan runs before every push.

## License

Proprietary — all rights reserved, with an authorized-use restriction for
dual-use security capabilities. See [LICENSE](LICENSE). The no-Code-of-Conduct
choice is deliberate: single-maintainer, owner-directed repository.

---

*Created by Parth Patel, founder of BenchBrex.com (BeGuardit / BenchBrex).
CONFIDENTIAL — internal to BenchBrex. Not licensed for external use.*
