import pytest
from nfe_sync.config import carregar_empresas, _parse_homologacao
from nfe_sync.exceptions import NfeConfigError


INI_MINIMO = """\
[SUL]
path = /tmp/cert.pfx
senha = 123456
uf = sp
homologacao = true
cnpj = 99999999000191
"""

INI_COMPLETO = INI_MINIMO + """\
razao_social = EMPRESA TESTE LTDA
nome_fantasia = EMPRESA TESTE
inscricao_estadual = 111111111111
cnae_fiscal = 4783101
regime_tributario = 1
"""


class TestCarregarEmpresas:
    def test_carregar_config_minimo(self, tmp_path):
        ini = tmp_path / "test.ini"
        ini.write_text(INI_MINIMO)
        empresas = carregar_empresas(str(ini))
        assert "SUL" in empresas
        emp = empresas["SUL"]
        assert emp.nome == "SUL"
        assert emp.certificado.path == "/tmp/cert.pfx"
        assert emp.certificado.senha == "123456"
        assert emp.uf == "sp"
        assert emp.homologacao is True
        assert emp.emitente.cnpj == "99999999000191"

    def test_carregar_config_completo(self, tmp_path):
        ini = tmp_path / "test.ini"
        ini.write_text(INI_COMPLETO)
        emp = carregar_empresas(str(ini))["SUL"]
        assert emp.emitente.razao_social == "EMPRESA TESTE LTDA"
        assert emp.emitente.inscricao_estadual == "111111111111"

    def test_carregar_config_vazio(self, tmp_path):
        ini = tmp_path / "vazio.ini"
        ini.write_text("")
        with pytest.raises(NfeConfigError):
            carregar_empresas(str(ini))

    def test_carregar_config_campo_faltando(self, tmp_path):
        ini = tmp_path / "incompleto.ini"
        ini.write_text("[SUL]\npath = /tmp/cert.pfx\nsenha = 123456\n")
        with pytest.raises(NfeConfigError, match="Campos obrigatorios faltando"):
            carregar_empresas(str(ini))


class TestParseHomologacao:
    @pytest.mark.parametrize("valor", ["true", "1", "sim", "True", "SIM"])
    def test_parse_homologacao_true(self, valor):
        assert _parse_homologacao(valor) is True

    @pytest.mark.parametrize("valor", ["false", "0", "nao", "False", "NAO"])
    def test_parse_homologacao_false(self, valor):
        assert _parse_homologacao(valor) is False
