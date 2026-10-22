"""Structured research and funding sources for the daily run. Standard library only.

Each search returns candidate items in the same shape as data/items.jsonl,
with the record's abstract attached. Claude still writes the summary, the
thermal and manufacturing lines and the gate before merging them.

  UKRI Gateway to Research  UK grants: lead, partners, award, dates
  CORDIS                    EU Horizon projects: every partner, EU contribution
  OpenAlex                  papers with institutions and countries (needs OPENALEX_API_KEY)
  arXiv                     newest preprints
  Crossref                  journal papers with funders

Used by `heatmap.py api-search` and `heatmap.py api-orgs`. Grant amounts are the
whole award as the funder records it, not one partner's share (CORDIS also gives
each partner's EU contribution, as eu_eur).
"""
import datetime as dt
import json
import os
import re
import time
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET

TIMEOUT = 60
GTR = "https://gtr.ukri.org/gtr/api"
GTR_JSON = {"Accept": "application/vnd.rcuk.gtr.json-v7"}
SOURCES = ("gtr", "cordis", "openalex", "arxiv", "crossref")

# A record must mention one of these in its title or abstract to be kept.
# Cheap first pass; the thermal gate in config/rubric.md is still the real test.
THERMAL_HINT = re.compile(
    r"heat|thermal|cool|boil|evaporat|condens|two-phase|refrigera|chiller|radiator", re.I)

COUNTRIES = {
    "GB": "UK", "UK": "UK", "US": "USA", "DE": "Germany", "FR": "France",
    "IT": "Italy", "ES": "Spain", "NL": "Netherlands", "BE": "Belgium",
    "DK": "Denmark", "SE": "Sweden", "NO": "Norway", "FI": "Finland",
    "CH": "Switzerland", "AT": "Austria", "IE": "Ireland", "PL": "Poland",
    "PT": "Portugal", "CZ": "Czechia", "EL": "Greece", "GR": "Greece",
    "TR": "Turkey", "IL": "Israel", "CN": "China", "JP": "Japan",
    "KR": "South Korea", "IN": "India", "CA": "Canada", "AU": "Australia",
    "SG": "Singapore", "TW": "Taiwan",
}
CORDIS_TYPES = {"PRC": "Commercial", "HES": "Uni", "REC": "RTO", "PUB": "Gov", "OTH": "Other"}
OPENALEX_TYPES = {"education": "Uni", "company": "Commercial", "government": "Gov",
                  "facility": "RTO", "nonprofit": "Other", "healthcare": "Other",
                  "funder": "Gov", "archive": "Other", "other": "Other"}
LEGAL_SUFFIX = re.compile(
    r"\b(the|ltd|limited|plc|llc|inc|gmbh|ag|sas|sa|srl|spa|bv|nv|aps|ab|as|oy|co|company|"
    r"corp|corporation|uk|group|holdings)\b", re.I)


def _get(url, headers=None, parse="json"):
    req = urllib.request.Request(url, headers={"User-Agent": "heatmap-horizon-scan", **(headers or {})})
    for attempt in range(3):
        try:
            with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
                body = r.read()
            break
        except urllib.error.HTTPError as e:
            if e.code != 429 or attempt == 2:
                raise
            time.sleep(3 * (attempt + 1))   # rate limited: back off and try again
    return json.loads(body) if parse == "json" else body


def _norm(text):
    return " ".join(re.sub(r"[-_/]", " ", (text or "").lower()).split())


def has_phrase(query, text):
    """The query appears in the text as a phrase (hyphens, case and plurals ignored)."""
    q = re.escape(_norm(query.replace('"', "")))
    return re.search(rf"\b{q}(s|es)?\b", _norm(text)) is not None


def _month(ms):
    return dt.datetime.fromtimestamp(ms / 1000, dt.timezone.utc).strftime("%Y-%m") if ms else None


def _clip(text, n=900):
    text = " ".join((text or "").split())
    return text if len(text) <= n else text[:n].rsplit(" ", 1)[0] + " ..."


