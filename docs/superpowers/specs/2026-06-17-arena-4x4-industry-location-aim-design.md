# Arena 4×4: Aim at Industry + Location, not a Company/Posting

Date: 2026-06-17
Status: Approved (design)

## Goal
Reframe the candidate-row Arena 4×4 so it reads as outreach to **employers in
an industry + region** (marketing available local talent), not as a reply to
one company's specific job posting. The whole slate goes out together; since
the slate is one industry + one location, bundling is correct.

## Background
The candidate-row 4×4 (`_4x4_generate_emails`, ~L47230) is built around an
"Advertised role (the anchor)": the setup card (~L37191) says *"Email 1
pinpoints a real role your targets are advertising… match the live
LinkedIn/Indeed posting"* and takes a job-link input. Email 1 opens with
*"I saw you're actively seeking a {role}…"* — company/posting-specific framing.

This is the scope the user pointed at and the path that produced the
Manufacturing preview. The **AICB-builder** 4×4 (~L34114) is a separate,
generic generator shared with MPC and other campaign types; reframing it
broadly would risk those types, so it is OUT of scope here.

## Scope (candidate-row 4×4 only)

### 1. New state var
- Add `self.cpc_industry: str = ""` near the other `cpc_*` vars (~L10351).
- Seed it when a 4×4 is started: anchor candidate's `industry` if present,
  else `s.aicb_industry`, else "" (user fills it in).

### 2. Setup card (~L37191–L37214) — "Target market: Industry + Location"
- Retitle the card from "Advertised role (the anchor)" to a market-aimed
  label ("Target market — industry & location").
- Replace the role input with an **Industry** input bound to `cpc_industry`
  (placeholder e.g. "Industry — e.g. Manufacturing").
- Keep the **Location** input (`cpc_ad_location`).
- **Drop** the "paste the LinkedIn/Indeed job link" input (it embodied the
  company-posting model). `cpc_ad_link` stays defined but is no longer set
  here or used by the 4×4 prompt.

### 3. Reframed copy — extract a pure prompt builder
- New pure helper `_4x4_email_prompt(sig_name, company, industry, location)`
  returns the 4-email prompt string (keeping the literal `[[HIGHLIGHTS]]` and
  `[[MARKET]]` tokens the caller fills in). Pure ⇒ unit-testable.
- The opener reframes to market outreach, e.g. *"I work with {industry}
  companies across {location} and wanted to put a few standout candidates
  currently available in your market on your radar."*
- Remove all posting/company assumptions: no "you're actively seeking
  {role}", no "the live job posting", no job link.
- Subjects key off industry: Email 1 "{industry} Candidates Available",
  Email 4 "Market Trends and Hiring Solutions for {industry}".
- `_4x4_generate_emails` calls the helper, passing
  `industry = (s.cpc_industry or fallback)` and `location = s.cpc_ad_location`.

### 4. Market stats by industry
- `market = _4x4_market_snapshot(client, sector=industry or "skilled trades")`
  (builds on the role-matched fix already shipped; now keyed to industry).

### 5. Camp name fallback (~L37777)
- `_adr = (s.cpc_industry or s.cpc_ad_role or role or "Placement")` so the
  saved campaign name reflects the industry when set.

## Out of scope
- The AICB-builder 4×4 path and all other campaign types.
- Slate building, scheduling, resume attach, J Way handoff (unchanged).
- Renaming `cpc_ad_role` / `cpc_ad_link` (left in place; just unused by the
  4×4 prompt).

## Testing
- `_4x4_email_prompt("Mike", "Arena Direct Hire", "Manufacturing",
  "Salt Lake City, UT")`:
  - contains "Manufacturing" and "Salt Lake City, UT";
  - contains the `[[HIGHLIGHTS]]` and `[[MARKET]]` tokens;
  - does NOT contain banned company/posting phrasing: "job posting",
    "actively seeking", "advertising", "job link".
- Existing 4×4/arena tests still pass.
- Manual: start a 4×4, confirm the setup card shows Industry + Location (no
  job link), and the generated Email 1 reads as industry/region outreach.
