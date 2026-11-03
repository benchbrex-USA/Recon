<div align="center">

# BeGuardit Hacking Tools

### Assess only what you own.

**One command center for host posture, owned sites, an AI red team, a local lab, and an offline model.**

[![v2.6](https://img.shields.io/badge/release-v2.6-0f766e?style=flat-square)](CHANGELOG.md)
[![gates](https://img.shields.io/badge/gates-guard_26%2F26_%C2%B7_recon_34%2F34-2ea44f?style=flat-square)](.github/workflows/ci.yml)
[![platform](https://img.shields.io/badge/platform-macOS_26_%C2%B7_Apple_Silicon-111827?style=flat-square)](#requirements)
[![license](https://img.shields.io/badge/license-proprietary-f4c430?style=flat-square)](LICENSE)

[Quick start](#quick-start) · [The model](#the-assessment-model) · [Current status](#current-status) · [How it works](#how-it-works) · [CLI](#cli) · [Security](#security) · [Disclaimer](#disclaimer)

<br />

<code>bgx status && bgx doctor</code>

<br />

<img src="docs/system.png" alt="BeGuardit Hacking Tools: operator, bgx, authorization gate, BG Recon, BG RedTeam, BG Lab, and Sable-01" width="1200" />

**Created by Parth Patel, founder of BenchBrex.com** (BeGuardit / BenchBrex).

</div>

---

Give an owned host to `bgx`. It checks what is listening, what a site is exposing, whether the local agent refuses abuse, and what an offline model will say — then writes the record. It does not scan hosts the operator has not authorized, and it does not upload the target anywhere.

The four systems already on this machine are BG Recon, BG RedTeam, BG Lab, and Sable-01. `bgx` is the only entry point. Public hosts are refused unless that command was given `--allow-external`. Lab exploits ignore that flag. Their allowlist is `127.0.0.1:8081`.

> Authorized use only. Do not remove the gates. [LICENSE](LICENSE) §3 · [SECURITY.md](SECURITY.md).

## Disclaimer

Anyone who uses BeGuardit Hacking Tools for any illegal activity is solely responsible for their own actions. Neither BenchBrex nor BeGuardit has any involvement in that use, and neither BenchBrex nor BeGuardit has any liability for it.

The tools are for authorized assessment of systems the operator owns or has written permission to assess. Illegal use is outside that scope. It is the user's act alone. Full text: [DISCLAIMER.md](DISCLAIMER.md).

## Just ask

Health, then the owned host:

```bash
bgx status
bgx assess <host-you-own> --allow-external
```

Or, to the agent:

```text
Run bgx assess on the host I own. Show the findings. Do not scan anything else.
```

`<host-you-own>` is not a default target. Passing `--allow-external` is the written acknowledgment for that one command.

## The assessment model

<table>
<tr>
<td width="33%" valign="top">
<strong>Observe</strong><br /><br />
Listeners, headers, TLS, a bounded site map, Tailscale, and a passive ZAP baseline. GET and handshakes. Cookie values are redacted.
</td>
<td width="33%" valign="top">
<strong>Gate</strong><br /><br />
Loopback and private addresses pass. A public address passes only with <code>--allow-external</code> on that command. The lab never leaves <code>127.0.0.1:8081</code>.
</td>
<td width="33%" valign="top">
<strong>Record</strong><br /><br />
Markdown and HTML under <code>engagements/</code>. A bot interstitial is unverified, not an exposed path. A new LAN listener is attention, not all-clear.
</td>
</tr>
</table>

The toolchain shows what it measured. It does not invent a score, and it does not claim a scan finished when the tool did not finish.

## Why this exists

| | |
| --- | --- |
| **One entry point** | `bgx`. The name `bg` is a shell builtin. |
| **Fails closed** | Missing target or a public host without the flag exits 2. Attention exits 1. |
| **Local by design** | Model, lab, and reports stay on this machine. Weights are not in git. |
| **Agent and terminal** | The same commands from the shell or from Hermes. `ask_sable` is the model bridge. |
| **Declared residuals** | T-10, K-04, and three red-team failures are written down. They are not hidden behind a green badge. |

## Quick start

### On this machine

`bgx` is already on `PATH` (`~/bin/bgx` → `tools/bg` on the canonical volume).

```bash
bgx status
bgx doctor
bgx recon posture
bgx recon tailscale
```

Start the model only when you need it. Do not run it at the same time as the lab.

```bash
~/sable-01/serve.sh start          # guard :8001, model :8002
bgx sable status
~/sable-01/serve.sh stop
```

### Assess a host you own

```bash
bgx assess <host> --allow-external
bgx assess <host> --deep --allow-external    # adds testssl.sh
bgx recon web <host> --allow-external
bgx recon tls <host> --allow-external
bgx recon map <host> --allow-external
```

`--deep` needs `tools/testssl.sh/` on the volume. It is installed, not committed. See [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md).

### Lab — local only

```bash
bgx lab up
bgx lab xss
bgx lab down
```

### Requirements

- macOS on Apple Silicon. Guard CI runs on a macOS ARM runner because MLX does not run elsewhere.
- Python 3.11. Sable-01 uses `sable-01/`'s own venv.
- The volume mounted at `/Volumes/Parth Patel/BeGuardit Hacking Tools`. Home paths are symlinks into it. A clone with the volume unmounted cannot serve the model or pass `bgx doctor`.
- Optional, gitignored: testssl.sh 3.2.4, OWASP ZAP 2.17.0, Temurin JDK.
- Colima, only while the lab is up.

Day-to-day procedures: [USER-GUIDE.md](USER-GUIDE.md). That guide is still the v2.0 command set (2026-11-01). For v2.2–v2.6 commands, use this README. Operations: `sable-01/RUNBOOK.md`.

If something is not working:

```bash
bgx doctor
```

## Current status

Release line **v2.6**. Numbers are from executed runs in [CHANGELOG.md](CHANGELOG.md), not targets. The gate badge above is a recorded result, not a live status check.

| | |
| --- | --- |
| Frozen eval | 27/28 on production adapter `r16-run4` |
| Tool-emission gate | 9/10. Residual **T-10** |
| Guard | 26/26 · CI `unit-suite` |
| Recon | 34/34 · CI `recon-suite` |
| Red team | 13 cases. Echo-in-a-refusal is not a fail. **TOOL-001**, **TOOL-002**, **TAI-002** are still real failures |
| Run-5 | Trained three times. Best 25/28 and 8/10. **Not promoted** |
| ZAP | Wired. First daemon start can fail until `zap.sh -daemon` has finished its Automation Framework init once |
| Adapter rank | Configs say 16. mlx-lm 0.32.2 ignores that field. Effective rank is 8. Directory names stay `r16*` |

Production adapter: `sable-01/adapters/r16-run4`.

## How it works

```mermaid
flowchart LR
    Operator["Operator<br/>Hermes · CLI · cron"] --> bgx["bgx"]
    bgx --> Gate["authorization()"]
    Gate --> Recon["BG Recon<br/>posture · web · tls · map"]
    Gate --> Red["BG RedTeam<br/>13 cases · hermes -z"]
    Gate --> Lab["BG Lab<br/>127.0.0.1:8081"]
    Operator --> Sable["ask_sable"]
    Sable --> Guard["guard :8001"]
    Guard --> Model["mlx :8002<br/>Qwen3-4B + r16-run4"]
    Recon --> Out["engagements/"]
    Red --> Out
```

The CLI and the agent use the same `bgx` commands. The guard binds loopback. A listener on `*` is a finding, not a feature. Tailscale checks are read-only: this repo will not turn Serve or Funnel on.

Ports: guard **8001**, model **8002**, lab **8081**.

## CLI

Exit codes: **0** healthy or no high findings, **1** attention, **2** usage.

### Health

```bash
bgx status
bgx doctor
bgx report
```

`status` includes the recon baseline diff. A new LAN-exposed listener marks the verdict unhealthy.

### Assessment

```bash
bgx assess <host> [--deep] [--allow-external]
bgx recon posture
bgx recon scan <target> [ports] [--allow-external]
bgx recon web <host> [--path /] [--allow-external]
bgx recon tls <host> [--deep] [--allow-external]
bgx recon map <host> [--allow-external]
bgx recon web-history <host>
bgx recon baseline-save
bgx recon baseline-diff
bgx recon report
bgx recon tailscale
bgx zap <host> --allow-external
```

`assess` runs web, TLS, and map, and adds the Tailscale check when the target is this machine. It writes `engagements/<date>-<host>.assess.md` and HTML. `web` is GET only: redirect, HSTS (RFC 6797 §8.1), `Set-Cookie` Secure/HttpOnly, `X-Powered-By`. `tls` checks the certificate, the chain, and TLS 1.0–1.3 (RFC 8996). `map` is at most 80 sequential GETs. `zap` is the OWASP ZAP baseline and refuses without the flag.

### Red team, lab, model

```bash
bgx redteam list
bgx redteam run
bgx redteam trend <older.json> <newer.json>
bgx lab up
bgx lab down
bgx lab status
bgx lab sqli
bgx lab cmdi
bgx lab xss
bgx lab brute
bgx sable start
bgx sable stop
bgx sable status
bgx sable test
```

Canary leak and postcheck tamper always fail. A banned string quoted inside a refusal does not.

Owned-site watchdog, not a `bgx` subcommand: `~/.hermes/scripts/web_watchdog.sh`, Mondays 10:00 IST. It speaks only when a **new** finding id appears.

## Security

Security fixes are for `main`. Report a defect in this toolchain in private. Do not open a public issue, and do not include credentials, session cookies, or proof-of-concept exploits in a place others can read.

Preferred path: **Report a vulnerability** on this repository's Security tab. The boundary — what the gates do and do not promise — is in [SECURITY.md](SECURITY.md).

## Repository

```
tools/bg                 bgx
bg-recon-plugin/         scan, posture, web, tls, map, assess
bg-redteam/              cases, harness, reports
bg-lab/                  lab.py, allowlisted exercises
sable-01/                serving, train, eval, designs
sable-bridge/            ask_sable
engagements/             assessment records
docs/system.png          the diagram above
```

Not in git: weights, adapters, virtualenvs, the VM disk, `bg-recon-plugin/state/`, `tools/testssl.sh/`, `tools/zap/`.

CI: [`.github/workflows/ci.yml`](.github/workflows/ci.yml). `unit-suite` on macOS ARM. `recon-suite` on ubuntu. An attribution sweep requires the maintainer line in the five root docs. Tagged releases publish SLSA provenance without writing this private repository's name to the public Rekor log.

Owner-directed. No public contribution path. [CONTRIBUTING.md](CONTRIBUTING.md). Internal citation: [CITATION.cff](CITATION.cff). There is no `CODE_OF_CONDUCT.md` on purpose.

## License

Proprietary. All rights reserved. Dual-use capabilities are limited to authorized assessment. [LICENSE](LICENSE).

---

*Created by Parth Patel, founder of BenchBrex.com (BeGuardit / BenchBrex). Public repository. Proprietary. Not licensed for external use.*