def _country(code):
    return COUNTRIES.get((code or "").upper(), code or None)


def org_key(name):
    """Compare organisation names across sources: case, punctuation and legal suffixes ignored."""
    s = re.sub(r"[^a-z0-9 ]+", " ", (name or "").lower().replace("&", " and "))
    return " ".join(LEGAL_SUFFIX.sub(" ", s).split())


GENERIC_TAIL = {"technologies", "technology", "systems", "engineering", "international", "solutions",
                "research", "industries", "innovations"}


def same_org(found, wanted):
    """True when two names are the same organisation, allowing a generic tail ("Iceotope Technologies")."""
    a, b = org_key(found), org_key(wanted)
    return a == b or (a.startswith(b + " ") and set(a[len(b):].split()) <= GENERIC_TAIL)


def _org_type(name):
    n = name.lower()
    if re.search(r"universit|college|school of|institute of technology", n):
        return "Uni"
    if re.search(r"\b(ltd|limited|plc|llp|inc)\b", n):
        return "Commercial"
    if re.search(r"council|ministry|department|agency|authority", n):
        return "Gov"
    return "Other"


def _tidy(name):
    """GtR stores many names in capitals; give them ordinary capitalisation."""
    if not name or not name.isupper():
        return name
    small = {"OF", "AND", "THE", "FOR", "IN", "AT"}
    words = []
    for i, w in enumerate(name.split()):
        if w in small and i:
            words.append(w.lower())
        elif len(w) <= 3 and w.isalpha() and w not in small | {"LTD"}:
            words.append(w)   # acronyms such as UK, MTC, AWE
        else:
            words.append(w.capitalize())
    return " ".join(words)


# ---------------------------------------------------------------- GtR

def _gtr_links(p):
    links = {}
    for link in (p.get("links") or {}).get("link", []):
        links.setdefault(link["rel"], []).append(link)
    return links


def _gtr_org(href):
    o = _get(href.replace("http://", "https://"), GTR_JSON)
    addr = ((o.get("addresses") or {}).get("address") or [{}])[0]
    region = addr.get("region")
    country = _country(addr.get("country")) or ("UK" if region and region not in ("Outside UK", "Unknown") else None)
    return {"name": _tidy(o.get("name")), "type": _org_type(o.get("name") or ""), "country": country}


def _gtr_project(p, area, query):
    links = _gtr_links(p)
    orgs = []
    for rel, role in (("LEAD_ORG", "lead"), ("COLLAB_ORG", "partner"), ("PARTICIPANT_ORG", "partner"),
                      ("PP_ORG", "partner")):
        for link in links.get(rel, [])[:5]:
            try:
                o = _gtr_org(link["href"])
            except (urllib.error.URLError, ValueError):
                continue
            if o["name"] and org_key(o["name"]) not in {org_key(x["name"]) for x in orgs}:
                orgs.append({**o, "role": role})
    funding = {"funder": p.get("leadFunder"), "category": p.get("grantCategory"), "status": p.get("status")}
    if links.get("FUND"):
        f = links["FUND"][0]
        funding.update(start=_month(f.get("start")), end=_month(f.get("end")))
        try:
            value = _get(f["href"].replace("http://", "https://"), GTR_JSON).get("valuePounds")
            amount = value.get("amount") if isinstance(value, dict) else value
            if amount:
                funding.update(amount=amount, currency="GBP")
        except (urllib.error.URLError, ValueError):
            pass
    ref = next((i["value"] for i in (p.get("identifiers") or {}).get("identifier", [])), None)
    funding["ref"] = ref
    return {
        "url": f"https://gtr.ukri.org/projects?ref={urllib.parse.quote(ref or p['id'])}",
        "title": p.get("title"), "publisher": "UKRI Gateway to Research", "date": funding.get("start"),
        "area": area, "kind": "grant", "source_api": "gtr", "query": query,
        "abstract": _clip(p.get("abstractText")), "orgs": orgs, "funding": funding,
    }


