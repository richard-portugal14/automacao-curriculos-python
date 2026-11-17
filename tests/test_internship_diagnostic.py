from pathlib import Path

import pytest

from assistente_oportunidades import cli
from assistente_oportunidades.models import Job
from assistente_oportunidades.repositories.jobs import JobRepository
from assistente_oportunidades.services.internship_classifier import InternshipClassification
from assistente_oportunidades.services.internship_diagnostic import diagnose_stored_jobs


def _save_job(
    repository: JobRepository,
    title: str,
    description: str,
    company: str | None = None,
) -> None:
    repository.save(
        Job(
            source="adzuna",
            external_id=title,
            title=title,
            company=company or f"Empresa {title}",
            location="São Paulo",
            description=description,
            url=f"https://example.test/{title.replace(' ', '-')}",
        )
    )


def test_diagnostic_classifies_all_stored_jobs_and_calculates_percentages(tmp_path: Path):
    database = tmp_path / "jobs.sqlite3"
    with JobRepository(database) as repository:
        _save_job(repository, "Estágio em Dados", "SQL e Python")
        _save_job(repository, "Estagiário de TI", "Suporte e automação")
        _save_job(repository, "Analista Pleno", "Experiência anterior como estagiário")
        _save_job(repository, "Programa de Talentos", "Oportunidade em Dados")

    report = diagnose_stored_jobs(database)

    assert report.total == 4
    assert report.counts[InternshipClassification.ESTAGIO] == 2
    assert report.counts[InternshipClassification.NAO_ESTAGIO] == 1
    assert report.counts[InternshipClassification.INCERTO] == 1
    assert report.percentages[InternshipClassification.ESTAGIO] == 50
    assert len(report.confirmed) == 2
    assert len(report.uncertain) == 1


def test_diagnostic_cli_displays_summary_confirmed_and_uncertain_jobs(capsys, tmp_path: Path):
    database = tmp_path / "jobs.sqlite3"
    with JobRepository(database) as repository:
        _save_job(repository, "Estágio em Dados", "SQL e Python")
        _save_job(repository, "Programa de Talentos", "Oportunidade em Dados")

    result = cli.main(["diagnose-internships", "--database", str(database)])

    output = capsys.readouterr()
    assert result == 0
    assert "Total de vagas analisadas: 2" in output.out
    assert "ESTAGIO: 1 (50.0%)" in output.out
    assert "INCERTO: 1 (50.0%)" in output.out
    assert "Título: Estágio em Dados" in output.out
    assert "Classificação: ESTAGIO" in output.out
    assert "O título contém um marcador explícito de estágio." in output.out
    assert "Título: Programa de Talentos" in output.out
    assert "Classificação: INCERTO" in output.out
    assert output.err == ""


def test_each_confirmed_job_is_printed_as_a_complete_independent_record(
    capsys, tmp_path: Path
):
    database = tmp_path / "jobs.sqlite3"
    with JobRepository(database) as repository:
        _save_job(
            repository,
            "Estagiário de TI",
            "Suporte e automação",
            "GTEL - Grupo Técnico de Eletromecânica S.A.",
        )
        _save_job(repository, "Estágio em Dados", "SQL e Python", "JHSF")

    result = cli.main(["diagnose-internships", "--database", str(database)])
    output = capsys.readouterr()
    records = [
        block for block in output.out.split("\n\n") if block.startswith("Registro ")
    ]

    assert result == 0
    assert len(records) == 2
    assert "Título: Estagiário de TI" in records[0]
    assert "Empresa: GTEL - Grupo Técnico de Eletromecânica S.A." in records[0]
    assert "Classificação: ESTAGIO" in records[0]
    assert "Explicação: O título contém um marcador explícito de estágio." in records[0]
    assert "Título: Estágio em Dados" in records[1]
    assert "Empresa: JHSF" in records[1]
    assert "Classificação: ESTAGIO" in records[1]
    assert "Explicação: O título contém um marcador explícito de estágio." in records[1]


def test_diagnostic_fails_when_database_does_not_exist(tmp_path: Path):
    missing_database = tmp_path / "missing.sqlite3"
    with pytest.raises(FileNotFoundError, match="Banco de dados não encontrado"):
        diagnose_stored_jobs(missing_database)
