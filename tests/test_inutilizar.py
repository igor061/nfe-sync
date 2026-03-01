import pytest
from unittest.mock import patch, MagicMock
from nfe_sync.inutilizacao import inutilizar
from nfe_sync.exceptions import NfeValidationError
from nfe_sync.results import ResultadoInutilizacao


JUSTIFICATIVA_VALIDA = "Numero pulado por erro de sistema"


class TestInutilizarValidacao:
    def test_justificativa_curta(self, empresa_sul):
        with pytest.raises(NfeValidationError, match="15 caracteres"):
            inutilizar(empresa_sul, "1", 10, 10, "curta")

    def test_numero_inicial_maior_que_final(self, empresa_sul):
        with pytest.raises(NfeValidationError, match="menor ou igual"):
            inutilizar(empresa_sul, "1", 10, 5, JUSTIFICATIVA_VALIDA)


class TestInutilizarSefaz:
    def test_chama_sefaz_com_retry(self, empresa_sul):
        xml_bytes = (
            b'<?xml version="1.0"?>'
            b'<retInutNFe xmlns="http://www.portalfiscal.inf.br/nfe">'
            b'<infInut><cStat>102</cStat><xMotivo>Inutilizacao de numero homologado</xMotivo>'
            b'<nProt>135240000012345</nProt></infInut>'
            b'</retInutNFe>'
        )
        mock_resp = MagicMock()
        mock_resp.content = xml_bytes

        with patch("nfe_sync.inutilizacao.chamar_sefaz") as mock_chamar:
            from pynfe.utils import etree
            xml_el = etree.fromstring(xml_bytes)
            mock_chamar.return_value = (xml_el, xml_bytes.decode())
            resultado = inutilizar(empresa_sul, "1", 10, 10, JUSTIFICATIVA_VALIDA)

        mock_chamar.assert_called_once_with(
            empresa_sul, "inutilizacao",
            modelo="nfe", cnpj=empresa_sul.emitente.cnpj,
            numero_inicial=10, numero_final=10,
            justificativa=JUSTIFICATIVA_VALIDA, serie="1",
        )
        assert isinstance(resultado, ResultadoInutilizacao)
