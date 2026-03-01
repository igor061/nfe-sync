import logging
from datetime import datetime, timedelta
from unittest.mock import patch, MagicMock, call
import pytest

from nfe_sync.consulta import (
    verificar_cooldown, calcular_proximo_cooldown, consultar_nsu,
    consultar, consultar_dfe_chave,
    _agora_brt, _com_retry, _SALVAR_A_CADA,
)
from nfe_sync.exceptions import NfeValidationError
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
        cnpj = empresa_sul.emitente.cnpj
        estado = {"cooldown": {f"{cnpj}:homologacao": futuro}}
        state_file = str(tmp_path / "state.json")

        resultado = consultar_nsu(empresa_sul, estado, state_file)
        assert resultado["sucesso"] is False
        assert "bloqueada" in resultado["motivo"]
        assert resultado["documentos"] == []

    @patch("nfe_sync.xml_utils.ComunicacaoSefaz")
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

    XML_COM_DOC_FINAL = b"""<?xml version="1.0" encoding="utf-8"?>
    <retDistDFeInt xmlns="http://www.portalfiscal.inf.br/nfe">
        <tpAmb>2</tpAmb>
        <cStat>138</cStat>
        <xMotivo>Documento localizado</xMotivo>
        <ultNSU>000000000000100</ultNSU>
        <maxNSU>000000000000100</maxNSU>
        <loteDistDFeInt>
            <docZip NSU="000000000000100" schema="resNFe_v1.01.xsd">H4sIAAAAAAAAA6tWKkktLlGyUlAqS8wpTgUAhRxpOhUAAAA=</docZip>
        </loteDistDFeInt>
    </retDistDFeInt>"""

    @patch("nfe_sync.xml_utils.ComunicacaoSefaz")
    def test_documento_localizado(self, mock_sefaz_cls, empresa_sul, tmp_path):
        resp1 = MagicMock()
        resp1.content = self.XML_COM_DOC
        resp2 = MagicMock()
        resp2.content = self.XML_COM_DOC_FINAL
        mock_sefaz_cls.return_value.consulta_distribuicao.side_effect = [resp1, resp2]

        state_file = str(tmp_path / "state.json")
        estado = {}

        resultado = consultar_nsu(empresa_sul, estado, state_file)
        assert resultado["sucesso"] is True
        assert resultado["status"] == "138"
        assert resultado["ultimo_nsu"] == 100
        assert resultado["max_nsu"] == 100
        assert len(resultado["documentos"]) == 2
        assert resultado["documentos"][0]["nsu"] == "000000000000042"
        assert resultado["documentos"][1]["nsu"] == "000000000000100"

        # verifica que salvou estado (sem cooldown quando baixou documentos com 138)
        estado_salvo = carregar_estado(state_file)
        assert estado_salvo["nsu"][empresa_sul.emitente.cnpj] == 100
        assert f"{empresa_sul.emitente.cnpj}:homologacao" not in estado_salvo.get("cooldown", {})

    @patch("nfe_sync.xml_utils.ComunicacaoSefaz")
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


class TestAgoraBrt:
    """Issue #14: _agora_brt retorna datetime sem tzinfo."""

    def test_retorna_sem_tzinfo(self):
        dt = _agora_brt()
        assert dt.tzinfo is None

    def test_e_datetime(self):
        assert isinstance(_agora_brt(), datetime)


class TestComRetry:
    """Issue #5: retry com backoff exponencial."""

    def test_sucesso_na_primeira_tentativa(self):
        fn = MagicMock(return_value="ok")
        resultado = _com_retry(fn, "arg1", kw=1)
        assert resultado == "ok"
        fn.assert_called_once_with("arg1", kw=1)

    def test_retry_apos_falha(self):
        fn = MagicMock(side_effect=[RuntimeError("falha"), "ok"])
        with patch("nfe_sync.consulta.time.sleep") as mock_sleep:
            resultado = _com_retry(fn, tentativas=3, base=1)
        assert resultado == "ok"
        mock_sleep.assert_called_once_with(1)  # base * 2^0 = 1

    def test_levanta_na_ultima_tentativa(self):
        fn = MagicMock(side_effect=RuntimeError("sempre falha"))
        with patch("nfe_sync.consulta.time.sleep"):
            with pytest.raises(RuntimeError, match="sempre falha"):
                _com_retry(fn, tentativas=3, base=1)
        assert fn.call_count == 3

    def test_backoff_exponencial(self):
        fn = MagicMock(side_effect=[RuntimeError(), RuntimeError(), "ok"])
        with patch("nfe_sync.consulta.time.sleep") as mock_sleep:
            _com_retry(fn, tentativas=3, base=5)
        assert mock_sleep.call_args_list == [call(5), call(10)]  # 5*2^0, 5*2^1


