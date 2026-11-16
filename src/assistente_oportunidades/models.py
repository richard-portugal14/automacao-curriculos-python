"""Modelos internos usados pelas fontes e pela persistência."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


@dataclass(slots=True)
class Job:
    """Representação normalizada de uma oportunidade coletada."""

    source: str
    external_id: str
    title: str
    company: str | None
    location: str | None
    description: str | None
    url: str
    published_at: datetime | None = None
    contract_type: str | None = None
    contract_time: str | None = None
    salary_min: float | None = None
    salary_max: float | None = None
    salary_is_predicted: bool | None = None
    category: str | None = None
    latitude: float | None = None
    longitude: float | None = None
    raw: dict[str, Any] = field(default_factory=dict, repr=False)
    collected_at: datetime = field(default_factory=utc_now)
    analyzed_at: datetime | None = None
    score: float | None = None
    status: str = "coletada"
    deduplication_key: str = ""

    def __post_init__(self) -> None:
        if not self.title.strip():
            raise ValueError("O título da vaga não pode ser vazio.")
        if not self.url.strip():
            raise ValueError("A URL da vaga não pode ser vazia.")
        if not self.deduplication_key:
            self.deduplication_key = f"{self.source}:{self.external_id}"
