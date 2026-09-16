# Launching the inboxslide.ai instance

A start-to-finish runbook. Assumes no prior knowledge and no context from the
conversation that produced it. Roughly 45 minutes, most of it waiting.

**What you are building:** a second, completely independent copy of DripDrop on
its own server, at `app.inboxslide.ai`. Arena's instance keeps running,
untouched, on its own server. They share a code repository and nothing else.

---

## Before you start: two new accounts

Everything Arena runs on today is already yours — your DigitalOcean account,
your card, your Anthropic org, your Cloudflare zone — and you have said you
would transfer any of it to them.

That is exactly why the new instance needs its own accounts. **The risk is not
losing access to Arena's things. It is handing Arena your own venture by
accident**, because it happened to be sitting in the same account on transfer
day. Two signups now, instead of an untangling later under time pressure.

**The server — a different provider entirely.** Arena's droplet is on
DigitalOcean, in your account, on your card. Put this one somewhere else. These
instructions use **Vultr**; any host offering plain Ubuntu 24.04 works, because
nothing we install is provider-specific. Using a separate provider is the
cleanest possible separation — DigitalOcean does not cleanly move a single
droplet between accounts anyway, so a handover there is realistically the whole
account, and anything you leave in it goes with it.

**Anthropic — a new organization.** Same reasoning, one extra edge. An API key
belongs to the person who created it *inside that organization*, and Anthropic
deactivates the key when that person is removed from the org. So a key minted in
the org you may transfer has two ways to fail: Arena can see and revoke it, and
it dies on its own if you are later removed as a member. Create the key in a new
org on your own card, with **no expiry** and a workspace spend limit.

**Cloudflare — the existing account is fine.** `inboxslide.ai` and
`dripdripdrop.ai` both live there. Unlike a hosting account, Cloudflare *does*
move individual zones between accounts cleanly, so `dripdripdrop.ai` can be handed
over later on its own without disturbing `inboxslide.ai`. No action needed now.

---

## Step 1 — Create the server

In Vultr: **Compute → Create Instance**.

| Setting | Choose |
|---|---|
| Plan | **Shared CPU** — *not* the Dedicated CPU box it defaults to |
| Plan Selection | The row with **2 GB Memory** (~$0.018/hr, ~$12/mo) |
| Location | Whichever US city is closest to you |
| Operating System | **Ubuntu 24.04 LTS x64** |
| SSH Keys | Add your public key, then **tick it** |
| Hostname & Label | `inboxslide` |

Untick the add-ons — auto backups, IPv6, DDoS protection. All extra monthly cost,
none of it needed.

Two things that quietly cost money or break the install:

- **Shared CPU, not Dedicated.** Vultr's newer UI opens on Dedicated CPU at
  around $43/mo. Shared CPU is the same class of machine Arena runs on.
- **2 GB RAM is the floor.** There is a 1 GB plan for about half the price. The
  app parses large JSON files in memory and the kernel will kill it under load.

Sign up and deploy with any VPN **switched off**. Hosting providers score new
signups for fraud, and a VPN is the single most common reason a brand-new
account gets locked before it deploys anything.

When it finishes, check the instance is **Running**, not `Stopped` — start it if
it is not — and copy the **IP address**. You need it in the next step. It looks
like `216.128.x.x`. Do not confuse it with the instance ID, which is a long
string of letters and dashes.

---

## Step 2 — Point the domain at it (must happen BEFORE Step 4)

In Cloudflare, select the **inboxslide.ai** zone → **DNS** → **Add record**.

| Field | Value |
|---|---|
| Type | `A` |
| Name | `app` |
| IPv4 address | your server's IP from Step 1 |
| Proxy status | **DNS only** — click the orange cloud so it turns **grey** |

**The grey cloud matters and it is temporary.** When your server starts, it asks
Let's Encrypt for a free SSL certificate, and Let's Encrypt proves you own the
name by connecting directly to your server. If Cloudflare is proxying (orange),
it intercepts that connection and the certificate never gets issued. You will
turn the orange cloud back on in Step 6, once the certificate exists.

Wait about a minute for this to take effect.

---

## Step 3 — Prepare the server

Open a terminal. Connect to the server, substituting your IP:

```
ssh root@YOUR_DROPLET_IP
```

First connection warns about authenticity — type `yes`. Then run:

```
curl -fsSL https://raw.githubusercontent.com/Mkvaughn1987/FUnnelforge/feat/whitelabel-instance/deploy/setup-server.sh -o setup.sh
bash setup.sh
```

This takes 3–5 minutes and installs Python, the web server, and a firewall. Lots
of text will scroll past; that is normal. It is done when you see
`=== Setup complete! ===`.

---

## Step 4 — Install DripDrop

Still connected to the server:

```
curl -fsSL https://raw.githubusercontent.com/Mkvaughn1987/FUnnelforge/feat/whitelabel-instance/deploy/bootstrap-instance.sh -o bootstrap.sh
bash bootstrap.sh
```

It checks your DNS first and stops with a clear message if Step 2 has not taken
effect yet. Then it asks five questions:

1. **Hostname** — press Enter to accept `app.inboxslide.ai`.
2. **Login email** — press Enter to accept your gmail.
3. **Anthropic API key** — paste it. **Nothing appears as you type.** That is
   deliberate, so the key never lands in the terminal history. Paste and press
   Enter.
4. **Legal company name** — the real registered name of your business. This goes
   in the footer of every email you send; US anti-spam law requires it to be
   accurate, so this is not a placeholder field.
