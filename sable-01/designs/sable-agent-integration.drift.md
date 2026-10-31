# EGM drift audit: spec r3 vs implemented source
Audit date: 2026-10-30
Spec: `designs/sable-agent-integration.md` r3 (APPROVED 2026-10-30)
Source inspected (read-only): `serving/guard.py`, `serve.sh`, `sable-bridge/{plugin.yaml,schemas.py,tools.py}`,
profile `~/.hermes/profiles/sable/{config.yaml,SOUL.md}`, live endpoint probes (this session)
Audit isolation: NOT INDEPENDENT (Elephant performed the audit; EGM step 8 does not require fresh context)

## Verdict summary

**13 MATCH · 3 DRIFT · 0 UNVERIFIABLE.** All three drifts are in the same direction —
the implementation hardened or simplified *beyond* the approved spec during the live
ask_sable failure debugging — and all three are resolved by a minor spec amendment (r4)
rather than code changes. No unsafe or incorrect core behavior found.

## Drift findings

| ID | Spec section | Code path (verified) | Classification | Detail | Recommendation |
|---|---|---|---|---|---|
| D-1 | §4 validation / §5 tool contract | `guard.py:227-230` (content coercion), `sable-bridge/tools.py:20-21` (question coercion) | **DRIFT → RESOLVED (r4)** | Non-string `question`/`content` is coerced to JSON text before tokenizing — beyond the spec's validate-only wording. Cause: live failure (the calling model emitted `question` as a nested object; `'dict' object has no attribute 'startswith'` in the tokenizer). Verified fix in production. | **FIXED — both:** r4 §4/§5 document the coercion as intended; code retained. |
| D-2 | §4/§5 generation timeout → `504 {"error": "generation timeout"}` | `guard.py:253,266-267` (`forward()` timeout=180 s; expiry falls to the generic handler → `502 {"error": "backend failure: … — run serve.sh start"}`) | **DRIFT → RESOLVED (r4 + code)** | Timeout fires at 180 s as designed but surfaced as 502 with the generic backend-failure body, not a distinct 504. | **FIXED — both:** code now raises `GenTimeout` → distinct `504 {"error": "generation timeout — run serve.sh restart if it persists"}` (verified by handler test with a hanging backend); r4 §5 documents 502/504 distinctly. |
| D-3 | §4 lifecycle: "zombie marker re-validated at startup: cleared if the backend answers a probe successfully" | `guard.py` `write_pid()`/`main()` — startup writes PID only; NO backend probe at startup. Marker self-clears on the first successful (200) forward; TTL 10 min honored via `marker_fresh()` | **DRIFT → RESOLVED (r4 + code, corrected variant)** | Startup probe not implemented; the marker can survive a restart until the first generation. Operational impact minimal (status reports marker with mtime; restart guidance unchanged). | **FIXED — both, with a correction:** the naive `/v1/models` probe was REJECTED (it answers 200 even when the generation thread is dead — verified round 1). Implemented instead: a startup TINY-GENERATION probe (200 → clear; 404/down → keep), verified live (planted marker cleared after guard restart, probe logged). r4 §4 documents the corrected lifecycle. |

## Matched items (spot-verified, no action)

| Spec item | Code evidence | Verdict |
|---|---|---|
| INV-1 model rewrite to `default_model` | `guard.py:240` | MATCH |
| INV-2 single-user-message tool payloads | `tools.py` body construction; AC-007 request-log check | MATCH |
| INV-3 loopback-only binds | guard 8001, mlx 8002, both 127.0.0.1 | MATCH |
| INV-4 atomic marker, absolute paths | `atomic_write()`, `SABLE_DIR`-anchored | MATCH |
| INV-5 template-exact tokenization | `mlx_lm.tokenizer_utils.load(base/)` + `apply_chat_template` | MATCH |
| 8,192 envelope + 413 with count | `guard.py:246-250`; live: 413 at 12,816 tok | MATCH |
| Queue caps 2+4 / rate 60 min | `_cond` admission + deque window | MATCH |
| 400 field-specific validation | `guard.py:218-238` | MATCH |
| `/health` + `/ready` fields | `guard.py` do_GET | MATCH |
| Zombie 503 + `X-Sable-Zombie` + marker on 404 | `guard.py:259-263` | MATCH |
| ask_sable 120 s total timeout, unified errors | `tools.py` | MATCH |
| serve.sh v2 dual-process lifecycle + over-envelope test | current `serve.sh` (post-r3, ASCII-clean) | MATCH |
| Phase 3 profile: explicit alias copy, pinned SOUL, zero tools | profile config + SOUL.md | MATCH |
| Attribution on every artifact | grep verified across new files | MATCH |

## Human choice required

Intended behavior for D-1/D-2/D-3: **(a) amend the spec to the as-built behavior
(recommended — all three are verified improvements or neutral simplifications), or
(b) change the code to match the spec verbatim.** On (a), spec r4 is a documentation
amendment only — no re-review required (no behavioral change to the approved contracts).
