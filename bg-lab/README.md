# BG Lab

**Created by Parth Patel, founder of BenchBrex.com** (BeGuardit / BenchBrex).

Local CTF lab + exploit toolkit for DVWA-class targets. Implements the
security-tools curriculum's sanctioned track: **legal offense on your own lab
targets**, every attack answered with its detection/hardening twin.

> **Physical location:** this folder lives on the external volume
> (`/Volumes/Parth Patel/BeGuardit Hacking Tools/bg-lab`); `~/bg-lab` is a
> symlink. The colima VM (the multi-GB part) also lives on that volume — the
> drive must be mounted for `lab.py up` to work.

## Scope rules

- Exploit scripts refuse public targets unless `--allow-external` is passed
  (same gate as bg-recon: your acknowledgment of ownership or written scope).
- The lab runs in colima/Docker containers on this machine. Nothing here
  touches real infrastructure.
- Port note: `lab.py` binds DVWA on **8081** and Juice Shop on **3001** —
  port 5000 belongs to macOS ControlCenter on this host.

## Targets

| Container | Image | URL | Security-model lessons |
|---|---|---|---|
| bg-dvwa | `vulnerables/web-dvwa` (amd64 emu) | http://127.0.0.1:8081 | SQLi, command injection, XSS, auth brute force |
| bg-juice | `bkimminich/juice-shop` | http://127.0.0.1:3001 | modern JS-app vulns: broken auth, IDOR, XSS, API abuse |

DVWA default creds: `admin` / `password`. Set DVWA Security to `low` for the
v1 exploits.

## Usage

```bash
python3 lab.py up          # pull + start both targets (first run pulls images)
python3 lab.py status
python3 lab.py down

python3 lab.py sqli        # DVWA SQLi: login -> union dump -> offline crack
python3 lab.py cmdi        # DVWA exec() injection -> whoami, /etc/passwd
```

Both exploit commands run the full break-then-defend half: after dumping,
the script prints the detection/hardening that closes the same TTP.

## The loop (from your curriculum)

1. **LAB** — `lab.py up`
2. **BREAK** — run an exploit module
3. **DEFEND** — read the `[i] DEFEND` line it prints; implement + verify the
   fix, re-run the exploit against the fixed config, confirm the block
4. **TEACH/LOG** — one log line per session: TTP, detection rule, residual risk

## Adding an exploit

Drop `exploits/<target>_<vuln>.py` with a `run(target, ...)` entrypoint, wire
it into `lab.py` subcommands, gate the target through `check_target.py`.
Keep modules stdlib-only.
