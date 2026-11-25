from dataclasses import replace

import pytest

from assistente_oportunidades.models import Job
from assistente_oportunidades.services.area_classifier import AreaCategory, AreaClassificationResult
from assistente_oportunidades.services.profile_matcher import (
    AreaAlignment,
    CandidateProfile,
    EducationCompatibility,
    EducationMatch,
    ProfileMatchResult,
    load_candidate_profile,
)
from assistente_oportunidades.services.score import FitStatus, calculate_compatibility_score


@pytest.fixture
def profile() -> CandidateProfile:
    return load_candidate_profile()


def make_job(location="S\u00e3o Paulo, SP", text="", title="Est\u00e1gio em Dados") -> Job:
    return Job("adzuna", title, title, "Empresa Exemplo", location, text,
               "https://example.test/job")


def make_area(category: AreaCategory) -> AreaClassificationResult:
    return AreaClassificationResult(category, "Classifica\u00e7\u00e3o recebida", ())


def make_match(
    area: AreaCategory, *, found=(), matched=(), missing=(),
    education=EducationCompatibility.NAO_INFORMADO,
) -> ProfileMatchResult:
    return ProfileMatchResult(
        area, AreaAlignment.ALTA, tuple(found), tuple(matched), tuple(missing),
        EducationMatch(education, None, "Forma\u00e7\u00e3o para teste."), (),
    )


def calculate(job, category, profile, match=None):
    return calculate_compatibility_score(job, make_area(category), match or make_match(category), profile)


@pytest.mark.parametrize(("category", "expected"), [
    (AreaCategory.DADOS_ANALYTICS, 40), (AreaCategory.BI, 35),
    (AreaCategory.TI_DADOS, 25), (AreaCategory.TI_GERAL, 10), (AreaCategory.OUTRA, 0),
])
def test_area_points_use_supplied_classification(profile, category, expected):
    assert calculate(make_job(), category, profile).score_area == expected


def test_three_of_four_matched_skills_receive_26_25_points(profile):
    match = make_match(AreaCategory.DADOS_ANALYTICS,
                       found=("SQL", "Excel", "Power BI", "Tableau"),
                       matched=("SQL", "Excel", "Power BI"), missing=("Tableau",))
    result = calculate(make_job(), AreaCategory.DADOS_ANALYTICS, profile, match)
    assert result.score_habilidades == 26.25
    assert result.habilidades_contribuintes == ("SQL", "Excel", "Power BI")
    assert result.requisitos_sem_correspondencia == ("Tableau",)


def test_no_identified_skills_receive_zero_points(profile):
    assert calculate(make_job(), AreaCategory.BI, profile).score_habilidades == 0


def test_all_identified_skills_receive_full_points(profile):
    match = make_match(AreaCategory.BI, found=("Python", "SQL"), matched=("Python", "SQL"))
    assert calculate(make_job(), AreaCategory.BI, profile, match).score_habilidades == 35


@pytest.mark.parametrize(("education", "expected"), [
    (EducationCompatibility.COMPATIVEL, 15),
    (EducationCompatibility.NAO_INFORMADO, 10),
    (EducationCompatibility.INCOMPATIVEL, 0),
])
def test_education_points_follow_matcher_status(profile, education, expected):
    match = make_match(AreaCategory.BI, education=education)
    assert calculate(make_job(), AreaCategory.BI, profile, match).score_formacao == expected


def test_compatible_location_and_work_model_receive_ten_points(profile):
    result = calculate(make_job(text="Modelo h\u00edbrido."), AreaCategory.BI, profile)
    assert result.score_localizacao == 10
    assert result.location_work_assessment.location_status is FitStatus.COMPATIVEL
    assert result.location_work_assessment.work_model_status is FitStatus.COMPATIVEL


def test_compatible_location_without_model_receive_eight_points(profile):
    result = calculate(make_job(), AreaCategory.BI, profile)
    assert result.score_localizacao == 8
    assert result.location_work_assessment.work_model_status is FitStatus.NAO_INFORMADO


def test_compatible_model_without_location_receive_eight_points(profile):
    result = calculate(make_job(location=None, text="Trabalho remoto."), AreaCategory.BI, profile)
    assert result.score_localizacao == 8
    assert result.location_work_assessment.location_status is FitStatus.NAO_INFORMADO


def test_incompatible_location_or_model_receive_zero_points(profile):
    outside = calculate(make_job(location="Rio de Janeiro", text="Modelo remoto."), AreaCategory.BI, profile)
    remote_only = replace(profile, work_models=("remoto",))
    onsite = calculate(make_job(text="Trabalho presencial."), AreaCategory.BI, remote_only)
    assert outside.score_localizacao == onsite.score_localizacao == 0
    assert outside.location_work_assessment.location_status is FitStatus.INCOMPATIVEL
    assert outside.location_work_assessment.work_model_status is FitStatus.COMPATIVEL
    assert onsite.location_work_assessment.location_status is FitStatus.COMPATIVEL
    assert onsite.location_work_assessment.work_model_status is FitStatus.INCOMPATIVEL


def test_insufficient_location_and_model_receive_five_points(profile):
    result = calculate(make_job(location=None), AreaCategory.BI, profile)
    assert result.score_localizacao == 5
    assert result.location_work_assessment.location_status is FitStatus.NAO_INFORMADO
    assert result.location_work_assessment.work_model_status is FitStatus.NAO_INFORMADO


@pytest.mark.parametrize(
    "location",
    ["Brasil", "BR", "não informado", "unknown", "a definir", "vários locais"],
)
def test_non_identifying_location_is_not_treated_as_incompatible(profile, location):
    result = calculate(make_job(location=location), AreaCategory.BI, profile)

    assert result.score_localizacao == 5
    assert result.location_work_assessment.location_status is FitStatus.NAO_INFORMADO
    assert result.location_work_assessment.work_model_status is FitStatus.NAO_INFORMADO
    assert "insuficientemente informados" in result.location_work_assessment.explanation


def test_maximum_score_is_100_and_explains_components(profile):
    match = make_match(AreaCategory.DADOS_ANALYTICS, found=("SQL", "Excel"),
                       matched=("SQL", "Excel"), education=EducationCompatibility.COMPATIVEL)
    result = calculate(make_job(text="Modelo presencial."), AreaCategory.DADOS_ANALYTICS,
                       profile, match)
    assert result.score_total == 100
    assert 0 <= result.score_total <= 100
    assert len(result.explicacao) == 5
    assert any("\u00c1rea DADOS_ANALYTICS" in line for line in result.explicacao)
    assert any("Compatibilidade total" in line for line in result.explicacao)


def test_score_uses_supplied_area_without_reclassifying_job(profile):
    result = calculate_compatibility_score(make_job(title="Est\u00e1gio em Dados"),
        make_area(AreaCategory.BI), make_match(AreaCategory.BI), profile)
    assert result.score_area == 35


def test_mismatched_area_between_classifier_and_matcher_is_rejected(profile):
    with pytest.raises(ValueError, match="mesma usada pelo profile_matcher"):
        calculate_compatibility_score(make_job(), make_area(AreaCategory.DADOS_ANALYTICS),
            make_match(AreaCategory.BI), profile)
