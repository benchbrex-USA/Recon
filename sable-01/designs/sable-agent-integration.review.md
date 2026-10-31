# EGM review: Sable-01 agent integration
Spec revision reviewed: r1 / 2026-10-30 (critique) → r2 / 2026-10-30 (fixes applied)
Review isolation: INDEPENDENT (two fresh-context subagent runs; packet = frozen spec + serve.sh only)
Materials supplied to reviewer: `designs/sable-agent-integration.md` (r1), `serve.sh`

## Comprehension check (Stage 1, INDEPENDENT)

PASS. The reviewer reconstructed the architecture, data flow, boundaries, and error paths
accurately (8-sentence summary + 11-row ambiguity table). No FAIL. Ambiguities folded into
the r1→r2 consolidation below.

## Findings (Stage 2, INDEPENDENT critique of r1) and dispositions

| ID | Severity | Evidence (spec r1) | Impact | Recommended change | Disposition |
|---|---|---|---|---|---|
| F-001 | P0 | §3 mlx quirk; §4.1 forwarding; §5 contract; INV-1 | Guard bypass via direct 8002 POST + silent adapter stripping on any `model` ≠ `default_model` | Guard rewrites `model` → `default_model`; restate INV-1 | **FIX (r2 §4)** + residual accepted: loopback 8002 reachable by local processes (single-user host; INV-1 restated; R-2) |
| F-002 | P0 | §3 AS-3 ±10% claim vs backend `apply_chat_template` (verified server.py:661/677/718) | Gate undercounts 20–50%+ → 413s wrong / thread death still possible | Use the identical `apply_chat_template` path | **FIX (r2 INV-5, §4)** — AS-3 removed |
| F-003 | P1 | §4.1 zombie detect on POST-404 only; marker never cleared; non-atomic | Stale marker; /v1/models healthy-when-dead | Health endpoint; atomic self-clearing marker | **FIX (r2 §4: atomic tmp→rename, self-clear on 200, /health + /ready)** |
| F-004 | P1 | §8 serve.sh row; packet contained stale serve.sh | Phase-1 port conflict / 502 confusion | serve.sh update ships atomically with Phase 1 | **FIX (r2 §7 + AC-011)** |
| F-005 | P1 | §4.1 counts `messages[].content` only | System prompts/role overhead unmetered | Template-exact tokenization | **FIX (r2, same as F-002)** |
| F-006 | P2 | §6 "queue at backend (accept)" | Unbounded queue → latency/memory DoS | Caps + 503 Retry-After | **FIX (r2 §4: 2 in-flight + 4 queued caps)** |
| F-007 | P2 | §4.1 no validation | Malformed requests → undefined behavior | 400 field-specific validation | **FIX (r2 §4)** |
| F-008 | P2 | §5 guard JSON vs tool plain-text errors | Inconsistent error format | Unify | **FIX (r2 §5: tool surfaces JSON bodies as text)** |
| F-009 | P2 | §3 AS-1 | Profile may lack alias → AC-008 silent fail | Explicit copy + profile-show verification | **FIX (r2 §4.4/§8 + AC-008 precondition)** |
| F-010 | P2 | §3 AS-2 | Unpinned register_tool kwargs | Pin signature | **FIX (r2: pinned from developer guide; AS-2 closed)** |
| F-011 | P2 | §7 rollback | In-flight requests dropped on restart | Guard PID + SIGTERM drain | **FIX (r2 §4/§7 + AC-012)** |
| F-012 | P2 | §4.1 marker file | Corruption/stale/relative-path | Atomic write, absolute path, mtime check | **FIX (r2 §4/§5)** |
| F-013 | P3 | §4.1 no health endpoints | Cannot distinguish guard-down vs backend-down | /health + /ready | **FIX (r2 §4)** |
| F-014 | P3 | serve.sh test hits 8001 directly | Test bypasses guard | Test through guard + 413 case | **FIX (r2 §8 + AC-011)** |
| F-015 | P3 | §4.3 hardcoded temperature/max_tokens | No runtime configurability | Optional params with defaults | **FIX (r2 §5)** |
| F-016 | P3 | §6 no rate limit | Local DoS | Rate limit | **FIX (r2 §4: 60 req/min)** |
| F-017 | P3 | AC-010 | Attribution only check-time | CI enforcement | **ACCEPT WITH RATIONALE** — personal project, no CI infra; grep check retained (R-3) |

Stage-1 ambiguity table (11 rows) folded into the same r2 changes: tokenizer identity
(= base/, verified), reasoning-field strip (verified real — content null when thinking
incomplete), zombie marker pinned, health GETs defined, concurrency caps pinned, SOUL
content pinned, profile wiring explicit, gate margin rationale stated, REQ-007 clarified
(per-call invariant; repeated stateless calls allowed).

## Requirement and test traceability (r2)

| Requirement | Acceptance case(s) | Coverage verdict |
|---|---|---|
| REQ-001 | AC-001, AC-011 | covered (positive + negative) |
| REQ-002 | AC-002 | covered (incl. recovery) |
| REQ-003 | AC-003, AC-012 | covered (incl. drain) |
| REQ-004 | AC-004 | covered |
| REQ-005 | AC-005 | covered |
| REQ-006 | AC-006 | covered |
| REQ-007 | AC-007 | covered |
| REQ-008 | AC-008 | covered (measurement-based) |
| REQ-009 | AC-010 | covered (check-based; F-017 accepted) |

## Readiness gate

Round 1 verdict against r1: **revise** (3×P0, 2×P1 — all addressed in r2).
Round 2 against r2 (both INDEPENDENT fresh contexts):
- Critique re-check: defect classes (a) token mismatch **RESOLVED**, (b) zombie marker
  **RESOLVED**, (c) deployment ordering **PARTIALLY RESOLVED** (new serve.sh not yet
  written — pseudocode added in r3), (d) adapter stripping **RESOLVED**. New findings
  GC-001..GC-014 on the now-stateful guard: 1×P1 (GC-008 generation timeout), 6×P2,
  rest P3 — **all dispositioned in r3** (180 s generation timeout, single-lock mandate,
  atomic PID + stale check, marker TTL + startup re-validation, serve.sh v2 pseudocode,
  canonical root/attribution/timeout pins; GC-009/14 accepted as single-user residuals).
- Implementation readiness: **TECHNICALLY READY** — full REQ→AC coverage (9/9), no hard
  blockers; divergence points pinned in r3 §8.

**Gate status: APPROVED by Parth 2026-10-30 — implementation authorized** (phases C→B→A per D1). Technical conditions met (independent review ✓, no unresolved P0/P1 ✓, AC coverage ✓, actionable contracts ✓).

