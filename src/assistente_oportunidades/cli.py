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
from assistente_oportunidades.services.area_classifier import AreaCategory
from assistente_oportunidades.services.area_diagnostic import (
    AreaClassifiedJob,
    diagnose_stored_areas,
)
from assistente_oportunidades.services.internship_classifier import InternshipClassification
from assistente_oportunidades.services.internship_diagnostic import (
    ClassifiedJob,
    diagnose_stored_jobs,
)
from assistente_oportunidades.services.profile_diagnostic import (
    ProfileDiagnosedJob,
    diagnose_stored_profile,
)
from assistente_oportunidades.services.profile_matcher import EducationCompatibility
from assistente_oportunidades.services.profile_matcher import load_candidate_profile
from assistente_oportunidades.services.pipeline import run_pipeline
from assistente_oportunidades.reports.console import render_console_report
from assistente_oportunidades.services.score_diagnostic import (
    SCORE_BANDS,
    ScoreDiagnosedJob,
    diagnose_stored_scores,
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

    run = commands.add_parser("run", help="executa o pipeline completo de oportunidades")
    run.add_argument("--config-dir", type=Path, default=Path("config"))
    run.add_argument("--database", type=Path, default=Path("data/jobs.sqlite3"))
    run.add_argument("--top-n", type=int, default=10, help="quantidade de oportunidades exibidas")

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

    diagnose_areas = commands.add_parser(
        "diagnose-areas",
        help="classifica a área das vagas confirmadas como estágio no SQLite",
    )
    diagnose_areas.add_argument("--database", type=Path, default=Path("data/jobs.sqlite3"))

    diagnose_profile = commands.add_parser(
        "diagnose-profile",
        help="compara vagas de estágio do SQLite com o perfil configurado",
    )
    diagnose_profile.add_argument("--database", type=Path, default=Path("data/jobs.sqlite3"))

    diagnose_score = commands.add_parser(
        "diagnose-score",
        help="calcula e exibe o score das vagas de estágio existentes no SQLite",
    )
    diagnose_score.add_argument("--database", type=Path, default=Path("data/jobs.sqlite3"))
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

    if args.command == "run":
        if args.top_n < 0:
            print("Erro no relatório: --top-n não pode ser negativo.", file=sys.stderr)
            return 2
        try:
            config = load_config(config_dir=args.config_dir, database_path=args.database)
            profile = load_candidate_profile(
                args.config_dir / "profile.toml",
                args.config_dir / "preferences.toml",
            )
            result = run_pipeline(config, profile)
        except (AdzunaError, FileNotFoundError, ValueError, OSError, sqlite3.Error) as exc:
            print(f"Erro na execução do pipeline: {exc}", file=sys.stderr)
            return 1

        print(render_console_report(result, top_n=args.top_n))
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

    if args.command == "diagnose-areas":
        try:
            report = diagnose_stored_areas(args.database)
        except (OSError, sqlite3.Error, ValueError) as exc:
            print(f"Erro no diagnóstico de áreas: {exc}", file=sys.stderr)
            return 1

        print(f"Total de vagas analisadas: {report.total}")
        for category in AreaCategory:
            count = report.counts[category]
            percentage = report.percentages[category]
            print(f"{category.value}: {count} ({percentage:.1f}%)")
        _print_area_classified_jobs(report.classified_jobs)
        return 0

    if args.command == "diagnose-profile":
        try:
            report = diagnose_stored_profile(args.database)
        except (OSError, sqlite3.Error, ValueError) as exc:
            print(f"Erro no diagnóstico de compatibilidade: {exc}", file=sys.stderr)
            return 1

        print(f"Total de vagas analisadas: {report.total}")
        print(f"Com habilidades correspondentes: {report.with_skill_matches}")
        print(f"Sem habilidades correspondentes: {report.without_skill_matches}")
        for status in EducationCompatibility:
            print(f"Formação {status.value}: {report.education_counts[status]}")
        print("\nVagas por área:")
        for area in AreaCategory:
            print(f"{area.value}: {report.area_counts[area]}")
        _print_profile_diagnosed_jobs(report.results)
        return 0

    if args.command == "diagnose-score":
        try:
            report = diagnose_stored_scores(args.database)
        except (OSError, sqlite3.Error, ValueError) as exc:
            print(f"Erro no diagnóstico do score: {exc}", file=sys.stderr)
            return 1

        print(f"Total de vagas analisadas: {report.total}")
        print(f"Score médio: {_format_score(report.average)}")
        print(f"Score máximo: {_format_score(report.maximum)}")
        print(f"Score mínimo: {_format_score(report.minimum)}")
        print("\nDistribuição por faixa:")
        for band in SCORE_BANDS:
            print(f"{band}: {report.score_band_counts[band]}")
        print("\nVagas por área:")
        for area in AreaCategory:
            print(f"{area.value}: {report.area_counts[area]}")
        _print_score_diagnosed_jobs(report.results)
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


def _print_area_classified_jobs(items: list[AreaClassifiedJob]) -> None:
    print("\nVagas por área:")
    if not items:
        print("(nenhuma vaga classificada como ESTAGIO)")
        return

    records = []
    for index, item in enumerate(items, start=1):
        title = " ".join(item.job.title.split())
        company = " ".join((item.job.company or "(não informada)").split())
        evidence = ", ".join(item.result.evidence) or "(nenhuma)"
        explanation = " ".join(item.result.explanation.split())
        records.append(
            "\n".join(
                (
                    f"Registro {index}:",
                    f"  Título: {title}",
                    f"  Empresa: {company}",
                    f"  Área: {item.result.category.value}",
                    f"  Evidências: {evidence}",
                    f"  Explicação: {explanation}",
                )
            )
        )
    print()
    print("\n\n".join(records))


def _print_profile_diagnosed_jobs(items: list[ProfileDiagnosedJob]) -> None:
    print("\nDiagnóstico por vaga:")
    if not items:
        print("(nenhuma vaga classificada como ESTAGIO)")
        return

    education_labels = {
        EducationCompatibility.COMPATIVEL: "Compatível",
        EducationCompatibility.INCOMPATIVEL: "Incompatível",
        EducationCompatibility.NAO_INFORMADO: "Não informado",
    }
    records = []
    for index, item in enumerate(items, start=1):
        title = " ".join(item.job.title.split())
        company = " ".join((item.job.company or "(não informada)").split())
        matched = ", ".join(item.match.matched_profile_skills) or "nenhuma"
        missing = ", ".join(item.match.requirements_not_in_profile) or "nenhum"
        education = education_labels[item.match.education.compatibility]
        explanation = " ".join(item.match.explanation)
        records.append(
            "\n".join(
                (
                    f"Registro {index}:",
                    f"  Título: {title}",
                    f"  Empresa: {company}",
                    f"  Área: {item.match.area.value}",
                    f"  Habilidades correspondentes: {matched}",
                    f"  Requisitos não encontrados: {missing}",
                    f"  Formação: {education}",
                    f"  Explicação: {explanation}",
                )
            )
        )
    print()
    print("\n\n".join(records))


def _print_score_diagnosed_jobs(items: list[ScoreDiagnosedJob]) -> None:
    print("\nDiagnóstico detalhado por vaga:")
    if not items:
        print("(nenhuma vaga classificada como ESTAGIO)")
        return

    education_labels = {
        EducationCompatibility.COMPATIVEL: "Compatível",
        EducationCompatibility.INCOMPATIVEL: "Incompatível",
        EducationCompatibility.NAO_INFORMADO: "Não informado",
    }
    records = []
    for index, item in enumerate(items, start=1):
        score = item.score
        matched = ", ".join(item.match.matched_profile_skills) or "nenhuma"
        missing = ", ".join(item.match.requirements_not_in_profile) or "nenhum"
        explanations = " ".join(score.explicacao)
        records.append(
            "\n".join(
                (
                    f"Registro {index}:",
                    f"  Título: {' '.join(item.job.title.split())}",
                    f"  Empresa: {' '.join((item.job.company or '(não informada)').split())}",
                    f"  Área: {item.area.category.value}",
                    f"  Habilidades correspondentes: {matched}",
                    f"  Requisitos não encontrados: {missing}",
                    f"  Formação: {education_labels[item.match.education.compatibility]}",
                    f"  Score área: {_format_score(score.score_area)}",
                    f"  Score habilidades: {_format_score(score.score_habilidades)}",
                    f"  Score formação: {_format_score(score.score_formacao)}",
                    f"  Score localização: {_format_score(score.score_localizacao)}",
                    f"  SCORE TOTAL: {_format_score(score.score_total)}",
                    f"  Explicação do score: {explanations}",
                )
            )
        )
    print()
    print("\n\n".join(records))


def _format_score(value: float | None) -> str:
    if value is None:
        return "não disponível"
    return f"{value:.2f}".replace(".", ",")
