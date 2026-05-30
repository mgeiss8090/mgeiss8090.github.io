#!/usr/bin/env python3
"""
build.py — Fetches data from the ORCID public API and generates a static index.html.
Run locally or via GitHub Actions.
"""

import json
import urllib.request
import urllib.error
import re
import sys
from datetime import datetime

ORCID_ID = '0000-0002-0809-2427'
API_BASE = f'https://pub.orcid.org/v3.0/{ORCID_ID}'
HEADERS  = {'Accept': 'application/json'}

# ── Helpers ──────────────────────────────────────────────────────────────────

def fetch(path):
    url = API_BASE + path
    req = urllib.request.Request(url, headers=HEADERS)
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            return json.loads(r.read().decode())
    except Exception as e:
        print(f'  Warning: could not fetch {path}: {e}', file=sys.stderr)
        return None

def esc(s):
    """Minimal HTML escaping."""
    if not s:
        return ''
    return (str(s)
        .replace('&', '&amp;')
        .replace('<', '&lt;')
        .replace('>', '&gt;')
        .replace('"', '&quot;'))

def years(start, end):
    s = (start or {}).get('year', {}).get('value', '')
    e = (end   or {}).get('year', {}).get('value', '')
    if not s:
        return ''
    return f'{s}–{e}' if e else f'{s}–'

# ── Fetch all data ────────────────────────────────────────────────────────────

print('Fetching ORCID data...')

d_edu        = fetch('/educations')    or {}
d_qual       = fetch('/qualifications') or {}
d_emp        = fetch('/employments')   or {}
d_kw         = fetch('/keywords')      or {}
d_urls       = fetch('/researcher-urls') or {}
d_works      = fetch('/works')         or {}
d_fundings   = fetch('/fundings')      or {}

# ── Education ─────────────────────────────────────────────────────────────────

def extract_affiliations(data, summary_key):
    return [
        s[summary_key]
        for g in (data.get('affiliation-group') or [])
        for s in (g.get('summaries') or [])
        if s.get(summary_key)
    ]

edu_items = (
    extract_affiliations(d_edu,  'education-summary') +
    extract_affiliations(d_qual, 'qualification-summary')
)
edu_items.sort(key=lambda e: int(
    (e.get('end-date') or e.get('start-date') or {}).get('year', {}).get('value', 0) or 0
), reverse=True)

def render_cv_rows(items):
    if not items:
        return '<tr><td colspan="2" style="color:var(--ink-faint);padding:1rem 0;font-size:.85rem;">Keine Einträge in ORCID.</td></tr>'
    rows = []
    for e in items:
        org  = esc(e.get('organization', {}).get('name', ''))
        dept = esc(e.get('department-name', '') or '')
        org_full = f'{org}, {dept}' if dept else org
        rows.append(f'''<tr>
          <td>{esc(years(e.get("start-date"), e.get("end-date")))}</td>
          <td><strong>{esc(e.get("role-title", ""))}</strong>
          <em>{org_full}</em></td>
        </tr>''')
    return '\n'.join(rows)

education_html   = render_cv_rows(edu_items)

# ── Employment ────────────────────────────────────────────────────────────────

emp_items = [
    s['employment-summary']
    for g in (d_emp.get('affiliation-group') or [])
    for s in (g.get('summaries') or [])
    if s.get('employment-summary')
]
emp_items.sort(key=lambda e: e.get('end-date', {}).get('year', {}).get('value', '9999') if e.get('end-date') else '9999', reverse=True)
employment_html = render_cv_rows(emp_items)

# ── Keywords ──────────────────────────────────────────────────────────────────

kws = [k['content'] for k in (d_kw.get('keyword') or []) if k.get('content')]
if kws:
    keywords_html = '<div class="keyword-cloud">' + ''.join(f'<span class="keyword">{esc(k)}</span>' for k in kws) + '</div>'
    keywords_section_style = ''
else:
    keywords_html = ''
    keywords_section_style = 'display:none;'

# ── Researcher URLs ───────────────────────────────────────────────────────────

urls = d_urls.get('researcher-url') or []
if urls:
    urls_html  = '<br>'.join(
        f'<a href="{esc(u.get("url", {}).get("value", ""))}" target="_blank" rel="noopener">'
        f'{esc(u.get("url-name") or u.get("url", {}).get("value", ""))} →</a>'
        for u in urls
    )
    urls_card_style = ''
else:
    urls_html       = ''
    urls_card_style = 'display:none;'

# ── Publications ──────────────────────────────────────────────────────────────

