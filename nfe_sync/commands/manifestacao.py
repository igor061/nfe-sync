import argparse

from . import CliBlueprint, _carregar, _salvar_xml, _salvar_log_xml


def cmd_manifestar(args):
    empresa, estado = _carregar(args)
    cnpj = empresa.emitente.cnpj

    print(f"Empresa: {empresa.nome} (CNPJ {cnpj})")
    print(f"Ambiente: {'Homologacao' if empresa.homologacao else 'Producao'}")
    print(f"Operacao: {args.operacao}")
    print(f"Chave: {args.chave}")
    if args.justificativa:
        print(f"Justificativa: {args.justificativa}")
    print()

    from ..manifestacao import manifestar
    resultado = manifestar(empresa, args.operacao, args.chave, args.justificativa)

    _salvar_log_xml(resultado.xml_resposta, "manifestacao", f"{cnpj}-{args.operacao}")
    arquivo = _salvar_xml(cnpj, f"{args.chave}-evento-{args.operacao}.xml", resultado.xml)

    print("=== RESULTADO ===")
    for r in resultado.resultados:
        print(f"  cStat={r['status']}  {r['motivo']}")
    if resultado.protocolo:
        print(f"  Protocolo: {resultado.protocolo}")
    print(f"  Resposta salva em: {arquivo}")


class ManifestacaoBlueprint(CliBlueprint):
    def register(self, subparsers, parser, amb_parent=None) -> None:
        parents = [amb_parent] if amb_parent else []
        p = subparsers.add_parser(
            "manifestar",
            parents=parents,
            help=argparse.SUPPRESS,
            description="Registra a manifestacao do destinatario para uma NF-e na SEFAZ.",
            formatter_class=argparse.RawDescriptionHelpFormatter,
            epilog=(
                "Operacoes disponiveis:\n"
                "  ciencia          Ciencia da operacao\n"
                "  confirmacao      Confirmacao da operacao\n"
                "  desconhecimento  Desconhecimento da operacao\n"
                "  nao_realizada    Operacao nao realizada (requer --justificativa)\n\n"
                "Exemplos:\n"
                "  nfe-sync manifestar MINHAEMPRESA ciencia CHAVE\n"
                "  nfe-sync manifestar MINHAEMPRESA nao_realizada CHAVE --justificativa 'Mercadoria nao entregue'"
            ),
        )
        p.add_argument("empresa", help="Nome da empresa (secao no nfe-sync.conf.ini)")
        p.add_argument(
            "operacao",
            choices=["ciencia", "confirmacao", "desconhecimento", "nao_realizada"],
            help="Tipo de manifestacao",
        )
        p.add_argument("chave", help="Chave de acesso com 44 digitos")
        p.add_argument(
            "--justificativa",
            default="",
            help="Justificativa (obrigatoria para nao_realizada, minimo 15 caracteres)",
        )
        p.set_defaults(func=cmd_manifestar)
