# Second DripDrop Instance — Design

*(Originally "White-Label DripDrop Instance"; rescoped — see Status.)*

**Date:** 2026-09-15
**Status:** Rescoped 2026-09-15 — target changed from an outside client firm to
Mike's own new venture. Code changes complete and committed; provisioning not
started. Test suite at the known 15-failure baseline, no new failures.
**Branch:** `feat/whitelabel-instance`

## Goal

Stand up a second, fully isolated DripDrop instance as the operating platform for
Mike's new venture, containing none of Arena's candidates or clients. Same code,
same DripDrop branding, own domain, own server, own credentials.

**This is not a client white-label.** Mike is leaving Arena; this instance is where
he continues operating, and Arena's deployment becomes the legacy one. That changes
the design in one structural way: every dependency this instance carries on Arena is
a dependency that fails the day he leaves. See **Dependencies to sever**.

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
| Purpose | Operating instance for Mike's new venture; Arena's becomes legacy |
| Branding | Identical DripDrop — no theming layer |
| Hosting | New droplet, full isolation from Arena's box |
| Domain | `171.dripdripdrop.ai` — a subdomain in the existing Cloudflare zone |
| Credentials | Own Anthropic org, own OAuth apps — none shared with Arena |
| Code | Same code, no fork. Deploy targets parameterized; repo ownership to move — see **Dependencies to sever** |

### Dependencies to sever

Written for a client instance, this design treated shared Arena infrastructure as
harmless. For Mike's own venture each shared piece is a single point of failure
timed to his departure.

| Dependency | Status | Action |
|---|---|---|
| Anthropic org | Arena's, `Admin · Arena` | **Own org.** A workspace under Arena's org was tried first and abandoned: workspace keys are linked to the creating user and are *deactivated when that user leaves the organization* — the key would die exactly when the venture starts. Own org also removes the awkwardness of Arena's card funding the venture's tokens. Cost: a new org starts at rate-limit Tier 1, cleared by prepaying credits. |
| `dripdripdrop.ai` | **Mike holds it** | No action. `171.` as a subdomain stands. Note the mirror: after departure *Arena's* production sits on a domain Mike controls — decide whether they migrate off or he hosts them. |
| Repository | Shared with Arena | A repo Mike owns. "One repository, two deploy targets" assumes indefinite access to Arena's origin, which departure may end. Same code today; the point is that no future fix has to route through Arena's repo. |
| Arena-named campaign products | Shipped in code | See **What was deliberately not changed** — unresolved, and the sharper problem now. |

### Why a new droplet

Arena's box is a single vCPU; `create_campaign` already had to be moved off the
event loop because one slow request stalled the whole app. A second business's load
would contend for that same core. A separate droplet also keeps sending reputation
separate, and keeps the new venture's data out of reach of the cross-tenant dedupe
script, which walks every tenant's campaigns on the local disk. Given the departure,
isolation is also the point in itself: no shared box means no shared access to
unwind later.

### Why a subdomain

Branding stays identical, so `171.dripdripdrop.ai` is coherent. It costs nothing,
needs no new registration, and keeps DNS in a Cloudflare account **Mike personally
holds** — confirmed, and the reason this is not a dependency on Arena. Worth picking
the permanent hostname before launch rather than after: renaming later means DNS, the
Caddyfile, both OAuth redirect URIs, `DRIPDROP_PUBLIC_ORIGIN`, and every image URL
already baked into sent mail. Migrating to a vanity domain later is one additional Caddy
hostname and one A record — no server changes.

## Code changes

Every change below follows one rule: **the hardcoded Arena value becomes the
environment variable's default**, so shipping all of this to Arena's production
site is a behavioral no-op. The new instance overrides each one in its `.env`.

### 1. Access gates — who the app lets in

Six hardcoded `arenastaffing.net` gates would silently degrade or break the new
instance.

