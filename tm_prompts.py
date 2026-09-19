"""ThriveModal's catalogue for the AI Prompt page on the inboxslide instance.

ai_prompts.py is the engine: it asks the questions, keeps the saved setups
and writes the prompt. Everything in this file is what changes when the
product is inboxslide selling ThriveModal instead of DripDrop selling Arena:
the verticals with their recommended targeting, the routines, the sequences
(the six ThriveModal campaign types), the starters and the standing rules
the prompt ends with.

The two research documents this was folded from live in
docs/thrivemodal-research/. Every claim below is one thrivemodal.com makes
itself; the research is evidence for who to target, not for what to promise.
"""
import ai_prompts as _e
from ai_prompts import (Catalogue, F,
                        POSTING_AGE, SKIP_FIELDS, WHEN_OPTIONS,
                        finalize_routines)

# ── Verticals ────────────────────────────────────────────────────────────
#
# One row per market, in the order Mike wants them worked. `exploratory`
# rows are markets the research thought were plausible but unproven for
# ThriveModal; the prompt tells the assistant to treat them as a small test.
# A blank targeting answer on the screen is filled from the picked row at
# build time (see _derive_tm), which is how "recommend, but let them decide"
# works without a second set of fields.

VERTICALS = [
    {
        "key": "logistics",
        "label": "Logistics / 3PL",
        "band": "20 to 500 people",
        "buyers": "the Owner, President, COO or VP of Operations first, then "
                  "the Director of Operations and the Head of Carrier Sales, "
                  "with the CFO second",
        "roles": "track and trace, carrier sales support, load building, "
                 "dispatch support, freight billing, claims and back-office "
                 "data entry",
        "triggers": "night-shift or after-hours postings, a track-and-trace "
                    "or carrier-rep opening that has sat or been reposted, "
                    "several of the same entry-level posting at once, a new "
                    "lane or office, and margin language in what they "
                    "publish",
        "workload": "overnight track and trace and carrier sales support",
        "question": "How are you covering loads after six and on weekends "
                    "today, and who is doing the check calls?",
        "tells": "McLeod, Aljex, Turvo, MercuryGate or Tai in a posting",
        "season": "peak runs August to October, so the pitch lands best in "
                  "June and July",
        "exploratory": False,
    },
    {
        "key": "freight_forwarding",
        "label": "Freight forwarding / customs",
        "band": "20 to 300 people",
        "buyers": "the Owner, President or COO first, then the Director of "
                  "Operations and the Import or Export Manager",
        "roles": "shipment coordination, documentation, customs data entry, "
                 "milestone updates and freight billing",
        "triggers": "documentation or coordinator postings that repeat, "
                    "overnight or weekend coverage postings, a new trade "
                    "lane, and reviews that mention missed updates",
        "workload": "documentation and milestone updates on live shipments",
        "question": "Who keeps the shipment updates moving when the US "
                    "office is closed?",
        "tells": "CargoWise or Magaya in a posting",
        "season": "steady through the year with a lift ahead of peak "
                  "import season in late summer",
        "exploratory": False,
    },
    {
        "key": "accounting",
        "label": "Accounting / CAS firms",
        "band": "10 to 200 people",
        "buyers": "the Managing Partner or Owner first, then the Firm "
                  "Administrator, the COO and the Director of Client "
                  "Accounting Services",
        "roles": "bookkeeping, bank reconciliations, accounts payable and "
                 "receivable, payroll processing, tax return preparation "
                 "and workpaper support",
        "triggers": "a bookkeeper or staff accountant posting open past a "
                    "month, several junior postings at once, a merger or "
                    "acquisition of another firm, and partners posting about "
                    "being slammed or short-staffed",
        "workload": "bookkeeping and reconciliations on the client "
                    "accounting side",
        "question": "How did the last busy season go for capacity, and what "
                    "did it cost you in partner hours?",
        "tells": "Karbon, Canopy, TaxDome or QuickBooks Online in a posting",
        "season": "busy season is January to April and the buying window is "
                  "November to January, when they plan for it",
        "exploratory": False,
    },
    {
        "key": "property_management",
        "label": "Property management",
        "band": "500 to 10,000 units under management, roughly 10 to 200 "
                "people",
        "buyers": "the Owner or Principal first, then the Director of "
                  "Operations, the Regional Manager and the Controller",
        "roles": "maintenance coordination, leasing assistance, tenant "
                 "communication, accounts payable, rent collection follow-up "
                 "and after-hours phones",
        "triggers": "maintenance coordinator or leasing assistant postings "
                    "that repeat, a new portfolio or market, reviews about "
                    "unanswered calls, and after-hours coverage postings",
        "workload": "maintenance coordination and after-hours tenant "
                    "communication",
        "question": "How many maintenance requests come in after hours, and "
                    "who is answering them?",
        "tells": "AppFolio, Buildium, Yardi, RentManager or Propertyware in "
                 "a posting",
        "season": "year-round, with leasing season in spring and summer "
                  "adding pressure",
        "exploratory": False,
    },
    {
        "key": "healthcare_admin",
        "label": "Healthcare administration / RCM",
        "band": "20 to 300 people",
        "buyers": "the Practice Administrator or CEO first, then the COO, the "
                  "Director of Revenue Cycle and the CFO",
        "roles": "medical billing, coding support, claims follow-up, prior "
                 "authorisation, patient intake, scheduling and insurance "
                 "verification",
        "triggers": "biller, coder, intake or prior-authorisation postings "
                    "that repeat, complaints about denials or aging AR, a "
                    "new location, and a practice acquisition",
        "workload": "claims follow-up and prior authorisations",
        "question": "Where is the AR aging today, and how many people are "
                    "working denials?",
        "tells": "Epic, Athenahealth, eClinicalWorks, Kareo or AdvancedMD in "
                 "a posting",
        "season": "year-round, with open enrollment in the autumn adding "
                  "verification work",
        "exploratory": False,
    },
    {
        "key": "home_care",
        "label": "Home care agencies",
        "band": "30 to 300 caregivers, roughly 10 to 100 office staff",
        "buyers": "the Owner or Administrator first, then the Director of "
                  "Operations and the Regional Manager",
        "roles": "scheduling, client intake, caregiver recruiting "
                 "coordination, on-call phones, billing and authorisation "
                 "tracking",
        "triggers": "scheduler, intake or on-call postings that repeat, "
                    "overnight or weekend coverage postings, reviews about "
                    "missed shifts or unanswered phones, and a new office",
        "workload": "scheduling and on-call coverage",
        "question": "Who fills a shift that falls through at nine at night, "
                    "and how long does it take?",
        "tells": "WellSky, AxisCare, AlayaCare or ClearCare in a posting",
        "season": "year-round",
        "exploratory": False,
    },
    {
        "key": "general",
        "label": "General back office",
        "band": "10 to 300 people",
        "buyers": "the Owner, President or COO first, then the Director of "
                  "Operations and the Controller",
        "roles": "customer support, data entry, bookkeeping, order "
                 "processing, scheduling and executive assistance",
        "triggers": "an entry-level office posting open or reposted past "
                    "two months, several of the same posting at once, "
                    "after-hours coverage postings, fast-growth lists, and "
                    "reviews that say understaffed or overworked",
        "workload": "whichever repeatable back-office task they keep "
                    "reposting",
        "question": "Which role have you hired for more than once this year, "
                    "and what happens when it is empty?",
        "tells": "none in particular; read the posting",
        "season": "year-round",
        "exploratory": False,
    },
    {
        "key": "construction_aec",
        "label": "Construction / AEC",
        "band": "50 to 500 people",
        "buyers": "the Owner or President first, then the Controller, the "
                  "Director of Preconstruction and the Operations Manager",
        "roles": "estimating support, takeoffs, submittal tracking, RFI "
                 "logging, accounts payable, job costing and drafting "
                 "support",
        "triggers": "estimator or project coordinator postings that repeat, "
                    "a backlog announcement, and a new office or region",
        "workload": "takeoffs and submittal tracking",
        "question": "How much of your estimators' week is takeoffs and "
                    "tracking rather than pricing?",
        "tells": "Procore, Bluebeam, Sage or Viewpoint in a posting",
        "season": "bid season is winter and early spring",
        "exploratory": True,
    },
    {
        "key": "agencies",
        "label": "Marketing agencies",
        "band": "10 to 100 people",
        "buyers": "the Founder or CEO first, then the COO and the Director of "
                  "Operations",
        "roles": "campaign reporting, ad operations, design production, "
                 "content scheduling, account coordination and bookkeeping",
        "triggers": "coordinator or production postings that repeat, a new "
                    "client win announced, and founders posting about "
                    "capacity",
        "workload": "reporting and production work behind account managers",
        "question": "How much of your account managers' week is reporting "
                    "and production rather than clients?",
        "tells": "HubSpot, Asana, Monday or ClickUp in a posting",
        "season": "year-round, with planning in the fourth quarter",
        "exploratory": True,
    },
    {
        "key": "travel",
        "label": "Travel agencies and tour operators",
        "band": "10 to 100 people",
        "buyers": "the Owner or Founder first, then the Director of "
                  "Operations",
        "roles": "booking support, itinerary changes, supplier follow-up, "
                 "after-hours traveller support and invoicing",
        "triggers": "after-hours support postings, seasonal hiring, and "
                    "reviews about slow responses",
        "workload": "after-hours traveller support and itinerary changes",
        "question": "Who answers a traveller whose flight cancels at "
                    "midnight?",
        "tells": "Sabre, Amadeus or Travefy in a posting",
        "season": "booking season is January to March",
        "exploratory": True,
    },
    {
        "key": "ecommerce",
        "label": "E-commerce brands",
        "band": "10 to 150 people",
        "buyers": "the Founder or CEO first, then the Head of Operations and "
                  "the Head of Customer Experience",
        "roles": "customer support, order and returns processing, catalog "
                 "data entry, marketplace listing management and bookkeeping",
        "triggers": "support or fulfilment postings that repeat, a new "
                    "marketplace launch, and holiday season hiring",
        "workload": "customer support and order processing",
        "question": "What does your support queue look like the week after a "
                    "big promotion?",
        "tells": "Shopify, Gorgias, Zendesk or ShipStation in a posting",
        "season": "the fourth quarter is peak, so the pitch lands in summer",
        "exploratory": True,
    },
    {
        "key": "home_services",
        "label": "HVAC and home services",
        "band": "20 to 200 people",
        "buyers": "the Owner or General Manager first, then the Operations "
                  "Manager and the Office Manager",
        "roles": "dispatch support, call handling, appointment booking, "
                 "invoicing and permit paperwork",
        "triggers": "dispatcher or CSR postings that repeat, after-hours "
                    "phone postings, private-equity roll-ups, and reviews "
                    "about unanswered calls",
        "workload": "call handling and appointment booking",
        "question": "How many calls go to voicemail during a summer heat "
                    "wave?",
        "tells": "ServiceTitan, Housecall Pro or FieldEdge in a posting",
        "season": "summer for cooling, winter for heating; pitch in the "
                  "shoulder months",
        "exploratory": True,
    },
    {
        "key": "distributors",
        "label": "Wholesale distributors",
        "band": "20 to 250 people",
        "buyers": "the Owner or President first, then the VP of Operations "
                  "and the Controller",
        "roles": "order entry, inside sales support, purchasing support, "
                 "accounts receivable and inventory data",
        "triggers": "order entry or inside sales postings that repeat, a "
                    "new warehouse, and an ERP migration",
        "workload": "order entry and accounts receivable follow-up",
        "question": "How many orders still come in by email or phone and get "
                    "keyed by hand?",
        "tells": "NetSuite, Epicor, SAP Business One or Acumatica in a "
                 "posting",
        "season": "year-round",
        "exploratory": True,
    },
    {
        "key": "professional_services",
        "label": "Professional services firms",
        "band": "10 to 150 people",
        "buyers": "the Managing Partner or Founder first, then the Firm "
                  "Administrator and the COO",
        "roles": "intake, scheduling, document preparation, billing, "
                 "research support and executive assistance",
        "triggers": "paralegal, intake or assistant postings that repeat, a "
                    "merger, and partners posting about workload",
        "workload": "intake and document preparation",
        "question": "How much partner time goes to work a trained assistant "
                    "could do?",
        "tells": "Clio, MyCase or PracticePanther in a posting",
        "season": "year-round",
        "exploratory": True,
    },
]
VERTICAL_BY_LABEL = {v["label"]: v for v in VERTICALS}
VERTICAL_LABELS = [v["label"] for v in VERTICALS]
DEFAULT_VERTICAL = VERTICALS[0]["label"]


