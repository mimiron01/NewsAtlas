"""topic_templates: tighten seed query_terms/exclude_terms against generic-noise false positives

Revision ID: d5e6f7a8b9c0
Revises: c4d5e6f7a8b9
Create Date: 2026-08-04 13:00:00.000000

Editorial pass over the 12 EN + 12 DE seed templates (d4e5f6a7b8c9, a9b8c7d6e5f4),
extending exclude_terms with the same category the original curators already used for
some templates ("car insurance", "celebrity health", "AI art controversy", "celebrity
scandal") — generic consumer-interest/lifestyle content that happens to share a keyword
with the topic but carries no business signal — to templates that had none. M&A Activity
is deliberately left unchanged: no defensible false-positive category was identified for
it without inventing one.

query_terms are left untouched. This is a keyword-level pass and keyword exclusion can
only filter false-positive collisions, not distinguish "industry trend piece" from
"company-specific signal" (that distinction is what workspace_settings.
theme_match_min_relevance_score, added in c4d5e6f7a8b9, and the per-topic feedback note
fix in services/feedback.py are for). Per docs/google-news-quality-planning.html's own
stated limitation, this environment has no outbound egress to news.google.com, so none of
this was verified against the live feed — it follows the established pattern from the
original curation rather than being empirically tuned.

Updates existing seeded rows in place (matched by name + language) rather than
re-inserting, so applying this migration to a workspace that already has these templates
(and possibly ThemeWatches created_from_template_id-linked to them) doesn't create
duplicates or break that provenance link.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = 'd5e6f7a8b9c0'
down_revision: Union[str, None] = 'c4d5e6f7a8b9'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


# name -> additional exclude_terms appended to whatever the template already had.
_EN_ADDITIONS = {
    "Automotive": ["motorsport results"],
    "SaaS & Cloud Software": ["best software tools listicle", "software how-to guide"],
    "Fintech & Payments": ["personal budgeting advice"],
    "Healthcare & Biotech": ["diet and wellness trend"],
    "Retail & E-commerce": ["holiday shopping deals", "product review roundup"],
    "Supply Chain & Logistics": ["moving company review"],
    "AI & Machine Learning": ["AI chatbot personal use tips"],
    "Series A/B/C Funding": ["personal retirement savings"],
    "Regulatory & Compliance": ["parking ticket regulation"],
    "Cybersecurity Incidents": ["cybersecurity tips for consumers"],
    "Sustainability & ESG": ["eco-friendly lifestyle tips"],
}

_DE_ADDITIONS = {
    "Automobilindustrie": ["Motorsport-Ergebnisse"],
    "SaaS & Cloud-Software": ["Software-Tool-Empfehlungen", "Software-Anleitung"],
    "Fintech & Zahlungsverkehr": ["Spartipps für Verbraucher"],
    "Gesundheitswesen & Biotech": ["Ernährungstrend"],
    "Einzelhandel & E-Commerce": ["Shopping-Deals", "Produkttest-Ranking"],
    "Lieferkette & Logistik": ["Umzugsunternehmen-Bewertung"],
    "KI & Maschinelles Lernen": ["KI-Chatbot-Tipps für Verbraucher"],
    "Series-A/B/C-Finanzierung": ["private Altersvorsorge"],
    "Regulierung & Compliance": ["Parkverstoß"],
    "Cybersicherheitsvorfälle": ["Cybersicherheitstipps für Verbraucher"],
    "Nachhaltigkeit & ESG": ["nachhaltiger Lifestyle-Tipp"],
}


def _apply(connection, additions: dict[str, list[str]], language: str) -> None:
    topic_templates = sa.table(
        'topic_templates',
        sa.column('name', sa.String),
        sa.column('language', sa.String),
        sa.column('exclude_terms', postgresql.ARRAY(sa.String())),
    )
    for name, extra_terms in additions.items():
        existing = connection.execute(
            sa.select(topic_templates.c.exclude_terms).where(
                topic_templates.c.name == name, topic_templates.c.language == language
            )
        ).scalar_one_or_none()
        if existing is None:
            continue
        merged = list(existing) + [t for t in extra_terms if t not in existing]
        connection.execute(
            topic_templates.update()
            .where(topic_templates.c.name == name, topic_templates.c.language == language)
            .values(exclude_terms=merged)
        )


def upgrade() -> None:
    connection = op.get_bind()
    _apply(connection, _EN_ADDITIONS, 'en')
    _apply(connection, _DE_ADDITIONS, 'de')


def downgrade() -> None:
    connection = op.get_bind()
    topic_templates = sa.table(
        'topic_templates',
        sa.column('name', sa.String),
        sa.column('language', sa.String),
        sa.column('exclude_terms', postgresql.ARRAY(sa.String())),
    )
    for additions, language in ((_EN_ADDITIONS, 'en'), (_DE_ADDITIONS, 'de')):
        for name, extra_terms in additions.items():
            existing = connection.execute(
                sa.select(topic_templates.c.exclude_terms).where(
                    topic_templates.c.name == name, topic_templates.c.language == language
                )
            ).scalar_one_or_none()
            if existing is None:
                continue
            restored = [t for t in existing if t not in extra_terms]
            connection.execute(
                topic_templates.update()
                .where(topic_templates.c.name == name, topic_templates.c.language == language)
                .values(exclude_terms=restored)
            )
