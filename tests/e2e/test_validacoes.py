"""Testes de validação de entrada — não chamam a SEFAZ."""
import pytest
from .conftest import run_nfe


class TestEmitirValidacao:
    def test_empresa_inexistente_retorna_erro(self):
        result = run_nfe("emitir", "EMPRESA_QUE_NAO_EXISTE_XYZ", "--serie", "1")
        assert result.returncode == 1
        assert "EMPRESA_QUE_NAO_EXISTE_XYZ" in result.stdout or \
               "EMPRESA_QUE_NAO_EXISTE_XYZ" in result.stderr

    def test_sem_empresa_retorna_erro_argparse(self):
        result = run_nfe("emitir")
        assert result.returncode == 2

    def test_sem_serie_retorna_erro_argparse(self):
        result = run_nfe("emitir", "QUALQUER_EMPRESA")
        assert result.returncode == 2

    def test_destinatario_inexistente_retorna_erro(self, emitente):
        result = run_nfe(
            "emitir", emitente,
            "--serie", "1",
            "--destinatario", "DESTINATARIO_QUE_NAO_EXISTE_XYZ",
        )
        assert result.returncode == 1
        assert "DESTINATARIO_QUE_NAO_EXISTE_XYZ" in result.stdout or \
               "DESTINATARIO_QUE_NAO_EXISTE_XYZ" in result.stderr


class TestConsultarValidacao:
    def test_empresa_inexistente_retorna_erro(self):
        chave = "52991299999999999999550010000000011000000010"
        result = run_nfe("consultar", "EMPRESA_QUE_NAO_EXISTE_XYZ", chave)
        assert result.returncode == 1

    def test_sem_argumentos_retorna_erro_argparse(self):
        result = run_nfe("consultar")
        assert result.returncode == 2

    def test_sem_chave_retorna_erro_argparse(self):
        result = run_nfe("consultar", "QUALQUER_EMPRESA")
        assert result.returncode == 2


class TestInutilizarValidacao:
    def test_empresa_inexistente_retorna_erro(self):
        result = run_nfe(
            "inutilizar", "EMPRESA_QUE_NAO_EXISTE_XYZ",
            "--serie", "1", "--inicio", "5", "--fim", "8",
            "--justificativa", "teste",
        )
        assert result.returncode == 1

    def test_sem_argumentos_retorna_erro_argparse(self):
        result = run_nfe("inutilizar")
        assert result.returncode == 2


class TestManifestarValidacao:
    def test_empresa_inexistente_retorna_erro(self):
        chave = "52991299999999999999550010000000011000000010"
        result = run_nfe("manifestar", "EMPRESA_QUE_NAO_EXISTE_XYZ", "ciencia", chave)
        assert result.returncode == 1

    def test_sem_argumentos_retorna_erro_argparse(self):
        result = run_nfe("manifestar")
        assert result.returncode == 2
