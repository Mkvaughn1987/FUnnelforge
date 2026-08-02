# Arena 5×5 — Sequence Setup Spec

**Status:** copy locked, pending build
**Base:** clones the Arena 4×4 (`fourbyfour`) template in `flowdrip_app.py`
**Key:** `fivebyfive` · **Display:** "Arena 5×5" · **Subtitle:** "7 steps - 2 weeks"

## What the 5×5 is
The 4×4 (5 candidate-marketing touches: 4 emails + call + LinkedIn) with **one extra
email inserted on day 5**, and a warmer/softer, less-sales voice. "5×5" = 5 emails.
The 4×4 is left untouched for now; it can inherit this voice later.

## Legend
- `{token}` — merge field, auto-filled per recipient at send (`{FirstName}`, `{CompanyName}`).
- `⟦brackets⟧` — the AI writes this in at generation time (the market/sector, candidate profiles). NOT a token.
- `[your signature]` — auto-appended from `signature.txt`; the generator is told to write no sign-off.

## Conventions (apply across the sequence)
- **Voice:** warm, soft, professional/solo ("I", not "we"). No hard sell.
- **Market, not role:** wherever the 4×4 says the role, the 5×5 has the AI write the
  overall **market** (construction, manufacturing, etc.), inferred from the company.
  (Avoids the `{Industry}` token, which is blank on company-only 4×4 launches.)
- **Candidate aliases:** anonymized candidates render as a first-name alias whose initial
  matches the slot + a last initial — Candidate A → **Aaron M.**, B → **Ben T.**, C → **Carlos R.**
  Real first name used if the Candidate Highlights provide one. Consistent across ①②④.
- **No em dashes** (sender also auto-strips them at the queue boundary).
- **Newsletter:** ⑤ promises a monthly newsletter, so the launch must pass `enroll_newsletter`
  (already supported by the 4×4 path) so the contact is actually enrolled.
  - **NorCal 5×5 runs → `"NorCal - Market Pulse & Hot Candidates"`** (created 2026-07-20, 0 enrolled at creation).
    Set `template: "fivebyfive"` + `enroll_newsletter: "NorCal - Market Pulse & Hot Candidates"` in the
    launch payload. Other regions keep their own newsletter (e.g. `"Recruitment Rundown - Manufacturing"`).
  - **Name must match EXACTLY** — close variants silently enroll 0 (note the live list already has both
    "Recruitment Rundown - Manufacturing" and "Recruitment Rundown - Package Manufacturing"). After launch,
    check the 200 response's `newsletter_enrollment.matched`; if `false`, read its `available` list and use
    the exact string. The API is called from a connected dripdripdrop.ai browser tab, not the sandbox (egress-blocked).

## Schedule (delay_days are relative to the previous step)
| Step | Day | Type | delay_days |
|------|-----|------|-----------|
| ① Email — Intro | 0 | email_auto | 0 |
| ② Email — One-candidate spotlight | 3 | email_auto | 3 |
| Call (same day as ②) | 3 | call | 0 |
| LinkedIn connect (same day as ②) | 3 | linkedin | 0 |
| ③ Email — Following-up bump (NEW) | 5 | email_auto | 2 |
| ④ Email — Worth a look + Interview Guide | 8 | email_auto | 3 |
| ⑤ Email — Closing the loop + newsletter | 12 | email_auto | 4 |

## Attachments
- ③ (day 5): **none** (pure bump).
- ④ (day 8): **Interview Guide PDF** — built-in `interview_guide` PDF type.
  Attachment ref: `[AI-GENERATED] {CompanyName}_Interview_Guide.pdf`.

---

## Final email copy

### ① — Day 0
**Subject:** Quick note for {CompanyName}

Hi {FirstName},

Wanted to introduce myself. I place ⟦the specific role this campaign is targeting, if provided — otherwise the roles common to ⟦market⟧⟧, and I've been active in the space for a while. Came across {CompanyName} and wanted to reach out.

No candidates, no pitch here, just an intro.

Are you involved in the hiring process?

*[your signature]*

*(Revised 2026-08-02: email ① no longer opens with a candidate slate — that moved to ②. This is a pure warm intro that ends on the qualifying question above, shared verbatim with the 5×3's Step 1.)*

### ② — Day 3
**Subject:** One person worth having on your radar

Hi {FirstName},

Quick follow-up from earlier this week. After years working in ⟦market⟧, the one thing I can tell you is that the best people are rarely the ones actively looking. They're settled, doing good work, and only open up for the right fit.

With that in mind, one person stands out for {CompanyName}:

⟦AI: spotlight ONE candidate (Aaron M.) — 2-3 warm sentences: background, a standout strength, why they'd fit here⟧

If it's helpful I'm glad to share what's happening in the ⟦market⟧ hiring market too, but mostly I just wanted to put them in front of you.

No pressure at all.

*[your signature]*

### Call + LinkedIn — Day 3 (same day as ②, carried from 4×4)
- **Call:** reference the emails and the spotlighted candidate; ask if they had a chance to look; quick-qualify hiring timeline. Conversational, not pushy.
- **LinkedIn connect** (under 300 chars): "Sent you an email, wanted to connect here as well. Always sharing industry insights and market data in your space."

### ③ — Day 5 (ships verbatim)
**Subject:** Following up

Hi {FirstName} - just a quick follow-up in case this got missed. Any thoughts on my previous email below? And if hiring isn't your area, no worries at all, could you point me to whoever owns it?

*[your signature]*

### ④ — Day 8
**Subject:** Still think this one's worth a look

Hi {FirstName},

Just circling back, gently. I know inboxes are full and hiring is one of a hundred things on your plate, so no worries if the timing isn't right.

I mostly wanted to say that Aaron M. is genuinely worth a conversation, and I'm happy to make it as easy as a 10-minute call whenever you have a window.

I've also attached a short interview guide for the role, the questions worth asking and what to listen for, so it's handy whether or not we end up talking.

Either way, I appreciate you reading.

*📎 [AI-GENERATED] {CompanyName}_Interview_Guide.pdf*

*[your signature]*

### ⑤ — Day 12
**Subject:** Closing the loop for now

Hi {FirstName},

I don't want to crowd your inbox, so I'll close the loop here. It's been a pleasure reaching out, even if the timing isn't right just yet.

I'll add you to my monthly newsletter so the occasional useful bit of ⟦market⟧ hiring news still reaches you, nothing salesy, just worth-a-glance updates. And the door's always open whenever {CompanyName} needs a hand finding great people.

*[your signature]*

---

## Build notes (for the implementation plan)
- Add a new `("fivebyfive", "Arena 5×5", "7 steps - 2 weeks", <color>, <desc>, <tagline>, <step-prompt>)`
  entry to the template registry near the 4×4 tuple (~`flowdrip_app.py:4098`), following the
  same 7-step, delay_days format as the 4×4.
- Register `fivebyfive` wherever `fourbyfour` is branched on (chooser origin, camp_type,
  the `_camp_is_4x4` / handoff / font-wrap helpers around L4609–L8184, picker at L18504/L35584).
  Decide per-branch whether the 5×5 should behave identically to the 4×4.
- Wire the day-8 Interview Guide attachment via the existing `interview_guide` PDF generator.
- CAUTION (from repo memory): `flowdrip_app.py` is the ~60k-line monolith with known
  duplicate-helper shadowing and prod-deploy drift. Ship as a single-file change, baseline
  the 8 pre-existing test failures, and confirm the deploy path before touching prod.
