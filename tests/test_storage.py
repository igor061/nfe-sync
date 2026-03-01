"""Testes para storage.py — Issue #26."""
import logging
import pytest
from unittest.mock import patch, MagicMock

from nfe_sync.storage import DocumentoStorage


class TestDocumentoStorage:

    def test_salvar_cria_arquivo(self, tmp_path):
        storage = DocumentoStorage()
        storage.BASE = str(tmp_path)
        caminho = storage.salvar("99999999000191", "nota.xml", "<nfe/>")
        assert caminho.endswith("nota.xml")
        with open(caminho) as f:
            assert f.read() == "<nfe/>"

    def test_existe_verdadeiro(self, tmp_path):
        storage = DocumentoStorage()
        storage.BASE = str(tmp_path)
        storage.salvar("99999999000191", "nota.xml", "<nfe/>")
        assert storage.existe("99999999000191", "nota.xml") is True

    def test_existe_falso(self, tmp_path):
        storage = DocumentoStorage()
        storage.BASE = str(tmp_path)
        assert storage.existe("99999999000191", "inexistente.xml") is False

    def test_root_tag_retorna_tag_local(self, tmp_path):
        storage = DocumentoStorage()
        storage.BASE = str(tmp_path)
        storage.salvar("99999999000191", "nota.xml",
                       '<?xml version="1.0"?><resNFe xmlns="http://www.portalfiscal.inf.br/nfe"/>')
        tag = storage.root_tag("99999999000191", "nota.xml")
        assert tag == "resNFe"

    def test_root_tag_retorna_none_e_loga_warning_em_falha(self, tmp_path, caplog):
        storage = DocumentoStorage()
        storage.BASE = str(tmp_path)
        import nfe_sync.storage as storage_mod
        with patch.object(storage_mod, "safe_parse", side_effect=Exception("parse error")):
            with caplog.at_level(logging.WARNING):
                tag = storage.root_tag("99999999000191", "invalido.xml")
        assert tag is None
        assert any("parse error" in r.message for r in caplog.records)

    def test_listar_resumos_pendentes_detecta_resnfe(self, tmp_path):
        storage = DocumentoStorage()
        storage.BASE = str(tmp_path)
        cnpj = "99999999000191"
        import nfe_sync.storage as storage_mod

        with patch("os.path.isdir", return_value=True), \
             patch("os.listdir", return_value=["resumo.xml", "proc.xml"]), \
             patch.object(storage_mod, "safe_parse") as mock_parse:

            def fake_parse(path):
                tree = MagicMock()
                if path.endswith("resumo.xml"):
                    tree.getroot.return_value.tag = "{http://www.portalfiscal.inf.br/nfe}resNFe"
                else:
                    tree.getroot.return_value.tag = "procNFe"
                return tree

            mock_parse.side_effect = fake_parse
            resultado = storage.listar_resumos_pendentes(cnpj)

        assert "resumo" in resultado
        assert "proc" not in resultado

    def test_listar_resumos_pendentes_pasta_inexistente(self, tmp_path):
        storage = DocumentoStorage()
        storage.BASE = str(tmp_path)
        resultado = storage.listar_resumos_pendentes("00000000000000")
        assert resultado == []

    def test_listar_resumos_ignora_nao_xml(self, tmp_path):
        storage = DocumentoStorage()
        storage.BASE = str(tmp_path)
        cnpj = "99999999000191"
        with patch("os.path.isdir", return_value=True), \
             patch("os.listdir", return_value=["arquivo.txt", "foto.pdf"]):
            resultado = storage.listar_resumos_pendentes(cnpj)
        assert resultado == []

    def test_renomear(self, tmp_path):
        storage = DocumentoStorage()
        storage.BASE = str(tmp_path)
        storage.salvar("99999999000191", "orig.xml", "<nfe/>")
        destino = storage.renomear("99999999000191", "orig.xml", "dest.xml")
        assert destino.endswith("dest.xml")
        assert storage.existe("99999999000191", "dest.xml")
        assert not storage.existe("99999999000191", "orig.xml")

    def test_remover(self, tmp_path):
        storage = DocumentoStorage()
        storage.BASE = str(tmp_path)
        storage.salvar("99999999000191", "nota.xml", "<nfe/>")
        storage.remover("99999999000191", "nota.xml")
        assert not storage.existe("99999999000191", "nota.xml")

    def test_remover_inexistente_nao_levanta(self, tmp_path):
        storage = DocumentoStorage()
        storage.BASE = str(tmp_path)
        # Não deve levantar exceção
        storage.remover("99999999000191", "inexistente.xml")
