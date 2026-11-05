"""Testimonials (ThriveModal / inboxslide only).

The owner makes one private link per client on the Testimonials page. The
client opens it with no login, answers a short click-through survey, gets a
draft quote built ONLY from their own answers, edits it, picks how it may be
used, and approves it. Answers and the approved quote land back on the
owner's page.

Storage:
- tm_testimonials.json in the owner's user folder: {"requests": [...]}.
- tm_testimonial_links.json in the shared data root: {token: owner_email}.
  The public page has no session, so this index is how a link finds its
  owner. It holds nothing but the owner's email per token.

Companion module, lazy-imported by the host for the page; the public routes
register at host import (like ats.py), guarded so a failure here never stops
the app.
"""
import html
import json
import re
import secrets
import sys
import threading
from datetime import datetime, timezone

STATE_FILE = "tm_testimonials.json"
LINKS_FILE = "tm_testimonial_links.json"
_LOCK = threading.Lock()
_TOKEN_RE = re.compile(r"^[A-Za-z0-9_-]{10,40}$")

STATUS_LABEL = {"sent": "Link made", "opened": "Opened", "answered": "Answered",
                "approved": "Approved"}

# ── The survey ───────────────────────────────────────────────────────────
# kind: one (pick one), multi (pick any), rate (1-5 per item), text.
# Every option is (key, label). Keys are what gets stored.
QUESTIONS = [
    {"id": "roles", "kind": "multi", "section": "About your hire",
     "q": "What role(s) did you hire through us?",
     "opts": [("admin", "Admin / Executive assistant"), ("support", "Customer support"),
              ("accounting", "Bookkeeping / Accounting"), ("sales", "Sales support"),
              ("marketing", "Marketing"), ("dispatch", "Dispatch / Logistics"),
              ("it", "IT"), ("other", "Other")]},
    {"id": "count", "kind": "one", "q": "How many people have you hired through us?",
     "opts": [("1", "1"), ("2", "2"), ("3-5", "3 to 5"), ("6+", "6 or more")]},
    {"id": "tenure", "kind": "one", "q": "How long have we worked together?",
     "opts": [("lt3m", "Under 3 months"), ("3-6m", "3 to 6 months"), ("6-12m", "6 to 12 months"),
              ("1-2y", "1 to 2 years"), ("2y+", "2+ years")]},
    {"id": "challenge", "kind": "multi", "section": "Before and after",
     "q": "Before working with us, what was the biggest challenge?",
     "opts": [("local", "Couldn't find good local hires"), ("cost", "A U.S. hire was too expensive"),
              ("turnover", "Turnover"), ("admin", "I was doing too much admin myself"),
              ("coverage", "Gaps in after-hours coverage"),
              ("growth", "Growing faster than the team")]},
    {"id": "why", "kind": "multi", "q": "Why did you choose us?",
     "opts": [("cost", "Lower cost than a U.S. hire"),
              ("vetting", "Vetted, English-fluent candidates"),
              ("speed", "How fast we could fill the role"),
              ("quality", "Quality of the candidates"),
              ("service", "Hands-on, personal service"),
              ("referral", "Someone recommended us")]},
    {"id": "fill", "kind": "one", "q": "How fast was the role filled?",
     "opts": [("lt2w", "Under 2 weeks"), ("2-4w", "2 to 4 weeks"), ("1-2m", "1 to 2 months"),
              ("longer", "Longer")]},
    {"id": "ramp", "kind": "one", "q": "How quickly were they up to speed?",
     "opts": [("week", "Within the first week"), ("month", "Within the first month"),
              ("2-3m", "2 to 3 months")]},
    {"id": "results", "kind": "multi", "q": "What's the biggest result so far?",
     "opts": [("savings", "Cost savings"), ("hours", "Hours freed up for me"),
              ("response", "Faster customer response"),
              ("growth", "Grew without another local hire"),
              ("reliable", "Reliability"), ("quality", "Quality of work")]},
    {"id": "savings", "kind": "one", "q": "Roughly how much a year do you save compared with a U.S. hire?",
     "opts": [("lt20", "Under $20k"), ("20-40", "$20k to $40k"), ("40-60", "$40k to $60k"),
              ("60+", "$60k+"), ("skip", "Prefer not to say")]},
    {"id": "hours", "kind": "one", "q": "Hours a week freed up for you or your team",
     "opts": [("lt5", "Under 5"), ("5-10", "5 to 10"), ("10-20", "10 to 20"), ("20+", "20+")]},
    {"id": "ratings", "kind": "rate", "section": "Quality",
     "q": "Rate your hire from 1 to 5",
     "opts": [("english", "English and communication"), ("ethic", "Work ethic"),
              ("reliability", "Reliability"), ("quality", "Quality of work"),
              ("fit", "Fit with your team")]},
    {"id": "expanded", "kind": "one", "q": "Have you added more people since your first hire?",
     "opts": [("yes", "Yes"), ("planning", "Planning to"), ("no", "No")]},
    {"id": "happy", "kind": "one", "q": "How happy are you with the results?",
     "opts": [("very", "Very happy"), ("happy", "Happy"), ("mixed", "It's been mixed")]},
    {"id": "own_words", "kind": "text", "q": "Anything you'd like to say in your own words? (optional)"},
]
PERMISSIONS = [("full", "Name, title, company and logo"),
               ("anon", "Title and industry only (no names)"),
               ("internal", "Internal only. Please don't publish it.")]
_Q = {q["id"]: q for q in QUESTIONS}
_PERM = dict(PERMISSIONS)


def _ff():
    for name in ("flowdrip_app", "__main__"):
        m = sys.modules.get(name)
        if m is not None and hasattr(m, "_BASE_DATA_DIR") and hasattr(m, "C"):
            return m
    import flowdrip_app as m  # standalone/test fallback
    return m


def _now():
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _clip(v, n):
    return str(v or "").strip()[:n]


# ── Pure helpers (tested) ────────────────────────────────────────────────