| Site | Symbol | New var | Effect if left unfixed |
|---|---|---|---|
| `flowdrip_app.py:59` | `_ATS_ALLOWED_DOMAINS` | `DRIPDROP_ATS_DOMAINS` | Pipeline/ATS tab invisible on the new instance |
| `flowdrip_app.py:61-64`, `:87`, `:2583` | individual email allowlists | `DRIPDROP_ATS_EMAILS` | Arena staff implicitly privileged on their site |
| `flowdrip_app.py:84` | `_ROUNDUP_OWNER_EMAIL` | `DRIPDROP_ROUNDUP_OWNER` | Their roundups email an Arena employee |
| `flowdrip_app.py:85-89` | `_ROUNDUP_ALLOWED_EMAILS` | `DRIPDROP_ROUNDUP_EMAILS` | Arena staff can read the new instance's roundups |
| `ats.py:31` | `ALLOWED_EMAILS` | reuses `DRIPDROP_ATS_EMAILS` | Same as above, in the ATS module |
| `ats.py:36` | `_OWNER_BACKFILL_EMAIL` | `DRIPDROP_OWNER_EMAIL` | Pre-multi-user records assigned to an Arena account |
| `ats.py:897` | `_EMAIL_SKIP_DOMAINS` | `DRIPDROP_INTERNAL_DOMAINS` | **Candidate sequences can be mailed to their own recruiters** |

Six variables in total. `DRIPDROP_ROUNDUP_EMAILS` and `DRIPDROP_OWNER_EMAIL`
were added during implementation: the roundup viewer allowlist and the ATS
owner-backfill address are separate gates from the two they sit beside, and
leaving either hardcoded would have named an Arena account on the new
instance.

`ats.py:897` is the most serious. It skips recruiter addresses when choosing which
address on a record belongs to the candidate. Configured for Arena only, it will
not skip the venture's own staff addresses, so its internal recruiters can be
enrolled into candidate outreach.

`DRIPDROP_SUPER_ADMINS` is a seventh Arena-specific gate, but it was already
environment-driven before this work (`flowdrip_app.py:1683`), so it needs no code
change — only a value in the new instance's `.env`. It is listed here because it
shares the others' failure mode: left unset it names
`michael.vaughn@arenastaffing.net`, and the venture's own admin holds no keys on
his own instance.

`_ADMIN_EMAILS` turned out to be an eighth, and a worse one: a hardcoded pair of
Arena addresses checked *in addition to* `DRIPDROP_SUPER_ADMINS`, so setting that
variable did not revoke them. It becomes `DRIPDROP_ADMIN_EMAILS`.

> **Open question for Mike.** The historical pair is
> `michael.vaughn@arenastaffing.net,mkvaughn2023@gmail.com`. Everything else in
> the codebase and in `deploy/env.171.example` uses **`mkvaughn1987@gmail.com`**.
> The `2023` address is preserved verbatim as the default rather than silently
> corrected, because changing a default that grants admin on Arena production is
> not a change to make on inference. Confirm whether `2023` is a real account or
> a typo, then either keep it or drop it.

Each variable parses as a comma-separated list, trimmed, lowercased, empty entries
dropped. An unset variable yields today's Arena value.

### 2. Outbound identity — what leaves the box

The access gates only govern who gets in. A second class of hardcoding governs
what the venture's *recipients* see, and it fails silently: mail sends, images 404,
and the footer names the wrong company. A central block in `flowdrip_app.py`
(just after `_env_list`) defines `_env_str`, `_PUBLIC_ORIGIN`, `_COMPANY_NAME`,
`_COMPANY_ADDRESS` and `_JWAY_BANNER_URL`; the rest is call sites reading them.

| New var | Default | Effect if left unfixed |
|---|---|---|
| `DRIPDROP_PUBLIC_ORIGIN` | `https://dripdripdrop.ai` | Every absolute URL in outgoing mail — hosted images, password-reset links, newsletter deep links, the onboarding API example — points at Arena's host. The instance writes image files to its **own** disk and links them on Arena's domain, so every image in the venture's mail 404s. |
| `DRIPDROP_COMPANY_NAME` | `Arena Staffing` | AI drafting prompts, submittal/match instructions and the Roundup page all name Arena as the sender's employer. |
| `DRIPDROP_COMPANY_ADDRESS` | Arena's street address | The CAN-SPAM postal footer on every Roundup issue carries Arena's registered address. This is a legal requirement on commercial email and it must be the *sending* firm's own address. |
| `DRIPDROP_JWAY_BANNER_URL` | `{origin}/static/jway_banner.png` | Arena-branded artwork in every J's Way newsletter body. Set empty to drop the image entirely. |

Alongside those, a set of literal-text fixes with no variable attached, because
the right answer is generic copy rather than configuration:

