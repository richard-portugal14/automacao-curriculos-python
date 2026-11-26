from assistente_oportunidades.models import Job
from assistente_oportunidades.services.area_classifier import AreaCategory, AreaClassificationResult
from assistente_oportunidades.services.profile_matcher import (
    AreaAlignment,
    EducationCompatibility,
    EducationMatch,
    ProfileMatchResult,
)
from assistente_oportunidades.services.score import (
    CompatibilityScore,
    FitStatus,
    LocationWorkAssessment,
)
from assistente_oportunidades.services.score_diagnostic import ScoreDiagnosedJob
from assistente_oportunidades.services.ranking import rank_opportunities


def make_opportunity(
    external_id: str,
    *,
    score: float = 50,
    area: AreaCategory = AreaCategory.DADOS_ANALYTICS,
    matched_skills: tuple[str, ...] = (),
    education: EducationCompatibility = EducationCompatibility.NAO_INFORMADO,
) -> ScoreDiagnosedJob:
    job = Job(
        source="test",
        external_id=external_id,
        title=f"Estágio {external_id}",
        company="Empresa",
        location="São Paulo",
        description="Descrição",
        url=f"https://example.test/{external_id}",
    )
    area_result = AreaClassificationResult(area, "Classificação pronta", ())
    match = ProfileMatchResult(
        area=area,
        area_alignment=AreaAlignment.ALTA,
        skills_found_in_job=matched_skills,
        matched_profile_skills=matched_skills,
        requirements_not_in_profile=(),
        education=EducationMatch(education, None, "Resultado pronto"),
        explanation=(),
    )
    location_assessment = LocationWorkAssessment(
        FitStatus.COMPATIVEL,
        FitStatus.COMPATIVEL,
        ("híbrido",),
        "São Paulo",
        10,
        "Localização e modalidade compatíveis.",
    )
    score_result = CompatibilityScore(
        score_total=score,
        score_area=0,
        score_habilidades=0,
        score_formacao=0,
        score_localizacao=0,
        habilidades_contribuintes=matched_skills,
        requisitos_sem_correspondencia=(),
        location_work_assessment=location_assessment,
        explicacao=("Score previamente calculado.",),
    )
    return ScoreDiagnosedJob(job, area_result, match, score_result)


def test_orders_by_existing_score_descending():
    low = make_opportunity("low", score=40)
    high = make_opportunity("high", score=91)
    middle = make_opportunity("middle", score=70)

    ranked = rank_opportunities([low, high, middle])

    assert ranked == [high, middle, low]


def test_breaks_score_tie_by_area_priority():
    ti_data = make_opportunity("ti-data", score=75, area=AreaCategory.TI_DADOS)
    bi = make_opportunity("bi", score=75, area=AreaCategory.BI)
    data = make_opportunity("data", score=75, area=AreaCategory.DADOS_ANALYTICS)

    assert rank_opportunities([ti_data, bi, data]) == [data, bi, ti_data]


def test_breaks_ties_by_number_of_compatible_skills():
    one_skill = make_opportunity("one", score=75, matched_skills=("SQL",))
    three_skills = make_opportunity(
        "three", score=75, matched_skills=("SQL", "Python", "Excel")
    )

    assert rank_opportunities([one_skill, three_skills]) == [three_skills, one_skill]


def test_breaks_ties_by_education_compatibility():
    unknown = make_opportunity(
        "unknown", score=75, education=EducationCompatibility.NAO_INFORMADO
    )
    compatible = make_opportunity(
        "compatible", score=75, education=EducationCompatibility.COMPATIVEL
    )

    assert rank_opportunities([unknown, compatible]) == [compatible, unknown]


def test_keeps_input_order_when_all_ranking_criteria_tie():
    first = make_opportunity("first", score=75, matched_skills=("SQL",))
    second = make_opportunity("second", score=75, matched_skills=("SQL",))
    third = make_opportunity("third", score=75, matched_skills=("SQL",))

    assert rank_opportunities([first, second, third]) == [first, second, third]


def test_empty_input_returns_empty_list():
    assert rank_opportunities([]) == []


def test_single_opportunity_is_returned_unchanged():
    opportunity = make_opportunity("only")

    ranked = rank_opportunities([opportunity])

    assert len(ranked) == 1
    assert ranked[0] is opportunity


def test_ranking_does_not_modify_input_collection_or_evaluations():
    lower = make_opportunity("lower", score=60)
    higher = make_opportunity("higher", score=80)
    opportunities = [lower, higher]
    original_scores = [item.score.score_total for item in opportunities]
    original_areas = [item.area.category for item in opportunities]
    original_matches = [item.match for item in opportunities]

    ranked = rank_opportunities(opportunities)

    assert opportunities == [lower, higher]
    assert ranked == [higher, lower]
    assert [item.score.score_total for item in opportunities] == original_scores
    assert [item.area.category for item in opportunities] == original_areas
    assert [item.match for item in opportunities] == original_matches
    assert ranked[0].score.score_total == 80
