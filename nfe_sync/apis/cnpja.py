import requests
from pydantic import BaseModel, Field

from ..exceptions import NfeConfigError


class CnpjaEndereco(BaseModel, extra="allow"):
    logradouro: str = Field(default="", alias="street")
    numero: str = Field(default="", alias="number")
    bairro: str = Field(default="", alias="district")
    municipio: str = Field(default="", alias="municipality")
    uf: str = Field(default="", alias="state")
    cep: str = Field(default="", alias="zip")
    complemento: str = Field(default="", alias="details")


class CnpjaSocio(BaseModel, extra="allow"):
    nome: str = Field(default="", alias="name")
    tipo: str = Field(default="", alias="type")
    qualificacao: str = Field(default="", alias="role")


class CnpjaEmpresa(BaseModel, extra="allow"):
    cnpj: str = Field(default="", alias="taxId")
    razao_social: str = Field(default="", alias="company")
    nome_fantasia: str = Field(default="", alias="alias")
    data_abertura: str = Field(default="", alias="founded")
    situacao: str = Field(default="", alias="statusDate")
    endereco: CnpjaEndereco = Field(default_factory=CnpjaEndereco, alias="address")
    socios: list[CnpjaSocio] = Field(default_factory=list, alias="members")


def consultar(cnpj: str, config: dict, simples: bool = False) -> CnpjaEmpresa:
    base_url = config.get("base_url")
    headers = config.get("headers", {})

    if not base_url:
        raise NfeConfigError("base_url nao configurada para CNPJa.")
    if not headers.get("Authorization"):
        raise NfeConfigError("Authorization header nao configurado para CNPJa.")

    cnpj_limpo = cnpj.replace(".", "").replace("/", "").replace("-", "")
    url = f"{base_url}/office/{cnpj_limpo}"

    params = {}
    if simples:
        params["simples"] = "true"

    resp = requests.get(url, headers=headers, params=params, timeout=30)
    resp.raise_for_status()

    return CnpjaEmpresa.model_validate(resp.json())
