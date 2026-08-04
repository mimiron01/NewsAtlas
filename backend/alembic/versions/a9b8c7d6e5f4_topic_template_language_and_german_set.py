"""topic_templates: language column + curated German-market template set

Revision ID: a9b8c7d6e5f4
Revises: d4e5f6a7b8c1
Create Date: 2026-08-04 00:00:00.000000

Adds topic_templates.language (nullable — NULL means "shown regardless of workspace
language"), backfills the existing English seed set to language='en' so it stops
showing for German workspaces, and seeds a curated German-market set (German search
terms, German regulators/institutions — not just translated labels) for language='de'.
See docs/topics-ux-improvements-planning.html §2.1 and docs/german-i18n-planning.html.
"""
import uuid
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = 'a9b8c7d6e5f4'
down_revision: Union[str, None] = 'd4e5f6a7b8c1'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


# Curated by hand like the original English set (see d4e5f6a7b8c9's seed) — German search
# terms and, where relevant, German-market institutions (BaFin, Bundesnetzagentur, BSI,
# LkSG) rather than translations of the English terms, so German workspaces get topics
# that actually match German-language news coverage.
_SEED_TEMPLATES_DE = [
    {
        "name": "Automobilindustrie",
        "description": "Neue Fahrzeugmodelle, E-Auto/Batterie-News und Entwicklungen in der Automobilproduktion.",
        "category": "Industrie",
        "query_terms": ["Automobilindustrie", "Elektroauto", "E-Auto", "Autohersteller"],
        "exclude_terms": ["Autoversicherung", "Gebrauchtwagenhändler"],
        "sort_order": 10,
    },
    {
        "name": "SaaS & Cloud-Software",
        "description": "Produkteinführungen, Finanzierungen und Marktbewegungen im Cloud-/SaaS-Bereich.",
        "category": "Industrie",
        "query_terms": ["SaaS", "Cloud-Software", "Unternehmenssoftware"],
        "exclude_terms": [],
        "sort_order": 20,
    },
    {
        "name": "Fintech & Zahlungsverkehr",
        "description": "Digitale Zahlungen, Banktechnologie und Fintech-Produktnews.",
        "category": "Industrie",
        "query_terms": ["Fintech", "digitale Zahlungen", "Zahlungsabwicklung"],
        "exclude_terms": ["Versicherungsschaden"],
        "sort_order": 30,
    },
    {
        "name": "Gesundheitswesen & Biotech",
        "description": "Digital-Health-Produkte, Biotech-Durchbrüche und Health-Tech-Deals.",
        "category": "Industrie",
        "query_terms": ["Gesundheitstechnologie", "Biotech", "digitale Gesundheit"],
        "exclude_terms": ["Promi-Gesundheit"],
        "sort_order": 40,
    },
    {
        "name": "Einzelhandel & E-Commerce",
        "description": "Online-Handel-Launches, E-Commerce-Plattform-News und Einzelhandelstechnologie.",
        "category": "Industrie",
        "query_terms": ["E-Commerce", "Online-Handel", "Einzelhandelstechnologie"],
        "exclude_terms": [],
        "sort_order": 50,
    },
    {
        "name": "Lieferkette & Logistik",
        "description": "Fracht, Logistiktechnologie und Störungen in der Lieferkette.",
        "category": "Industrie",
        "query_terms": ["Lieferkette", "Logistiktechnologie", "Spedition"],
        "exclude_terms": [],
        "sort_order": 60,
    },
    {
        "name": "KI & Maschinelles Lernen",
        "description": "KI-Produkteinführungen, Modell-Releases und der Einsatz von KI in Unternehmen.",
        "category": "Industrie",
        "query_terms": ["künstliche Intelligenz", "maschinelles Lernen", "generative KI"],
        "exclude_terms": ["KI-Kunst-Kontroverse"],
        "sort_order": 70,
    },
    {
        "name": "Series-A/B/C-Finanzierung",
        "description": "Neue Wagniskapitalrunden für wachstumsstarke Startups.",
        "category": "Finanzierung & M&A",
        "query_terms": [
            "Series-A-Finanzierung", "Series-B-Finanzierung", "Series-C-Finanzierung", "Wagniskapitalrunde",
        ],
        "exclude_terms": [],
        "sort_order": 80,
    },
    {
        "name": "Fusionen & Übernahmen",
        "description": "Unternehmensübernahmen und Fusionsankündigungen.",
        "category": "Finanzierung & M&A",
        "query_terms": ["Fusion und Übernahme", "übernimmt Startup", "Übernahmeangebot"],
        "exclude_terms": [],
        "sort_order": 90,
    },
    {
        "name": "Regulierung & Compliance",
        "description": "Neue Regulierung und Compliance-Anforderungen für Unternehmen, u. a. durch BaFin und Bundesnetzagentur.",
        "category": "Regulatorisch",
        "query_terms": [
            "regulatorische Vorgaben", "neue Regulierung", "Compliance-Anforderung", "BaFin", "Bundesnetzagentur",
        ],
        "exclude_terms": ["Promi-Skandal"],
        "sort_order": 100,
    },
    {
        "name": "Cybersicherheitsvorfälle",
        "description": "Datenlecks, Ransomware-Angriffe und größere Sicherheitsvorfälle, eingeordnet auch nach BSI-Warnungen.",
        "category": "Regulatorisch",
        "query_terms": ["Datenleck", "Cybersicherheitsvorfall", "Ransomware-Angriff", "BSI-Warnung"],
        "exclude_terms": [],
        "sort_order": 110,
    },
    {
        "name": "Nachhaltigkeit & ESG",
        "description": "Nachhaltigkeitsinitiativen von Unternehmen, ESG-/Emissionsziele und Pflichten aus dem Lieferkettensorgfaltspflichtengesetz (LkSG).",
        "category": "Regulatorisch",
        "query_terms": ["ESG", "Nachhaltigkeitsinitiative", "CO2-Ziele", "Lieferkettensorgfaltspflichtengesetz"],
        "exclude_terms": [],
        "sort_order": 120,
    },
]


