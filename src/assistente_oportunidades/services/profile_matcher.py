"""Compara uma vaga com perfil e preferências, sem score ou ordenação."""

from __future__ import annotations

import re
import tomllib
import unicodedata
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Any

from assistente_oportunidades.models import Job
from assistente_oportunidades.services.area_classifier import AreaCategory


class AreaAlignment(str, Enum):
    ALTA = "ALTA"
    MEDIA = "MEDIA"
    BAIXA = "BAIXA"


class EducationCompatibility(str, Enum):
    COMPATIVEL = "COMPATIVEL"
    INCOMPATIVEL = "INCOMPATIVEL"
    NAO_INFORMADO = "NAO_INFORMADO"


@dataclass(frozen=True, slots=True)
class CandidateProfile:
    education: str | None
    skills: tuple[str, ...]
    area_priorities: tuple[AreaCategory, ...]
    locations: tuple[str, ...] = ()
    work_models: tuple[str, ...] = ()
    employment_types: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class EducationMatch:
    compatibility: EducationCompatibility
    requirement: str | None
    explanation: str


@dataclass(frozen=True, slots=True)
class ProfileMatchResult:
    area: AreaCategory
    area_alignment: AreaAlignment
    skills_found_in_job: tuple[str, ...]
    matched_profile_skills: tuple[str, ...]
    requirements_not_in_profile: tuple[str, ...]
    education: EducationMatch
    explanation: tuple[str, ...]


# Formas comuns normalizadas para nomes canônicos. O catálogo também reconhece
# requisitos ausentes do perfil, como Tableau, para não descartá-los do relatório.
_SKILL_ALIASES: dict[str, tuple[str, ...]] = {
    "Python": ("python", "python 3", "python3"),
    "Pandas": ("pandas",),
    "NumPy": ("numpy", "num py"),
    "SQL": ("sql", "sql server", "microsoft sql server", "tsql", "t sql"),
    "Excel": ("excel", "microsoft excel"),
    "Power BI": ("power bi", "powerbi"),
    "Análise de Dados": (
        "análise de dados",
        "data analytics",
        "data analysis",
        "data analyst",
    ),
    "Fundamentos de IA": (
        "fundamentos de ia",
        "inteligência artificial",
        "artificial intelligence",
        "ai fundamentals",
    ),
    "JavaScript": ("javascript", "java script"),
    "Git": ("git",),
    "GitHub": ("github", "git hub"),
    "BI": ("business intelligence",),
    "Tableau": ("tableau",),
    "Java": ("java",),
    "AWS": ("aws", "amazon web services"),
    "Azure": ("azure", "microsoft azure"),
    "Google Cloud": ("google cloud", "gcp"),
    "Apache Spark": ("apache spark", "spark"),
    "ETL/ELT": ("etl", "elt"),
    "Docker": ("docker",),
    "Linux": ("linux",),
    "R": ("linguagem r",),
    "Looker": ("looker",),
    "Databricks": ("databricks",),
    "Snowflake": ("snowflake",),
}
_SKILL_CONTEXT = re.compile(
    r"\b(?:requisitos?|qualificacoes?|conhecimentos?|habilidades?|experiencia|"
    r"diferencial|desejavel|obrigatorio|required|requirements?|qualifications?|"
    r"skills?|knowledge|experience|proficien\w*|using|utilizando|utilizar|uso de|"
    r"trabalhar com|atuacao com|desenvolver|desenvolvimento|construir|criacao|"
    r"criar|aplicar|aplicando|manipular|analisar|analise|gestao|responsavel por|"
    r"auxiliar|apoio|familiaridade|know\s+how)\b"
)