def vertical_for(label):
    """The row for a picked label, tolerating a key or a loose match, and
    the first row when nothing matches."""
    s = (label or "").strip()
    if s in VERTICAL_BY_LABEL:
        return VERTICAL_BY_LABEL[s]
    low = s.lower()
    for v in VERTICALS:
        if low == v["key"] or (low and low in v["label"].lower()):
            return v
    return VERTICALS[0]


def _vertical_guide(v):
    tier = ("This vertical is exploratory: the research thought it "
            "plausible but ThriveModal has not proven it. Treat the run as a "
            "test of ten to fifteen companies, not a full push, and tell me "
            "whether the signals actually showed up. "
            if v["exploratory"] else "")
    return (
        "Vertical guide for %s, so you know what to look for. %s"
        "Who buys: %s. Roles ThriveModal routinely places here: %s. "
        "Signals worth acting on: %s. The first workload to lead with: %s. "
        "Software that tells you they are the right kind of company: %s. "
        "Timing: %s. Open the conversation with this question: \"%s\""
        % (v["label"], tier, v["buyers"], v["roles"], v["triggers"],
           v["workload"], v["tells"], v["season"], v["question"]))


def _derive_tm(r, vals, d):
    """Engine hook. A blank targeting answer means "use the recommendation
    for the vertical I picked", so the prompt always carries a concrete
    band, buyer list and role list, and the screen never has to show a
    second, greyed-out set of answers."""
    if "vertical" not in r["field_by_key"]:
        return
    v = vertical_for(d.get("vertical"))
    d["vertical"] = v["label"]
    d["vertical_label"] = v["label"]
    d["vertical_guide"] = _vertical_guide(v)
    for key, attr in (("company_size", "band"), ("who_to_reach", "buyers"),
                      ("roles", "roles"), ("triggers", "triggers"),
                      ("season_note", "season")):
        if key in r["field_by_key"] and not d.get(key):
            d[key] = v[attr]
            # Into the answers too, so THE DETAILS table shows the value the
            # steps were written with rather than a blank.
            vals[key] = v[attr]


