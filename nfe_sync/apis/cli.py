import argparse
import sys

from ..exceptions import NfeConfigError


def cmd_cnpja(args):
    from .config import get_api_config
    from .cnpja import consultar

    config = get_api_config("cnpja")
    empresa = consultar(args.cnpj, config, simples=args.simples)

    print(f"CNPJ: {empresa.cnpj}")
    print(f"Razao Social: {empresa.razao_social}")
    print(f"Nome Fantasia: {empresa.nome_fantasia}")
    print(f"Data Abertura: {empresa.data_abertura}")
    print(f"Situacao: {empresa.situacao}")
    end = empresa.endereco
    print(f"Endereco: {end.logradouro}, {end.numero} - {end.bairro}")
    print(f"Municipio: {end.municipio} / {end.uf} - CEP {end.cep}")
    if empresa.socios:
        print("Socios:")
        for s in empresa.socios:
            print(f"  {s.nome} ({s.tipo}) - {s.qualificacao}")


def cli(argv=None):
    parser = argparse.ArgumentParser(prog="api", description="CLI para consulta de APIs externas")
    sub = parser.add_subparsers(dest="comando", required=True)

    # cnpja
    p_cnpja = sub.add_parser("cnpja", help="Consultar CNPJ via CNPJa")
    p_cnpja.add_argument("cnpj", help="CNPJ a consultar")
    p_cnpja.add_argument("--simples", action="store_true", help="Incluir dados do Simples Nacional")
    p_cnpja.set_defaults(func=cmd_cnpja)

    args = parser.parse_args(argv)

    try:
        args.func(args)
    except NfeConfigError as e:
        print(f"Erro de configuracao: {e}")
        sys.exit(1)


if __name__ == "__main__":
    cli()
