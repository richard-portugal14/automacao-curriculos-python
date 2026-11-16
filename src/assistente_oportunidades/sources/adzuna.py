"""Cliente da API oficial de busca de vagas da Adzuna."""

from __future__ import annotations

import hashlib
import logging
import re
from collections.abc import Iterator, Mapping
from datetime import datetime
from typing import Any
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

import httpx

from assistente_oportunidades.config import SearchConfig
from assistente_oportunidades.models import Job

logger = logging.getLogger(__name__)


class AdzunaError(RuntimeError):
    """Falha de autenticação, rede ou resposta da API Adzuna."""


class AdzunaSource:
    name = "adzuna"
    base_url = "https://api.adzuna.com/v1/api/jobs"

    def __init__(
        self,
        app_id: str,
        app_key: str,
        search: SearchConfig,
        *,
        timeout: float = 20.0,
        client: httpx.Client | None = None,
    ) -> None:
        if not app_id.strip() or not app_key.strip():
            raise ValueError("Configure ADZUNA_APP_ID e ADZUNA_APP_KEY no ambiente.")
        self.app_id = app_id
        self.app_key = app_key
        self.search_config = search
        self._client = client or httpx.Client(timeout=timeout, follow_redirects=True)
        self._owns_client = client is None

    def close(self) -> None:
        if self._owns_client:
            self._client.close()

    def __enter__(self) -> AdzunaSource:
        return self

    def __exit__(self, *_: object) -> None:
        self.close()

    def search(self) -> Iterator[Job]:
        """Consulta cada combinação termo/localidade, sem repetir resultados locais."""
        seen: set[str] = set()
        for term in self.search_config.terms:
            for location in self.search_config.locations:
                for page in range(1, self.search_config.max_pages_per_query + 1):
                    for job in self._search_page(term, location, page):
                        if job.deduplication_key not in seen:
                            seen.add(job.deduplication_key)
                            yield job

    def _search_page(self, term: str, location: str, page: int) -> list[Job]:
        endpoint = f"{self.base_url}/{self.search_config.country}/search/{page}"
        params = {
            "app_id": self.app_id,
            "app_key": self.app_key,
            "results_per_page": self.search_config.results_per_page,
            "what": term,
            "where": location,
            "content-type": "application/json",
        }
        try:
            response = self._client.get(endpoint, params=params)
            response.raise_for_status()
            payload = response.json()
        except httpx.HTTPStatusError as exc:
            code = exc.response.status_code
            if code in (401, 403):
                message = "Credenciais Adzuna inválidas ou sem acesso à API."
            elif code == 429:
                message = "Limite de requisições Adzuna atingido; aguarde antes de tentar novamente."
            else:
                message = f"A API Adzuna respondeu com HTTP {code}."
            raise AdzunaError(message) from exc
        except (httpx.HTTPError, ValueError) as exc:
            # Evita incluir a URL da requisição (que contém app_key) em mensagens/logs.
            raise AdzunaError("Não foi possível consultar ou interpretar a resposta Adzuna.") from exc

        if not isinstance(payload, dict) or not isinstance(payload.get("results", []), list):
            raise AdzunaError("A resposta Adzuna não contém a lista esperada em 'results'.")
        jobs: list[Job] = []
        for item in payload.get("results", []):
            if not isinstance(item, dict):
                logger.warning("Resultado Adzuna ignorado: formato inesperado.")
                continue
            try:
                jobs.append(normalize_adzuna_job(item))
            except (KeyError, TypeError, ValueError) as exc:
                logger.warning("Resultado Adzuna ignorado por dados inválidos: %s", exc)
        return jobs


def normalize_adzuna_job(item: Mapping[str, Any]) -> Job:
    """Converte um anúncio Adzuna para o modelo interno, sem completar dados ausentes."""
    external_id = str(item.get("id", "")).strip()
    title = str(item.get("title", "")).strip()
    url = _normalize_url(str(item.get("redirect_url", "")).strip())
    if not external_id or not title or not url:
        raise ValueError("anúncio sem id, título ou URL")

    company_raw = item.get("company")
    location_raw = item.get("location")
    category_raw = item.get("category")
    published = _parse_datetime(item.get("created"))

    return Job(
        source="adzuna",
        external_id=external_id,
        title=title,
        company=_nested_text(company_raw, "display_name"),
        location=_nested_text(location_raw, "display_name"),
        description=_optional_text(item.get("description")),
        url=url,
        published_at=published,
        contract_type=_optional_text(item.get("contract_type")),
        contract_time=_optional_text(item.get("contract_time")),
        salary_min=_optional_number(item.get("salary_min")),
        salary_max=_optional_number(item.get("salary_max")),
        salary_is_predicted=_optional_bool(item.get("salary_is_predicted")),
        category=_nested_text(category_raw, "label"),
        latitude=_optional_number(item.get("latitude")),
        longitude=_optional_number(item.get("longitude")),
        raw=dict(item),
        deduplication_key=f"adzuna:{external_id}",
    )


def _normalize_url(url: str) -> str:
    if not url:
        return ""
    parts = urlsplit(url)
    kept = [(key, value) for key, value in parse_qsl(parts.query) if not key.lower().startswith("utm_")]
    return urlunsplit((parts.scheme.lower(), parts.netloc.lower(), parts.path.rstrip("/"), urlencode(kept), ""))


def fallback_fingerprint(title: str, company: str | None, location: str | None, url: str = "") -> str:
    """Chave de contingência para fontes futuras sem identificador estável."""
    normalized_url = _normalize_url(url)
    identity = normalized_url or "|".join(
        re.sub(r"\s+", " ", value or "").strip().casefold()
        for value in (title, company or "", location or "")
    )
    return hashlib.sha256(identity.encode("utf-8")).hexdigest()


def _nested_text(value: Any, key: str) -> str | None:
    if isinstance(value, Mapping):
        return _optional_text(value.get(key))
    return None


def _optional_text(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _optional_number(value: Any) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _optional_bool(value: Any) -> bool | None:
    if value is None:
        return None
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    return None


def _parse_datetime(value: Any) -> datetime | None:
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
