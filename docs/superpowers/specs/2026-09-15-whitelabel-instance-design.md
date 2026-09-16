# White-Label DripDrop Instance — Design

**Date:** 2026-09-15
**Status:** Approved, ready for implementation
**Branch:** `feat/whitelabel-instance`

## Goal

Stand up a second, fully isolated DripDrop instance for an outside firm, containing
none of Arena's candidates or clients. Same code, same DripDrop branding, own
domain, own server, own credentials.

## Why the data needs no scrubbing

Candidate and client data lives **entirely** under `DRIPDROP_DATA_DIR`
(`/opt/dripdrop/data` in production), never in code:

| Path | Contents |
|---|---|
| `users.json` | accounts and credentials |
| `users/<safe_email>/` | campaigns, contacts, PDFs, profile, candidate pool |
| `tenants/<safe_domain>/` | shared per-domain campaign data |
| `teams/<safe_domain>/` | team membership |
| `email_imgs/`, `city_images/`, `ai_usage.jsonl`, `logs/` | global caches and telemetry |

Starting that directory empty yields a clean instance *by construction*. There is
no export, no anonymization pass, and no possibility of missing a record.

The Arena 4x4 / 5x5 / 5x3 sequences are defined in code
(`flowdrip_app.py:4118-4211`), so they ship with the deploy. The new instance gets
a fully functional product on day one — with nobody in it.

## Decisions

| Decision | Choice |
|---|---|
| Purpose | White-label for an outside firm |
| Branding | Identical DripDrop — no theming layer |
| Hosting | New droplet, full isolation from Arena's box |
| Domain | `171.dripdripdrop.ai` — a subdomain in the existing Cloudflare zone |
| Credentials | The firm supplies their own Anthropic key and Google/Microsoft OAuth apps |
| Code | One repository, two deploy targets — no fork |

### Why a new droplet

Arena's box is a single vCPU; `create_campaign` already had to be moved off the
event loop because one slow request stalled the whole app. An outside firm's load
would contend for that same core. A separate droplet also keeps sending reputation
separate, and keeps the outside firm's data out of reach of the cross-tenant
dedupe script, which walks every tenant's campaigns on the local disk.

### Why a subdomain

Branding stays identical, so `171.dripdripdrop.ai` is coherent. It costs
nothing, needs no new registration, and keeps DNS in the Cloudflare account we
already control. Migrating to a vanity domain later is one additional Caddy
hostname and one A record — no server changes.

## Code changes

Six hardcoded `arenastaffing.net` gates would silently degrade or break the new
instance. Each becomes an environment variable **whose default is the current
hardcoded value**, so deploying this change to Arena's production site is a no-op.

| Site | Symbol | New var | Effect if left unfixed |
|---|---|---|---|
| `flowdrip_app.py:59` | `_ATS_ALLOWED_DOMAINS` | `DRIPDROP_ATS_DOMAINS` | Pipeline/ATS tab invisible to the firm |
| `flowdrip_app.py:61-64`, `:87`, `:2583` | individual email allowlists | `DRIPDROP_ATS_EMAILS` | Arena staff implicitly privileged on their site |
| `flowdrip_app.py:84` | `_ROUNDUP_OWNER_EMAIL` | `DRIPDROP_ROUNDUP_OWNER` | Their roundups email an Arena employee |
| `flowdrip_app.py:85-89` | `_ROUNDUP_ALLOWED_EMAILS` | `DRIPDROP_ROUNDUP_EMAILS` | Arena staff can read the firm's roundups |
| `ats.py:31` | `ALLOWED_EMAILS` | reuses `DRIPDROP_ATS_EMAILS` | Same as above, in the ATS module |
| `ats.py:36` | `_OWNER_BACKFILL_EMAIL` | `DRIPDROP_OWNER_EMAIL` | Pre-multi-user records assigned to an Arena account |
| `ats.py:897` | `_EMAIL_SKIP_DOMAINS` | `DRIPDROP_INTERNAL_DOMAINS` | **Candidate sequences can be mailed to their own recruiters** |

Six variables in total. `DRIPDROP_ROUNDUP_EMAILS` and `DRIPDROP_OWNER_EMAIL`
were added during implementation: the roundup viewer allowlist and the ATS
owner-backfill address are separate gates from the two they sit beside, and
leaving either hardcoded would have named an Arena account on the firm's
instance.

