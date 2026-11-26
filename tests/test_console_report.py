from assistente_oportunidades import cli
from assistente_oportunidades.models import Job
from assistente_oportunidades.services.area_classifier import AreaCategory, AreaClassificationResult
from assistente_oportunidades.services.collect import CollectionSummary
from assistente_oportunidades.services.internship_classifier import (
    InternshipClassification,
    InternshipClassificationResult,
)
from assistente_oportunidades.services.pipeline import PipelineOpportunity, PipelineResult
from assistente_oportunidades.services.profile_matcher import (
    AreaAlignment,
    EducationCompatibility,
    EducationMatch,
    ProfileMatchResult,
)
from assistente_oportunidades.services.score import (
    CompatibilityScore,
    FitStatus,
    LocationWorkAssessment,
)
from assistente_oportunidades.reports.console import render_console_report


def _opportunity(
    position: int,
    identifier: str,
    score: float,
    *,
    company: str | None = "Empresa Exemplo",
    location: str | None = "São Paulo, SP",
    skills_found: tuple[str, ...] = ("SQL", "Tableau"),
    matched_skills: tuple[str, ...] = ("SQL",),
    education: EducationCompatibility = EducationCompatibility.COMPATIVEL,
    detected_models: tuple[str, ...] = ("híbrido",),
    explanation: tuple[str, ...] = ("Score calculado a partir dos componentes disponíveis.",),
) -> PipelineOpportunity:
    job = Job(
        source="test",
        external_id=identifier,
        title=f"Estágio em Dados {identifier}",
        company=company,
        location=location,
        description=None,
        url=f"https://jobs.example/{identifier}?redirect=%2Fapply",
    )
    internship = InternshipClassificationResult(
        InternshipClassification.ESTAGIO,
        "O título contém marcador de estágio.",
        True,
        False,
    )
    area = AreaClassificationResult(
        AreaCategory.DADOS_ANALYTICS,
        "Área já classificada pelo pipeline.",
        ("dados",),
    )
    match = ProfileMatchResult(
        area=AreaCategory.DADOS_ANALYTICS,
        area_alignment=AreaAlignment.ALTA,
        skills_found_in_job=skills_found,
        matched_profile_skills=matched_skills,
        requirements_not_in_profile=tuple(
            skill for skill in skills_found if skill not in matched_skills
        ),
        education=EducationMatch(education, None, "Formação previamente avaliada."),
        explanation=("Matcher executado pelo pipeline.",),
    )
    location_work = LocationWorkAssessment(
        location_status=(FitStatus.COMPATIVEL if location else FitStatus.NAO_INFORMADO),
        work_model_status=(
            FitStatus.COMPATIVEL if detected_models else FitStatus.NAO_INFORMADO
        ),
        detected_work_models=detected_models,
        matched_location=location,
        points=10 if location and detected_models else 5,
        explanation="Localização/modelo já avaliados.",
    )
    score_result = CompatibilityScore(
        score_total=score,
        score_area=40,
        score_habilidades=25,
        score_formacao=15,
        score_localizacao=10,
        habilidades_contribuintes=matched_skills,
        requisitos_sem_correspondencia=match.requirements_not_in_profile,
        location_work_assessment=location_work,
        explicacao=explanation,
    )
    return PipelineOpportunity(position, job, internship, area, match, score_result)


def _result(*opportunities: PipelineOpportunity) -> PipelineResult:
    return PipelineResult(
        collection=CollectionSummary(received=63, inserted=35, updated=28),
        ranked_opportunities=opportunities,
    )


def test_report_shows_collection_and_persisted_inventory_summary():
    opportunities = tuple(
        _opportunity(position, f"job-{position}", 87.25)
        for position in range(1, 70)
    )
    report = render_console_report(_result(*opportunities))

    assert "Vagas recebidas na coleta atual: 63" in report
    assert "Novas: 35" in report
    assert "Atualizadas: 28" in report
    assert "Oportunidades confirmadas como estágio e ranqueadas no inventário: 69" in report
    assert "Oportunidades exibidas: 10" in report
    assert "inventário persistido no banco, não somente a coleta atual" in report


