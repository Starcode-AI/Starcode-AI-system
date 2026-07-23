# Security model

## Implemented controls

- Argon2id password hashing; plaintext passwords are never logged or stored
- Random opaque session tokens stored only as keyed SHA-256 hashes
- HttpOnly, SameSite=Strict session cookie and separate CSRF token
- Revocable sessions, active-device list, login throttling and temporary lockout
- Role checks for moderator/administrator/system-administrator operations
- CSP, HSTS in HTTPS mode, clickjacking prevention, MIME sniffing prevention, restrictive permissions policy and no-store API responses
- SQLAlchemy parameter binding rather than constructed SQL
- Output through DOM `textContent`; no dynamic HTML rendering of model/user text
- HTTPS-only external research, DNS/IP validation, private/reserved address rejection, port restrictions, bounded redirects, size/time limits and robots.txt checks
- File-name normalization, fixed user roots, non-executable permissions, archive traversal/symlink/device-entry rejection and decompression limits
- Optional ClamAV streaming scan without executing the file
- Generated project path allowlisting and total file/size limits
- Audit and security event records without passwords, raw session tokens or secret keys
- Encrypted SQLite backup files

## Prompt injection

Websites, documents, tool output and knowledge records are always data. The research loader strips common instruction-override patterns and logs the event. The fixed system policy tells the model not to follow source instructions. A second output check occurs before release.

This reduces risk; it cannot prove that an arbitrary model will never be manipulated. For sensitive deployments, add human approval for tool actions, use narrow allowlists, minimize retrieved content and run independent model/content classifiers.

## SSRF and DNS rebinding

The URL validator resolves a host and rejects every non-global address before each redirect. External URLs must use HTTPS and port 443. This blocks common localhost, RFC1918, link-local, multicast and reserved ranges.

DNS can still change between validation and the HTTP client's connection. A high-assurance deployment should enforce the same destination policy at the network layer using an egress proxy or firewall and prevent the application container from reaching private infrastructure.

## Files and archives

Archives are inspected, not extracted. The service rejects unsafe member names, links, devices, excessive file counts, excessive expanded size and suspicious ratios. Nested archives remain inert because version 1.0 never recursively extracts them. Executables receive a `.quarantine` storage suffix and mode `0600`.

## Reporting a vulnerability

Do not include real credentials, private data or a working exploit against a public system. Report the affected version, component, impact and minimal reproduction privately to the deployment owner.
