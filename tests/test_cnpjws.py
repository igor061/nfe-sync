"""Testes para apis/cnpjws.py — Issues #46, #54."""
from nfe_sync.apis.cnpjws import CnpjwsEmpresa

DADOS_API = {
    "razao_social": "EMPRESA TESTE LTDA",
    "estabelecimento": {
        "cnpj": "99999999000191",
        "nome_fantasia": "EMPRESA TESTE",
        "situacao_cadastral": "Ativa",
        "data_inicio_atividade": "2000-01-01",
        "tipo_logradouro": "RUA",
        "logradouro": "EXEMPLO",
        "numero": "100",
        "complemento": "",
        "bairro": "CENTRO",
        "cidade": {
            "id": 5564,
            "nome": "SAO PAULO",
            "ibge_id": 3550308,
            "siafi_id": "7107",
        },
        "estado": {"sigla": "SP"},
        "cep": "01310100",
        "atividade_principal": {"id": 4783101, "descricao": "Comercio varejista"},
        "inscricoes_estaduais": [],
    },
}

DADOS_SEM_IBGE = {
    "razao_social": "EMPRESA TESTE LTDA",
    "estabelecimento": {
        "cnpj": "99999999000191",
        "nome_fantasia": "",
        "situacao_cadastral": "Ativa",
        "data_inicio_atividade": "2000-01-01",
        "tipo_logradouro": "",
        "logradouro": "RUA EXEMPLO",
        "numero": "100",
        "complemento": "",
        "bairro": "CENTRO",
        "cidade": {"id": 5564, "nome": "SAO PAULO"},  # sem ibge_id
        "estado": {"sigla": "SP"},
        "cep": "01310100",
        "atividade_principal": {"id": 0, "descricao": ""},
        "inscricoes_estaduais": [],
    },
}


class TestCnpjwsFromApi:
    """Issue #46: cod_municipio deve ser extraído do ibge_id da API."""

    def test_cod_municipio_extraido_do_ibge_id(self):
        empresa = CnpjwsEmpresa.from_api(DADOS_API)
        assert empresa.endereco.cod_municipio == "3550308"

    def test_cod_municipio_vazio_sem_ibge_id(self):
        empresa = CnpjwsEmpresa.from_api(DADOS_SEM_IBGE)
        assert empresa.endereco.cod_municipio == ""

    def test_municipio_extraido_do_nome(self):
        empresa = CnpjwsEmpresa.from_api(DADOS_API)
        assert empresa.endereco.municipio == "SAO PAULO"


class TestSalvarIniComplemento:
    """Issue #54: complemento com espaços múltiplos deve ser normalizado no _salvar_ini."""

    def test_complemento_espacos_multiplos_normalizado(self, tmp_path):
        import configparser
        from unittest.mock import MagicMock, patch
        from nfe_sync.apis.cli import _salvar_ini

        empresa = MagicMock()
        empresa.cnpj = "99999999000191"
        empresa.razao_social = "EMPRESA TESTE"
        empresa.nome_fantasia = ""
        empresa.cnae_fiscal = 0
        empresa.inscricoes_estaduais = []
        empresa.endereco.logradouro = "RUA EXEMPLO"
        empresa.endereco.numero = "100"
        empresa.endereco.complemento = "QUADRA01                  LOTE  01                  LOJA  259"
        empresa.endereco.bairro = "CENTRO"
        empresa.endereco.municipio = "SAO PAULO"
        empresa.endereco.cod_municipio = "3550308"
        empresa.endereco.uf = "SP"
        empresa.endereco.cep = "01310100"

        ini_path = str(tmp_path / "test.ini")
        with patch("nfe_sync.apis.cli.INI_FILE", ini_path):
            _salvar_ini(empresa, "SUL")

        cfg = configparser.ConfigParser()
        cfg.read(ini_path)
        complemento = cfg.get("SUL", "complemento")
        assert "  " not in complemento  # sem espaços duplos
        assert complemento == "QUADRA01 LOTE 01 LOJA 259"

    def test_complemento_vazio_permanece_vazio(self, tmp_path):
        from unittest.mock import MagicMock, patch
        from nfe_sync.apis.cli import _salvar_ini
        import configparser

        empresa = MagicMock()
        empresa.cnpj = "99999999000191"
        empresa.razao_social = "EMPRESA TESTE"
        empresa.nome_fantasia = ""
        empresa.cnae_fiscal = 0
        empresa.inscricoes_estaduais = []
        empresa.endereco.logradouro = "RUA EXEMPLO"
        empresa.endereco.numero = "100"
        empresa.endereco.complemento = ""
        empresa.endereco.bairro = "CENTRO"
        empresa.endereco.municipio = "SAO PAULO"
        empresa.endereco.cod_municipio = "3550308"
        empresa.endereco.uf = "SP"
        empresa.endereco.cep = "01310100"

        ini_path = str(tmp_path / "test.ini")
        with patch("nfe_sync.apis.cli.INI_FILE", ini_path):
            _salvar_ini(empresa, "SUL")

        cfg = configparser.ConfigParser()
        cfg.read(ini_path)
        assert cfg.get("SUL", "complemento") == ""
