# inboxslide.ai — state of play

Written to be read cold, with no memory of the conversation that produced it.
Companion to `LAUNCH-inboxslide.md`, which is the full runbook. This file is the
shorter question: what is already true, and what is left.

**Last verified: 2026-09-16 (fourth pass, after the rebrand was deployed and the site verified live -- see step 0).** Everything in the first section was checked by
running a command, not by remembering. Re-check before trusting any of it.

---

## What Mike is doing

Mike Vaughn is leaving Arena Staffing and running his own venture (Thrive Modal)
on a second, independent copy of DripDrop at `app.inboxslide.ai`.

**Arena's instance keeps running in parallel, indefinitely, from the same
repository.** This is the single most important fact about the project. Nothing
done for inboxslide may change Arena's behaviour. The two instances share a code
repo and nothing else — separate servers, separate providers, separate Anthropic
orgs, separate data.

---

## What is already done

| # | Step | State |
|---|---|---|
| 1 | Server | Vultr, Dallas, `216.128.142.21`, Ubuntu 24.04.4 LTS, 1962 MB RAM, 52 GB disk |
| 2 | DNS | **Proxied (orange)**, SSL/TLS **Full (strict)** — resolves to Cloudflare IPs, origin hidden |
| 3 | `setup-server.sh` | Complete |
| 4 | `bootstrap-instance.sh` | Complete — all six phases |
| 5 | HTTPS | **Verified through the proxy: HTTP 200, certificate valid, `Server: cloudflare`** |
| 6 | Anthropic key | **Set.** `.env` no longer holds the placeholder |

Beyond the runbook: hostname set to `inboxslide`; SSH hardened to **key-only**
via `/etc/ssh/sshd_config.d/00-inboxslide-hardening.conf` — named `00-` on
purpose, because sshd is first-match-wins and Vultr ships a `50-cloud-init.conf`
that turns password auth back on.

The app checkout at `/opt/dripdrop/app` is on branch `feat/whitelabel-instance`.

Two settings that are already correct and should not be "fixed":

- **`DRIPDROP_VALUE_PROPS` in `/opt/dripdrop/.env` is the safe draft** —
  contingency, replacement guarantee, cost-effective, dedicated attention. It
  does **not** contain the 80–90% fill rate and 2–3 week time-to-fill that the
  *code default* asserts. Those are Arena's placement history and a new firm
  cannot truthfully claim them. Mike may still want to personalise the wording,
  but there is no live legal problem.
- **Caddy logs `localhost:8081 connection refused` every few seconds.** Benign.
  That is the blue/green failover health check; only blue (8080) runs on a fresh
  box. Do not chase it.

---

## What is left, in order

### 0. Deploy the rebrand -- DONE 2026-09-16, do not re-run as if pending

**This step is complete and verified live.** The server is on `836e759`, all 27
branding variables are in `/opt/dripdrop/.env`, and `app.inboxslide.ai` renders
in forest/ivory. Verified: app `200`, apex `301` -> app `200`, both logo PNGs
`200` (~44 KB each), `NRestarts` 0, zero errors since process start. Nothing
below in this section needs doing again; it is kept as the record of how the
deploy works.

The command, for reference (pull, write the branding variables, restart, print
`active`):

```
ssh root@216.128.142.21 "cd /opt/dripdrop/app && git pull --ff-only origin feat/whitelabel-instance && python3 deploy/sync_brand_env.py --apply && systemctl restart dripdrop && sleep 12 && systemctl is-active dripdrop"
```

**The first attempt at this took the site down, and the trap is still live in the
file.** Pulling `a639a2a` crash-looped the service on import:
`NameError: name '_env_color' is not defined`. The `WEB_*` palette is assigned at
module level in `flowdrip_app.py`, but `_env_color` was defined ~140 lines below
it. Python runs module-level assignments at import, so the app never booted and
Caddy served `503`. Fixed in `836e759` by moving the helper up beside `_env_str`.
**Anything a module-level literal reads must be defined above it** -- this file
has now been bitten twice (see also `DRIPDROP_VALUE_PROPS` moving to line 110).

