"""Diagnóstico de score sobre vagas existentes, sem persistir resultados."""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from pathlib import Path

from assistente_oportunidades.models import Job
from assistente_oportunidades.services.area_classifier import AreaCategory, AreaClassificationResult
from assistente_oportunidades.services.profile_diagnostic import diagnose_stored_profile
from assistente_oportunidades.services.profile_matcher import (
    CandidateProfile,
    ProfileMatchResult,
    load_candidate_profile,
)
from assistente_oportunidades.services.score import CompatibilityScore, calculate_compatibility_score


SCORE_BANDS = ("90-100", "80-89", "70-79", "60-69", "50-59", "0-49")


@dataclass(frozen=True, slots=True)
class ScoreDiagnosedJob:
    job: Job
    area: AreaClassificationResult
    match: ProfileMatchResult
    score: CompatibilityScore


@dataclass(frozen=True, slots=True)
class ScoreDiagnosticReport:
    total: int
    average: float | None
    maximum: float | None
    minimum: float | None
    score_band_counts: dict[str, int]
    area_counts: dict[AreaCategory, int]
    results: list[ScoreDiagnosedJob]


def diagnose_stored_scores(
    database_path: Path | str,
    profile: CandidateProfile | None = None,
) -> ScoreDiagnosticReport:
    """Calcula e resume o score apenas para vagas ESTAGIO já armazenadas."""
    candidate = profile or load_candidate_profile()
    profile_report = diagnose_stored_profile(database_path, candidate)
    results = [
        ScoreDiagnosedJob(
            item.job,
            item.area,
            item.match,
            calculate_compatibility_score(item.job, item.area, item.match, candidate),
        )
        for item in profile_report.results
    ]
    scores = [item.score.score_total for item in results]
    bands = Counter({band: 0 for band in SCORE_BANDS})
    area_counts = Counter({area: 0 for area in AreaCategory})
    for item in results:
        bands[score_band(item.score.score_total)] += 1
        area_counts[item.area.category] += 1

    return ScoreDiagnosticReport(
        total=len(results),
        average=sum(scores) / len(scores) if scores else None,
        maximum=max(scores) if scores else None,
        minimum=min(scores) if scores else None,
        score_band_counts=dict(bands),
        area_counts=dict(area_counts),
        results=results,
    )


def score_band(score: float) -> str:
    """Retorna a faixa inclusiva no limite inferior, com intervalos de dez pontos."""
    if not 0 <= score <= 100:
        raise ValueError("O score deve estar entre 0 e 100.")
    if score >= 90:
        return "90-100"
    if score >= 80:
        return "80-89"
    if score >= 70:
        return "70-79"
    if score >= 60:
        return "60-69"
    if score >= 50:
        return "50-59"
    return "0-49"
