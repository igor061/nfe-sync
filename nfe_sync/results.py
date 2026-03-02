from dataclasses import dataclass, field


@dataclass(frozen=True, slots=True)
class Documento:
    nsu: str
    schema: str
    nome: str | None = None
    chave: str | None = None
    xml: str | None = None
    erro: str | None = None  # None = sucesso, str = descrição do erro


@dataclass(frozen=True, slots=True)
class ResultadoConsulta:
    situacao: list  # list[dict] — [{status, motivo}]; vem do xml_utils
    xml: str | None
    xml_resposta: str


@dataclass(frozen=True, slots=True)
class ResultadoDfeChave:
    sucesso: bool
    status: str | None
    motivo: str | None
    documentos: list  # list[Documento]
    xml_resposta: str
    xml_cancelamento: str | None


@dataclass(frozen=True, slots=True)
class ResultadoDistribuicao:
    sucesso: bool
    status: str | None
    motivo: str | None
    ultimo_nsu: int
    max_nsu: int
    documentos: list  # list[Documento]
    xmls_resposta: list  # list[str]
    estado: dict  # estado mutável; frozen impede re-atribuição do campo, não mutação


@dataclass(frozen=True, slots=True)
class ResultadoEmissao:
    sucesso: bool
    status: str | None
    motivo: str | None
    protocolo: str | None
    chave: str | None
    xml: str | None
    xml_resposta: str | None
    erros: list  # list[dict]


@dataclass(frozen=True, slots=True)
class ResultadoManifestacao:
    resultados: list  # list[dict]
    protocolo: str | None
    xml: str
    xml_resposta: str


@dataclass(frozen=True, slots=True)
class ResultadoInutilizacao:
    sucesso: bool  # True se algum cStat == "102"
    resultados: list  # list[dict]
    protocolo: str | None
    xml: str
    xml_resposta: str


@dataclass(frozen=True, slots=True)
class ResultadoCancelamento:
    sucesso: bool        # True se cStat in ("135", "136")
    resultados: list     # list[dict] de extract_status_motivo
    protocolo: str | None
    xml: str
    xml_resposta: str
