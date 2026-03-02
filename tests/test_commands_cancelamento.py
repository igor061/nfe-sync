"""Testes para commands/cancelamento.py."""
import pytest
from unittest.mock import patch, MagicMock

from nfe_sync.results import ResultadoCancelamento


CHAVE_VALIDA = "52991299999999999999550010000000011000000010"


def _make_resultado(sucesso, c_stat, motivo):
    return ResultadoCancelamento(
        sucesso=sucesso,
        resultados=[{"status": c_stat, "motivo": motivo}],
        protocolo="135240000012345" if sucesso else None,
        xml="<cancNFe/>",
        xml_resposta="<retEnvEvento/>",
    )


def _make_args(empresa):
    args = MagicMock()
    args.empresa = empresa.nome
    args.chave = CHAVE_VALIDA
    args.protocolo = "135240000012345"
    args.justificativa = "Erro de emissao no sistema"
    args.homologacao = True
    args.producao = False
    return args


class TestCmdCancelar:
    def test_cancelar_sucesso_salva_xml(self, empresa_sul, capsys):
        from nfe_sync.commands.cancelamento import cmd_cancelar

        resultado = _make_resultado(True, "135", "Evento registrado e vinculado a NF-e")
        args = _make_args(empresa_sul)
        arquivo_salvo = f"downloads/{empresa_sul.emitente.cnpj}/{CHAVE_VALIDA}-cancelamento.xml"

        with patch("nfe_sync.commands.cancelamento._carregar", return_value=(empresa_sul, {})), \
             patch("nfe_sync.cancelamento.cancelar", return_value=resultado), \
             patch("nfe_sync.commands.cancelamento._salvar_log_xml"), \
             patch("nfe_sync.commands.cancelamento._salvar_xml", return_value=arquivo_salvo) as mock_salvar:
            cmd_cancelar(args)  # nao deve levantar SystemExit

        mock_salvar.assert_called_once_with(
            empresa_sul.emitente.cnpj,
            f"{CHAVE_VALIDA}-cancelamento.xml",
            resultado.xml,
        )
        out = capsys.readouterr().out
        assert "135" in out
        assert "RESULTADO" in out

    def test_cancelar_falha_exit_1(self, empresa_sul, capsys):
        from nfe_sync.commands.cancelamento import cmd_cancelar

        resultado = _make_resultado(False, "589", "Rejeicao: Duplicidade de evento")
        args = _make_args(empresa_sul)

        with patch("nfe_sync.commands.cancelamento._carregar", return_value=(empresa_sul, {})), \
             patch("nfe_sync.cancelamento.cancelar", return_value=resultado), \
             patch("nfe_sync.commands.cancelamento._salvar_log_xml"), \
             patch("nfe_sync.commands.cancelamento._salvar_xml", return_value="arquivo.xml"):
            with pytest.raises(SystemExit) as exc:
                cmd_cancelar(args)

        assert exc.value.code == 1

    def test_resultado_impresso_antes_exit(self, empresa_sul, capsys):
        """Mesmo em caso de erro, o cStat é impresso antes do exit."""
        from nfe_sync.commands.cancelamento import cmd_cancelar

        resultado = _make_resultado(False, "589", "Rejeicao: Duplicidade de evento")
        args = _make_args(empresa_sul)

        with patch("nfe_sync.commands.cancelamento._carregar", return_value=(empresa_sul, {})), \
             patch("nfe_sync.cancelamento.cancelar", return_value=resultado), \
             patch("nfe_sync.commands.cancelamento._salvar_log_xml"), \
             patch("nfe_sync.commands.cancelamento._salvar_xml", return_value="arquivo.xml"):
            with pytest.raises(SystemExit):
                cmd_cancelar(args)

        out = capsys.readouterr().out
        assert "589" in out
        assert "RESULTADO" in out
