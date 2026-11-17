from pathlib import Path

from assistente_oportunidades import cli
from assistente_oportunidades.models import Job
from assistente_oportunidades.repositories.jobs import JobRepository


def test_inspect_descriptions_shows_requested_fields_for_at_least_ten_jobs(
    capsys, tmp_path: Path
):
    database = tmp_path / "jobs.sqlite3"
    with JobRepository(database) as repository:
        for index in range(12):
            repository.save(
                Job(
                    source="adzuna",
                    external_id=f"job-{index}",
                    title=f"Estágio em Dados {index}",
                    company=f"Empresa {index}",
                    location="São Paulo",
                    description=f"Descrição completa da vaga {index}. Requisitos SQL e Python.",
                    url=f"https://example.test/jobs/{index}",
                    contract_type="contract",
                    category="IT Jobs",
                )
            )

    result = cli.main(["inspect-descriptions", "--limit", "10", "--database", str(database)])

    output = capsys.readouterr()
    assert result == 0
    assert output.err == ""
    assert output.out.count("--- Vaga ") == 10
    for expected in (
        "title: Estágio em Dados",
        "company: Empresa",
        "location: São Paulo",
        "contract_type: contract",
        "category: IT Jobs",
        "description:",
        "Descrição completa da vaga",
        "url: https://example.test/jobs/",
    ):
        assert expected in output.out


def test_repository_inspection_rejects_non_positive_limit(tmp_path: Path):
    with JobRepository(tmp_path / "jobs.sqlite3") as repository:
        try:
            repository.list_for_inspection(0)
        except ValueError as error:
            assert "pelo menos 1" in str(error)
        else:
            raise AssertionError("Era esperado erro para limite igual a zero.")
