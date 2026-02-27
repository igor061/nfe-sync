import json

import pytest
from nfe_sync.apis.config import carregar_apis, get_api_config
from nfe_sync.apis.cnpja import CnpjaEmpresa, consultar
from nfe_sync.exceptions import NfeConfigError


CNPJA_RESPONSE = {
    "taxId": "33000167000101",
    "company": "PETROLEO BRASILEIRO S.A. PETROBRAS",
    "alias": "PETROBRAS",
    "founded": "1966-09-28",
    "statusDate": "2005-11-03",
    "address": {
        "street": "AV REPUBLICA DO CHILE",
        "number": "65",
        "district": "CENTRO",
        "municipality": "RIO DE JANEIRO",
        "state": "RJ",
        "zip": "20031912",
    },
    "members": [
        {
            "name": "JOAO SILVA",
            "type": "PERSON",
            "role": "Socio-Administrador",
        }
    ],
}


class TestCnpjaEmpresa:
    def test_parse_resposta_completa(self):
        empresa = CnpjaEmpresa.model_validate(CNPJA_RESPONSE)
        assert empresa.cnpj == "33000167000101"
        assert empresa.nome_fantasia == "PETROBRAS"
        assert empresa.data_abertura == "1966-09-28"
        assert empresa.endereco.municipio == "RIO DE JANEIRO"
        assert empresa.endereco.uf == "RJ"
        assert empresa.endereco.cep == "20031912"
        assert len(empresa.socios) == 1
        assert empresa.socios[0].nome == "JOAO SILVA"
        assert empresa.socios[0].qualificacao == "Socio-Administrador"

    def test_parse_resposta_minima(self):
        empresa = CnpjaEmpresa.model_validate({"taxId": "12345678000199"})
        assert empresa.cnpj == "12345678000199"
        assert empresa.nome_fantasia == ""
        assert empresa.socios == []

    def test_extra_fields_allowed(self):
        data = {**CNPJA_RESPONSE, "campoExtra": "valor"}
        empresa = CnpjaEmpresa.model_validate(data)
        assert empresa.cnpj == "33000167000101"


class TestApisConfig:
    def test_carregar_apis_ok(self, tmp_path):
        cfg = tmp_path / "apis.json"
        cfg.write_text(json.dumps({"cnpja": {"base_url": "https://api.cnpja.com"}}))
        result = carregar_apis(str(cfg))
        assert "cnpja" in result

    def test_carregar_apis_arquivo_nao_existe(self):
        with pytest.raises(NfeConfigError, match="nao encontrado"):
            carregar_apis("/tmp/nao_existe_abc123.json")

    def test_get_api_config_ok(self, tmp_path):
        cfg = tmp_path / "apis.json"
        cfg.write_text(json.dumps({"cnpja": {"base_url": "https://api.cnpja.com"}}))
        result = get_api_config("cnpja", str(cfg))
        assert result["base_url"] == "https://api.cnpja.com"

    def test_get_api_config_nao_configurada(self, tmp_path):
        cfg = tmp_path / "apis.json"
        cfg.write_text(json.dumps({"outra": {}}))
        with pytest.raises(NfeConfigError, match="nao configurada"):
            get_api_config("cnpja", str(cfg))


class TestConsultar:
    def test_config_sem_base_url(self):
        with pytest.raises(NfeConfigError, match="base_url"):
            consultar("33000167000101", {})

    def test_config_sem_authorization(self):
        with pytest.raises(NfeConfigError, match="Authorization"):
            consultar("33000167000101", {"base_url": "https://api.cnpja.com"})
