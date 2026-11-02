# Drift report — 2026-11-02

Source: official EGM plugin `~/.hermes/plugins/elephant-goldfish-model` (`egm-drift-report`).
Directory scanned: `/Volumes/Parth Patel/BeGuardit Hacking Tools/sable-01/designs`.
Code read this pass, not from memory.

## concepts_brief.md

- Still states Sable-01 cannot participate in Hermes agent turns. `sable-bridge/tools.py` `ask_sable` and the `sable` profile exist and have been used live.
- Still states tool-calling reliability is UNVERIFIED. Frozen tool gate on `adapters/r16-run4` is 9/10 (T-10 residual).
- Still states the server is ≈3 GB resident. `model-selection.md` and a live `footprint` measurement put the model server at 2.36 GB idle / 2.48 GB under generation.

## sable-agent-integration.md

- §8 names the tokenizer loader `mlx_lm.tokenizer_utils.load_tokenizer`. `serving/guard.py` imports `load`, not `load_tokenizer`.
- §8 describes a load-at-startup tokenizer bound to `<SABLE_DIR>/base`. The code loads lazily and honors `SABLE_TOKENIZER_SOURCE` (CI uses a fetched public tokenizer). Fail-fast still happens on first tokenize, not at import.
- §8 guard surface lists `/health` and `/ready` only. The code also serves `/metrics` and refuses non-`/v1/` GETs.

## sable-agent-integration.review.md

Not an implementation contract. No code claims re-checked as a spec.

## sable-agent-integration.drift.md

Ledger of an earlier audit, not a current implementation contract. It does not record the tokenizer-loader or `/metrics` divergences above.

## toolchain-v2.md

- §3 Recon CLI lists `posture|baseline-save|baseline-diff|report`. `plugin_api.py` also implements `scan` (private/loopback only, connects to the resolved IP). `bgx recon scan` calls it.
- §3 says tool calls are parsed by brace-matching. `eval/run_tool_gate.py` uses `json.JSONDecoder.raw_decode`.
- §4 says the lab pre-flight lives in `run()`. `dvwa_xss.py` and `dvwa_brute.py` run `_preflight` in `__main__` before `run()`. `run()` itself has no pre-flight.
- §6 says rollback is git-less. The toolchain is now the git repo `benchbrex-USA/Recon`.
- Guard behavior added after r2 and not in this spec: negative `Content-Length` is rejected (400); `max_tokens` must not be a bool; unit suite is 26 tests, not the 23 cited in `.github/workflows/ci.yml`.

## model-selection.md

No drift detected.
