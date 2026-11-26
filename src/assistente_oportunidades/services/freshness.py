"""Política central de validade temporal das vagas armazenadas."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from assistente_oportunidades.models import Job, utc_now


def is_job_within_age_limit(
    job: Job,
    max_days_old: int,
    *,
    now: datetime | None = None,
) -> bool:
    """Retorna se a publicação (ou coleta, como fallback) está na janela inclusiva."""
    if max_days_old < 1:
        raise ValueError("max_days_old deve ser pelo menos 1.")

    reference = _as_utc(now or utc_now())
    published_at = _usable_datetime(job.published_at, reference)
    collected_at = _usable_datetime(job.collected_at, reference)
    effective_date = published_at or collected_at
    if effective_date is None:
        return False

    cutoff = reference - timedelta(days=max_days_old)
    return cutoff <= effective_date <= reference


def _usable_datetime(value: object, reference: datetime) -> datetime | None:
    if not isinstance(value, datetime) or value.tzinfo is None:
        return None
    normalized = _as_utc(value)
    if normalized > reference:
        return None
    return normalized


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)
