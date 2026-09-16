# Launching the inboxslide.ai instance

A start-to-finish runbook. Assumes no prior knowledge and no context from the
conversation that produced it. Roughly 45 minutes, most of it waiting.

**What you are building:** a second, completely independent copy of DripDrop on
its own server, at `app.inboxslide.ai`. Arena's instance keeps running,
untouched, on its own server. They share a code repository and nothing else.

---

## Before you start: two accounts that must be yours

This is the whole point of the exercise, so get it right.

**DigitalOcean.** If you create the new server inside Arena's DigitalOcean
account, it stops being yours the day you lose access to that account. Create it
under an account billed to your own card. If you are unsure which account you
are in, check the billing page — whose card is on file is the real answer.

**Anthropic.** Same logic, sharper edge. An API key created inside an
organization is tied to the person who made it, and Anthropic **deactivates it
when that person leaves the organization**. A key minted in Arena's org will
simply stop working one day with no warning. The key you use here must come from
your own organization on your own card.

Everything else — the domain, the Cloudflare zone — you already own.

---

## Step 1 — Create the server

In DigitalOcean: **Create → Droplet**.

| Setting | Choose |
|---|---|
| Region | Whichever is closest to you |
| Image | **Ubuntu 24.04 LTS** |
| Size | Basic → Regular → **2 GB RAM / 1 vCPU** ($12–14/mo) |
| Authentication | **SSH key** if you have one, otherwise Password |
| Hostname | `inboxslide` |

On size: 1 GB is too small — the app parses large JSON files in memory and will
be killed by the kernel under load. 2 GB is the floor.

When it finishes, copy the **IP address** from the droplet page. You need it in
the next step. It looks like `164.92.x.x`.

---

## Step 2 — Point the domain at it (must happen BEFORE Step 4)

In Cloudflare, select the **inboxslide.ai** zone → **DNS** → **Add record**.

| Field | Value |
|---|---|
| Type | `A` |
| Name | `app` |
| IPv4 address | your droplet's IP from Step 1 |
| Proxy status | **DNS only** — click the orange cloud so it turns **grey** |

**The grey cloud matters and it is temporary.** When your server starts, it asks
Let's Encrypt for a free SSL certificate, and Let's Encrypt proves you own the
name by connecting directly to your server. If Cloudflare is proxying (orange),
it intercepts that connection and the certificate never gets issued. You will
turn the orange cloud back on in Step 6, once the certificate exists.

Wait about a minute for this to take effect.

---

## Step 3 — Prepare the server

Open a terminal. Connect to the droplet, substituting your IP:

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
