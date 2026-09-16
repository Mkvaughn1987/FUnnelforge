# inboxslide.ai — state of play

Written to be read cold, with no memory of the conversation that produced it.
Companion to `LAUNCH-inboxslide.md`, which is the full runbook. This file is the
shorter question: what is already true, and what is left.

**Last verified: 2026-09-16.** Everything in the first section was checked by
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
| 2 | DNS | `app.inboxslide.ai` → `216.128.142.21`, still **grey cloud** (DNS only) |
| 3 | `setup-server.sh` | Complete |
| 4 | `bootstrap-instance.sh` | Complete — all six phases |
| 5 | HTTPS | **Verified: HTTP 200, certificate valid, HTTP→HTTPS 308** |

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

### 1. The Anthropic API key — Mike only

`/opt/dripdrop/.env` currently holds the literal string
`ANTHROPIC_API_KEY=sk-ant-PLACEHOLDER-REPLACE-ME`. The app starts fine with it
because `bootstrap-instance.sh` never validates the key, it only writes it — but
nothing that calls Claude will work.

A helper is already on the server. Mike runs:

```
ssh root@216.128.142.21
bash /root/setkey.sh
```

It reads the key invisibly, rejects anything not starting with `sk-ant-`, writes
it, restarts the service, and **prints the invite code**, which he needs for
step 3 below and which is not recorded anywhere else.

The key must come from the **new** Anthropic org, under the login
`mkvaughn11@gmail.com` — not Arena's org (`6fa72573-ae2d-4da4-9c6c-9e2b18b2f087`).
A key minted in Arena's org has two ways to die: Arena can revoke it, and
Anthropic deactivates it automatically if Mike is ever removed from that org.

### 2. Cloudflare — put the proxy back in front

Order matters, and getting it wrong takes the site down.

1. Cloudflare → **SSL/TLS** → **Full (strict)**
2. Cloudflare → **DNS** → click the grey cloud on the `app` record → **orange**

Not **Flexible**: it sends plaintext to a server that redirects everything to
HTTPS, which is an infinite redirect loop.

Confirm afterwards — if the resolved address is still `216.128.142.21`, the
proxy is not on yet:

```
nslookup app.inboxslide.ai 1.1.1.1
curl -sI https://app.inboxslide.ai/ | head -1
```

### 3. Register — Mike only

`https://app.inboxslide.ai`, with **email and password** plus the invite code.

**Never a "Sign in with Google" button.** In this app the Google login flow and
Gmail-for-sending are the same grant, so signing in with Google hands over
permission to send as him, and campaigns would start going out from his personal
gmail. It is deliberately disabled on this instance; if the button appears,
something is misconfigured — stop.

His gmail is the **login identity only**. It is never the sending mailbox.

### 4. Brevo — the actual sender

Runbook Step 8. Verify a sender, add the SPF and DKIM records to Cloudflare,
create an `xkeysib-` key, paste it into Settings. Then Cloudflare → Email →
Email Routing to forward replies to his gmail (no mailbox needed).

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
