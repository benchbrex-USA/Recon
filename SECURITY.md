# Security Policy — Recon (BeGuardit Hacking Tools)

**Maintainer:** Parth Patel, founder of BenchBrex.com (BeGuardit / BenchBrex)

## 1. What this repository is

A proprietary, authorization-gated security-assessment toolchain: a TCP/port
and posture scanner (BG Recon), an AI red-team harness (BG RedTeam), a local
exploitation range (BG Lab), and an owned local language model with a hardening
proxy (Sable-01). All network capabilities enforce authorization allowlists and
bind to loopback only.

## 2. Responsible use (non-negotiable)

- Operate only against systems and agents **you own or have express written
  authorization** to assess. The tools refuse non-allow-listed targets; do not
  attempt to bypass those gates.
- The exploitation modules are scoped to the local lab containers
  (127.0.0.1:8081) by an allowlist in each module.
- Do not remove authorization gates. A gate removal is a license violation
  (see LICENSE §3) and voids the tooling's design guarantees.

## 3. Reporting a vulnerability in this toolchain

Report privately — do not open a public issue for a security defect.

1. **Preferred:** GitHub private vulnerability reporting
   (Security tab → "Report a vulnerability") on this repository.
2. **Alternative:** contact the maintainer directly (Parth Patel, BenchBrex)
   through existing private channels.

Include: affected component, reproduction steps, observed vs expected behavior,
and any log/metrics output. You will receive an acknowledgement and a fix or
mitigation plan.

## 4. Known design boundaries (declared, not vulnerabilities)

- Single-user trust model: the guard assumes the local operator is trusted.
- The red-team harness scores transcripts, not out-of-band side effects.
- The rate-limit window resets on guard restart (single-user residual).
- Tool-gate residual T-10: unauthorized-target requests inside a tool context
  may receive a tool call instead of a refusal (frozen gate 9/10).

These are documented in `sable-01/designs/` and the Master Guide. Reports that
restate a declared boundary without a new impact will be closed as informational.

## 5. Supported version

`main` only. The adapter provenance and gate results are recorded in
`sable-01/PROVENANCE.md` and `sable-01/designs/`.