# ── Sequences: the ThriveModal campaign types ─────────────────────────────
# Named for the situation, matching the app's chooser (2026-09-19). Grow a
# client and the old 5 Emails, 3 Calls + LinkedIn stay registered in the app
# but are not offered.

SEQUENCES = [
    "Standard Outreach",
    "Quick Intro",
    "Priority Account Push",
    "They're Hiring",
    "Top 25 Accounts",
    "Stay on Their Radar",
    "Revive Old Leads",
    "After the Call",
    "One of my saved styles",
    "Let Claude choose",
]
TEMPLATE_KEY = {
    "Standard Outreach": "tm_fivebyseven",
    "Quick Intro": "tm_threebythree",
    "Priority Account Push": "tm_conversation",
    "They're Hiring": "tm_hiring_signal",
    "Top 25 Accounts": "tm_twelveweek",
    "Stay on Their Radar": "tm_stay_in_touch",
    "Revive Old Leads": "tm_reengage",
    "After the Call": "tm_meeting_followup",
}
DEFAULT_SEQUENCE = "Standard Outreach"
DEFAULT_TEMPLATE = TEMPLATE_KEY[DEFAULT_SEQUENCE]


# ── Shared field groups ───────────────────────────────────────────────────

_REC = "Leave blank and the recommendation for the vertical you picked is used."