def gtr(query, area, since, n):
    """UK grants. GtR matches any word, so a plain phrase is quoted; results come by relevance."""
    q = urllib.parse.urlencode({"q": query if '"' in query else f'"{query}"', "f": "pro.t", "s": 100})
    projects = _get(f"{GTR}/projects?{q}", GTR_JSON).get("project", [])
    out = []
    for p in projects:
        fund = _gtr_links(p).get("FUND", [{}])[0]
        if (_month(fund.get("start")) or "") < since[:7]:
            continue
        if not THERMAL_HINT.search(f"{p.get('title')} {p.get('abstractText')}"):
            continue
        out.append(_gtr_project(p, area, query))
        if len(out) >= n:
            break
    return out


def gtr_org_projects(name, since, limit=60):
    """Recent GtR projects for one organisation. Skips organisations with more than `limit` projects."""
    q = urllib.parse.urlencode({"q": name, "f": "org.n", "s": 25})
    matches = [o for o in _get(f"{GTR}/organisations?{q}", GTR_JSON).get("organisation", [])
               if same_org(o.get("name"), name)]
    links = [link for o in matches for link in _gtr_links(o).get("PROJECT", [])]
    if len(links) > limit:
        return {"skipped": f"{len(links)} projects in GtR, too many to list"}
    out = []
    for link in links:
        p = _get(link["href"].replace("http://", "https://"), GTR_JSON)
        fund = _gtr_links(p).get("FUND", [{}])[0]
        start = _month(fund.get("start"))
        if (start or "") < since[:7]:
            continue
        lead = _gtr_links(p).get("LEAD_ORG", [{}])[0].get("href", "")
        ref = next((i["value"] for i in (p.get("identifiers") or {}).get("identifier", [])), None)
        amount = None
        if fund.get("href"):
            try:
                value = _get(fund["href"].replace("http://", "https://"), GTR_JSON).get("valuePounds")
                amount = value.get("amount") if isinstance(value, dict) else value
            except (urllib.error.URLError, ValueError):
                pass
        out.append({"source": "gtr", "ref": ref, "title": p.get("title"), "funder": p.get("leadFunder"),
                    "start": start, "end": _month(fund.get("end")), "amount": amount or None, "currency": "GBP",
                    "role": "lead" if any(o["id"] in lead for o in matches) else "partner",
                    "thermal": bool(THERMAL_HINT.search(f"{p.get('title')} {p.get('abstractText')}")),
                    "url": f"https://gtr.ukri.org/projects?ref={urllib.parse.quote(ref or p['id'])}"})
    return {"projects": sorted(out, key=lambda r: r["start"] or "", reverse=True)}


# ---------------------------------------------------------------- CORDIS

def _cordis(query):
    params = urllib.parse.urlencode({"q": query, "format": "json", "num": 20, "p": 1})
    hits = _get(f"https://cordis.europa.eu/search?{params}").get("hits", {}).get("hit", [])
    return [h["project"] for h in ([hits] if isinstance(hits, dict) else hits) if "project" in h]


def _cordis_item(p, area, query):
    orgs = (p.get("relations") or {}).get("associations", {}).get("organization", [])
    orgs = [orgs] if isinstance(orgs, dict) else orgs
    out = []
    for o in orgs:
        cat = ((o.get("relations") or {}).get("categories") or {}).get("category", {})
        cat = cat[0] if isinstance(cat, list) else cat
        attrs = o.get("@attributes", {})
        out.append({"name": _tidy(o.get("legalName") or o.get("shortName")),
                    "type": CORDIS_TYPES.get(cat.get("code"), "Other"),
                    "country": _country((o.get("address") or {}).get("country")),
                    "role": "lead" if attrs.get("type") == "coordinator" else "partner",
                    "eu_eur": float(attrs["ecContribution"]) if attrs.get("ecContribution") else None})
    out.sort(key=lambda o: (o["role"] != "lead", -(o["eu_eur"] or 0)))
    eu = p.get("ecMaxContribution")
    return {
        "url": f"https://cordis.europa.eu/project/id/{p.get('id')}",
        "title": f"{p.get('acronym')}: {p.get('title')}" if p.get("acronym") else p.get("title"),
        "publisher": "CORDIS", "date": (p.get("startDate") or "")[:7] or None,
        "area": area, "kind": "grant", "source_api": "cordis", "query": query,
        "abstract": _clip(p.get("objective") or p.get("teaser")), "orgs": out[:12],
        "funding": {"funder": "European Commission", "amount": float(eu) if eu else None, "currency": "EUR",
                    "start": (p.get("startDate") or "")[:7] or None, "end": (p.get("endDate") or "")[:7] or None,
                    "status": p.get("status"), "ref": p.get("id"), "partners": len(orgs)},
    }


