"""Testes para commands/inutilizacao.py — Issue #41."""
import pytest
from unittest.mock import patch, MagicMock

from nfe_sync.results import ResultadoInutilizacao


def _make_resultado(sucesso, c_stat, motivo):
    return ResultadoInutilizacao(
        sucesso=sucesso,
        resultados=[{"status": c_stat, "motivo": motivo}],
        protocolo="123456789" if sucesso else None,
        xml="<inutNFe/>",
        xml_resposta="<retInutNFe/>",
    )


def _make_args(empresa):
    args = MagicMock()
    args.empresa = empresa.nome
    args.serie = "1"
    args.inicio = 900000
    args.fim = 900000
    args.justificativa = "Numeracao nao utilizada no sistema"
    args.homologacao = True
    args.producao = False
    return args


class TestCmdInutilizarExitCode:
    """Issue #41: exit code 1 quando SEFAZ rejeita inutilizacao."""

    def test_exit_0_quando_sucesso(self, empresa_sul, tmp_path, capsys):
        from nfe_sync.commands.inutilizacao import cmd_inutilizar

        resultado = _make_resultado(True, "102", "Inutilizacao de numero homologado")
        args = _make_args(empresa_sul)

        with patch("nfe_sync.commands.inutilizacao._carregar", return_value=(empresa_sul, {})), \
             patch("nfe_sync.inutilizacao.inutilizar", return_value=resultado), \
             patch("nfe_sync.commands.inutilizacao._salvar_log_xml"), \
             patch("nfe_sync.commands.inutilizacao.os.makedirs"), \
             patch("builtins.open", MagicMock()):
            cmd_inutilizar(args)  # não deve levantar SystemExit

    def test_exit_1_quando_rejeicao(self, empresa_sul, capsys):
        from nfe_sync.commands.inutilizacao import cmd_inutilizar

        resultado = _make_resultado(False, "266", "Rejeicao: Serie utilizada nao permitida no Web Service")
        args = _make_args(empresa_sul)

        with patch("nfe_sync.commands.inutilizacao._carregar", return_value=(empresa_sul, {})), \
             patch("nfe_sync.inutilizacao.inutilizar", return_value=resultado), \
             patch("nfe_sync.commands.inutilizacao._salvar_log_xml"), \
             patch("nfe_sync.commands.inutilizacao.os.makedirs"), \
             patch("builtins.open", MagicMock()):
            with pytest.raises(SystemExit) as exc:
                cmd_inutilizar(args)

        assert exc.value.code == 1

    def test_resultado_impresso_antes_exit(self, empresa_sul, capsys):
        """Mesmo em caso de erro, o cStat é impresso antes do exit."""
        from nfe_sync.commands.inutilizacao import cmd_inutilizar

        resultado = _make_resultado(False, "266", "Rejeicao: Serie utilizada nao permitida")
        args = _make_args(empresa_sul)

        with patch("nfe_sync.commands.inutilizacao._carregar", return_value=(empresa_sul, {})), \
             patch("nfe_sync.inutilizacao.inutilizar", return_value=resultado), \
             patch("nfe_sync.commands.inutilizacao._salvar_log_xml"), \
             patch("nfe_sync.commands.inutilizacao.os.makedirs"), \
             patch("builtins.open", MagicMock()):
            with pytest.raises(SystemExit):
                cmd_inutilizar(args)

        out = capsys.readouterr().out
        assert "266" in out
        assert "RESULTADO" in out