def _vertical_field(default=DEFAULT_VERTICAL):
    return F("vertical", "Which vertical", "details", "select",
             default=default, options=VERTICAL_LABELS,
             hint="The core five are proven. The rest are worth a small "
                  "test, and the prompt says so.")


def _targeting_fields():
    return [
        F("location", "Where", "details",
          default="anywhere in the United States",
          placeholder="e.g. Texas and the Southeast"),
        F("company_size", "How big a company", "details", hint=_REC,
          placeholder="Recommended band for the vertical"),
        F("roles", "Which roles they are hiring for", "details", hint=_REC,
          placeholder="Recommended roles for the vertical"),
        F("who_to_reach", "Who to reach", "details", hint=_REC,
          placeholder="Recommended buyers for the vertical"),
    ]


# The three skip checkboxes only: "Never these companies" / "Only these
# companies" text boxes removed from ThriveModal (Mike 2026-09-19).
_TM_SKIP_FIELDS = [f for f in SKIP_FIELDS
                   if f["key"] not in ("never_these", "only_these")]


def _newsletter_fields():
    return [
        # One dropdown of the user's newsletters (+ create button), which
        # writes newsletter_mode / newsletter itself (ai_prompts type
        # "newsletter"). Mike 2026-09-19.
        F("newsletter", "Add them to a newsletter", "details", "newsletter",
          hint="Pick one of yours, let Claude match one by line of work, "
               "or create a new one."),
    ]


def _email_fields(sequence=DEFAULT_SEQUENCE, name_default="the company name"):
    return [
        F("sequence", "Which campaign type", "emails", "select",
          default=sequence, options=SEQUENCES),
        F("saved_style", "Which saved style", "emails",
          hint="Only if you picked one of your saved styles above."),
        F("start_when", "When the first email goes out", "emails", "select",
          default="Next Monday", options=WHEN_OPTIONS),
        F("campaign_name", "What to call the campaigns", "emails",
          default=name_default),
    ]


def _size_fields(companies="5", contacts="4", cap=None):
    return [
        F("companies", "How many companies you want to end up with", "size",
          "number", default=companies),
        F("contacts_each", "How many people at each company", "size",
          "number", default=contacts,
          hint="Two is the fewest worth doing, five the most. One buyer and "
               "the people around them, not the whole org chart."),
        # "Most emails this run should send" removed (Mike 2026-09-19);
        # `cap` is kept only so existing callers don't change.
    ]


_CONTACTS_STEP = (
    "Pull the buying centre for each company out of your ZoomInfo connector: "
    "search_contacts for the titles, then enrich_contacts for work emails. "
    "Aim for {contacts_each} people per company, never more than five, "
    "working down {who_to_reach}. Two with a verified email is the floor "
    "that qualifies a company at all. If ZoomInfo returns a permissions "
    "error, quote it, keep the company list, and stop before the emails "
    "rather than guessing at addresses.")

_SHOW_STEP = (
    "Show me the companies, the signal on each one, the contacts and the "
    "total send volume. Then {gate}.")

_BUILD_STEP = (
    "{go_prefix} call tm_mailboxes and confirm a connected sending mailbox "
    "is there, then build one campaign per company with create_campaign "
    "using {template_clause}, start_date {start_date}, the company's "
    "contacts passed in the contacts argument, and industry, location and "
    "roles set from THE DETAILS above.{name_clause}{newsletter_clause} Read "
    "back the campaign id, the step count and the queued-contact count for "
    "every one, and tell me about any that came back short.")

