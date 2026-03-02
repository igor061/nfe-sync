"""Testes para apis/cnpjws.py — Issue #46: cod_municipio extraído do ibge_id."""
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
