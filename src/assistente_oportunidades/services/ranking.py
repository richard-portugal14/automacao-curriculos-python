"""Ordenação determinística de oportunidades já avaliadas."""

from __future__ import annotations

from collections.abc import Iterable
from typing import Protocol, TypeVar

from assistente_oportunidades.models import Job
from assistente_oportunidades.services.area_classifier import AreaCategory, AreaClassificationResult
from assistente_oportunidades.services.profile_matcher import (
    EducationCompatibility,
    ProfileMatchResult,
)
from assistente_oportunidades.services.score import CompatibilityScore


class EvaluatedOpportunity(Protocol):
    """Dados estruturados já calculados que o ranking pode usar."""

    job: Job
    area: AreaClassificationResult
    match: ProfileMatchResult
    score: CompatibilityScore


T = TypeVar("T", bound=EvaluatedOpportunity)

_AREA_PRIORITY = {
    AreaCategory.DADOS_ANALYTICS: 0,
    AreaCategory.BI: 1,
    AreaCategory.TI_DADOS: 2,
    AreaCategory.TI_GERAL: 3,
    AreaCategory.OUTRA: 4,
}
_EDUCATION_PRIORITY = {
    EducationCompatibility.COMPATIVEL: 0,
    EducationCompatibility.NAO_INFORMADO: 1,
    EducationCompatibility.INCOMPATIVEL: 2,
}


def rank_opportunities(opportunities: Iterable[T]) -> list[T]:
    """Ordena sem recalcular ou alterar avaliações; empates finais preservam a entrada.

    Critérios em ordem: score total decrescente, prioridade da área, quantidade
    de skills compatíveis e compatibilidade de formação. O sort estável mantém
    a ordem de entrada quando todos esses valores empatam.
    """
    return sorted(opportunities, key=_ranking_key)


def _ranking_key(opportunity: EvaluatedOpportunity) -> tuple[float, int, int, int]:
    return (
        -opportunity.score.score_total,
        _AREA_PRIORITY[opportunity.area.category],
        -len(opportunity.match.matched_profile_skills),
        _EDUCATION_PRIORITY[opportunity.match.education.compatibility],
    )