def cordis(query, area, since, n):
    """EU Horizon projects. Matches the exact phrase anywhere in the record."""
    phrase = query.replace('"', "").replace("'", " ")
    q = f"contenttype='project' AND programme/code='HORIZON' AND '{phrase}'"
    out = []
    for p in _cordis(q):
        if (p.get("startDate") or "") < since or not THERMAL_HINT.search(f"{p.get('title')} {p.get('objective')}"):
            continue
        out.append(_cordis_item(p, area, query))
        if len(out) >= n:
            break
    return out


def cordis_org_projects(name, since):
    q = f"contenttype='project' AND programme/code='HORIZON' AND relations/associations/organization/legalName='{name}'"
    out = []
    for p in _cordis(q):
        if (p.get("startDate") or "") < since:
            continue
        item = _cordis_item(p, None, None)
        me = next((o for o in item["orgs"] if same_org(o["name"], name)), {})
        out.append({"source": "cordis", "ref": p.get("id"), "title": item["title"], "funder": "European Commission",
                    "start": item["funding"]["start"], "end": item["funding"]["end"],
                    "role": me.get("role", "partner"), "amount": me.get("eu_eur"), "currency": "EUR",
                    "thermal": bool(THERMAL_HINT.search(f"{p.get('title')} {p.get('objective')}")),
                    "url": item["url"]})
    return {"projects": out}


# ---------------------------------------------------------------- OpenAlex

def _abstract(inverted):
    if not inverted:
        return ""
    words = sorted((i, w) for w, places in inverted.items() for i in places)
    return " ".join(w for _, w in words)


def openalex(query, area, since, n, country=None):
    """Papers with institutions and countries. Pass country="gb" for UK work only."""
    key = os.environ.get("OPENALEX_API_KEY")
    if not key:
        raise RuntimeError("OPENALEX_API_KEY is not set in this environment")
    # Title and abstract only: plain `search` also matches full text and is too loose.
    phrase = query.replace(",", " ").replace('"', "")
    filters = [f'title_and_abstract.search:"{phrase}"', f"from_publication_date:{since}",
               "type:article|preprint|review"]
    if country:
        filters.append(f"institutions.country_code:{country}")
    params = urllib.parse.urlencode({
        "filter": ",".join(filters), "per-page": 25, "sort": "relevance_score:desc",
        "select": "id,doi,display_name,publication_date,primary_location,authorships,"
                  "abstract_inverted_index,funders,type"})
    works = _get(f"https://api.openalex.org/works?{params}", {"Authorization": f"Bearer {key}"})["results"]
    out = []
    for w in works:
        abstract = _abstract(w.get("abstract_inverted_index"))
        text = f"{w.get('display_name')} {abstract}"
        if not THERMAL_HINT.search(text) or not has_phrase(query, text):
            continue
        orgs, seen = [], set()
        for a in w.get("authorships", []):
            for i in a.get("institutions", []):
                if i.get("display_name") and i["display_name"] not in seen:
                    seen.add(i["display_name"])
                    orgs.append({"name": i["display_name"], "type": OPENALEX_TYPES.get(i.get("type"), "Other"),
                                 "country": _country(i.get("country_code")), "role": "researcher"})
        venue = ((w.get("primary_location") or {}).get("source") or {}).get("display_name")
        funders = sorted({f["display_name"] for f in w.get("funders") or [] if f.get("display_name")})
        out.append({
            "url": (w.get("doi") or w["id"]).lower(), "title": w.get("display_name"), "publisher": venue or "OpenAlex",
            "date": w.get("publication_date"), "area": area, "kind": "paper", "source_api": "openalex",
            "query": query, "abstract": _clip(abstract), "orgs": orgs[:10],
            "funding": {"funders": funders} if funders else None,
        })
        if len(out) >= n:
            break
    return out