_SCORE_STEP = (
    "Size about {pool} companies to land {companies} of about "
    "{company_size}. Score each one before you rank it: how strong and how "
    "fresh the signal is, whether the roles are ones ThriveModal actually "
    "places, whether it sits in the size band, and whether a buyer is "
    "reachable. Keep the A and B tier only. For every pick give the concrete "
    "signal that earned it, the actual fact from what you read, not \"good "
    "fit\", and say which workload the first hire would take.")

_CAMPAIGN_TOOLS = ["campaign_types", "my_campaign_styles", "tm_mailboxes",
                   "campaigns_list", "create_campaign"]


# ── Routines ─────────────────────────────────────────────────────────────

ROUTINES = [
    {
        "key": "tm_signal_hunt",
        "name": "Find companies showing a hiring signal",
        "blurb": "Search the job boards for companies in one vertical that "
                 "are hiring the roles ThriveModal places, pull the buyer, "
                 "and build a new-business campaign for each.",
        "example": "Find freight brokerages in Texas hiring overnight track "
                   "and trace reps and set up outreach to the owners",
        "tools": _CAMPAIGN_TOOLS,
        "fields": [
            _vertical_field(),
        ] + _targeting_fields() + [
            F("triggers", "Which signals count", "details", hint=_REC,
              placeholder="Recommended signals for the vertical"),
        ] + _newsletter_fields() + _email_fields("They're Hiring") + _size_fields() + [
            F("posting_age", "How recent the job postings have to be", "size",
              "select", default="Posted in the last 30 days",
              options=POSTING_AGE),
            F("boards", "Where to look for the jobs", "size",
              default="Google Jobs first, then ZipRecruiter, then LinkedIn, "
                      "then Indeed"),
        ] + _TM_SKIP_FIELDS,
        "steps": [
            "{vertical_guide}",
            "Search the job boards for {vertical_label} companies in "
            "{location} hiring {roles}, {posting_age_lc}. {boards}. Read "
            "each posting for the signals that count here: {triggers}. If "
            "Google shows a bot check, do not try to solve it: drop to "
            "ZipRecruiter and tell me Google was skipped. Run ZipRecruiter "
            "either way.",
            "{skip_clause}",
            _SCORE_STEP,
            _CONTACTS_STEP,
            _SHOW_STEP,
            _BUILD_STEP,
        ],
    },
    {
        "key": "tm_lookalikes",
        "name": "Find companies like a customer",
        "blurb": "Start from a company ThriveModal already serves, find the "
                 "ones that look like it through ZoomInfo, and open a "
                 "conversation with the owners.",
        "example": "Find forty asset-light 3PLs like Knichel Logistics and "
                   "start conversations with the top ten",
        "tools": _CAMPAIGN_TOOLS,
        "fields": [
            F("seed", "Which company to start from", "details",
              default="knichellogistics.com",
              hint="A reference customer's website. It shapes the search "
                   "and is never named in the emails."),
            _vertical_field(),
        ] + _targeting_fields() + _newsletter_fields() + _email_fields(
            DEFAULT_SEQUENCE) + [
            F("lookalike_pool", "How many lookalikes to pull before scoring",
              "size", "number", default="40"),
        ] + _size_fields("10", "4", "160") + _TM_SKIP_FIELDS,
        "steps": [
            "{vertical_guide}",
            "Use your ZoomInfo connector: find_similar_companies with "
            "{seed} as the seed, asking for {lookalike_pool} companies in "
            "{location} of about {company_size}. Fill any gap with "
            "search_companies on the same band. Keep the ones that resemble "
            "the seed in what they actually do, not just in size, and drop "
            "the seed itself and anything on ThriveModal's customer list.",
            "{skip_clause}",
            "Score the pool and land {companies}: for each one check the "
            "careers page for {roles} and the signals in the guide. A "
            "company with no live signal can still make the list if it "
            "resembles the seed closely, but say so, and rank the ones with "
            "a signal first.",
            _CONTACTS_STEP,
            _SHOW_STEP,
            _BUILD_STEP,
        ],
    },
    {
        "key": "tm_displacement",
        "name": "Find companies already using offshore staff",
        "blurb": "Companies that already run offshore staff have proven the "
                 "model. Find the ones in one vertical whose postings or "
                 "pages say so, and pitch the better-run version.",
        "example": "Find accounting firms whose job posts mention Manila or "
                   "an offshore team and start conversations",
        "tools": _CAMPAIGN_TOOLS,
        "fields": [
            _vertical_field("Accounting / CAS firms"),
        ] + _targeting_fields() + [
            F("search_terms", "What to search for", "details",
              default="Manila, Cebu, Philippines, offshore team, offshore "
                      "operations, night shift, overnight team, virtual "
                      "assistant"),
        ] + _newsletter_fields() + _email_fields(DEFAULT_SEQUENCE) + \
            _size_fields("5", "4", "120") + _TM_SKIP_FIELDS,
        "steps": [
            "{vertical_guide}",
            "Search job boards, LinkedIn and company pages for "
            "{vertical_label} companies in {location} of about "
            "{company_size} whose postings or pages mention {search_terms}. "
            "A US company posting a Philippines-based role, or describing "
            "an offshore team, is the signal. Note what they seem to be "
            "doing offshore today and whether it is through a provider or "
            "directly.",
            "{skip_clause}",
            "Land {companies} companies. The angle for these is not "
            "whether to go offshore, it is whether they are getting "
            "dedicated staff who work only for them, a replacement "
            "when someone leaves, and someone else handling HR, compliance "
            "and payroll. For each pick say what you can see about their "
            "current set-up and what the gap looks like, from evidence, "
            "not assumption.",
            _CONTACTS_STEP,
            _SHOW_STEP,
            _BUILD_STEP,
        ],
    },
    {
        "key": "tm_cost_pressure",
        "name": "Scan for cost pressure",
        "blurb": "Layoff notices, private-equity roll-ups and office "
                 "closures in one vertical: companies under pressure to do "
                 "the same work with fewer people onshore.",
        "example": "Read the WARN notices in Texas and Florida for logistics "
                   "companies and set up outreach to the survivors' COOs",
        "tools": _CAMPAIGN_TOOLS,
        "fields": [
            _vertical_field(),
            F("states", "Which states' WARN notices to read", "details",
              default="California, New York, Texas, Florida, Georgia, "
                      "Illinois and Pennsylvania"),
            F("lookback", "How far back to look", "details",
              default="the last 90 days"),
        ] + _targeting_fields() + _newsletter_fields() + _email_fields(
            DEFAULT_SEQUENCE) + _size_fields("5", "4", "120") + \
            _TM_SKIP_FIELDS,
        "steps": [
            "{vertical_guide}",
            "Read the state WARN notice pages for {states} over {lookback} "
            "and the news for private-equity acquisitions, roll-ups and "
            "office closures among {vertical_label} companies in "
            "{location}. Use your ZoomInfo connector's search_scoops for "
            "leadership changes and funding. Keep companies of about "
            "{company_size} where the cut hit operations, admin or "
            "back-office roles and the company is still trading, not "
            "closing.",
            "{skip_clause}",
            "Land {companies} companies and rank them by how recent and how "
            "targeted the pressure is. Do not open with the layoff. The "
            "first email leads with keeping the work moving with fewer "
            "people onshore, and never says we saw the notice.",
            _CONTACTS_STEP,
            _SHOW_STEP,
            _BUILD_STEP,
        ],
    },
    {
        "key": "tm_seasonal",
        "name": "Run a seasonal push for one vertical",
        "blurb": "Time a push to the season one vertical plans its staffing "
                 "in: accounting before busy season, logistics before "
                 "peak, and so on.",
        "example": "Reach accounting firm partners in November before they "
                   "staff for tax season",
        "tools": _CAMPAIGN_TOOLS,
        "fields": [
            _vertical_field("Accounting / CAS firms"),
            F("season_note", "Why now", "details", hint=_REC,
              placeholder="Recommended timing note for the vertical"),
        ] + _targeting_fields() + _newsletter_fields() + _email_fields(
            DEFAULT_SEQUENCE) + _size_fields("8", "4", "160") + \
            _TM_SKIP_FIELDS,
        "steps": [
            "{vertical_guide}",
            "Timing: {season_note}. Search job boards, LinkedIn and company "
            "pages for {vertical_label} companies in {location} of about "
            "{company_size} that are hiring {roles} or talking about the "
            "season ahead. Postings for temporary or seasonal help count "
            "double.",
            "{skip_clause}",
            _SCORE_STEP,
            _CONTACTS_STEP,
            _SHOW_STEP,
            _BUILD_STEP,
        ],
    },
    {
        "key": "tm_audience",
        "name": "Turn a saved audience into a campaign",
        "blurb": "Take contacts already imported into inboxslide, check "
                 "them, and put them into one campaign.",
        "example": "Take my Denver property managers audience and start a "
                   "conversation with all of them",
        "tools": ["tm_audiences", "tm_audience_preview", "campaign_types",
                  "my_campaign_styles", "tm_mailboxes", "campaigns_list",
                  "create_campaign"],
        "fields": [
            F("audience", "Which saved audience", "details", ask=True,
              placeholder="The name it has under Audiences"),
            _vertical_field("General back office"),
        ] + _newsletter_fields() + _email_fields(
            DEFAULT_SEQUENCE, "the audience name") + [
            F("email_cap", "Most people in one campaign", "size", "number",
              default="150",
              hint="A bigger audience is split into batches of this size."),
        ],
        "steps": [
            "Call tm_audiences and find the audience called {audience}. "
            "Call tm_audience_preview on it and tell me how many people are "
            "in it, which companies, and which job titles you see.",
            "{vertical_guide}",
            "Drop anyone without a work email, anyone at a staffing firm, "
            "a job board or a government body, and anyone whose title is "
            "nowhere near a buyer. Tell me how many you dropped and why.",
            "Show me the cleaned list grouped by company and the send "
            "volume. Then {gate}.",
            "{go_prefix} call tm_mailboxes and confirm a connected sending "
            "mailbox is there, then build one campaign for the whole "
            "audience with create_campaign using {template_clause}, "
            "start_date {start_date}, niche set to what these people have "
            "in common, and the contacts passed in the contacts argument. "
            "If there are more than {email_cap} people, split them into "
            "batches of that size and number the batches.{name_clause}"
            "{newsletter_clause} Read back the campaign id, the step count "
            "and the queued-contact count for each batch.",
        ],
    },
    {
        "key": "tm_account",
        "name": "Research one account before I reach out",
        "blurb": "Everything worth knowing about one company before a call "
                 "or a hand-written email: what they do, who buys, what "
                 "they are hiring, and the talk track. No emails are sent.",
        "example": "Research Acme Freight in Dallas before I call the COO",
        "tools": [],
        "fields": [
            F("company", "Which company", "details", ask=True,
              placeholder="Name, and the website if you have it"),
            _vertical_field(),
            F("who_to_reach", "Who to find there", "details", hint=_REC,
              placeholder="Recommended buyers for the vertical"),
        ],
        "steps": [
            "{vertical_guide}",
            "Read {company}'s website, careers page, LinkedIn page and "
            "recent news. Use your ZoomInfo connector: account_research and "
            "search_scoops for the company, then contact_research for the "
            "people. Tell me what they do, how big they are, the roles they "
            "are hiring, which of those ThriveModal routinely places, every "
            "signal from the guide you actually found, and any disqualifier "
            "from the standing rules.",
            "Name the people to reach, working down {who_to_reach}, with "
            "their titles and how long they have been there. No emails "
            "needed yet.",
            "Write me a one-paragraph talk track and three discovery "
            "questions that use what you found, keeping to the claims in "
            "the standing rules. Do not draft the outreach emails; I will "
            "run a campaign routine for that.",
        ],
    },
    {
        "key": "other",
        "name": "Something else",
        "blurb": "Describe it in your own words and the prompt is built "
                 "around that, with the ThriveModal rules attached.",
        "example": "Go through my Stay on Their Radar campaigns and tell me which "
                   "contacts have replied",
        "tools": [],
        "fields": [
            F("what", "What you want done", "details", "textarea", ask=True,
              placeholder="Say it the way you'd say it to a colleague."),
            F("done_when", "How you'll know it worked", "details",
              placeholder="Optional"),
        ],
        "steps": [
            "Work out what is actually being asked and say it back to me "
            "in one line before you start. If it needs prospects, use the "
            "standing rules below to qualify them. If it needs a campaign, "
            "call campaign_types first and pick the type that matches the "
            "situation.",
            "{what}",
            "{done_clause}",
            "Show me the result before acting on anything that leaves this "
            "machine.",
        ],
    },
]
ROUTINE_BY_KEY = finalize_routines(ROUTINES)
DEFAULT_ROUTINE = "other"