| Site | Was | Now |
|---|---|---|
| `deploy/arena_pdfs.py` no-logo branch | drew the "ARENA / DIRECT HIRE" wordmark on client-facing PDFs | draws the user's own company name, falling back to "Your Company" |
| `flowdrip_app.py` — 25 stock campaign templates | bodies signed `Mike` / `Best,\nMike` | sign-off deleted; the user's signature is auto-appended at send time, so the literal was both wrong and redundant |
| `flowdrip_app.py` — `sig_name = "Mike"` ×4 | hardcoded fallback in four AI-draft prompts | new `_sig_first_name()` helper: first token of the user's signature file, else the local part of their own address, else `"the recruiter"` |
| `ats.py` record OWNER column | rendered `"Mike Vaughn"` for any record with no `added_by` | renders `"Unassigned"` |
| `_HOLIDAYS` notes ×3 | "Arena's here when it's time to scale" | first-person plural, matching every other entry |
| few-shot example, 4×4 EMAIL 3 prompt, style-guide examples, Roundup UI copy, tenant name placeholder | named Arena or Mike | generic |

A missing signature file is the **default** state for a new account, so the
`sig_name` fallback was not an edge case: until a user wrote a signature, their
AI-generated drafts went out written as Mike.

### 3. Deployment plumbing

| File | Change |
|---|---|
| `deploy/Caddyfile.171` | **New.** A separate Caddyfile for `171.dripdripdrop.ai`. It cannot be a second site block in Arena's file: Caddy tries to obtain a certificate for **every** block it loads, so a 171 block on Arena's box would fail ACME forever for a hostname whose A record points elsewhere, and vice versa. Carries the same blue/green `lb_policy first` + `/healthz` failover, and deliberately omits the `mcp.*` and internal `:8082` blocks. |
| `deploy/setup-server.sh` | Steps 5–6 now name the right Caddyfile per instance and state why, and call out the Cloudflare **Full (strict)** requirement. Normalized to LF — it runs on Ubuntu, and CRLF yields `bad interpreter: /bin/bash^M`. |
| `mcp_server/dripdrop_client.py` | `PUBLIC_ORIGIN` now reads `DRIPDROP_PUBLIC_ORIGIN`. It is stamped as `Origin`/`Referer` on loopback API calls; a white-label instance sending Arena's origin is misidentifying itself. |
| `deploy/dripdrop-mcp.service` | `DRIPDROP_MCP_PUBLIC_URL` made explicit, and `EnvironmentFile=` moved last so `/opt/dripdrop/.env` can override per instance. Also commits the 2026-08-29 live hotfix that was never committed back: `DRIPDROP_API_BASE_URL` is `:8082`, Caddy's loopback blue/green endpoint, not `:8080`, which was pinned to blue and broke every MCP tool call whenever a deploy left the app on green. |

### What was deliberately *not* changed

The Arena 4×4 / 5×5 / 5×3 sequences are Arena's **named BD product**, shipped as
a DripDrop feature — not stray branding. The campaign registry, the chooser
tiles, and the hand-authored step bodies stay. Critically, the campaign-type
detection regex at `flowdrip_app.py:~8513` matches on the literal `arena`;
removing it breaks campaign detection outright.

**This is the one open question the departure makes sharper, not easier.** The
instance ships campaigns named for the company Mike is leaving, and prospects will
see that name. Three options, none free:

1. **Keep the names.** Zero work, zero risk of breaking detection. But the venture
   markets a product carrying Arena's name, which is a licensing question for Mike.
2. **Rename in the UI only**, leaving the internal registry keys and the `arena`
   regex untouched. Moderate work, detection keeps working, prospect-visible name is
   clean. **Recommended.**
3. **Rename throughout**, keys and regex included. Cleanest, and the most likely to
   break campaign detection on data already written with the old keys.

Whichever is chosen, it is a pre-launch decision: it changes what recipients see.

### `_4X4_VALUE_PROPS` — launch blocker (code done, copy still owed)

`_4X4_VALUE_PROPS` asserts Arena's specific commercial claims (80–90% fill rate,
2–3 week fill time, Replacement Guarantee) as fact in outgoing email. On a client
instance this was a "should fix." For a new venture it is a **blocker before the
first 4×4 send**: a company with no placement history cannot truthfully assert a
fill rate or guarantee, and these are outbound commercial claims to strangers.

**Now config-driven** via `DRIPDROP_VALUE_PROPS`, defaulting to Arena's text so
Arena is unaffected. The audit found the claims at **two** module-level sites, not
one:

