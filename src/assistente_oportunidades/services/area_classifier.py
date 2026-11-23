"""Classificação explicável da área de uma vaga, sem integração ao pipeline."""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from enum import Enum

from assistente_oportunidades.models import Job


class AreaCategory(str, Enum):
    DADOS_ANALYTICS = "DADOS_ANALYTICS"
    BI = "BI"
    TI_DADOS = "TI_DADOS"
    TI_GERAL = "TI_GERAL"
    OUTRA = "OUTRA"


@dataclass(frozen=True, slots=True)
class AreaClassificationResult:
    category: AreaCategory
    explanation: str
    evidence: tuple[str, ...]


_DATA_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("análise de dados", re.compile(r"\banalise de dados\b|\bdata analysis\b")),
    ("analista de dados", re.compile(r"\banalista de dados\b|\bdata analyst\b")),
    ("data analytics", re.compile(r"\bdata analytics\b")),
    ("ciência de dados", re.compile(r"\bciencia de dados\b|\bdata science\b")),
    ("estatística aplicada a dados", re.compile(r"\bestatistica aplicada (?:a|aos) dados\b")),
    ("gestão de dados", re.compile(r"\bgestao de dados\b|\bdata management\b")),
    ("analytics", re.compile(r"\banalytics\b")),
    ("dados", re.compile(r"\bdados\b")),
)
_BI_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("Business Intelligence", re.compile(r"\bbusiness intelligence\b")),
    ("Power BI", re.compile(r"\bpower bi\b")),
    ("BI", re.compile(r"\bbi\b")),
    ("dashboards", re.compile(r"\bdashboards?\b")),
    ("indicadores", re.compile(r"\bindicadores?\b")),
    ("reporting", re.compile(r"\breporting\b|\brelatorios?\b")),
    ("visualização de dados", re.compile(r"\bvisualizacao de dados\b|\bdata visualization\b")),
)
_IT_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("TI", re.compile(r"\bti\b|\btecnologia da informacao\b|\binformation technology\b")),
    (
        "desenvolvimento de software",
        re.compile(r"\bdesenvolvedor(?:a)?\b|\bdeveloper\b|\bsoftware\b|\bdev\b"),
    ),
    (
        "suporte técnico",
        re.compile(r"\bsuporte tecnico\b|\bhelp desk\b|\bhelpdesk\b|\bit support\b"),
    ),
    ("infraestrutura e redes", re.compile(r"\binfraestrutura\b|\bredes\b|\bnetwork(?:s|ing)?\b")),
    (
        "sistemas e manutenção",
        re.compile(r"\badministracao de sistemas\b|\bsistemas?\b|\bmanutencao de computadores\b"),
    ),
    (
        "suporte a usuários",
        re.compile(
            r"\bsuporte aos usuarios\b|\bsuporte a usuarios\b|"
            r"\buser support\b|\bimpressoras?\b"
        ),
    ),
)
_DATA_ENGINEERING_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    (
        "engenharia de dados",
        re.compile(r"\bengenharia de dados\b|\bdata engineer(?:ing)?s?\b"),
    ),
    ("pipelines de dados", re.compile(r"\bdata pipelines?\b|\bpipelines? (?:de )?dados\b")),
    ("automação de dados", re.compile(r"\bautomacao de dados\b|\bdata automation\b")),
    (
        "cloud aplicada a dados",
        re.compile(r"\bcloud\b.{0,50}\b(?:dados|data)\b|\b(?:dados|data)\b.{0,50}\bcloud\b"),
    ),
)
_ETL = re.compile(r"\b(?:etl|elt)\b")
_PYTHON_OR_SQL = re.compile(r"\b(?:python|sql)\b")
_DATA_PROCESSING = re.compile(
    r"\b(?:tratamento|analise|integracao|modelagem|processamento) de dados\b|\bdata processing\b"
)
_TITLE_DATA_ENGINEERING = re.compile(
    r"\bengenharia de dados\b|\bdata engineer(?:ing)?s?\b"
)


