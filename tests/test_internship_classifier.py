import pytest

from assistente_oportunidades.models import Job
from assistente_oportunidades.services.internship_classifier import (
    InternshipClassification,
    classify_internship,
    filter_internships,
)


def make_job(title: str, description: str = "") -> Job:
    return Job(
        source="adzuna",
        external_id=f"{title}-{description}"[:100],
        title=title,
        company="Empresa Exemplo",
        location="São Paulo",
        description=description,
        url="https://example.test/job",
        contract_type="permanent",
        category="Other",
    )


@pytest.mark.parametrize(
    "title",
    [
        "Estágio em Dados",
        "Estagiário de TI",
        "Estagiário(a) de Tecnologia da Informação",
        "Estagiária de Análise de Dados",
        "estagio em dados",
        "ESTAGIARIA de Analytics",
        "Data Analyst Intern",
        "Data Internship",
    ],
)
def test_explicit_internship_title_is_classified_as_internship(title: str):
    result = classify_internship(make_job(title))

    assert result.classification is InternshipClassification.ESTAGIO
    assert result.title_has_internship_marker


@pytest.mark.parametrize(
    ("title", "description"),
    [
        (
            "Analista de Dados Pleno",
            "Experiência anterior como estagiário será considerada um diferencial.",
        ),
        ("Desenvolvedor Python", "Desenvolvimento de APIs e manutenção de sistemas."),
        ("Data Analyst", "Candidates may have previous experience as an intern."),
    ],
)
def test_description_mention_does_not_turn_non_internship_title_into_internship(
    title: str, description: str
):
    result = classify_internship(make_job(title, description))

    assert result.classification is InternshipClassification.NAO_ESTAGIO
    assert not result.title_has_internship_marker


def test_generic_title_with_internship_only_in_description_is_uncertain():
    result = classify_internship(
        make_job("Programa de Talentos", "A oportunidade é destinada a estágio em Dados.")
    )

    assert result.classification is InternshipClassification.INCERTO
    assert result.description_has_internship_marker


def test_filter_keeps_only_confirmed_internships_and_counts_diagnostics():
    internship = make_job("Estágio em Dados")
    non_internship = make_job("Analista Pleno", "Experiência como estagiário é desejável.")
    uncertain = make_job("Programa de Talentos", "Experiência em estágio será valorizada.")

    result = filter_internships([internship, non_internship, uncertain])

    assert result.eligible == [internship]
    assert result.rejected_count == 1
    assert result.uncertain_count == 1
    assert len(result.diagnostics) == 2
