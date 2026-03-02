import pytest
from unittest.mock import patch
from pynfe.utils import etree

from nfe_sync.cancelamento import cancelar
from nfe_sync.exceptions import NfeValidationError
from nfe_sync.results import ResultadoCancelamento


CHAVE_VALIDA = "52991299999999999999550010000000011000000010"
PROTOCOLO_VALIDO = "135240000012345"
JUSTIFICATIVA_VALIDA = "Erro de emissao no sistema"


class TestCancelarValidacao:
    def test_chave_invalida(self, empresa_sul):
        with pytest.raises(NfeValidationError, match="44 digitos"):
            cancelar(empresa_sul, "123", PROTOCOLO_VALIDO, JUSTIFICATIVA_VALIDA)

    def test_chave_nao_numerica(self, empresa_sul):
        chave_letras = "A" * 44
        with pytest.raises(NfeValidationError, match="44 digitos"):
            cancelar(empresa_sul, chave_letras, PROTOCOLO_VALIDO, JUSTIFICATIVA_VALIDA)

    def test_justificativa_curta(self, empresa_sul):
        with pytest.raises(NfeValidationError, match="15 chars"):
            cancelar(empresa_sul, CHAVE_VALIDA, PROTOCOLO_VALIDO, "curta")


def _patch_pynfe(chamar_sefaz_return):
    """Context manager que mocka os componentes pynfe para não precisar de certificado real."""
    return (
        patch("nfe_sync.cancelamento.SerializacaoXML"),
        patch("nfe_sync.cancelamento.AssinaturaA1"),
        patch("nfe_sync.cancelamento.chamar_sefaz", return_value=chamar_sefaz_return),
    )


class TestCancelarSefaz:
    def test_cancelar_sucesso(self, empresa_sul):
        xml_bytes = (
            b'<?xml version="1.0"?>'
            b'<retEnvEvento xmlns="http://www.portalfiscal.inf.br/nfe">'
            b'<retEvento><infEvento>'
            b'<cStat>135</cStat>'
            b'<xMotivo>Evento registrado e vinculado a NF-e</xMotivo>'
            b'<nProt>135240000012345</nProt>'
            b'</infEvento></retEvento>'
            b'</retEnvEvento>'
        )
        xml_el = etree.fromstring(xml_bytes)
        p_serial, p_assin, p_sefaz = _patch_pynfe((xml_el, xml_bytes.decode()))

        with p_serial, p_assin, p_sefaz:
            resultado = cancelar(empresa_sul, CHAVE_VALIDA, PROTOCOLO_VALIDO, JUSTIFICATIVA_VALIDA)

        assert isinstance(resultado, ResultadoCancelamento)
        assert resultado.sucesso is True
        assert resultado.protocolo == "135240000012345"

    def test_cancelar_falha(self, empresa_sul):
        xml_bytes = (
            b'<?xml version="1.0"?>'
            b'<retEnvEvento xmlns="http://www.portalfiscal.inf.br/nfe">'
            b'<retEvento><infEvento>'
            b'<cStat>589</cStat>'
            b'<xMotivo>Rejeicao: Duplicidade de evento</xMotivo>'
            b'</infEvento></retEvento>'
            b'</retEnvEvento>'
        )
        xml_el = etree.fromstring(xml_bytes)
        p_serial, p_assin, p_sefaz = _patch_pynfe((xml_el, xml_bytes.decode()))

        with p_serial, p_assin, p_sefaz:
            resultado = cancelar(empresa_sul, CHAVE_VALIDA, PROTOCOLO_VALIDO, JUSTIFICATIVA_VALIDA)

        assert isinstance(resultado, ResultadoCancelamento)
        assert resultado.sucesso is False
        assert resultado.protocolo is None

    def test_cancelar_sucesso_cstat_136(self, empresa_sul):
        """cStat=136 (cancelamento homologado) também é sucesso."""
        xml_bytes = (
            b'<?xml version="1.0"?>'
            b'<retEnvEvento xmlns="http://www.portalfiscal.inf.br/nfe">'
            b'<retEvento><infEvento>'
            b'<cStat>136</cStat>'
            b'<xMotivo>Evento registrado e vinculado a NF-e</xMotivo>'
            b'<nProt>135240000099999</nProt>'
            b'</infEvento></retEvento>'
            b'</retEnvEvento>'
        )
        xml_el = etree.fromstring(xml_bytes)
        p_serial, p_assin, p_sefaz = _patch_pynfe((xml_el, xml_bytes.decode()))

        with p_serial, p_assin, p_sefaz:
            resultado = cancelar(empresa_sul, CHAVE_VALIDA, PROTOCOLO_VALIDO, JUSTIFICATIVA_VALIDA)

        assert resultado.sucesso is True