def classify_area(job: Job) -> AreaClassificationResult:
    """Classifica a área com evidências de título e descrição, sem usar metadados da fonte."""
    title = _normalize(job.title)
    description = _normalize(job.description or "")
    combined = f"{title} {description}"

    title_data = _find_evidence(title, _DATA_PATTERNS)
    title_bi = _find_evidence(title, _BI_PATTERNS)
    title_it = _find_evidence(title, _IT_PATTERNS)
    description_data = _find_evidence(description, _DATA_PATTERNS)
    description_bi = _find_evidence(description, _BI_PATTERNS)
    strong_description_data = tuple(
        evidence for evidence in description_data if evidence != "dados"
    )
    engineering = _find_evidence(combined, _DATA_ENGINEERING_PATTERNS)

    engineering_context = bool(
        _TITLE_DATA_ENGINEERING.search(title)
        or (
            title_it
            and (
                engineering
                or strong_description_data
                or (_ETL.search(description) and _PYTHON_OR_SQL.search(description))
                or (_PYTHON_OR_SQL.search(description) and _DATA_PROCESSING.search(description))
            )
        )
    )
    if engineering_context:
        evidence = _unique(
            (
                *title_it,
                *_find_evidence(title, _DATA_ENGINEERING_PATTERNS),
                *engineering,
                *strong_description_data,
            )
        )
        if _ETL.search(description):
            evidence += ("ETL/ELT",)
        if _PYTHON_OR_SQL.search(description):
            evidence += tuple(
                tool.upper() if tool == "sql" else "Python"
                for tool in ("python", "sql")
                if re.search(rf"\b{tool}\b", description)
            )
        return _result(
            AreaCategory.TI_DADOS,
            "O título indica uma função de TI e a descrição traz atuação técnica ligada a dados.",
            evidence,
        )

    if title_bi:
        return _result(
            AreaCategory.BI,
            "O título contém evidência direta de Business Intelligence ou "
            "visualização de indicadores.",
            title_bi,
        )

    if title_it and title_data == ("dados",):
        return _result(
            AreaCategory.TI_GERAL,
            "O título indica TI, mas a menção isolada a dados não comprova atuação "
            "especializada em dados.",
            _unique((*title_it, *title_data)),
        )

    if title_data:
        return _result(
            AreaCategory.DADOS_ANALYTICS,
            "O título identifica diretamente uma função ou área de dados e analytics.",
            title_data,
        )

    if _has_strong_bi_description(description, description_bi):
        return _result(
            AreaCategory.BI,
            "A descrição reúne evidências específicas de BI, dashboards ou indicadores.",
            description_bi,
        )

    if strong_description_data:
        return _result(
            AreaCategory.DADOS_ANALYTICS,
            "A descrição menciona uma atividade específica de análise, ciência ou gestão de dados.",
            strong_description_data,
        )

    if title_it:
        return _result(
            AreaCategory.TI_GERAL,
            "O título indica uma função de TI sem evidência forte de atuação com dados.",
            title_it,
        )

    description_it = _find_evidence(description, _IT_PATTERNS)
    if description_it:
        return _result(
            AreaCategory.TI_GERAL,
            "A descrição indica atividades gerais de TI, sem evidência forte de atuação com dados.",
            description_it,
        )

    incidental_data = tuple(evidence for evidence in description_data if evidence == "dados")
    explanation = (
        "A menção incidental a dados na descrição não basta para classificar a vaga "
        "como Dados/Analytics."
        if incidental_data
        else "Não há evidências suficientes para associar a vaga às categorias de Dados, BI ou TI."
    )
    return _result(AreaCategory.OUTRA, explanation, incidental_data)


def _has_strong_bi_description(
    description: str, evidence: tuple[str, ...]
) -> bool:
    if not evidence:
        return False
    explicit_bi = (
        r"\bbusiness intelligence\b|\bpower bi\b|\bvisualizacao de dados\b|"
        r"\bdata visualization\b"
    )
    if re.search(explicit_bi, description):
        return True
    return len(evidence) >= 2


def _find_evidence(
    text: str, patterns: tuple[tuple[str, re.Pattern[str]], ...]
) -> tuple[str, ...]:
    return tuple(label for label, pattern in patterns if pattern.search(text))


def _result(
    category: AreaCategory, explanation: str, evidence: tuple[str, ...]
) -> AreaClassificationResult:
    return AreaClassificationResult(category, explanation, _unique(evidence))


def _unique(values: tuple[str, ...]) -> tuple[str, ...]:
    return tuple(dict.fromkeys(values))


def _normalize(text: str) -> str:
    decomposed = unicodedata.normalize("NFKD", text.casefold())
    without_accents = "".join(char for char in decomposed if not unicodedata.combining(char))
    return re.sub(r"[^a-z0-9]+", " ", without_accents).strip()