TYPE_MAP = {
    'book':              {'key': 'book',         'de': 'Buch',                 'en': 'Book'},
    'edited-book':       {'key': 'edited',       'de': 'Herausgeberband',      'en': 'Edited Volume'},
    'journal-article':   {'key': 'article',      'de': 'Zeitschriftenartikel', 'en': 'Journal Article'},
    'journal-issue':     {'key': 'specialissue', 'de': 'Themenheft',           'en': 'Special Issue'},
    'book-chapter':      {'key': 'chapter',      'de': 'Buchkapitel',          'en': 'Book Chapter'},
    'conference-paper':  {'key': 'chapter',      'de': 'Konferenzbeitrag',     'en': 'Conference Paper'},
    'report':            {'key': 'report',       'de': 'Bericht',              'en': 'Report'},
    'working-paper':     {'key': 'report',       'de': 'Working Paper',        'en': 'Working Paper'},
    'dissertation':      {'key': 'book',         'de': 'Dissertation',         'en': 'Dissertation'},
    'magazine-article':  {'key': 'other',        'de': 'Magazinartikel',       'en': 'Magazine Article'},
    'newspaper-article': {'key': 'other',        'de': 'Zeitungsartikel',      'en': 'Newspaper Article'},
    'book-review':       {'key': 'other',        'de': 'Rezension',            'en': 'Book Review'},
    'review':            {'key': 'other',        'de': 'Rezension',            'en': 'Review'},
    'online-resource':   {'key': 'other',        'de': 'Online-Ressource',     'en': 'Online Resource'},
    'lecture-speech':    {'key': 'other',        'de': 'Vortrag',              'en': 'Lecture / Speech'},
    'translation':       {'key': 'other',        'de': 'Übersetzung',          'en': 'Translation'},
    'other':             {'key': 'other',        'de': 'Sonstiges',            'en': 'Other'},
    'undefined':         {'key': 'other',        'de': 'Sonstiges',            'en': 'Other'},
}

def map_type(t):
    key = (t or '').lower().replace('_', '-')
    return TYPE_MAP.get(key, {'key': 'other', 'de': t or 'Sonstiges', 'en': t or 'Other'})

groups = d_works.get('group') or []
works = []
for g in groups:
    summaries = g.get('work-summary') or []
    best = next((s for s in summaries if s.get('title')), summaries[0] if summaries else None)
    if best:
        works.append(best)

works.sort(key=lambda w: int((w.get('publication-date') or {}).get('year', {}).get('value', 0) or 0), reverse=True)
pub_count = len(works)

by_year = {}
for w in works:
    y = (w.get('publication-date') or {}).get('year', {}).get('value') or 'n.d.'
    by_year.setdefault(y, []).append(w)

pub_items_html = []
for year in sorted(by_year.keys(), key=lambda y: y if y == 'n.d.' else y, reverse=True):
    pub_items_html.append(f'<div class="pub-year-group"><div class="pub-year">{esc(year)}</div>')
    for w in by_year[year]:
        title     = esc(w.get('title', {}).get('title', {}).get('value', '') or '(Kein Titel)')
        type_info = map_type(w.get('type'))
        ext_ids   = (w.get('external-ids') or {}).get('external-id') or []
        doi_entry = next((e for e in ext_ids if e.get('external-id-type') == 'doi'), None)
        doi_url   = f'https://doi.org/{doi_entry["external-id-value"]}' if doi_entry else None
        title_html = f'<a href="{esc(doi_url)}" target="_blank" rel="noopener">{title}</a>' if doi_url else title
        journal = esc((w.get('journal-title') or {}).get('value', '') or '')
        journal_html = f'<div class="pub-meta">{journal}</div>' if journal else ''
        pub_items_html.append(f'''<div class="pub-item" data-type="{esc(type_info["key"])}">
          <div class="pub-bar"></div>
          <div>
            <div class="pub-title">{title_html}</div>
            {journal_html}
            <span class="pub-type-tag de">{esc(type_info["de"])}</span>
            <span class="pub-type-tag en">{esc(type_info["en"])}</span>
          </div>
        </div>''')
    pub_items_html.append('</div>')

publications_html = '\n'.join(pub_items_html) if pub_items_html else '<p style="color:var(--ink-faint);font-style:italic;">Keine Publikationen gefunden.</p>'

# ── Funding ───────────────────────────────────────────────────────────────────

