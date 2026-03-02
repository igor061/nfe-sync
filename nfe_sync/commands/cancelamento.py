import argparse
import sys

from . import CliBlueprint, _carregar, _salvar_log_xml, _salvar_xml


def cmd_cancelar(args):
    empresa, _ = _carregar(args)
    cnpj = empresa.emitente.cnpj

    print(f"Empresa: {empresa.nome} (CNPJ {cnpj})")
    print(f"Ambiente: {'Homologacao' if empresa.homologacao else 'Producao'}")
    print(f"Chave: {args.chave}")
    print(f"Protocolo: {args.protocolo}")
    print()

    from ..cancelamento import cancelar
    resultado = cancelar(empresa, args.chave, args.protocolo, args.justificativa)

    _salvar_log_xml(resultado.xml_resposta, "cancelamento", args.chave)
    arquivo = _salvar_xml(cnpj, f"{args.chave}-cancelamento.xml", resultado.xml)

    print("=== RESULTADO ===")
    for r in resultado.resultados:
        print(f"  cStat={r['status']}  {r['motivo']}")
    if resultado.protocolo:
        print(f"  Protocolo: {resultado.protocolo}")
    print(f"  XML salvo em: {arquivo}")

    if not resultado.sucesso:
        sys.exit(1)


class CancelamentoBlueprint(CliBlueprint):
    def register(self, subparsers, parser, amb_parent=None) -> None:
        parents = [amb_parent] if amb_parent else []
        p = subparsers.add_parser(
            "cancelar",
            parents=parents,
            help=argparse.SUPPRESS,
            description="Cancela uma NF-e emitida na SEFAZ.",
            formatter_class=argparse.RawDescriptionHelpFormatter,
            epilog="Exemplo:\n  nfe-sync cancelar EMPRESA CHAVE --protocolo 135XXX --justificativa 'Motivo'",
        )
        p.add_argument("empresa", help="Nome da empresa (secao no nfe-sync.conf.ini)")
        p.add_argument("chave", help="Chave de acesso com 44 digitos")
        p.add_argument("--protocolo", required=True, help="Protocolo de autorizacao da NF-e")
        p.add_argument("--justificativa", required=True, help="Motivo do cancelamento (minimo 15 caracteres)")
        p.set_defaults(func=cmd_cancelar)
