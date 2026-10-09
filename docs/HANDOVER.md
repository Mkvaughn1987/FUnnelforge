# DripDrop handover

What it takes to move DripDrop (dripdripdrop.ai) from Mike to a new owner,
and how to run it afterwards. Written 2026-10-08. Re-check the "Inventory"
section on the day; it was taken from the live server on that date.

DripDrop and inboxslide started as one codebase. They are now fully
separate: different servers, different data, different Google sign-in
clients, different Anthropic accounts. This repo contains DripDrop only.

---

## Part 1 - Handover day, in order

Every step keeps the site running. Do them in this order: nothing of Mike's
is removed until its replacement is live.

### Before the day (Mike)
1. Copy Arena's do-not-contact list into inboxslide one last time. The
   tool is `deploy/dnc_transfer.py` in the inboxslide repo: copy it to this
   server, run `export`, then `import` on inboxslide.
2. Have in writing: inboxslide and its code stay Mike's, plus any access to
   DripDrop Mike keeps afterwards.

### Code
3. The new owner creates an empty private GitHub repo.
4. Mike runs, from this repo:
   `bash deploy/handover_export.sh https://github.com/<owner>/<repo>.git`
   It checks the code against what the live server runs, then pushes a
   clean copy (one commit, no history) to the new repo. The server does not
   pull from GitHub, so this changes nothing on the live site.

### Accounts (new owner sets up, then Mike steps off)
| What | Today | Handover step |
|---|---|---|
| Server | DigitalOcean droplet `134.199.237.206`, Mike's account and card | New owner's card on first. Then move the droplet to their account or team |
| Domain | `dripdripdrop.ai` in Mike's Cloudflare account | Transfer the zone only (not the account) |
| Anthropic API (`ANTHROPIC_API_KEY`) | Key in the Arena org | New owner creates a key from **their own** login and it goes in `.env`. A key stops working when the person who made it leaves the org |
| Gmail sign-in (`GOOGLE_CLIENT_*`) | Google Cloud OAuth client | Find whose Google account owns the project. If Mike's: new owner makes their own client, redirect URI `https://dripdripdrop.ai/auth/google/callback`; users then reconnect Gmail once in Settings |
| Outlook sending (`MS_CLIENT_*`, `MS_TENANT_ID`) | Azure app registration in Arena's Microsoft tenant | Confirm it is Arena's; if it was registered under Mike's admin login, add the new owner as an owner of the app |
| Images (`UNSPLASH_ACCESS_KEY`) | Unsplash developer key | New owner's key |
| Login cookie key + invite codes (`DRIPDROP_SECRET`, `DRIPDROP_INVITE_CODES`) | Generated on the server | Optional: rotate. A new `DRIPDROP_SECRET` signs everyone out once |
| Claude connector (`mcp.dripdripdrop.ai`) | Each user adds it in their own Claude | Nothing on the server. The new owner adds it to their Claude |

5. After every new key is in `.env`, restart and check (see Part 3).
6. Mike turns off his own Claude routines and skills that create campaigns on
   DripDrop (PipelineBlast, CandidateBlast, Sales Campaign, scheduled BD
   runs). They live in Mike's Claude account and use his DripDrop API key.
7. Let it run a full day on the new keys. Then Mike removes himself from
   each account and his SSH key from the server (`/root/.ssh/authorized_keys`).

---

## Part 1b - What it costs, and moving the bills

After the handover, every bill below is the new owner's. Mike pays for
none of it. Figures are from 2026-10-08; check each provider's billing page
for the real invoice.

| Cost | About | Billed by | How it is billed |
|---|---|---|---|
| Server (droplet `563901245`, region `sfo3`, 1 CPU / 2 GB / 25 GB disk) | $12 a month (+$2.40 if weekly backups are on) | DigitalOcean | Monthly invoice on the 1st, for the hours used the month before, charged to the card on the account |
| AI (Claude API) | Was $50-65 a month May-Sept; October is on pace for ~$230 (research PDFs now use a larger model plus web search) | Anthropic | Prepaid credits on the org, or auto-reload from its card. Every AI feature in the app draws from the key in `.env` |
| Domain `dripdripdrop.ai` | .ai names have a 2-year minimum; paid through 2028-04-09 | Cloudflare Registrar | Renews from the card on the Cloudflare account that holds the domain |
| DNS, HTTPS, GitHub, Google sign-in, Microsoft app, Unsplash | $0 | various | Free tiers |

Not part of the server bill: each user's own Claude, ZoomInfo and email
accounts. Email goes out through each user's own Gmail or Outlook, so there
is no sending service to pay for.

The app logs every AI call with its cost in
`/opt/dripdrop/data/ai_usage.jsonl` (also on the admin AI-usage page). The
Anthropic console is the real bill: web-search fees and anything outside
the app do not appear in that log.

### Moving each bill
**DigitalOcean.** A droplet cannot be moved straight to another person's
account. Two ways to hand it over:
1. *Hand over the team (simplest, no downtime).* In DigitalOcean every
   account is a "team". If the team holding this droplet holds nothing else
   of Mike's, invite the new owner, make them owner, they add their card,
   Mike removes his card and leaves the team.
2. *Rebuild in their account.* Take a snapshot, have DigitalOcean support
   move it, or build a fresh 2 GB droplet and copy `/opt/dripdrop` across.
   Then point the Cloudflare DNS record at the new IP. More work, and a few
   minutes of downtime.

