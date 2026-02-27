import configparser

from .exceptions import NfeConfigError
from .models import Certificado, Emitente, Endereco, EmpresaConfig


CAMPOS_CERTIFICADO = ("path", "senha")
CAMPOS_OBRIGATORIOS = ("path", "senha", "uf", "homologacao", "cnpj", "razao_social",
                        "nome_fantasia", "inscricao_estadual", "cnae_fiscal",
                        "regime_tributario", "logradouro", "numero", "bairro",
                        "municipio", "cod_municipio", "endereco_uf", "cep")


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

    endereco = Endereco(
        logradouro=secao["logradouro"],
        numero=secao["numero"],
        complemento=secao.get("complemento", ""),
        bairro=secao["bairro"],
        municipio=secao["municipio"],
        cod_municipio=secao["cod_municipio"],
        uf=secao["endereco_uf"],
        cep=secao["cep"],
    )

    emitente = Emitente(
        cnpj=secao["cnpj"],
        razao_social=secao["razao_social"],
        nome_fantasia=secao["nome_fantasia"],
        inscricao_estadual=secao["inscricao_estadual"],
        cnae_fiscal=secao["cnae_fiscal"],
        regime_tributario=secao["regime_tributario"],
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
    config = configparser.ConfigParser()
    config.read(config_file)
    secoes = config.sections()
    if not secoes:
        raise NfeConfigError(f"Nenhum certificado configurado em {config_file}")

    empresas = {}
    for nome in secoes:
        empresas[nome] = _parse_secao(nome, config[nome])
    return empresas
