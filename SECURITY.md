# Security Policy

## What this software is

AFENDA xForge is a **modified distribution** of Odoo 19.0 Community. That matters for
security reporting, because a vulnerability here can have one of three origins and they go
to different places:

| Where the flaw lives | Who can fix it | Where to report |
|---|---|---|
| AFENDA's own code (`afenda/addons/`, `afenda/tools/`) | us only | here — see below |
| The identity transform's effect on upstream code | us only | here — see below |
| Upstream Odoo, unmodified by us | Odoo, then us | Odoo **and** us |

**Do not report AFENDA vulnerabilities to Odoo.** Odoo's security team cannot act on a
distribution they do not ship, and sending them our details discloses our issue to a third
party. The reverse also holds: if you find a flaw in upstream Odoo that we merely inherit,
Odoo should hear about it through their own process — please tell us as well, so we can
assess our exposure and pick up the fix.

## Supported versions

| Version | Supported |
| ------- | --------- |
| 19.0 | yes — the only release line |

There are no earlier AFENDA releases. Upstream Odoo's support for its own older series is
Odoo's business, not ours, and says nothing about this distribution.

## Reporting a vulnerability

⚠️ **A disclosure channel is not yet established, and must be before any public or
customer-facing deployment.** Until it is:

- Prefer GitHub's **private vulnerability reporting** on this repository (Security →
  Report a vulnerability). This has to be enabled by the repository owner; if you do not
  see it, it is not on yet.
- Otherwise contact the repository owner privately. Do **not** open a public issue for a
  security problem, and do not include exploit details in a pull request.

Whoever sets up the channel should replace this section with a real address and a stated
response time. An unread mailbox is worse than an admission that there isn't one yet.

## What to include

- The exact steps to reproduce, as text. A short proof-of-concept script is far more useful
  than a screen recording.
- The version or commit you tested, and how it was deployed (this distribution differs from
  stock Odoo in ways that can matter).
- What you believe is at risk, and for whom — a reader, a tenant, the host.
- Whether the same flaw appears in unmodified upstream Odoo, if you know.

## Scope

There is no bug bounty and no guaranteed response time. Reports are handled on a
best-effort basis by a small team. We would rather hear about a real issue late than not at
all.

Two things that are **in scope** and easy to miss, because they are specific to a
white-labelled distribution:

- **Identity leaks** — a path, header, asset or outbound request that reveals the upstream
  product to an end user. Not a memory-safety issue, but a defect we want reported.
- **Third-party egress** — anything in a deployed instance that contacts a host we do not
  control. One known case is tracked in the repository's own documentation; others are
  worth telling us about.
