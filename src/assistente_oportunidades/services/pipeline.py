"""Orquestra coleta, avaliação e ordenação sem duplicar as regras dos serviços."""

from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Callable

from assistente_oportunidades.config import AppConfig
from assistente_oportunidades.models import Job
from assistente_oportunidades.repositories.jobs import JobRepository
from assistente_oportunidades.services.area_classifier import (
    AreaClassificationResult,
    classify_area,
)
from assistente_oportunidades.services.collect import CollectionSummary, collect_adzuna
from assistente_oportunidades.services.freshness import is_job_within_age_limit
from assistente_oportunidades.services.internship_classifier import (
    InternshipClassification,
    InternshipClassificationResult,
    classify_internship,
)
from assistente_oportunidades.services.profile_matcher import (
    CandidateProfile,
    ProfileMatchResult,
    load_candidate_profile,
    match_profile,
)
from assistente_oportunidades.services.ranking import rank_opportunities
from assistente_oportunidades.services.score import (
    CompatibilityScore,
    calculate_compatibility_score,
)


@dataclass(frozen=True, slots=True)
class PipelineOpportunity:
    position: int
    job: Job
    internship: InternshipClassificationResult
    area: AreaClassificationResult
    match: ProfileMatchResult
    score: CompatibilityScore


@dataclass(frozen=True, slots=True)
class PipelineResult:
    collection: CollectionSummary
    ranked_opportunities: tuple[PipelineOpportunity, ...]


Collector = Callable[[AppConfig], CollectionSummary]


def run_pipeline(
    config: AppConfig,
    profile: CandidateProfile | None = None,
    *,
    collector: Collector | None = None,
) -> PipelineResult:
    """Coleta, carrega vagas deduplicadas e executa os serviços em sequência."""
    collection = (collector or collect_adzuna)(config)
    candidate = profile or load_candidate_profile()

    with JobRepository(config.database_path) as repository:
        jobs = repository.list_all()

    evaluated: list[PipelineOpportunity] = []
    for job in jobs:
        if not is_job_within_age_limit(job, config.search.max_days_old):
            continue
        internship = classify_internship(job)
        if internship.classification is not InternshipClassification.ESTAGIO:
            continue

        area = classify_area(job)
        match = match_profile(job, area.category, candidate)
        score = calculate_compatibility_score(job, area, match, candidate)
        evaluated.append(PipelineOpportunity(0, job, internship, area, match, score))

    ordered = rank_opportunities(evaluated)
    ranked = tuple(
        replace(opportunity, position=position)
        for position, opportunity in enumerate(ordered, start=1)
    )
    return PipelineResult(collection=collection, ranked_opportunities=ranked)
