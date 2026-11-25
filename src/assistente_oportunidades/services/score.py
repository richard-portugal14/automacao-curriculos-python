"""Score determinístico e explicável de compatibilidade."""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from enum import Enum

from assistente_oportunidades.models import Job
from assistente_oportunidades.services.area_classifier import AreaCategory, AreaClassificationResult
from assistente_oportunidades.services.profile_matcher import (
    CandidateProfile,
    EducationCompatibility,
    ProfileMatchResult,
)


class FitStatus(str, Enum):
    COMPATIVEL = "COMPATIVEL"
    INCOMPATIVEL = "INCOMPATIVEL"
    NAO_INFORMADO = "NAO_INFORMADO"


@dataclass(frozen=True, slots=True)
class LocationWorkAssessment:
    location_status: FitStatus
    work_model_status: FitStatus
    detected_work_models: tuple[str, ...]
    matched_location: str | None
    points: float
    explanation: str


@dataclass(frozen=True, slots=True)
class CompatibilityScore:
    score_total: float
    score_area: float
    score_habilidades: float
    score_formacao: float
    score_localizacao: float
    habilidades_contribuintes: tuple[str, ...]
    requisitos_sem_correspondencia: tuple[str, ...]
    location_work_assessment: LocationWorkAssessment
    explicacao: tuple[str, ...]


_AREA_POINTS = {
    AreaCategory.DADOS_ANALYTICS: 40.0,
    AreaCategory.BI: 35.0,
    AreaCategory.TI_DADOS: 25.0,
    AreaCategory.TI_GERAL: 10.0,
    AreaCategory.OUTRA: 0.0,
}
_WORK_MODE_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("remoto", re.compile(r"\bremot[oa]s?\b|\bhome office\b|\bteletrabalho\b|\bremote\b")),
    ("h\u00edbrido", re.compile(r"\bhibrid[oa]s?\b|\bhybrid\b")),
    ("presencial", re.compile(r"\bpresencial\b|\bon site\b|\bonsite\b|\bin person\b")),
)
_REMOTE_LOCATION = re.compile(r"\bremot[oa]s?\b|\bhome office\b|\bteletrabalho\b|\bremote\b|\banywhere\b")
_UNIDENTIFIED_LOCATIONS = {
    "br",
    "brasil",
    "brazil",
    "n a",
    "na",
    "nao informado",
    "nao identificada",
    "not informed",
    "not specified",
    "unknown",
    "a definir",
    "a combinar",
    "varios locais",
    "multiple locations",
}


def calculate_compatibility_score(
    job: Job,
    area: AreaClassificationResult,
    profile_match: ProfileMatchResult,
    profile: CandidateProfile,
) -> CompatibilityScore:
    """Calcula os componentes recebidos sem reclassificar a área ou a vaga."""
    if area.category is not profile_match.area:
        raise ValueError("A área recebida deve ser a mesma usada pelo profile_matcher.")

    score_area = _AREA_POINTS[area.category]
    contributing, missing = _skill_partition(profile_match)
    identified_count = len(profile_match.skills_found_in_job)
    score_skills = round(len(contributing) / identified_count * 35, 2) if identified_count else 0.0
    score_education = {
        EducationCompatibility.COMPATIVEL: 15.0,
        EducationCompatibility.NAO_INFORMADO: 10.0,
        EducationCompatibility.INCOMPATIVEL: 0.0,
    }[profile_match.education.compatibility]
    location_assessment = _assess_location_and_work_model(job, profile)

    total = round(score_area + score_skills + score_education + location_assessment.points, 2)
    total = min(100.0, max(0.0, total))
    explanation = (
        f"Área {area.category.value}: {score_area:g}/40 pontos.",
        _skill_explanation(contributing, missing, identified_count, score_skills),
        f"Formação {profile_match.education.compatibility.value}: {score_education:g}/15 pontos.",
        location_assessment.explanation,
        f"Compatibilidade total: {total:g}/100 pontos.",
    )
    return CompatibilityScore(
        score_total=total,
        score_area=score_area,
        score_habilidades=score_skills,
        score_formacao=score_education,
        score_localizacao=location_assessment.points,
        habilidades_contribuintes=contributing,
        requisitos_sem_correspondencia=missing,
        location_work_assessment=location_assessment,
        explicacao=explanation,
    )


