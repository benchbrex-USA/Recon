# Changelog

All notable changes to the BeGuardit Hacking Tools toolchain.
Created by Parth Patel, founder of BenchBrex.com (BeGuardit / BenchBrex).

## [2.5] — 2026-11-03

### Added
- `bgx assess <host> [--deep] [--allow-external]` — one-command engagement:
  composes web + tls + map (tailscale context when the target is this
  machine), aggregates findings severity-ordered with sources, and writes the
  engagement record (Markdown) + client-ready HTML report to `engagements/`
  automatically. Authorization gate enforced once up front.
- `bgx recon tls <host> --deep` — vendored testssl.sh 3.2.4 (handshake-only
  checks, `--fast --quiet`, JSON parsed into finding rows). GPL third-party
  tool: cloned to `tools/testssl.sh/`, gitignored, credited in
  THIRD_PARTY_NOTICES.md — not vendored into this proprietary repo.
- Owned-site watchdog: `~/.hermes/scripts/web_watchdog.sh` + cron
  `beguardit-web-watchdog` (e80792f9073e, Mondays 10:00 IST, no_agent,
  deliver bot-chat, silent unless NEW findings appear).
- CI: new `recon-suite` job runs every `bg-recon-plugin/tests/test_*.py`
  (stdlib-only, ubuntu) on every push/PR; guard-suite comment corrected
  23 → 26 tests.
- Spec drift from the 2026-11-02 EGM drift report closed: tokenizer loader
  (`load`, lazy, `SABLE_TOKENIZER_SOURCE`), `/metrics` + GET allowlist,
  recon CLI subcommand list, raw_decode parser (was brace-matching), lab
  pre-flight placement, git-based rollback, concepts-brief status updates
  (tool gate verified, as-built footprint).

### Tests
- `test_assess.py` (7): aggregation order/sources, host slugs, testssl JSON
  shapes + severity normalization, HTML escaping. Suite total 32/32 across
  four files; guard suite green locally and in CI.

### Verified live (shreeramaerospace.com, owner-authorized)
- `bgx assess` (no deep): verdict ATTENTION, 3 high findings (hsts-absent,
  http-no-redirect, /cpanel mistake-path), engagement md + html written.
- Watchdog: silence path silent, alert path correct on synthetic diff.

## [2.4] — 2026-11-02

### Added
- `bgx recon tailscale` — read-only Tailscale attack-surface check of this
  machine: version, backend state, self DNS/Tailscale IPs, peer count,
  Serve/Funnel state (JSON-first with text fallback; raw command output kept
  in the report), Tailscale SSH, advertised exit-node routes. Funnel active =
  critical (public ts.net URL reaches the machine); Serve active = medium;
  SSH/exit-node = low; not connected = info. Never mutates config — Serve,
  Funnel, ACL and route changes stay owner-approval actions.
- Foundational research recorded: RFC 8996 (TLS 1.0/1.1 deprecated), RFC 6797
  §8.1 (HSTS noted only over secure transport), MDN Set-Cookie (Secure /
  HttpOnly semantics).

### Tests
- `bg-recon-plugin/tests/test_tailscale.py` (12): serve JSON shapes including
  the 1.102.x config-map contract (`{}` = off; non-map values = unknown),
  funnel text classification, severity rules. Suite total 19/19 across three
  files.

### Verified live (this machine)
- Tailscale 1.102.4, backend Running, self `benchbrex.taila8b570.ts.net`
  (100.107.166.54), 1 peer, Serve off, Funnel off, SSH off, no exit node.
  Exit 0 / NO HIGH FINDINGS.

## [2.3] — 2026-11-02

### Added
- `bgx recon web <host> --allow-external [--path /]` — authorized header
  posture: HTTP redirect, HSTS (RFC 6797 §8.1), `Set-Cookie` Secure/HttpOnly
  (MDN), `X-Powered-By`. GET-only, no redirects followed, cookie values
  redacted before they exist in any report. Probes run concurrently.
