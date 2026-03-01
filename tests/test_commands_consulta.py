"""Testes para commands/consulta.py — Issues #8, #9, #10."""
import logging
import os
import pytest
from unittest.mock import patch, MagicMock


class TestProcessarESalvarDocs:
    """Issue #8: helper _processar_e_salvar_docs elimina duplicação."""

    def test_imprime_e_salva_prochfe(self, tmp_path, capsys):
        from nfe_sync.commands.consulta import _processar_e_salvar_docs

        docs = [{
            "nsu": "001",
            "chave": "12345678901234567890123456789012345678901234",
            "schema": "procNFe_v4.00.xsd",
            "nome": "12345678901234567890123456789012345678901234.xml",
            "xml": "<procNFe/>",
        }]

        with patch("nfe_sync.commands.consulta._salvar_xml") as mock_salvar:
            completos = _processar_e_salvar_docs("99999999000191", docs)

        assert completos == ["12345678901234567890123456789012345678901234"]
        captured = capsys.readouterr()
        assert "XML completo" in captured.out

    def test_imprime_erro(self, capsys):
        from nfe_sync.commands.consulta import _processar_e_salvar_docs

        docs = [{"nsu": "001", "schema": "resNFe_v1.01.xsd", "erro": "falha ao descompactar"}]
        with patch("nfe_sync.commands.consulta._salvar_xml"):
            completos = _processar_e_salvar_docs("99999999000191", docs)

        assert completos == []
        captured = capsys.readouterr()
        assert "ERRO" in captured.out

    def test_resumo_nao_adicionado_a_completos(self, capsys):
        from nfe_sync.commands.consulta import _processar_e_salvar_docs

        docs = [{
            "nsu": "001",
            "chave": "12345678901234567890123456789012345678901234",
            "schema": "resNFe_v1.01.xsd",
            "nome": "12345678901234567890123456789012345678901234.xml",
            "xml": "<resNFe/>",
        }]
        with patch("nfe_sync.commands.consulta._salvar_xml"):
            completos = _processar_e_salvar_docs("99999999000191", docs)

        assert completos == []
        captured = capsys.readouterr()
        assert "resumo" in captured.out


class TestListarResumosPendentes:
    """Issue #9: deve detectar resNFe por root tag, sem filtrar por len(nome)."""

    def test_detecta_arquivo_com_nome_curto(self, tmp_path):
        """Arquivos com nome != 44 chars também devem ser detectados se root tag = resNFe."""
        from nfe_sync.commands import _listar_resumos_pendentes
        import nfe_sync.commands as cmds_mod

        cnpj = "99999999000191"

        with patch("os.path.isdir", return_value=True), \
             patch("os.listdir", return_value=["resumo-curto.xml", "outro.xml"]), \
             patch.object(cmds_mod, "safe_parse") as mock_parse:

            def fake_parse(path):
                mock_tree = MagicMock()
                if "resumo-curto" in path:
                    mock_tree.getroot.return_value.tag = "{http://www.portalfiscal.inf.br/nfe}resNFe"
                else:
                    mock_tree.getroot.return_value.tag = "outro"
                return mock_tree

            mock_parse.side_effect = fake_parse
            resultado = _listar_resumos_pendentes(cnpj)

        assert "resumo-curto" in resultado

    def test_ignora_arquivos_nao_xml(self, tmp_path):
        from nfe_sync.commands import _listar_resumos_pendentes

        cnpj = "99999999000191"
        with patch("os.path.isdir", return_value=True), \
             patch("os.listdir", return_value=["arquivo.txt", "arquivo.pdf"]):
            resultado = _listar_resumos_pendentes(cnpj)

        assert resultado == []

    def test_loga_warning_para_xml_invalido(self, tmp_path, caplog):
        """Issue #10: XML inválido deve gerar warning, não engolir silenciosamente."""
        from nfe_sync.commands import _listar_resumos_pendentes
        import nfe_sync.commands as cmds_mod

        cnpj = "99999999000191"
        with patch("os.path.isdir", return_value=True), \
             patch("os.listdir", return_value=["invalido.xml"]), \
             patch.object(cmds_mod, "safe_parse", side_effect=Exception("xml quebrado")):
            with caplog.at_level(logging.WARNING):
                resultado = _listar_resumos_pendentes(cnpj)

        assert resultado == []
        assert any("invalido.xml" in r.message for r in caplog.records)


class TestTratarArquivoCancelado:
    """Issue #10: logging em _tratar_arquivo_cancelado."""

    def test_loga_warning_ao_falhar_leitura(self, tmp_path, caplog):
        import nfe_sync.commands.consulta as consulta_cmds
        from nfe_sync.commands.consulta import _tratar_arquivo_cancelado

        cnpj = "99999999000191"
        chave = "12345678901234567890123456789012345678901234"

        with patch("os.path.exists", return_value=True), \
             patch("os.rename"), \
             patch.object(consulta_cmds, "safe_parse", side_effect=Exception("parse error")):
            with caplog.at_level(logging.WARNING):
                # Deve continuar sem levantar exceção
                _tratar_arquivo_cancelado(cnpj, chave)

        assert any("parse error" in r.message or chave in r.message for r in caplog.records)
