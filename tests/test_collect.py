from pathlib import Path

from assistente_oportunidades.config import AppConfig, SearchConfig
from assistente_oportunidades.models import Job
from assistente_oportunidades.services import collect


class FakeAdzunaSource:
    def __init__(self, app_id, app_key, search):
        pass

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        pass

    def search(self):
        yield Job(
            source="adzuna",
            external_id="job-1",
            title="Estágio em Dados",
            company="Empresa Exemplo",
            location="São Paulo",
            description="SQL e Python",
            url="https://example.test/job-1",
        )


def test_collect_adzuna_returns_inserted_and_updated_counts(monkeypatch, tmp_path: Path):
    monkeypatch.setattr(collect, "AdzunaSource", FakeAdzunaSource)
    config = AppConfig(
        profile={},
        preferences={},
        search=SearchConfig("br", ("estágio dados",), ("São Paulo",)),
        app_id="test-id",
        app_key="test-key",
        database_path=tmp_path / "jobs.sqlite3",
    )

    first_run = collect.collect_adzuna(config)
    second_run = collect.collect_adzuna(config)

    assert (first_run.received, first_run.inserted, first_run.updated) == (1, 1, 0)
    assert (second_run.received, second_run.inserted, second_run.updated) == (1, 0, 1)
