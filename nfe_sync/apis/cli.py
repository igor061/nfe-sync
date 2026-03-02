import argparse
import configparser
import re
import sys

from .exceptions import ApiConfigError

INI_FILE = "nfe-sync.conf.ini"


def cmd_cnpja(args):
    from .cnpja import consultar

    config = None
    try:
        from .config import get_api_config
        config = get_api_config("cnpja")
    except ApiConfigError:
        pass

    empresa = consultar(args.cnpj, config)

    print(f"CNPJ: {empresa.cnpj}")
    print(f"Razao Social: {empresa.razao_social}")
    print(f"Nome Fantasia: {empresa.nome_fantasia}")
    print(f"Data Abertura: {empresa.data_abertura}")
    print(f"Situacao: {empresa.situacao.texto}")
    ap = empresa.atividade_principal
    print(f"CNAE Principal: {ap.cnae} - {ap.texto}")
    if empresa.atividades_secundarias:
        print("CNAEs Secundarios:")
        for a in empresa.atividades_secundarias:
            print(f"  {a.cnae} - {a.texto}")
    end = empresa.endereco
    print(f"Endereco: {end.logradouro}, {end.numero} - {end.bairro}")
    print(f"Cidade: {end.cidade} / {end.uf} - CEP {end.cep}")
    if empresa.socios:
        print("Socios:")
        for s in empresa.socios:
            print(f"  {s.nome} ({s.tipo}) - {s.qualificacao}")


def _salvar_ini(empresa, nome_secao: str):
    cfg = configparser.ConfigParser(inline_comment_prefixes=("#", ";"))
    cfg.read(INI_FILE)

    acao = "Atualizada" if cfg.has_section(nome_secao) else "Criada"
    if not cfg.has_section(nome_secao):
        cfg.add_section(nome_secao)

    end = empresa.endereco
    ie_ativa = next((ie for ie in empresa.inscricoes_estaduais if ie.ativo), None)

    # preserva path e senha se a secao ja existia
    if not cfg.get(nome_secao, "path", fallback=""):
        cfg.set(nome_secao, "path", "certs/certificado.pfx")
    if not cfg.get(nome_secao, "senha", fallback=""):
        cfg.set(nome_secao, "senha", "")
    if not cfg.get(nome_secao, "homologacao", fallback=""):
        cfg.set(nome_secao, "homologacao", "true")

    cfg.set(nome_secao, "uf", end.uf.lower())
    cfg.set(nome_secao, "cnpj", empresa.cnpj)
    cfg.set(nome_secao, "razao_social", empresa.razao_social)
    cfg.set(nome_secao, "nome_fantasia", empresa.nome_fantasia)
    cfg.set(nome_secao, "inscricao_estadual", ie_ativa.inscricao_estadual if ie_ativa else "")
    cfg.set(nome_secao, "cnae_fiscal", str(empresa.cnae_fiscal))
    cfg.set(nome_secao, "regime_tributario", cfg.get(nome_secao, "regime_tributario", fallback="1"))
    cfg.set(nome_secao, "logradouro", end.logradouro)
    cfg.set(nome_secao, "numero", end.numero)
    cfg.set(nome_secao, "complemento", re.sub(r'\s+', ' ', end.complemento or "").strip())
    cfg.set(nome_secao, "bairro", end.bairro)
    cfg.set(nome_secao, "municipio", end.municipio)
    cfg.set(nome_secao, "cod_municipio", end.cod_municipio)
    cfg.set(nome_secao, "endereco_uf", end.uf.upper())
    cfg.set(nome_secao, "cep", str(end.cep))

    with open(INI_FILE, "w") as f:
        cfg.write(f)

    print(f"{acao} secao [{nome_secao}] em {INI_FILE}")
    if not cfg.get(nome_secao, "path", fallback=""):
        print(f"  Atenção: preencha 'path' e 'senha' do certificado em {INI_FILE}")


def cmd_cnpjws(args):
    from .cnpjws import consultar

    empresa = consultar(args.cnpj)

    print(f"CNPJ: {empresa.cnpj}")
    print(f"Razao Social: {empresa.razao_social}")
    print(f"Nome Fantasia: {empresa.nome_fantasia}")
    print(f"Situacao: {empresa.situacao_cadastral}")
    print(f"Inicio Atividade: {empresa.data_inicio_atividade}")
    print(f"CNAE: {empresa.cnae_fiscal} - {empresa.cnae_fiscal_descricao}")
    end = empresa.endereco
    print(f"Endereco: {end.logradouro}, {end.numero} - {end.bairro}")
    print(f"Cidade: {end.municipio} / {end.uf} - CEP {end.cep}")
    if empresa.inscricoes_estaduais:
        print("Inscricoes Estaduais:")
        for ie in empresa.inscricoes_estaduais:
            ativo = "ativa" if ie.ativo else "inativa"
            print(f"  {ie.uf}: {ie.inscricao_estadual} ({ativo})")

    if args.salvar_ini:
        _salvar_ini(empresa, args.salvar_ini)


def cli(argv=None):
    parser = argparse.ArgumentParser(
        prog="api_cli",
        description="Consulta de dados cadastrais de CNPJ via APIs publicas.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Exemplos de uso:\n"
            "  api_cli cnpja  33000167000101\n"
            "  api_cli cnpjws 33000167000101\n"
            f"  api_cli cnpjws 33000167000101 --salvar-ini MINHAEMPRESA"
        ),
    )
    sub = parser.add_subparsers(dest="comando", required=True)

    # cnpja
    p_cnpja = sub.add_parser(
        "cnpja",
        help="Consultar CNPJ via CNPJa — dados cadastrais, CNAE, socios, endereco",
        description="Consulta dados cadastrais de um CNPJ usando a API open.cnpja.com.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="Exemplo:\n  api_cli cnpja 33000167000101",
    )
    p_cnpja.add_argument("cnpj", help="CNPJ a consultar (com ou sem formatacao)")
    p_cnpja.set_defaults(func=cmd_cnpja)

    # cnpjws
    p_cnpjws = sub.add_parser(
        "cnpjws",
        help="Consultar CNPJ via publica.cnpj.ws — inclui inscricoes estaduais por UF",
        description="Consulta dados cadastrais de um CNPJ usando a API publica.cnpj.ws, incluindo inscricoes estaduais.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Exemplos:\n"
            "  api_cli cnpjws 33000167000101\n"
            f"  api_cli cnpjws 33000167000101 --salvar-ini MINHAEMPRESA"
        ),
    )
    p_cnpjws.add_argument("cnpj", help="CNPJ a consultar (com ou sem formatacao)")
    p_cnpjws.add_argument(
        "--salvar-ini",
        metavar="NOME",
        default=None,
        help=f"Cria ou atualiza secao [{INI_FILE}] com os dados consultados (preenche automaticamente os campos cadastrais)",
    )
    p_cnpjws.set_defaults(func=cmd_cnpjws)

    args = parser.parse_args(argv)

    try:
        args.func(args)
    except ApiConfigError as e:
        print(f"Erro de configuracao: {e}")
        sys.exit(1)


if __name__ == "__main__":
    cli()
