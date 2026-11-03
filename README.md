# Recon — BeGuardit Hacking Tools

Proprietary, authorization-gated security-assessment platform for one operator:
owned-host reconnaissance, website and TLS posture, an AI red-team harness, a
local exploitation range, and an offline cyber model behind a hardening proxy.

**Created by Parth Patel, founder of BenchBrex.com** (BeGuardit / BenchBrex).

| | |
|---|---|
| Repository | [benchbrex-USA/Recon](https://github.com/benchbrex-USA/Recon) (private) |
| Platform | macOS 26 · Apple Silicon · Python 3.11 · MLX |
| Classification | Proprietary — confidential. [LICENSE](LICENSE) |
| Current release line | v2.6 (see [CHANGELOG.md](CHANGELOG.md)) |
| Maintainer | Parth Patel, founder of BenchBrex.com |
| Security contact | Private report only. [SECURITY.md](SECURITY.md) |

> **Authorized use only.** Every network and exploit capability is restricted to
> systems the operator owns or has written authorization to assess. Public hosts
> are refused unless `--allow-external` is passed on that command. Do not remove
> those gates. [LICENSE](LICENSE) §3 · [SECURITY.md](SECURITY.md).

## What this is

One command center (`bgx`) over four systems that already exist on the owner's
machine. It is not a general-purpose scanner product and it is not licensed for
external use.

| System | Job |
|---|---|
| **BG Recon** | What is listening, what changed, and what an owned site is exposing |
| **BG RedTeam** | Whether the owner's own AI agent resists injection and tool abuse |
| **BG Lab** | Practice exploits against a local DVWA container, and nothing else |
| **Sable-01** | An owned offline model for security questions, behind an envelope guard |

The agent-facing bridge is `sable-bridge` (`ask_sable`). Engagement records land
in `engagements/`. Design specs and review ledgers live in `sable-01/designs/`.

## Why it exists

Cloud models and generic scanners do not know this host, this allowlist, or
this operator's authorization boundary. This toolchain keeps reconnaissance,
lab practice, and model inference on the machine that owns them, with gates
that fail closed.

## Who it is for

The owner, and agents acting under explicit owner direction. There is no public
contribution path. See [CONTRIBUTING.md](CONTRIBUTING.md).

## Requirements

- macOS on Apple Silicon. The guard CI job uses a macOS ARM runner because MLX
  does not run elsewhere.
- Python 3.11 for the toolchain. Sable-01 uses its own venv under `sable-01/`.
- `bgx` on `PATH` (`~/bin/bgx` → `tools/bg` on the canonical volume).
- The external volume mounted at `/Volumes/Parth Patel/BeGuardit Hacking Tools`.
  Home paths (`~/sable-01`, `~/bg-lab`, `~/bg-redteam`, the bg-recon plugin) are
  symlinks into that volume. A clone without the volume mounted cannot serve
  the model or pass `bgx doctor`.
- Optional, installed locally and **not** committed (see
  [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md)):
  - `tools/testssl.sh/` — testssl.sh 3.2.4 (GPL), used by `tls --deep`
  - `tools/zap/` — OWASP ZAP 2.17.0 and a Temurin JDK, used by `bgx zap`
- Colima, only when the lab is up. Do not run the MLX stack and the lab
  containers at the same time (one-heavy-system rule).

## Quick start

```bash
bgx status                         # one-screen health; exit 0 or 1
bgx doctor                         # files, ports, adapter, imports
~/sable-01/serve.sh start          # guard :8001, model :8002
bgx recon posture                  # listeners on this machine
bgx recon tailscale                # Funnel / Serve / SSH / exit-node
```

Stop when finished:

```bash
~/sable-01/serve.sh stop
python3 ~/bg-lab/lab.py down      # only if the lab was started
```

Day-to-day procedures: [USER-GUIDE.md](USER-GUIDE.md) (v2.0, 2026-11-01 — the
command surface below is newer; prefer this README for v2.2–v2.6 commands).
Formal how-to: `BeGuardit-Hacking-Tools-Master-Guide.pdf`. Operations:
`sable-01/RUNBOOK.md`.

## Command reference

`bgx` is the only entry point. The binary name is `bgx`, not `bg` (`bg` is a
shell builtin). Exit codes: **0** healthy or no high findings, **1** attention
or a failed check, **2** usage (missing target, missing `--allow-external` on
a public host).

### Health

| Command | What it does |
|---|---|
| `bgx status` | Stack, recon baseline diff, red-team case count, lab state. A new LAN-exposed listener marks the verdict unhealthy. |
| `bgx doctor` | Deep verification of files, ports, adapter, and imports. |
| `bgx report [path]` | Machine-readable JSON. Default: `<volume>/status_report.json`. |

### Assessment (owned hosts)

Public targets require `--allow-external` on that invocation. That flag is the
written acknowledgment that the caller owns the host or has scope. It is not a
default.

| Command | What it does |
|---|---|
| `bgx assess <host> [--deep] [--allow-external]` | One engagement: web + TLS + site map. Adds the Tailscale check when the target resolves to this machine. Writes Markdown and HTML under `engagements/`. |
| `bgx recon posture` | Local listeners, LAN exposure, AI runtimes, secret-file permissions. |
| `bgx recon scan <target> [ports] [--allow-external]` | TCP connect + banner. Default port set if omitted. |
| `bgx recon web <host> [--path /] [--allow-external]` | Header posture: HTTP redirect, HSTS (RFC 6797 §8.1), `Set-Cookie` Secure/HttpOnly, `X-Powered-By`. GET only. Cookie values are redacted. |
| `bgx recon tls <host> [--deep] [--allow-external]` | Certificate, chain verify, pinned TLS 1.0–1.3 handshakes (RFC 8996). `--deep` runs vendored testssl.sh. |
| `bgx recon map <host> [--allow-external]` | Bounded sequential crawl (≤80 GETs): sitemap, same-host links, a fixed mistake-path list. Anti-bot interstitials are reported as unverified, not exposed. |
| `bgx recon web-history <host>` | Diff of finding IDs between the last two `web` runs for that host. |
| `bgx recon baseline-save` | Snapshot local listeners to `state/baseline.json`. |
| `bgx recon baseline-diff` | Added, removed, and new LAN-exposed listeners since the snapshot. |
| `bgx recon report` | One-page HTML posture report. |
| `bgx recon tailscale` | Read-only. Funnel on = critical. Never changes Serve, Funnel, ACLs, or routes. |
| `bgx zap <host> --allow-external` | OWASP ZAP baseline (spider + passive rules). Refuses without the flag. |

### Red team, lab, model

| Command | What it does |
|---|---|
| `bgx redteam list` | Case ids, severity, names. |
| `bgx redteam run` | Every case, via `hermes -z`, against a harness-owned sandbox. |
| `bgx redteam trend <older.json> <newer.json>` | Exit 1 if the newer run regressed. |
| `bgx lab up\|down\|status` | DVWA on `127.0.0.1:8081`. |
| `bgx lab sqli\|cmdi\|xss\|brute` | Allowlisted lab exercises. Other targets are refused. |
| `bgx sable start\|stop\|status\|test` | Wraps `sable-01/serve.sh`. |

Owned-site watchdog (not a `bgx` subcommand): `~/.hermes/scripts/web_watchdog.sh`,
cron job `beguardit-web-watchdog`, Mondays 10:00 IST. It re-runs `bgx recon web`
and speaks only when a **new** finding id appears.

## Architecture

```
Hermes chat / CLI
      │
      ├─ ask_sable ──► guard :8001 ──► mlx :8002 ──► Qwen3-4B + LoRA (offline)
      │                envelope 8192 tokens · rate/queue caps · /metrics
      │                zombie marker · GET limited to /v1/ /health /ready /metrics
      │
      ├─ bgx assess ─► web + tls [+ testssl --deep] + map
      │                └─ engagements/<date>-<host>.assess.md + .html
      │
      ├─ bgx recon ──► authorization() ──► scan | posture | web | tls | map
      │                public hosts refused unless --allow-external
      │
      ├─ bgx zap ────► ZAP baseline (passive) ──► engagements/zap-*.log
      │
      ├─ BG RedTeam ─► hermes -z ──► sandbox postchecks + canary
      │                echo inside a refusal is not a fail (echo_ok)
      │                canary leak and postcheck tamper always fail
      │
      └─ BG Lab ─────► 127.0.0.1:8081 only ──► DVWA exercises
```

Ports: guard **8001**, model **8002**, lab **8081**. The model servers bind
loopback. A listener on `*` is a posture finding, not a feature.

## Authorization model

1. Resolve the target.
2. If every address is loopback or private, allow.
3. If any address is public, allow only when that command was given
   `--allow-external`.
4. Lab exploits ignore that flag. Their allowlist is `127.0.0.1:8081` and
   `localhost:8081`.
5. Tailscale checks are local and read-only. Turning Funnel or Serve on is an
   owner action; this repo will not do it.

## Verification

Numbers below are from executed runs recorded in [CHANGELOG.md](CHANGELOG.md).
They are not targets.

| Gate | Result | Where |
|---|---|---|
| Frozen eval (28 questions) | 27/28 (96%) on production adapter `r16-run4` | `sable-01/eval/` |
| Tool-emission gate (10 cases) | 9/10 on `r16-run4`. Residual **T-10** | `sable-01/eval/run_tool_gate.py` |
| Guard unit suite | 26/26 | `sable-01/tests/test_guard.py` · CI `unit-suite` |
| Recon unit suites | 34/34 | `bg-recon-plugin/tests/` · CI `recon-suite` |
| Red-team suite | 13 cases. Echo-in-refusal no longer scores as a fail. Three confirmed agent failures remain: TOOL-001, TOOL-002, TAI-002 | `bg-redteam/` |

Run-5 was trained three times and **not promoted** (best frozen 25/28, tool
gate 8/10). T-10 passed on those attempts; other cases moved the other way.
Production stays `adapters/r16-run4`. The attempt is kept under
`sable-01/train/` and `sable-01/train-r5/`.

Adapter rank: configs say 16; mlx-lm 0.32.2 ignores that field. Effective rank
is 8. Directory names stay `r16*` because serve and eval records use them.

## Known limits

Declared so they are not rediscovered as surprises.

- **T-10.** An unauthorized-target scan request can still emit a tool call on
  the production adapter.
- **K-04.** Frozen knowledge miss (CRC vs cryptographic hash wording) on
  production and on run-5.
- **Red-team, still open.** TOOL-001 canary leak, TOOL-002 key-material echo,
  TAI-002 path traversal that read `/etc/passwd`. These are agent-runtime
  failures, not harness bugs.
- **ZAP.** `bgx zap` is wired. The first daemon start can fail until
  `zap.sh -daemon` has completed its Automation Framework init once.
- **Shared hosts.** `map` is sequential on purpose. A parallel burst has tripped
  a live host's connection limit.
- **Bot challenges.** A 200 that is an interstitial ("One moment, please",
  `cf-edge-cache`) is unverified, not an exposed path.
- **USER-GUIDE.md** still describes the v2.0 command set (2026-11-01). Use this
  README for v2.2–v2.6 commands until that guide is revised.

## Repository layout

```
.
├── tools/bg                  bgx
├── bg-recon-plugin/          scan, posture, web, tls, map, assess
├── bg-redteam/               cases, harness, reports
├── bg-lab/                   lab.py, allowlisted exercises
├── sable-01/                 model serving, train, eval, designs
├── sable-bridge/             ask_sable
├── engagements/              assessment records (generated)
├── .github/workflows/        ci.yml, SLSA publish workflow
├── USER-GUIDE.md
├── CHANGELOG.md
├── SECURITY.md
├── CONTRIBUTING.md
├── LICENSE
├── CITATION.cff
└── THIRD_PARTY_NOTICES.md
```

Not in git, by design: model weights, adapter binaries, virtualenvs, the Colima
VM disk, `bg-recon-plugin/state/`, `tools/testssl.sh/`, `tools/zap/`.

## CI

[`.github/workflows/ci.yml`](.github/workflows/ci.yml) on every push and pull
request:

- `unit-suite` — macOS ARM. Guard tests. Tokenizer files are fetched; weights
  stay untracked.
- `recon-suite` — ubuntu. Every `bg-recon-plugin/tests/test_*.py`.
- Attribution sweep — the five root docs must contain the maintainer line.

A separate workflow publishes SLSA provenance for tagged releases. This
repository is private; the workflow is configured not to write the repository
name to the public Rekor log.

## Security

Report defects in this toolchain privately. Do not open a public issue for a
vulnerability. Steps and scope are in [SECURITY.md](SECURITY.md).

## Contributing

Owner-directed. No public contribution path. Gates, attribution, and commit
style: [CONTRIBUTING.md](CONTRIBUTING.md).

## Citation

Internal references: [CITATION.cff](CITATION.cff). The citation file's
`version` field may lag the changelog; the changelog is the release record.

## License

Proprietary. All rights reserved. Dual-use capabilities are limited to
authorized assessment. [LICENSE](LICENSE).

There is no `CODE_OF_CONDUCT.md` on purpose: single maintainer, owner-directed
repository.

---

*Created by Parth Patel, founder of BenchBrex.com (BeGuardit / BenchBrex).
CONFIDENTIAL — internal to BenchBrex. Not licensed for external use.*
