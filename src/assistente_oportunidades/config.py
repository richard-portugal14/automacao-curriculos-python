"""Leitura da configuração TOML e das credenciais do Adzuna."""

from __future__ import annotations

import os
import tomllib
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from dotenv import load_dotenv

DEFAULT_MAX_DAYS_OLD = 30


@dataclass(frozen=True, slots=True)
class SearchConfig:
    country: str
    terms: tuple[str, ...]
    locations: tuple[str, ...]
    results_per_page: int = 20
    max_pages_per_query: int = 1
    max_days_old: int = DEFAULT_MAX_DAYS_OLD


@dataclass(frozen=True, slots=True)
class AppConfig:
    profile: dict[str, Any]
    preferences: dict[str, Any]
    search: SearchConfig
    app_id: str | None
    app_key: str | None
    database_path: Path


def _read_toml(path: Path) -> dict[str, Any]:
    try:
        with path.open("rb") as file:
            return tomllib.load(file)
    except FileNotFoundError as exc:
        raise FileNotFoundError(f"Arquivo de configuração não encontrado: {path}") from exc
    except tomllib.TOMLDecodeError as exc:
        raise ValueError(f"TOML inválido em {path}: {exc}") from exc


def load_config(config_dir: Path | str = "config", database_path: Path | str = "data/jobs.sqlite3") -> AppConfig:
    """Carrega perfil e preferências; credenciais vêm somente do ambiente."""
    load_dotenv()
    directory = Path(config_dir)
    profile_doc = _read_toml(directory / "profile.toml")
    preferences_doc = _read_toml(directory / "preferences.toml")

    search_doc = preferences_doc.get("search", {})
    terms = tuple(_non_empty_strings(search_doc.get("terms", []), "search.terms"))
    locations = tuple(_non_empty_strings(search_doc.get("locations", []), "search.locations"))
    country = str(search_doc.get("country", "br")).strip().lower()
    results_per_page = int(search_doc.get("results_per_page", 20))
    max_pages = int(search_doc.get("max_pages_per_query", 1))
    max_days_old = int(search_doc.get("max_days_old", DEFAULT_MAX_DAYS_OLD))
    if not country.isalpha() or len(country) != 2:
        raise ValueError("search.country deve ser um código de país com duas letras.")
    if not 1 <= results_per_page <= 50:
        raise ValueError("search.results_per_page deve estar entre 1 e 50.")
    if max_pages < 1:
        raise ValueError("search.max_pages_per_query deve ser pelo menos 1.")
    if max_days_old < 1:
        raise ValueError("search.max_days_old deve ser pelo menos 1.")
    if not terms:
        raise ValueError("Configure ao menos um termo em search.terms.")
    if not locations:
        raise ValueError("Configure ao menos uma localidade em search.locations.")

    return AppConfig(
        profile=profile_doc.get("profile", {}),
        preferences=preferences_doc.get("preferences", {}),
        search=SearchConfig(country, terms, locations, results_per_page, max_pages, max_days_old),
        app_id=os.getenv("ADZUNA_APP_ID") or None,
        app_key=os.getenv("ADZUNA_APP_KEY") or None,
        database_path=Path(database_path),
    )


def _non_empty_strings(value: Any, name: str) -> list[str]:
    if not isinstance(value, list) or any(not isinstance(item, str) for item in value):
        raise ValueError(f"{name} deve ser uma lista de textos.")
    return [item.strip() for item in value if item.strip()]
