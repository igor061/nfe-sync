import argparse
import sys
import urllib3

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

from .exceptions import NfeConfigError, NfeValidationError
from .commands.consulta import ConsultaBlueprint
from .commands.manifestacao import ManifestacaoBlueprint
from .commands.inutilizacao import InutilizacaoBlueprint
from .commands.emissao import EmissaoBlueprint
from .commands.sistema import SistemaBlueprint

BLUEPRINTS = [
    ConsultaBlueprint(),
    ManifestacaoBlueprint(),
    InutilizacaoBlueprint(),
    EmissaoBlueprint(),
    SistemaBlueprint(),
]


def cli(argv=None):
    parser = argparse.ArgumentParser(
        prog="nfe-sync",
        description="Integracao direta com a SEFAZ: consulta, manifestacao e inutilizacao de NF-e.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Comandos SEFAZ:\n"
            "  consultar       Consultar situacao de uma NF-e pela chave de acesso\n"
            "  consultar-nsu   Baixar NF-e e eventos recebidos via distribuicao DFe\n"
            "  pendentes       Listar NF-e com resumo pendente aguardando XML completo\n"
            "  manifestar      Manifestar ciencia, confirmacao, desconhecimento ou nao-realizacao\n"
            "  inutilizar      Inutilizar faixa de numeracao de NF-e\n"
            "  emitir          Emitir NF-e de teste em homologacao\n"
            "\n"
            "Sistema:\n"
            "  versao          Verificar versao instalada e atualizacoes disponiveis\n"
            "  atualizar       Atualizar para a versao mais recente\n"
            "  readme          Exibir documentacao completa\n"
            "\n"
            "Exemplos:\n"
            "  nfe-sync consultar      EMPRESA 12345678901234567890123456789012345678901234\n"
            "  nfe-sync consultar-nsu  EMPRESA\n"
            "  nfe-sync consultar-nsu  EMPRESA --chave CHAVE\n"
            "  nfe-sync pendentes      EMPRESA\n"
            "  nfe-sync manifestar     EMPRESA ciencia CHAVE\n"
            "  nfe-sync inutilizar     EMPRESA --serie 1 --inicio 5 --fim 8 --justificativa 'Motivo'\n"
            "  nfe-sync emitir         EMPRESA --serie 1\n"
        ),
    )
    amb = parser.add_mutually_exclusive_group()
    amb.add_argument("--producao", action="store_true", help="Forcar ambiente de producao")
    amb.add_argument("--homologacao", action="store_true", help="Forcar ambiente de homologacao")
    sub = parser.add_subparsers(dest="comando", required=True, metavar="<comando>")

    # remove o grupo de subparsers do help (os grupos ficam no epilog formatado)
    parser._action_groups = [
        g for g in parser._action_groups
        if not any(isinstance(a, argparse._SubParsersAction) for a in g._group_actions)
    ]

    for blueprint in BLUEPRINTS:
        blueprint.register(sub, parser)

    args = parser.parse_args(argv)

    try:
        args.func(args)
    except NfeConfigError as e:
        print(f"Erro de configuracao: {e}")
        print()
        print("Crie o arquivo nfe-sync.conf.ini no diretorio atual com o conteudo:")
        print()
        print("[MINHAEMPRESA]")
        print("path = certs/certificado.pfx   # caminho do certificado A1 (.pfx)")
        print("senha = senha_do_certificado   # senha do certificado")
        print("uf = sp                        # UF da empresa")
        print("homologacao = true             # true = testes, false = producao")
        print("cnpj = 00000000000191          # CNPJ somente numeros")
        print()
        print("Dica: use o api_cli para preencher os dados cadastrais automaticamente:")
        print("  api_cli cnpjws <CNPJ> --salvar-ini MINHAEMPRESA")
        print("  (depois preencha manualmente path e senha do certificado)")
        print()
        print("Para ver a documentacao completa:")
        print("  nfe-sync readme")
        sys.exit(1)
    except NfeValidationError as e:
        print(f"Erro de validacao: {e}")
        sys.exit(1)


if __name__ == "__main__":
    cli()
