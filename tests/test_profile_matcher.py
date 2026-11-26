from dataclasses import replace

import pytest

from assistente_oportunidades.models import Job
from assistente_oportunidades.services.area_classifier import AreaCategory
from assistente_oportunidades.services.profile_matcher import (
    AreaAlignment,
    CandidateProfile,
    EducationCompatibility,
    load_candidate_profile,
    match_profile,
)


@pytest.fixture
def profile() -> CandidateProfile:
    return load_candidate_profile()


def make_job(title: str, description: str) -> Job:
    return Job(
        source="adzuna",
        external_id=title,
        title=title,
        company="Empresa Exemplo",
        location="São Paulo",
        description=description,
        url="https://example.test/job",
    )


def test_data_job_matches_sql_excel_and_power_bi(profile: CandidateProfile):
    job = make_job(
        "Estágio em Dados",
        "Auxiliar em análises utilizando SQL, Microsoft Excel e Power BI.",
    )

    result = match_profile(job, AreaCategory.DADOS_ANALYTICS, profile)

    assert {"SQL", "Excel", "Power BI"}.issubset(result.skills_found_in_job)
    assert {"SQL", "Excel", "Power BI"}.issubset(result.matched_profile_skills)
    assert result.requirements_not_in_profile == ()
    assert result.area_alignment is AreaAlignment.ALTA


def test_data_analytics_job_recognizes_python(profile: CandidateProfile):
    job = make_job("Estágio em Data Analytics", "Conhecimento em Python será diferencial.")

    result = match_profile(job, AreaCategory.DADOS_ANALYTICS, profile)

    assert "Análise de Dados" in result.skills_found_in_job
    assert "Python" in result.skills_found_in_job
    assert "Python" in result.matched_profile_skills


def test_bi_job_recognizes_power_bi_and_uses_passed_area(profile: CandidateProfile):
    job = make_job("Estagiário em Business Intelligence", "Conhecimento em Power BI desejável.")

    result = match_profile(job, AreaCategory.BI, profile)

    assert "BI" in result.skills_found_in_job
    assert "Power BI" in result.skills_found_in_job
    assert "Power BI" in result.matched_profile_skills
    assert result.area is AreaCategory.BI
    assert result.area_alignment is AreaAlignment.ALTA


def test_python_pandas_and_sql_server_variants_match_profile_skills(
    profile: CandidateProfile,
):
    job = make_job(
        "Estágio em Data Analytics",
        "Conhecimento em Python e Pandas; experiência em SQL Server.",
    )

    result = match_profile(job, AreaCategory.DADOS_ANALYTICS, profile)

    assert {"Python", "Pandas", "SQL"}.issubset(result.skills_found_in_job)
    assert {"Python", "Pandas", "SQL"}.issubset(result.matched_profile_skills)


def test_general_it_has_low_area_alignment_and_few_matching_skills(profile: CandidateProfile):
    job = make_job(
        "Estágio de TI",
        "Suporte aos usuários, manutenção de computadores e configuração de impressoras.",
    )

    result = match_profile(job, AreaCategory.TI_GERAL, profile)

    assert result.area_alignment is AreaAlignment.BAIXA
    assert result.matched_profile_skills == ()
    assert "baixa" in " ".join(result.explanation).casefold()


def test_skill_missing_from_profile_is_reported_as_requirement(profile: CandidateProfile):
    job = make_job("Estágio de BI", "Requisito: conhecimento em Tableau será obrigatório.")

    result = match_profile(job, AreaCategory.BI, profile)

    assert "Tableau" in result.skills_found_in_job
    assert "Tableau" in result.requirements_not_in_profile


@pytest.mark.parametrize(
    "course",
    [
        "Ciência da Computação",
        "Tecnologia da Informação",
        "Engenharia da Computação",
        "Análise e Desenvolvimento de Sistemas",
    ],
)
def test_related_technology_courses_are_compatible(profile: CandidateProfile, course: str):
    job = make_job("Estágio em Dados", f"Requisito: cursando {course} ou áreas correlatas.")

    result = match_profile(job, AreaCategory.DADOS_ANALYTICS, profile)

    assert result.education.compatibility is EducationCompatibility.COMPATIVEL


def test_unrelated_required_education_is_incompatible(profile: CandidateProfile):
    job = make_job("Estágio em Administração", "Formação exigida em Engenharia Civil.")

    result = match_profile(job, AreaCategory.OUTRA, profile)

    assert result.education.compatibility is EducationCompatibility.INCOMPATIVEL


def test_education_without_requirement_is_not_informed(profile: CandidateProfile):
    job = make_job("Estágio em TI", "Suporte aos usuários e manutenção de equipamentos.")

    result = match_profile(job, AreaCategory.TI_GERAL, profile)

    assert result.education.compatibility is EducationCompatibility.NAO_INFORMADO


def test_incidental_skill_mention_is_not_counted_as_job_skill(profile: CandidateProfile):
    job = make_job(
        "Estágio em Marketing",
        "A empresa possui uma ferramenta chamada Python Café, criada por um dos fundadores.",
    )

    result = match_profile(job, AreaCategory.OUTRA, profile)

    assert "Python" not in result.skills_found_in_job
    assert "Python" not in result.matched_profile_skills


def test_service_uses_area_argument_without_reclassifying_job(profile: CandidateProfile):
    job = make_job("Estágio em Dados", "Conhecimento em SQL será diferencial.")

    result = match_profile(job, AreaCategory.TI_GERAL, profile)

    assert result.area is AreaCategory.TI_GERAL
    assert result.area_alignment is AreaAlignment.BAIXA


def test_profile_is_loaded_from_existing_configuration(profile: CandidateProfile):
    assert profile.education == "Ciência da Computação — superior incompleto"
    assert "Python" in profile.skills
    assert "São Paulo" in profile.locations
    assert "remoto" in profile.work_models
    assert tuple(area.value for area in profile.area_priorities[:2]) == (
        "DADOS_ANALYTICS",
        "BI",
    )
