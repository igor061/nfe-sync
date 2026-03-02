import requests
from pydantic import BaseModel, Field


BASE_URL = "https://publica.cnpj.ws/cnpj"


class CnpjwsEndereco(BaseModel, extra="allow"):
    logradouro: str = ""
    numero: str = ""
    complemento: str = ""
    bairro: str = ""
    municipio: str = ""
    cod_municipio: str = ""
    uf: str = ""
    cep: str = ""


class CnpjwsInscricaoEstadual(BaseModel, extra="allow"):
    inscricao_estadual: str = ""
    ativo: bool = False
    uf: str = ""


class CnpjwsEmpresa(BaseModel, extra="allow"):
    cnpj: str = ""
    razao_social: str = ""
    nome_fantasia: str = ""
    situacao_cadastral: str = ""
    data_inicio_atividade: str = ""
    cnae_fiscal: int = 0
    cnae_fiscal_descricao: str = ""
    endereco: CnpjwsEndereco = Field(default_factory=CnpjwsEndereco)
    inscricoes_estaduais: list[CnpjwsInscricaoEstadual] = Field(default_factory=list)

    @classmethod
    def from_api(cls, dados: dict) -> "CnpjwsEmpresa":
        est = dados.get("estabelecimento", {})
        cidade = est.get("cidade", {}) if isinstance(est.get("cidade"), dict) else {}
        municipio = cidade.get("nome", "") or est.get("municipio", "")
        cod_municipio = str(cidade.get("ibge_id", "")) if cidade.get("ibge_id") else ""
        estado = est.get("estado", {}).get("sigla", "") if isinstance(est.get("estado"), dict) else est.get("uf", "")
        endereco = CnpjwsEndereco(
            logradouro=f"{est.get('tipo_logradouro', '')} {est.get('logradouro', '')}".strip(),
            numero=est.get("numero", ""),
            complemento=est.get("complemento", ""),
            bairro=est.get("bairro", ""),
            municipio=municipio,
            cod_municipio=cod_municipio,
            uf=estado,
            cep=est.get("cep", ""),
        )
        inscricoes = [
            CnpjwsInscricaoEstadual(
                inscricao_estadual=ie.get("inscricao_estadual", ""),
                ativo=ie.get("ativo", False),
                uf=ie.get("estado", {}).get("sigla", "") if isinstance(ie.get("estado"), dict) else "",
            )
            for ie in est.get("inscricoes_estaduais", [])
        ]
        return cls(
            cnpj=est.get("cnpj", ""),
            razao_social=dados.get("razao_social", ""),
            nome_fantasia=est.get("nome_fantasia", ""),
            situacao_cadastral=est.get("situacao_cadastral", ""),
            data_inicio_atividade=est.get("data_inicio_atividade", ""),
            cnae_fiscal=int(est.get("atividade_principal", {}).get("id", 0) or 0),
            cnae_fiscal_descricao=est.get("atividade_principal", {}).get("descricao", ""),
            endereco=endereco,
            inscricoes_estaduais=inscricoes,
        )


def consultar(cnpj: str) -> CnpjwsEmpresa:
    cnpj_limpo = cnpj.replace(".", "").replace("/", "").replace("-", "")
    url = f"{BASE_URL}/{cnpj_limpo}"
    resp = requests.get(url, timeout=30)
    resp.raise_for_status()
    return CnpjwsEmpresa.from_api(resp.json())