- `bgx recon tls <host> --allow-external` — leaf certificate (subject, issuer,
  notAfter, days remaining, SAN), chain verification, pinned-version
  handshakes for TLS 1.0/1.1/1.2/1.3 (RFC 8996). Client-unsupported vs
  server-rejected are labeled separately; cipher-level failure is reported
  with its raw error instead of being overclaimed.
- `bgx recon map <host> --allow-external` — bounded sequential site inventory
  (≤80 GETs): sitemap + same-host links + a fixed mistake-path list
  (`.env`, `.git/`, backups, phpinfo, `/cpanel`, ...). Shared-host friendly:
  sequential because a parallel burst tripped a live host's connection limit.
- `bgx recon web-history <host>` — per-host posture history with a diff of
  new vs resolved findings between the last two runs. `web` auto-saves.
- `bgx recon scan --allow-external` — public targets now reachable by explicit
  flag; default refusal unchanged.
- `bgx status` now treats `NEW LAN-EXPOSED` as unhealthy (was printing
  ALL SYSTEMS GO over a live exposure).

### Tests
- `bg-recon-plugin/tests/test_web_posture.py` (4) and `test_v23.py` (7):
  cookie flag parsing/redaction, day-remaining math, protocol-error
  classification, same-host link extraction, history save/diff. 11/11.

### Verified live on shreeramaerospace.com (owner-authorized)
- web: `http-no-redirect`, `hsts-absent` (exit 1); cookie path adds
  `cookie-cleartext`, `cookie-not-httponly`, `version-disclosure`.
- tls: GoDaddy DV, 160 days left, chain OK, TLS 1.2 accepted, TLS 1.3
  server-rejected, 1.0/1.1 not accepted.
- map: 59 requests, `/cpanel` served 200 on port 80 flagged high.

## [2.1] — 2026-11-01

### Added
- Git distribution: repo initialized (73+ files), `.gitignore` excludes model
  weights, adapter binaries, virtualenvs, VM disk
- `USER-GUIDE.md` — hands-on manual for all four systems
- `LICENSE` (proprietary, authorized-use restriction), `SECURITY.md`,
  `CONTRIBUTING.md`, `CITATION.cff`

### Fixed
- Memory documentation: measured footprint (2.36–2.48 GB) supersedes the
  RSS-based "1.3 GB" figure (weights are memory-mapped; RSS understates)
- Repo rename: `Recon---BeGuardit-Hacking-Tools` → `Recon` (README heading,
  guide references, remote)

## [2.0] — 2026-11-01

### Added
- `bgx` command center (status / doctor / report + dispatch)
- BG Recon v2: posture baseline snapshot, change detection (verified in both
  directions), HTML assessment reports
- BG RedTeam v2: suite expanded 7 → 13 cases (exfil shapes, tool-arg
  injection, authority spoof); `trend.py` severity-weighted regression
  tracking; first live run: 8 pass / 5 agent-safety findings (1 critical)
- BG Lab v2: reflected-XSS and brute-force modules (4 total); authorization
  allowlist + pre-flight on every exploit module
- Sable-01: `/metrics` endpoint (request counts, status breakdown, latency
  p50/p95); guard unit suite 21 → 23 tests

### Changed
- **Production adapter promoted to `r16-run4`**: tool-context-aware training
  (192-row dataset, 2× rehearsal rebalance) — tool gate 9/10, frozen eval
  27/28 (96%), refusals 10/10. Run 3 (25/28) was gated out.
- Provenance correction (binary-verified from safetensors headers): all
  adapters train at LoRA rank 8, scale 20; mlx-lm ignores the top-level
  `rank:` key — "r16" directory names are labels, not parameters

### Reviewed
- Two-round independent Goldfish review: round 1 NO-GO with 5 P0 findings
  (all fixed with live verification), round 2 READY (16/16 confirmed)

## [1.0] — 2026-10-31

### Added
- Initial verified toolchain: BG Recon (plugin), BG RedTeam (7 cases),
  BG Lab (SQLi + command injection), Sable-01 (Qwen3-4B-4bit + LoRA,
  envelope guard on 127.0.0.1:8001, ask_sable bridge, sable profile,
  frozen eval 27/28), Master Operations Guide PDF
