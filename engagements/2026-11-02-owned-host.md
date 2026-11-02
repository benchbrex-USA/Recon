# Engagement record — owned-host posture, 2026-11-02

Created by Parth Patel, founder of BenchBrex.com (BeGuardit / BenchBrex).

Client: the owner of this Mac (authorized target). Not a lab exercise.
Operator: Hermes, using the installed toolchain. No third-party host was scanned.

## What ran

| Step | Command | Result |
|---|---|---|
| Status | `bgx status` | Exit 0. Guard up, mlx up, zombie no. Verdict printed `ALL SYSTEMS GO`. |
| Posture | `plugin_api.py posture` | 2026-11-02 09:44 IST. 10 listeners, 4 LAN-exposed, 0 secrets findings. |
| Diff | `plugin_api.py baseline-diff` | `2 added, 2 removed, 1 NEW LAN-EXPOSED`. New exposed listener: rapportd on a high port, bound `*`. Removed: prior ssh-named listener on 8081 and an older rapportd port. |
| Report | `plugin_api.py report` | `bg-recon-plugin/state/posture_report.html` |
| Model | `ask_sable` on the DNS exposure | See below. Wrong. |

## Findings that are about the host

Four listeners are bound to `*` (LAN-reachable): limactl:53 (dns), ControlCe:5000, ControlCe:7000, rapportd:63507. The model servers on 8001 and 8002 are loopback-only. That split is the useful result of the engagement.

## Findings that are about the toolchain (this run)

1. `bgx status` returned exit 0 and printed `ALL SYSTEMS GO` while the same screen reported `1 NEW LAN-EXPOSED`. The verdict does not treat a new exposure as attention. That is a product defect, observed live, not theorized.
2. `ask_sable` answered: "I would stop listening on that interface — it's outbound traffic, and you don't own it." The question was about a LAN-exposed DNS listener on a host the owner does own. The answer confuses inbound exposure with outbound traffic and denies ownership. Do not act on it.

## External score

Not obtained. Searched GitHub issues and X for a person who had offered to score a writeup. GitHub search returned no issue. X search returned no cited post (the tool's own uncited reply is not a person and is not a score). No message was sent, because there was no identified person who had asked to receive one, and publishing this host's listener list would expose the client.

No number out of 100 is stated. Inventing one would violate the engagement rule.
