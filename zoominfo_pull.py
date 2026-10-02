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

# Appended to every step that pulls contacts out of ZoomInfo.
ZI_PULL_RULE = (
    "Pull the contacts with the ZoomInfo connector: search_companies to pin "
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
    "which pool paid for it, bulk or seat.")
