# DripDrop handover to Arena IT

DripDrop (dripdripdrop.ai) is moving from Mike Vaughn to Arena IT. This
document is how IT takes full control (code, server, domain, keys and
in-app admin) and how to run and change it afterwards.

Updated 2026-11-14. The code in this repo matches the live server as of
that date, apart from the files listed under "Server vs repo". The server
figures in Part 4 were taken on 2026-10-08. Re-check them on the day.

---

## Part 1 - What IT will own

When the handover is finished, IT holds every one of these and Mike holds
none of them:

| Area | What IT gets | Lets IT |
|---|---|---|
| Code | Owner of a private GitHub repo with this code (one clean commit, no history) | Change anything in the app |
| Server | Root SSH to the DigitalOcean droplet, inside IT's own DigitalOcean team | Deploy, restart, back up, read logs |
| Domain + DNS | `dripdripdrop.ai` zone in IT's own Cloudflare account | Point the site anywhere, renew the domain |
| AI | IT's own Anthropic API key in `/opt/dripdrop/.env` | Every AI feature (prompts, PDFs, research) |
| Gmail sending + sign-in | IT's own Google Cloud OAuth client | Users connecting Gmail |
| Outlook sending | Owner of the Azure app registration in Arena's tenant | Users connecting Outlook |
| In-app admin | IT's email in `DRIPDROP_SUPER_ADMINS` and marked admin on the Admin page | Manage users, teams, tenants, the admin pages |
| Claude connector | `mcp.dripdripdrop.ai` runs on the same server | Nothing extra to own; any user adds it in their own Claude |

---

## Part 2 - Handover day, in order

Every step keeps the site running. Nothing of Mike's is removed until IT's
replacement is live.

### A. Before the day

**IT:**
1. Create the accounts, all under one shared Arena IT email:
   GitHub (or GitHub organisation), DigitalOcean, Cloudflare, Anthropic
   Console (with credits loaded), and Google Cloud.
2. Create an empty **private** GitHub repo and send Mike its URL.
3. Make an SSH key for the server (`ssh-keygen -t ed25519`) and send Mike the
   **public** half (`~/.ssh/id_ed25519.pub`). Never send the private half.

**Mike:**
4. Agree in writing what DripDrop access (if any) Mike keeps afterwards.
5. Send IT a list of his own Claude routines that use DripDrop (step 13),
   so IT knows what stops when Mike turns them off.

### B. Code (Mike, 10 minutes)
6. From this repo's root, with a clean working tree:
   `bash deploy/handover_export.sh https://github.com/<it-owner>/<repo>.git`
   It first compares every Python file on the live server with this repo,
   then pushes a clean one-commit copy as `main`. The server does not pull
   from GitHub, so this changes nothing on the live site. If it reports a
   file that differs, see "Server vs repo" in Part 4 and fix that first.

### C. Server access (Mike adds, IT checks)
7. Mike adds IT's public key to `/root/.ssh/authorized_keys` on the server.
8. IT checks it can log in: `ssh root@134.199.237.206`.
9. Mike moves the droplet into IT's hands (see "Moving each bill",
   DigitalOcean). The simplest way: invite IT to the DigitalOcean team that
   holds the droplet, make IT the owner, IT adds its card.

### D. Domain (Mike starts, IT accepts)
10. Mike moves the `dripdripdrop.ai` zone (only the zone, not his whole
    Cloudflare account) to IT's Cloudflare account. IT checks the zone shows
    with its DNS records and auto-renew on.

### E. Keys (IT, on the server)
Every key lives in `/opt/dripdrop/.env`. After changing it, restart and
check (Part 3, "Checking it is healthy").

| Setting | What it is today | What IT does |
|---|---|---|
| `ANTHROPIC_API_KEY` | Key in an org Mike set up | Make a key from IT's own Anthropic login and put it here. A key stops working when the person who made it leaves its org |
| `GOOGLE_CLIENT_ID`, `GOOGLE_CLIENT_SECRET` | Google Cloud OAuth client | If the Google project is Mike's: make IT's own client with redirect URI `https://dripdripdrop.ai/auth/google/callback`. Users then reconnect Gmail once in Settings |
| `MS_CLIENT_ID`, `MS_CLIENT_SECRET`, `MS_TENANT_ID`, `MS_REDIRECT_URI` | Azure app registration in Arena's Microsoft tenant | Confirm it is Arena's. If Mike registered it under his admin login, add IT as an owner of the app |
| `UNSPLASH_ACCESS_KEY` | Unsplash developer key (newsletter images) | IT's own free key |
| `DRIPDROP_SUPER_ADMINS` | Comma-separated emails with full admin | Add IT's email; remove Mike's when done |
| `DRIPDROP_SECRET` | Signs login cookies | Optional: replace with a new random value. Everyone gets signed out once |
| `DRIPDROP_INVITE_CODES` | Sign-up invite codes | Optional: replace |