| Site | What it was |
|---|---|
| `AICB_CAMPAIGN_TYPES` → `"fourbyfour"` entry | the claims written out longhand inside the step-5 prompt |
| the 4×4 prompt builder | interpolated `_4X4_VALUE_PROPS` |

Both now read the one constant. Because the registry is a module-level literal
evaluated at import, the constant had to move up into the identity block
(`flowdrip_app.py:110`) — it is a config value, and it now sits with the others.

The 5×5 and 5×3 registry entries were audited and carry no performance or
guarantee language of their own — no fill rate, no fill time, no guarantee, no
cost figure. Whatever claims they make come through the shared slate machinery
(`_ARENA_SLATE_TYPES`), so they are covered by the same variable.

**Still owed, and still a blocker:** the actual replacement text. Setting
`DRIPDROP_VALUE_PROPS=` (empty) drops the section and is the honest default until
there are real numbers. One softer instance remains at `flowdrip_app.py:~30845`,
where the one-pager generator instructs the model to write bullets on
"replacement guarantees, no-fee-until-start, outcome-based pricing." It asserts no
figures, but it does presume commercial terms. Left alone deliberately — fixing it
needs a decision about what terms the venture actually offers, not a code change.

## Provisioning sequence

1. Ship the config vars to Arena production, **leaving every new variable
   unset there**. Verify Pipeline still loads for `@arenastaffing.net`.

   Inertness was verified against `main` on 2026-09-15: every new variable's
   default is byte-equal to the value `main` had hardcoded, `_env_list`'s
   lowercasing is a no-op because every default was already lowercase, and the
   new `if _JWAY_BANNER_URL:` guard is always true under its default.

   The safety comes from leaving them **unset**, not from the defaults alone.
   `DRIPDROP_ATS_EMAILS` is the one variable name read by *both* `flowdrip_app.py`
   and `ats.py`, which on `main` held two *different* allowlists (four addresses
   and two) that `_allowed_set()` unions. Setting it collapses them into one —
   correct on the new instance, but on Arena a two-address value would silently
   revoke Pipeline access for Sarah Henze and Elizabeth Simonov.
2. Provision the droplet and run `deploy/setup-server.sh`.
3. Add an A record for `171.dripdripdrop.ai` to the new droplet in the existing
   Cloudflare zone. Set SSL/TLS mode to **Full (strict)** — Flexible mode sends
   plain HTTP to a Caddy that redirects to HTTPS, producing a redirect loop.
3a. Install **the 171 Caddyfile, not Arena's**:
   `cp /opt/dripdrop/app/deploy/Caddyfile.171 /etc/caddy/Caddyfile && systemctl restart caddy`.
   Copying Arena's file — which is what `setup-server.sh` used to say — leaves
   the box with no site block for this hostname and therefore no TLS cert.
4. Write `/opt/dripdrop/.env` from the annotated template `deploy/env.171.example`,
   which carries every variable below with the venture's domain already filled in:
   - `DRIPDROP_SECRET` — freshly generated, never reused from Arena's instance
   - `ANTHROPIC_API_KEY` — a key from **Mike's own Anthropic org**, not Arena's.
     Must not be a key created under Arena's org, including in a workspace there:
     workspace keys are linked to their creating user and are deactivated when that
     user leaves the organization. A `Thrive Modal` workspace
     (`wrkspc_012cqUFL1Bb2cQ16z33TaVHj`) was created under Arena's org on 2026-09-15
     before this was understood. The `dripdrop-171` key was **deleted 2026-09-15**;
     the empty workspace still needs archiving (Console → Organization settings →
     Workspaces → ⋮ on the Thrive Modal row → Archive).
     Set no expiry on the replacement: an expiring key on an unattended box fails as
     scattered AI errors, not as anything that says "expired." Set a workspace spend
     limit.
   - `DRIPDROP_INVITE_CODES` — a fresh code. **Unset does not mean closed**:
     the loader falls back to a code hardcoded into every build, Arena's
     included, so an unset value lets anyone holding Arena's code register on
     the new instance.
   - `DRIPDROP_SUPER_ADMINS` — Mike. No client handover; this is his instance.
   - `GOOGLE_REDIRECT_URI`, `MS_REDIRECT_URI` — on `171.dripdripdrop.ai`
   - `DRIPDROP_ATS_DOMAINS`, `DRIPDROP_INTERNAL_DOMAINS` — the venture's email
     domain, `thrivemodal.com`. **Both must be set**, or the résumé extractor
     will not skip the venture's own recruiters (see `ats.py:897` above).
   - `DRIPDROP_ATS_EMAILS`, `DRIPDROP_ROUNDUP_OWNER`, `DRIPDROP_ROUNDUP_EMAILS`,
     `DRIPDROP_OWNER_EMAIL`, `DRIPDROP_ADMIN_EMAILS` — the venture's admin accounts
   - `DRIPDROP_PUBLIC_ORIGIN` — `https://171.dripdripdrop.ai`. Left at the
     default, every image in the venture's outgoing mail 404s.
   - `DRIPDROP_COMPANY_NAME`, `DRIPDROP_COMPANY_ADDRESS` — the **legal name and
     registered postal address of the entity actually sending** (CAN-SPAM). Placeholder
     values are fine while provisioning; they must name the real sending entity before
     any real recipient. Settle first whether the venture is its own entity or trades
     under the partner's — this field has to match that answer.
   - Sending identity note: outbound mail carries the connected mailbox's domain. While
     that domain is the partner's, the venture's sending reputation and the partner's
     web presence are the same reputation. A bad early run damages theirs too.
   - `DRIPDROP_JWAY_BANNER_URL` — leave empty until the venture has its own artwork

   `DRIPDROP_ROUNDUP_OWNER` is the account whose folder *stores* every issue and the
   identity the send worker runs as. Set it to the address Mike intends to keep
   permanently — not a provisioning placeholder. Moving it later means copying issues
   across user folders, so the cost of getting it wrong rises with every issue sent.
