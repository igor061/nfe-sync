"""Testes para commands/consulta.py — Issues #8, #9, #10."""
import logging
import os
import pytest
from unittest.mock import patch, MagicMock

from nfe_sync.results import (
    Documento, ResultadoConsulta, ResultadoDfeChave, ResultadoDistribuicao,
)


class TestProcessarESalvarDocs:
    """Issue #8: helper _processar_e_salvar_docs elimina duplicação."""

    def test_imprime_e_salva_prochfe(self, tmp_path, capsys):
        from nfe_sync.commands.consulta import _processar_e_salvar_docs

        docs = [Documento(
            nsu="001",
            chave="12345678901234567890123456789012345678901234",
            schema="procNFe_v4.00.xsd",
            nome="12345678901234567890123456789012345678901234.xml",
            xml="<procNFe/>",
        )]

        with patch("nfe_sync.commands.consulta._salvar_xml") as mock_salvar:
            completos = _processar_e_salvar_docs("99999999000191", docs)

        assert completos == ["12345678901234567890123456789012345678901234"]
        captured = capsys.readouterr()
        assert "XML completo" in captured.out

    def test_imprime_erro(self, capsys):
        from nfe_sync.commands.consulta import _processar_e_salvar_docs

        docs = [Documento(nsu="001", schema="resNFe_v1.01.xsd", erro="falha ao descompactar")]
        with patch("nfe_sync.commands.consulta._salvar_xml"):
            completos = _processar_e_salvar_docs("99999999000191", docs)

        assert completos == []
        captured = capsys.readouterr()
        assert "ERRO" in captured.out

    def test_resumo_nao_adicionado_a_completos(self, capsys):
        from nfe_sync.commands.consulta import _processar_e_salvar_docs

        docs = [Documento(
            nsu="001",
            chave="12345678901234567890123456789012345678901234",
            schema="resNFe_v1.01.xsd",
            nome="12345678901234567890123456789012345678901234.xml",
            xml="<resNFe/>",
        )]
        with patch("nfe_sync.commands.consulta._salvar_xml"):
            completos = _processar_e_salvar_docs("99999999000191", docs)

        assert completos == []
        captured = capsys.readouterr()
        assert "resumo" in captured.out

    def test_substituiu_quando_procnfe_existente(self, capsys):
        """Issue #36: usa _storage.existe() para detectar substituição de resumo."""
        from nfe_sync.commands.consulta import _processar_e_salvar_docs

        docs = [Documento(
            nsu="001",
            chave="12345678901234567890123456789012345678901234",
            schema="procNFe_v4.00.xsd",
            nome="12345678901234567890123456789012345678901234.xml",
            xml="<procNFe/>",
        )]

        with patch("nfe_sync.commands.consulta._salvar_xml") as mock_salvar, \
             patch("nfe_sync.commands.consulta._storage") as mock_storage:
            mock_storage.existe.return_value = True
            mock_salvar.return_value = "downloads/99999999000191/chave.xml"
            completos = _processar_e_salvar_docs("99999999000191", docs)

        mock_storage.existe.assert_called_once_with(
            "99999999000191", "12345678901234567890123456789012345678901234.xml"
        )
        captured = capsys.readouterr()
        assert "substituiu resumo" in captured.out


class TestListarResumosPendentes:
    """Issue #9: deve detectar resNFe por root tag, sem filtrar por len(nome)."""

    def test_detecta_arquivo_com_nome_curto(self, tmp_path):
        """Arquivos com nome != 44 chars também devem ser detectados se root tag = resNFe."""
        from nfe_sync.commands import _listar_resumos_pendentes
        import nfe_sync.storage as storage_mod

        cnpj = "99999999000191"

        with patch("os.path.isdir", return_value=True), \
             patch("os.listdir", return_value=["resumo-curto.xml", "outro.xml"]), \
             patch.object(storage_mod, "safe_parse") as mock_parse:

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
        import nfe_sync.storage as storage_mod

        cnpj = "99999999000191"
        with patch("os.path.isdir", return_value=True), \
             patch("os.listdir", return_value=["invalido.xml"]), \
             patch.object(storage_mod, "safe_parse", side_effect=Exception("xml quebrado")):
            with caplog.at_level(logging.WARNING):
                resultado = _listar_resumos_pendentes(cnpj)

        assert resultado == []
        assert any("invalido.xml" in r.message for r in caplog.records)


