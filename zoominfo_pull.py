"""The ZoomInfo and job-board rules every DripDrop prompt hands Claude.

One place, so the AI Prompts page (ai_prompts.py, staffing_prompts.py) and
the Sales Campaign hand-off brief (sales_campaign.py) cannot drift apart.
Plain text only: no app imports, so any of the three can import it at the
top. Inboxslide's tm_prompts.py deliberately does not use it - its runs must
never fall back onto an Arena ZoomInfo seat.

Strings here are dropped into str.format_map templates by ai_prompts, so
they must not contain braces.
"""

# The order the boards are searched in. Also the default answer to the
# "Where to look for the jobs" question, which the user can edit.
BOARDS_DEFAULT = ("Google Jobs first, then LinkedIn Jobs, then Indeed, then "
                  "ZipRecruiter")

# Follows the boards sentence in every sourcing step.
BOARDS_RULE = (
    "Go in that order, one board at a time, and finish each board before "
    "you start the next. Google Jobs and LinkedIn Jobs are searched in "
    "Chrome. Indeed and ZipRecruiter have connectors, but they still come "
    "after Google Jobs and LinkedIn: do not start with the connectors or "
    "run them alongside the browser searches just because they are faster. "
    "If Google shows a bot check, do not try to solve it: move to the next "
    "board and tell me Google was skipped. Search every board either way, "
    "not just until you have enough, then pool what you found and pick the "
    "best targets from the whole pool. A company posting the same kind of "
    "role on more than one board is a stronger signal than one that posted "
    "once.")

# Keep both numbers on file for every contact. On the connector, phone (the
# direct work line) comes back as a DisallowedOutputFields warning on the
# current licence; asking anyway costs nothing and starts the work numbers
# flowing the day the licence adds it.
ZI_PHONES_RULE = (
    "Keep both phone numbers on file for every contact: ask enrich_contacts "
    "for mobilePhone and phone along with the email. A DisallowedOutputFields "
    "warning on phone is expected and is not an error - the rest still "
    "comes back. On my seat, copy the mobile and the direct or company phone "
    "off the profile. Put the mobile in phone_mobile and the work number in "
    "phone_office on every contact you hand DripDrop, so both stay on the "
    "contact's record.")

# Follows the "take these out" sentence: the exclusions come from DripDrop's
# own records, never from the AI's memory of who our clients are.
SKIP_CHECK_RULE = (
    "Do not guess who our clients are or what the team has worked: call the "
    "DripDrop skip_check tool once with every company on your list, names "
    "or email domains. It answers from DripDrop's own records - our Current "
    "Clients, and every company anyone on the team put in a campaign in the "
    "last 30 days, cancelled ones included - with the rep and the date each "
    "one opens again. Drop every company it marks skip before any research "
    "or ZoomInfo pull. DripDrop refuses to launch at those companies "
    "anyway.")

# Before ZoomInfo: the team's own bank of people already reached.
BANK_FIRST_RULE = (
    "Before ZoomInfo, check the Shared Arena Contacts bank: for each company "
    "call the DripDrop team_contacts tool with the company name or email "
    "domain. If it comes back with verdict skip - a Current Client, or a "
    "company a teammate put in a campaign in the last 30 days - drop that "
    "company and pull nobody there, from the bank or ZoomInfo. Otherwise it "
    "returns the people our team has already reached there, from "
    "every campaign and uploaded list, with titles, emails and phones; "
    "anyone who said not interested or is on a Do Not Contact list is "
    "already left out, and people who replied are flagged. Use those "
    "contacts first, replied ones at the top. Only pull from ZoomInfo for "
    "companies that come back empty or that need more people to reach the "
    "count. Never re-add a person the bank left out. ")

# Appended to every step that pulls contacts out of ZoomInfo.
ZI_PULL_RULE = (
    BANK_FIRST_RULE +
    "Pull the rest with the ZoomInfo connector: search_companies to pin "
    "the right company, search_contacts to find the people (free, so search "
    "wide), then enrich_contacts in batches of 10 to reveal them - that "
    "spends our shared Bulk Credits. If enrich_contacts comes back with a "
    "quota or \"Limit exceeded\" error, that is not a failure and not a "
    "reason to stop: switch to my own ZoomInfo seat. Open "
    "recruiter-app.zoominfo.com in Chrome, where I am already signed in, "
    "find the same people there and reveal each one through their profile "
    "preview - that spends my own monthly view credits, a separate pool. "
    "Never type a password; if that tab is signed out, say so. If both "
    "pools are out, keep the company, mark it waiting on ZoomInfo with the "
    "exact error, and carry on with the rest. For every contact, note "
    "which pool paid for it, bulk or seat. " + ZI_PHONES_RULE)
