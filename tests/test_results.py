"""Testes para nfe_sync/results.py — Issue #25."""
import pytest
from dataclasses import FrozenInstanceError

from nfe_sync.results import (
    Documento,
    ResultadoConsulta,
    ResultadoDfeChave,
    ResultadoDistribuicao,
    ResultadoEmissao,
    ResultadoManifestacao,
    ResultadoInutilizacao,
)


class TestDocumento:
    def test_sucesso_sem_erro(self):
        doc = Documento(nsu="001", schema="procNFe_v4.00.xsd", nome="chave.xml",
                        chave="chave", xml="<procNFe/>")
        assert doc.nsu == "001"
        assert doc.schema == "procNFe_v4.00.xsd"
        assert doc.nome == "chave.xml"
        assert doc.chave == "chave"
        assert doc.xml == "<procNFe/>"
        assert doc.erro is None

    def test_erro_sem_nome_xml_chave(self):
        doc = Documento(nsu="002", schema="resNFe_v1.01.xsd", erro="falha ao descompactar")
        assert doc.erro == "falha ao descompactar"
        assert doc.nome is None
        assert doc.xml is None
        assert doc.chave is None

    def test_frozen_impede_atribuicao(self):
        doc = Documento(nsu="001", schema="x")
        with pytest.raises(FrozenInstanceError):
            doc.nsu = "999"

    def test_slots_impede_atributo_arbitrario(self):
        doc = Documento(nsu="001", schema="x")
        with pytest.raises((AttributeError, TypeError)):
            doc.campo_inexistente = "y"


class TestResultadoConsulta:
    def test_campos_basicos(self):
        r = ResultadoConsulta(
            situacao=[{"status": "100", "motivo": "Autorizado"}],
            xml="<procNFe/>",
            xml_resposta="<retConsSitNFe/>",
        )
        assert r.situacao[0]["status"] == "100"
        assert r.xml == "<procNFe/>"
        assert r.xml_resposta == "<retConsSitNFe/>"

    def test_xml_none_quando_erro(self):
        r = ResultadoConsulta(
            situacao=[{"status": "215", "motivo": "Rejeicao"}],
            xml=None,
            xml_resposta="<retConsSitNFe/>",
        )
        assert r.xml is None

    def test_frozen(self):
        r = ResultadoConsulta(situacao=[], xml=None, xml_resposta="<r/>")
        with pytest.raises(FrozenInstanceError):
            r.xml = "x"


class TestResultadoDfeChave:
    def test_sucesso(self):
        doc = Documento(nsu="001", schema="procNFe_v4.00.xsd", xml="<x/>")
        r = ResultadoDfeChave(
            sucesso=True, status="138", motivo="Documento localizado",
            documentos=[doc], xml_resposta="<r/>", xml_cancelamento=None,
        )
        assert r.sucesso is True
        assert r.documentos[0].nsu == "001"
        assert r.xml_cancelamento is None

    def test_cancelamento(self):
        r = ResultadoDfeChave(
            sucesso=False, status="653", motivo="NF-e cancelada",
            documentos=[], xml_resposta="<r/>", xml_cancelamento="<cancel/>",
        )
        assert r.xml_cancelamento == "<cancel/>"

    def test_frozen(self):
        r = ResultadoDfeChave(sucesso=False, status=None, motivo=None,
                              documentos=[], xml_resposta="<r/>", xml_cancelamento=None)
        with pytest.raises(FrozenInstanceError):
            r.sucesso = True


class TestResultadoDistribuicao:
    def test_campos_completos(self):
        estado = {"nsu": {"99999999000191": 42}}
        r = ResultadoDistribuicao(
            sucesso=True, status="137", motivo="Nenhum documento",
            ultimo_nsu=42, max_nsu=42, documentos=[], xmls_resposta=["<r/>"],
            estado=estado,
        )
        assert r.sucesso is True
        assert r.ultimo_nsu == 42
        assert r.estado["nsu"]["99999999000191"] == 42

    def test_estado_mutavel_dentro_de_frozen(self):
        estado = {}
        r = ResultadoDistribuicao(
            sucesso=False, status=None, motivo="bloqueado",
            ultimo_nsu=0, max_nsu=0, documentos=[], xmls_resposta=[], estado=estado,
        )
        # Pode mutar o dict interno, mas não reatribuir o campo
        r.estado["key"] = "val"
        assert r.estado["key"] == "val"
        with pytest.raises(FrozenInstanceError):
            r.estado = {}

    def test_cooldown_bloqueado(self):
        r = ResultadoDistribuicao(
            sucesso=False, status=None, motivo="Distribuicao DFe bloqueada ate 10:00:00 (60min restantes)",
            ultimo_nsu=0, max_nsu=0, documentos=[], xmls_resposta=[], estado={},
        )
        assert r.sucesso is False
        assert r.status is None
        assert "bloqueada" in r.motivo


class TestResultadoEmissao:
    def test_sucesso(self):
        r = ResultadoEmissao(
            sucesso=True, status="100", motivo="Autorizado",
            protocolo="123456789", chave="1" * 44,
            xml="<nfeProc/>", xml_resposta=None, erros=[],
        )
        assert r.sucesso is True
        assert r.protocolo == "123456789"
        assert r.erros == []

    def test_falha_com_erros(self):
        r = ResultadoEmissao(
            sucesso=False, status=None, motivo=None,
            protocolo=None, chave=None, xml=None,
            xml_resposta="<ret/>", erros=[{"status": "215", "motivo": "Rejeicao"}],
        )
        assert r.sucesso is False
        assert r.erros[0]["status"] == "215"

    def test_frozen(self):
        r = ResultadoEmissao(sucesso=False, status=None, motivo=None,
                             protocolo=None, chave=None, xml=None,
                             xml_resposta=None, erros=[])
        with pytest.raises(FrozenInstanceError):
            r.sucesso = True


class TestResultadoManifestacao:
    def test_campos(self):
        r = ResultadoManifestacao(
            resultados=[{"status": "135", "motivo": "Evento registrado"}],
            protocolo="999",
            xml="<retEvento/>",
            xml_resposta="<retEvento/>",
        )
        assert r.resultados[0]["status"] == "135"
        assert r.protocolo == "999"

    def test_frozen(self):
        r = ResultadoManifestacao(resultados=[], protocolo=None, xml="<x/>", xml_resposta="<x/>")
        with pytest.raises(FrozenInstanceError):
            r.protocolo = "x"


class TestResultadoInutilizacao:
    def test_campos(self):
        r = ResultadoInutilizacao(
            sucesso=True,
            resultados=[{"status": "102", "motivo": "Inutilizacao homologada"}],
            protocolo="777",
            xml="<retInutNFe/>",
            xml_resposta="<retInutNFe/>",
        )
        assert r.sucesso is True
        assert r.resultados[0]["status"] == "102"
        assert r.protocolo == "777"

    def test_frozen(self):
        r = ResultadoInutilizacao(sucesso=False, resultados=[], protocolo=None, xml="<x/>", xml_resposta="<x/>")
        with pytest.raises(FrozenInstanceError):
            r.xml = "outro"
