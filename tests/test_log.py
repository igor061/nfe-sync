"""Testes para log.py — Issue #13 (log cleanup tolerante a erros)."""
import logging
import os
import time
from datetime import datetime, timedelta
from unittest.mock import patch

import pytest

import nfe_sync.log as log_module
from nfe_sync.log import _limpar_logs_antigos
from nfe_sync.xml_utils import agora_brt as _agora_brt


class TestAgora:
    def test_retorna_datetime_com_tzinfo_brt(self):
        """Issue #53: tzinfo deve ser BRT (-03:00), não None."""
        dt = _agora_brt()
        assert dt.tzinfo is not None
        assert dt.utcoffset() == timedelta(hours=-3)

    def test_aproximadamente_agora(self):
        from datetime import timezone
        dt = _agora_brt()
        agora_utc = datetime.now(timezone.utc)
        # BRT é UTC-3; diferença deve ser < 1 minuto
        diff = abs((agora_utc - dt).total_seconds())
        assert diff < 60


class TestLimparLogsAntigos:
    def test_remove_arquivo_antigo(self, tmp_path, monkeypatch):
        monkeypatch.setattr(log_module, "LOG_DIR", str(tmp_path))
        arquivo = tmp_path / "antigo.xml"
        arquivo.write_text("<x/>")
        # Forçar mtime antigo
        tempo_antigo = time.time() - 8 * 24 * 3600
        os.utime(str(arquivo), (tempo_antigo, tempo_antigo))

        _limpar_logs_antigos()
        assert not arquivo.exists()

    def test_mantem_arquivo_recente(self, tmp_path, monkeypatch):
        monkeypatch.setattr(log_module, "LOG_DIR", str(tmp_path))
        arquivo = tmp_path / "recente.xml"
        arquivo.write_text("<x/>")

        _limpar_logs_antigos()
        assert arquivo.exists()

    def test_tolerante_a_erro_de_remocao(self, tmp_path, monkeypatch, caplog):
        """Issue #13: erro ao remover arquivo individual não interrompe limpeza."""
        monkeypatch.setattr(log_module, "LOG_DIR", str(tmp_path))

        arq1 = tmp_path / "antigo1.xml"
        arq2 = tmp_path / "antigo2.xml"
        arq1.write_text("<x/>")
        arq2.write_text("<x/>")

        tempo_antigo = time.time() - 8 * 24 * 3600
        os.utime(str(arq1), (tempo_antigo, tempo_antigo))
        os.utime(str(arq2), (tempo_antigo, tempo_antigo))

        def remove_com_falha(caminho):
            if "antigo1" in caminho:
                raise OSError("permissao negada")
            os.unlink(caminho)

        with patch("os.remove", side_effect=remove_com_falha):
            with caplog.at_level(logging.WARNING):
                _limpar_logs_antigos()

        assert any("antigo1" in r.message for r in caplog.records)
