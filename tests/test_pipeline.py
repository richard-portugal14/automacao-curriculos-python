from pathlib import Path
from datetime import datetime, timedelta, timezone

from assistente_oportunidades.config import AppConfig, SearchConfig
from assistente_oportunidades.models import Job
from assistente_oportunidades.repositories.jobs import JobRepository
from assistente_oportunidades.services import pipeline
from assistente_oportunidades.services.area_classifier import AreaCategory
from assistente_oportunidades.services.collect import CollectionSummary
from assistente_oportunidades.services.internship_classifier import InternshipClassification
from assistente_oportunidades.services.profile_matcher import CandidateProfile
from assistente_oportunidades.reports.console import render_console_report


def _config(database: Path) -> AppConfig:
    return AppConfig(
        profile={},
        preferences={},
        search=SearchConfig("br", ("estágio dados",), ("São Paulo",)),
        app_id="fake-id",
        app_key="fake-key",
        database_path=database,
    )


def _profile() -> CandidateProfile:
    return CandidateProfile(
        education="Ciência da Computação — superior incompleto",
        skills=("SQL", "Excel", "Python"),
        area_priorities=(AreaCategory.DADOS_ANALYTICS, AreaCategory.BI),
        locations=("São Paulo",),
        work_models=("presencial", "híbrido", "remoto"),
    )


def _job(external_id: str, title: str, description: str) -> Job:
    return Job(
        source="test",
        external_id=external_id,
        title=title,
        company=f"Empresa {external_id}",
        location="São Paulo",
        description=description,
        url=f"https://example.test/{external_id}",
    )


def _controlled_collector(jobs: list[Job], events: list[str] | None = None):
    def collect(config: AppConfig) -> CollectionSummary:
        if events is not None:
            events.append("collect")
        inserted = 0
        with JobRepository(config.database_path) as repository:
            for job in jobs:
                inserted += repository.save(job)
        return CollectionSummary(len(jobs), inserted, len(jobs) - inserted)

    return collect


def test_end_to_end_pipeline_persists_evaluates_ranks_and_reports_controlled_jobs(
    tmp_path: Path,
):
    database = tmp_path / "jobs.sqlite3"
    data_job = _job(
        "data",
        "Estágio em Dados",
        "Conhecimento em SQL, Excel e Python. Cursando Ciência da Computação. "
        "Modalidade híbrida.",
    )
    bi_job = _job("bi", "Estágio em BI", "Apoio em dashboards e relatórios.")
    full_time_job = _job(
        "full-time", "Analista de Dados Pleno", "Experiência em SQL e Python."
    )
    uncertain_job = _job(
        "uncertain", "Programa de Talentos", "A descrição menciona estágio."
    )
    jobs = [data_job, bi_job, full_time_job, uncertain_job, data_job]

    result = pipeline.run_pipeline(
        _config(database), _profile(), collector=_controlled_collector(jobs)
    )

    assert result.collection == CollectionSummary(5, 4, 1)
    assert len(result.ranked_opportunities) == 2
    first, second = result.ranked_opportunities
    assert first.position == 1
    assert first.job.external_id == "data"
    assert first.job.title == "Estágio em Dados"
    assert first.job.company == "Empresa data"
    assert first.job.url == "https://example.test/data"
    assert first.internship.classification is InternshipClassification.ESTAGIO
    assert first.area.category is AreaCategory.DADOS_ANALYTICS
    assert set(first.match.matched_profile_skills) == {"SQL", "Excel", "Python"}
    assert first.score.score_total == 100
    assert first.score.explicacao
    assert first.position < second.position
    assert second.job.external_id == "bi"
    assert second.area.category is AreaCategory.BI
    assert second.score.score_total < first.score.score_total
    assert len({item.job.deduplication_key for item in result.ranked_opportunities}) == 2

    report = render_console_report(result)

    assert "Vagas recebidas na coleta atual: 5" in report
    assert "Novas: 4" in report
    assert "Atualizadas: 1" in report
    assert "Oportunidades confirmadas como estágio e ranqueadas no inventário: 2" in report
    assert "#1 — Estágio em Dados" in report
    assert "Score: 100,00" in report
    assert "Área: DADOS_ANALYTICS" in report
    skill_line = next(
        line for line in report.splitlines() if line.startswith("Skills compatíveis:")
    )
    assert all(skill in skill_line for skill in ("SQL", "Excel", "Python"))
    assert "Link: https://example.test/data" in report
    assert "Analista de Dados Pleno" not in report
    assert report.count("Link: https://example.test/data") == 1


