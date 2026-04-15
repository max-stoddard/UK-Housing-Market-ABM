#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Official-source evidence reviews and recommendation logic for BoE policy stories.

All sources in this module are current public sources from the Bank of England,
FCA, ONS, or GOV.UK/HM Treasury.

@author: Max Stoddard
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Mapping, Sequence

from scripts.python.experiments.model.policy_story_catalog import PolicyStoryDefinition
from scripts.python.experiments.model.policy_story_scoring import StoryScore

V41_VALIDATION_CAVEAT = (
    "`v4.1` is a fork of `v4.0` with aligned hard LTV caps for FTB, HM, and BTL, "
    "and its R8 validation is now tracked as `complete` in `input-data-versions/dashboard-input-version-history.json`."
)


@dataclass(frozen=True)
class OfficialEvidenceSource:
    """One current official/public source used in a story evidence review."""

    title: str
    url: str
    publisher: str
    published_on: str
    relevance: str

    def to_json(self) -> dict[str, str]:
        return asdict(self)


@dataclass(frozen=True)
class StoryEvidenceReview:
    """Official-source review for one policy story."""

    story_id: str
    evidence_strength: float
    fit_summary: str
    gap_summary: str
    sources: tuple[OfficialEvidenceSource, ...]

    def to_json(self) -> dict[str, object]:
        payload = asdict(self)
        payload["sources"] = [source.to_json() for source in self.sources]
        return payload


@dataclass(frozen=True)
class StoryRecommendation:
    """Balanced single-story recommendation for the demo."""

    story_id: str
    title: str
    blended_score: float
    model_score: float
    model_score_normalized: float
    evidence_strength: float
    rationale: str
    caveat: str

    def to_json(self) -> dict[str, object]:
        return asdict(self)


