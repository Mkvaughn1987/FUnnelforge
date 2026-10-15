# Buying News & Signals (inboxslide) - design

Date: 2026-10-15. Instance: inboxslide only (ThriveModal playbook). DripDrop untouched.

## What it is

A fourth row under CONTENT, **Buying Signals**, opening the page **Buying News &
Signals**. A user opts in, picks any number of the fifteen ThriveModal verticals
and a location (USA by default), and every **Tuesday and Thursday at 7am local**
gets one email, sent from their own connected mailbox to their login address:

- per picked industry, companies showing one of seven buying signals, dated
  inside the last 14 days, each with the signal, the date, a one-line why-now,
  a suggested opener, the source link and a *Build a campaign* link
- a short industry-news section per industry

Subject: `Buying news & signals: Thu 16 Oct`. No industry in the subject, since
users pick several.

## The seven signals (fixed in code, `tm_signals.SIGNALS`)

Move on these now: private equity acquisition or new investor; new CFO/COO/CEO;
layoffs, WARN filing, closure or restructuring; big contract, expansion, new
location or funding. Worth a look: hiring surge or long-open back-office
postings; fully remote postings; offshore tells (Philippines, BPO, VA, US hours).

## How it runs

- `tm_signals.py` is a companion module (lazy import, like `ai_prompts`).
- Settings + the last 8 issues live in `<user root>/tm_signals.json`.
- The server scheduler loop calls `_tm_signals_tick()` every tick; the module
  does a real pass every 5 minutes, only for users whose file exists, whose
  workspace is ThriveModal, who are opted in with at least one industry, on a
  Tue/Thu at or after 7am in their timezone, and who have not run today. The run
  date is stamped before the research thread starts so a slow run never
  doubles.
- One research call per picked industry (Sonnet 5.5 with web search, allowlist
  widened by a fixed list of business-news and WARN domains). The parser keeps
  only a known signal id, a name, a parseable date in the window and an http
  source; companies sent in the last 30 days are dropped; urgent signals rank
  first.
- Nothing found means no email (the issue is stored with a note). A failed
  industry drops that section, not the issue.
- The page has *Send me one now* (same run, in a thread, page polls) and
  shows the stored issues so a signal can be acted on without the inbox.
- `?open=tm_signals|tm_prompts` deep links (whitelisted, ThriveModal only).

## Out of scope

Prefilling the company into AI Prompt from the link; a team-wide feed; any
change to DripDrop/Arena.
