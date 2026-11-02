# Design: Sable-01 agent integration — envelope guard, ask_sable bridge, minimal profile
Status: DRAFT
Owner: Parth Patel (founder, BenchBrex.com)
Revision: r4 / 2026-10-31 (drift-audit resolution: D-1/D-2/D-3 — as-built behavior documented, 504 distinction and startup generation-probe implemented; ledger in `sable-agent-integration.review.md` + `sable-agent-integration.drift.md`)
Verified inputs: `sable-01/PROGRAM.md`, `sable-01/TRAINING-REPORT.md`, `sable-01/serve.sh`,
`sable-01/serve.log` (thread-death traceback), `sable-01/eval/predictions-*.jsonl`,
`hermes-agent/website/docs/developer-guide/plugins/index.md` (tool registration contract,
including the full `ctx.register_tool(name, toolset, schema, handler)` signature),
`mlx_lm/server.py` v0.32.2 in the project venv (tokenization path verified: lines 661/677/718
use `tokenizer.apply_chat_template`; adapter-dir contents verified to contain no tokenizer
files), `hermes profile --help`. Envelope probe numbers (293/2,218/5,518 tok OK; 28,308 tok
thread death) verified 2026-10-30.

## 1. Problem and goals

- Sable-01 (Qwen3-4B-4bit + LoRA ckpt 300) serves verified trained facts on
  `127.0.0.1:8001`, but full Hermes agent turns fail: the agent system prompt is
  28,308 tokens, whose KV cache (~4.1 GB) kills the mlx generation thread
  (verified traceback, serve.log). After death the server is a zombie returning 404s.
- Stakeholders: the owner (single user); the main Hermes agent (cloud model) which
  should be able to consult Sable-01; Sable-01 itself (owned, offline).
- Desired behavior: (1) the server never crashes-and-zombies on oversized prompts —
  it rejects them cleanly; (2) the main agent can ask Sable-01 short questions as a tool;
  (3) a minimal `sable` profile can hold short conversations with Sable-01 directly.
- Success metrics and requirements:
  - REQ-001: Prompts whose chat-template-tokenized length ≤ 8,192 tokens are forwarded;
    longer prompts receive HTTP 413 with an actionable message, and the generation
    thread survives. The gate MUST use the same `apply_chat_template` tokenization the
    backend uses (see §4, INV-5), leaving ≥ 3× margin to the verified 28,308-token
    death point.
  - REQ-002: A dead generation thread is detected and surfaced as a zombie state
    (HTTP 503 + `X-Sable-Zombie: true` + atomic marker file) instead of a bare 404,
    and the marker self-clears on the next successful generation.
  - REQ-003: Valid requests and `/v1/models` behave identically through the guard as
    direct to the server (transparent proxy).
  - REQ-004: A `sable-bridge` Hermes plugin registers an `ask_sable` tool visible to
    the main agent (`hermes plugins doctor --ci` passes; tool appears in tool listings).
  - REQ-005: `ask_sable` returns Sable-01's answer for a domain question.
  - REQ-006: `ask_sable` degrades gracefully when the server is down (readable error
    string, no exception leak to the model).
  - REQ-007: `ask_sable` transmits only the question text to the local API — never
    conversation history, file contents, or other context. Per-call isolation is the
    invariant; the main agent MAY issue multiple independent calls (each is stateless).
  - REQ-008: A `sable` Hermes profile exists with a pinned-content SOUL, zero tools, and
    the local model; short turns complete in < 60 s with < 2,000 chat-templated prompt
    tokens (measured from serve.log prefill counters).
  - REQ-009: Every artifact carries the attribution line and lives on the external
    volume (`/Volumes/Parth Patel/BeGuardit Hacking Tools/`), symlinked from `$HOME`
    where Hermes requires a fixed path.

## 2. Scope and non-goals

- In scope: a token-envelope reverse proxy in front of mlx_lm.server; a `sable-bridge`
  agent plugin exposing `ask_sable`; creation of a minimal `sable` profile wired to the
  local endpoint; serve.sh updates (dual ports, guard lifecycle, zombie status, test
  through the guard) — the serve.sh update ships atomically with Phase 1 (AC-011).