def clean_answers(raw):
    """Keep only known questions and known option keys."""
    out = {}
    if not isinstance(raw, dict):
        return out
    for q in QUESTIONS:
        v = raw.get(q["id"])
        keys = [k for k, _ in q.get("opts", [])]
        if q["kind"] == "one":
            if isinstance(v, str) and v in keys:
                out[q["id"]] = v
        elif q["kind"] == "multi":
            if isinstance(v, list):
                picked = [k for k in keys if k in v]
                if picked:
                    out[q["id"]] = picked
        elif q["kind"] == "rate":
            if isinstance(v, dict):
                r = {}
                for k in keys:
                    try:
                        n = int(v.get(k))
                    except (TypeError, ValueError):
                        continue
                    if 1 <= n <= 5:
                        r[k] = n
                if r:
                    out[q["id"]] = r
        elif q["kind"] == "text":
            t = _clip(v, 1000)
            if t:
                out[q["id"]] = t
    return out


def answer_lines(answers):
    """[(question, answer text)] for display, survey order."""
    rows = []
    for q in QUESTIONS:
        v = answers.get(q["id"])
        if not v:
            continue
        lab = dict(q.get("opts", []))
        if q["kind"] == "one":
            txt = lab.get(v, v)
        elif q["kind"] == "multi":
            txt = ", ".join(lab.get(k, k) for k in v)
        elif q["kind"] == "rate":
            txt = ", ".join(f"{lab.get(k, k)} {n}/5" for k, n in v.items())
        else:
            txt = v
        rows.append((q["q"], txt))
    return rows


_ROLE_PHRASE = {"admin": "executive assistant", "support": "customer support",
                "accounting": "bookkeeping", "sales": "sales support", "marketing": "marketing",
                "dispatch": "dispatch", "it": "IT"}
_CHALLENGE = {"local": "we couldn't find good people locally",
              "cost": "a U.S. hire was too expensive",
              "turnover": "we kept losing people to turnover",
              "admin": "I was buried in admin work",
              "coverage": "we had gaps in after-hours coverage",
              "growth": "we were growing faster than our team"}
_WHY = {"cost": "the lower cost", "vetting": "their vetted, English-fluent candidates",
        "speed": "how fast they could fill the role",
        "quality": "the quality of their candidates", "service": "their hands-on service",
        "referral": "a recommendation from someone we trust"}
_FILL = {"lt2w": "in under two weeks", "2-4w": "in under a month", "1-2m": "in about a month"}
_RAMP = {"week": "within the first week", "month": "within the first month"}
_SAVE = {"lt20": "up to $20,000", "20-40": "$20,000 to $40,000", "40-60": "$40,000 to $60,000",
         "60+": "over $60,000"}
_HOURS = {"5-10": "5 to 10 hours", "10-20": "10 to 20 hours", "20+": "over 20 hours"}
_COUNT = {"2": "2", "3-5": "3 to 5", "6+": "6 or more"}
_SOLVED = (("response", "Our customers get answers faster."),
           ("growth", "We grew without adding another local hire."),
           ("reliable", "The work is reliable and done right."),
           ("quality", "The work is reliable and done right."),
           ("savings", "It cut our hiring costs."))
_HAPPY = {"very": "We're very happy with the results.", "happy": "We're happy with the results."}


def _picked(a, key, table, n=2):
    return [table[k] for k in (a.get(key) or []) if k in table][:n]


def build_draft(answers, company="us", hire_name=""):
    """A short first-person quote made only from what the client picked, in
    one order: why they came to us, how we delivered, what they got (numbers
    first), how happy they are. Nothing here adds a claim the answers do not
    make, and nothing is filler."""
    a = answers or {}
    company = (company or "").strip() or "us"
    parts = []

    # 1. Why they came to us.
    why = _picked(a, "why", _WHY)
    ch = _picked(a, "challenge", _CHALLENGE, 1 if why else 2)
    if ch and why:
        parts.append(f"We came to {company} because {ch[0]} and chose them for "
                     f"{' and '.join(why)}.")
    elif ch:
        parts.append(f"We came to {company} because {' and '.join(ch)}.")
    elif why:
        parts.append(f"We chose {company} for {' and '.join(why)}.")

    # 2. How we delivered.
    roles = [r for r in a.get("roles") or [] if r in _ROLE_PHRASE]
    role = _ROLE_PHRASE[roles[0]] + " " if len(roles) == 1 else ""
    fill = _FILL.get(a.get("fill", ""), "")
    ramp = _RAMP.get(a.get("ramp", ""), "")
    who = (hire_name or "").strip() or "our new hire"
    subj = "They" if parts else company
    if fill:
        s = f"{subj} filled our {role}role {fill}"
        s += f", and {who} was up to speed {ramp}." if ramp else "."
        parts.append(s)
    elif ramp:
        parts.append(f"{who[0].upper() + who[1:]} was up to speed {ramp}.")

    # 3. What they got: numbers first, else the one thing it solved.
    sav = _SAVE.get(a.get("savings", ""))
    hrs = _HOURS.get(a.get("hours", ""))
    if sav and hrs:
        parts.append(f"We're saving {sav} a year compared with a U.S. hire and getting "
                     f"{hrs} a week back.")
    elif sav:
        parts.append(f"We're saving {sav} a year compared with a U.S. hire.")
    elif hrs:
        parts.append(f"We're getting {hrs} a week back.")
    else:
        res = a.get("results") or []
        line = next((txt for k, txt in _SOLVED if k in res), "")
        if line:
            parts.append(line)
    n = _COUNT.get(a.get("count", ""))
    if a.get("expanded") == "yes":
        parts.append(f"We've since grown to {n} people with them." if n
                     else "We've since added more people.")
    elif a.get("expanded") == "planning":
        parts.append("We're planning our next hire.")

    # 4. How happy they are, then anything in their own words.
    if a.get("happy") in _HAPPY:
        parts.append(_HAPPY[a["happy"]])
    own = (a.get("own_words") or "").strip()
    if own:
        parts.append(own)
    return " ".join(parts)