def upgrade() -> None:
    op.add_column('topic_templates', sa.Column('language', sa.String(length=8), nullable=True))

    # The existing seed set is English-only content; tag it explicitly so it stops
    # appearing for German workspaces once the filter (main_language) is live. Any
    # admin-created template (not part of that original seed) is left language=NULL
    # (universal) rather than guessed at.
    op.execute(
        "UPDATE topic_templates SET language = 'en' WHERE language IS NULL "
        "AND name IN ("
        "'Automotive', 'SaaS & Cloud Software', 'Fintech & Payments', "
        "'Healthcare & Biotech', 'Retail & E-commerce', 'Supply Chain & Logistics', "
        "'AI & Machine Learning', 'Series A/B/C Funding', 'M&A Activity', "
        "'Regulatory & Compliance', 'Cybersecurity Incidents', 'Sustainability & ESG'"
        ")"
    )

    topic_templates = sa.table(
        'topic_templates',
        sa.column('id', postgresql.UUID(as_uuid=True)),
        sa.column('name', sa.String),
        sa.column('description', sa.String),
        sa.column('category', sa.String),
        sa.column('language', sa.String),
        sa.column('query_terms', postgresql.ARRAY(sa.String())),
        sa.column('exclude_terms', postgresql.ARRAY(sa.String())),
        sa.column('sort_order', sa.Integer),
    )
    op.bulk_insert(
        topic_templates,
        [
            {
                'id': uuid.uuid4(),
                'name': t['name'],
                'description': t['description'],
                'category': t['category'],
                'language': 'de',
                'query_terms': t['query_terms'],
                'exclude_terms': t['exclude_terms'],
                'sort_order': t['sort_order'],
            }
            for t in _SEED_TEMPLATES_DE
        ],
    )


def downgrade() -> None:
    op.execute(
        "DELETE FROM topic_templates WHERE language = 'de' AND name IN ("
        + ", ".join(f"'{t['name']}'" for t in _SEED_TEMPLATES_DE)
        + ")"
    )
    op.execute("UPDATE topic_templates SET language = NULL WHERE language = 'en'")
    op.drop_column('topic_templates', 'language')
