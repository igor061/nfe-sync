import configparser

from .exceptions import NfeConfigError
from .models import Certificado, Emitente, Endereco, EmpresaConfig


CAMPOS_OBRIGATORIOS = ("path", "senha", "uf", "homologacao", "cnpj")


def _parse_homologacao(valor: str) -> bool:
    return valor.lower() in ("true", "1", "sim")


def _parse_secao(nome: str, secao: configparser.SectionProxy) -> EmpresaConfig:
    faltando = [c for c in CAMPOS_OBRIGATORIOS if not secao.get(c)]
    if faltando:
        raise NfeConfigError(
            f"Campos obrigatorios faltando na secao [{nome}]: {', '.join(faltando)}"
        )

    certificado = Certificado(
        path=secao["path"],
        senha=secao["senha"],
    )

    logradouro = secao.get("logradouro", "")
    bairro = secao.get("bairro", "")
    municipio = secao.get("municipio", "")
    cod_municipio = secao.get("cod_municipio", "")
    cep = secao.get("cep", "")
    endereco_uf = secao.get("endereco_uf", "") or secao.get("uf", "").upper()

    endereco = None
    if logradouro and bairro and municipio and cod_municipio and cep:
        endereco = Endereco(
            logradouro=logradouro,
            numero=secao.get("numero", ""),
            complemento=secao.get("complemento", ""),
            bairro=bairro,
            municipio=municipio,
            cod_municipio=cod_municipio,
            uf=endereco_uf,
            cep=cep,
        )

    emitente = Emitente(
        cnpj=secao["cnpj"],
        razao_social=secao.get("razao_social", ""),
        nome_fantasia=secao.get("nome_fantasia", ""),
        inscricao_estadual=secao.get("inscricao_estadual", ""),
        cnae_fiscal=secao.get("cnae_fiscal", ""),
        regime_tributario=secao.get("regime_tributario", ""),
        endereco=endereco,
    )

    return EmpresaConfig(
        nome=nome,
        certificado=certificado,
        emitente=emitente,
        uf=secao["uf"],
        homologacao=_parse_homologacao(secao["homologacao"]),
    )


def carregar_empresas(config_file: str) -> dict[str, EmpresaConfig]:
    config = configparser.ConfigParser(inline_comment_prefixes=("#", ";"))
    config.read(config_file)
    secoes = config.sections()
    if not secoes:
        raise NfeConfigError(f"Nenhum certificado configurado em {config_file}")

    empresas = {}
    for nome in secoes:
        empresas[nome] = _parse_secao(nome, config[nome])
    return empresas