Two things that misled during that incident, worth knowing before trusting a
green result: `systemctl is-active` printed `active` *in the gap between crash
restarts*, so it is not a health check on its own -- check `NRestarts` too. And
`journalctl --since '5 min ago'` still counts the pre-fix crashes, which makes a
healthy box look broken; grep since `ExecMainStartTimestamp` instead. The
`sleep 3` above was also too short for startup and returned `activating` (exit
code 3) on a deploy that had in fact succeeded -- hence `sleep 12`.

`deploy/sync_brand_env.py` is new in `34bd0a2`. It upserts **only** keys matching
`DRIPDROP_BRAND_*`, `_WEB_*`, `_TERM_*`, `_THEME_*` and `_GREETINGS` out of
`deploy/env.inboxslide.example` (27 of them) into `/opt/dripdrop/.env`, taking a
timestamped backup first. The scoping is deliberate: the example file carries
placeholder values for real credentials, so a general "sync everything" tool
would overwrite a live API key with the word `CHANGEME`. It is idempotent, and a
dry run unless given `--apply`.

Afterwards Mike must hard-refresh (Ctrl+Shift+R) -- and note the separate gotcha
that an already-open tab's client-side nav dies across a restart, so reloading
the tab is required regardless.

**What he should then see:** forest green and ivory on every signed-out page
(login, register, forgot, reset, setup, landing, `/privacy`, `/terms`), the
inboxslide logo instead of the DripDrop wordmark, sales copy instead of
recruiting on the landing page, and slide-metaphor dashboard greetings instead
of the water-metaphor ones.

**Arena is unaffected**, by construction: every one of those variables falls back
to Arena's current value when unset, and Arena sets none of them. Byte-identity
of Arena's rendered output was proven for every customer-facing page. The one
documented exception is the internal admin AI-usage page, where five
near-identical navy shades were folded onto the nine palette names.


### 1-2. API key and Cloudflare — DONE 2026-09-16

Both verified live. The key is set (a helper `/root/setkey.sh` remains on the box
if it ever needs replacing; it takes the key invisibly and reprints the invite
code). Cloudflare is **Full (strict)** with the `app` record **proxied**.

The invite code is in `/opt/dripdrop/.env` under `DRIPDROP_INVITE_CODES` and can
be reprinted with `grep '^DRIPDROP_INVITE_CODES=' /opt/dripdrop/.env | cut -d= -f2`.

### 3. Register — Mike only

`https://app.inboxslide.ai`, with **email and password** plus the invite code.

There is no "Sign in with Google" button on the login page, and there never
was — registration is email + password + invite code. An earlier version of
this file and of the runbook warned against such a button, on the theory that
Google login and Gmail-for-sending were the same grant. **That was wrong.**
The only Google callback in the app is `/auth/google/callback`
(`flowdrip_app.py:54391`), and every branch that starts it lives in the
Settings / mailbox region (`:43797`, `:43998`, `:44346`). Connecting Gmail is
a deliberate act in Settings, not a side effect of signing in.

His gmail is still the **login identity**. Whether it is also the sending
mailbox is a separate choice made in Settings.

### 4. Gmail OAuth — the actual sender, and it is already live

`GOOGLE_CLIENT_ID`, `GOOGLE_CLIENT_SECRET` and `GOOGLE_REDIRECT_URI` are all
set in `/opt/dripdrop/.env`, and mail sends through Gmail. The redirect URI
*must* be overridden, because it defaults to Arena's host
(`gmail_oauth.py:35`), and it must match the Google Cloud console entry exactly.

Two things that bite later:

- An OAuth app left in **Testing** has its refresh tokens expired by Google
  after about 7 days, so the scheduled sender stops silently a week after the
  mailbox connects. Publish it to **In production**.
- Consent is per-user (`gmail_oauth.py:48`), so no Workspace admin and no
  domain owner is involved.

Microsoft Graph is deferred and optional. If it is ever configured it
**outranks** Gmail — the send chain takes Graph, then Gmail, then SMTP,
whichever holds a token first.

**Outstanding:** the Google client secret currently in `.env` was pasted into a
chat transcript and is considered burned. Rotate it — Google Cloud → the
`inboxslide` client → Client secrets → **+ Add secret**, then disable and
delete the old row → on the server, `bash /root/setgoogle.sh`. Rotating does
**not** disconnect an already-connected mailbox; the stored refresh token keeps
working.

