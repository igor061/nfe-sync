"""Testes para xml_utils.py — Issues #3 (XXE) e #11 (timeout)."""
import pytest
from pynfe.utils import etree

from nfe_sync.xml_utils import safe_fromstring, safe_parse, criar_comunicacao


class TestSafeFromstring:
    """Issue #3: parser seguro contra XXE."""

    def test_parse_xml_valido(self):
        xml = b"<root><filho>texto</filho></root>"
        el = safe_fromstring(xml)
        assert el.tag == "root"
        assert el.find("filho").text == "texto"

    def test_rejeita_entidade_externa(self, tmp_path):
        """Parser seguro não deve expandir entidades externas (XXE)."""
        arquivo_secreto = tmp_path / "secreto.txt"
        arquivo_secreto.write_text("SEGREDO")

        xml_xxe = (
            b'<?xml version="1.0"?>'
            b'<!DOCTYPE foo [<!ENTITY xxe SYSTEM "file:///etc/passwd">]>'
            b"<root>&xxe;</root>"
        )
        # Com resolve_entities=False, a entidade nao e expandida — sem erro, mas sem conteudo
        el = safe_fromstring(xml_xxe)
        assert el.tag == "root"
        # O texto nao deve conter conteudo do arquivo externo
        assert el.text is None or "root" not in (el.text or "")

    def test_parse_xml_com_namespace(self):
        xml = b'<root xmlns="http://example.com"><item>val</item></root>'
        el = safe_fromstring(xml)
        assert "root" in el.tag

    def test_safe_parse_arquivo(self, tmp_path):
        arquivo = tmp_path / "test.xml"
        arquivo.write_text("<root><a>1</a></root>")
        tree = safe_parse(str(arquivo))
        assert tree.getroot().tag == "root"


class TestCriarComunicacao:
    """Issue #11: ComunicacaoSefaz nao expoe timeout — limitacao conhecida."""

    def test_criar_comunicacao_usa_uf_empresa(self, empresa_sul):
        """criar_comunicacao usa a UF da empresa quando nao fornecida."""
        from unittest.mock import patch
        with patch("nfe_sync.xml_utils.ComunicacaoSefaz") as mock_cls:
            criar_comunicacao(empresa_sul)
            mock_cls.assert_called_once_with(
                empresa_sul.uf,
                empresa_sul.certificado.path,
                empresa_sul.certificado.senha,
                empresa_sul.homologacao,
            )

    def test_criar_comunicacao_sobrescreve_uf(self, empresa_sul):
        """criar_comunicacao usa uf fornecida, ignorando empresa.uf."""
        from unittest.mock import patch
        with patch("nfe_sync.xml_utils.ComunicacaoSefaz") as mock_cls:
            criar_comunicacao(empresa_sul, uf="sp")
            mock_cls.assert_called_once_with(
                "sp",
                empresa_sul.certificado.path,
                empresa_sul.certificado.senha,
                empresa_sul.homologacao,
            )