- Out of scope: giving the `sable` profile ANY tools (deferred behind probe U2);
  training changes; model swaps; remote exposure (everything stays 127.0.0.1);
  auto-restart supervisors; multi-tenant hardening (single-user host).
- Backward compatibility: public port stays 8001 (the Hermes alias `model_aliases.sable-01`
  already targets it); mlx_lm.server moves to internal port 8002 — no external consumer
  exists today except the alias and serve.sh, both updated in this design.

## 3. Context and assumptions

Verified facts:
- Envelope probe: 293 tok → 3 s; 2,218 tok → 9 s; 5,518 tok → 16 s (correct trained
  answers); 28,308 tok → generation thread death (KV ≈ 147 KB/token → ≈4.1 GB spike).
  Probe structure: single user message; the r2 gate counts full chat-template output, so
  multi-turn and system roles are covered by construction.
- mlx_lm.server 0.32.2 quirks (all verified in source/logs): (a) only the request id
  `default_model` maps to the CLI-loaded adapter — any other model string loads a path
  WITHOUT the adapter; (b) after generation-thread death the server keeps answering
  404s (zombie) until restarted; (c) responses carry a separate `reasoning` field and
  `content` may be null while thinking is incomplete (verified live with max_tokens 150).
- Tokenization: the backend applies `tokenizer.apply_chat_template` to the full message
  list (mlx_lm/server.py:661/677/718 — verified). The adapter directory contains only
  adapter weights + config (verified: no tokenizer files), so the tokenizer identity is
  the BASE model tokenizer (`base/`) — the same files the backend loads.
- Hermes plugin tool contract (verified against plugins/index.md, including the full
  calculator example): `plugin.yaml` declares `provides_tools:`; `schemas.py` holds
  JSON-schema dicts; `tools.py` holds handlers; `register(ctx)` calls
  `ctx.register_tool(name=..., toolset=..., schema=..., handler=...)`;
  `hermes plugins doctor --ci` validates the whole chain.
- `hermes profile create` exists (verified via CLI help).
- Profile isolation: each profile has its own skills/plugins/cron/memories (environment fact).

Assumptions (labeled):
- AS-1: Whether the `sable` profile's config inherits the global `model_aliases` entry is
  UNVERIFIED — Phase 3 therefore writes the alias explicitly into the profile config
  (r2: no inheritance reliance; critique F-009) and verifies via `hermes profile show
  sable` before AC-008 runs.
- AS-2: CLOSED in r2 — `ctx.register_tool(name, toolset, schema, handler)` pinned from
  the developer guide (verified snippet).

## 4. Proposed design