FUNDING_TYPE_LABELS = {
    'grant':    {'de': 'Grant',        'en': 'Grant'},
    'contract': {'de': 'Auftrag',      'en': 'Contract'},
    'award':    {'de': 'Auszeichnung', 'en': 'Award'},
    'salary':   {'de': 'Stipendium',   'en': 'Salary'},
    'other':    {'de': 'Sonstiges',    'en': 'Other'},
}

funding_summaries = [
    s
    for g in (d_fundings.get('group') or [])
    for s in (g.get('funding-summary') or [])
    if s
]
funding_summaries.sort(key=lambda s: int(
    (s.get('end-date') or s.get('start-date') or {}).get('year', {}).get('value', 0) or 0
), reverse=True)

print(f'  Fetching {len(funding_summaries)} funding details...')
funding_cards_html = []
for s in funding_summaries:
    put_code  = s.get('put-code')
    detail    = fetch(f'/funding/{put_code}') if put_code else None
    title     = esc(s.get('title', {}).get('title', {}).get('value', '') or '(Kein Titel)')
    type_key  = (s.get('type') or 'other').lower()
    type_label = FUNDING_TYPE_LABELS.get(type_key, FUNDING_TYPE_LABELS['other'])
    funder    = esc(s.get('organization', {}).get('name', '') or '')
    ext_url = ((detail or {}).get('url') or {}).get('value') if detail else None
    href      = esc(ext_url or f'https://orcid.org/{ORCID_ID}')
    funder_html = f'<div class="project-funder">{funder}</div>' if funder else ''
    funding_cards_html.append(f'''<div class="project-card">
        <div class="project-type-band" data-type="{esc(type_key)}">
          <span class="de">{esc(type_label["de"])}</span>
          <span class="en">{esc(type_label["en"])}</span>
        </div>
        <div class="project-body">
          <h3 class="project-title">{title}</h3>
          {funder_html}
          <a class="project-link" href="{href}" target="_blank" rel="noopener">
            <span class="de">Mehr erfahren →</span>
            <span class="en">Read more →</span>
          </a>
        </div>
      </div>''')

funding_html = '\n'.join(funding_cards_html) if funding_cards_html else '<p style="color:var(--ink-faint);font-style:italic;">Keine Einträge in ORCID.</p>'

# ── Research years ────────────────────────────────────────────────────────────

research_years = str(datetime.now().year - 2013) + '+'

# ── Build timestamp ───────────────────────────────────────────────────────────

build_date = datetime.utcnow().strftime('%Y-%m-%d %H:%M UTC')

# ── Assemble HTML ─────────────────────────────────────────────────────────────

