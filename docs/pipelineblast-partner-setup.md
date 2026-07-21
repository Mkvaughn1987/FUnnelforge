# PipelineBlast — Partner Setup & How to Run It

*(Send this to each partner once the connector is live. One-time setup is ~10 minutes, then every
weekly run is a single sentence in Claude.)*

---

## What this is

PipelineBlast finds companies in a target market that are actively hiring a role you name, pulls
their decision-makers, launches a personalized 5-email DripDrop campaign per company **from your
own DripDrop account** (the system matches our candidate bench and attaches redacted résumés
automatically), and logs everything in the CRM. You run it by typing one sentence in the Claude
app.

## What you need before starting

- A **Claude Pro or Max** subscription (claude.ai)
- Your **DripDrop login** (Mike will send you your account invite — use that to set your password)
- Your **ZoomInfo login**

## One-time setup (~10 minutes)

### 1. Connect ZoomInfo and Indeed

1. In the Claude app, open **Settings → Connectors**.
2. Find **ZoomInfo** → click **Connect** → sign in with your ZoomInfo login.
3. Find **Indeed** → click **Connect**.

### 2. Add the DripDrop connector

1. Still in **Settings → Connectors**, click **Add custom connector**.
2. Name: `DripDrop` — URL: `https://dripdripdrop.ai/mcp` — click **Add**.
3. Click **Connect**. A DripDrop login page opens — sign in with **your** DripDrop account and
   approve. (This is what makes campaigns send from *your* account.)

### 3. Install the PipelineBlast skill

1. Mike will send you a file called `pipelineblast-app.zip`. Don't unzip it.
2. In the Claude app, open **Settings → Capabilities**, find the **Skills** section, and click
   **Upload skill**.
3. Choose the zip. You should see **pipelineblast** appear in your skills list.

Setup done. You never repeat these steps — except step 2's **Connect** button, if Claude ever says
your DripDrop connection expired.

## Running it (every time)

Start a new chat and type one sentence with the **role**, the **place**, and the **industry**:

> Run PipelineBlast for **project managers** in **Phoenix**, **commercial construction**.

Then let it work — a full run takes a while (it's researching companies, pulling contacts, and
launching a campaign per company). Along the way it may ask you to confirm things (like which
companies to take forward this week) — just answer in the chat. If Claude asks permission to use
ZoomInfo, Indeed, or DripDrop tools, allow them.

### What a finished run gives you

- The week's **selected companies** (already checked against the shared team list, so you'll never
  work an account anyone on the team already touched)
- A **launched campaign per company** — campaign ID and the send schedule (all sends land on
  business days; first email goes out the next business day)
- Companies + hiring managers **logged in the CRM** automatically
- Notes on any company that was **skipped** — most commonly "no bench fit," which means our
  system decided none of our current candidates were strong enough for that company. That's
  normal; it just moves on.

## If something goes wrong

| What you see | What to do |
|---|---|
| "DripDrop connection expired / not authorized" | Settings → Connectors → DripDrop → **Connect**, sign in again. Then tell Claude to continue. |
| ZoomInfo asks you to sign in again | Reconnect it the same way, then continue the run. |
| "No matching newsletter for this market" | Tell Mike the role/geo/industry you ran — he needs to create the newsletter for that market. |
| "TT load failed" on some companies | Nothing for you to do — Mike gets flagged and fixes the CRM side. Your campaigns still launched. |
| A company you know we've worked shows up as new | Stop and tell Mike before launching to it — the shared list may be missing it. |

Anything else weird: screenshot it and send it to Mike.

## Ground rules

- **One run per market per week.** The dedupe list protects accounts, not send volume.
- **Don't add candidates manually** if Claude ever offers — candidate matching is automatic and
  server-side. The campaign is designed around it.
- Campaigns send **as you**, from your DripDrop account — replies come to you. Work them.