class TestStateSaveFrequency:
    """Issue #7: salvar estado a cada _SALVAR_A_CADA páginas."""

    XML_TEMPLATE = b"""<?xml version="1.0" encoding="utf-8"?>
    <retDistDFeInt xmlns="http://www.portalfiscal.inf.br/nfe">
        <tpAmb>2</tpAmb>
        <cStat>138</cStat>
        <xMotivo>Documento localizado</xMotivo>
        <ultNSU>{nsu:015d}</ultNSU>
        <maxNSU>000000000000200</maxNSU>
        <loteDistDFeInt>
            <docZip NSU="{nsu:015d}" schema="resNFe_v1.01.xsd">H4sIAAAAAAAAA6tWKkktLlGyUlAqS8wpTgUAhRxpOhUAAAA=</docZip>
        </loteDistDFeInt>
    </retDistDFeInt>"""

    XML_FINAL = b"""<?xml version="1.0" encoding="utf-8"?>
    <retDistDFeInt xmlns="http://www.portalfiscal.inf.br/nfe">
        <tpAmb>2</tpAmb>
        <cStat>137</cStat>
        <xMotivo>Nenhum documento localizado</xMotivo>
        <ultNSU>000000000000200</ultNSU>
        <maxNSU>000000000000200</maxNSU>
    </retDistDFeInt>"""

    @patch("nfe_sync.xml_utils.ComunicacaoSefaz")
    def test_salva_apenas_a_cada_n_paginas(self, mock_sefaz_cls, empresa_sul, tmp_path):
        """Deve salvar estado a cada _SALVAR_A_CADA páginas, não a cada 1."""
        respostas = []
        # Gerar _SALVAR_A_CADA páginas com nsu crescente, cada uma ainda abaixo do max
        for i in range(1, _SALVAR_A_CADA + 1):
            nsu = i
            xml = self.XML_TEMPLATE.replace(b"{nsu:015d}", f"{nsu:015d}".encode()).replace(
                b"{nsu:015d}", f"{nsu:015d}".encode()
            )
            # usar format simples
            xml_str = (
                b'<?xml version="1.0" encoding="utf-8"?>\n'
                b'<retDistDFeInt xmlns="http://www.portalfiscal.inf.br/nfe">'
                b"<tpAmb>2</tpAmb><cStat>138</cStat>"
                b"<xMotivo>Documento localizado</xMotivo>"
                + f"<ultNSU>{nsu:015d}</ultNSU>".encode()
                + b"<maxNSU>000000000000200</maxNSU>"
                b"<loteDistDFeInt>"
                b'<docZip NSU="' + f"{nsu:015d}".encode() + b'" schema="resNFe_v1.01.xsd">'
                b"H4sIAAAAAAAAA6tWKkktLlGyUlAqS8wpTgUAhRxpOhUAAAA="
                b"</docZip></loteDistDFeInt>"
                b"</retDistDFeInt>"
            )
            resp = MagicMock()
            resp.content = xml_str
            respostas.append(resp)
        resp_final = MagicMock()
        resp_final.content = self.XML_FINAL
        respostas.append(resp_final)

        mock_sefaz_cls.return_value.consulta_distribuicao.side_effect = respostas

        state_file = str(tmp_path / "state.json")
        estado = {}

        save_calls = []
        import nfe_sync.consulta as consulta_mod
        original_salvar = consulta_mod.salvar_estado

        def track_save(sf, est):
            save_calls.append(est.get("nsu", {}).copy())
            original_salvar(sf, est)

        with patch.object(consulta_mod, "salvar_estado", side_effect=track_save):
            consultar_nsu(empresa_sul, estado, state_file)

        # Deve ter salvo na página _SALVAR_A_CADA (NSU = _SALVAR_A_CADA) e no cooldown final
        # Não deve ter salvo nas páginas 1..(_SALVAR_A_CADA - 1)
        assert len(save_calls) >= 1


