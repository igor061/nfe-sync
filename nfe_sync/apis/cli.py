import argparse
import sys

from .exceptions import ApiConfigError


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


def cli(argv=None):
    parser = argparse.ArgumentParser(prog="api", description="CLI para consulta de APIs externas")
    sub = parser.add_subparsers(dest="comando", required=True)

    # cnpja
    p_cnpja = sub.add_parser(
        "cnpja",
        help="Consultar CNPJ via CNPJa (open.cnpja.com)",
        epilog="Exemplo: api cnpja 33.000.167/0001-01",
    )
    p_cnpja.add_argument("cnpj", help="CNPJ a consultar (com ou sem formatacao)")
    p_cnpja.set_defaults(func=cmd_cnpja)

    # cnpjws
    p_cnpjws = sub.add_parser(
        "cnpjws",
        help="Consultar CNPJ via publica.cnpj.ws (inclui inscricao estadual)",
        epilog="Exemplo: api cnpjws 33.000.167/0001-01",
    )
    p_cnpjws.add_argument("cnpj", help="CNPJ a consultar (com ou sem formatacao)")
    p_cnpjws.set_defaults(func=cmd_cnpjws)

    args = parser.parse_args(argv)

    try:
        args.func(args)
    except ApiConfigError as e:
        print(f"Erro de configuracao: {e}")
        sys.exit(1)


if __name__ == "__main__":
    cli()