11. Restart both colors after editing `.env`:
    `systemctl restart dripdrop-green && sleep 20 && systemctl restart dripdrop`
    (and `systemctl restart dripdrop-mcp` if a connector setting changed).

### F. In-app admin
12. Mike signs in, opens the **Admin** page and makes IT's DripDrop account
    an admin (the toggle in the user list).

### G. Mike steps off
13. Mike turns off his own Claude routines and skills that create campaigns
    on DripDrop (PipelineBlast, CandidateBlast, Sales Campaign, scheduled BD
    runs). They live in Mike's Claude account and use his DripDrop API key.
14. Let it run a full day on IT's keys. Then Mike: deletes his old Anthropic
    key, removes his card and leaves the DigitalOcean team, and IT removes
    Mike's SSH key from `/root/.ssh/authorized_keys`.
15. IT removes Mike as a permanent admin in the code (Part 3, "Remove Mike
    from the code") and deploys.

---

## Part 3 - Changing DripDrop

### Remove Mike from the code (after the handover)
Some accounts are hardcoded. Edit these, then deploy:

| File | Name | What it does | Change |
|---|---|---|---|
| `flowdrip_app.py` | `_ADMIN_EMAILS` (about line 2741) | Permanent admins, cannot be demoted in the UI | Put IT's email in, take Mike's two out |
| `flowdrip_app.py` | `_super_admin_emails()` default (about line 1728) | Used only when `DRIPDROP_SUPER_ADMINS` is not set | Change the fallback to IT's email |
| `flowdrip_app.py` | `_ATS_ALLOWED_EMAILS` (about line 60) | Who outside `@arenastaffing.net` sees Pipeline | Remove Mike's personal gmail |
| `flowdrip_app.py` | `_ROUNDUP_ALLOWED_EMAILS` (about line 85) | Who sees The Roundup newsletter | Remove Mike's two addresses, add whoever replaces him |
| `ats.py` | `ALLOWED_EMAILS`, `_OWNER_BACKFILL_EMAIL` (about line 30) | Pipeline fallback list; owner of old pre-team candidates | Remove Mike's gmail; point the backfill owner at whoever takes his candidates |

### Making a change with Claude Code (or by hand)
1. Change the code in your repo and run the tests (below).
2. Check the server has not drifted from the repo (below).
3. Deploy with `_deploy_zero_downtime.sh`.
4. Check it is healthy. Roll back if not.

Asking Claude Code to make changes works well on this codebase. Point it at
this file first.

### Deploying a change
`_deploy_zero_downtime.sh` (run from the repo root, in Git Bash or Linux)
uploads `flowdrip_app.py` plus the files listed in its `EXTRA_FILES`, swaps
colors and waits for `/healthz`. Set `SERVER` and `SSH_KEY` at the top to
your own (it defaults to `~/.ssh/id_ed25519`).

A change to any other module (`ai_prompts.py`, `staffing_prompts.py`,
`sales_campaign.py`, `top_ten.py`, `team_contacts.py`, `zoominfo_drop.py`,
...) only reaches the server if you add it to `EXTRA_FILES` or copy it up
yourself (`scp file root@<server>:/opt/dripdrop/app/`), then restart both
colors. `dripdrop-mcp` only needs a restart when `mcp_server/` changes.

Before any deploy, check the server still has what you think it has:

```
ssh root@<server> "cd /opt/dripdrop/app && tr -d '\r' < flowdrip_app.py | sha256sum"
git show HEAD:flowdrip_app.py | tr -d '\r' | sha256sum
```

Compare with line endings stripped (the `tr -d '\r'`): server files can be
CRLF, so raw git hashes never match. If they differ, someone changed the
server directly. Copy the server's file back into the repo before
deploying, or the deploy silently undoes that change. `deploy/handover_export.sh`
does this check for every file at once.

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
`pip install -r requirements.txt pypdf`, then
`DRIPDROP_SECRET=x python -m pytest -q` from the repo root. On a machine
without an Anthropic key, tests in `test_campaign_api.py` that call the AI
fail with 503 ("AI not configured"); everything else should pass, apart
from skips for data files that only live on the server (`us_geo.csv`).

### Things that bite
- `flowdrip_app.py` is very large (~66k lines) and sometimes defines the
  same helper twice; the later one wins silently. Search before adding one.
- Anything a module-level setting reads must be defined above it in the
  file, or the app crashes on start.
- The app keeps the send queue in memory. Stop both colors before editing
  queue files on disk, or the app writes its copy back over yours.

---

## Part 4 - The server

Figures from 2026-10-08; re-check on the day.

- DigitalOcean droplet `563901245`, region `sfo3`, IP `134.199.237.206`.
  Ubuntu 24.04, 1 vCPU, 2 GB RAM, 25 GB disk. Keep 2 GB minimum: the app
  loads large JSON files in one process.
- `/opt/dripdrop/app` - the code. Plain files, **not** a git checkout.
- `/opt/dripdrop/data` - everything users have (1.9 GB, 24 accounts on
  2026-10-08): `users.json`, `users/<email>/`, `tenants/`, `teams/`.
  **Back this up.** There is no off-server backup today.
- `/opt/dripdrop/backups` - one folder per deploy, the files it replaced.
- `/opt/dripdrop/.env` - every key and setting (Part 2, step E).
- `/opt/dripdrop/venv` - Python environment (`requirements.txt`).
- Services:
  - `dripdrop` (port 8080) and `dripdrop-green` (port 8081): the same app
    twice. Caddy sends traffic to whichever is healthy, so one can restart
    while the other serves. Only one of them sends email at a time (leader
    election inside the app).
  - `dripdrop-mcp` (port 8090): the Claude connector at
    `mcp.dripdripdrop.ai` (42 tools covering every page). It reaches the
    app through `127.0.0.1:8082`.
  - `caddy`: HTTPS and routing, config in `deploy/Caddyfile`.
- Cron, daily 04:15: `/opt/dripdrop/scripts/queue_maintenance.py` (copy in
  this repo's `scripts/`) trims the send queue. Without it the queue file
  grows past 100 MB and the app slows down.

### Server vs repo
Checked file by file against the live server on 2026-11-14. Every Python
file the app runs matches this repo (including `ats.py`, copied in from
the server that day) except:
- `funnelforge_core.py`: the repo holds a newer version (per-user queue
  paths) that was never deployed. The server's older copy is what runs and
  works. Test it before ever deploying the repo's version.
- `arena_pdfs.py` in the app root is an old copy from April. The app loads
  `funnel_forge/arena_pdfs.py` instead. Safe to delete from the server.
- `scripts_backfill_api_key_plaintext.py` was a one-off, already run.

Also on the server and deliberately not in the repo: dozens of
`*.bak*` copies from old deploys, `.nicegui/` (login sessions), `.env`.

---

## Part 5 - What it costs, and moving the bills

After the handover, every bill below is Arena's. Mike pays for none of it.
Figures from 2026-10-08; check each provider's billing page.

| Cost | About | Billed by | How it is billed |
|---|---|---|---|
| Server | $12 a month (+$2.40 if weekly backups are on) | DigitalOcean | Monthly invoice on the 1st for the month before, charged to the card on the account |
| AI (Claude API) | Was $50-65 a month May-Sept; October was on pace for ~$230 (research PDFs use a larger model plus web search) | Anthropic | Prepaid credits on the org, or auto-reload from its card |
| Domain `dripdripdrop.ai` | .ai has a 2-year minimum; paid through 2028-04-09 | Cloudflare Registrar | Renews from the card on the Cloudflare account that holds it |
| DNS, HTTPS, GitHub, Google sign-in, Microsoft app, Unsplash | $0 | various | Free tiers |

Not part of the server bill: each user's own Claude, ZoomInfo and email
accounts. Email goes out through each user's own Gmail or Outlook, so there
is no sending service to pay for.

The app logs every AI call with its cost in
`/opt/dripdrop/data/ai_usage.jsonl` (also on the admin AI-usage page). The
Anthropic console is the real bill: web-search fees do not appear in that
log.

### Moving each bill
**DigitalOcean.** A droplet cannot be moved straight to another account.
1. *Hand over the team (simplest, no downtime).* Every DigitalOcean account
   is a "team". If the team holding this droplet holds nothing else of
   Mike's, invite IT, make IT the owner, IT adds its card, Mike removes his
   card and leaves.
2. *Rebuild in IT's account.* Snapshot and have DigitalOcean support move
   it, or build a fresh 2 GB droplet and copy `/opt/dripdrop` across. Then
   point the Cloudflare DNS records at the new IP. A few minutes of
   downtime.

The invoice on the 1st covers the month before and goes to whichever card
is on file that day. Settle the handover month between you.

**Anthropic.** IT's own key replaces `ANTHROPIC_API_KEY` (Part 2, step E).
Then Mike deletes the old key and turns off auto-reload. Until it is
deleted, any use of the old key bills Mike.

**Cloudflare.** Moving the zone moves the domain's renewal with it. Check
it shows in IT's account with auto-renew on before Mike removes his card.

### Mike's "stop paying" check, after the day
- DigitalOcean: his card removed or he has left the team; next invoice
  shows nothing for the droplet.
- Anthropic: old DripDrop key deleted, auto-reload off, no new usage.
- Cloudflare: `dripdripdrop.ai` gone from his account.
- His own Claude routines that run against DripDrop turned off.
