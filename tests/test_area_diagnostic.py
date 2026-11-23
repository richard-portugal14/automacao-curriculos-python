from pathlib import Path

import pytest

from assistente_oportunidades import cli
from assistente_oportunidades.models import Job
from assistente_oportunidades.repositories.jobs import JobRepository
from assistente_oportunidades.services.area_classifier import AreaCategory
from assistente_oportunidades.services.area_diagnostic import diagnose_stored_areas


def _save_job(
    repository: JobRepository,
    external_id: str,
    title: str,
    description: str,
    company: str,
) -> None:
    repository.save(
        Job(
            source="adzuna",
            external_id=external_id,
            title=title,
            company=company,
            location="São Paulo",
            description=description,
            url=f"https://example.test/{external_id}",
        )
    )


def test_area_diagnostic_processes_only_internship_classified_jobs(tmp_path: Path):
    database = tmp_path / "jobs.sqlite3"
    with JobRepository(database) as repository:
        _save_job(repository, "intern", "Estágio em Dados", "SQL", "Empresa A")
        _save_job(repository, "not-intern", "Analista de Dados Pleno", "SQL", "Empresa B")
        _save_job(repository, "uncertain", "Programa de Talentos", "Dados", "Empresa C")

    report = diagnose_stored_areas(database)

    assert report.total == 1
    assert report.counts[AreaCategory.DADOS_ANALYTICS] == 1
    assert report.classified_jobs[0].job.company == "Empresa A"


def test_area_diagnostic_summary_percentages_match_category_counts(tmp_path: Path):
    database = tmp_path / "jobs.sqlite3"
    with JobRepository(database) as repository:
        _save_job(repository, "data", "Estágio em Dados", "SQL", "Empresa A")
        _save_job(repository, "bi", "Estágio em BI", "Dashboards", "Empresa B")
        _save_job(repository, "other", "Estágio em Marketing", "Campanhas", "Empresa C")
        _save_job(repository, "fulltime", "Analista Pleno", "Business Intelligence", "Empresa D")

    report = diagnose_stored_areas(database)

    assert report.total == sum(report.counts.values()) == 3
    assert sum(report.percentages.values()) == pytest.approx(100)
    assert report.counts[AreaCategory.DADOS_ANALYTICS] == 1
    assert report.counts[AreaCategory.BI] == 1
    assert report.counts[AreaCategory.OUTRA] == 1


def test_area_diagnostic_cli_prints_complete_independent_records(capsys, tmp_path: Path):
    database = tmp_path / "jobs.sqlite3"
    with JobRepository(database) as repository:
        _save_job(repository, "data", "Estágio em Dados", "SQL", "Empresa A")
        _save_job(repository, "bi", "Estágio em BI", "Power BI", "Empresa B")
        _save_job(repository, "fulltime", "Analista Pleno", "SQL", "Empresa C")

    result = cli.main(["diagnose-areas", "--database", str(database)])
    output = capsys.readouterr()
    records = [
        block for block in output.out.split("\n\n") if block.startswith("Registro ")
    ]

    assert result == 0
    assert "Total de vagas analisadas: 2" in output.out
    assert "DADOS_ANALYTICS: 1 (50.0%)" in output.out
    assert "BI: 1 (50.0%)" in output.out
    assert len(records) == 2
    assert "Título: Estágio em Dados" in records[0]
    assert "Empresa: Empresa A" in records[0]
    assert "Área: DADOS_ANALYTICS" in records[0]
    assert "Evidências: dados" in records[0]
    assert "Explicação:" in records[0]
    assert "Título: Estágio em BI" in records[1]
    assert "Empresa: Empresa B" in records[1]
    assert "Área: BI" in records[1]
    assert "Evidências: BI" in records[1]
    assert output.err == ""
