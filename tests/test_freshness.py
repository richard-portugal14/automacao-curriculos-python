from datetime import datetime, timedelta, timezone
from pathlib import Path

import httpx
import pytest

from assistente_oportunidades.config import SearchConfig
from assistente_oportunidades.config import load_config
from assistente_oportunidades.models import Job
from assistente_oportunidades.repositories.jobs import JobRepository
from assistente_oportunidades.services.freshness import is_job_within_age_limit
from assistente_oportunidades.sources.adzuna import AdzunaSource


NOW = datetime(2026, 11, 26, 12, tzinfo=timezone.utc)


def _job(*, published_at=None, collected_at=None) -> Job:
    return Job(
        source="test",
        external_id="freshness-job",
        title="Estágio em Dados",
        company="Empresa Exemplo",
        location="São Paulo",
        description="Conhecimento em SQL.",
        url="https://example.test/job",
        published_at=published_at,
        collected_at=collected_at or NOW,
    )


def test_job_published_within_30_days_is_current():
    job = _job(published_at=NOW - timedelta(days=29))

    assert is_job_within_age_limit(job, 30, now=NOW)


def test_job_published_exactly_30_days_ago_is_included_inclusive_boundary():
    job = _job(published_at=NOW - timedelta(days=30))

    assert is_job_within_age_limit(job, 30, now=NOW)


def test_job_published_more_than_30_days_ago_is_expired():
    job = _job(published_at=NOW - timedelta(days=30, microseconds=1))

    assert not is_job_within_age_limit(job, 30, now=NOW)


def test_missing_published_at_uses_persisted_collection_date():
    recent = _job(published_at=None, collected_at=NOW - timedelta(days=2))
    old = _job(published_at=None, collected_at=NOW - timedelta(days=31))

    assert is_job_within_age_limit(recent, 30, now=NOW)
    assert not is_job_within_age_limit(old, 30, now=NOW)


def test_invalid_published_at_uses_persisted_collection_date():
    job = _job(published_at="not-a-date", collected_at=NOW - timedelta(days=2))

    assert is_job_within_age_limit(job, 30, now=NOW)


def test_publication_date_without_timezone_uses_persisted_collection_date():
    job = _job(
        published_at=(NOW - timedelta(days=2)).replace(tzinfo=None),
        collected_at=NOW - timedelta(days=3),
    )

    assert is_job_within_age_limit(job, 30, now=NOW)


def test_future_published_at_is_unusable_and_falls_back_to_collection_date():
    job = _job(
        published_at=NOW + timedelta(days=1),
        collected_at=NOW - timedelta(days=2),
    )

    assert is_job_within_age_limit(job, 30, now=NOW)


def test_no_usable_publication_or_collection_date_is_not_current():
    job = _job(published_at="not-a-date", collected_at="also-not-a-date")

    assert not is_job_within_age_limit(job, 30, now=NOW)


def test_non_positive_age_limit_is_rejected():
    with pytest.raises(ValueError, match="pelo menos 1"):
        is_job_within_age_limit(_job(), 0, now=NOW)


def test_max_days_old_is_loaded_from_preferences_toml(tmp_path: Path, monkeypatch):
    config_dir = tmp_path / "config"
    config_dir.mkdir()
    (config_dir / "profile.toml").write_text("[profile]\n", encoding="utf-8")
    (config_dir / "preferences.toml").write_text(
        '[search]\ncountry = "br"\nterms = ["estágio dados"]\n'
        'locations = ["São Paulo"]\nmax_days_old = 17\n',
        encoding="utf-8",
    )
    monkeypatch.delenv("ADZUNA_APP_ID", raising=False)
    monkeypatch.delenv("ADZUNA_APP_KEY", raising=False)

    config = load_config(config_dir, tmp_path / "jobs.sqlite3")

    assert config.search.max_days_old == 17


