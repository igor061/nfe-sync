"""Testes para commands/emissao.py — Issues #40, #45."""
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

    def _make_args(self, empresa, destinatario=None):
        args = MagicMock()
        args.empresa = empresa.nome
        args.serie = "1"
        args.destinatario = destinatario
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


class TestCmdEmitirDestinatario:
    """Issue #45: --destinatario permite especificar outra empresa como destinatária."""

    ENDERECO = Endereco(
        logradouro="RUA EXEMPLO",
        numero="100",
        bairro="CENTRO",
        municipio="SAO PAULO",
        cod_municipio="3550308",
        uf="SP",
        cep="01310100",
    )

    def _make_empresa(self, nome, cnpj, com_endereco=True):
        return EmpresaConfig(
            nome=nome,
            certificado=Certificado(path="/tmp/cert.pfx", senha="123456"),
            emitente=Emitente(
                cnpj=cnpj,
                endereco=self.ENDERECO if com_endereco else None,
            ),
            uf="sp",
            homologacao=True,
        )

    def test_destinatario_invalido_exit_1(self, capsys):
        from nfe_sync.commands.emissao import cmd_emitir

        emitente = self._make_empresa("SUL", "99999999000191")
        args = MagicMock()
        args.empresa = "SUL"
        args.serie = "1"
        args.destinatario = "INEXISTENTE"
        args.homologacao = True
        args.producao = False

        with patch("nfe_sync.commands.emissao._carregar", return_value=(emitente, {})), \
             patch("nfe_sync.commands.emissao.carregar_empresas", return_value={"SUL": emitente}):
            with pytest.raises(SystemExit) as exc:
                cmd_emitir(args)

        assert exc.value.code == 1
        assert "INEXISTENTE" in capsys.readouterr().out

    def test_destinatario_sem_endereco_exit_1(self, capsys):
        from nfe_sync.commands.emissao import cmd_emitir

        emitente = self._make_empresa("SUL", "99999999000191")
        dest = self._make_empresa("SRNACIONAL", "99999999000191", com_endereco=False)
        args = MagicMock()
        args.empresa = "SUL"
        args.serie = "1"
        args.destinatario = "SRNACIONAL"
        args.homologacao = True
        args.producao = False

        with patch("nfe_sync.commands.emissao._carregar", return_value=(emitente, {})), \
             patch("nfe_sync.commands.emissao.carregar_empresas",
                   return_value={"SUL": emitente, "SRNACIONAL": dest}):
            with pytest.raises(SystemExit) as exc:
                cmd_emitir(args)

        assert exc.value.code == 1
        out = capsys.readouterr().out
        assert "SRNACIONAL" in out
        assert "endereco" in out.lower()