Components:
1. **Guard proxy** (`serving/guard.py`, stdlib ThreadingHTTPServer): binds 127.0.0.1:8001
   (public). Behavior per request:
   - `POST /v1/chat/completions`: strict validation first — `model` present, `messages`
     a non-empty array of `{role, content}` objects, `max_tokens` integer in [1, 8192]
     (default 512), `temperature` in [0, 2] if present; invalid → `400` with a
     field-specific error (F-007). Then rewrite `model` to `default_model` (F-001 fix),
     tokenize with the BASE tokenizer via `apply_chat_template(messages,
     add_generation_prompt=True)` — the identical code path the backend uses — and:
     (a) ≤ 8,192 tokens → forward to `127.0.0.1:8002`, return the response verbatim;
     (b) > 8,192 → `413 {"error": "prompt is N tokens; Sable-01 envelope is 8192 — send a
     short, self-contained question"}`. The template-exact count covers system prompts,
     multi-turn history, role overhead, and thinking markers (F-002/F-005 fix — the raw-
     content undercount flaw of r1 is removed).
   - Zombie handling: if the backend answers a POST with 404 (the verified zombie
     signature), return `503 {"error": "generation thread dead — run ~/sable-01/serve.sh
     restart"}` + header `X-Sable-Zombie: true`, and write the marker atomically
     (`<sable-01>/serving/zombie.tmp` → rename; absolute path, F-012). On the next
     successful (200) forward, delete the marker (self-clearing — F-003 fix). At guard
     startup, if a marker exists, run a tiny generation probe against the backend:
     200 → clear the marker (thread alive); 404/down → keep it (the naive `/v1/models`
     probe was REJECTED — it answers 200 even when the generation thread is dead,
     verified in review round 1).
   - `GET /v1/models` → forwarded verbatim. `GET /health` → guard-local:
     `{"guard": "up", "zombie": <bool>, "in_flight": n, "last_backend_ok_age_s": n}`
     (guard up even if backend dead — F-013). `GET /ready` → 200 only if the last
     forward succeeded within 120 s; else 503. `GET /metrics` → guard-local JSON
      counters (uptime_s/requests_total/by_status/latency_s). Any other GET path is
      refused 404 (T26, as-built: only /v1/, /health, /ready, /metrics are served).
   - Validation hardening (drift D-1, as-built): non-string `question` (tool) or
     `content` (messages) is coerced to its JSON text before tokenization — models
     occasionally emit nested objects, and the tokenizer crashes on them.
   - Backpressure: max 2 in-flight generations + 4 queued; excess →
     `503 {"error": "server busy"}` + `Retry-After: 5`. Global rate limit 60 req/min →
     `429 + Retry-After` (sliding window; counter reset on guard restart is an accepted
     single-user residual — GC-007). **Generation timeout: 180 s per request** — on
     expiry the guard abandons the backend stream, decrements in-flight, and returns
     `504 {"error": "generation timeout — run serve.sh restart if it persists"}`
     (GC-008 fix; distinct from 502 per drift D-2 resolution). All shared mutable state
     (counters, queues, rate limiter, marker) is guarded by a single `threading.Lock`
     (GC-010 mandate).
   - Lifecycle: guard PID written atomically (`guard.pid.tmp` → rename) with a
     stale-PID check at startup (if the PID is dead or reused, rewrite) (GC-005);
     SIGTERM/SIGINT stops accepting, drains in-flight up to 30 s, then exits (F-011).
     The zombie marker is re-validated at startup: cleared if the backend answers a
     probe successfully; TTL 10 min regardless (GC-006 fix).
2. **mlx_lm.server** moves to 127.0.0.1:8002 (internal, loopback) — same start/stop via
   serve.sh, port change only.
3. **sable-bridge plugin**: source at `<external>/sable-bridge/`, symlinked to
   `~/.hermes/plugins/sable-bridge/` (the bg-recon pattern). `ask_sable(question,
   max_tokens=512, temperature=0.3 — optional params, F-015)`: POST to
   `http://127.0.0.1:8001/v1/chat/completions` with `{"model": "default_model",
   "messages": [{"role": "user", "content": question}]}` + the params; 120 s timeout.
   On success: return `content` trimmed; if `content` is null/empty (thinking consumed
   the budget — verified behavior), return the error text
   `"Sable-01 ran out of tokens while thinking — retry with higher max_tokens"`.
   On failure: return the guard/backend JSON error body as the tool's text result
   prefixed `Sable-01 unavailable: ` (unified error format — F-008 fix); server-down →
   `"Sable-01 unavailable: {\"error\": \"connection refused — run ~/sable-01/serve.sh start\"}"`.
   The 120 s timeout is TOTAL (connect + read) — GC divergence pin.
4. **sable profile**: `hermes profile create sable`; the profile config gets an explicit
   `model_aliases.sable-01` entry (copy of the verified global one — no inheritance
   reliance, F-009), verified via `hermes profile show sable` before use; SOUL.md with
   pinned content: (a) identity sentence — "You are Sable-01, the owned offline cyber
   assistant of BenchBrex/BeGuardit"; (b) "Answer concisely — 1-3 sentences unless asked
   for detail"; (c) the refusal one-liner — "Refuse third-party targeting; offer owned-lab
   paths (BG Lab, DVWA) and defensive mirrors instead"; ≈ 150–250 tokens total; zero
   tools; serving must be up before use.