html = f'''<!DOCTYPE html>
<html lang="de">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <link rel="canonical" href="https://michaelgeiss.net">
  <title>Michael Geiss</title>

  <!-- SEO: Meta-Tags -->
  <meta name="description" content="Michael Geiss – Professor für Erziehungswissenschaft an der Pädagogischen Hochschule Zürich. Forschung zu Bildungsgeschichte, Technologie und Governance.">
  <meta name="author" content="Michael Geiss">
  <meta name="robots" content="index, follow">

  <!-- SEO: Open Graph -->
  <meta property="og:title" content="Michael Geiss – Professor of Education">
  <meta property="og:description" content="Research at the intersection of history of education, technology, and governance.">
  <meta property="og:type" content="profile">
  <meta property="og:url" content="https://michaelgeiss.net">
  <meta property="og:image" content="https://michaelgeiss.net/comput_semantic_net.gif">

  <!-- SEO: Strukturierte Daten -->
  <script type="application/ld+json">
  {{
    "@context": "https://schema.org",
    "@type": "Person",
    "name": "Michael Geiss",
    "jobTitle": "Professor of Education",
    "affiliation": {{
      "@type": "Organization",
      "name": "Pädagogische Hochschule Zürich"
    }},
    "email": "michael.geiss@gmail.com",
    "sameAs": ["https://orcid.org/0000-0002-0809-2427"]
  }}
  </script>

  <link rel="preconnect" href="https://fonts.googleapis.com">
  <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
  <link href="https://fonts.googleapis.com/css2?family=Libre+Baskerville:ital,wght@0,400;0,700;1,400&family=DM+Sans:opsz,wght@9..40,300;9..40,400;9..40,500&display=swap" rel="stylesheet">

  <style>
    :root {{
      --ink: #1a1a1a;
      --ink-light: #555;
      --ink-faint: #999;
      --accent: #2c4a6e;
      --accent-warm: #8b6348;
      --accent-green: #4a6e52;
      --bg: #faf9f6;
      --bg-warm: #f3f0eb;
      --rule: #d8d3cb;
      --serif: 'Libre Baskerville', Georgia, serif;
      --sans: 'DM Sans', system-ui, sans-serif;
    }}
    *, *::before, *::after {{ box-sizing: border-box; margin: 0; padding: 0; }}
    html {{ scroll-behavior: smooth; }}
    body {{
      font-family: var(--sans);
      background: var(--bg);
      color: var(--ink);
      font-size: 15px;
      line-height: 1.7;
      font-weight: 300;
    }}

    /* LANGUAGE BAR */
    .lang-bar {{
      position: fixed; top: 0; left: 0; right: 0; z-index: 100;
      background: rgba(250,249,246,0.95);
      border-bottom: 1px solid var(--rule);
      display: flex; justify-content: flex-end;
      padding: 0.55rem 2rem; gap: 0.6rem;
      backdrop-filter: blur(10px);
    }}
    .lang-btn {{
      font-family: var(--sans); font-size: 0.7rem; font-weight: 500;
      letter-spacing: 0.12em; text-transform: uppercase;
      background: none; border: 1px solid var(--rule);
      padding: 0.2rem 0.7rem; cursor: pointer;
      color: var(--ink-light); border-radius: 2px; transition: all 0.2s;
    }}
    .lang-btn.active, .lang-btn:hover {{ background: var(--accent); border-color: var(--accent); color: #fff; }}

    /* LAYOUT */
    .page-wrap {{ max-width: 900px; margin: 0 auto; padding: 0 2rem; }}

    /* HERO */
    .hero {{
      padding: 7.5rem 0 3.5rem;
      display: grid; grid-template-columns: 1fr 1fr;
      gap: 2rem; align-items: center;
      border-bottom: 1px solid var(--rule);
    }}
    .hero-name {{
      font-family: var(--serif);
      font-size: clamp(2.2rem, 5vw, 3.4rem);
      font-weight: 700; line-height: 1.1; letter-spacing: -0.02em;
    }}
    .hero-title {{
      font-family: var(--serif); font-style: italic;
      font-size: 1.05rem; color: var(--accent);
      margin-top: 0.55rem; line-height: 1.5;
    }}
    .hero-meta {{ margin-top: 1.2rem; display: flex; flex-direction: column; gap: 0.25rem; }}
    .hero-meta span {{ font-size: 0.82rem; color: var(--ink-light); }}
    .hero-meta strong {{ font-weight: 500; color: var(--ink); }}
    .hero-orcid {{
      margin-top: 1rem; display: inline-flex; align-items: center; gap: 0.5rem;
      font-size: 0.75rem; color: var(--ink-faint); text-decoration: none;
      border: 1px solid var(--rule); padding: 0.3rem 0.8rem; border-radius: 2px;
      transition: all 0.2s;
    }}
    .hero-orcid:hover {{ border-color: #a6ce39; color: #4c7a1e; }}
    .hero-orcid svg {{ width: 16px; height: 16px; }}
    .hero-image {{ display: flex; align-items: center; justify-content: center; min-width: 0; }}
    .hero-image img {{
      width: clamp(200px, 35vw, 380px);
      max-height: 340px;
      object-fit: contain;
      mix-blend-mode: multiply;
      display: block;
    }}

    /* NAV */
    .site-nav {{
      position: sticky; top: 36px; z-index: 90;
      background: rgba(250,249,246,0.95); border-bottom: 1px solid var(--rule);
      backdrop-filter: blur(10px);
      overflow-x: auto;
    }}
    .site-nav ul {{ display: flex; list-style: none; min-width: max-content; }}
    .site-nav a {{
      display: block; padding: 0.85rem 1.1rem;
      font-size: 0.76rem; font-weight: 500;
      letter-spacing: 0.08em; text-transform: uppercase;
      color: var(--ink-light); text-decoration: none;
      border-bottom: 2px solid transparent; transition: all 0.2s;
      white-space: nowrap;
    }}
    .site-nav a:hover {{ color: var(--accent); border-bottom-color: var(--accent); }}

    /* SECTIONS */
    section {{ padding: 3.5rem 0; border-bottom: 1px solid var(--rule); }}
    section:last-child {{ border-bottom: none; }}
    .section-label {{
      font-size: 0.67rem; font-weight: 500; letter-spacing: 0.18em; text-transform: uppercase;
      color: var(--accent-warm); margin-bottom: 1.6rem;
      display: flex; align-items: center; gap: 0.75rem;
    }}
    .section-label::after {{ content: ''; flex: 1; height: 1px; background: var(--rule); }}
    .section-heading {{
      font-family: var(--serif); font-size: 1.5rem; font-weight: 700;
      margin-bottom: 1.4rem; line-height: 1.25;
    }}

    /* CV TABLE */
    .cv-table {{ width: 100%; border-collapse: collapse; }}
    .cv-table tr {{ border-bottom: 1px solid var(--rule); }}
    .cv-table tr:last-child {{ border-bottom: none; }}
    .cv-table td {{ padding: 0.9rem 0; vertical-align: top; }}
    .cv-table td:first-child {{
      width: 130px; font-size: 0.76rem; color: var(--ink-faint);
      padding-right: 1.5rem; padding-top: 1rem;
      font-variant-numeric: tabular-nums; white-space: nowrap;
    }}
    .cv-table td:nth-child(2) {{ color: var(--ink); }}
    .cv-table td:nth-child(2) em {{
      font-family: var(--serif); font-style: italic;
      color: var(--ink-light); font-size: 0.88rem; display: block; margin-top: 0.15rem;
    }}

    /* KEYWORDS */
    .keyword-cloud {{ display: flex; flex-wrap: wrap; gap: 0.5rem; margin-top: 0.5rem; }}
    .keyword {{
      font-size: 0.78rem; background: var(--bg-warm);
      border: 1px solid var(--rule); padding: 0.25rem 0.75rem;
      border-radius: 2px; color: var(--ink-light);
    }}

    /* PUBLICATIONS */
    .pub-filters {{ display: flex; gap: 0.5rem; flex-wrap: wrap; margin-bottom: 2rem; }}
    .pub-filter {{
      font-family: var(--sans); font-size: 0.7rem; font-weight: 500;
      letter-spacing: 0.08em; text-transform: uppercase;
      background: none; border: 1px solid var(--rule);
      padding: 0.28rem 0.85rem; cursor: pointer;
      color: var(--ink-light); border-radius: 2px; transition: all 0.2s;
    }}
    .pub-filter.active, .pub-filter:hover {{ background: var(--accent); border-color: var(--accent); color: #fff; }}
    .pub-year-group {{ margin-bottom: 2rem; }}
    .pub-year {{
      font-size: 0.8rem; font-weight: 500; color: var(--ink-faint);
      border-bottom: 1px solid var(--rule); padding-bottom: 0.35rem; margin-bottom: 0.8rem;
    }}
    .pub-item {{
      display: grid; grid-template-columns: 4px 1fr;
      gap: 1rem; padding: 0.85rem 0; border-bottom: 1px solid var(--bg-warm);
    }}
    .pub-item:last-child {{ border-bottom: none; }}
    .pub-bar {{ width: 3px; border-radius: 2px; margin-top: 4px; background: var(--rule); }}
    .pub-item[data-type="book"] .pub-bar {{ background: var(--accent); }}
    .pub-item[data-type="article"] .pub-bar {{ background: var(--accent-warm); }}
    .pub-item[data-type="chapter"] .pub-bar {{ background: var(--accent-green); }}
    .pub-item[data-type="edited"] .pub-bar {{ background: #6a5acd; }}
    .pub-item[data-type="specialissue"] .pub-bar {{ background: #b8860b; }}
    .pub-item[data-type="report"] .pub-bar {{ background: #888; }}
    .pub-item[data-type="other"] .pub-bar {{ background: #b0a090; }}
    .pub-title {{
      font-family: var(--serif); font-style: italic;
      font-size: 0.95rem; color: var(--ink); line-height: 1.45;
    }}
    .pub-title a {{
      color: inherit; text-decoration: none;
      border-bottom: 1px solid var(--rule); transition: border-color 0.2s;
    }}
    .pub-title a:hover {{ border-bottom-color: var(--accent); }}
    .pub-meta {{ font-size: 0.8rem; color: var(--ink-faint); margin-top: 0.2rem; }}
    .pub-type-tag {{
      display: inline-block; font-size: 0.63rem; font-weight: 500;
      letter-spacing: 0.1em; text-transform: uppercase;
      padding: 0.12rem 0.45rem; border-radius: 2px; margin-top: 0.35rem;
      background: var(--bg-warm); color: var(--ink-faint);
    }}

    /* PROJECTS */
    .projects-grid {{
      display: grid;
      grid-template-columns: repeat(auto-fill, minmax(260px, 1fr));
      gap: 1.5rem;
      margin-top: 0.5rem;
    }}
    .project-card {{
      border: 1px solid var(--rule);
      border-radius: 4px;
      overflow: hidden;
      background: var(--bg);
      display: flex;
      flex-direction: column;
      transition: box-shadow 0.2s;
    }}
    .project-card:hover {{ box-shadow: 0 2px 12px rgba(0,0,0,0.07); }}
    .project-type-band {{
      padding: 0.55rem 1.4rem;
      font-size: 0.68rem;
      font-weight: 500;
      letter-spacing: 0.14em;
      text-transform: uppercase;
      color: var(--ink-faint);
      border-left: 3px solid var(--rule);
      background: none;
    }}
    .project-type-band[data-type="grant"]    {{ border-left-color: var(--accent-green); color: var(--accent-green); }}
    .project-type-band[data-type="contract"] {{ border-left-color: #7a9e7e; color: #7a9e7e; }}
    .project-type-band[data-type="award"]    {{ border-left-color: #a0956e; color: #a0956e; }}
    .project-type-band[data-type="salary"]   {{ border-left-color: #7a8e7a; color: #7a8e7a; }}
    .project-type-band[data-type="other"]    {{ border-left-color: #a09080; color: #a09080; }}
    .project-body {{
      padding: 1.2rem 1.4rem;
      display: flex;
      flex-direction: column;
      flex: 1;
    }}
    .project-title {{
      font-family: var(--serif);
      font-size: 1rem;
      font-weight: 700;
      margin-bottom: 0.6rem;
      line-height: 1.3;
    }}
    .project-funder {{
      font-size: 0.82rem;
      color: var(--ink-light);
      margin-bottom: 0.4rem;
    }}
    .project-link {{
      display: inline-block;
      margin-top: 1rem;
      font-size: 0.78rem;
      font-weight: 500;
      color: var(--accent);
      text-decoration: none;
      letter-spacing: 0.03em;
    }}
    .project-link:hover {{ text-decoration: underline; }}

    /* CONTACT */
    .contact-grid {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(200px,1fr)); gap: 1.2rem; margin-top: 0.5rem; }}
    .contact-card {{ background: var(--bg-warm); border: 1px solid var(--rule); border-radius: 4px; padding: 1.2rem 1.4rem; }}
    .contact-card--stats {{ background: var(--bg-warm); }}
    .stats-row {{ display: flex; flex-direction: column; gap: 1.5rem; }}
    .stats-row > div {{ display: flex; flex-direction: column; }}
    .stat-num {{
      font-family: var(--serif); font-size: 1.9rem; font-weight: 700;
      color: var(--accent); line-height: 1;
    }}
    .stat-label {{
      font-size: 0.68rem; letter-spacing: 0.1em; text-transform: uppercase;
      color: var(--ink-faint); margin-top: 0.2rem;
    }}
    .contact-card-label {{ font-size: 0.66rem; font-weight: 500; letter-spacing: 0.12em; text-transform: uppercase; color: var(--ink-faint); margin-bottom: 0.4rem; }}
    .contact-card-value {{ font-size: 0.88rem; color: var(--ink); }}
    .contact-card-value a {{ color: var(--accent); text-decoration: none; }}
    .contact-card-value a:hover {{ text-decoration: underline; }}

    /* FOOTER */
    footer {{ padding: 2.5rem 0; text-align: center; font-size: 0.73rem; color: var(--ink-faint); }}

    /* LANG */
    body.lang-en .de {{ display: none; }}
    body.lang-de .en {{ display: none; }}

    @media (max-width: 640px) {{
      .hero {{ grid-template-columns: 1fr; gap: 1.5rem; }}
      .hero-image {{ display: none; }}
      .page-wrap {{ padding: 0 1.2rem; }}
      .cv-table td:first-child {{ width: 90px; }}
    }}
  </style>
</head>
<body class="lang-en">

<div class="lang-bar">
  <button class="lang-btn active" onclick="setLang('de')" id="btn-de">DE</button>
  <button class="lang-btn" onclick="setLang('en')" id="btn-en">EN</button>
</div>

<div class="page-wrap">

  <header class="hero">
    <div>
      <h1 class="hero-name">Michael Geiss</h1>
      <p class="hero-title de">Professor für Erziehungswissenschaft</p>
      <p class="hero-title en">Professor of Education</p>
      <div class="hero-meta">
        <span class="de"><strong>Derzeitige Position:</strong> Leiter Zentrum Bildung und Digitaler Wandel &amp; Professor für Erziehungswissenschaft</span>
        <span class="en"><strong>Current Position:</strong> Head of the Centre for Education and Digital Transformation &amp; Professor of Education</span>
        <span><strong>Pädagogische Hochschule Zürich</strong></span>
      </div>
      <a class="hero-orcid" href="https://orcid.org/0000-0002-0809-2427" target="_blank" rel="noopener">
        <svg viewBox="0 0 256 256" fill="#a6ce39"><path d="M128 0C57.3 0 0 57.3 0 128s57.3 128 128 128 128-57.3 128-128S198.7 0 128 0zm-16.3 64.4h-17V192h17V64.4zm34.6 0h-17.6l-.1 127.6H147c37.4 0 63.5-25.4 63.5-63.8 0-40.2-26-63.8-64.2-63.8zm-.8 111.2h-0.4V80.8h.4c28.8 0 47.3 17.8 47.3 47.4 0 29.9-18.5 47.4-47.3 47.4z"/></svg>
        ORCID 0000-0002-0809-2427
      </a>
    </div>
    <div class="hero-image">
      <img src="comput_semantic_net.gif" alt="Publikationsnetzwerk" />
    </div>
  </header>

  <nav class="site-nav">
    <ul>
      <li><a href="#vita"><span class="de">Vita</span><span class="en">Vita</span></a></li>
      <li><a href="#forschung"><span class="de">Forschung</span><span class="en">Research</span></a></li>
      <li><a href="#publikationen"><span class="de">Publikationen</span><span class="en">Publications</span></a></li>
      <li><a href="#projekte"><span class="de">Projekte</span><span class="en">Projects</span></a></li>
      <li><a href="#kontakt"><span class="de">Kontakt</span><span class="en">Contact</span></a></li>
    </ul>
  </nav>

  <section id="vita">
    <div class="section-label de">Akademische Laufbahn</div>
    <div class="section-label en">Academic Career</div>

    <h2 class="section-heading de">Ausbildung</h2>
    <h2 class="section-heading en">Education</h2>
    <table class="cv-table">
      {education_html}
    </table>

    <h2 class="section-heading de" style="margin-top:2.5rem;">Anstellungen</h2>
    <h2 class="section-heading en" style="margin-top:2.5rem;">Employment</h2>
    <table class="cv-table">
      {employment_html}
    </table>
  </section>

  <section id="forschung">
    <div class="section-label de">Schwerpunkte</div>
    <div class="section-label en">Focus Areas</div>
    <h2 class="section-heading de">Forschung</h2>
    <h2 class="section-heading en">Research</h2>
    <p class="de" style="font-family:var(--serif);font-style:italic;color:var(--ink-light);font-size:1rem;line-height:1.8;max-width:640px;">
      Meine Forschung bewegt sich an der Schnittstelle von Bildungsgeschichte, Technologieentwicklung und Educational Governance. Besonders interessiere ich mich für die Rolle nichtstaatlicher Akteure im Bildungswesen.
    </p>
    <p class="en" style="font-family:var(--serif);font-style:italic;color:var(--ink-light);font-size:1rem;line-height:1.8;max-width:640px;">
      My research lies at the intersection of educational history, technology development, and governance, with a focus on the role of non-state actors in public education.
    </p>
    <div id="keywords-section" style="margin-top:1.5rem;{keywords_section_style}">
      <p style="font-size:0.75rem;letter-spacing:0.1em;text-transform:uppercase;color:var(--ink-faint);margin-bottom:0.75rem;" class="de">Schlagwörter aus ORCID</p>
      <p style="font-size:0.75rem;letter-spacing:0.1em;text-transform:uppercase;color:var(--ink-faint);margin-bottom:0.75rem;" class="en">Keywords from ORCID</p>
      {keywords_html}
    </div>
  </section>

  <section id="publikationen">
    <div class="section-label de">Schriften</div>
    <div class="section-label en">Writings</div>
    <h2 class="section-heading de">Publikationen</h2>
    <h2 class="section-heading en">Publications</h2>
    <div class="pub-filters">
      <button class="pub-filter active" onclick="filterPubs('all')" data-filter="all">
        <span class="de">Alle</span><span class="en">All</span>
      </button>
      <button class="pub-filter" onclick="filterPubs('book')" data-filter="book">
        <span class="de">Bücher und Herausgeberbände</span><span class="en">Books and Edited Volumes</span>
      </button>
      <button class="pub-filter" onclick="filterPubs('specialissue')" data-filter="specialissue">
        <span class="de">Thementeile</span><span class="en">Special Issues</span>
      </button>
      <button class="pub-filter" onclick="filterPubs('article')" data-filter="article">
        <span class="de">Artikel</span><span class="en">Articles</span>
      </button>
      <button class="pub-filter" onclick="filterPubs('chapter')" data-filter="chapter">
        <span class="de">Buchkapitel</span><span class="en">Chapters</span>
      </button>
      <button class="pub-filter" onclick="filterPubs('report')" data-filter="report">
        <span class="de">Berichte</span><span class="en">Reports</span>
      </button>
      <button class="pub-filter" onclick="filterPubs('other')" data-filter="other">
        <span class="de">Andere</span><span class="en">Other</span>
      </button>
    </div>
    <div id="publications-list">
      {publications_html}
    </div>
  </section>

  <section id="projekte">
    <div class="section-label de">Drittmittel &amp; Förderung</div>
    <div class="section-label en">Funding</div>
    <h2 class="section-heading de">Projekte</h2>
    <h2 class="section-heading en">Projects</h2>
    <div class="projects-grid">
      {funding_html}
    </div>
  </section>

  <section id="kontakt">
    <div class="section-label de">Erreichbarkeit</div>
    <div class="section-label en">Get in Touch</div>
    <h2 class="section-heading de">Kontakt</h2>
    <h2 class="section-heading en">Contact</h2>
    <div class="contact-grid">
      <div class="contact-card contact-card--stats">
        <div class="stats-row">
          <div>
            <span class="stat-num">{pub_count}</span>
            <span class="stat-label de">Publikationen</span>
            <span class="stat-label en">Publications</span>
          </div>
          <div>
            <span class="stat-num">{research_years}</span>
            <span class="stat-label de">Jahre Forschung</span>
            <span class="stat-label en">Years Research</span>
          </div>
        </div>
      </div>
      <div class="contact-card">
        <div class="contact-card-label de">Institution</div>
        <div class="contact-card-label en">Institution</div>
        <div class="contact-card-value">Pädagogische Hochschule Zürich<br>Zentrum Bildung und Digitaler Wandel</div>
      </div>
      <div class="contact-card">
        <div class="contact-card-label de">E-Mail</div>
        <div class="contact-card-label en">Email</div>
        <div class="contact-card-value"><a href="mailto:michael.geiss@gmail.com">michael.geiss@gmail.com</a></div>
      </div>
      <div class="contact-card">
        <div class="contact-card-label">ORCID</div>
        <div class="contact-card-value">
          <a href="https://orcid.org/0000-0002-0809-2427" target="_blank" rel="noopener">0000-0002-0809-2427 →</a>
        </div>
      </div>
      <div class="contact-card" style="{urls_card_style}">
        <div class="contact-card-label de">Weitere Profile</div>
        <div class="contact-card-label en">Further Profiles</div>
        <div class="contact-card-value">{urls_html}</div>
      </div>
    </div>
  </section>

</div>

<footer>
  <p>© {datetime.now().year} Michael Geiss ·
    <a href="/impressum.html" style="color:inherit;">Impressum</a> ·
    <span class="de">Daten via</span><span class="en">Data via</span>
    <a href="https://orcid.org/0000-0002-0809-2427" target="_blank" rel="noopener" style="color:inherit;">ORCID API</a>
    · <span style="color:var(--ink-faint);">Built {build_date}</span>
  </p>
</footer>

<script>
function setLang(lang) {{
  document.body.className = 'lang-' + lang;
  document.getElementById('btn-de').classList.toggle('active', lang === 'de');
  document.getElementById('btn-en').classList.toggle('active', lang === 'en');
  localStorage.setItem('lang', lang);
}}
setLang(localStorage.getItem('lang') || 'en');

function filterPubs(type) {{
  document.querySelectorAll('.pub-filter').forEach(b => b.classList.toggle('active', b.dataset.filter === type));
  document.querySelectorAll('.pub-item').forEach(i => {{ i.style.display = (type === 'all' || i.dataset.type === type) ? '' : 'none'; }});
  document.querySelectorAll('.pub-year-group').forEach(g => {{
    g.style.display = [...g.querySelectorAll('.pub-item')].some(i => i.style.display !== 'none') ? '' : 'none';
  }});
}}
</script>
</body>
</html>'''

with open('index.html', 'w', encoding='utf-8') as f:
    f.write(html)

print(f'Done. index.html written ({pub_count} publications, {len(funding_summaries)} funding entries, built {build_date})')