def new_token():
    return secrets.token_urlsafe(12)


def new_request(company, contact="", email="", hire="", role=""):
    return {"token": new_token(), "company": _clip(company, 120), "contact": _clip(contact, 80),
            "email": _clip(email, 160), "hire": _clip(hire, 80), "role": _clip(role, 80),
            "created": _now(), "status": "sent", "answers": {}, "draft": "",
            "quote": "", "permission": "", "sig_name": "", "sig_title": "",
            "sig_company": "", "answered_at": "", "approved_at": ""}


def request_email(req, link, sender_first="", our_company="ThriveModal"):
    """(subject, body) the owner pastes into their own inbox."""
    first = (req.get("contact") or "").split(" ")[0] or "there"
    hire = req.get("hire") or ""
    line = (f"I've heard great things about how {hire} has settled in with your team."
            if hire else "I hope things are going well with your team.")
    body = (f"Hi {first},\n\n{line}\n\n"
            "I have a favor to ask. We're asking a few of our best clients for a short "
            "testimonial. Owners thinking about hiring offshore trust another business "
            "owner more than anything we could tell them.\n\n"
            "I made it quick: a few click-through questions, about 3 minutes, no "
            "login. At the end it drafts a short quote from your answers. You can edit "
            "it and approve it. Nothing goes anywhere "
            "without your OK.\n\n"
            f"{link}\n\n"
            "Thanks either way. We appreciate you.\n\n"
            f"{sender_first}\n{our_company}")
    return "Quick favor?", body


SURVEY_LINK_TEXT = "fill out this quick 2-minute survey"


def shared_email(link, sender_first="", our_company="ThriveModal"):
    """(subject, plain text, html) for the one link every client gets. The
    html puts the link on the survey sentence (Mike, 2026-11-05)."""
    paras = [
        "Hi,",
        "I hope things are going well with your team.",
        "I have a favor to ask. We're asking our clients for a short testimonial. Owners "
        "thinking about hiring offshore trust another business owner more than anything "
        "we could tell them.",
        f"If you have a minute, just reply with a few sentences on why you chose "
        f"{our_company} and how it's gone. If you don't have time to write an email, you "
        f"can just {{LINK}} and that works just as well. It drafts a short quote from your "
        "answers that you can edit and approve. Nothing is used without your OK.",
        "Thanks either way. We appreciate you.",
    ]
    sign = [x for x in (sender_first, our_company) if x]
    text = "\n\n".join(paras).replace("{LINK}", f"{SURVEY_LINK_TEXT} ({link})")
    text += "\n\n" + "\n".join(sign)
    esc = html.escape
    a = (f'<a href="{esc(link, quote=True)}">{SURVEY_LINK_TEXT}</a>')
    body = "".join(f"<p>{esc(x).replace('{LINK}', a)}</p>" for x in paras)
    body += "<p>" + "<br>".join(esc(x) for x in sign) + "</p>"
    return "Quick favor?", text, body


def public_link(origin, token):
    """The link clients see: says whose it is, so it never reads as spam."""
    return f"{origin}/ThriveModal/review/{token}"


# ── Storage ──────────────────────────────────────────────────────────────

def _links_path():
    return _ff()._BASE_DATA_DIR / LINKS_FILE


def _state_path(owner):
    return _ff()._resolve_user_root(owner) / STATE_FILE


def _read_json(p, default):
    try:
        if p.exists():
            d = json.loads(p.read_text(encoding="utf-8"))
            if isinstance(d, type(default)):
                return d
    except Exception:
        pass
    return default


def _write_json(p, data):
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, indent=2), encoding="utf-8")
    tmp.replace(p)


def load_requests(owner):
    d = _read_json(_state_path(owner), {})
    return [r for r in (d.get("requests") or []) if isinstance(r, dict) and r.get("token")]


def save_requests(owner, reqs):
    d = _read_json(_state_path(owner), {})
    d["requests"] = reqs
    _write_json(_state_path(owner), d)


def shared_token(owner, create=True):
    """The owner's one link for every client. Made on first ask, then fixed."""
    with _LOCK:
        d = _read_json(_state_path(owner), {})
        tok = d.get("shared_token") or ""
        if tok or not create:
            return tok
        tok = new_token()
        d["shared_token"] = tok
        d.setdefault("requests", [])
        _write_json(_state_path(owner), d)
        links = _read_json(_links_path(), {})
        links[tok] = owner.lower().strip()
        _write_json(_links_path(), links)
        return tok


def find_shared(token):
    """The owner whose shared link this is, or None."""
    if not _TOKEN_RE.match(str(token or "")):
        return None
    owner = _read_json(_links_path(), {}).get(token)
    if owner and _read_json(_state_path(owner), {}).get("shared_token") == token:
        return owner
    return None


def clean_about(raw):
    """Who filled in the shared link. Name and company are required."""
    raw = raw if isinstance(raw, dict) else {}
    return {"name": _clip(raw.get("name"), 80), "title": _clip(raw.get("title"), 80),
            "company": _clip(raw.get("company"), 120), "email": _clip(raw.get("email"), 160),
            "hire": _clip(raw.get("hire"), 80)}


def add_request(owner, req):
    with _LOCK:
        reqs = load_requests(owner)
        reqs.insert(0, req)
        save_requests(owner, reqs)
        links = _read_json(_links_path(), {})
        links[req["token"]] = owner.lower().strip()
        _write_json(_links_path(), links)


def delete_request(owner, token):
    with _LOCK:
        save_requests(owner, [r for r in load_requests(owner) if r["token"] != token])
        links = _read_json(_links_path(), {})
        if links.get(token) == owner.lower().strip():
            links.pop(token, None)
            _write_json(_links_path(), links)


def find(token):
    """(owner, request) for a public token, or (None, None)."""
    if not _TOKEN_RE.match(str(token or "")):
        return None, None
    owner = _read_json(_links_path(), {}).get(token)
    if not owner:
        return None, None
    for r in load_requests(owner):
        if r["token"] == token:
            return owner, r
    return None, None


