"""Apresentação em console de resultados já produzidos pelo pipeline."""

from __future__ import annotations

from assistente_oportunidades.services.pipeline import PipelineOpportunity, PipelineResult
from assistente_oportunidades.services.profile_matcher import EducationCompatibility


_EDUCATION_LABELS = {
    EducationCompatibility.COMPATIVEL: "Compatível",
    EducationCompatibility.INCOMPATIVEL: "Incompatível",
    EducationCompatibility.NAO_INFORMADO: "Não informado",
}


def render_console_report(result: PipelineResult, top_n: int = 10) -> str:
    """Renderiza os dados já avaliados, preservando a ordem e os valores recebidos."""
    if top_n < 0:
        raise ValueError("top_n não pode ser negativo.")

    ranked = result.ranked_opportunities
    displayed = ranked[:top_n]
    collection = result.collection
    lines = [
        "RESUMO DA EXECUÇÃO",
        f"Vagas recebidas na coleta atual: {collection.received}",
        f"Novas: {collection.inserted}",
        f"Atualizadas: {collection.updated}",
        f"Oportunidades confirmadas como estágio e ranqueadas no inventário: {len(ranked)}",
        f"Oportunidades exibidas: {len(displayed)}",
        "O ranking considera o inventário persistido no banco, não somente a coleta atual.",
        "",
        f"TOP OPORTUNIDADES (até {top_n})",
    ]

    if not displayed:
        lines.append("Nenhuma oportunidade de estágio confirmada para exibição.")
        return "\n".join(lines)

    for opportunity in displayed:
        lines.extend(_render_opportunity(opportunity))
    return "\n".join(lines)


def _render_opportunity(opportunity: PipelineOpportunity) -> list[str]:
    job = opportunity.job
    match = opportunity.match
    location_work = opportunity.score.location_work_assessment
    found_skills = match.skills_found_in_job
    matched_skills = match.matched_profile_skills
    if matched_skills:
        skills_label = ", ".join(matched_skills)
    elif found_skills:
        skills_label = "Nenhuma correspondente ao perfil"
    else:
        skills_label = "Não identificadas"

    model_label = ", ".join(location_work.detected_work_models) or "Não identificado"
    location_label = job.location or "Não informado"
    explanation = " ".join(opportunity.score.explicacao) or "Não informada"

    return [
        "",
        "-" * 72,
        f"#{opportunity.position} — {job.title or 'Não informado'}",
        f"Empresa: {job.company or 'Não informado'}",
        f"Score: {_format_score(opportunity.score.score_total)}",
        f"Área: {opportunity.area.category.value}",
        f"Skills compatíveis: {skills_label}",
        f"Formação: {_EDUCATION_LABELS[match.education.compatibility]}",
        f"Localização: {location_label}",
        f"Modelo de trabalho: {model_label}",
        f"Compatibilidade: {explanation}",
        f"Link: {job.url or 'Não informado'}",
    ]


def _format_score(value: float) -> str:
    return f"{value:.2f}".replace(".", ",")
