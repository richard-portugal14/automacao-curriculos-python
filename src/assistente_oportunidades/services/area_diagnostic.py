"""Diagnóstico da classificação de área para vagas confirmadas como estágio."""

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
from assistente_oportunidades.services.internship_diagnostic import diagnose_stored_jobs


@dataclass(frozen=True, slots=True)
class AreaClassifiedJob:
    job: Job
    result: AreaClassificationResult


@dataclass(frozen=True, slots=True)
class AreaDiagnosticReport:
    total: int
    counts: dict[AreaCategory, int]
    percentages: dict[AreaCategory, float]
    classified_jobs: list[AreaClassifiedJob]


def diagnose_stored_areas(database_path: Path | str) -> AreaDiagnosticReport:
    """Classifica somente vagas ESTAGIO lidas do SQLite, sem gravar resultados."""
    internship_report = diagnose_stored_jobs(database_path)
    counts = Counter({category: 0 for category in AreaCategory})
    classified_jobs: list[AreaClassifiedJob] = []

    for internship in internship_report.confirmed:
        result = classify_area(internship.job)
        counts[result.category] += 1
        classified_jobs.append(AreaClassifiedJob(internship.job, result))

    total = len(classified_jobs)
    percentages = {
        category: (counts[category] / total * 100 if total else 0.0)
        for category in AreaCategory
    }
    return AreaDiagnosticReport(
        total=total,
        counts=dict(counts),
        percentages=percentages,
        classified_jobs=classified_jobs,
    )