def update(owner, token, fn):
    with _LOCK:
        reqs = load_requests(owner)
        for r in reqs:
            if r["token"] == token:
                fn(r)
                save_requests(owner, reqs)
                return r
    return None


def _our_company(owner):
    try:
        ff = _ff()
        p = ff._resolve_user_root(owner) / "dripdrop_config.json"
        cfg = _read_json(p, {})
        return (cfg.get("company_name") or "").strip() or "ThriveModal"
    except Exception:
        return "ThriveModal"


# ── Public routes (no login) ─────────────────────────────────────────────

def _open_request():
    """The blank request the shared link renders before anyone answers."""
    return {"token": "", "status": "opened", "company": "", "contact": ""}


def _public_html(req, our_company, logo_url, open_token=""):
    state = {"open": bool(open_token), "child": False, "token": open_token or req["token"], "status": req["status"], "company": req["company"],
             "contact": req["contact"], "draft": req.get("draft") or "",
             "quote": req.get("quote") or "", "permission": req.get("permission") or "",
             "sig_name": req.get("sig_name") or req.get("contact") or "",
             "sig_title": req.get("sig_title") or "",
             "sig_company": req.get("sig_company") or req.get("company") or "",
             "answers": req.get("answers") or {}}
    qs = [{"id": q["id"], "kind": q["kind"], "q": q["q"], "section": q.get("section", ""),
           "opts": q.get("opts", [])} for q in QUESTIONS]
    blob = json.dumps({"state": state, "questions": qs, "perms": PERMISSIONS,
                       "us": our_company}).replace("</", "<\\/")
    page = _PUBLIC_TEMPLATE.replace("__DATA__", blob).replace(
        "__US__", html.escape(our_company)).replace("__LOGO__", html.escape(logo_url))
    return page


def register_routes():
    from nicegui import app
    from starlette.requests import Request
    from starlette.responses import HTMLResponse, JSONResponse

    def _limited(request):
        ff = _ff()
        try:
            fwd = (request.headers.get("x-forwarded-for") or "").split(",")[0].strip()
            ip = fwd or (request.client.host if request.client else "?")
            key = f"review:{ip}"
            if not ff._rate_limit_check(key):
                return True
            ff._rate_limit_record(key)
        except Exception:
            pass
        return False

    @app.get("/ThriveModal/review/{token}")
    @app.get("/review/{token}")
    async def review_page(token: str):
        owner, req = find(token)
        if not req:
            shared_owner = find_shared(token)
            if shared_owner:
                ff = _ff()
                logo = f"{getattr(ff, '_PUBLIC_ORIGIN', '')}/static/thrivemodal_logo_email.png"
                return HTMLResponse(
                    _public_html(_open_request(), _our_company(shared_owner), logo, token),
                    headers={"Cache-Control": "no-store", "X-Robots-Tag": "noindex, nofollow"})
            return HTMLResponse(_NOT_FOUND, status_code=404)
        if req["status"] == "sent":
            update(owner, token, lambda r: r.update(status="opened"))
            req["status"] = "opened"
        ff = _ff()
        logo = f"{getattr(ff, '_PUBLIC_ORIGIN', '')}/static/thrivemodal_logo_email.png"
        return HTMLResponse(_public_html(req, _our_company(owner), logo),
                            headers={"Cache-Control": "no-store",
                                     "X-Robots-Tag": "noindex, nofollow"})

    @app.post("/review/{token}/answers")
    async def review_answers(token: str, request: Request):
        if _limited(request):
            return JSONResponse({"error": "Too many tries. Wait a minute and try again."},
                                status_code=429)
        owner, req = find(token)
        if not req:
            shared_owner = find_shared(token)
            if not shared_owner:
                return JSONResponse({"error": "This link is no longer active."}, status_code=404)
            # The shared link: every person who answers becomes their own
            # entry, with its own token the page uses from here on.
            try:
                body = await request.json()
            except Exception:
                body = {}
            body = body if isinstance(body, dict) else {}
            about = clean_about(body.get("about"))
            if not about["name"] or not about["title"] or not about["company"]:
                return JSONResponse({"error": "Add your name, title and company at the top."},
                                    status_code=400)
            ans = clean_answers(body.get("answers"))
            if not ans:
                return JSONResponse({"error": "Pick at least one answer first."}, status_code=400)
            new = new_request(about["company"], about["name"], about["email"], about["hire"])
            new.update(source="shared", answers=ans, status="answered", answered_at=_now(),
                       sig_name=about["name"], sig_title=about["title"],
                       sig_company=about["company"],
                       draft=build_draft(ans, _our_company(shared_owner), about["hire"]))
            add_request(shared_owner, new)
            return JSONResponse({"draft": new["draft"], "token": new["token"]})
        if req["status"] == "approved":
            return JSONResponse({"error": "Already approved. Thank you!"}, status_code=409)
        try:
            body = await request.json()
        except Exception:
            body = {}
        body = body if isinstance(body, dict) else {}
        about = clean_about(body.get("about"))
        if not about["name"] or not about["title"] or not about["company"]:
            return JSONResponse({"error": "Add your name, title and company at the top."},
                                status_code=400)
        ans = clean_answers(body.get("answers"))
        if not ans:
            return JSONResponse({"error": "Pick at least one answer first."}, status_code=400)
        hire = req.get("hire") or about["hire"]
        draft = build_draft(ans, _our_company(owner), hire)

        def _set(r):
            r.update(answers=ans, draft=draft, status="answered", answered_at=_now(),
                     sig_name=about["name"], sig_title=about["title"],
                     sig_company=about["company"])
            if about["hire"] and not r.get("hire"):
                r["hire"] = about["hire"]
            if about["email"] and not r.get("email"):
                r["email"] = about["email"]
        update(owner, token, _set)
        return JSONResponse({"draft": draft})

    @app.post("/review/{token}/approve")
    async def review_approve(token: str, request: Request):
        if _limited(request):
            return JSONResponse({"error": "Too many tries. Wait a minute and try again."},
                                status_code=429)
        owner, req = find(token)
        if not req:
            return JSONResponse({"error": "This link is no longer active."}, status_code=404)
        try:
            body = await request.json()
        except Exception:
            body = {}
        body = body if isinstance(body, dict) else {}
        quote = _clip(body.get("quote"), 1500)
        if not quote:
            return JSONResponse({"error": "The quote is empty."}, status_code=400)
        if not (req.get("sig_name") and req.get("sig_company")):
            return JSONResponse({"error": "Go back and add your name, title and company."},
                                status_code=400)

        # Clicking Approve is the OK to use it with their name (Mike,
        # 2026-11-05: no "How can we use it?" question).
        def _set(r):
            r.update(quote=quote, permission="full", status="approved", approved_at=_now())
        update(owner, token, _set)
        return JSONResponse({"ok": True})