def get_story_evidence_reviews() -> dict[str, StoryEvidenceReview]:
    """Return the official-source evidence pack for each catalog story."""

    return {
        "lti_flow_limit_bundle": StoryEvidenceReview(
            story_id="lti_flow_limit_bundle",
            evidence_strength=0.95,
            fit_summary=(
                "Strong fit: current BoE and FCA material directly discusses high-LTI lending, "
                "recent policy flexibility around the 15% flow limit, and rising high-LTI activity."
            ),
            gap_summary=(
                "Minor gap: official sources discuss lender-level flexibility around the aggregate flow limit, "
                "not a fresh proposal to tighten the aggregate limit itself."
            ),
            sources=(
                OfficialEvidenceSource(
                    title="Financial Stability Report - December 2025",
                    url="https://www.bankofengland.co.uk/financial-stability-report/2025/december-2025",
                    publisher="Bank of England",
                    published_on="2025-12-02",
                    relevance=(
                        "Explains the 2025 update to the LTI flow-limit implementation and notes higher household credit supply."
                    ),
                ),
                OfficialEvidenceSource(
                    title="Mortgage Lenders and Administrators Statistics - 2025 Q3",
                    url="https://www.bankofengland.co.uk/statistics/mortgage-lenders-and-administrators/2025/2025-q3",
                    publisher="Bank of England",
                    published_on="2025-12-09",
                    relevance=(
                        "Shows high-LTI lending rose to 44.7% on the BoE definition and provides current mortgage-composition context."
                    ),
                ),
                OfficialEvidenceSource(
                    title="FCA sets out plans to help build mortgage market of the future",
                    url="https://www.fca.org.uk/news/press-releases/fca-sets-out-plans-help-build-mortgage-market-future",
                    publisher="FCA",
                    published_on="2025-12-15",
                    relevance=(
                        "Confirms current regulatory discussion around widening mortgage access while preserving risk controls."
                    ),
                ),
            ),
        ),
        "ftb_ltv_cap": StoryEvidenceReview(
            story_id="ftb_ltv_cap",
            evidence_strength=0.98,
            fit_summary=(
                "Very strong fit: current official sources directly cover high-LTV mortgage availability, "
                "small-deposit access, and the high-price backdrop facing first-time buyers."
            ),
            gap_summary=(
                "Minor gap: official sources support 95% LTV availability and deposit pressure, "
                "but do not argue for a new BoE-style FTB-specific hard cap."
            ),
            sources=(
                OfficialEvidenceSource(
                    title="Mortgage Lenders and Administrators Statistics - 2025 Q3",
                    url="https://www.bankofengland.co.uk/statistics/mortgage-lenders-and-administrators/2025/2025-q3",
                    publisher="Bank of England",
                    published_on="2025-12-09",
                    relevance=(
                        "Shows the share of advances above 90% LTV reached 7.4%, the highest since 2008 Q2."
                    ),
                ),
                OfficialEvidenceSource(
                    title="2025 Mortgage Guarantee Scheme",
                    url="https://www.gov.uk/government/publications/2025-mortgage-guarantee-scheme",
                    publisher="GOV.UK / HM Treasury",
                    published_on="2025-07-15",
                    relevance=(
                        "Shows the UK government made 91-95% LTV mortgage availability a standing policy instrument for small-deposit borrowers."
                    ),
                ),
                OfficialEvidenceSource(
                    title="FCA sets out plans to help build mortgage market of the future",
                    url="https://www.fca.org.uk/news/press-releases/fca-sets-out-plans-help-build-mortgage-market-future",
                    publisher="FCA",
                    published_on="2025-12-15",
                    relevance=(
                        "Frames first-time buyer access as a current regulatory objective."
                    ),
                ),
                OfficialEvidenceSource(
                    title="Private rent and house prices, UK: February 2026",
                    url="https://www.ons.gov.uk/economy/inflationandpriceindices/bulletins/privaterentandhousepricesuk/february2026",
                    publisher="ONS",
                    published_on="2026-02-18",
                    relevance=(
                        "Provides the current price-and-rent backdrop that makes deposit constraints salient for first-time buyers."
                    ),
                ),
            ),
        ),
        "hm_ltv_cap": StoryEvidenceReview(
            story_id="hm_ltv_cap",
            evidence_strength=0.62,
            fit_summary=(
                "Moderate fit: official sources support the relevance of 95% LTV products and home-mover lending activity, "
                "but the policy conversation is less explicitly about mover-specific LTV ceilings."
            ),
            gap_summary=(
                "Main gap: the current official narrative is more first-time-buyer focused than home-mover specific."
            ),
            sources=(
                OfficialEvidenceSource(
                    title="Mortgage Lenders and Administrators Statistics - 2025 Q3",
                    url="https://www.bankofengland.co.uk/statistics/mortgage-lenders-and-administrators/2025/2025-q3",
                    publisher="Bank of England",
                    published_on="2025-12-09",
                    relevance=(
                        "Shows current home-mover share within owner-occupier house-purchase lending."
                    ),
                ),
                OfficialEvidenceSource(
                    title="2025 Mortgage Guarantee Scheme",
                    url="https://www.gov.uk/government/publications/2025-mortgage-guarantee-scheme",
                    publisher="GOV.UK / HM Treasury",
                    published_on="2025-07-15",
                    relevance=(
                        "Covers 95% LTV availability for both first-time buyers and home movers."
                    ),
                ),
            ),
        ),
        "affordability_cap": StoryEvidenceReview(
            story_id="affordability_cap",
            evidence_strength=0.90,
            fit_summary=(
                "Strong fit: current FCA and BoE material directly discusses mortgage affordability stress testing, "
                "credit supply effects, and broader mortgage-market flexibility."
            ),
            gap_summary=(
                "Minor gap: the current policy direction is toward more flexible affordability treatment rather than a tighter cap."
            ),
            sources=(
                OfficialEvidenceSource(
                    title="Interest rate ‘stress test’ rule – application of MCOB 11.6.18R",
                    url="https://www.fca.org.uk/firms/interest-rate-stress-test-rule",
                    publisher="FCA",
                    published_on="2025-03-07",
                    relevance=(
                        "Directly addresses how affordability stress testing should be applied in current market conditions."
                    ),
                ),
                OfficialEvidenceSource(
                    title="FS25/6: Mortgage Rule Review: Feedback to DP25/2 and Roadmap",
                    url="https://www.fca.org.uk/publications/feedback-statements/fs25-6-mortgage-rule-review-feedback-dp25-2-and-roadmap",
                    publisher="FCA",
                    published_on="2025-12-15",
                    relevance=(
                        "Shows affordability and access remain active parts of the current mortgage-rule review."
                    ),
                ),
                OfficialEvidenceSource(
                    title="Financial Stability Report - December 2025",
                    url="https://www.bankofengland.co.uk/financial-stability-report/2025/december-2025",
                    publisher="Bank of England",
                    published_on="2025-12-02",
                    relevance=(
                        "Links stress-rate changes to higher household credit supply and continued monitoring of mortgage-market effects."
                    ),
                ),
            ),
        ),
        "btl_icr_cap": StoryEvidenceReview(
            story_id="btl_icr_cap",
            evidence_strength=0.25,
            fit_summary=(
                "Weak fit: current official sources still cover BTL activity, but there is little live official discussion of "
                "ICR calibration as a front-and-centre policy instrument for the present demo."
            ),
            gap_summary=(
                "Main gap: reviewed official sources provide current BTL market context but no comparably strong live policy narrative "
                "for changing the ICR floor."
            ),
            sources=(
                OfficialEvidenceSource(
                    title="Mortgage Lenders and Administrators Statistics - 2025 Q3",
                    url="https://www.bankofengland.co.uk/statistics/mortgage-lenders-and-administrators/2025/2025-q3",
                    publisher="Bank of England",
                    published_on="2025-12-09",
                    relevance=(
                        "Provides current BTL share-of-advances context, showing BTL is a smaller slice of current mortgage activity."
                    ),
                ),
            ),
        ),
        "base_rate": StoryEvidenceReview(
            story_id="base_rate",
            evidence_strength=0.48,
            fit_summary=(
                "Moderate fit: official BoE releases provide current mortgage approvals and effective-rate context, "
                "but the demo’s value is more about macroprudential recalibration than the monetary channel."
            ),
            gap_summary=(
                "Main gap: this is a weaker story for the demo because it does not foreground the updated model inputs as clearly as borrower-constraint stories."
            ),
            sources=(
                OfficialEvidenceSource(
                    title="Money and Credit - December 2025",
                    url="https://www.bankofengland.co.uk/statistics/money-and-credit/2025/december-2025",
                    publisher="Bank of England",
                    published_on="2026-01-30",
                    relevance=(
                        "Provides current approvals and mortgage-flow context tied to changing rates."
                    ),
                ),
                OfficialEvidenceSource(
                    title="Effective interest rates - December 2025",
                    url="https://www.bankofengland.co.uk/statistics/effective-interest-rates/2025/december-2025",
                    publisher="Bank of England",
                    published_on="2026-01-30",
                    relevance=(
                        "Provides current effective mortgage-rate context for the monetary transmission channel."
                    ),
                ),
            ),
        ),
    }


