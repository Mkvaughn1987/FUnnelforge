# Find Candidates for an Opening (AI Prompts card + findcandidates template)

Date: 2026-10-06. Approved verbally by Mike ("recommended sounds good").

## Goal

A DripDrop AI Prompts card that takes an opening (role, client, pay, selling
points), a place to look (named target companies expanded with ZoomInfo
lookalikes, or an industry and size band), who to find (titles, level,
experience, tenure, geography), and produces a prompt that has the AI pull
the people out of ZoomInfo, add them to the Pipeline, and launch one
`findcandidates` campaign to them.

Two halves ship together because the second does not exist on prod:

1. The card, in `staffing_prompts.py` (DripDrop only).
2. The `findcandidates` server template, cherry-picked from
   `feat/mcp-campaigns-and-findcandidates` (d832746) onto the current prod
   lineage and upgraded, plus the read-only `GET /api/v1/campaigns` routes
   from the same commit (prod returns 405 on them today, and every
   newsletter clause on the page already calls `campaigns_list`).

## Why the template needs upgrading

The branch version writes 1 to 3 emails from one Haiku prompt with no
purpose per step, takes only a job description, merges only `{FirstName}`,
has no way to keep the client confidential, and its three-email cadence runs
in three days.

## Server: findcandidates spec

`POST /api/v1/campaigns` with `template: "findcandidates"`. All fields
optional unless noted.

| field | meaning |
|---|---|
| `contacts` / `contacts_csv` | the candidates (recipients) |
| `role` | the title of the opening |
| `client` | the hiring company |
| `confidential` | default true. True: the emails never name the client, they describe it instead. False: the client is named. |
| `location` | where the job is |
| `pay` | pay range, written as the recruiter would say it |
| `selling_points` | list of strings, or one string: why someone would move |
| `job_description` | full JD text, parsed with `_tc_parse_jd` as before |
| `cadence` | `one_email`, `two_emails_1day`, `three_emails_3days`, or the new `three_emails_1week` (days 0, 3, 7). Default `one_email` (unchanged, the in-app wizard relies on it). |
| `name` | campaign name. Fallback: "Find Candidates - {role}", then the parsed role title, then "Find Candidates". |

Validation: `company`/`niche` not required for this template; `cadence` must
be a known key; `selling_points` must be a list or a string.

Generation (`_generate_findcandidates_emails`) gets the new fields and a
purpose per step:

- 1 email: intro with the ask.
- 2 emails: intro; value plus soft close.
- 3 emails: intro; proof and value (pay, selling points, what the company
  offers); soft close with an easy out.

Rules carried into the prompt: `{FirstName}` only as a merge token, respectful,
no fake urgency, under 150 words, distinct subjects, no emoji, no
"I came across your profile", and the confidentiality rule.

The in-app Find Candidates wizard calls the same helper (JD and cadence only),
so its behaviour is unchanged.

Visibility: `findcandidates` joins `_API_ONLY_TYPES` so it is hidden from
the wizard tiles and the Sales Campaign picker (the wizard already has its own
Find Candidates card). `GET /api/v1/campaign_types` lists it.

Campaign record: `variables.TargetRole` = role, `Geography` = location,
`CompanyName` = client only when not confidential.

## The card

Starter `staff_find_candidates`, routine of the same key, title "Find
Candidates for an Opening", on the DripDrop board right after the MPC card.

Questions, by step:

- The details: role (asked), client (asked), keep the client confidential
  (on), job description, pay, three reasons someone would move, start from
  (companies I name / an industry and size), target companies, industry,
  company size (50 to 1000 people), titles to search (asked), level
  (non-managers and managers), years of experience (2 to 10), time in current
  job (2 to 8 years), include people who left those companies (off),
  geography mode (radius / state / nationwide), zip, radius (25), state.
- The emails: cadence ("Three, over a week" default), start date fields,
  campaign name.
- How big: companies (20), people per company (5), email cap (100), add
  everyone found to my Pipeline (on).
- Leave these out: companies we do business with (on), people already in a
  campaign for this opening (on), never these companies (the client is always
  left out).
- Create a schedule: the shared block.

No newsletter and no Candidates block: the recipients are the candidates.

## How the prompt runs

1. Companies. Named seeds: `search_companies` to pin each, then
   `find_similar_companies` with `sameIndustry` and `sameEmployeeRange`,
   drop the seeds, the client and the skip list, keep only companies with a
   presence in the geography (the lookalike call has no location filter).
   Industry mode: `search_companies` on industry, size band and geography.
2. People. Per company `search_contacts` with `companyIdList`,
   `jobTitleList` (one title per entry, letters and spaces only),
   `managementLevelList`, years of experience, `positionStartDateMin/Max`
   for tenure, `requiredFieldsList ["email"]`, accuracy 80 or more, the
   geography filter, sorted by accuracy. Alumni on: a second pass with
   `companyPastOrPresent "past"`. Then reveal in batches of ten under
   `ZI_PULL_RULE` (connector, then the user's own seat). Business emails
   only. Never anyone currently at the client.
3. Dedupe. `campaigns_list`, then `campaign_get` on every campaign with
   this campaign's name, and drop anyone already on one.
4. Pipeline. `import_candidate_records`, one record per person with
   `external_id "zi-<personId>"`, so a re-run never doubles anyone.
5. Review. Companies, people per company, total, the cap, then carry on.
6. Launch. One `create_campaign` with the spec above and every person as a
   contact with both phone numbers.

Tools: `campaigns_list`, `campaign_get`, `import_candidate_records`,
`create_campaign`. ZoomInfo is named in the steps as on the lookalike card.

## Out of scope (follow-ups)

- "More like this person" from a Pipeline candidate via
  `find_similar_contacts`.
- A call task on day 2 using the revealed mobile numbers.
- Routing a candidate's reply back onto the Pipeline record.

## Testing

- `tests/test_findcandidates_api.py` from the branch, extended for the new
  fields, the one-week cadence and the name fallback.
- A prompt test in the `test_ai_prompts_candidates.py` style covering: the
  card is on the board after MPC, both seed modes, confidential on and off,
  alumni on, the three geography modes, the cadence key, Pipeline import on
  and off, and that no newsletter or candidates block appears.
- Full suite green before deploy.

## Deploy

`flowdrip_app.py`, `staffing_prompts.py`, `ai_prompts.py` (only if
touched), `mcp_server/dripdrop_mcp.py` to the DripDrop box, hash-guarded
against the current prod blobs, via the inboxslide jump host. Restart blue
and green; verify `campaign_types` over MCP shows `findcandidates` and
`campaigns_list` no longer 405s.
