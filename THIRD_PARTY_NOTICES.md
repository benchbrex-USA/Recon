
- **testssl.sh 3.2.4** — https://github.com/testssl/testssl.sh — GNU GPL v2.
  Cloned to tools/testssl.sh/ and gitignored (not vendored into this
  proprietary-licensed repository). Invoked optionally via
  'bgx recon tls --deep' / 'bgx assess --deep'. Copyright its upstream
  authors; see its LICENSE in tools/testssl.sh/LICENSE.

- **osquery 5.19.0** — https://osquery.io — dual licensed Apache 2.0 / GPL v2.
  Installed from the official .pkg into tools/blue/osquery/ (gitignored, not
  vendored). Used by tools/blue/blue_sweep.py for endpoint state queries.

- **Nmap 7.993** — https://nmap.org — GPL v2 with the Nmap License
  reinterpretation. Built natively (arm64) from the official source tarball;
  the official dmg is x86_64-only and Rosetta is not installed. Binary and
  data under tools/blue/nmap/ (gitignored, not vendored).

- **Wireshark 4.6.9 / tshark** — https://www.wireshark.org — GPL v2.
  Installed from the official universal dmg into tools/blue/Wireshark.app/
  (gitignored, not vendored). tshark is used to parse capture files; packet
  capture itself requires privileges (ChmodBPF or sudo) and is not wired.
