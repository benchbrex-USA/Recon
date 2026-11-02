# Engagement — shreeramaerospace.com — 2026-11-02

Created by Parth Patel, founder of BenchBrex.com.

Client: Shreeram Aerospace & Defence LLP. Owner stated in chat that this is their company and asked for the toolchain to be used on https://shreeramaerospace.com/.
Scope: one host, non-destructive. TCP connect + banner on 20 ports, TLS certificate, response headers, a handful of public paths. No logins, no exploits, no other hosts.

Tool: BG Recon `authorization()` + `scan_target()` from `~/.hermes/plugins/bg-recon/dashboard/plugin_api.py`. `allow_external=true` was passed because the owner gave written scope in this session. The default CLI still refuses public targets.

## What the host is

- `shreeramaerospace.com` and `www` both resolve to `132.148.176.3` (and NAT64 `64:ff9b::8494:b003`).
- Reverse DNS: `3.176.148.132.host.secureserver.net` (GoDaddy shared hosting).
- Certificate: CN `shreeramaerospace.com`, issuer GoDaddy TLS Intermediate CA DV, valid 2026-09-28 to 2027-04-12.
- Web server header: `Apache`, no version. Page last-modified 2026-08-12.

## Open ports (connect scan, 20 ports, 8 workers, 1.2s timeout, 3.1s)

Open: 21 FTP (Pure-FTPd, banner says no anonymous login), 22 SSH (`SSH-2.0-OpenSSH_8.0`), 80 HTTP, 110 POP3 (Dovecot), 143 IMAP (Dovecot), 443 HTTPS, 465 SMTPS, 587 submission, 993 IMAPS, 995 POP3S, 3306 MySQL (no banner; port accepted the connection).
Filtered: 25, 53, 445, 3389, 5432, 8000, 8080, 8443, 8888.
Closed: none of the 20.

Port 465 answered `421 Too many concurrent SMTP connections from this IP`. The parallel connect scan tripped the host's limit. Scan stopped. Not retried.

## Web checks

- `http://shreeramaerospace.com/` returns **200**. It does not redirect to HTTPS.
- HTTPS response sets `X-Content-Type-Options: nosniff`, `X-Frame-Options: SAMEORIGIN`, `X-XSS-Protection: 1; mode=block`.
- Not set: `Strict-Transport-Security`, `Content-Security-Policy`, `Referrer-Policy`.
- `/.env` and `/.git/HEAD` return 403 (not readable). `wp-login.php`, `/admin`, `/phpmyadmin`, `/server-status` return 404.
- `robots.txt` allows all and points at the sitemap.

## What the owner should change

1. Force HTTP to HTTPS, then add HSTS. Right now the same page is served in cleartext.
2. In the GoDaddy panel, turn off remote MySQL unless a specific office IP needs it. Port 3306 accepted a connection from the public internet.
3. SSH, FTP, and mail on this IP are the shared host's services, not a dedicated plant network. OpenSSH 8.0 is years behind current upstream; patching it is GoDaddy's job unless this account has its own VPS. Restrict FTP to known IPs if the panel allows it.
4. Do not treat 403 on `/.env` as proof the file is absent. It is not publicly readable. Leave it that way.

Not done, on purpose: no password attempts, no exploit modules, no scan of other customers on that shared IP, no Sable recommendation (the last live answer was wrong).

## Item 1 — HTTP does not redirect, no HSTS, no CSP

Re-checked 2026-11-02 after the first pass. BG Recon `authorization()` allowed the host (`allow_external` from the owner's written scope). Bodies fetched with curl, redirects not followed.

| URL | Status | Location | HSTS | CSP |
|---|---|---|---|---|
| http://shreeramaerospace.com/ | 200 | none | absent | absent |
| http://www.shreeramaerospace.com/ | 200 | none | absent | absent |
| https://shreeramaerospace.com/ | 200 | none | absent | absent |
| https://www.shreeramaerospace.com/ | 200 | none | absent | absent |
| http and https `/index.html` | 200 | none | absent | absent |

All six responses are the same file: 80,916 bytes, sha256 `b48d0e231266c493fec2e195f7986fcee4c7661c72be4c4e3025a8532df3988a`. Cleartext is not a stub. It is the full homepage.

HTML has no CSP meta tag, no `upgrade-insecure-requests`, no meta refresh. The only `http://` strings in the page are the W3C namespace URIs (`www.w3.org/1999/xlink`, `www.w3.org/2000/svg`). Those are not fetched. No mixed-content image or script URL was found. The defect is the page itself being served on port 80, not broken assets inside the HTTPS page.

Headers that are present on both schemes: `X-Content-Type-Options: nosniff`, `X-Frame-Options: SAMEORIGIN`, `X-XSS-Protection: 1; mode=block`. No `Set-Cookie` on this page, so there is no session cookie to steal here.

Concrete exposure: the contact form (`#homepage-contact-form`) posts to `https://formsubmit.co/info@shreeramaerospace.com`. A visitor who opened the site as `http://` can have that form rewritten on the wire before it is submitted. The form action being HTTPS does not protect the HTML that contains it.

Certificate is fine and is not this defect. OpenSSL verify return code 0. Chain sent: leaf, GoDaddy TLS Intermediate CA DV - R1v1, GoDaddy TLS Root CA - R1. SAN covers apex and `www`. A local Python 3.11 trust store failed to build the chain; curl and OpenSSL did not. That failure is the assessment machine, not the site.

Fix order, or HSTS will not stick:

1. In GoDaddy, turn on the HTTPS redirect (or an `.htaccess` rule that 301s port 80 to `https://`). Confirm `http://` then returns 301, not 200.
2. Only after that, add `Strict-Transport-Security` on the HTTPS response. Browsers ignore HSTS on cleartext responses, which is why it is absent and useless until step 1 exists.
3. CSP is a separate change. The page loads `https://img1.wsimg.com/traffic-assets/js/tccl.min.js` and posts to `formsubmit.co`. A default-deny policy will break the contact form and that script unless those origins are allowed. Do not paste a strict CSP without checking the form still submits.

Next item, not started: MySQL 3306.