def test_pipeline_calls_existing_services_in_order(monkeypatch, tmp_path: Path):
    events: list[str] = []
    jobs = [
        _job("stage", "Estágio em Dados", "Conhecimento em SQL."),
        _job("non-stage", "Analista Pleno", "Experiência em SQL."),
    ]
    original_internship = pipeline.classify_internship
    original_area = pipeline.classify_area
    original_match = pipeline.match_profile
    original_score = pipeline.calculate_compatibility_score
    original_rank = pipeline.rank_opportunities

    def classify_internship(job):
        events.append(f"internship:{job.external_id}")
        return original_internship(job)

    def classify_area(job):
        events.append(f"area:{job.external_id}")
        return original_area(job)

    def match_profile(job, area, profile):
        events.append(f"matcher:{job.external_id}")
        return original_match(job, area, profile)

    def calculate_score(job, area, match, profile):
        events.append(f"score:{job.external_id}")
        return original_score(job, area, match, profile)

    def rank_opportunities(opportunities):
        events.append("ranking")
        return original_rank(opportunities)

    monkeypatch.setattr(pipeline, "classify_internship", classify_internship)
    monkeypatch.setattr(pipeline, "classify_area", classify_area)
    monkeypatch.setattr(pipeline, "match_profile", match_profile)
    monkeypatch.setattr(pipeline, "calculate_compatibility_score", calculate_score)
    monkeypatch.setattr(pipeline, "rank_opportunities", rank_opportunities)

    result = pipeline.run_pipeline(
        _config(tmp_path / "ordered.sqlite3"),
        _profile(),
        collector=_controlled_collector(jobs, events),
    )

    assert events == [
        "collect",
        "internship:stage",
        "area:stage",
        "matcher:stage",
        "score:stage",
        "internship:non-stage",
        "ranking",
    ]
    assert len(result.ranked_opportunities) == 1


def test_empty_pipeline_returns_no_ranked_opportunities(tmp_path: Path):
    result = pipeline.run_pipeline(
        _config(tmp_path / "empty.sqlite3"),
        _profile(),
        collector=_controlled_collector([]),
    )

    assert result.collection == CollectionSummary(0, 0, 0)
    assert result.ranked_opportunities == ()
    assert "Nenhuma oportunidade de estágio confirmada" in render_console_report(result)


def test_single_controlled_vacancy_runs_through_pipeline_and_report(tmp_path: Path):
    job = _job("single", "Estágio em Dados", "Conhecimento em SQL.")

    result = pipeline.run_pipeline(
        _config(tmp_path / "single.sqlite3"),
        _profile(),
        collector=_controlled_collector([job]),
    )
    report = render_console_report(result)

    assert result.collection == CollectionSummary(1, 1, 0)
    assert len(result.ranked_opportunities) == 1
    assert result.ranked_opportunities[0].position == 1
    assert "Oportunidades confirmadas como estágio e ranqueadas no inventário: 1" in report
    assert "Link: https://example.test/single" in report


def test_expired_vacancy_stays_in_database_but_is_not_ranked(tmp_path: Path):
    database = tmp_path / "expired.sqlite3"
    recent = _job("recent", "Estágio em Dados", "Conhecimento em SQL.")
    expired = _job("expired", "Estágio em BI", "Conhecimento em Excel.")
    expired.published_at = datetime.now(timezone.utc) - timedelta(days=31)

    result = pipeline.run_pipeline(
        _config(database),
        _profile(),
        collector=_controlled_collector([recent, expired]),
    )

    assert [item.job.external_id for item in result.ranked_opportunities] == ["recent"]
    with JobRepository(database) as repository:
        assert repository.get("test:expired") is not None
        stored = {job.external_id: job for job in repository.list_all()}
    assert stored["expired"].published_at == expired.published_at
    assert stored["recent"].collected_at <= datetime.now(timezone.utc)