class TestTratarArquivoCancelado:
    """Issue #10: logging em _tratar_arquivo_cancelado."""

    def test_loga_warning_ao_falhar_leitura(self, tmp_path, caplog):
        import nfe_sync.storage as storage_mod
        from nfe_sync.commands.consulta import _tratar_arquivo_cancelado

        cnpj = "99999999000191"
        chave = "12345678901234567890123456789012345678901234"

        with patch("os.path.exists", return_value=True), \
             patch("os.rename"), \
             patch.object(storage_mod, "safe_parse", side_effect=Exception("parse error")):
            with caplog.at_level(logging.WARNING):
                # Deve continuar sem levantar exceção
                _tratar_arquivo_cancelado(cnpj, chave)

        assert any("parse error" in r.message or chave in r.message for r in caplog.records)


class TestCmdConsultarExitCode:
    """Issue #22: cmd_consultar deve retornar exit code 1 para status de erro SEFAZ."""

    def _make_mock_empresa(self):
        from nfe_sync.models import EmpresaConfig, Certificado, Emitente
        return EmpresaConfig(
            nome="SUL",
            certificado=Certificado(path="/tmp/cert.pfx", senha="123456"),
            emitente=Emitente(cnpj="99999999000191"),
            uf="sp",
            homologacao=True,
        )

    def _make_args(self, chave="52991299999999999999550010000000011000000010"):
        args = MagicMock()
        args.chave = chave
        args.empresa = "SUL"
        args.producao = False
        args.homologacao = False
        return args

    @patch("nfe_sync.commands.consulta._carregar")
    @patch("nfe_sync.commands.consulta._salvar_log_xml")
    @patch("nfe_sync.commands.consulta.consultar")
    def test_status_215_sai_com_codigo_1(self, mock_consultar, mock_log, mock_carregar):
        """cStat=215 (rejeição) → exit code 1."""
        mock_carregar.return_value = (self._make_mock_empresa(), {})
        mock_log.return_value = "log/x.xml"
        mock_consultar.return_value = ResultadoConsulta(
            situacao=[{"status": "215", "motivo": "Rejeicao: CNPJ invalido"}],
            xml=None,
            xml_resposta="<resp/>",
        )

        from nfe_sync.commands.consulta import cmd_consultar
        with pytest.raises(SystemExit) as exc:
            cmd_consultar(self._make_args())
        assert exc.value.code == 1

    @patch("nfe_sync.commands.consulta._carregar")
    @patch("nfe_sync.commands.consulta._salvar_log_xml")
    @patch("nfe_sync.commands.consulta.consultar")
    @patch("nfe_sync.commands.consulta.consultar_dfe_chave")
    def test_status_100_nao_sai(self, mock_dfe, mock_consultar, mock_log, mock_carregar):
        """cStat=100 (autorizado) → sem SystemExit."""
        mock_carregar.return_value = (self._make_mock_empresa(), {})
        mock_log.return_value = "log/x.xml"
        mock_consultar.return_value = ResultadoConsulta(
            situacao=[{"status": "100", "motivo": "Autorizado o uso da NF-e"}],
            xml="<procNFe/>",
            xml_resposta="<resp/>",
        )
        mock_dfe.return_value = ResultadoDfeChave(
            sucesso=True,
            status="138",
            motivo="Documento localizado",
            xml_cancelamento=None,
            documentos=[],
            xml_resposta="<resp/>",
        )

        with patch("nfe_sync.commands.consulta._salvar_xml"):
            from nfe_sync.commands.consulta import cmd_consultar
            cmd_consultar(self._make_args())  # não deve levantar SystemExit

    @patch("nfe_sync.commands.consulta._carregar")
    @patch("nfe_sync.commands.consulta._salvar_log_xml")
    @patch("nfe_sync.commands.consulta.consultar_nsu")
    def test_nsu_status_589_sai_com_codigo_1(self, mock_nsu, mock_log, mock_carregar, tmp_path):
        """consultar_nsu com status 589 (erro) → exit code 1."""
        mock_carregar.return_value = (self._make_mock_empresa(), {})
        mock_log.return_value = "log/x.xml"
        mock_nsu.return_value = ResultadoDistribuicao(
            sucesso=False,
            status="589",
            motivo="Rejeicao: acesso negado",
            ultimo_nsu=0,
            max_nsu=0,
            documentos=[],
            xmls_resposta=["<resp/>"],
            estado={},
        )

        args = MagicMock()
        args.empresa = "SUL"
        args.nsu = None
        args.zerar_nsu = False
        args.chave = None
        args.producao = False
        args.homologacao = False

        from nfe_sync.commands.consulta import cmd_consultar_nsu
        with pytest.raises(SystemExit) as exc:
            cmd_consultar_nsu(args)
        assert exc.value.code == 1

    @patch("nfe_sync.commands.consulta._carregar")
    @patch("nfe_sync.commands.consulta._salvar_log_xml")
    @patch("nfe_sync.commands.consulta.consultar_nsu")
    def test_nsu_status_137_nao_sai(self, mock_nsu, mock_log, mock_carregar, tmp_path):
        """consultar_nsu com status 137 (sem docs) → sem SystemExit."""
        mock_carregar.return_value = (self._make_mock_empresa(), {})
        mock_log.return_value = "log/x.xml"
        mock_nsu.return_value = ResultadoDistribuicao(
            sucesso=True,
            status="137",
            motivo="Nenhum documento localizado",
            ultimo_nsu=0,
            max_nsu=0,
            documentos=[],
            xmls_resposta=["<resp/>"],
            estado={},
        )

        args = MagicMock()
        args.empresa = "SUL"
        args.nsu = None
        args.zerar_nsu = False
        args.chave = None
        args.producao = False
        args.homologacao = False

        from nfe_sync.commands.consulta import cmd_consultar_nsu
        cmd_consultar_nsu(args)  # não deve levantar SystemExit

    @patch("nfe_sync.commands.consulta._carregar")
    @patch("nfe_sync.commands.consulta._salvar_log_xml")
    @patch("nfe_sync.commands.consulta.consultar_nsu")
    def test_nsu_erro_imprime_status_antes_de_sair(self, mock_nsu, mock_log, mock_carregar, capsys):
        """Issue #71: consultar_nsu com sucesso=False deve imprimir status e motivo antes do exit."""
        mock_carregar.return_value = (self._make_mock_empresa(), {})
        mock_log.return_value = "log/x.xml"
        mock_nsu.return_value = ResultadoDistribuicao(
            sucesso=False,
            status="656",
            motivo="Consumo Indevido",
            ultimo_nsu=0,
            max_nsu=0,
            documentos=[],
            xmls_resposta=[],
            estado={},
        )

        args = MagicMock()
        args.empresa = "SUL"
        args.nsu = None
        args.zerar_nsu = False
        args.chave = None
        args.producao = False
        args.homologacao = False

        from nfe_sync.commands.consulta import cmd_consultar_nsu
        with pytest.raises(SystemExit) as exc:
            cmd_consultar_nsu(args)
        assert exc.value.code == 1
        out = capsys.readouterr().out
        assert "656" in out
        assert "Consumo Indevido" in out


