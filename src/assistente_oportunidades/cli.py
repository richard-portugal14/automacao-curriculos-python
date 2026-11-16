"""Interface de terminal para as operações disponíveis no MVP."""

from __future__ import annotations

import argparse
import sqlite3
import sys
from collections.abc import Sequence
from pathlib import Path

from assistente_oportunidades.config import load_config
from assistente_oportunidades.services.collect import collect_adzuna
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

    return 2