def test_repository_restores_persisted_dates_instead_of_using_load_time(tmp_path: Path):
    database = tmp_path / "jobs.sqlite3"
    published = NOW - timedelta(days=10)
    collected = NOW - timedelta(days=4)
    job = _job(published_at=published, collected_at=collected)

    with JobRepository(database) as repository:
        repository.save(job)
        loaded = repository.list_all()[0]

    assert loaded.published_at == published
    assert loaded.collected_at == collected


def test_repository_treats_invalid_persisted_publication_date_as_missing(tmp_path: Path):
    database = tmp_path / "jobs.sqlite3"
    collected = NOW - timedelta(days=5)
    job = _job(published_at=None, collected_at=collected)

    with JobRepository(database) as repository:
        repository.save(job)
        repository._connection.execute(
            "UPDATE jobs SET published_at = ? WHERE deduplication_key = ?",
            ("invalid-date", job.deduplication_key),
        )
        repository._connection.commit()
        loaded = repository.list_all()[0]

    assert loaded.published_at is None
    assert loaded.collected_at == collected


def test_repository_treats_unexpected_date_type_as_missing(tmp_path: Path):
    database = tmp_path / "jobs.sqlite3"
    collected = NOW - timedelta(days=5)
    job = _job(published_at=None, collected_at=collected)

    with JobRepository(database) as repository:
        repository.save(job)
        repository._connection.execute(
            "UPDATE jobs SET published_at = ? WHERE deduplication_key = ?",
            (123, job.deduplication_key),
        )
        repository._connection.commit()
        loaded = repository.list_all()[0]

    assert loaded.published_at is None
    assert loaded.collected_at == collected


def test_repository_invalid_collection_date_does_not_make_vacancy_look_recent(
    tmp_path: Path,
):
    database = tmp_path / "jobs.sqlite3"
    job = _job(published_at=None, collected_at=NOW - timedelta(days=2))

    with JobRepository(database) as repository:
        repository.save(job)
        repository._connection.execute(
            "UPDATE jobs SET collected_at = ? WHERE deduplication_key = ?",
            ("invalid-date", job.deduplication_key),
        )
        repository._connection.commit()
        loaded = repository.list_all()[0]

    assert not is_job_within_age_limit(loaded, 30, now=NOW)


def test_adzuna_search_receives_configured_max_days_old():
    seen_params: list[httpx.QueryParams] = []

    def handle(request: httpx.Request) -> httpx.Response:
        seen_params.append(request.url.params)
        return httpx.Response(200, json={"results": []})

    client = httpx.Client(transport=httpx.MockTransport(handle))
    search = SearchConfig("br", ("estágio dados",), ("São Paulo",), max_days_old=30)
    source = AdzunaSource("app-id", "app-key", search, client=client)

    list(source.search())
    client.close()

    assert len(seen_params) == 1
    assert seen_params[0]["max_days_old"] == "30"


def test_adzuna_search_uses_other_search_configuration():
    seen_requests: list[tuple[str, httpx.QueryParams]] = []

    def handle(request: httpx.Request) -> httpx.Response:
        seen_requests.append((request.url.path, request.url.params))
        return httpx.Response(200, json={"results": []})

    client = httpx.Client(transport=httpx.MockTransport(handle))
    search = SearchConfig(
        country="br",
        terms=("term-a", "term-b"),
        locations=("location-a", "location-b"),
        results_per_page=17,
        max_pages_per_query=2,
        max_days_old=30,
    )
    source = AdzunaSource("app-id", "app-key", search, client=client)

    list(source.search())
    client.close()

    assert len(seen_requests) == 8
    assert {path.rsplit("/", 1)[-1] for path, _ in seen_requests} == {"1", "2"}
    assert {params["what"] for _, params in seen_requests} == {"term-a", "term-b"}
    assert {params["where"] for _, params in seen_requests} == {
        "location-a",
        "location-b",
    }
    assert all(params["results_per_page"] == "17" for _, params in seen_requests)
    assert all("/br/search/" in path for path, _ in seen_requests)
