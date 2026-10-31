# Recon

**BeGuardit Hacking Tools** — the local, authorization-gated security platform
built and verified on Apple Silicon.

**Created by Parth Patel, founder of BenchBrex.com** (BeGuardit / BenchBrex).

## What's in here

| Directory | System |
|---|---|
| `bg-recon-plugin/` | BG Recon — Hermes plugin: gated TCP scan + host posture audit, baseline diffing, HTML reports |
| `bg-redteam/` | BG RedTeam — 13-case adversarial suite for testing own AI agents, with trend tracking |
| `bg-lab/` | BG Lab — DVWA/Juice Shop local range + 4 stdlib exploit modules behind authorization gates |
| `sable-01/` | Sable-01 — owned offline cyber LLM: envelope guard, frozen eval, tool gate, serving stack (model binaries excluded) |
| `sable-bridge/` | the ask_sable bridge plugin (agent ↔ model) |
| `tools/` | `bgx` — the command center CLI for all four systems |
| `USER-GUIDE.md` | the hands-on manual |
| `BeGuardit-Hacking-Tools-Master-Guide.pdf` | the formal how-to (v2.0) |

## Ground rules

- **Authorization-first**: recon refuses non-allow-listed targets; lab exploits
  run against the local lab only; the model enforces a trained refusal policy.
- **Loopback only**: all listeners bind 127.0.0.1.
- Large artifacts (model weights, adapter binaries, the colima VM disk) are
  intentionally excluded from this repo — see `.gitignore`.

*CONFIDENTIAL — internal to BenchBrex. Not licensed for external use.*