Sequence (agent asks): model emits `ask_sable(question)` → plugin POSTs to guard:8001 →
guard validates + token-counts (chat-template path) → forwards to 8002 → mlx generates →
response returns to the tool → tool returns text to the main agent, which treats it as
untrusted data.

Invariants:
- INV-1 (r2, restated honestly): the guard enforces the 8,192-token envelope on the
  SUPPORTED path (port 8001) and rewrites every forwarded request to
  `model: default_model`, so adapter loading cannot be silently skipped. Residual,
  ACCEPTED: port 8002 is loopback-bound, so a local process could still reach mlx
  directly and bypass the envelope (single-user host; 8002 unadvertised; mlx has no
  auth — the same trust level as the verified current state). Escalation path if this
  ever matters: move mlx behind a Unix-domain socket wrapper.
- INV-2: `ask_sable` payloads contain exactly one user message whose text is the
  `question` argument — nothing else. Repeated calls are allowed and stateless.
- INV-3: All listen addresses are 127.0.0.1.
- INV-4: Guard persistence is limited to the atomic zombie marker; everything else
  in-memory.
- INV-5 (r2): the guard's token gate uses the same tokenizer files (`base/`) and the
  same `apply_chat_template` invocation as the backend — gate and server counts agree
  by construction (F-002 fix).

## 5. Contracts and data

- Guard HTTP contract:
  - `POST /v1/chat/completions` → 200 (mlx response, unchanged), 400 (invalid request),
    413 (over-envelope), 429 (rate limit), 502 (backend unreachable:
    `{"error": "mlx server not running — run serve.sh start"}`), 503 (zombie or busy),
    504 (generation timeout — drift D-2).
  - `GET /v1/models` → forwarded; `GET /health`, `GET /ready`, `GET /metrics` →
    guard-local (§4); any other GET refused (T26).
  - All error bodies: single-field JSON `{"error": "..."}` naming the fix.
- Tool contract (`ask_sable`): parameters `question` (string, required), `max_tokens`
  (integer 64–1024, default 512), `temperature` (number 0–2, default 0.3). Returns the
  assistant text on success; on failure returns the JSON error body as text prefixed
  `Sable-01 unavailable: `. Never raw tracebacks.
- mlx server contract (unchanged): `default_model` id; thinking enabled; adapter ckpt 300.
- Auth: none added — everything is 127.0.0.1-only and owner-local (loopback binding is
  the boundary, same as the verified current state).
- Persistence: atomic zombie marker only; absolute paths (no CWD dependence — F-012).

## 6. Failure modes and security

- Over-envelope prompt → 413 with fix instructions (replaces thread death; gate is
  template-exact per INV-5).
- Backend down → 502 with `serve.sh start` hint. Zombie → 503 + marker; recovery manual.
- Busy/queue overflow → 503 with Retry-After; rate limit → 429 (F-006/F-016).
- Malformed request → 400 field-specific (F-007).
- Volume unmounted → guard/backend fail to start; serve.sh start errors loudly.
- Prompt injection: Sable-01 output is untrusted text returned into the main agent's
  context; the tool description instructs the model to treat it as data. The injected
  surface is minimal: only the bare question is sent (INV-2) and Sable-01 has no tools.
- Abuse: local-only model with no tools; refusal policy is trained-soft — tool-level
  gates (out of scope) remain the enforcement layer if the profile ever gets tools (D3).
  Local DoS bounded by the queue cap + rate limit (F-016).
- Secrets: none in flight; `api_key: local-sable-01` is a constant placeholder.
- Concurrency: ThreadingHTTPServer accepts parallel connections; generation serializes
  at the backend within the 2-in-flight/4-queued caps; excess rejected with 503 (no
  unbounded queue — F-006).
- Accepted residuals (owner-approved under the D1 "all" mandate): direct loopback access
  to 8002 bypasses the guard (single-user host, INV-1); attribution grep is a check, not
  runtime enforcement (F-017).