def test_report_limits_count_and_preserves_ranking_order():
    first = _opportunity(1, "first", 77.5)
    second = _opportunity(2, "second", 65)
    third = _opportunity(3, "third", 45)

    report = render_console_report(_result(first, second, third), top_n=2)

    assert "Oportunidades exibidas: 2" in report
    assert "#1 — Estágio em Dados first" in report
    assert "#2 — Estágio em Dados second" in report
    assert "Estágio em Dados third" not in report
    assert report.index("#1 —") < report.index("#2 —")


def test_report_displays_pipeline_score_and_job_fields_without_rewriting_link():
    opportunity = _opportunity(4, "job-4", 87.25)

    report = render_console_report(_result(opportunity))

    assert "Score: 87,25" in report
    assert "Estágio em Dados job-4" in report
    assert "Empresa: Empresa Exemplo" in report
    assert "Área: DADOS_ANALYTICS" in report
    assert "Skills compatíveis: SQL" in report
    assert "Formação: Compatível" in report
    assert "Compatibilidade: Score calculado a partir dos componentes disponíveis." in report
    assert "Link: https://jobs.example/job-4?redirect=%2Fapply" in report


def test_report_labels_missing_information_without_inventing_values():
    opportunity = _opportunity(
        1,
        "missing",
        50,
        company=None,
        location=None,
        skills_found=(),
        matched_skills=(),
        education=EducationCompatibility.NAO_INFORMADO,
        detected_models=(),
        explanation=(),
    )

    report = render_console_report(_result(opportunity))

    assert "Empresa: Não informado" in report
    assert "Skills compatíveis: Não identificadas" in report
    assert "Formação: Não informado" in report
    assert "Localização: Não informado" in report
    assert "Modelo de trabalho: Não identificado" in report
    assert "Compatibilidade: Não informada" in report
    assert "None" not in report


def test_report_does_not_mutate_received_objects():
    opportunity = _opportunity(1, "stable", 87.25)
    result = _result(opportunity)
    original_values = (
        opportunity.position,
        opportunity.job.title,
        opportunity.job.company,
        opportunity.job.url,
        opportunity.area.category,
        opportunity.match,
        opportunity.score,
    )

    render_console_report(result, top_n=1)

    assert result.ranked_opportunities == (opportunity,)
    assert (
        opportunity.position,
        opportunity.job.title,
        opportunity.job.company,
        opportunity.job.url,
        opportunity.area.category,
        opportunity.match,
        opportunity.score,
    ) == original_values


def test_empty_report_displays_zero_counts_and_empty_state():
    result = PipelineResult(CollectionSummary(0, 0, 0), ())

    report = render_console_report(result)

    assert "Oportunidades confirmadas como estágio e ranqueadas no inventário: 0" in report
    assert "Oportunidades exibidas: 0" in report
    assert "Nenhuma oportunidade de estágio confirmada para exibição." in report


def test_run_cli_uses_console_report_without_real_collection(monkeypatch, capsys):
    result = _result(_opportunity(1, "cli", 88))
    monkeypatch.setattr(cli, "load_config", lambda **_kwargs: object())
    monkeypatch.setattr(cli, "load_candidate_profile", lambda *_args: object())
    monkeypatch.setattr(cli, "run_pipeline", lambda _config, _profile: result)

    exit_code = cli.main(["run", "--top-n", "1"])

    output = capsys.readouterr()
    assert exit_code == 0
    assert "RESUMO DA EXECUÇÃO" in output.out
    assert "TOP OPORTUNIDADES" in output.out
    assert "#1 — Estágio em Dados cli" in output.out
    assert output.err == ""
