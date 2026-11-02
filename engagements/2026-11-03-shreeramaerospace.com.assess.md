# Assessment — shreeramaerospace.com — 2026-11-03

Created by Parth Patel, founder of BenchBrex.com.

Scope: Owner-authorized. GET/handshake checks only: no logins, no POST, no exploits. Shared-host friendly (sequential map).
Verdict: **ATTENTION** (2 high/critical).

| Check | Verdict |
|---|---|
| web | ATTENTION |
| tls | NO HIGH FINDINGS |
| map | NO HIGH FINDINGS |

## Findings

| Source | Severity | ID | Detail |
|---|---|---|---|
| web | high | hsts-absent | HTTPS response has no Strict-Transport-Security header (RFC 6797 §8.1). |
| web | high | http-no-redirect | HTTP returned 200 with no Location. RFC 6797 §8.1: a browser notes HSTS only from a response received over a secure transport, so this response cannot start that policy. |
| map | info | bot-challenge-observed | 20 path(s) returned an anti-bot interstitial (cf-edge-cache / 'One moment, please'). Those paths are unverified, not exposed - and the host has bot protection enabled. |