## 7. Rollout and operations

- Deploy order: **Phase 1 ships atomically** — serve.sh update (mlx → 8002, guard
  start/stop/status/test) + guard.py land together; verify AC-011 before proceeding →
  Phase 2 (bridge plugin, doctor --ci, enable) → Phase 3 (profile, measure U1/AC-008).
  Each phase independently revertible: Phase 1 rollback = stop guard, revert serve.sh
  (direct 8001); Phase 2 = `hermes plugins disable sable-bridge`; Phase 3 =
  `hermes profile delete sable`.
- Monitoring: serve.sh status reports guard up, backend up, zombie marker state (mtime
  honored); serve.log remains the diagnostic trail (mlx logs chat-template prefill counts).
- Support playbook: zombie → `serve.sh restart`; volume unmounted → remount then start;
  busy 503s → reduce concurrent callers (single-user expectation).

## 8. Implementation map

Canonical root: `SABLE_DIR` = the directory containing this spec's parent
(`<external>/sable-01/`); every runtime path (guard.py, marker, pid, log) resolves from
`SABLE_DIR` absolutely — no CWD dependence (GC divergence fix). Canonical attribution
line (all new files): `Created by Parth Patel, founder of BenchBrex.com (BeGuardit / BenchBrex).`
Guard tokenizer loader (as-built 2026-11-02): `from mlx_lm.tokenizer_utils import load`,
then `load(<SABLE_DIR>/base)` — mlx-lm 0.32.2 exposes `load`, not `load_tokenizer`.
Loading is lazy (first tokenize, not import) and honors `SABLE_TOKENIZER_SOURCE` (CI
fetches a public tokenizer; weights stay untracked). Parity with the backend is verified
by AC-003 text equivalence.

| Path / component | Concrete change | Dependencies | Verification |
|---|---|---|---|
| `sable-01/serving/guard.py` (NEW) | stdlib reverse proxy: chat-template-exact token gate, model rewrite, validation, queue/rate caps, 180 s generation timeout, atomic zombie marker, /health + /ready, drain, single lock | venv tokenizer (base/) | AC-001/002/003/011 |
| `sable-01/serve.sh` (v2) | Dual-process lifecycle — see pseudocode below | guard.py | AC-002/003/011 |
| `<external>/sable-bridge/{plugin.yaml,schemas.py,tools.py,__init__.py}` (NEW) | ask_sable tool per §4/§5 (pinned `ctx.register_tool(name=, toolset=, schema=, handler=)`) | urllib (stdlib), guard running | AC-004/005/006/007 |
| `~/.hermes/plugins/sable-bridge` | symlink → external source (bg-recon pattern) | external volume mounted | AC-004 |
| `hermes profile create sable` + explicit profile-config alias + pinned-content `SOUL.md` | minimal profile per §4 | AS-1 verified at implementation (`hermes profile show sable`) | AC-008/009 |
| `sable-01/PROGRAM.md`, `TRAINING-REPORT.md` | gate/status updates | none | review |

serve.sh v2 lifecycle pseudocode (GC-013):

```
start:  [volume mounted?] → start mlx on 8002 → poll /v1/models (30×2s)
        → start guard on 8001 (guard pidfile) → poll /health (15×2s)
        → both up = OK; if guard fails → stop mlx, exit 1 (no orphaned backend)
stop:   SIGTERM guard (drain ≤30 s) → SIGTERM mlx → rm pidfiles
status: guard /health + marker mtime (TTL 10 min) + mlx port probe
test:   short question through guard (expect trained fact)
        + over-envelope case (expect 413, thread alive)
```

NEW paths are proposed components of this design (owned by this project). Profile-config
internals remain UNVERIFIED per AS-1 and are explicitly verified in Phase 3.

## 9. Tests and acceptance

- AC-001 (REQ-001): Given the stack is up, When a request whose chat-template count is
  ~9,000 tokens hits :8001, Then the client receives 413 with the envelope message, and a
  subsequent short request still returns a correct trained answer (thread alive).