Either way, the invoice on the 1st covers the month before and goes to
whichever card is on file that day. Settle the handover month between you.

**Anthropic.** Simplest: the new owner opens their own Anthropic account,
buys credits, makes a key, and it replaces `ANTHROPIC_API_KEY` in `.env`
(restart both colors). Then Mike deletes the old key and turns off
auto-reload on his org. Until the old key is deleted, any use of it bills
Mike.

**Cloudflare.** Moving `dripdripdrop.ai` to the new owner's Cloudflare
account moves its renewal with it. Check after the move that the domain
shows in their account with auto-renew on, before Mike removes his card.

### Mike's "stop paying" check, after the day
- DigitalOcean: his card removed, or he has left the team. Next invoice
  shows nothing for the droplet.
- Anthropic: old DripDrop key deleted, auto-reload off, no new usage.
- Cloudflare: `dripdripdrop.ai` gone from his account.
- His own Claude routines that run against DripDrop turned off.

---

## Part 2 - Inventory (live server, 2026-10-08)

- Ubuntu 24.04, 1 vCPU, 2 GB RAM. Keep 2 GB minimum: the app loads large
  JSON files in one process.
- `/opt/dripdrop/app` - the code. Plain files, **not** a git checkout.
- `/opt/dripdrop/data` - everything users have (1.9 GB, 24 accounts):
  `users.json`, `users/<email>/`, `tenants/`, `teams/`. Back this up.
- `/opt/dripdrop/backups` - one folder per deploy, the files it replaced.
- `/opt/dripdrop/.env` - every key and setting (names listed in Part 1).
- `/opt/dripdrop/venv` - Python environment (`requirements.txt`).
- Services:
  - `dripdrop` (port 8080) and `dripdrop-green` (port 8081): the same app
    twice. Caddy sends traffic to whichever is healthy, so one can restart
    while the other serves. Only one of them sends email at a time (leader
    election inside the app).
  - `dripdrop-mcp` (port 8090): the Claude connector at
    `mcp.dripdripdrop.ai`. It reaches the app through `127.0.0.1:8082`.
  - `caddy`: HTTPS and routing, config in `deploy/Caddyfile`.
- Cron, daily 04:15: `/opt/dripdrop/scripts/queue_maintenance.py` (copy in
  this repo's `scripts/`) trims the send queue. Without it the queue file
  grows past 100 MB and the app slows down.

### Server vs repo
Checked file by file on 2026-10-08. Everything the app runs is in this repo,
with three known exceptions that `deploy/handover_export.sh` skips:
- `arena_pdfs.py` in the app root is an old copy from April. The app loads
  `funnel_forge/arena_pdfs.py` instead (it puts `funnel_forge/` first on
  the import path). Safe to delete from the server.
- `scripts_backfill_api_key_plaintext.py` was a one-off, already run.
- `funnelforge_core.py`: the repo holds a newer version (per-user queue
  paths) that was never deployed. The server's older copy is what runs and
  works. Test it before ever deploying the repo's version.

Also on the server and deliberately not in the repo: dozens of
`*.bak*` copies from old deploys, `.nicegui/` (login sessions), `.env`.

---

## Part 3 - Running it

### Deploying a change
`_deploy_zero_downtime.sh` (run from the repo root) uploads
`flowdrip_app.py` plus the files listed in its `EXTRA_FILES`, swaps colors
and waits for `/healthz`. Set `SERVER` and `SSH_KEY` at the top to your own.
A change to any other module (`ai_prompts.py`, `staffing_prompts.py`,
`sales_campaign.py`, ...) only reaches the server if you add it to
`EXTRA_FILES` or copy it up yourself; then restart both colors.
`dripdrop-mcp` only needs a restart when `mcp_server/` changes.

Before any deploy, check the server still has what you think it has:

```
ssh root@<server> "cd /opt/dripdrop/app && tr -d '\r' < flowdrip_app.py | sha256sum"
git show HEAD:flowdrip_app.py | tr -d '\r' | sha256sum
```

Compare with line endings stripped (the `tr -d '\r'`): server files can be
CRLF, so raw git hashes never match. If they differ, someone changed the
server directly. Copy the server's file back into the repo before deploying,
or the deploy silently undoes that change.

### Checking it is healthy
```
systemctl show -p NRestarts dripdrop dripdrop-green dripdrop-mcp
curl -s -o /dev/null -w '%{http_code}\n' https://dripdripdrop.ai/healthz
journalctl -u dripdrop --since '10 min ago' | grep -i traceback
```
`systemctl is-active` alone is not enough: a crash-looping service reads
"active" between restarts. NRestarts should not climb.

### Rolling back
Every deploy leaves the replaced files in `/opt/dripdrop/backups/<stamp>/`.
Copy them back into `/opt/dripdrop/app/` and
`systemctl restart dripdrop-green dripdrop`.

### Tests
`DRIPDROP_SECRET=x python -m pytest -q` from the repo root. All pass
except a skip for a data file that only lives on the server.

### Things that bite
- `flowdrip_app.py` is very large (~60k lines) and sometimes defines the
  same helper twice; the later one wins silently. Search before adding one.
- Anything a module-level setting reads must be defined above it in the
  file, or the app crashes on start.
- The app keeps the send queue in memory. Stop both colors before editing
  queue files on disk, or the app writes its copy back over yours.