_NOT_FOUND = """<!doctype html><html><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>Link not found</title>
<style>body{font-family:system-ui,sans-serif;background:#f5f7fa;color:#1d2733;display:flex;
min-height:100vh;align-items:center;justify-content:center;margin:0;padding:16px}
div{max-width:420px;text-align:center}</style></head><body><div><h2>This link isn't active</h2>
<p>It may have been replaced. Reply to the email you got it from and we'll send a fresh one.</p>
</div></body></html>"""

_PUBLIC_TEMPLATE = r"""<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover">
<meta name="robots" content="noindex,nofollow">
<title>A quick favor from __US__</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link href="https://fonts.googleapis.com/css2?family=Fraunces:opsz,wght@9..144,600&family=Plus+Jakarta+Sans:wght@400;500;600;700&display=swap" rel="stylesheet">
<style>
/* One calm column, like a letter; sections read as a short form, not an app. */
:root{--bg:#f4f6f8;--card:#ffffff;--ink:#16212e;--muted:#5d6b7a;--line:#dbe2e9;
--accent:#0f6e6a;--accent-soft:#e3f1ef;--warn:#b4441f;
--display:'Fraunces',Georgia,serif;--body:'Plus Jakarta Sans','Segoe UI',system-ui,sans-serif}
@media (prefers-color-scheme:dark){:root{--bg:#0f151c;--card:#16202a;--ink:#e8eef4;--muted:#93a3b3;
--line:#2a3846;--accent:#4fc1b8;--accent-soft:#163734;--warn:#f08a62;color-scheme:dark}}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--ink);font:15px/1.55 var(--body);
padding:28px max(16px,env(safe-area-inset-left)) 60px max(16px,env(safe-area-inset-right))}
.wrap{max-width:640px;margin:0 auto;display:flex;flex-direction:column;gap:18px}
.logo{height:40px;width:auto;max-width:100%;object-fit:contain;object-position:left;display:block}
h1{font:600 30px/1.15 var(--display);margin:6px 0 0;text-wrap:balance}
.lead{color:var(--muted);margin:0}
.sec{font-size:11.5px;font-weight:700;letter-spacing:.09em;text-transform:uppercase;
color:var(--accent);margin:14px 0 -6px}
.q{background:var(--card);border:1px solid var(--line);border-radius:14px;padding:18px}
.q h3{font-size:15.5px;font-weight:600;margin:0 0 4px}
.hint{font-size:12.5px;color:var(--muted);margin:0 0 10px}
.chips{display:flex;flex-wrap:wrap;gap:8px}
.chip{font:500 14px var(--body);color:var(--ink);background:var(--card);border:1.5px solid var(--line);
border-radius:999px;padding:8px 14px;cursor:pointer;text-align:left}
.chip:hover{border-color:var(--accent)}
.chip[aria-pressed="true"]{border-color:var(--accent);background:var(--accent-soft);font-weight:600}
.chip:focus-visible,button:focus-visible,textarea:focus-visible,input:focus-visible{outline:2px solid var(--accent);outline-offset:2px}
.rate{display:grid;grid-template-columns:1fr auto;gap:10px 14px;align-items:center}
.rate .lbl{font-size:14px}
.dots{display:flex;gap:6px}
.dot{width:36px;height:36px;border-radius:50%;border:1.5px solid var(--line);background:var(--card);
color:var(--ink);font:600 13px var(--body);cursor:pointer}
.dot[aria-pressed="true"]{background:var(--accent);border-color:var(--accent);color:#fff}
@media (max-width:480px){.rate{grid-template-columns:1fr}.dot{width:40px;height:40px}}
textarea,input[type=text]{width:100%;font:15px/1.5 var(--body);color:var(--ink);background:var(--card);
border:1.5px solid var(--line);border-radius:10px;padding:10px 12px}
textarea{min-height:90px;resize:vertical}
.btn{font:700 15px var(--body);background:var(--accent);color:#fff;border:0;border-radius:10px;
padding:13px 22px;cursor:pointer}
.btn[disabled]{opacity:.55;cursor:wait}
.ghost{background:none;border:0;color:var(--accent);font:600 14px var(--body);cursor:pointer;padding:6px 0}
.err{color:var(--warn);font-size:13.5px;min-height:1em}
.quote{font:600 21px/1.4 var(--display);border-left:3px solid var(--accent);padding:4px 0 4px 16px;margin:0}
.fields{display:grid;grid-template-columns:1fr 1fr;gap:10px}
@media (max-width:480px){.fields{grid-template-columns:1fr}}
.fields label{font-size:12.5px;color:var(--muted);display:flex;flex-direction:column;gap:4px}
.perm{display:flex;flex-direction:column;gap:8px}
.foot{font-size:12px;color:var(--muted);text-align:center}
[hidden]{display:none!important}
</style></head><body><main class="wrap">
<img class="logo" src="__LOGO__" alt="__US__" onerror="this.hidden=true">
<section id="s-survey" hidden>
  <h1 id="hello"></h1>
  <p class="lead">About 2 minutes, all clicks. At the end you'll see a short draft quote built from
  your answers. You edit it and approve it, and nothing is used without your OK.</p>
  <div class="q" id="about" hidden style="margin-top:8px"><h3>About you</h3>
    <p class="hint">This is how we'll credit your quote. Name, title and company are required.</p>
    <div class="fields">
      <label>Your name<input type="text" id="a-name" autocomplete="name"></label>
      <label>Title<input type="text" id="a-title" autocomplete="organization-title" placeholder="e.g. Owner, VP Operations"></label>
      <label>Company<input type="text" id="a-company" autocomplete="organization"></label>
      <label>Email (optional)<input type="text" id="a-email" autocomplete="email" inputmode="email"></label>
      <label style="grid-column:1/-1">Who you hired through us (optional)<input type="text" id="a-hire" placeholder="First name is fine"></label>
    </div></div>
  <div id="qs" style="display:flex;flex-direction:column;gap:14px;margin-top:8px"></div>
  <div class="err" id="err1"></div>
  <div><button class="btn" id="next">See my draft quote</button></div>
</section>
<section id="s-draft" hidden style="display:flex;flex-direction:column;gap:14px">
  <h1>Here's your draft</h1>
  <p class="lead">Built only from what you picked. Change anything you like, it's your quote.
  If you're OK with us using it, click Approve.</p>
  <textarea id="quote" style="min-height:150px"></textarea>
  <p class="lead" id="credit-note"></p>
  <div class="err" id="err2"></div>
  <div style="display:flex;gap:16px;align-items:center;flex-wrap:wrap">
    <button class="btn" id="approve">Approve</button>
    <button class="ghost" id="back">Back to my answers</button></div>
</section>
<section id="s-done" hidden style="display:flex;flex-direction:column;gap:14px">
  <h1>Thank you!</h1>
  <p class="lead" id="done-lead"></p>
  <p class="quote" id="done-quote"></p>
</section>
<p class="foot" id="foot">Private link for you. Questions? Just reply to the email it came in.</p>
</main>
<script>
const D = __DATA__;
const S = D.state, A = JSON.parse(JSON.stringify(S.answers || {}));
const $ = id => document.getElementById(id);
function el(tag, attrs, text){const e=document.createElement(tag);
  for(const k in (attrs||{})) e.setAttribute(k, attrs[k]); if(text!=null) e.textContent=text; return e;}
function show(id){for(const s of ['s-survey','s-draft','s-done']) $(s).hidden = (s!==id); window.scrollTo(0,0);}
function render(){
  const first = (S.contact||'').split(' ')[0];
  $('hello').textContent = (first ? first + ', a' : 'A') + ' quick favor from ' + D.us;
  $('about').hidden=false;
  for(const [id,v] of [['a-name',S.sig_name],['a-title',S.sig_title],['a-company',S.sig_company]])
    if(!$(id).value && v) $(id).value=v;
  if(S.open) $('foot').textContent='Questions? Just reply to the email this came in.';
  const box = $('qs'); box.innerHTML='';
  for(const q of D.questions){
    if(q.section) box.appendChild(el('div',{class:'sec'},q.section));
    const card = el('div',{class:'q'}); card.appendChild(el('h3',{},q.q));
    if(q.kind==='multi') card.appendChild(el('p',{class:'hint'},'Pick any that apply'));
    if(q.kind==='one'||q.kind==='multi'){
      const chips = el('div',{class:'chips',role:'group'});
      for(const [k,l] of q.opts){
        const on = q.kind==='one' ? A[q.id]===k : (A[q.id]||[]).includes(k);
        const b = el('button',{type:'button',class:'chip','aria-pressed':String(on)},l);
        b.onclick=()=>{ if(q.kind==='one'){A[q.id] = A[q.id]===k ? undefined : k;}
          else {const v=A[q.id]||[]; A[q.id]= v.includes(k)? v.filter(x=>x!==k) : v.concat([k]);}
          render(); };
        chips.appendChild(b);}
      card.appendChild(chips);
    } else if(q.kind==='rate'){
      const g = el('div',{class:'rate'}); A[q.id]=A[q.id]||{};
      for(const [k,l] of q.opts){ g.appendChild(el('div',{class:'lbl'},l));
        const dots = el('div',{class:'dots',role:'group','aria-label':l});
        for(let n=1;n<=5;n++){const b=el('button',{type:'button',class:'dot',
          'aria-pressed':String(A[q.id][k]===n),'aria-label':l+' '+n},String(n));
          b.onclick=()=>{A[q.id][k]=n; render();}; dots.appendChild(b);}
        g.appendChild(dots);}
      card.appendChild(g);
    } else {
      const t = el('textarea',{id:'own'}); t.value = A[q.id]||'';
      t.oninput=()=>{A[q.id]=t.value;}; card.appendChild(t);
    }
    box.appendChild(card);
  }
}
async function post(path, body){
  const r = await fetch('/review/'+encodeURIComponent(S.token)+path,{method:'POST',
    headers:{'Content-Type':'application/json'},body:JSON.stringify(body)});
  let j={}; try{j=await r.json();}catch(e){}
  if(!r.ok) throw new Error(j.error||'Something went wrong. Try again in a moment.');
  return j;
}
function draftView(text){
  $('quote').value = text;
  const who = [S.sig_name, S.sig_title, S.sig_company].filter(Boolean).join(', ');
  $('credit-note').textContent = who ? 'It will be credited to ' + who + '.' : '';
  show('s-draft');
}
$('next').onclick = async ()=>{
  $('err1').textContent=''; $('next').disabled=true;
  const about = {name:$('a-name').value.trim(), title:$('a-title').value.trim(),
    company:$('a-company').value.trim(), email:$('a-email').value.trim(),
    hire:$('a-hire').value.trim()};
  if(!about.name || !about.title || !about.company){
    $('err1').textContent='Add your name, title and company at the top.'; $('next').disabled=false;
    $('about').scrollIntoView({behavior:'smooth'}); return; }
  try{ const j = await post('/answers',{answers:A, about:about}); S.draft=j.draft;
    if(S.open && !S.child && j.token){ S.token=j.token; S.child=true; }
    S.sig_name=about.name; S.sig_title=about.title; S.sig_company=about.company;
    draftView(j.draft || 'Working with ' + D.us + ' has been great.'); }
  catch(e){ $('err1').textContent=e.message; }
  finally{ $('next').disabled=false; }
};
$('back').onclick=()=>show('s-survey');
$('approve').onclick = async ()=>{
  $('err2').textContent='';
  $('approve').disabled=true;
  try{ await post('/approve',{quote:$('quote').value});
    S.quote=$('quote').value; done(); }
  catch(e){ $('err2').textContent=e.message; }
  finally{ $('approve').disabled=false; }
};
function done(){
  $('done-lead').textContent = 'Your quote is approved and on its way to the ' + D.us +
    ' team. We really appreciate you taking the time.';
  $('done-quote').textContent = '“' + S.quote + '”';
  show('s-done');
}
render();
if(S.status==='approved') done();
else if(S.status==='answered' && S.draft) draftView(S.draft);
else show('s-survey');
</script></body></html>"""


