"""Diagnóstico da classificação sobre vagas já persistidas, em modo somente leitura."""

from __future__ import annotations

import sqlite3
from collections import Counter
from dataclasses import dataclass
from pathlib import Path

from assistente_oportunidades.models import Job
from assistente_oportunidades.services.internship_classifier import (
    InternshipClassification,
    InternshipClassificationResult,
    classify_internship,
)


@dataclass(frozen=True, slots=True)
class ClassifiedJob:
    job: Job
    result: InternshipClassificationResult


@dataclass(frozen=True, slots=True)
class InternshipDiagnosticReport:
    total: int
    counts: dict[InternshipClassification, int]
    percentages: dict[InternshipClassification, float]
    confirmed: list[ClassifiedJob]
    uncertain: list[ClassifiedJob]


def diagnose_stored_jobs(database_path: Path | str) -> InternshipDiagnosticReport:
    """Classifica todas as vagas armazenadas sem modificar o banco nem consultar fontes."""
    database = Path(database_path).expanduser().resolve()
    if not database.is_file():
        raise FileNotFoundError(f"Banco de dados não encontrado: {database}")

    uri = f"{database.as_uri()}?mode=ro"
    with sqlite3.connect(uri, uri=True) as connection:
        connection.row_factory = sqlite3.Row
        rows = connection.execute(
            """SELECT source, external_id, title, company, location, description, url
            FROM jobs
            ORDER BY id"""
        ).fetchall()

    classified: list[ClassifiedJob] = []
    counts = Counter({classification: 0 for classification in InternshipClassification})
    for row in rows:
        job = Job(
            source=row["source"],
            external_id=row["external_id"],
            title=row["title"],
            company=row["company"],
            location=row["location"],
            description=row["description"],
            url=row["url"],
        )
        result = classify_internship(job)
        counts[result.classification] += 1
        classified.append(ClassifiedJob(job, result))

    total = len(classified)
    percentages = {
        classification: (counts[classification] / total * 100 if total else 0.0)
        for classification in InternshipClassification
    }
    return InternshipDiagnosticReport(
        total=total,
        counts=dict(counts),
        percentages=percentages,
        confirmed=[
            item for item in classified
            if item.result.classification is InternshipClassification.ESTAGIO
        ],
        uncertain=[
            item for item in classified
            if item.result.classification is InternshipClassification.INCERTO
        ],
    )
