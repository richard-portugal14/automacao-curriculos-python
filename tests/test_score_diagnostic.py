import sqlite3
from pathlib import Path

import pytest

from assistente_oportunidades import cli
from assistente_oportunidades.models import Job
from assistente_oportunidades.repositories.jobs import JobRepository
from assistente_oportunidades.services.area_classifier import AreaCategory
from assistente_oportunidades.services.score_diagnostic import diagnose_stored_scores, score_band


def _save_job(repository, external_id: str, title: str, description: str):
    repository.save(
        Job(
            source="adzuna",
            external_id=external_id,
            title=title,
            company=f"Empresa {external_id}",
            location="São Paulo",
            description=description,
            url=f"https://example.test/{external_id}",
        )
    )


def _populate_database(database: Path) -> None:
    with JobRepository(database) as repository:
        _save_job(repository, "data", "Estágio em Dados", "Apoio à equipe.")
        _save_job(repository, "bi", "Estágio em BI", "Apoio à equipe.")
        _save_job(repository, "fulltime", "Analista de Dados Pleno", "SQL obrigatório.")
        _save_job(repository, "uncertain", "Programa de Talentos", "Vaga em tecnologia.")


def _database_snapshot(database: Path):
    with sqlite3.connect(database) as connection:
        return connection.execute("SELECT * FROM jobs ORDER BY id").fetchall()


def test_score_diagnostic_processes_only_confirmed_internships_and_summarizes(tmp_path: Path):
    database = tmp_path / "jobs.sqlite3"
    _populate_database(database)

    report = diagnose_stored_scores(database)

    assert report.total == 2
    assert [item.job.external_id for item in report.results] == ["data", "bi"]
    assert report.average == pytest.approx(55.5)
    assert report.maximum == 58
    assert report.minimum == 53
    assert report.score_band_counts["50-59"] == 2
    assert sum(report.score_band_counts.values()) == report.total
    assert report.area_counts[AreaCategory.DADOS_ANALYTICS] == 1
    assert report.area_counts[AreaCategory.BI] == 1
    assert sum(report.area_counts.values()) == report.total


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        (100, "90-100"),
        (90, "90-100"),
        (89.99, "80-89"),
        (80, "80-89"),
        (79.99, "70-79"),
        (70, "70-79"),
        (69.99, "60-69"),
        (60, "60-69"),
        (59.99, "50-59"),
        (50, "50-59"),
        (49.99, "0-49"),
        (0, "0-49"),
    ],
)
def test_score_band_boundaries(value, expected):
    assert score_band(value) == expected


def test_diagnose_score_cli_prints_score_components_and_explanation(capsys, tmp_path: Path):
    database = tmp_path / "jobs.sqlite3"
    _populate_database(database)

    result = cli.main(["diagnose-score", "--database", str(database)])
    captured = capsys.readouterr()
    records = [block for block in captured.out.split("\n\n") if block.startswith("Registro ")]

    assert result == 0
    assert len(records) == 2
    for required in (
        "Título:",
        "Empresa:",
        "Área:",
        "Habilidades correspondentes:",
        "Requisitos não encontrados:",
        "Formação:",
        "Score área:",
        "Score habilidades:",
        "Score formação:",
        "Score localização:",
        "SCORE TOTAL:",
        "Explicação do score:",
    ):
        assert required in records[0]
    assert "Score médio: 55,50" in captured.out
    assert "Score máximo: 58,00" in captured.out
    assert "Score mínimo: 53,00" in captured.out
    assert "50-59: 2" in captured.out
    assert "DADOS_ANALYTICS: 1" in captured.out
    assert "BI: 1" in captured.out
    assert "SCORE TOTAL: 58,00" in records[0]
    assert "SCORE TOTAL: 53,00" in records[1]
    assert captured.err == ""


def test_score_diagnostic_does_not_persist_changes(tmp_path: Path):
    database = tmp_path / "jobs.sqlite3"
    _populate_database(database)
    before = _database_snapshot(database)

    diagnose_stored_scores(database)

    assert _database_snapshot(database) == before
