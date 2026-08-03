"""topic_templates: curated starter topics, seeded + theme_watches provenance FK

Revision ID: d4e5f6a7b8c9
Revises: c3d4e5f6a7b8
Create Date: 2026-08-02 00:10:00.000000

Adds the topic_templates table (see docs/topics-ux-improvements-planning.html §2.1),
seeds it with an initial curated set, and adds theme_watches.created_from_template_id
(nullable, SET NULL) so a topic created from a template keeps a link back to it for
§2.4's performance aggregation. Fully additive — no existing row's meaning changes.
"""
import uuid
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = 'd4e5f6a7b8c9'
down_revision: Union[str, None] = 'c3d4e5f6a7b8'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


# Curated by hand, not generated — the whole point of a template is that a human has
# already tuned it (including exclude_terms to cut known noise) so it's more trustworthy
# than a topic a user free-types from scratch. Refine via the admin template-management
# endpoints post-launch (see §2.4's performance tracking), not by editing this migration.
_SEED_TEMPLATES = [
    {
        "name": "Automotive",
        "description": "New vehicle launches, EV/battery news, and auto manufacturing moves.",
        "category": "Industry",
        "query_terms": ["automotive", "electric vehicle", "EV", "auto manufacturing"],
        "exclude_terms": ["car insurance", "used car dealership"],
        "sort_order": 10,
    },
    {
        "name": "SaaS & Cloud Software",
        "description": "Product launches, funding, and market moves across cloud/SaaS.",
        "category": "Industry",
        "query_terms": ["SaaS", "cloud software", "enterprise software"],
        "exclude_terms": [],
        "sort_order": 20,
    },
    {
        "name": "Fintech & Payments",
        "description": "Digital payments, banking technology, and fintech product news.",
        "category": "Industry",
        "query_terms": ["fintech", "digital payments", "payment processing"],
        "exclude_terms": ["insurance claim"],
        "sort_order": 30,
    },
    {
        "name": "Healthcare & Biotech",
        "description": "Digital health products, biotech breakthroughs, and health-tech deals.",
        "category": "Industry",
        "query_terms": ["healthcare technology", "biotech", "digital health"],
        "exclude_terms": ["celebrity health"],
        "sort_order": 40,
    },
    {
        "name": "Retail & E-commerce",
        "description": "Online retail launches, e-commerce platform news, and retail tech.",
        "category": "Industry",
        "query_terms": ["e-commerce", "online retail", "retail technology"],
        "exclude_terms": [],
        "sort_order": 50,
    },
    {
        "name": "Supply Chain & Logistics",
        "description": "Freight, logistics technology, and supply-chain disruption news.",
        "category": "Industry",
        "query_terms": ["supply chain", "logistics technology", "freight"],
        "exclude_terms": [],
        "sort_order": 60,
    },
    {
        "name": "AI & Machine Learning",
        "description": "AI product launches, model releases, and enterprise AI adoption.",
        "category": "Industry",
        "query_terms": ["artificial intelligence", "machine learning", "generative AI"],
        "exclude_terms": ["AI art controversy"],
        "sort_order": 70,
    },
    {
        "name": "Series A/B/C Funding",
        "description": "New venture funding rounds for growth-stage startups.",
        "category": "Funding & M&A",
        "query_terms": [
            "Series A funding", "Series B funding", "Series C funding", "venture capital round",
        ],
        "exclude_terms": [],
        "sort_order": 80,
    },
    {
        "name": "M&A Activity",
        "description": "Company acquisitions and merger announcements.",
        "category": "Funding & M&A",
        "query_terms": ["merger and acquisition", "acquires startup", "acquisition deal"],
        "exclude_terms": [],
        "sort_order": 90,
    },
    {
        "name": "Regulatory & Compliance",
        "description": "New regulations and compliance requirements affecting businesses.",
        "category": "Regulatory",
        "query_terms": ["regulatory compliance", "new regulation", "compliance requirement"],
        "exclude_terms": ["celebrity scandal"],
        "sort_order": 100,
    },
    {
        "name": "Cybersecurity Incidents",
        "description": "Data breaches, ransomware attacks, and major security incidents.",
        "category": "Regulatory",
        "query_terms": ["data breach", "cybersecurity incident", "ransomware attack"],
        "exclude_terms": [],
        "sort_order": 110,
    },
    {
        "name": "Sustainability & ESG",
        "description": "Corporate sustainability initiatives and ESG/emissions targets.",
        "category": "Regulatory",
        "query_terms": ["ESG", "sustainability initiative", "carbon emissions target"],
        "exclude_terms": [],
        "sort_order": 120,
    },
]


def upgrade() -> None:
    op.create_table(
        'topic_templates',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('name', sa.String(length=255), nullable=False),
        sa.Column('description', sa.String(length=500), nullable=False, server_default=''),
        sa.Column('category', sa.String(length=100), nullable=True),
        sa.Column('query_terms', postgresql.ARRAY(sa.String()), nullable=False, server_default='{}'),
        sa.Column('exclude_terms', postgresql.ARRAY(sa.String()), nullable=False, server_default='{}'),
        sa.Column(
            'suggested_source_allowlist', postgresql.ARRAY(sa.String()), nullable=False, server_default='{}'
        ),
        sa.Column('is_active', sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column('sort_order', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )

    topic_templates = sa.table(
        'topic_templates',
        sa.column('id', postgresql.UUID(as_uuid=True)),
        sa.column('name', sa.String),
        sa.column('description', sa.String),
        sa.column('category', sa.String),
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
                'query_terms': t['query_terms'],
                'exclude_terms': t['exclude_terms'],
                'sort_order': t['sort_order'],
            }
            for t in _SEED_TEMPLATES
        ],
    )

    op.add_column('theme_watches', sa.Column('created_from_template_id', postgresql.UUID(as_uuid=True), nullable=True))
    op.create_foreign_key(
        'fk_theme_watches_created_from_template_id',
        'theme_watches',
        'topic_templates',
        ['created_from_template_id'],
        ['id'],
        ondelete='SET NULL',
    )


def downgrade() -> None:
    op.drop_constraint('fk_theme_watches_created_from_template_id', 'theme_watches', type_='foreignkey')
    op.drop_column('theme_watches', 'created_from_template_id')
    op.drop_table('topic_templates')
