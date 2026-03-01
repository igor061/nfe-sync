"""Testes para cli.py — Issue #20: --producao/--homologacao em qualquer posição."""
import argparse
import pytest
from unittest.mock import patch, MagicMock


def _mock_empresas_hom():
    """Retorna empresa com homologacao=True (para testar override com --producao)."""
    from nfe_sync.models import EmpresaConfig, Certificado, Emitente
    return {
        "SUL": EmpresaConfig(
            nome="SUL",
            certificado=Certificado(path="/tmp/cert.pfx", senha="123456"),
            emitente=Emitente(cnpj="99999999000191"),
            uf="sp",
            homologacao=True,
        )
    }


def _mock_empresas_prod():
    """Retorna empresa com homologacao=False (para testar override com --homologacao)."""
    from nfe_sync.models import EmpresaConfig, Certificado, Emitente
    return {
        "SUL": EmpresaConfig(
            nome="SUL",
            certificado=Certificado(path="/tmp/cert.pfx", senha="123456"),
            emitente=Emitente(cnpj="99999999000191"),
            uf="sp",
            homologacao=False,
        )
    }


_NSU_OK = {
    "sucesso": True, "status": "137", "motivo": "OK",
    "ultimo_nsu": 0, "max_nsu": 0, "documentos": [], "xmls_resposta": [], "estado": {},
}


class TestFlagsAmbientePos:
    """Issue #20: --producao/--homologacao deve ser aceito antes OU depois do subcomando."""

    def test_homologacao_antes_do_subcomando(self):
        """nfe-sync --homologacao consultar-nsu SUL → empresa.homologacao = True."""
        mock_nsu = MagicMock(return_value=_NSU_OK)
        with patch("nfe_sync.commands.carregar_empresas", return_value=_mock_empresas_prod()), \
             patch("nfe_sync.commands.consulta.consultar_nsu", mock_nsu), \
             patch("nfe_sync.commands._salvar_log_xml", return_value="x"), \
             patch("nfe_sync.commands.consulta._listar_resumos_pendentes", return_value=[]):
            from nfe_sync.cli import cli
            cli(["--homologacao", "consultar-nsu", "SUL"])

        empresa_chamada = mock_nsu.call_args[0][0]
        assert empresa_chamada.homologacao is True

    def test_homologacao_apos_subcomando(self):
        """nfe-sync consultar-nsu SUL --homologacao → empresa.homologacao = True."""
        mock_nsu = MagicMock(return_value=_NSU_OK)
        with patch("nfe_sync.commands.carregar_empresas", return_value=_mock_empresas_prod()), \
             patch("nfe_sync.commands.consulta.consultar_nsu", mock_nsu), \
             patch("nfe_sync.commands._salvar_log_xml", return_value="x"), \
             patch("nfe_sync.commands.consulta._listar_resumos_pendentes", return_value=[]):
            from nfe_sync.cli import cli
            cli(["consultar-nsu", "SUL", "--homologacao"])

        empresa_chamada = mock_nsu.call_args[0][0]
        assert empresa_chamada.homologacao is True

    def test_producao_apos_subcomando(self):
        """nfe-sync consultar-nsu SUL --producao → empresa.homologacao = False."""
        mock_nsu = MagicMock(return_value=_NSU_OK)
        with patch("nfe_sync.commands.carregar_empresas", return_value=_mock_empresas_hom()), \
             patch("nfe_sync.commands.consulta.consultar_nsu", mock_nsu), \
             patch("nfe_sync.commands._salvar_log_xml", return_value="x"), \
             patch("nfe_sync.commands.consulta._listar_resumos_pendentes", return_value=[]):
            from nfe_sync.cli import cli
            cli(["consultar-nsu", "SUL", "--producao"])

        empresa_chamada = mock_nsu.call_args[0][0]
        assert empresa_chamada.homologacao is False

    def test_sem_flag_usa_config(self):
        """nfe-sync consultar-nsu SUL (sem flag) → usa valor do config (homologacao=True)."""
        mock_nsu = MagicMock(return_value=_NSU_OK)
        with patch("nfe_sync.commands.carregar_empresas", return_value=_mock_empresas_hom()), \
             patch("nfe_sync.commands.consulta.consultar_nsu", mock_nsu), \
             patch("nfe_sync.commands._salvar_log_xml", return_value="x"), \
             patch("nfe_sync.commands.consulta._listar_resumos_pendentes", return_value=[]):
            from nfe_sync.cli import cli
            cli(["consultar-nsu", "SUL"])

        empresa_chamada = mock_nsu.call_args[0][0]
        assert empresa_chamada.homologacao is True