5. Register the Google callback URL. **This was previously recorded as blocked on
   the partner. It is not** — corrected 2026-09-16. Every scope the app requests
   (`gmail_oauth.py:48`: `gmail.send`, `gmail.readonly`, `openid`/`email`/`profile`)
   is consented per user for that user's own mailbox. There is no domain-wide
   delegation anywhere in the flow, so no Workspace admin is involved and the Cloud
   project can live under a personal Google account with the consent screen set to
   External. Mike will **not** have a `thrivemodal.com` mailbox, and does not need one.

   The real constraint is publishing status. An app left in **Testing** has its
   refresh tokens expired by Google after ~7 days, which for a scheduled sender means
   every connected mailbox stops sending about a week after it is connected, silently.
   Move the app to **In production** before relying on it; `gmail.*` are restricted
   scopes, so that is where verification review applies.

   Microsoft is optional and can be skipped entirely — `ms_email.is_configured()`
   is False unless both `MS_CLIENT_ID` and `MS_CLIENT_SECRET` are set. The redirect
   URIs are already environment-driven (`deploy/gmail_oauth.py:33`,
   `deploy/ms_email.py:16`); no code change needed.

   **Deliverability is the part that the gmail decision actually costs.** Outbound
   carries the connected mailbox's domain, and cold B2B outreach from a consumer
   `@gmail.com` address has no SPF/DKIM/DMARC under the venture's control and is
   filtered hard. Mike already owns `dripdripdrop.ai`, so a mailbox on that domain is
   available today, needs nobody's permission, and is strictly better than gmail for
   sending. Recorded as a recommendation, not a blocker.
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
  it only if the venture needs it.
- **Shared reporting across instances.** The instances are deliberately isolated.
- **Data migration of any kind.** The new instance starts empty.

## Verification

- Every new variable, unset, reproduces current behavior exactly — verified by
  the existing test suite against the 15-failure baseline. Run 2026-09-15:
  **15 failed / 617 passed**, matching the documented baseline *list* item for
  item (6 genuine committed failures + 9 uncommitted orphan-test failures). No
  new regressions from any of the ~24 edits. Baseline against the list, never
  the count — a count alone cannot distinguish a regression from a
  checkout-cleanliness difference.
- `python -m py_compile flowdrip_app.py ats.py mcp_server/dripdrop_client.py`
  clean.
- Line endings verified before deploy. `flowdrip_app.py` (0 CRLF / 56,526 LF),
  `ats.py`, `deploy/Caddyfile.171`, `deploy/dripdrop-mcp.service`,
  `deploy/env.171.example` and `deploy/setup-server.sh` are all pure LF. This is
  not pedantry: `core.autocrlf=true` with no `.gitattributes` means `git apply`
  CRLF-ifies the *working* file while git's clean filter normalizes the blob to
  LF — and the working file is what the deploy script pushes to the Linux box.
  Count bytes in Python to check; MSYS `grep -c` misreports it.
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
