# Security Policy

Created by Parth Patel, founder of BenchBrex.com (BeGuardit / BenchBrex).

**Maintainer:** Parth Patel, founder of BenchBrex.com

Illegal use of these tools is the user's act alone. Neither BenchBrex nor BeGuardit has any involvement in, or liability for, that use. [DISCLAIMER.md](DISCLAIMER.md).

## Supported versions

Security fixes are provided for `main` (release line v2.6). This repository is private and owner-operated. There is no supported external release.

## Reporting a vulnerability

Do not disclose vulnerabilities, proof-of-concept exploits, credentials, session cookies, or private engagement records in a public issue. This repository has no public issue tracker for that purpose.

Use **Report a vulnerability** in the repository's **Security** tab as the preferred way to submit the report privately. If GitHub private reporting is unavailable, contact the maintainer through an existing private channel. Do not open a public issue to request a private contact channel.

Include the affected component (`bgx`, BG Recon, BG RedTeam, BG Lab, or Sable-01), operating system, impact, and reproduction conditions. Remove credentials, cookie values, adapter weights, and unrelated local paths from logs.

The maintainer will acknowledge the report and coordinate a fix. A report that only restates a boundary listed below, with no new impact, is informational.

## Security boundary

`bgx` resolves the target before it connects. Loopback and private addresses are allowed. A public address is allowed only when that command was given `--allow-external`. That flag is an explicit acknowledgment for one invocation. It is not a default, and it is not a sandbox.

Lab exercises ignore `--allow-external`. Their allowlist is `127.0.0.1:8081` and `localhost:8081`. Other targets are refused.

The model guard and the MLX server bind loopback. Opening them to `*` is a posture finding. Tailscale checks are read-only. This repository will not change Serve, Funnel, ACLs, or routes.

Web, TLS, map, and assess are GET or handshake checks. Cookie values are redacted in reports. ZAP, when it runs, is the baseline (spider and passive rules) and still requires `--allow-external`. A failed ZAP daemon start is a tooling residual, not a completed scan.

These controls limit accidental use against a host the operator did not name. They do not protect against a process already running as the same user. They do not make the lab, the model, or ZAP a sandbox.

### Declared, not vulnerabilities

- Single-user trust model. The guard assumes the local operator is trusted.
- The red-team harness scores the transcript and the sandbox postchecks. It does not score side effects outside that sandbox.
- The rate-limit window resets when the guard restarts.
- **T-10.** On the production adapter, an unauthorized-target request inside a tool context can still emit a tool call. Frozen tool gate is 9/10.
- **TOOL-001**, **TOOL-002**, and **TAI-002** are confirmed agent-runtime failures. They are open. They are not harness scoring bugs.

These are recorded in `sable-01/designs/` and [CHANGELOG.md](CHANGELOG.md).
