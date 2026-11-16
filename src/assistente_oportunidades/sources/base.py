"""Contrato pequeno compartilhado pelas fontes de vagas."""

from __future__ import annotations

from collections.abc import Iterator
from typing import Protocol

from assistente_oportunidades.models import Job


class JobSource(Protocol):
    name: str

    def search(self) -> Iterator[Job]: ...