# ── Starters ─────────────────────────────────────────────────────────────

STARTERS = [
    {
        "id": "signal",
        "label": "Find companies showing a hiring signal",
        "sub": "Job boards, one vertical, the buyer at each company, and a "
               "new-business campaign for every one.",
        "summary": "Find companies in one vertical hiring the roles "
                   "ThriveModal places, pull the buyer at each, and build a "
                   "new-business campaign for each one.",
        "routine": "tm_signal_hunt",
        "vals": {"vertical": "Logistics / 3PL"},
    },
    {
        "id": "lookalike",
        "label": "Find companies like a customer",
        "sub": "Start from a reference customer and find the companies that "
               "look like it.",
        "summary": "Find companies that look like a reference customer, "
                   "check them for a signal, and start a conversation with "
                   "the owners.",
        "routine": "tm_lookalikes",
        "vals": {},
    },
    {
        "id": "displace",
        "label": "Find companies already offshore",
        "sub": "They have proven the model. Pitch the better-run version.",
        "summary": "Find companies whose postings or pages show they already "
                   "use offshore staff and start a conversation about doing "
                   "it with dedicated people and someone else running the "
                   "admin.",
        "routine": "tm_displacement",
        "vals": {},
    },
    {
        "id": "pressure",
        "label": "Scan for cost pressure",
        "sub": "WARN notices, roll-ups and closures in one vertical.",
        "summary": "Find companies in one vertical under visible cost "
                   "pressure and start a conversation about keeping the work "
                   "moving with fewer people onshore.",
        "routine": "tm_cost_pressure",
        "vals": {},
    },
    {
        "id": "season",
        "label": "Run a seasonal push",
        "sub": "Time it to when one vertical plans its staffing.",
        "summary": "Run a push into one vertical timed to the season it "
                   "staffs for.",
        "routine": "tm_seasonal",
        "vals": {"vertical": "Accounting / CAS firms"},
    },
    {
        "id": "audience",
        "label": "Turn a saved audience into a campaign",
        "sub": "Contacts already in inboxslide, checked and put into one "
               "campaign.",
        "summary": "Take one of my saved audiences, clean it, and put it "
                   "into a campaign.",
        "routine": "tm_audience",
        "vals": {},
    },
    {
        "id": "account",
        "label": "Research one account",
        "sub": "Everything worth knowing before a call. Nothing is sent.",
        "summary": "Research one company before I reach out: what they do, "
                   "who buys, what they are hiring, and the talk track.",
        "routine": "tm_account",
        "vals": {},
    },
    {
        "id": "other",
        "label": "Something else",
        "sub": "Say it in your own words.",
        "summary": "",
        "routine": "other",
        "vals": {},
    },
]
STARTER_BY_ID = {st["id"]: st for st in STARTERS}


