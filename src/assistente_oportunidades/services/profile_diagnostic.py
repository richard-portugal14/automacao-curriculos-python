"""Diagnóstico do profile matcher sobre vagas já confirmadas como estágio."""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from pathlib import Path

from assistente_oportunidades.models import Job
from assistente_oportunidades.services.area_classifier import (
    AreaCategory,
    AreaClassificationResult,
    classify_area,
)
from assistente_oportunidades.services.internship_classifier import InternshipClassification
from assistente_oportunidades.services.internship_diagnostic import diagnose_stored_jobs
from assistente_oportunidades.services.profile_matcher import (
    CandidateProfile,
    EducationCompatibility,
    ProfileMatchResult,
    load_candidate_profile,
    match_profile,
)


@dataclass(frozen=True, slots=True)
class ProfileDiagnosedJob:
    job: Job
    area: AreaClassificationResult
    match: ProfileMatchResult


@dataclass(frozen=True, slots=True)
class ProfileDiagnosticReport:
    total: int
    with_skill_matches: int
    without_skill_matches: int
    education_counts: dict[EducationCompatibility, int]
    area_counts: dict[AreaCategory, int]
    results: list[ProfileDiagnosedJob]


def diagnose_stored_profile(
    database_path: Path | str,
    profile: CandidateProfile | None = None,
) -> ProfileDiagnosticReport:
    """Compara apenas estágios confirmados, sem gravar resultado no banco."""
    candidate = profile or load_candidate_profile()
    internship_report = diagnose_stored_jobs(database_path)
    confirmed = [
        item.job
        for item in internship_report.confirmed
        if item.result.classification is InternshipClassification.ESTAGIO
    ]

    results: list[ProfileDiagnosedJob] = []
    education_counts = Counter({status: 0 for status in EducationCompatibility})
    area_counts = Counter({category: 0 for category in AreaCategory})
    with_skill_matches = 0

    for job in confirmed:
        area_result = classify_area(job)
        match = match_profile(job, area_result.category, candidate)
        results.append(ProfileDiagnosedJob(job, area_result, match))
        area_counts[area_result.category] += 1
        education_counts[match.education.compatibility] += 1
        if match.matched_profile_skills:
            with_skill_matches += 1

    total = len(results)
    return ProfileDiagnosticReport(
        total=total,
        with_skill_matches=with_skill_matches,
        without_skill_matches=total - with_skill_matches,
        education_counts=dict(education_counts),
        area_counts=dict(area_counts),
        results=results,
    )