# ── Owner page ───────────────────────────────────────────────────────────

def _state_attrs(s):
    for attr, default in (("_tmr_form", {}), ("_tmr_open", ""), ("_tmr_del", "")):
        if not hasattr(s, attr):
            setattr(s, attr, default)


def _css():
    from nicegui import ui
    ui.html(
        "<style>"
        ".tmr-wrap{max-width:1080px;}"
        ".tmr-new{background:var(--dd-card);border:1px solid var(--dd-border);border-radius:12px;"
        "padding:16px 18px;margin-bottom:16px;display:flex;flex-direction:column;gap:10px;}"
        ".tmr-row{display:grid;gap:10px;grid-template-columns:repeat(auto-fit,minmax(190px,1fr));}"
        ".tmr-list{display:flex;flex-direction:column;gap:10px;}"
        ".tmr-card{background:var(--dd-card);border:1px solid var(--dd-border);border-radius:12px;"
        "padding:14px 18px;display:flex;flex-direction:column;gap:8px;}"
        ".tmr-top{display:flex;justify-content:space-between;gap:12px;align-items:flex-start;flex-wrap:wrap;}"
        ".tmr-name{font-size:15px;font-weight:800;color:var(--dd-text_l);}"
        ".tmr-meta{font-size:12px;color:var(--dd-muted);}"
        ".tmr-st{font-size:11px;font-weight:700;padding:3px 10px;border-radius:999px;"
        "background:var(--dd-bg);color:var(--dd-muted);border:1px solid var(--dd-border);}"
        ".tmr-st.answered{color:var(--dd-teal);border-color:var(--dd-teal);}"
        ".tmr-st.approved{background:var(--dd-good);color:#fff;border-color:var(--dd-good);}"
        ".tmr-link{font-family:ui-monospace,Consolas,monospace;font-size:12px;color:var(--dd-text_l);"
        "background:var(--dd-bg);border:1px solid var(--dd-border);border-radius:8px;padding:6px 10px;"
        "overflow-wrap:anywhere;}"
        ".tmr-acts{display:flex;gap:8px;flex-wrap:wrap;}"
        ".tmr-mail{background:var(--dd-bg);border:1px solid var(--dd-border);border-radius:10px;"
        "padding:14px 18px;font-size:14px;line-height:1.55;color:var(--dd-text_l);max-width:720px;}"
        ".tmr-mail p{margin:0 0 10px;} .tmr-mail a{color:var(--dd-teal);font-weight:600;}"
        ".tmr-subj{font-weight:700;margin-bottom:10px;}"
        ".tmr-q{font-size:15px;line-height:1.5;color:var(--dd-text_l);border-left:3px solid var(--dd-good);"
        "padding:2px 0 2px 12px;font-style:italic;}"
        ".tmr-ans{display:grid;grid-template-columns:minmax(180px,1fr) 2fr;gap:4px 14px;font-size:12.5px;}"
        ".tmr-ans .k{color:var(--dd-muted);} .tmr-ans .v{color:var(--dd-text_l);}"
        "@media (max-width:700px){.tmr-ans{grid-template-columns:1fr;}}"
        "</style>", sanitize=False)


