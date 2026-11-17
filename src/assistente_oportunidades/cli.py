"""Interface de terminal para as operações disponíveis no MVP."""

from __future__ import annotations

import argparse
import sqlite3
import sys
from collections.abc import Sequence
from pathlib import Path

from assistente_oportunidades.config import load_config
from assistente_oportunidades.repositories.jobs import JobRepository
from assistente_oportunidades.services.collect import collect_adzuna
from assistente_oportunidades.services.internship_classifier import InternshipClassification
from assistente_oportunidades.services.internship_diagnostic import (
    ClassifiedJob,
    diagnose_stored_jobs,
)
from assistente_oportunidades.sources.adzuna import AdzunaError


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="assistente-oportunidades",
        description="Busca e armazena vagas da Adzuna no banco local.",
    )
    commands = parser.add_subparsers(dest="command", required=True)
    collect = commands.add_parser("collect", help="coleta vagas conforme config/preferences.toml")
    collect.add_argument("--config-dir", type=Path, default=Path("config"))
    collect.add_argument("--database", type=Path, default=Path("data/jobs.sqlite3"))

    inspect = commands.add_parser(
        "inspect-descriptions",
        help="exibe os campos e descrições das vagas armazenadas",
    )
    inspect.add_argument("--limit", type=int, default=10, help="quantidade de vagas (padrão: 10)")
    inspect.add_argument("--database", type=Path, default=Path("data/jobs.sqlite3"))

    diagnose = commands.add_parser(
        "diagnose-internships",
        help="classifica as vagas do SQLite e mostra um diagnóstico",
    )
    diagnose.add_argument("--database", type=Path, default=Path("data/jobs.sqlite3"))
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.command == "collect":
        try:
            config = load_config(config_dir=args.config_dir, database_path=args.database)
            summary = collect_adzuna(config)
        except (AdzunaError, FileNotFoundError, ValueError, OSError, sqlite3.Error) as exc:
            print(f"Erro na coleta: {exc}", file=sys.stderr)
            return 1

        print(
            "Coleta concluída: "
            f"{summary.received} vagas recebidas, "
            f"{summary.inserted} novas e {summary.updated} atualizadas."
        )
        print(f"Banco de dados: {config.database_path}")
        return 0

    if args.command == "inspect-descriptions":
        if args.limit < 1:
            print("Erro na inspeção: --limit deve ser pelo menos 1.", file=sys.stderr)
            return 2
        try:
            with JobRepository(args.database) as repository:
                jobs = repository.list_for_inspection(args.limit)
        except (OSError, sqlite3.Error, ValueError) as exc:
            print(f"Erro na inspeção: {exc}", file=sys.stderr)
            return 1

        if not jobs:
            print("Nenhuma vaga encontrada no banco de dados.")
            return 0

        for index, job in enumerate(jobs, start=1):
            print(f"--- Vaga {index} ---")
            for field in ("title", "company", "location", "contract_type", "category"):
                print(f"{field}: {job[field] or '(não informado)'}")
            print("description:")
            print(job["description"] or "(não informado)")
            print(f"url: {job['url'] or '(não informado)'}")
            print()
        return 0

    if args.command == "diagnose-internships":
        try:
            report = diagnose_stored_jobs(args.database)
        except (OSError, sqlite3.Error, ValueError) as exc:
            print(f"Erro no diagnóstico: {exc}", file=sys.stderr)
            return 1

        print(f"Total de vagas analisadas: {report.total}")
        for classification in InternshipClassification:
            count = report.counts[classification]
            percentage = report.percentages[classification]
            print(f"{classification.value}: {count} ({percentage:.1f}%)")

        _print_classified_jobs("ESTAGIO", report.confirmed)
        _print_classified_jobs("INCERTO", report.uncertain)
        return 0

    return 2


def _print_classified_jobs(label: str, items: list[ClassifiedJob]) -> None:
    print(f"\nVagas {label}:")
    if not items:
        print("(nenhuma)")
        return
    records = []
    for index, item in enumerate(items, start=1):
        title = " ".join(item.job.title.split())
        company = " ".join((item.job.company or "(não informada)").split())
        explanation = " ".join(item.result.explanation.split())
        records.append(
            "\n".join(
                (
                    f"Registro {index}:",
                    f"  Título: {title}",
                    f"  Empresa: {company}",
                    f"  Classificação: {item.result.classification.value}",
                    f"  Explicação: {explanation}",
                )
            )
        )
    print()
    print("\n\n".join(records))