_TECH_COURSES = (
    "Ciência da Computação",
    "Tecnologia da Informação",
    "Engenharia da Computação",
    "Análise e Desenvolvimento de Sistemas",
    "Sistemas de Informação",
    "Engenharia de Software",
    "Sistemas para Internet",
    "Ciência de Dados",
    "Estatística",
    "Matemática",
)
_OTHER_COURSES = (
    "Administração",
    "Marketing",
    "Contabilidade",
    "Direito",
    "Psicologia",
    "Recursos Humanos",
    "Engenharia Civil",
    "Economia",
    "Biologia",
)
_EDUCATION_MARKER = re.compile(
    r"\b(?:formacao|curso|cursando|graduacao|superior|degree|education|"
    r"academic background|estudantes?)\b"
)
_RELATED_EDUCATION = re.compile(
    r"\b(?:areas? correlatas?|areas? afins|related fields|related courses|"
    r"cursos? de tecnologia|technology related)\b"
)
_GENERIC_ENROLLMENT = re.compile(
    r"\b(?:cursando (?:o )?(?:ensino superior|superior|graduacao|curso superior)|"
    r"undergraduate student|currently enrolled in (?:college|university))\b"
)


def load_candidate_profile(
    profile_path: Path | str = "config/profile.toml",
    preferences_path: Path | str = "config/preferences.toml",
) -> CandidateProfile:
    """Carrega perfil e preferências dos TOML já usados pelo projeto."""
    profile_doc = _read_toml(Path(profile_path))
    preferences_doc = _read_toml(Path(preferences_path))
    profile = profile_doc.get("profile", {})
    preferences = preferences_doc.get("preferences", {})
    search = preferences_doc.get("search", {})

    skills = _text_tuple(profile.get("skills", ()), "profile.skills")
    area_names = _text_tuple(preferences.get("areas_priority", ()), "preferences.areas_priority")
    locations = _text_tuple(
        preferences.get("locations", search.get("locations", ())),
        "preferences.locations",
    )
    return CandidateProfile(
        education=_optional_text(profile.get("education")),
        skills=skills,
        area_priorities=_area_priorities(area_names),
        locations=locations,
        work_models=_text_tuple(preferences.get("work_models", ()), "preferences.work_models"),
        employment_types=_text_tuple(
            preferences.get("employment_types_allowed", ()),
            "preferences.employment_types_allowed",
        ),
    )


def match_profile(
    job: Job,
    area: AreaCategory,
    profile: CandidateProfile,
) -> ProfileMatchResult:
    """Gera uma comparação explicável usando a área recebida sem reclassificar a vaga."""
    if not isinstance(area, AreaCategory):
        area = AreaCategory(area)

    skills_found = _find_job_skills(job, profile.skills)
    matched: list[str] = []
    missing: list[str] = []
    for skill in skills_found:
        equivalents = _profile_equivalents(skill)
        profile_label = next(
            (
                original
                for original in profile.skills
                if _canonical_skill(original)[0] in equivalents
            ),
            None,
        )
        if profile_label is not None:
            matched.append(profile_label)
        else:
            missing.append(skill)

    alignment, area_explanation = _area_alignment(area, profile.area_priorities)
    education = _education_match(job.description or "", profile.education)

    general_explanation = [area_explanation]
    if matched:
        general_explanation.append(
            "Habilidades da vaga que correspondem ao perfil: " + ", ".join(matched) + "."
        )
    else:
        general_explanation.append(
            "Não foram encontradas habilidades da vaga no perfil cadastrado."
        )
    if missing:
        general_explanation.append(
            "Requisitos identificados que não constam no perfil: " + ", ".join(missing) + "."
        )
    else:
        general_explanation.append(
            "Nenhuma habilidade identificada ficou sem correspondência no perfil."
        )
    general_explanation.append(education.explanation)

    return ProfileMatchResult(
        area=area,
        area_alignment=alignment,
        skills_found_in_job=skills_found,
        matched_profile_skills=tuple(dict.fromkeys(matched)),
        requirements_not_in_profile=tuple(dict.fromkeys(missing)),
        education=education,
        explanation=tuple(general_explanation),
    )