def public_credit(r):
    """The credit printed under a quote in a PDF or email. 'anon' never
    names the person or company."""
    if r.get("permission") == "full":
        return ", ".join(b for b in (r.get("sig_name"), r.get("sig_title"),
                                     r.get("sig_company")) if b)
    return r.get("sig_title") or "Client"


def public_quotes(owner=None, limit=2):
    """[(quote, credit)] the client approved for outside use, newest first.
    'internal' quotes never leave the Testimonials page. owner None = the
    user bound to this request. Empty when there are none."""
    try:
        reqs = load_requests(owner)
    except Exception:
        return []
    ok = [r for r in reqs if r.get("status") == "approved"
          and r.get("permission") in ("full", "anon") and (r.get("quote") or "").strip()]
    ok.sort(key=lambda r: r.get("approved_at") or "", reverse=True)
    return [(r["quote"].strip(), public_credit(r)) for r in ok[:max(0, int(limit))]]


def credit_line(r):
    perm = r.get("permission")
    if perm == "full":
        bits = [r.get("sig_name"), r.get("sig_title"), r.get("sig_company")]
        return ", ".join(b for b in bits if b)
    if perm == "anon":
        return (r.get("sig_title") or "Client") + " (no names)"
    if perm == "internal":
        return "Internal only, do not publish"
    return ""