`ats.py:897` is the most serious. It skips recruiter addresses when choosing which
address on a record belongs to the candidate. Configured for Arena only, it will
not skip the new firm's own staff addresses, so their internal recruiters can be
enrolled into candidate outreach.

`DRIPDROP_SUPER_ADMINS` is a seventh Arena-specific gate, but it was already
environment-driven before this work (`flowdrip_app.py:1683`), so it needs no code
change — only a value in the new instance's `.env`. It is listed here because it
shares the others' failure mode: left unset it names
`michael.vaughn@arenastaffing.net`, and the firm's own admin holds no keys on
their own instance.

Each variable parses as a comma-separated list, trimmed, lowercased, empty entries
dropped. An unset variable yields today's Arena value.

## Provisioning sequence

1. Ship the six config vars to Arena production. Verify Pipeline still loads for
   `@arenastaffing.net` — the change is expected to be behaviorally inert.
2. Provision the droplet and run `deploy/setup-server.sh`.
3. Add an A record for `171.dripdripdrop.ai` to the new droplet in the existing
   Cloudflare zone. Set SSL/TLS mode to **Full (strict)** — Flexible mode sends
   plain HTTP to a Caddy that redirects to HTTPS, producing a redirect loop.
4. Write `/opt/dripdrop/.env` from the annotated template `deploy/env.171.example`,
   which carries every variable below with the firm's domain already filled in:
   - `DRIPDROP_SECRET` — freshly generated, never reused from Arena's instance
   - `ANTHROPIC_API_KEY` — the firm's own key
   - `DRIPDROP_INVITE_CODES`, `DRIPDROP_SUPER_ADMINS` — the firm's values
   - `GOOGLE_REDIRECT_URI`, `MS_REDIRECT_URI` — on `171.dripdripdrop.ai`
   - `DRIPDROP_ATS_DOMAINS`, `DRIPDROP_INTERNAL_DOMAINS` — the firm's email
     domain, `thrivemodal.com`. **Both must be set**, or the résumé extractor
     will not skip the firm's own recruiters (see `ats.py:897` above).
   - `DRIPDROP_ATS_EMAILS`, `DRIPDROP_ROUNDUP_OWNER`, `DRIPDROP_ROUNDUP_EMAILS`,
     `DRIPDROP_OWNER_EMAIL` — the firm's admin accounts
5. The firm registers the two callback URLs in their own Google Cloud and Azure
   app registrations. The redirect URIs are already environment-driven
   (`deploy/gmail_oauth.py:33`, `deploy/ms_email.py:16`); no code change needed.
6. Deploy, create the first admin account, and send one test campaign to a
   controlled mailbox before any real recipient.
7. Install the queue-pruning cron immediately. Arena's instance reached a 133MB
   `scheduled_queue.json` before this was added; preventing the growth is far
   cheaper than remediating it.

## Deployment

`_deploy_zero_downtime.sh` hardcodes `SERVER` at line 30. Parameterize it via an
environment variable defaulting to Arena's address, so the same script deploys to
either target. One repository, two `.env` files, no divergence.

## Out of scope

- **Theming layer.** Branding is identical; there is nothing to abstract.
- **MCP connector on the new instance.** It is a separate service needing its own
  subdomain and OAuth registration, and has caused three separate production
  incidents (transport-security 421s, blue/green mismatch, Caddy regression). Add
  it only if the firm asks.
- **Shared reporting across instances.** The instances are deliberately isolated.
- **Data migration of any kind.** The new instance starts empty.

## Verification

- The six new variables, unset, reproduce current behavior exactly — verified by
  the existing test suite against a 15-failure baseline.
- `ats.py:897` behavior is verified with the new firm's domain configured: their
  recruiter addresses must be skipped when selecting a candidate address. Done
  2026-09-15 against `thrivemodal.com`, both directions, on a résumé carrying a
  `dana.reed@thrivemodal.com` sourcing header above the candidate's own
  `jordan.blake@gmail.com`:

  | `DRIPDROP_INTERNAL_DOMAINS` | Extracted as the candidate's email |
  |---|---|
  | unset (Arena default) | `dana.reed@thrivemodal.com` — **the recruiter** |
  | `thrivemodal.com` | `jordan.blake@gmail.com` — correct |

  The failure is silent: nothing errors, the recruiter is simply enrolled into
  candidate outreach. This is why the variable is not optional.
- Arena production is confirmed unchanged after step 1 before the new droplet is
  provisioned.
