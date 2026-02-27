import requests
from pydantic import BaseModel, Field


BASE_URL_PUBLICA = "https://open.cnpja.com"


class CnpjaEndereco(BaseModel, extra="allow"):
    logradouro: str = Field(default="", alias="street")
    numero: str = Field(default="", alias="number")
    bairro: str = Field(default="", alias="district")
    cidade: str = Field(default="", alias="city")
    uf: str = Field(default="", alias="state")
    cep: str = Field(default="", alias="zip")
    complemento: str | None = Field(default=None, alias="details")


class CnpjaStatus(BaseModel, extra="allow"):
    id: int = 0
    texto: str = Field(default="", alias="text")


class CnpjaAtividade(BaseModel, extra="allow"):
    id: int = 0
    texto: str = Field(default="", alias="text")

    @property
    def cnae(self) -> str:
        s = str(self.id).zfill(7)
        return f"{s[:2]}.{s[2:4]}-{s[4]}-{s[5:]}"


class CnpjaSocio(BaseModel, extra="allow"):
    nome: str = ""
    tipo: str = ""
    qualificacao: str = ""

    @classmethod
    def from_api(cls, membro: dict) -> "CnpjaSocio":
        pessoa = membro.get("person", {})
        cargo = membro.get("role", {})
        return cls(
            nome=pessoa.get("name", ""),
            tipo=pessoa.get("type", ""),
            qualificacao=cargo.get("text", ""),
        )


class CnpjaEmpresa(BaseModel, extra="allow"):
    cnpj: str = Field(default="", alias="taxId")
    razao_social: str = ""
    nome_fantasia: str = Field(default="", alias="alias")
    data_abertura: str = Field(default="", alias="founded")
    situacao: CnpjaStatus = Field(default_factory=CnpjaStatus, alias="status")
    atividade_principal: CnpjaAtividade = Field(default_factory=CnpjaAtividade, alias="mainActivity")
    atividades_secundarias: list[CnpjaAtividade] = Field(default_factory=list, alias="sideActivities")
    endereco: CnpjaEndereco = Field(default_factory=CnpjaEndereco, alias="address")
    socios: list[CnpjaSocio] = Field(default_factory=list)

    @classmethod
    def from_api(cls, dados: dict) -> "CnpjaEmpresa":
        empresa_obj = dados.get("company", {})
        membros = empresa_obj.get("members", [])
        socios = [CnpjaSocio.from_api(m) for m in membros]

        return cls.model_validate({
            **dados,
            "razao_social": empresa_obj.get("name", ""),
            "socios": [s.model_dump() for s in socios],
        })


def consultar(cnpj: str, config: dict | None = None) -> CnpjaEmpresa:
    cnpj_limpo = cnpj.replace(".", "").replace("/", "").replace("-", "")

    if config and config.get("base_url"):
        base_url = config["base_url"]
        headers = config.get("headers", {})
    else:
        base_url = BASE_URL_PUBLICA
        headers = {}

    url = f"{base_url}/office/{cnpj_limpo}"
    resp = requests.get(url, headers=headers, timeout=30)
    resp.raise_for_status()

    return CnpjaEmpresa.from_api(resp.json())
