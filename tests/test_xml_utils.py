"""Testes para xml_utils.py — Issues #3 (XXE), #11 (timeout), #27 (chamar_sefaz)."""
import pytest
from pynfe.utils import etree
from unittest.mock import patch, MagicMock, call

from nfe_sync.xml_utils import safe_fromstring, safe_parse, criar_comunicacao, chamar_sefaz, _com_retry


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
    """Issues #11/#19: timeout injetado via monkey-patch em _post."""

    def test_criar_comunicacao_usa_uf_empresa(self, empresa_sul):
        """criar_comunicacao usa a UF da empresa quando nao fornecida."""
        from unittest.mock import patch, MagicMock
        mock_con = MagicMock()
        with patch("nfe_sync.xml_utils.ComunicacaoSefaz", return_value=mock_con) as mock_cls:
            criar_comunicacao(empresa_sul)
            mock_cls.assert_called_once_with(
                empresa_sul.uf,
                empresa_sul.certificado.path,
                empresa_sul.certificado.senha,
                empresa_sul.homologacao,
            )

    def test_criar_comunicacao_sobrescreve_uf(self, empresa_sul):
        """criar_comunicacao usa uf fornecida, ignorando empresa.uf."""
        from unittest.mock import patch, MagicMock
        mock_con = MagicMock()
        with patch("nfe_sync.xml_utils.ComunicacaoSefaz", return_value=mock_con) as mock_cls:
            criar_comunicacao(empresa_sul, uf="sp")
            mock_cls.assert_called_once_with(
                "sp",
                empresa_sul.certificado.path,
                empresa_sul.certificado.senha,
                empresa_sul.homologacao,
            )

    def test_timeout_injetado_em_post(self, empresa_sul):
        """Issue #19: _post deve receber timeout=30 quando nao fornecido."""
        from unittest.mock import patch, MagicMock
        mock_con = MagicMock()
        original_post_chamadas = []

        def fake_original_post(url, xml, timeout=None):
            original_post_chamadas.append(timeout)
            return MagicMock()

        mock_con._post = fake_original_post

        with patch("nfe_sync.xml_utils.ComunicacaoSefaz", return_value=mock_con):
            con = criar_comunicacao(empresa_sul)

        # Chamar _post sem timeout — deve usar o default de 30s
        con._post("http://sefaz", "<xml/>")
        assert original_post_chamadas == [30]

    def test_timeout_explicito_tem_prioridade(self, empresa_sul):
        """Timeout explícito passado pelo chamador deve ser respeitado."""
        from unittest.mock import patch, MagicMock
        mock_con = MagicMock()
        chamadas = []

        def fake_original_post(url, xml, timeout=None):
            chamadas.append(timeout)
            return MagicMock()

        mock_con._post = fake_original_post

        with patch("nfe_sync.xml_utils.ComunicacaoSefaz", return_value=mock_con):
            con = criar_comunicacao(empresa_sul)

        con._post("http://sefaz", "<xml/>", timeout=60)
        assert chamadas == [60]


class TestChamarSefaz:
    """Issue #27: chamar_sefaz centraliza retry + parsing de resposta."""

    XML_RESP = b'<retConsSitNFe xmlns="http://www.portalfiscal.inf.br/nfe"><cStat>100</cStat></retConsSitNFe>'

    def test_chama_metodo_correto(self, empresa_sul):
        mock_resp = MagicMock()
        mock_resp.content = self.XML_RESP
        with patch("nfe_sync.xml_utils.ComunicacaoSefaz") as mock_cls:
            mock_cls.return_value.consulta_nota.return_value = mock_resp
            xml_el, xml_str = chamar_sefaz(empresa_sul, "consulta_nota", modelo="nfe", chave="x")

        mock_cls.return_value.consulta_nota.assert_called_once_with(modelo="nfe", chave="x")

    def test_retorna_elemento_e_string(self, empresa_sul):
        mock_resp = MagicMock()
        mock_resp.content = self.XML_RESP
        with patch("nfe_sync.xml_utils.ComunicacaoSefaz") as mock_cls:
            mock_cls.return_value.consulta_nota.return_value = mock_resp
            xml_el, xml_str = chamar_sefaz(empresa_sul, "consulta_nota", modelo="nfe", chave="x")

        assert "retConsSitNFe" in xml_el.tag
        assert "<?xml" in xml_str
        assert "retConsSitNFe" in xml_str

    def test_usa_uf_fornecida(self, empresa_sul):
        mock_resp = MagicMock()
        mock_resp.content = self.XML_RESP
        with patch("nfe_sync.xml_utils.ComunicacaoSefaz") as mock_cls:
            mock_cls.return_value.consulta_nota.return_value = mock_resp
            chamar_sefaz(empresa_sul, "consulta_nota", uf="rj", modelo="nfe", chave="x")

        mock_cls.assert_called_once_with(
            "rj",
            empresa_sul.certificado.path,
            empresa_sul.certificado.senha,
            empresa_sul.homologacao,
        )

    def test_usa_uf_empresa_quando_nao_fornecida(self, empresa_sul):
        mock_resp = MagicMock()
        mock_resp.content = self.XML_RESP
        with patch("nfe_sync.xml_utils.ComunicacaoSefaz") as mock_cls:
            mock_cls.return_value.consulta_nota.return_value = mock_resp
            chamar_sefaz(empresa_sul, "consulta_nota", modelo="nfe", chave="x")

        mock_cls.assert_called_once_with(
            empresa_sul.uf,
            empresa_sul.certificado.path,
            empresa_sul.certificado.senha,
            empresa_sul.homologacao,
        )

    def test_aplica_retry_em_falha(self, empresa_sul):
        mock_resp = MagicMock()
        mock_resp.content = self.XML_RESP
        with patch("nfe_sync.xml_utils.ComunicacaoSefaz") as mock_cls, \
             patch("nfe_sync.xml_utils.time.sleep"):
            mock_cls.return_value.consulta_nota.side_effect = [
                RuntimeError("timeout"), mock_resp
            ]
            xml_el, xml_str = chamar_sefaz(empresa_sul, "consulta_nota", modelo="nfe", chave="x")

        assert mock_cls.return_value.consulta_nota.call_count == 2

    def test_trata_resposta_sem_content(self, empresa_sul):
        """Resposta que é bytes diretamente (sem .content) também deve funcionar."""
        with patch("nfe_sync.xml_utils.ComunicacaoSefaz") as mock_cls:
            mock_cls.return_value.consulta_nota.return_value = self.XML_RESP
            xml_el, xml_str = chamar_sefaz(empresa_sul, "consulta_nota", modelo="nfe", chave="x")

        assert "retConsSitNFe" in xml_el.tag
