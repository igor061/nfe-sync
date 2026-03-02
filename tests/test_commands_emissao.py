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
    """Issues #45, #50, #51, #52: --destinatario com ajuste automático de CFOP/indicadores."""

    ENDERECO_SP = Endereco(
        logradouro="RUA EXEMPLO",
        numero="100",
        bairro="CENTRO",
        municipio="SAO PAULO",
        cod_municipio="3550308",
        uf="SP",
        cep="01310100",
    )

    ENDERECO_GO = Endereco(
        logradouro="RUA EXEMPLO",
        numero="200",
        bairro="CENTRO",
        municipio="GOIANIA",
        cod_municipio="5208707",
        uf="GO",
        cep="74000000",
    )

    # manter retrocompatibilidade com testes existentes
    ENDERECO = ENDERECO_SP

    def _make_empresa(self, nome, cnpj, com_endereco=True, uf_endereco="SP", inscricao_estadual=""):
        endereco = (self.ENDERECO_GO if uf_endereco == "GO" else self.ENDERECO_SP) if com_endereco else None
        return EmpresaConfig(
            nome=nome,
            certificado=Certificado(path="/tmp/cert.pfx", senha="123456"),
            emitente=Emitente(
                cnpj=cnpj,
                inscricao_estadual=inscricao_estadual,
                endereco=endereco,
            ),
            uf=uf_endereco.lower(),
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


class TestCmdEmitirIndicadores:
    """Issues #50, #51, #52: indicador_destino, indicador_ie e CFOP ajustados automaticamente."""

    ENDERECO_SP = Endereco(
        logradouro="RUA EXEMPLO", numero="100", bairro="CENTRO",
        municipio="SAO PAULO", cod_municipio="3550308", uf="SP", cep="01310100",
    )
    ENDERECO_GO = Endereco(
        logradouro="RUA EXEMPLO", numero="200", bairro="CENTRO",
        municipio="GOIANIA", cod_municipio="5208707", uf="GO", cep="74000000",
    )

    def _make_empresa(self, nome, cnpj, endereco, inscricao_estadual=""):
        return EmpresaConfig(
            nome=nome,
            certificado=Certificado(path="/tmp/cert.pfx", senha="123456"),
            emitente=Emitente(cnpj=cnpj, inscricao_estadual=inscricao_estadual, endereco=endereco),
            uf=endereco.uf.lower(),
            homologacao=True,
        )

    def _make_args(self, destinatario=None):
        args = MagicMock()
        args.empresa = "SUL"
        args.serie = "1"
        args.destinatario = destinatario
        args.homologacao = True
        args.producao = False
        return args

    def test_intraestadual_cfop_5102_indicador_1(self, capsys):
        """Mesma UF → CFOP 5102, indicador_destino 1."""
        from nfe_sync.commands.emissao import cmd_emitir
        from nfe_sync.results import ResultadoEmissao

        emitente = self._make_empresa("SUL", "99999999000191", self.ENDERECO_SP, "111111111111")
        dest = self._make_empresa("DEST", "99999999000191", self.ENDERECO_SP, "222222222222")

        resultado_mock = ResultadoEmissao(
            sucesso=False, status="100", motivo="ok", protocolo=None,
            chave=None, xml=None, xml_resposta=None, erros=[{"status": "x", "motivo": "y"}],
        )

        capturado = {}
        def fake_emitir(empresa, serie, numero_nf, dados):
            capturado["dados"] = dados
            return resultado_mock

        with patch("nfe_sync.commands.emissao._carregar", return_value=(emitente, {})), \
             patch("nfe_sync.commands.emissao.carregar_empresas",
                   return_value={"SUL": emitente, "DEST": dest}), \
             patch("nfe_sync.emissao.emitir", fake_emitir):
            with pytest.raises(SystemExit):
                cmd_emitir(self._make_args(destinatario="DEST"))

        dados = capturado["dados"]
        assert dados.indicador_destino == 1
        assert dados.produtos[0].cfop == "5102"
        assert dados.destinatario.indicador_ie == 1

    def test_interestadual_cfop_6102_indicador_2(self, capsys):
        """UFs diferentes → CFOP 6102, indicador_destino 2."""
        from nfe_sync.commands.emissao import cmd_emitir
        from nfe_sync.results import ResultadoEmissao

        emitente = self._make_empresa("SUL", "99999999000191", self.ENDERECO_SP, "111111111111")
        dest = self._make_empresa("DEST", "99999999000191", self.ENDERECO_GO, "333333333333")

        resultado_mock = ResultadoEmissao(
            sucesso=False, status="100", motivo="ok", protocolo=None,
            chave=None, xml=None, xml_resposta=None, erros=[{"status": "x", "motivo": "y"}],
        )

        capturado = {}
        def fake_emitir(empresa, serie, numero_nf, dados):
            capturado["dados"] = dados
            return resultado_mock

        with patch("nfe_sync.commands.emissao._carregar", return_value=(emitente, {})), \
             patch("nfe_sync.commands.emissao.carregar_empresas",
                   return_value={"SUL": emitente, "DEST": dest}), \
             patch("nfe_sync.emissao.emitir", fake_emitir):
            with pytest.raises(SystemExit):
                cmd_emitir(self._make_args(destinatario="DEST"))

        dados = capturado["dados"]
        assert dados.indicador_destino == 2
        assert dados.produtos[0].cfop == "6102"
        assert dados.destinatario.indicador_ie == 1

    def test_destinatario_sem_ie_indicador_ie_9(self, capsys):
        """Destinatário sem inscricao_estadual → indicador_ie 9."""
        from nfe_sync.commands.emissao import cmd_emitir
        from nfe_sync.results import ResultadoEmissao

        emitente = self._make_empresa("SUL", "99999999000191", self.ENDERECO_SP, "111111111111")
        dest = self._make_empresa("DEST", "99999999000191", self.ENDERECO_SP, "")  # sem IE

        resultado_mock = ResultadoEmissao(
            sucesso=False, status="100", motivo="ok", protocolo=None,
            chave=None, xml=None, xml_resposta=None, erros=[{"status": "x", "motivo": "y"}],
        )

        capturado = {}
        def fake_emitir(empresa, serie, numero_nf, dados):
            capturado["dados"] = dados
            return resultado_mock

        with patch("nfe_sync.commands.emissao._carregar", return_value=(emitente, {})), \
             patch("nfe_sync.commands.emissao.carregar_empresas",
                   return_value={"SUL": emitente, "DEST": dest}), \
             patch("nfe_sync.emissao.emitir", fake_emitir):
            with pytest.raises(SystemExit):
                cmd_emitir(self._make_args(destinatario="DEST"))

        assert capturado["dados"].destinatario.indicador_ie == 9
