from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from app.services.article_scoring import (
    IDENTITY_IN_TITLE,
    article_domain,
    collapse_near_duplicate_titles,
    normalize_title,
    rank_candidates,
    score_candidate,
    title_similarity,
)


@dataclass
class Candidate:
    title: str
    url: str = "https://example.com/a"
    description: str | None = None
    published_at: datetime | None = None


NOW = datetime(2026, 7, 30, 12, 0, tzinfo=timezone.utc)
SINCE = NOW - timedelta(hours=24)


def test_normalize_title_strips_attribution_suffix_and_punctuation():
    assert normalize_title("Acme raises $10M! - TechCrunch") == "acme raises 10m"


def test_title_similarity_treats_syndicated_variants_as_the_same_story():
    assert (
        title_similarity(
            "Acme raises $10M in Series B - TechCrunch",
            "Acme raises $10M in Series B | Reuters",
        )
        >= 0.85
    )


def test_title_similarity_separates_genuinely_different_stories():
    assert title_similarity("Acme raises $10M", "Acme announces layoffs") < 0.85


def test_article_domain_strips_www():
    assert article_domain("https://www.reuters.com/world/story") == "reuters.com"
    assert article_domain(None) == ""


def test_score_rewards_identity_in_title_over_description():
    in_title = score_candidate(Candidate(title="Acme Corp raises $10M"), identity_terms=["Acme Corp"])
    in_description = score_candidate(
        Candidate(title="Funding roundup", description="Acme Corp raised $10M"),
        identity_terms=["Acme Corp"],
    )
    assert in_title > in_description > 0


def test_score_rewards_allowlisted_domain_including_subdomains():
    scored = score_candidate(
        Candidate(title="x", url="https://feeds.reuters.com/a"),
        identity_terms=[],
        allowlist=["reuters.com"],
    )
    assert scored > 0


def test_score_penalises_the_fourth_article_from_one_domain():
    kwargs = dict(identity_terms=["Acme"], since=SINCE, now=NOW)
    free = score_candidate(Candidate(title="Acme"), domain_seen_count=2, **kwargs)
    penalised = score_candidate(Candidate(title="Acme"), domain_seen_count=3, **kwargs)
    assert penalised < free


def test_rank_prefers_an_older_original_over_a_newer_aggregator_repost():
    """The core of finding F5: newest-first systematically picked the repost."""
    original = Candidate(
        title="Acme Corp raises $10M",
        url="https://reuters.com/acme",
        published_at=NOW - timedelta(hours=10),
    )
    repost = Candidate(
        title="Funding news roundup",
        url="https://aggregator.example/roundup",
        published_at=NOW - timedelta(minutes=5),
    )

    ranked = rank_candidates(
        [repost, original],
        article_of=lambda item: item,
        identity_terms=["Acme Corp"],
        allowlist=["reuters.com"],
        since=SINCE,
        now=NOW,
    )

    assert ranked[0] is original


def test_rank_falls_back_to_recency_when_nothing_else_distinguishes():
    older = Candidate(title="Acme", url="https://a.example/1", published_at=NOW - timedelta(hours=5))
    newer = Candidate(title="Acme", url="https://b.example/2", published_at=NOW - timedelta(hours=1))

    ranked = rank_candidates(
        [older, newer], article_of=lambda item: item, identity_terms=["Acme"], since=SINCE, now=NOW
    )

    assert ranked[0] is newer


def test_rank_is_stable_for_identical_inputs():
    items = [Candidate(title="Acme", url=f"https://x.example/{i}") for i in range(5)]
    first = rank_candidates(items, article_of=lambda i: i, identity_terms=["Acme"])
    second = rank_candidates(items, article_of=lambda i: i, identity_terms=["Acme"])
    assert [id(i) for i in first] == [id(i) for i in second]


def test_collapse_keeps_one_copy_of_a_syndicated_story():
    items = [
        Candidate(title="Acme raises $10M in Series B - Outlet A", url="https://a.example/1"),
        Candidate(title="Acme raises $10M in Series B - Outlet B", url="https://b.example/2"),
        Candidate(title="Acme announces layoffs", url="https://c.example/3"),
    ]

    kept, dropped = collapse_near_duplicate_titles(items, key=lambda i: i.title)

    assert len(kept) == 2
    assert len(dropped) == 1


def test_collapse_keeps_the_best_scoring_copy_not_the_first():
    """The best copy of a wire story is rarely the one a provider happened to return
    first, so the cluster's representative is chosen by score."""
    weak = Candidate(title="Acme raises $10M - Aggregator", url="https://spam.example/1")
    strong = Candidate(title="Acme raises $10M - Reuters", url="https://reuters.com/1")

    kept, dropped = collapse_near_duplicate_titles(
        [weak, strong],
        key=lambda i: i.title,
        score=lambda i: score_candidate(i, identity_terms=["Acme"], allowlist=["reuters.com"]),
    )

    assert kept == [strong]
    assert dropped == [weak]


def test_collapse_without_a_scorer_keeps_the_first_occurrence():
    first = Candidate(title="Acme raises $10M", url="https://a.example/1")
    second = Candidate(title="Acme raises $10M", url="https://b.example/2")

    kept, dropped = collapse_near_duplicate_titles([first, second], key=lambda i: i.title)

    assert kept == [first]
    assert dropped == [second]


def test_score_identity_weight_is_the_dominant_signal():
    """Guards the intent of the weight table: nothing else should outweigh the article
    actually naming the company in its headline."""
    other_signals = score_candidate(
        Candidate(title="x", url="https://reuters.com/a", published_at=NOW),
        identity_terms=["Acme"],
        context_terms=["EV"],
        allowlist=["reuters.com"],
        since=SINCE,
        now=NOW,
    )
    assert IDENTITY_IN_TITLE > 0
    assert other_signals < IDENTITY_IN_TITLE + 5