def _find_job_skills(job: Job, profile_skills: tuple[str, ...]) -> tuple[str, ...]:
    catalog = dict(_SKILL_ALIASES)
    for skill in profile_skills:
        canonical, aliases = _canonical_skill(skill)
        catalog.setdefault(canonical, aliases or (skill,))

    title = _normalize(job.title)
    description_chunks = [
        _normalize(chunk)
        for chunk in re.split(r"[.!?;\n\r]+", job.description or "")
        if chunk.strip()
    ]
    found = []
    for canonical, aliases in catalog.items():
        if _contains_alias(title, aliases):
            found.append(canonical)
            continue
        if any(
            _SKILL_CONTEXT.search(chunk) and _contains_alias(chunk, aliases)
            for chunk in description_chunks
        ):
            found.append(canonical)
    return tuple(found)


def _contains_alias(text: str, aliases: tuple[str, ...]) -> bool:
    for alias in aliases:
        normalized_alias = _normalize(alias)
        if not normalized_alias:
            continue
        pattern = rf"\b{re.escape(normalized_alias)}\b"
        if re.search(pattern, text):
            return True
    return False


def _canonical_skill(skill: str) -> tuple[str, tuple[str, ...]]:
    normalized = _normalize(skill)
    for canonical, aliases in _SKILL_ALIASES.items():
        if normalized == _normalize(canonical) or any(
            normalized == _normalize(alias) for alias in aliases
        ):
            return canonical, aliases
    return skill.strip(), (skill.strip(),)


def _profile_equivalents(skill: str) -> set[str]:
    canonical, _ = _canonical_skill(skill)
    equivalents = {canonical}
    # Power BI é uma habilidade do perfil diretamente relacionada a BI.
    if canonical == "BI":
        equivalents.add("Power BI")
    return equivalents


def _area_alignment(
    area: AreaCategory, priorities: tuple[AreaCategory, ...]
) -> tuple[AreaAlignment, str]:
    if area not in priorities:
        return AreaAlignment.BAIXA, f"A área {area.value} não está entre as prioridades do perfil."
    rank = priorities.index(area)
    if rank < 2:
        return (
            AreaAlignment.ALTA,
            f"A área {area.value} está entre as principais prioridades do perfil.",
        )
    if rank == 2:
        return (
            AreaAlignment.MEDIA,
            f"A área {area.value} é compatível, mas tem prioridade secundária.",
        )
    return AreaAlignment.BAIXA, f"A área {area.value} tem prioridade baixa no perfil."


def _education_match(description: str, candidate_education: str | None) -> EducationMatch:
    text = _normalize(description)
    if not _EDUCATION_MARKER.search(text):
        return EducationMatch(
            EducationCompatibility.NAO_INFORMADO,
            None,
            "A descrição não informa requisito de formação.",
        )
    if not candidate_education:
        return EducationMatch(
            EducationCompatibility.NAO_INFORMADO,
            _education_requirement_excerpt(text),
            "O requisito de formação foi identificado, mas a formação do perfil "
            "não está informada.",
        )

    candidate = _normalize(candidate_education)
    technology_courses = tuple(course for course in _TECH_COURSES if _contains_course(text, course))
    other_courses = tuple(course for course in _OTHER_COURSES if _contains_course(text, course))
    requirement = _education_requirement_excerpt(text)
    candidate_is_technology = any(_contains_course(candidate, course) for course in _TECH_COURSES)
    candidate_courses = tuple(
        course
        for course in (*_TECH_COURSES, *_OTHER_COURSES)
        if _contains_course(candidate, course)
    )

    if technology_courses:
        compatible = candidate_is_technology or any(
            _normalize(course) in {_normalize(item) for item in technology_courses}
            for course in candidate_courses
        )
        return _education_result(
            compatible,
            requirement,
            "A formação do perfil é de tecnologia e atende ao campo de estudo indicado."
            if compatible
            else "A formação do perfil não corresponde ao curso de tecnologia indicado.",
        )

    if other_courses:
        compatible = any(
            _normalize(course) in {_normalize(item) for item in other_courses}
            for course in candidate_courses
        )
        return _education_result(
            compatible,
            requirement,
            "A formação do perfil corresponde à área exigida."
            if compatible
            else "A formação do perfil não corresponde à área de curso indicada.",
        )

    if _RELATED_EDUCATION.search(text):
        compatible = candidate_is_technology
        return _education_result(
            compatible,
            requirement,
            "A formação em tecnologia do perfil se enquadra nas áreas relacionadas aceitas."
            if compatible
            else "A formação do perfil não corresponde às áreas relacionadas indicadas.",
        )

    if _GENERIC_ENROLLMENT.search(text):
        compatible = "superior" in candidate or "graduacao" in candidate
        return _education_result(
            compatible,
            requirement,
            "O perfil informa graduação superior em andamento, conforme solicitado."
            if compatible
            else "O perfil não confirma graduação superior em andamento.",
        )

    return EducationMatch(
        EducationCompatibility.NAO_INFORMADO,
        requirement,
        "A descrição menciona formação, mas não especifica um requisito comparável ao perfil.",
    )


