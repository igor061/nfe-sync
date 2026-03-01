"""Testes para commands/emissao.py — Issue #40."""
import pytest
from unittest.mock import patch, MagicMock

from nfe_sync.models import EmpresaConfig, Certificado, Emitente, Endereco


@pytest.fixture
def empresa_sem_endereco():
    return EmpresaConfig(
        nome="SUL",
        certificado=Certificado(path="/tmp/cert.pfx", senha="123456"),
        emitente=Emitente(cnpj="99999999000191"),
        uf="sp",
        homologacao=True,
    )


@pytest.fixture
def empresa_com_endereco():
    return EmpresaConfig(
        nome="SUL",
        certificado=Certificado(path="/tmp/cert.pfx", senha="123456"),
        emitente=Emitente(
            cnpj="99999999000191",
            endereco=Endereco(
                logradouro="RUA EXEMPLO",
                numero="100",
                bairro="CENTRO",
                municipio="SAO PAULO",
                cod_municipio="3550308",
                uf="SP",
                cep="01310100",
            ),
        ),
        uf="sp",
        homologacao=True,
    )


class TestCmdEmitirSemEndereco:
    """Issue #40: mensagem amigável quando endereco é None."""

    def _make_args(self, empresa):
        args = MagicMock()
        args.empresa = empresa.nome
        args.serie = "1"
        args.homologacao = True
        args.producao = False
        return args

    def test_exit_code_1_sem_endereco(self, empresa_sem_endereco, capsys):
        from nfe_sync.commands.emissao import cmd_emitir

        args = self._make_args(empresa_sem_endereco)
        with patch("nfe_sync.commands.emissao._carregar", return_value=(empresa_sem_endereco, {})):
            with pytest.raises(SystemExit) as exc:
                cmd_emitir(args)

        assert exc.value.code == 1

    def test_mensagem_amigavel_sem_endereco(self, empresa_sem_endereco, capsys):
        from nfe_sync.commands.emissao import cmd_emitir

        args = self._make_args(empresa_sem_endereco)
        with patch("nfe_sync.commands.emissao._carregar", return_value=(empresa_sem_endereco, {})):
            with pytest.raises(SystemExit):
                cmd_emitir(args)

        out = capsys.readouterr().out
        assert "endereco" in out.lower()
        assert "api_cli" in out

    def test_sem_traceback_sem_endereco(self, empresa_sem_endereco, capsys):
        """Não deve levantar AttributeError — apenas SystemExit com mensagem."""
        from nfe_sync.commands.emissao import cmd_emitir

        args = self._make_args(empresa_sem_endereco)
        with patch("nfe_sync.commands.emissao._carregar", return_value=(empresa_sem_endereco, {})):
            with pytest.raises(SystemExit):
                cmd_emitir(args)
        # Se chegou aqui sem AttributeError, o teste passou