# ---------------------------------------------------------------- arXiv

ATOM = {"a": "http://www.w3.org/2005/Atom", "arxiv": "http://arxiv.org/schemas/atom"}


def arxiv(query, area, since, n):
    """Newest preprints whose abstract has the query as a phrase."""
    q = f'abs:"{query.replace(chr(34), "")}"'
    params = urllib.parse.urlencode({"search_query": q, "max_results": 25,
                                     "sortBy": "submittedDate", "sortOrder": "descending"})
    feed = ET.fromstring(_get(f"https://export.arxiv.org/api/query?{params}", parse="raw"))
    out = []
    for e in feed.findall("a:entry", ATOM):
        date = e.findtext("a:published", "", ATOM)[:10]
        title = " ".join(e.findtext("a:title", "", ATOM).split())
        abstract = e.findtext("a:summary", "", ATOM)
        if date < since or not THERMAL_HINT.search(f"{title} {abstract}") or not has_phrase(query, f"{title} {abstract}"):
            continue
        affs = sorted({x.text for x in e.findall(".//arxiv:affiliation", ATOM) if x.text})
        authors = [a.findtext("a:name", "", ATOM) for a in e.findall("a:author", ATOM)]
        out.append({
            "url": re.sub(r"v\d+$", "", e.findtext("a:id", "", ATOM)).replace("http://", "https://"),
            "title": title, "publisher": "arXiv", "date": date, "area": area, "kind": "preprint",
            "source_api": "arxiv", "query": query, "abstract": _clip(abstract),
            "authors": authors[:6], "orgs": [{"name": a, "type": _org_type(a), "country": None,
                                              "role": "researcher"} for a in affs[:8]],
        })
        if len(out) >= n:
            break
    return out


# ---------------------------------------------------------------- Crossref


def crossref(query, area, since, n):
    """Journal papers. Relevance is rough, so the thermal hint and gate do the sorting."""
    params = urllib.parse.urlencode({
        "query.bibliographic": query.replace('"', ""), "rows": 25,
        "filter": f"from-pub-date:{since},type:journal-article",
        "select": "DOI,title,issued,container-title,author,funder,abstract"})
    items = _get(f"https://api.crossref.org/works?{params}")["message"]["items"]
    out = []
    for it in items:
        title = (it.get("title") or [""])[0]
        abstract = re.sub(r"<[^>]+>", " ", it.get("abstract") or "")
        if not THERMAL_HINT.search(f"{title} {abstract}") or not has_phrase(query, f"{title} {abstract}"):
            continue
        affs = sorted({a2["name"] for a in it.get("author", []) for a2 in a.get("affiliation", []) if a2.get("name")})
        parts = (it.get("issued") or {}).get("date-parts", [[None]])[0]
        date = "-".join(f"{p:02d}" if i else str(p) for i, p in enumerate(parts) if p) or None
        funders = sorted({f["name"] for f in it.get("funder", []) if f.get("name")})
        out.append({
            "url": f"https://doi.org/{it['DOI'].lower()}", "title": title,
            "publisher": (it.get("container-title") or ["Crossref"])[0], "date": date, "area": area,
            "kind": "paper", "source_api": "crossref", "query": query, "abstract": _clip(abstract),
            "orgs": [{"name": a[:120], "type": _org_type(a), "country": None, "role": "researcher"} for a in affs[:8]],
            "funding": {"funders": funders} if funders else None,
        })
        if len(out) >= n:
            break
    return out


SEARCH = {"gtr": gtr, "cordis": cordis, "openalex": openalex, "arxiv": arxiv, "crossref": crossref}