def recommend_story(
    *,
    story_scores: Sequence[StoryScore],
    stories: Mapping[str, PolicyStoryDefinition],
    evidence_reviews: Mapping[str, StoryEvidenceReview],
) -> StoryRecommendation:
    """Recommend one story using a balanced model-plus-evidence score."""

    candidates = [score for score in story_scores if score.passes_minimum_robustness] or list(story_scores)
    if not candidates:
        raise RuntimeError("Cannot recommend a story from an empty screening result.")

    score_values = [score.total_score for score in candidates]
    score_floor = min(score_values)
    score_ceiling = max(score_values)

    def normalized_model_score(score: StoryScore) -> float:
        if abs(score_ceiling - score_floor) < 1e-12:
            return 1.0
        return (score.total_score - score_floor) / (score_ceiling - score_floor)

    ranked = []
    for score in candidates:
        story = stories[score.story_id]
        evidence = evidence_reviews.get(
            score.story_id,
            StoryEvidenceReview(
                story_id=score.story_id,
                evidence_strength=0.0,
                fit_summary="No official-source review was recorded for this story.",
                gap_summary="No evidence review available.",
                sources=(),
            ),
        )
        appendix_penalty = 0.10 if story.appendix_only else 0.0
        model_component = normalized_model_score(score)
        blended_score = 0.60 * model_component + 0.40 * evidence.evidence_strength - appendix_penalty
        ranked.append((blended_score, model_component, evidence.evidence_strength, score, evidence))

    blended_score, model_component, evidence_strength, score, evidence = max(
        ranked,
        key=lambda item: (item[0], item[2], item[3].total_score),
    )
    rationale = (
        f"{score.title} is the strongest balanced demo story because it pairs a strong screened model separation "
        f"({score.total_score:.3f}) with current official-source support ({evidence_strength:.2f}). "
        f"{score.interpretation or evidence.fit_summary} {evidence.fit_summary}"
    )
    return StoryRecommendation(
        story_id=score.story_id,
        title=score.title,
        blended_score=blended_score,
        model_score=score.total_score,
        model_score_normalized=model_component,
        evidence_strength=evidence_strength,
        rationale=rationale,
        caveat=V41_VALIDATION_CAVEAT,
    )