# ── Standing rules ────────────────────────────────────────────────────────
#
# The first rule is swapped for UNATTENDED_RULE on a scheduled run, so it
# has to be the "wait for me" one.

STANDING_RULES = [
    "Show me what you have before anything sends, imports or spends "
    "credits, and wait for me to say go.",
    "If a step is blocked, quote the literal error and tell me what you "
    "could not determine. Do not guess at a cause and do not pad around it.",
    "Do not invent a specific. Every company, number and date you give me "
    "has to come from something you actually read.",
    "What ThriveModal offers comes from thrivemodal.com and nowhere else: "
    "dedicated full-time staff in the Philippines who work only for the "
    "client, in any US time zone; ThriveModal is the employer of record and "
    "handles HR, compliance, payroll and admin, with IT set up before day "
    "one; no upfront or placement fee; month to month with no cancellation "
    "fee; a lifetime free replacement; one all-inclusive monthly rate "
    "invoiced every two weeks; three or more vetted candidates per role "
    "with video pre-screens; a start in about ten days; an account "
    "executive reply within a day; NDAs, isolated workstations and a secure "
    "VPN; and the ThriveCore layer of an account manager, monthly "
    "check-ins, quarterly reviews and monthly reports.",
    "Savings are \"up to sixty to seventy percent, fully burdened\" and "
    "that is a ceiling, not a promise. Never quote a monthly, hourly or "
    "total figure, never say guaranteed savings, and never invent a client "
    "count, a retention figure, a certification, a placement or a result. "
    "One person is not round-the-clock coverage. Knichel Logistics and The "
    "Travel Byrds are proof references, not prospects: never put them on a "
    "list and never attach numbers to them.",
    "Say nothing about Filipino workers as a group beyond what the website "
    "says. No lines about accents, work ethic or cost of living.",
    "Disqualify before you rank: union shops, work that must be on site, "
    "licensed or physical roles, companies under ten people, and companies "
    "past about a thousand people that already run a captive offshore team "
    "or a large BPO contract. A vacancy counts as a signal only if it is "
    "under thirty days old; an announcement, under ninety.",
    "The ZoomInfo connector is the only ZoomInfo surface you have. Do not "
    "call the ZoomInfo REST API and do not scrape the site. If the "
    "connector refuses, quote it and stop at the company list.",
    "Before any create_campaign call, call tm_mailboxes and confirm a "
    "connected sending mailbox is there. If there is none, stop and tell "
    "me: nothing can send without one.",
]
UNATTENDED_RULE = _e.UNATTENDED_RULE


