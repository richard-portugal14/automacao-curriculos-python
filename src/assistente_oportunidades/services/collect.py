"""Orquestra coleta, normalização e persistência sem interface de usuário."""

from __future__ import annotations

from dataclasses import dataclass

from assistente_oportunidades.config import AppConfig
from assistente_oportunidades.repositories.jobs import JobRepository
from assistente_oportunidades.sources.adzuna import AdzunaSource


@dataclass(frozen=True, slots=True)
class CollectionSummary:
    received: int
    inserted: int
    updated: int


def collect_adzuna(config: AppConfig) -> CollectionSummary:
    """Busca as consultas configuradas e persiste vagas sem duplicar registros."""
    if not config.app_id or not config.app_key:
        raise ValueError("Configure ADZUNA_APP_ID e ADZUNA_APP_KEY no arquivo .env ou ambiente.")

    received = inserted = 0
    with JobRepository(config.database_path) as repository:
        with AdzunaSource(config.app_id, config.app_key, config.search) as source:
            for job in source.search():
                received += 1
                if repository.save(job):
                    inserted += 1
    return CollectionSummary(received, inserted, received - inserted)
