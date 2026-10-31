# Changelog

All notable changes to the BeGuardit Hacking Tools toolchain.
Created by Parth Patel, founder of BenchBrex.com (BeGuardit / BenchBrex).

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
