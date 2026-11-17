"""Classificação determinística de vagas de estágio, isolada da coleta e do ranking."""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from enum import Enum
from typing import Iterable

from assistente_oportunidades.models import Job


class InternshipClassification(str, Enum):
    ESTAGIO = "ESTAGIO"
    NAO_ESTAGIO = "NAO_ESTAGIO"
    INCERTO = "INCERTO"


@dataclass(frozen=True, slots=True)
class InternshipClassificationResult:
    classification: InternshipClassification
    explanation: str
    title_has_internship_marker: bool
    description_has_internship_marker: bool


@dataclass(frozen=True, slots=True)
class InternshipFilterResult:
    eligible: list[Job]
    rejected_count: int
    uncertain_count: int
    diagnostics: list[tuple[Job, InternshipClassificationResult]]


_INTERNSHIP_MARKER = re.compile(
    r"\b(?:estag(?:io|iari[oa])s?|intern(?:ship)?s?)\b",
    re.IGNORECASE,
)
_GENERIC_TITLE_MARKER = re.compile(
    r"\b(?:programa de (?:talentos|formacao|desenvolvimento)|"
    r"jovem talento|young talent|talent program|graduate program|career program|"
    r"oportunidade(?:s)?)\b",
    re.IGNORECASE,
)


def classify_internship(job: Job) -> InternshipClassificationResult:
    """Classifica estágio dando prioridade ao título sobre menções na descrição."""
    title = _normalize(job.title)
    description = _normalize(job.description or "")
    title_match = bool(_INTERNSHIP_MARKER.search(title))
    description_match = bool(_INTERNSHIP_MARKER.search(description))

    if title_match:
        return InternshipClassificationResult(
            InternshipClassification.ESTAGIO,
            "O título contém um marcador explícito de estágio.",
            True,
            description_match,
        )

    if not title:
        return InternshipClassificationResult(
            InternshipClassification.INCERTO,
            "O título está ausente; a descrição sozinha não confirma estágio."
            if description_match
            else "Não há título nem evidência suficiente para confirmar o tipo da vaga.",
            False,
            description_match,
        )

    if _GENERIC_TITLE_MARKER.search(title):
        explanation = (
            "O título é genérico e o marcador de estágio aparece somente na descrição."
            if description_match
            else "O título é genérico e não permite determinar se a vaga é de estágio."
        )
        return InternshipClassificationResult(
            InternshipClassification.INCERTO,
            explanation,
            False,
            description_match,
        )

    explanation = (
        "O título não indica estágio; a menção na descrição pode ser contextual e não confirma a vaga."
        if description_match
        else "O título não contém marcador explícito de estágio."
    )
    return InternshipClassificationResult(
        InternshipClassification.NAO_ESTAGIO,
        explanation,
        False,
        description_match,
    )


def filter_internships(jobs: Iterable[Job]) -> InternshipFilterResult:
    """Mantém somente estágios confirmados e contabiliza os demais para diagnóstico."""
    eligible: list[Job] = []
    diagnostics: list[tuple[Job, InternshipClassificationResult]] = []
    rejected_count = uncertain_count = 0

    for job in jobs:
        result = classify_internship(job)
        if result.classification is InternshipClassification.ESTAGIO:
            eligible.append(job)
        else:
            diagnostics.append((job, result))
            if result.classification is InternshipClassification.NAO_ESTAGIO:
                rejected_count += 1
            else:
                uncertain_count += 1

    return InternshipFilterResult(eligible, rejected_count, uncertain_count, diagnostics)


def _normalize(text: str) -> str:
    decomposed = unicodedata.normalize("NFKD", text.casefold())
    without_accents = "".join(char for char in decomposed if not unicodedata.combining(char))
    return re.sub(r"[^a-z0-9]+", " ", without_accents).strip()
