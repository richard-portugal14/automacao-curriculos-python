from pathlib import Path

from assistente_oportunidades import cli
from assistente_oportunidades.models import Job
from assistente_oportunidades.repositories.jobs import JobRepository
from assistente_oportunidades.services.area_classifier import AreaCategory
from assistente_oportunidades.services.profile_diagnostic import diagnose_stored_profile
from assistente_oportunidades.services.profile_matcher import EducationCompatibility


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


def test_profile_diagnostic_matches_only_confirmed_internships(tmp_path: Path):
    database = tmp_path / "jobs.sqlite3"
    with JobRepository(database) as repository:
        _save_job(
            repository,
            "intern",
            "Estágio em Dados",
            "Conhecimento em SQL será diferencial. Cursando Ciência da Computação.",
            "Empresa A",
        )
        _save_job(
            repository,
            "not-intern",
            "Analista de Dados Pleno",
            "Python e SQL obrigatórios. Formação em Administração.",
            "Empresa B",
        )
        _save_job(
            repository,
            "uncertain",
            "Programa de Talentos",
            "Vaga para profissional com conhecimento em Python.",
            "Empresa C",
        )

    report = diagnose_stored_profile(database)

    assert report.total == 1
    assert [item.job.external_id for item in report.results] == ["intern"]
    assert report.results[0].area.category is AreaCategory.DADOS_ANALYTICS


def test_profile_diagnostic_summary_counts_are_consistent(tmp_path: Path):
    database = tmp_path / "jobs.sqlite3"
    with JobRepository(database) as repository:
        _save_job(
            repository,
            "match",
            "Estágio em Dados",
            "Utilizando SQL e Excel. Cursando Ciência da Computação.",
            "Empresa A",
        )
        _save_job(
            repository,
            "no-match",
            "Estagiário de TI",
            "Suporte aos usuários e manutenção de computadores.",
            "Empresa B",
        )
        _save_job(
            repository,
            "fulltime",
            "Analista Pleno",
            "Python e SQL desejáveis.",
            "Empresa C",
        )

    report = diagnose_stored_profile(database)

    assert report.total == 2
    assert report.with_skill_matches == 1
    assert report.without_skill_matches == 1
    assert report.with_skill_matches + report.without_skill_matches == report.total
    assert report.education_counts[EducationCompatibility.COMPATIVEL] == 1
    assert report.education_counts[EducationCompatibility.NAO_INFORMADO] == 1
    assert sum(report.area_counts.values()) == report.total


def test_diagnose_profile_cli_prints_complete_independent_records(capsys, tmp_path: Path):
    database = tmp_path / "jobs.sqlite3"
    with JobRepository(database) as repository:
        _save_job(
            repository,
            "data",
            "Estágio em Dados",
            "Utilizando SQL e Excel. Cursando Ciência da Computação.",
            "Empresa A",
        )
        _save_job(
            repository,
            "it",
            "Estagiário de TI",
            "Suporte aos usuários e manutenção de computadores.",
            "Empresa B",
        )
        _save_job(
            repository,
            "fulltime",
            "Analista Pleno",
            "SQL obrigatório.",
            "Empresa C",
        )

    result = cli.main(["diagnose-profile", "--database", str(database)])
    output = capsys.readouterr()
    records = [
        block for block in output.out.split("\n\n") if block.startswith("Registro ")
    ]

    assert result == 0
    assert "Total de vagas analisadas: 2" in output.out
    assert "Com habilidades correspondentes: 1" in output.out
    assert "Sem habilidades correspondentes: 1" in output.out
    assert len(records) == 2
    assert "Título: Estágio em Dados" in records[0]
    assert "Empresa: Empresa A" in records[0]
    assert "Área: DADOS_ANALYTICS" in records[0]
    assert "Habilidades correspondentes: SQL, Excel" in records[0]
    assert "Formação: Compatível" in records[0]
    assert "Explicação:" in records[0]
    assert "Título: Estagiário de TI" in records[1]
    assert "Empresa: Empresa B" in records[1]
    assert "Área: TI_GERAL" in records[1]
    assert "Habilidades correspondentes: nenhuma" in records[1]
    assert "Explicação:" in records[1]
    assert output.err == ""
