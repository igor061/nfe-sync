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

INI_COM_ENDERECO = INI_COMPLETO + """\
logradouro = RUA EXEMPLO
numero = 100
complemento = SALA 01
bairro = CENTRO
municipio = SAO PAULO
cod_municipio = 3550308
endereco_uf = SP
cep = 01310100
"""

INI_SEM_COD_MUNICIPIO = INI_COMPLETO + """\
logradouro = RUA EXEMPLO
numero = 100
bairro = CENTRO
municipio = SAO PAULO
cod_municipio =
cep = 01310100
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


class TestCarregarEndereco:
    """Issue #44: config.py deve carregar campos de endereço do INI."""

    def test_endereco_carregado_quando_completo(self, tmp_path):
        ini = tmp_path / "test.ini"
        ini.write_text(INI_COM_ENDERECO)
        emp = carregar_empresas(str(ini))["SUL"]
        end = emp.emitente.endereco
        assert end is not None
        assert end.logradouro == "RUA EXEMPLO"
        assert end.bairro == "CENTRO"
        assert end.municipio == "SAO PAULO"
        assert end.cod_municipio == "3550308"
        assert end.cep == "01310100"
        assert end.uf == "SP"

    def test_endereco_none_quando_sem_ini(self, tmp_path):
        ini = tmp_path / "test.ini"
        ini.write_text(INI_MINIMO)
        emp = carregar_empresas(str(ini))["SUL"]
        assert emp.emitente.endereco is None

    def test_endereco_none_quando_cod_municipio_vazio(self, tmp_path):
        """Sem cod_municipio, endereco não é construído (campo obrigatório para SEFAZ)."""
        ini = tmp_path / "test.ini"
        ini.write_text(INI_SEM_COD_MUNICIPIO)
        emp = carregar_empresas(str(ini))["SUL"]
        assert emp.emitente.endereco is None


class TestParseHomologacao:
    @pytest.mark.parametrize("valor", ["true", "1", "sim", "True", "SIM"])
    def test_parse_homologacao_true(self, valor):
        assert _parse_homologacao(valor) is True

    @pytest.mark.parametrize("valor", ["false", "0", "nao", "False", "NAO"])
    def test_parse_homologacao_false(self, valor):
        assert _parse_homologacao(valor) is False