def render_page(s, rf):
    from nicegui import ui
    ff = _ff()
    C = ff.C
    owner = (getattr(s, "_user_email", "") or "").strip().lower()
    if owner:
        try:
            ff._CURRENT_USER_EMAIL.set(owner)
        except Exception:
            pass
    _state_attrs(s)
    reqs = load_requests(owner) if owner else []
    origin = getattr(ff, "_PUBLIC_ORIGIN", "")
    try:
        rec = ff._get_user_record(owner) or {}
        sender_first = (rec.get("name") or "").split(" ")[0]
    except Exception:
        sender_first = ""
    us = _our_company(owner)

    def _copy(text, msg):
        ui.run_javascript("navigator.clipboard.writeText(%s).catch(function(){})" % json.dumps(text))
        ui.notify(msg, type="positive")

    def _copy_email(text, body_html, msg):
        # Rich copy so the survey sentence pastes as a hyperlink in Outlook
        # and Gmail; plain text where the browser refuses rich copy.
        ui.run_javascript(
            "(function(t,h){try{navigator.clipboard.write([new ClipboardItem({"
            "'text/html':new Blob([h],{type:'text/html'}),"
            "'text/plain':new Blob([t],{type:'text/plain'})})])"
            ".catch(function(){navigator.clipboard.writeText(t).catch(function(){})});}"
            "catch(e){navigator.clipboard.writeText(t).catch(function(){});}})(%s,%s)"
            % (json.dumps(text), json.dumps(body_html)))
        ui.notify(msg, type="positive")

    def _toggle(tok):
        s._tmr_open = "" if s._tmr_open == tok else tok
        rf()

    def _delete(tok):
        if s._tmr_del != tok:
            s._tmr_del = tok
            rf()
            return
        delete_request(owner, tok)
        s._tmr_del = ""
        rf()

    with ui.element("div").classes("tmr-wrap"):
        _css()
        ui.label("Testimonials").classes("fd-h1")
        ui.label("Send the email below to every client at once. They answer a 2-minute "
                 "click-through survey with no login, get a draft quote built from their "
                 "answers, edit it and approve it. Every response lands here.").classes("fd-sub")

        n_ans = sum(1 for r in reqs if r["status"] in ("answered", "approved"))
        n_ok = sum(1 for r in reqs if r["status"] == "approved")
        with ui.element("div").classes("fd-stat-strip").style("margin:14px 0;"):
            for val, lbl, col in [(n_ans, "Responses", C["teal"]),
                                  (n_ok, "Approved quotes", C["good"])]:
                with ui.element("div").classes("fd-stat-cell" + (" zero" if not val else "")):
                    ui.label(str(val)).classes("fd-sn").style(f"color:{col};")
                    ui.label(lbl).classes("fd-sl")

        stok = shared_token(owner) if owner else ""
        if stok:
            slink = public_link(origin, stok)
            subj, text, body_html = shared_email(slink, sender_first, us)
            with ui.element("div").classes("tmr-new"):
                with ui.element("div").classes("tmr-top"):
                    with ui.element("div"):
                        ui.label("Your testimonial email").style(
                            f"font-size:15px;font-weight:800;color:{C['text_l']};")
                        ui.label("Copy it into Outlook or Gmail and BCC your clients. The "
                                 "survey sentence stays a link when you paste.").classes(
                            "tmr-meta")
                    with ui.element("div").classes("tmr-acts"):
                        with ui.element("button").classes("fd-pb").props(
                                'type="button"').style("padding:7px 14px;font-size:12.5px;").on(
                                "click", lambda: _copy_email(
                                    text, body_html, "Email copied. Paste it into a new message.")):
                            ui.label("Copy email")
                        with ui.element("button").classes("fd-gb").props(
                                'type="button"').style("padding:7px 14px;font-size:12.5px;").on(
                                "click", lambda: _copy(subj, "Subject copied.")):
                            ui.label("Copy subject")
                        with ui.element("button").classes("fd-gb").props(
                                'type="button"').style("padding:7px 14px;font-size:12.5px;").on(
                                "click", lambda: _copy(slink, "Link copied.")):
                            ui.label("Copy link")
                ui.html(f'<div class="tmr-mail"><div class="tmr-subj">Subject: '
                        f'{html.escape(subj)}</div>{body_html}</div>', sanitize=False)

        if not reqs:
            ui.label("No responses yet. Each client who fills in the survey shows up here."
                     ).style(f"color:{C['muted']};font-size:13px;")
            return

        with ui.element("div").classes("tmr-list"):
            for r in reqs:
                with ui.element("div").classes("tmr-card"):
                    with ui.element("div").classes("tmr-top"):
                        with ui.element("div"):
                            ui.label(r["company"]).classes("tmr-name")
                            meta = " · ".join(x for x in (r.get("contact"), r.get("email"),
                                                          ("hired " + r["hire"]) if r.get("hire") else "",
                                                          r["created"][:10]) if x)
                            ui.label(meta).classes("tmr-meta")
                        ui.label(STATUS_LABEL.get(r["status"], r["status"])).classes(
                            "tmr-st " + r["status"])
                    if r["status"] == "approved":
                        ui.label("“" + r["quote"] + "”").classes("tmr-q")
                        ui.label(credit_line(r)).classes("tmr-meta")
                    with ui.element("div").classes("tmr-acts"):
                        def _btn(label, fn):
                            with ui.element("button").classes("fd-gb").props(
                                    'type="button"').style("padding:6px 12px;font-size:12.5px;"
                                                           ).on("click", fn):
                                ui.label(label)
                        if r["status"] == "approved":
                            _btn("Copy quote", lambda r=r: _copy(
                                f"“{r['quote']}”\n- {credit_line(r)}", "Quote copied."))
                        if r.get("answers"):
                            _btn("Hide answers" if s._tmr_open == r["token"] else "See answers",
                                 lambda t=r["token"]: _toggle(t))
                        _btn("Click again to delete" if s._tmr_del == r["token"] else "Delete",
                             lambda t=r["token"]: _delete(t))
                    if s._tmr_open == r["token"] and r.get("answers"):
                        with ui.element("div").classes("tmr-ans"):
                            for q, a in answer_lines(r["answers"]):
                                ui.label(q).classes("k")
                                ui.label(a).classes("v")
                        if r.get("draft") and r["status"] != "approved":
                            ui.label("Draft they haven't approved yet: " + r["draft"]).classes(
                                "tmr-meta")
