import json

import pytest
from nfe_sync.apis.config import carregar_apis, get_api_config
from nfe_sync.apis.cnpja import CnpjaEmpresa, CnpjaSocio, consultar
from nfe_sync.apis.exceptions import ApiConfigError


CNPJA_RESPONSE = {
    "taxId": "33000167000101",
    "alias": "Petrobras - Edise",
    "founded": "1966-09-28",
    "company": {
        "name": "PETROLEO BRASILEIRO S.A. PETROBRAS",
        "members": [
            {
                "person": {
                    "name": "JOAO SILVA",
                    "type": "NATURAL",
                },
                "role": {
                    "id": 10,
                    "text": "Diretor",
                },
            }
        ],
    },
    "status": {
        "id": 2,
        "text": "Ativa",
    },
    "mainActivity": {
        "id": 600001,
        "text": "Extracao de petroleo e gas natural",
    },
    "address": {
        "street": "AV REPUBLICA DO CHILE",
        "number": "65",
        "district": "CENTRO",
        "city": "RIO DE JANEIRO",
        "state": "RJ",
        "zip": "20031912",
        "details": None,
    },
}


class TestCnpjaEmpresa:
    def test_parse_resposta_completa(self):
        empresa = CnpjaEmpresa.from_api(CNPJA_RESPONSE)
        assert empresa.cnpj == "33000167000101"
        assert empresa.razao_social == "PETROLEO BRASILEIRO S.A. PETROBRAS"
        assert empresa.nome_fantasia == "Petrobras - Edise"
        assert empresa.data_abertura == "1966-09-28"
        assert empresa.situacao.texto == "Ativa"
        assert empresa.atividade_principal.texto == "Extracao de petroleo e gas natural"
        assert empresa.endereco.cidade == "RIO DE JANEIRO"
        assert empresa.endereco.uf == "RJ"
        assert empresa.endereco.cep == "20031912"
        assert len(empresa.socios) == 1
        assert empresa.socios[0].nome == "JOAO SILVA"
        assert empresa.socios[0].qualificacao == "Diretor"

    def test_parse_resposta_minima(self):
        empresa = CnpjaEmpresa.from_api({"taxId": "12345678000199"})
        assert empresa.cnpj == "12345678000199"
        assert empresa.razao_social == ""
        assert empresa.socios == []

    def test_campos_extras_permitidos(self):
        dados = {**CNPJA_RESPONSE, "campoExtra": "valor"}
        empresa = CnpjaEmpresa.from_api(dados)
        assert empresa.cnpj == "33000167000101"


class TestCnpjaSocio:
    def test_from_api(self):
        membro = {
            "person": {"name": "Maria", "type": "NATURAL"},
            "role": {"text": "Presidente"},
        }
        socio = CnpjaSocio.from_api(membro)
        assert socio.nome == "Maria"
        assert socio.tipo == "NATURAL"
        assert socio.qualificacao == "Presidente"

    def test_from_api_vazio(self):
        socio = CnpjaSocio.from_api({})
        assert socio.nome == ""
        assert socio.qualificacao == ""


class TestApisConfig:
    def test_carregar_apis_ok(self, tmp_path):
        cfg = tmp_path / "apis.json"
        cfg.write_text(json.dumps({"cnpja": {"base_url": "https://api.cnpja.com"}}))
        resultado = carregar_apis(str(cfg))
        assert "cnpja" in resultado

    def test_carregar_apis_arquivo_nao_existe(self):
        with pytest.raises(ApiConfigError, match="nao encontrado"):
            carregar_apis("/tmp/nao_existe_abc123.json")

    def test_get_api_config_ok(self, tmp_path):
        cfg = tmp_path / "apis.json"
        cfg.write_text(json.dumps({"cnpja": {"base_url": "https://api.cnpja.com"}}))
        resultado = get_api_config("cnpja", str(cfg))
        assert resultado["base_url"] == "https://api.cnpja.com"

    def test_get_api_config_nao_configurada(self, tmp_path):
        cfg = tmp_path / "apis.json"
        cfg.write_text(json.dumps({"outra": {}}))
        with pytest.raises(ApiConfigError, match="nao configurada"):
            get_api_config("cnpja", str(cfg))


class TestConsultar:
    def test_sem_config_usa_api_publica(self, monkeypatch):
        def mock_get(url, **kwargs):
            assert "open.cnpja.com" in url

            class Resp:
                def raise_for_status(self): pass
                def json(self): return CNPJA_RESPONSE
            return Resp()

        import nfe_sync.apis.cnpja as mod
        monkeypatch.setattr(mod.requests, "get", mock_get)
        empresa = consultar("33000167000101")
        assert empresa.cnpj == "33000167000101"

    def test_com_config_usa_base_url_customizada(self, monkeypatch):
        def mock_get(url, **kwargs):
            assert "api.cnpja.com" in url
            assert kwargs["headers"]["Authorization"] == "minha-key"

            class Resp:
                def raise_for_status(self): pass
                def json(self): return CNPJA_RESPONSE
            return Resp()

        import nfe_sync.apis.cnpja as mod
        monkeypatch.setattr(mod.requests, "get", mock_get)

        config = {"base_url": "https://api.cnpja.com", "headers": {"Authorization": "minha-key"}}
        empresa = consultar("33000167000101", config)
        assert empresa.cnpj == "33000167000101"