# ── The catalogue ─────────────────────────────────────────────────────────

TM = Catalogue(
    routines=ROUTINES,
    routine_by_key=ROUTINE_BY_KEY,
    default_routine=DEFAULT_ROUTINE,
    standing_rules=STANDING_RULES,
    unattended_rule=UNATTENDED_RULE,
    starters=STARTERS,
    starter_by_id=STARTER_BY_ID,
    sequences=SEQUENCES,
    template_key=TEMPLATE_KEY,
    default_sequence=DEFAULT_SEQUENCE,
    default_template=DEFAULT_TEMPLATE,
    setups_file="tm_prompt_setups.json",
    product="inboxslide",
    connector="inboxslide connector",
    assistant="Claude",
    page_title="AI Prompt",
    page_sub=("Pick what you want done. inboxslide asks the questions worth "
              "asking, recommends the targeting for the vertical you pick, "
              "and writes the message to paste into Claude - with the "
              "ThriveModal rules already in it."),
    result_copy=("Copy it, open Claude with your inboxslide connector "
                 "switched on, and paste it as your first message."),
    result_extra=None,
    derive_extra=_derive_tm,
)


def build_prompt(req):
    """The ThriveModal prompt for a request, for tests and callers that
    never render the page."""
    return _e.build_prompt(req, TM)


def p_tm_prompts(s, rf):
    """AI Prompt - the inboxslide page. Binds the ThriveModal catalogue and
    hands the rest to the engine."""
    _e.render_page(s, rf, TM)


def p_tm_saved_prompts(s, rf):
    """Saved Prompts - the prompts this user saved from the AI Prompt page."""
    _e.render_saved_page(s, rf, TM)