5. **Postal address** — same reason. Format:
   `Your Company | 123 Main St Suite 4 | Denver, CO 80202 US`

Then it runs six steps and finishes with an **invite code**.

> **Write the invite code down before you close the terminal.** You cannot
> create your account without it, and it is not shown anywhere else.

---

## Step 5 — Check it worked

Wait about 30 seconds, then open **https://app.inboxslide.ai** in a browser.

You should see the DripDrop login page with a padlock in the address bar.

If it does not load, run this on the server and read the last few lines:

```
journalctl -u caddy -n 40 --no-pager
```

Do not continue to Step 6 until the page loads with a working padlock.

---

## Step 6 — Turn Cloudflare's protection on

Now that the certificate exists, put Cloudflare back in front. **Order matters.**

1. Cloudflare → **SSL/TLS** → set encryption mode to **Full (strict)**.
2. Cloudflare → **DNS** → click the grey cloud on your `app` record so it turns
   **orange** (Proxied).

Do these in that order. And do not choose **Flexible** — it sends unencrypted
traffic to a server that redirects everything to encrypted, which produces an
infinite redirect loop and a site that will not load at all.

---

## Step 7 — Create your account

Go to **https://app.inboxslide.ai** and register with your **email and a
password**, using the invite code from Step 4.

> **Do not use a "Sign in with Google" button if you see one.** In this app,
> signing in with Google and connecting Gmail-for-sending are the same action —
> the login also hands over permission to send mail as you. The app would then
> start sending campaigns from your personal gmail address, which will get that
> address flagged. Google sign-in is deliberately switched off on this instance,
> so you should not see the button; if you do, something is misconfigured — stop
> and check.

---

## Step 8 — Connect an email sender

Your gmail account is how you log in. It is **not** what sends your campaigns.
Those are independent, and keeping them separate is what protects your personal
address.

Sign up for **Brevo** (free, 300 emails/day, no card required). In Brevo:

1. Add and verify a sender address, e.g. `mike@inboxslide.ai`.
2. Add the SPF and DKIM DNS records Brevo gives you into your Cloudflare zone.
   These prove you are allowed to send as that domain; without them your mail
   goes to spam.
3. Create an API key (it starts with `xkeysib-`).

Then in DripDrop: **Settings → connect Brevo**, paste the key.

**To receive replies** you do not need a mailbox. In Cloudflare → **Email** →
**Email Routing**, forward `mike@inboxslide.ai` to your gmail. Free, and takes
about two minutes.

---

## Step 9 — Before your first real campaign

**Rewrite the sales claims.** Open the config on the server:

```
nano /opt/dripdrop/.env
```

Find `DRIPDROP_VALUE_PROPS`. The text there is a draft. The version that ships in
the code asserts an 80–90% fill rate and a 2–3 week average time-to-fill — those
are **Arena's placement history**, and a new firm cannot truthfully claim them.
Replace it with terms you can actually stand behind. Save with `Ctrl+O`, Enter,
then `Ctrl+X`. Then:

```
systemctl restart dripdrop
```

**Seed the do-not-contact list.** This instance starts with no memory of anyone.
It does not know who unsubscribed from Arena, and it does not know which
addresses already bounced there. Running both instances without doing this means
you can email the same prospect from two companies in one week, or email someone
who explicitly opted out. Export Arena's DNC entries and load them here first.
The list accepts whole domains as `@company.com`, so you can also exclude
accounts Arena is actively working, in one line each.

---

## Separately: handing Arena's hosting over

Not required to launch. But you have said you would transfer anything to them,
so here is the order that avoids breaking their production on the way out.

Arena currently depends on three things of yours: the **DigitalOcean account and
card** paying for the droplet, the **Cloudflare zone** for `dripdripdrop.ai`
that their production resolves through, and the **Anthropic org** the app's API
key lives in.

**Do the new accounts first.** Every item above is only awkward to hand over
because your own work is mixed into it. Once inboxslide is on its own host and
its own Anthropic org, all three become clean handovers.

**Their card goes on before yours comes off.** If your card is removed while it
is the only one on file, Arena's production stops at the next billing cycle.
This applies to DigitalOcean and Anthropic both.

**Move the zone, do not move the account.** In Cloudflare, transfer the
`dripdripdrop.ai` zone to Arena's account. Do not hand over your whole Cloudflare
account — `inboxslide.ai` is in it.

**Agree continued access in writing, before the transfer.** You have said you
will keep using Arena's instance. The moment the accounts are theirs, that is
their decision to make, not a setting you control. Much easier to agree now.

## The one rule for keeping the two instances apart

**Never copy anything from `deploy/env.inboxslide.example` onto Arena's server.**

Both instances run the same code. What makes them behave differently is that
this one sets a group of configuration variables and Arena's leaves them unset.
Each variable falls back to exactly Arena's old built-in behaviour when it is
absent — which is what keeps Arena correct.

Setting one of them on Arena's box would change Arena silently. The worst is
`DRIPDROP_ATS_EMAILS`: setting it there removes Pipeline access for Sarah Henze
and Elizabeth Simonov, with no error message and nothing in a log.

---

## If something breaks

```
systemctl status dripdrop          # is the app running?
journalctl -u dripdrop -n 50       # app errors
journalctl -u caddy -n 40          # certificate / web server errors
systemctl restart dripdrop         # restart the app
```

Configuration lives in `/opt/dripdrop/.env`. Your data lives in
`/opt/dripdrop/data`. Nothing in either touches Arena.
