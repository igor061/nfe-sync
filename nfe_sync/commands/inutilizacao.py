import argparse
import os
import sys

from . import CliBlueprint, _carregar, _salvar_log_xml


def cmd_inutilizar(args):
    empresa, estado = _carregar(args)
    cnpj = empresa.emitente.cnpj

    print(f"Empresa: {empresa.nome} (CNPJ {cnpj})")
    print(f"Ambiente: {'Homologacao' if empresa.homologacao else 'Producao'}")
    print(f"Serie: {args.serie}")
    print(f"Faixa: {args.inicio} a {args.fim}")
    print(f"Justificativa: {args.justificativa}")
    print()

    from ..inutilizacao import inutilizar
    resultado = inutilizar(empresa, args.serie, args.inicio, args.fim, args.justificativa)

    _salvar_log_xml(resultado.xml_resposta, "inutilizacao", f"{cnpj}-serie{args.serie}-{args.inicio}-{args.fim}")
    os.makedirs("xml/inutilizacao", exist_ok=True)
    arquivo = f"xml/inutilizacao/inut-serie{args.serie}-{args.inicio}-{args.fim}.xml"
    with open(arquivo, "w") as f:
        f.write(resultado.xml)

    print("=== RESULTADO ===")
    for r in resultado.resultados:
        print(f"  cStat={r['status']}  {r['motivo']}")
    if resultado.protocolo:
        print(f"  Protocolo: {resultado.protocolo}")
    print(f"  Resposta salva em: {arquivo}")

    if not resultado.sucesso:
        sys.exit(1)


class InutilizacaoBlueprint(CliBlueprint):
    def register(self, subparsers, parser, amb_parent=None) -> None:
        parents = [amb_parent] if amb_parent else []
        p = subparsers.add_parser(
            "inutilizar",
            parents=parents,
            help=argparse.SUPPRESS,
            description="Inutiliza uma faixa de numeros de NF-e na SEFAZ.",
            formatter_class=argparse.RawDescriptionHelpFormatter,
            epilog="Exemplo:\n  nfe-sync inutilizar MINHAEMPRESA --serie 1 --inicio 5 --fim 8 --justificativa 'Numeracao nao utilizada'",
        )
        p.add_argument("empresa", help="Nome da empresa (secao no nfe-sync.conf.ini)")
        p.add_argument("--serie", required=True, help="Serie da NF-e")
        p.add_argument("--inicio", required=True, type=int, help="Numero inicial da faixa")
        p.add_argument("--fim", required=True, type=int, help="Numero final da faixa")
        p.add_argument("--justificativa", required=True, help="Justificativa da inutilizacao (minimo 15 caracteres)")
        p.set_defaults(func=cmd_inutilizar)
