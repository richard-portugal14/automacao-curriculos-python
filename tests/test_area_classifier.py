import pytest

from assistente_oportunidades.models import Job
from assistente_oportunidades.services.area_classifier import AreaCategory, classify_area


def make_job(
    title: str,
    description: str = "",
    *,
    contract_type: str = "contract",
    category: str = "Other",
) -> Job:
    return Job(
        source="adzuna",
        external_id=f"{title}-{description}"[:100],
        title=title,
        company="Empresa Exemplo",
        location="São Paulo",
        description=description,
        url="https://example.test/job",
        contract_type=contract_type,
        category=category,
    )


@pytest.mark.parametrize(
    "title",
    ["Estágio em Dados", "Estagiário de Análise de Dados"],
)
def test_explicit_data_titles_are_classified_as_data_analytics(title: str):
    result = classify_area(make_job(title))

    assert result.category is AreaCategory.DADOS_ANALYTICS
    assert result.explanation
    assert result.evidence


@pytest.mark.parametrize(
    "title",
    ["Estagiário(a) em Business Intelligence", "Estágio em BI"],
)
def test_explicit_bi_titles_are_classified_as_bi(title: str):
    result = classify_area(make_job(title))

    assert result.category is AreaCategory.BI
    assert result.explanation
    assert result.evidence


def test_it_title_with_data_engineering_evidence_is_ti_data():
    result = classify_area(
        make_job(
            "Estagiário de TI - Dados e IA",
            "Desenvolvimento em Python, ETL e construção de pipelines de dados.",
        )
    )

    assert result.category is AreaCategory.TI_DADOS
    assert "ETL/ELT" in result.evidence
    assert "Python" in result.evidence


def test_data_engineering_title_is_ti_data():
    result = classify_area(make_job("Estágio em Engenharia de Dados"))

    assert result.category is AreaCategory.TI_DADOS
    assert "engenharia de dados" in result.evidence


def test_general_it_title_with_support_tasks_is_ti_general():
    result = classify_area(
        make_job(
            "Estagiário de TI",
            "Suporte aos usuários, configuração de impressoras e manutenção de computadores.",
        )
    )

    assert result.category is AreaCategory.TI_GERAL
    assert "TI" in result.evidence


def test_incidental_mention_of_data_does_not_classify_as_data():
    result = classify_area(
        make_job("Estágio em Marketing", "Atualização de dados cadastrais de clientes.")
    )

    assert result.category is AreaCategory.OUTRA
    assert "dados" in result.evidence
    assert "incidental" in result.explanation


def test_incidental_power_bi_in_data_role_does_not_override_title_area():
    result = classify_area(
        make_job("Estágio em Análise de Dados", "Power BI será considerado diferencial.")
    )

    assert result.category is AreaCategory.DADOS_ANALYTICS


def test_description_with_combined_bi_evidence_is_classified_as_bi():
    result = classify_area(
        make_job("Estágio em Tecnologia", "Criação de dashboards e acompanhamento de indicadores.")
    )

    assert result.category is AreaCategory.BI
    assert "dashboards" in result.evidence
    assert "indicadores" in result.evidence


def test_generic_it_role_with_data_in_description_but_no_strong_signal_is_ti_general():
    result = classify_area(make_job("Estagiário de TI", "Organização de dados e suporte interno."))

    assert result.category is AreaCategory.TI_GERAL


def test_unrelated_area_is_classified_as_other():
    result = classify_area(
        make_job("Estágio em Recursos Humanos", "Apoio a recrutamento e seleção.")
    )

    assert result.category is AreaCategory.OUTRA


def test_classifier_does_not_use_contract_type_or_source_category():
    first = classify_area(
        make_job("Estágio em Dados", "", contract_type="contract", category="Other")
    )
    second = classify_area(
        make_job("Estágio em Dados", "", contract_type="permanent", category="Finance")
    )

    assert first.category is second.category is AreaCategory.DADOS_ANALYTICS


@pytest.mark.parametrize(
    ("title", "description", "expected"),
    [
        (
            "Estágio em Dados",
            "Apoio em análises, indicadores e tratamento de dados.",
            AreaCategory.DADOS_ANALYTICS,
        ),
        (
            "Estagiário de Análise de Dados",
            "Elaboração de análises e relatórios.",
            AreaCategory.DADOS_ANALYTICS,
        ),
        (
            "Estagiário de TI - Dados e IA",
            "Python, ETL, pipelines de dados e automação.",
            AreaCategory.TI_DADOS,
        ),
        (
            "Estagiário de TI",
            "Suporte aos usuários, manutenção de computadores e impressoras.",
            AreaCategory.TI_GERAL,
        ),
    ],
)
def test_area_precedence_for_data_analytics_and_it_data_titles(
    title: str, description: str, expected: AreaCategory
):
    result = classify_area(make_job(title, description))

    assert result.category is expected
    assert result.explanation
    assert result.evidence


def test_generic_data_mention_in_it_title_is_not_data_analytics():
    result = classify_area(
        make_job(
            "Estagiário de TI - Dados e IA",
            "Suporte técnico aos usuários e configuração de equipamentos.",
        )
    )

    assert result.category is AreaCategory.TI_GERAL
    assert "dados" in result.evidence
    assert "não comprova atuação especializada em dados" in result.explanation
