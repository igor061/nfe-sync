import pytest
from nfe_sync.config import carregar_empresas, _parse_homologacao
from nfe_sync.exceptions import NfeConfigError


INI_COMPLETO = """\
[SUL]
path = /tmp/cert.pfx
senha = 123456
uf = go
homologacao = true
cnpj = 10755237000136
razao_social = RM VALPARAISO JOIAS LTDA
nome_fantasia = CORALLI JOIAS
inscricao_estadual = 104452420
cnae_fiscal = 4783101
regime_tributario = 1
logradouro = ROD BR 040 KM 12 GLEBA F
numero = SN
complemento = QUADRA01 LOTE 01 LOJA 259
bairro = PARQUE ESPLANADA III
municipio = VALPARAISO DE GOIAS
cod_municipio = 5221858
endereco_uf = GO
cep = 72876902
"""


class TestCarregarEmpresas:
    def test_carregar_config_valido(self, tmp_path):
        ini = tmp_path / "test.ini"
        ini.write_text(INI_COMPLETO)
        empresas = carregar_empresas(str(ini))
        assert "SUL" in empresas
        emp = empresas["SUL"]
        assert emp.nome == "SUL"
        assert emp.certificado.path == "/tmp/cert.pfx"
        assert emp.certificado.senha == "123456"
        assert emp.uf == "go"
        assert emp.homologacao is True
        assert emp.emitente.cnpj == "10755237000136"
        assert emp.emitente.endereco.municipio == "VALPARAISO DE GOIAS"

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