### 5. DNC transfer — before the first send, not after

This instance has no memory of who unsubscribed from Arena or bounced there.
Running both without reconciling means emailing the same prospect from two
companies in one week, or emailing someone who opted out.

`deploy/dnc_transfer.py` does it, and is already on the server. Commands are in
runbook Step 9. Two things about the ordering:

- The import needs Mike's user directory, which is only created at **first
  login** — so this comes after step 3, not before.
- The export half only reads. It changes nothing on Arena.

### 6. Anthropic housekeeping

Confirm the key was created in the new org, set expiry to **Never**, add a
workspace spend limit. Archive the empty workspace
`wrkspc_012cqUFL1Bb2cQ16z33TaVHj` via Organization settings → Workspaces →
row ⋮ → **Archive**. Never the red "Delete organization" button.

---

## The merge to main — analysed, deliberately not done

The spec recommends both instances eventually run from `main`.
`feat/whitelabel-instance` is 22 commits ahead of `main`; `main` is 16 commits
ahead of the branch. **This is not a launch blocker** — the instance runs fine
from the branch — and it was left undone on purpose rather than rushed.

A dry run says: **one conflicting file, `flowdrip_app.py`, five hunks, all
clustered in the dashboard-card region around lines 27238–27396.**

It is a delete/modify conflict, not a mechanical one. Counting occurrences
across the three versions:

| marker | merge-base | branch | main |
|---|---|---|---|
| "emails sending today" | 4 | 3 | 4 |
| the "tasks today" label | 2 | 1 | 2 |
| `_pipe_email` | 2 | 0 | 1 |

So **the branch deleted one copy of each** — almost certainly de-duplicating,
which this file is notoriously full of — while **main edited the copy the branch
removed**. Resolving it means keeping the branch's deletion *and* checking that
main's improvements (the "total responses / N this week" split, the `_pipe_email`
binding) actually landed in the surviving copy rather than only in the deleted
one.

Give that its own session, with the app runnable to check the dashboard renders.
Do not resolve it under time pressure: a bad resolution regresses **Arena's**
dashboard, not just this instance's.

---

## Rules that must not be broken

**Never copy `deploy/env.inboxslide.example` onto Arena's server.** Both
instances run the same code; the difference is entirely that this one sets a
group of env vars and Arena leaves them unset. Every one of them falls back to
Arena's original behaviour when absent. The sharpest is `DRIPDROP_ATS_EMAILS` —
setting it on Arena silently removes Pipeline access for Sarah Henze and
Elizabeth Simonov, with no error and nothing in a log.

**Secrets never enter chat.** Not API keys, not passwords, not the invite code.
Anything pasted into a conversation lands in the transcript on disk, in summaries
and in logs. They belong in `/opt/dripdrop/.env`, entered on the server. The
private key at `C:\Users\mkvau\.ssh\id_ed25519` is never shared; only the `.pub`
half. The root password that was pasted earlier is **burned** — password auth has
since been disabled on the box entirely, so it is inert, but never reuse it.

**Arena's production is reachable but writes are blocked** by the permission
classifier, and some multi-host probes are refused outright. Verify in-session,
then hand Mike the command to run himself. Do not try to route around it.

**Corrected 2026-09-16 for the inboxslide box specifically:** `git push` to
GitHub and `ssh ... git pull && systemctl restart` both ran fine from a session
on this host -- earlier notes saying the push had to land on Mike are stale. What
the classifier *does* refuse is a self-composed destructive prod write:
`git reset --hard` was denied mid-incident, which is why recovery from the `503`
had to be fix-forward (commit, push, re-pull) rather than a rollback. **Plan for
fix-forward here, not rollback**, and keep a known-good SHA handy anyway.

---

## Quick reference

```
ssh root@216.128.142.21              # key auth, no password
systemctl status dripdrop            # is the app up?
journalctl -u dripdrop -n 50         # app errors
journalctl -u caddy -n 40            # certificate / web server errors
systemctl restart dripdrop
```

Config: `/opt/dripdrop/.env` — Data: `/opt/dripdrop/data` — App: `/opt/dripdrop/app`

Nothing in any of those touches Arena.
