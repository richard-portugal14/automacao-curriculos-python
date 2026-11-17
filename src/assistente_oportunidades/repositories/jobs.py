"""Repositório SQLite para vagas e deduplicação persistente."""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime
from pathlib import Path

from assistente_oportunidades.models import Job


class JobRepository:
    def __init__(self, database_path: Path | str) -> None:
        self.database_path = Path(database_path)
        self.database_path.parent.mkdir(parents=True, exist_ok=True)
        self._connection = sqlite3.connect(self.database_path)
        self._connection.row_factory = sqlite3.Row
        self._connection.execute("PRAGMA foreign_keys = ON")
        self._initialize()

    def close(self) -> None:
        self._connection.close()

    def __enter__(self) -> JobRepository:
        return self

    def __exit__(self, *_: object) -> None:
        self.close()

    def save(self, job: Job) -> bool:
        """Insere ou atualiza a vaga; retorna True apenas para vaga inédita."""
        existing = self._connection.execute(
            "SELECT id FROM jobs WHERE deduplication_key = ?", (job.deduplication_key,)
        ).fetchone()
        values = _job_values(job)
        if existing is None:
            self._connection.execute(
                """INSERT INTO jobs (
                    source, external_id, deduplication_key, title, company, location,
                    description, url, published_at, contract_type, contract_time,
                    salary_min, salary_max, salary_is_predicted, category, latitude,
                    longitude, raw_json, collected_at, analyzed_at, score, status
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                values,
            )
            self._connection.commit()
            return True

        self._connection.execute(
            """UPDATE jobs SET
                title=?, company=?, location=?, description=?, url=?, published_at=?,
                contract_type=?, contract_time=?, salary_min=?, salary_max=?,
                salary_is_predicted=?, category=?, latitude=?, longitude=?, raw_json=?,
                collected_at=?
            WHERE deduplication_key=?""",
            (
                job.title, job.company, job.location, job.description, job.url,
                _iso(job.published_at), job.contract_type, job.contract_time,
                job.salary_min, job.salary_max,
                None if job.salary_is_predicted is None else int(job.salary_is_predicted),
                job.category, job.latitude, job.longitude,
                json.dumps(job.raw, ensure_ascii=False), _iso(job.collected_at),
                job.deduplication_key,
            ),
        )
        self._connection.commit()
        return False

    def get(self, deduplication_key: str) -> sqlite3.Row | None:
        return self._connection.execute(
            "SELECT * FROM jobs WHERE deduplication_key = ?", (deduplication_key,)
        ).fetchone()

    def list_for_inspection(self, limit: int = 10) -> list[sqlite3.Row]:
        """Retorna os campos necessários para inspecionar anúncios armazenados."""
        if limit < 1:
            raise ValueError("O limite de vagas deve ser pelo menos 1.")
        rows = self._connection.execute(
            """SELECT title, company, location, contract_type, category, description, url
            FROM jobs
            ORDER BY collected_at DESC, id DESC
            LIMIT ?""",
            (limit,),
        )
        return list(rows.fetchall())

    def _initialize(self) -> None:
        self._connection.execute(
            """CREATE TABLE IF NOT EXISTS jobs (
                id INTEGER PRIMARY KEY,
                source TEXT NOT NULL,
                external_id TEXT NOT NULL,
                deduplication_key TEXT NOT NULL UNIQUE,
                title TEXT NOT NULL,
                company TEXT,
                location TEXT,
                description TEXT,
                url TEXT NOT NULL,
                published_at TEXT,
                contract_type TEXT,
                contract_time TEXT,
                salary_min REAL,
                salary_max REAL,
                salary_is_predicted INTEGER,
                category TEXT,
                latitude REAL,
                longitude REAL,
                raw_json TEXT NOT NULL,
                collected_at TEXT NOT NULL,
                analyzed_at TEXT,
                score REAL,
                status TEXT NOT NULL
            )"""
        )
        self._connection.execute(
            "CREATE INDEX IF NOT EXISTS idx_jobs_collected_at ON jobs(collected_at)"
        )
        self._connection.commit()


def _job_values(job: Job) -> tuple[object, ...]:
    return (
        job.source, job.external_id, job.deduplication_key, job.title, job.company,
        job.location, job.description, job.url, _iso(job.published_at), job.contract_type,
        job.contract_time, job.salary_min, job.salary_max,
        None if job.salary_is_predicted is None else int(job.salary_is_predicted),
        job.category, job.latitude, job.longitude, json.dumps(job.raw, ensure_ascii=False),
        _iso(job.collected_at), _iso(job.analyzed_at), job.score, job.status,
    )


def _iso(value: datetime | None) -> str | None:
    return value.isoformat() if value else None
