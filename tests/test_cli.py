from pathlib import Path

from assistente_oportunidades import cli
from assistente_oportunidades.services.collect import CollectionSummary
from assistente_oportunidades.sources.adzuna import AdzunaError


def test_collect_command_prints_collection_summary(monkeypatch, capsys, tmp_path: Path):
    monkeypatch.setattr(cli, "load_config", lambda **kwargs: type("Config", (), {"database_path": kwargs["database_path"]})())
    monkeypatch.setattr(cli, "collect_adzuna", lambda config: CollectionSummary(3, 2, 1))

    result = cli.main(["collect", "--database", str(tmp_path / "jobs.sqlite3")])

    captured = capsys.readouterr()
    assert result == 0
    assert "3 vagas recebidas, 2 novas e 1 atualizadas" in captured.out
    assert "jobs.sqlite3" in captured.out
    assert captured.err == ""


def test_collect_command_reports_configuration_errors(monkeypatch, capsys):
    def fail_to_load_config(**kwargs):
        raise ValueError("Configure ADZUNA_APP_ID e ADZUNA_APP_KEY")

    monkeypatch.setattr(cli, "load_config", fail_to_load_config)

    result = cli.main(["collect"])

    captured = capsys.readouterr()
    assert result == 1
    assert "Configure ADZUNA_APP_ID e ADZUNA_APP_KEY" in captured.err
    assert captured.out == ""


def test_collect_command_stops_after_collection_error(monkeypatch, capsys):
    monkeypatch.setattr(cli, "load_config", lambda **kwargs: object())

    def fail_collection(config):
        raise AdzunaError("Falha da API")

    monkeypatch.setattr(cli, "collect_adzuna", fail_collection)

    result = cli.main(["collect"])

    captured = capsys.readouterr()
    assert result == 1
    assert captured.out == ""
    assert captured.err.strip() == "Erro na coleta: Falha da API"
