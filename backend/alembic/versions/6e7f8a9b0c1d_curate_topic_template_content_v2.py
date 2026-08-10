"""topic_templates: second curation pass (exclude_terms, regulator anchors, suggested sources)

Revision ID: 6e7f8a9b0c1d
Revises: 5d61bc93aef9
Create Date: 2026-08-10 12:00:00.000000

Follow-up to d5e6f7a8b9c0's exclude_terms pass, driven by a manual review of the seed
templates rather than live performance data (this environment still has no egress to
news.google.com, so none of this is empirically verified — same caveat as d5e6f7a8b9c0).

Three changes, all additive/update-in-place (matched by name + language, same pattern as
d5e6f7a8b9c0) so they don't disturb ThemeWatch.created_from_template_id provenance:

1. exclude_terms: extends templates whose noise categories were missed by the first pass
   or introduced by their own query_terms —
   - "Automotive"/"Automobilindustrie": bare "EV" collides with the finance shorthand for
     Enterprise Value (as in "EV/EBITDA"), pulling in valuation/M&A coverage that has
     nothing to do with vehicles.
   - "AI & Machine Learning"/"KI & Maschinelles Lernen": the two existing exclude_terms
     don't touch the biggest noise categories for a term this saturated in current
     coverage (regulation op-eds, job-loss opinion pieces, companion-app stories, student
     cheating stories, celebrity deepfakes).
   - "Supply Chain & Logistics"/"Lieferkette & Logistik": "supply chain" alone is a
     generic macro-economic term; the first pass only addressed an unrelated "logistics"
     collision ("moving company review"), not this breadth problem.
   - "Regulatory & Compliance"/"Regulierung & Compliance": "new regulation" isn't scoped
     to business at all (sports, immigration, education, etc. all use the phrase); the
     first pass only removed one narrow collision ("parking ticket regulation").
   - "Cybersecurity Incidents"/"Cybersicherheitsvorfälle": adds a consumer-product-review
     exclusion matching the pattern already used for antivirus/security tips content.

2. query_terms: the German set anchors two templates to named regulators/institutions
   (BaFin, Bundesnetzagentur, BSI-Warnung) that the English set never got an equivalent
   for, making the English versions structurally vaguer for the same topic. Adds the same
   kind of anchor to "Regulatory & Compliance" (SEC/FTC/antitrust) and "Cybersecurity
   Incidents" (CISA) so both language sets have comparable specificity.

3. suggested_source_allowlist: every one of the 24 seed templates shipped with this field
   empty, even though TopicTemplate models it and ThemeWatch.apply() uses it as the
   theme's starting google_news_source_allowlist when the user doesn't override it. Sets a
   small set of reputable, topic-appropriate domains per template so a freshly-applied
   topic starts scoped to trustworthy sources instead of the open web.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = '6e7f8a9b0c1d'
down_revision: Union[str, None] = '5d61bc93aef9'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


# name -> additional exclude_terms appended to whatever the template already had.
_EN_EXCLUDE_ADDITIONS = {
    "Automotive": ["EV/EBITDA", "enterprise value"],
    "AI & Machine Learning": [
        "AI regulation op-ed",
        "AI job loss opinion",
        "AI companion app",
        "student AI cheating",
        "celebrity deepfake",
    ],
    "Supply Chain & Logistics": [
        "grocery shortage",
        "holiday shipping delay",
        "consumer shortage explainer",
    ],
    "Regulatory & Compliance": ["sports regulation change", "immigration policy", "school district policy"],
    "Cybersecurity Incidents": ["antivirus software review"],
}

_DE_EXCLUDE_ADDITIONS = {
    "KI & Maschinelles Lernen": [
        "KI-Regulierungsdebatte",
        "KI-Jobverlust-Meinungsbeitrag",
        "KI-Begleiter-App",
        "Schüler-KI-Betrug",
        "Promi-Deepfake",
    ],
    "Lieferkette & Logistik": [
        "Lebensmittelknappheit",
        "Weihnachtsversand-Verzögerung",
        "Verbraucher-Lieferengpass",
    ],
    "Regulierung & Compliance": ["Sportregel-Änderung", "Einwanderungspolitik", "Schulordnung"],
    "Cybersicherheitsvorfälle": ["Antivirensoftware-Test"],
}

# name -> additional query_terms appended (regulator/institution anchors, EN only — the
# DE set already has these from a9b8c7d6e5f4).
_EN_QUERY_ADDITIONS = {
    "Regulatory & Compliance": ["SEC enforcement action", "FTC investigation", "antitrust regulation"],
    "Cybersecurity Incidents": ["CISA advisory"],
}

# name -> suggested_source_allowlist (overwrite; every seed row is currently []).
_EN_ALLOWLISTS = {
    "Automotive": ["reuters.com", "bloomberg.com", "autonews.com", "electrek.co"],
    "SaaS & Cloud Software": ["techcrunch.com", "theinformation.com", "reuters.com"],
    "Fintech & Payments": ["reuters.com", "bloomberg.com", "finextra.com"],
    "Healthcare & Biotech": ["reuters.com", "statnews.com", "fiercebiotech.com"],
    "Retail & E-commerce": ["reuters.com", "retaildive.com", "bloomberg.com"],
    "Supply Chain & Logistics": ["reuters.com", "freightwaves.com", "supplychaindive.com"],
    "AI & Machine Learning": ["reuters.com", "techcrunch.com", "theinformation.com"],
    "Series A/B/C Funding": ["techcrunch.com", "crunchbase.com", "bloomberg.com"],
    "M&A Activity": ["reuters.com", "bloomberg.com", "wsj.com"],
    "Regulatory & Compliance": ["reuters.com", "bloomberg.com", "law360.com"],
    "Cybersecurity Incidents": ["reuters.com", "bleepingcomputer.com", "therecord.media"],
    "Sustainability & ESG": ["reuters.com", "bloomberg.com", "esgtoday.com"],
}

_DE_ALLOWLISTS = {
    "Automobilindustrie": ["handelsblatt.com", "reuters.com", "automobilwoche.de"],
    "SaaS & Cloud-Software": ["handelsblatt.com", "reuters.com", "t3n.de"],
    "Fintech & Zahlungsverkehr": ["handelsblatt.com", "finance-forward.com", "reuters.com"],
    "Gesundheitswesen & Biotech": ["handelsblatt.com", "aerzteblatt.de", "reuters.com"],
    "Einzelhandel & E-Commerce": ["handelsblatt.com", "lebensmittelzeitung.net", "reuters.com"],
    "Lieferkette & Logistik": ["handelsblatt.com", "dvz.de", "reuters.com"],
    "KI & Maschinelles Lernen": ["handelsblatt.com", "t3n.de", "reuters.com"],
    "Series-A/B/C-Finanzierung": ["deutsche-startups.de", "handelsblatt.com", "reuters.com"],
    "Fusionen & Übernahmen": ["handelsblatt.com", "reuters.com", "wiwo.de"],
    "Regulierung & Compliance": ["handelsblatt.com", "reuters.com", "bafin.de"],
    "Cybersicherheitsvorfälle": ["heise.de", "bsi.bund.de", "reuters.com"],
    "Nachhaltigkeit & ESG": ["handelsblatt.com", "wiwo.de", "reuters.com"],
}


def _table():
    return sa.table(
        'topic_templates',
        sa.column('name', sa.String),
        sa.column('language', sa.String),
        sa.column('query_terms', postgresql.ARRAY(sa.String())),
        sa.column('exclude_terms', postgresql.ARRAY(sa.String())),
        sa.column('suggested_source_allowlist', postgresql.ARRAY(sa.String())),
    )


def _append(connection, table, name, language, column, extra_terms):
    existing = connection.execute(
        sa.select(getattr(table.c, column)).where(table.c.name == name, table.c.language == language)
    ).scalar_one_or_none()
    if existing is None:
        return None
    merged = list(existing) + [t for t in extra_terms if t not in existing]
    connection.execute(
        table.update()
        .where(table.c.name == name, table.c.language == language)
        .values(**{column: merged})
    )
    return existing


def _set_allowlist(connection, table, name, language, allowlist):
    connection.execute(
        table.update()
        .where(table.c.name == name, table.c.language == language)
        .values(suggested_source_allowlist=allowlist)
    )


def upgrade() -> None:
    connection = op.get_bind()
    table = _table()

    for name, extra in _EN_EXCLUDE_ADDITIONS.items():
        _append(connection, table, name, 'en', 'exclude_terms', extra)
    for name, extra in _DE_EXCLUDE_ADDITIONS.items():
        _append(connection, table, name, 'de', 'exclude_terms', extra)
    for name, extra in _EN_QUERY_ADDITIONS.items():
        _append(connection, table, name, 'en', 'query_terms', extra)
    for name, allowlist in _EN_ALLOWLISTS.items():
        _set_allowlist(connection, table, name, 'en', allowlist)
    for name, allowlist in _DE_ALLOWLISTS.items():
        _set_allowlist(connection, table, name, 'de', allowlist)


def downgrade() -> None:
    connection = op.get_bind()
    table = _table()

    for name, extra in _EN_EXCLUDE_ADDITIONS.items():
        existing = connection.execute(
            sa.select(table.c.exclude_terms).where(table.c.name == name, table.c.language == 'en')
        ).scalar_one_or_none()
        if existing is None:
            continue
        restored = [t for t in existing if t not in extra]
        connection.execute(
            table.update().where(table.c.name == name, table.c.language == 'en').values(exclude_terms=restored)
        )
    for name, extra in _DE_EXCLUDE_ADDITIONS.items():
        existing = connection.execute(
            sa.select(table.c.exclude_terms).where(table.c.name == name, table.c.language == 'de')
        ).scalar_one_or_none()
        if existing is None:
            continue
        restored = [t for t in existing if t not in extra]
        connection.execute(
            table.update().where(table.c.name == name, table.c.language == 'de').values(exclude_terms=restored)
        )
    for name, extra in _EN_QUERY_ADDITIONS.items():
        existing = connection.execute(
            sa.select(table.c.query_terms).where(table.c.name == name, table.c.language == 'en')
        ).scalar_one_or_none()
        if existing is None:
            continue
        restored = [t for t in existing if t not in extra]
        connection.execute(
            table.update().where(table.c.name == name, table.c.language == 'en').values(query_terms=restored)
        )
    for name in _EN_ALLOWLISTS:
        _set_allowlist(connection, table, name, 'en', [])
    for name in _DE_ALLOWLISTS:
        _set_allowlist(connection, table, name, 'de', [])