def _education_result(
    compatible: bool, requirement: str | None, explanation: str
) -> EducationMatch:
    status = (
        EducationCompatibility.COMPATIVEL
        if compatible
        else EducationCompatibility.INCOMPATIVEL
    )
    return EducationMatch(status, requirement, explanation)


def _contains_course(text: str, course: str) -> bool:
    return bool(re.search(rf"\b{re.escape(_normalize(course))}\b", text))


def _education_requirement_excerpt(text: str) -> str | None:
    marker = _EDUCATION_MARKER.search(text)
    if not marker:
        return None
    excerpt = text[marker.start() : marker.start() + 120].strip()
    return excerpt or None


def _area_priorities(names: tuple[str, ...]) -> tuple[AreaCategory, ...]:
    aliases: dict[str, tuple[AreaCategory, ...]] = {
        "dados": (AreaCategory.DADOS_ANALYTICS,),
        "analise de dados": (AreaCategory.DADOS_ANALYTICS,),
        "data analytics": (AreaCategory.DADOS_ANALYTICS,),
        "analytics": (AreaCategory.DADOS_ANALYTICS,),
        "bi": (AreaCategory.BI,),
        "business intelligence": (AreaCategory.BI,),
        "ti dados": (AreaCategory.TI_DADOS,),
        "ti relacionada a dados": (AreaCategory.TI_DADOS,),
        "ti": (AreaCategory.TI_DADOS, AreaCategory.TI_GERAL),
    }
    ordered: list[AreaCategory] = []
    for name in names:
        normalized = _normalize(name)
        values = aliases.get(normalized)
        if values is None:
            try:
                values = (AreaCategory(name),)
            except ValueError:
                continue
        for area in values:
            if area not in ordered:
                ordered.append(area)
    return tuple(ordered)


def _read_toml(path: Path) -> dict[str, Any]:
    try:
        with path.open("rb") as file:
            return tomllib.load(file)
    except FileNotFoundError as exc:
        raise FileNotFoundError(f"Arquivo de perfil não encontrado: {path}") from exc
    except tomllib.TOMLDecodeError as exc:
        raise ValueError(f"TOML inválido em {path}: {exc}") from exc


def _text_tuple(value: Any, name: str) -> tuple[str, ...]:
    if not isinstance(value, list) or any(not isinstance(item, str) for item in value):
        raise ValueError(f"{name} deve ser uma lista de textos.")
    return tuple(item.strip() for item in value if item.strip())


def _optional_text(value: Any) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise ValueError("profile.education deve ser um texto.")
    return value.strip() or None


def _normalize(text: str) -> str:
    decomposed = unicodedata.normalize("NFKD", text.casefold())
    without_accents = "".join(char for char in decomposed if not unicodedata.combining(char))
    return re.sub(r"[^a-z0-9]+", " ", without_accents).strip()