- AC-002 (REQ-002): Given a dead generation thread (verified zombie behavior), When a
  POST arrives, Then the client receives 503 + `X-Sable-Zombie: true`, the marker exists,
  and `serve.sh status` prints the zombie state; after `serve.sh restart`, the marker is
  gone and a short request succeeds.
- AC-003 (REQ-003): A short request through :8001 returns the same fields and
  substantively identical text as a direct :8002 request; `/v1/models` forwards.
- AC-004 (REQ-004): `hermes plugins doctor --ci sable-bridge` exits 0; the tool appears
  in the default profile's tool listing.
- AC-005 (REQ-005): With serving up, `ask_sable("What is Sable-01?")` returns text
  containing "owned, offline cybersecurity LLM" (the trained fact).
- AC-006 (REQ-006): With serving stopped, the tool returns the unified
  "Sable-01 unavailable: …" error text; the agent turn completes without an exception.
- AC-007 (REQ-007): The outbound POST body (guard request-log during a test) contains
  exactly the question text — no conversation history, file contents, or system context.
- AC-008 (REQ-008): A `sable` profile short turn completes < 60 s with server-side
  chat-template prefill < 2,000 tokens (serve.log counters), after
  `hermes profile show sable` confirms the alias.
- AC-009 (REQ-008): In the `sable` profile, "What is Sable-01?" returns the trained fact.
- AC-010 (REQ-009): The attribution grep over every new file returns the line.
- AC-011 (REQ-001/003, F-004): The updated serve.sh passes Phase-1 verification: guard on
  8001, mlx on 8002, `serve.sh test` answers through the guard, and an over-envelope test
  case receives 413 without killing the thread.
- AC-012 (REQ-003, F-011): During `serve.sh stop` with an in-flight generation, the guard
  drains up to 30 s; the in-flight client receives its response or a clean 503 — never a
  broken pipe.
- Negative cases: AC-001 (over-envelope), AC-006 (backend down), malformed-request 400,
  busy 503. Race: single-user; queue caps bound any concurrent burst (§6) — no race test
  required.

## 10. Alternatives and decisions

| Decision | Alternatives | Chosen | Why / trade-off | Human owner |
|---|---|---|---|---|
| D1 architecture | A profile-only / B tool-only / C guard-only | All, phased C→B→A | owner chose "all"; each phase independently useful and revertible | Parth |
| Guard mechanism | Patch mlx site-packages / external proxy | External proxy | no third-party-code edits; survives mlx updates; one extra port | Parth |
| Gate tokenization | Raw content count (r1) / chat-template exact (r2) | Chat-template exact | r1 undercounted 20–50%+ (F-002, verified against server source) | Parth |
| Model field handling | Forward as-is / rewrite to default_model | Rewrite + document loopback residual | adapter stripping is silent and verified; loopback residual accepted for single-user | Parth |
| Zombie recovery | Auto-restart supervisor / manual restart | Manual + self-clearing marker | owner keeps control of a 3 GB resident process | Parth |
| Profile tools | None / gated toolsets | None (v1) | 4B tool-calling UNVERIFIED (U2); zero-tool variant removes the dual-use class | Parth |
| Error formats | JSON vs plain-text split (r1) | Unified JSON bodies; tool surfaces them as text | F-008 | Parth |

## 11. Open questions and risks

| ID | Severity | Open item | Owner | Target / resolution |
|---|---|---|---|---|
| AS-1 | P2 | Profile alias inheritance vs explicit copy | Elephant (Phase 3) | explicit copy + `hermes profile show` verification (r2 decision) |
| U2 | P2 | 4B tool-call reliability (future A-with-tools) | Elephant | separate probe task; blocks D3 only |
| R-1 | P3 | mlx generation effectively serial; caps bound concurrency | accepted | single-user host |
| R-2 | P3 | Direct loopback 8002 access bypasses the guard | accepted | single-user host; INV-1 restated |
| R-3 | P3 | Attribution is a check, not runtime enforcement | accepted | personal project; AC-010 grep |