class TestCmdConsultarNsuTodasEmpresas:
    """Issue #92: sem empresa → itera todos os cadastros."""

    def _make_resultado_sucesso(self):
        return ResultadoDistribuicao(
            sucesso=True, status="137", motivo="Nenhum documento localizado",
            ultimo_nsu=0, max_nsu=0, documentos=[], xmls_resposta=["<r/>"], estado={},
        )

    def _make_resultado_falha(self):
        return ResultadoDistribuicao(
            sucesso=False, status="656", motivo="Consumo Indevido",
            ultimo_nsu=0, max_nsu=0, documentos=[], xmls_resposta=[], estado={},
        )

    @patch("nfe_sync.commands.consulta._salvar_log_xml")
    @patch("nfe_sync.commands.consulta.consultar_nsu")
    @patch("nfe_sync.commands.consulta.carregar_empresas")
    def test_sem_empresa_itera_todas(self, mock_empresas, mock_nsu, mock_log, capsys):
        """Sem empresa: cmd_consultar_nsu deve chamar consultar_nsu para cada empresa."""
        from unittest.mock import MagicMock
        from nfe_sync.commands.consulta import cmd_consultar_nsu

        emp1 = MagicMock(); emp1.emitente.cnpj = "11111111000191"; emp1.nome = "EMP1"; emp1.homologacao = True
        emp2 = MagicMock(); emp2.emitente.cnpj = "22222222000191"; emp2.nome = "EMP2"; emp2.homologacao = True
        mock_empresas.return_value = {"EMP1": emp1, "EMP2": emp2}
        mock_nsu.return_value = self._make_resultado_sucesso()
        mock_log.return_value = "log/x.xml"

        args = MagicMock()
        args.empresa = None
        args.nsu = None
        args.zerar_nsu = False
        args.chave = None
        args.producao = False
        args.homologacao = False

        cmd_consultar_nsu(args)  # não deve levantar SystemExit

        assert mock_nsu.call_count == 2
        out = capsys.readouterr().out
        assert "EMP1" in out
        assert "EMP2" in out

    @patch("nfe_sync.commands.consulta._salvar_log_xml")
    @patch("nfe_sync.commands.consulta.consultar_nsu")
    @patch("nfe_sync.commands.consulta.carregar_empresas")
    def test_sem_empresa_falha_parcial_sai_1(self, mock_empresas, mock_nsu, mock_log):
        """Sem empresa: se qualquer empresa falhar, exit code 1 ao final."""
        from unittest.mock import MagicMock
        from nfe_sync.commands.consulta import cmd_consultar_nsu

        emp1 = MagicMock(); emp1.emitente.cnpj = "11111111000191"; emp1.nome = "EMP1"; emp1.homologacao = True
        emp2 = MagicMock(); emp2.emitente.cnpj = "22222222000191"; emp2.nome = "EMP2"; emp2.homologacao = True
        mock_empresas.return_value = {"EMP1": emp1, "EMP2": emp2}
        mock_nsu.side_effect = [self._make_resultado_sucesso(), self._make_resultado_falha()]
        mock_log.return_value = "log/x.xml"

        args = MagicMock()
        args.empresa = None
        args.nsu = None
        args.zerar_nsu = False
        args.chave = None
        args.producao = False
        args.homologacao = False

        with pytest.raises(SystemExit) as exc:
            cmd_consultar_nsu(args)
        assert exc.value.code == 1

    def test_sem_empresa_chave_exige_empresa(self, capsys):
        """--chave sem empresa deve sair com erro."""
        from unittest.mock import MagicMock
        from nfe_sync.commands.consulta import cmd_consultar_nsu

        args = MagicMock()
        args.empresa = None
        args.chave = "52991299999999999999550010000000011000000010"
        args.zerar_nsu = False
        args.producao = False
        args.homologacao = False

        with pytest.raises(SystemExit) as exc:
            cmd_consultar_nsu(args)
        assert exc.value.code == 1
        assert "requerem empresa" in capsys.readouterr().out

    def test_sem_empresa_zerar_nsu_exige_empresa(self, capsys):
        """--zerar-nsu sem empresa deve sair com erro."""
        from unittest.mock import MagicMock
        from nfe_sync.commands.consulta import cmd_consultar_nsu

        args = MagicMock()
        args.empresa = None
        args.chave = None
        args.zerar_nsu = True
        args.producao = False
        args.homologacao = False

        with pytest.raises(SystemExit) as exc:
            cmd_consultar_nsu(args)
        assert exc.value.code == 1
        assert "requerem empresa" in capsys.readouterr().out