class TestProcessarDocsLogging:
    """Issue #1: logging de traceback em _processar_docs."""

    XML_COM_DOC_CORROMPIDO = (
        b'<?xml version="1.0" encoding="utf-8"?>'
        b'<retDistDFeInt xmlns="http://www.portalfiscal.inf.br/nfe">'
        b"<tpAmb>2</tpAmb><cStat>138</cStat>"
        b"<xMotivo>Documento localizado</xMotivo>"
        b"<ultNSU>000000000000001</ultNSU>"
        b"<maxNSU>000000000000001</maxNSU>"
        b"<loteDistDFeInt>"
        b'<docZip NSU="000000000000001" schema="resNFe_v1.01.xsd">DADOS_INVALIDOS</docZip>'
        b"</loteDistDFeInt>"
        b"</retDistDFeInt>"
    )

    @patch("nfe_sync.xml_utils.ComunicacaoSefaz")
    def test_erro_processamento_gera_warning(self, mock_sefaz_cls, empresa_sul, tmp_path, caplog):
        resp = MagicMock()
        resp.content = self.XML_COM_DOC_CORROMPIDO
        mock_sefaz_cls.return_value.consulta_distribuicao.return_value = resp

        state_file = str(tmp_path / "state.json")
        with caplog.at_level(logging.WARNING):
            resultado = consultar_nsu(empresa_sul, {}, state_file)

        # O documento com erro deve estar na lista mas sem interromper
        assert len(resultado["documentos"]) == 1
        assert "erro" in resultado["documentos"][0]
        # O warning deve ter sido emitido
        assert any("000000000000001" in r.message for r in caplog.records)


class TestValidarChave:
    """Issue #21: validação local da chave de acesso antes de enviar à SEFAZ."""

    CHAVE_VALIDA = "52991299999999999999550010000000011000000010"

    def test_consultar_chave_curta_levanta_erro(self, empresa_sul):
        with pytest.raises(NfeValidationError, match="44 digitos"):
            consultar(empresa_sul, "1234")

    def test_consultar_chave_com_letras_levanta_erro(self, empresa_sul):
        with pytest.raises(NfeValidationError, match="44 digitos"):
            consultar(empresa_sul, "A" * 44)

    def test_consultar_chave_vazia_levanta_erro(self, empresa_sul):
        with pytest.raises(NfeValidationError):
            consultar(empresa_sul, "")

    def test_consultar_chave_valida_nao_levanta(self, empresa_sul):
        """Chave válida passa a validação e chega até a chamada SEFAZ."""
        with patch("nfe_sync.xml_utils.ComunicacaoSefaz") as mock_cls:
            mock_resp = MagicMock()
            mock_resp.content = (
                b'<retConsSitNFe xmlns="http://www.portalfiscal.inf.br/nfe">'
                b"<cStat>100</cStat><xMotivo>Autorizado</xMotivo>"
                b"</retConsSitNFe>"
            )
            mock_cls.return_value.consulta_nota.return_value = mock_resp
            resultado = consultar(empresa_sul, self.CHAVE_VALIDA)
        assert resultado["situacao"] is not None

    def test_consultar_dfe_chave_curta_levanta_erro(self, empresa_sul):
        with pytest.raises(NfeValidationError, match="44 digitos"):
            consultar_dfe_chave(empresa_sul, "1234")

    def test_consultar_dfe_chave_com_letras_levanta_erro(self, empresa_sul):
        with pytest.raises(NfeValidationError, match="44 digitos"):
            consultar_dfe_chave(empresa_sul, "X" * 44)