def _skill_partition(profile_match: ProfileMatchResult) -> tuple[tuple[str, ...], tuple[str, ...]]:
    found = tuple(dict.fromkeys(profile_match.skills_found_in_job))
    missing_keys = {_normalize(skill) for skill in profile_match.requirements_not_in_profile}
    missing = tuple(skill for skill in found if _normalize(skill) in missing_keys)
    contributing = tuple(skill for skill in found if _normalize(skill) not in missing_keys)
    return contributing, missing


def _skill_explanation(
    contributing: tuple[str, ...], missing: tuple[str, ...], identified_count: int, points: float
) -> str:
    if not identified_count:
        return "Nenhuma habilidade identificável na vaga: 0/35 pontos."
    details = f"{len(contributing)} de {identified_count} habilidades identificadas correspondem ao perfil"
    if contributing:
        details += "; contribuem: " + ", ".join(contributing)
    if missing:
        details += "; sem correspondência: " + ", ".join(missing)
    return f"{details}: {points:g}/35 pontos."


def _assess_location_and_work_model(job: Job, profile: CandidateProfile) -> LocationWorkAssessment:
    location_status, matched_location = _location_status(job.location, profile.locations)
    detected = _detect_work_models(f"{job.title} {job.description or ''}")
    model_status = _work_model_status(detected, profile.work_models)

    if FitStatus.INCOMPATIVEL in (location_status, model_status):
        points, explanation = 0.0, "Localização ou modelo de trabalho incompatível: 0/10 pontos."
    elif location_status is FitStatus.COMPATIVEL and model_status is FitStatus.COMPATIVEL:
        points, explanation = 10.0, "Localização e modelo de trabalho compatíveis: 10/10 pontos."
    elif location_status is FitStatus.COMPATIVEL and model_status is FitStatus.NAO_INFORMADO:
        points, explanation = 8.0, "Localização compatível; modelo não informado: 8/10 pontos."
    elif location_status is FitStatus.NAO_INFORMADO and model_status is FitStatus.COMPATIVEL:
        points, explanation = 8.0, "Modelo compatível; localização não identificável: 8/10 pontos."
    else:
        points, explanation = 5.0, "Localização e modelo de trabalho insuficientemente informados: 5/10 pontos."

    if matched_location:
        explanation += f" Localidade compatível: {matched_location}."
    if detected:
        explanation += " Modelo(s) indicado(s): " + ", ".join(detected) + "."
    return LocationWorkAssessment(location_status, model_status, detected, matched_location, points, explanation)


def _location_status(job_location: str | None, accepted_locations: tuple[str, ...]) -> tuple[FitStatus, str | None]:
    location = _normalize(job_location or "")
    if (
        not location
        or location in _UNIDENTIFIED_LOCATIONS
        or _REMOTE_LOCATION.search(location)
        or not accepted_locations
    ):
        return FitStatus.NAO_INFORMADO, None
    for accepted in accepted_locations:
        normalized = _normalize(accepted)
        if normalized and (
            re.search(rf"\b{re.escape(normalized)}\b", location)
            or re.search(rf"\b{re.escape(location)}\b", normalized)
        ):
            return FitStatus.COMPATIVEL, accepted
    return FitStatus.INCOMPATIVEL, None


def _detect_work_models(text: str) -> tuple[str, ...]:
    normalized = _normalize(text)
    return tuple(name for name, pattern in _WORK_MODE_PATTERNS if pattern.search(normalized))


def _work_model_status(detected: tuple[str, ...], accepted_models: tuple[str, ...]) -> FitStatus:
    if not detected or not accepted_models:
        return FitStatus.NAO_INFORMADO
    accepted = {_normalize(model) for model in accepted_models}
    return FitStatus.COMPATIVEL if any(_normalize(model) in accepted for model in detected) else FitStatus.INCOMPATIVEL


def _normalize(text: str) -> str:
    decomposed = unicodedata.normalize("NFKD", text.casefold())
    plain = "".join(char for char in decomposed if not unicodedata.combining(char))
    return re.sub(r"[^a-z0-9]+", " ", plain).strip()
