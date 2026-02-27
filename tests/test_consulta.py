from datetime import datetime, timedelta
from unittest.mock import patch, MagicMock
import pytest

from nfe_sync.consulta import verificar_cooldown, calcular_proximo_cooldown, consultar_nsu
from nfe_sync.state import carregar_estado


class TestVerificarCooldown:
    def test_sem_bloqueio(self):
        bloqueado, msg = verificar_cooldown(None)
        assert bloqueado is False
        assert msg == ""

    def test_string_vazia(self):
        bloqueado, msg = verificar_cooldown("")
        assert bloqueado is False
        assert msg == ""

    def test_expirado(self):
        passado = (datetime.now() - timedelta(hours=2)).isoformat(timespec="seconds")
        bloqueado, msg = verificar_cooldown(passado)
        assert bloqueado is False
        assert msg == ""

    def test_ativo(self):
        futuro = (datetime.now() + timedelta(hours=1)).isoformat(timespec="seconds")
        bloqueado, msg = verificar_cooldown(futuro)
        assert bloqueado is True
        assert "bloqueada ate" in msg

    def test_valor_invalido(self):
        bloqueado, msg = verificar_cooldown("lixo")
        assert bloqueado is False
        assert msg == ""


class TestCalcularProximoCooldown:
    def test_retorna_iso_futuro(self):
        resultado = calcular_proximo_cooldown(60)
        dt = datetime.fromisoformat(resultado)
        assert dt > datetime.now()


class TestConsultarNsu:
    XML_VAZIO = b"""<?xml version="1.0" encoding="utf-8"?>
    <retDistDFeInt xmlns="http://www.portalfiscal.inf.br/nfe">
        <tpAmb>2</tpAmb>
        <cStat>137</cStat>
        <xMotivo>Nenhum documento localizado</xMotivo>
        <ultNSU>000000000000000</ultNSU>
        <maxNSU>000000000000000</maxNSU>
    </retDistDFeInt>"""

    XML_COM_DOC = b"""<?xml version="1.0" encoding="utf-8"?>
    <retDistDFeInt xmlns="http://www.portalfiscal.inf.br/nfe">
        <tpAmb>2</tpAmb>
        <cStat>138</cStat>
        <xMotivo>Documento localizado</xMotivo>
        <ultNSU>000000000000042</ultNSU>
        <maxNSU>000000000000100</maxNSU>
        <loteDistDFeInt>
            <docZip NSU="000000000000042" schema="resNFe_v1.01.xsd">H4sIAAAAAAAAA6tWKkktLlGyUlAqS8wpTgUAhRxpOhUAAAA=</docZip>
        </loteDistDFeInt>
    </retDistDFeInt>"""

    def test_bloqueado_por_cooldown(self, empresa_sul, tmp_path):
        futuro = (datetime.now() + timedelta(hours=1)).isoformat(timespec="seconds")
        estado = {"cooldown": {empresa_sul.emitente.cnpj: futuro}}
        state_file = str(tmp_path / "state.json")

        resultado = consultar_nsu(empresa_sul, estado, state_file)
        assert resultado["sucesso"] is False
        assert "bloqueada" in resultado["motivo"]
        assert resultado["documentos"] == []

    @patch("nfe_sync.consulta.ComunicacaoSefaz")
    def test_nenhum_documento(self, mock_sefaz_cls, empresa_sul, tmp_path):
        mock_resp = MagicMock()
        mock_resp.content = self.XML_VAZIO
        mock_sefaz_cls.return_value.consulta_distribuicao.return_value = mock_resp

        state_file = str(tmp_path / "state.json")
        estado = {}

        resultado = consultar_nsu(empresa_sul, estado, state_file)
        assert resultado["sucesso"] is True
        assert resultado["status"] == "137"
        assert resultado["documentos"] == []

    @patch("nfe_sync.consulta.ComunicacaoSefaz")
    def test_documento_localizado(self, mock_sefaz_cls, empresa_sul, tmp_path):
        mock_resp = MagicMock()
        mock_resp.content = self.XML_COM_DOC
        mock_sefaz_cls.return_value.consulta_distribuicao.return_value = mock_resp

        state_file = str(tmp_path / "state.json")
        estado = {}

        resultado = consultar_nsu(empresa_sul, estado, state_file)
        assert resultado["sucesso"] is True
        assert resultado["status"] == "138"
        assert resultado["ultimo_nsu"] == 42
        assert resultado["max_nsu"] == 100
        assert len(resultado["documentos"]) == 1
        assert resultado["documentos"][0]["nsu"] == "000000000000042"

        # verifica que salvou estado
        estado_salvo = carregar_estado(state_file)
        assert estado_salvo["nsu"][empresa_sul.emitente.cnpj] == 42
        assert empresa_sul.emitente.cnpj in estado_salvo.get("cooldown", {})

    @patch("nfe_sync.consulta.ComunicacaoSefaz")
    def test_usa_ultimo_nsu_do_estado(self, mock_sefaz_cls, empresa_sul, tmp_path):
        mock_resp = MagicMock()
        mock_resp.content = self.XML_VAZIO
        mock_sefaz_cls.return_value.consulta_distribuicao.return_value = mock_resp

        state_file = str(tmp_path / "state.json")
        cnpj = empresa_sul.emitente.cnpj
        estado = {"nsu": {cnpj: 50}}

        consultar_nsu(empresa_sul, estado, state_file)
        mock_sefaz_cls.return_value.consulta_distribuicao.assert_called_once_with(
            cnpj=cnpj, nsu=50
        )
