"""Recommend Arena Sales Contacts for Pipeline candidates (2026-11-12).

Mike: users hand Claude one or more candidates and ask "who in our sales
contacts should I pitch them to?". This ranks the team bank's companies
(team_contacts.group_by_company rows) for those candidates and picks the
best people at each.

Pure functions, no app imports, so it is unit-testable. The caller supplies
the bank rows and the flags it knows (Current Clients, companies a teammate
is working now); this module only scores and explains.

Scoring, per company, best candidate wins:
  industry   +40 same bucket as the candidate, +20 a sibling construction
             trade (a superintendent fits a GC and a mechanical sub alike)
  location   +25 same state, +10 more when a contact is in the same city
  people     best contact: +20 hiring authority in the title (owner, VP,
             director, HR/talent...), +6 per word shared with the
             candidate's title family (project, estimating, safety...)
  history    +8 someone there replied to the team before
Never recommended: the candidate's own current employer.
"""
from __future__ import annotations

import re

import team_campaigns as _tc

# Buckets that hire the same field people; a near miss, not a miss.
_CONSTRUCTION_FAMILY = frozenset({
    "Construction", "General Contracting", "Mechanical Contracting",
    "Electrical Contracting", "Healthcare Construction",
    "Data Center / Mission Critical", "Civil & Engineering",
})

_AUTHORITY = re.compile(
    r"\b(owner|founder|president|ceo|coo|cfo|chief|principal|partner|vp|"
    r"vice president|director|head|general manager|gm|"
    r"hr|human resources|talent|recruit\w*|people|hiring|operations manager)\b")

# Words that say nothing about the role family.
_STOP = frozenset("""senior sr junior jr lead i ii iii iv the and of a an at
for to in with manager mgr assistant asst associate staff chief head
director vp vice president principal level""".split())

_WORD = re.compile(r"[a-z][a-z/&]+")


def industry_of_text(*parts) -> str:
    """The team_campaigns industry bucket a candidate's text points at."""
    text = " ".join(str(p or "") for p in parts).lower()
    for label, pat in _tc.INDUSTRIES:
        if re.search(pat, text):
            return label
    return _tc.INDUSTRY_OTHER


def role_words(title: str) -> set:
    return {w for w in _WORD.findall((title or "").lower())
            if w not in _STOP and len(w) > 2}


def _norm_co(name: str) -> str:
    n = re.sub(r"[^a-z0-9 ]", " ", (name or "").lower())
    n = re.sub(r"\b(inc|llc|ltd|co|corp|corporation|company|group|the)\b", " ", n)
    return re.sub(r"\s+", " ", n).strip()


def profile(cand: dict) -> dict:
    """What scoring needs from a candidate dict (Pipeline row fields or a
    free-text profile: title, skills, summary, industry, city, state,
    employer)."""
    title = cand.get("title") or cand.get("current_title") or ""
    employer = cand.get("employer") or cand.get("current_employer") or ""
    industry = _tc.category_label(cand.get("industry")) if cand.get("industry") else ""
    if not industry:
        industry = industry_of_text(title, cand.get("skills"), cand.get("summary"),
                                    employer, cand.get("work_history"))
    return {
        "label": cand.get("label") or title or "candidate",
        "title": title,
        "words": role_words(title),
        "industry": industry,
        "state": _tc.state_of(cand.get("state") or "") or "",
        "city": (cand.get("city") or "").strip().lower(),
        "employer": _norm_co(employer),
    }


def _contact_score(c: dict, prof: dict) -> tuple:
    title = (c.get("title") or "").lower()
    pts, why = 0, []
    if _AUTHORITY.search(title):
        pts += 20
        why.append("hiring authority")
    shared = prof["words"] & role_words(title)
    if shared:
        pts += 6 * len(shared)
        why.append("same field (" + ", ".join(sorted(shared)) + ")")
    if c.get("replied"):
        pts += 4
        why.append("replied before")
    return pts, why


def score_row(row: dict, prof: dict) -> dict | None:
    """Score one bank company for one candidate; None if it must not be
    pitched (their own employer)."""
    co = _norm_co(row.get("company"))
    if prof["employer"] and co and (co == prof["employer"]
                                    or co.startswith(prof["employer"] + " ")
                                    or prof["employer"].startswith(co + " ")):
        return None
    pts, why = 0, []
    ind = row.get("industry") or _tc.INDUSTRY_OTHER
    if prof["industry"] != _tc.INDUSTRY_OTHER and ind == prof["industry"]:
        pts += 40
        why.append(f"industry match ({ind})")
    elif ind in _CONSTRUCTION_FAMILY and prof["industry"] in _CONSTRUCTION_FAMILY:
        pts += 20
        why.append(f"related trade ({ind})")
    if prof["state"] and row.get("state") == prof["state"]:
        pts += 25
        why.append(f"same state ({prof['state']})")
        if prof["city"] and any((c.get("city") or "").strip().lower() == prof["city"]
                                for c in row.get("contacts") or []):
            pts += 10
            why.append("contact in the same city")
    people = []
    for c in row.get("contacts") or []:
        cp, cw = _contact_score(c, prof)
        people.append((cp, cw, c))
    people.sort(key=lambda t: (-t[0], t[2].get("name") or ""))
    if people and people[0][0] > 0:
        pts += people[0][0]
    if row.get("replied"):
        pts += 8
        why.append("someone there replied to the team before")
    return {"score": pts, "why": why, "people": people}


def recommend(rows: list, candidates: list, limit: int = 15,
              per_company: int = 3, state: str = "", industry: str = "",
              flags: dict | None = None, skip: set | None = None) -> dict:
    """Rank bank company rows for the candidates.

    rows: team_contacts.group_by_company rows. candidates: dicts for
    profile(). flags: company key -> list of notes to show (e.g. "Current
    Client"). skip: company keys to leave out (e.g. worked by a teammate in
    the last 30 days). state / industry narrow the rows first."""
    flags = flags or {}
    skip = skip or set()
    profs = [profile(c) for c in candidates]
    st = _tc.state_of(state) if state else ""
    ind = _tc.category_label(industry) if industry else ""
    out, skipped = [], 0
    for row in rows:
        if st and row.get("state") != st:
            continue
        if ind and row.get("industry") != ind:
            continue
        if row.get("key") in skip:
            skipped += 1
            continue
        best, fits = None, []
        for p in profs:
            s = score_row(row, p)
            if s is None:
                best = None
                fits = []
                break
            if s["score"] >= 30:
                fits.append(p["label"])
            if best is None or s["score"] > best["score"]:
                best = dict(s, prof=p)
        if best is None or best["score"] <= 0:
            continue
        out.append((best, fits, row))
    out.sort(key=lambda t: (-t[0]["score"], (t[2].get("company") or "").lower()))
    recs = []
    for best, fits, row in out[:limit]:
        people = []
        for cp, cw, c in best["people"][:per_company]:
            people.append({"contact": c, "why": cw})
        recs.append({
            "company": row.get("company"), "key": row.get("key"),
            "industry": row.get("industry"), "state": row.get("state"),
            "score": best["score"], "why": best["why"],
            "best_fit": best["prof"]["label"], "fits": fits,
            "flags": flags.get(row.get("key"), []),
            "people": people,
        })
    return {"candidates": [{"label": p["label"], "title": p["title"],
                            "industry": p["industry"], "state": p["state"]}
                           for p in profs],
            "considered": len(rows), "skipped_worked_recently": skipped,
            "recommendations": recs}
