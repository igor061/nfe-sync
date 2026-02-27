import argparse
import sys
import urllib3
from decimal import Decimal

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

from .config import carregar_empresas
from .models import Destinatario, Produto, Pagamento, DadosEmissao, Endereco
from .state import (
    carregar_estado,
    salvar_estado,
    get_ultimo_numero_nf,
    set_ultimo_numero_nf,
)
from .exceptions import NfeConfigError, NfeValidationError

CONFIG_FILE = ".certs.ini"
STATE_FILE = ".state.json"


def _carregar(args):
    empresas = carregar_empresas(CONFIG_FILE)
    nome = args.empresa
    if nome not in empresas:
        print(f"Erro: empresa '{nome}' nao encontrada.")
        print(f"Empresas disponiveis: {', '.join(empresas.keys())}")
        sys.exit(1)
    empresa = empresas[nome]
    if args.producao:
        empresa = empresa.model_copy(update={"homologacao": False})
    elif args.homologacao:
        empresa = empresa.model_copy(update={"homologacao": True})
    estado = carregar_estado(STATE_FILE)
    return empresa, estado


def cmd_emitir(args):
    empresa, estado = _carregar(args)
    cnpj = empresa.emitente.cnpj
    serie = args.serie

    ultimo = get_ultimo_numero_nf(estado, cnpj, serie)
    numero_nf = ultimo + 1

    print(f"Empresa: {empresa.nome} (CNPJ {cnpj})")
    print(f"UF: {empresa.uf.upper()}")
    print(f"Ambiente: {'Homologacao' if empresa.homologacao else 'Producao'}")
    print(f"Serie: {serie}  Numero NF: {numero_nf}")
    print()

    emi = empresa.emitente
    end = emi.endereco

    dados = DadosEmissao(
        destinatario=Destinatario(
            razao_social="NF-E EMITIDA EM AMBIENTE DE HOMOLOGACAO - SEM VALOR FISCAL",
            tipo_documento="CNPJ",
            numero_documento=emi.cnpj,
            indicador_ie=1,
            inscricao_estadual=emi.inscricao_estadual,
            endereco=Endereco(
                logradouro=end.logradouro,
                numero=end.numero,
                bairro=end.bairro,
                municipio=end.municipio,
                cod_municipio=end.cod_municipio,
                uf=end.uf,
                cep=end.cep,
            ),
        ),
        produtos=[
            Produto(
                codigo="0001",
                descricao="PRODUTO TESTE HOMOLOGACAO",
                ncm="71131100",
                cfop="5102",
                quantidade_comercial=Decimal("1.0000"),
                valor_unitario_comercial=Decimal("10.00"),
                quantidade_tributavel=Decimal("1.0000"),
                valor_unitario_tributavel=Decimal("10.00"),
                valor_total_bruto=Decimal("10.00"),
            ),
        ],
        pagamentos=[
            Pagamento(tipo="01", valor=Decimal("10.00")),
        ],
        informacoes_complementares="NF-e de teste emitida em homologacao.",
    )

    from .emissao import emitir
    resultado = emitir(empresa, serie, numero_nf, dados)

    if resultado.get("sucesso"):
        print(f"Status: {resultado['status']}")
        print(f"Motivo: {resultado['motivo']}")
        print(f"Protocolo: {resultado['protocolo']}")
        print(f"Chave: {resultado['chave']}")
        print(f"XML salvo em: {resultado['arquivo']}")

        set_ultimo_numero_nf(estado, cnpj, serie, numero_nf)
        salvar_estado(STATE_FILE, estado)
        print(f"Numero NF {numero_nf} serie {serie} salvo em {STATE_FILE}")
    else:
        print("ERRO na emissao:")
        for erro in resultado.get("erros", []):
            print(f"  cStat={erro['status']}  {erro['motivo']}")
        sys.exit(1)


def cmd_consultar(args):
    empresa, estado = _carregar(args)
    cnpj = empresa.emitente.cnpj

    print(f"Empresa: {empresa.nome} (CNPJ {cnpj})")
    print(f"Ambiente: {'Homologacao' if empresa.homologacao else 'Producao'}")
    print(f"Consultando situacao da NF-e...")
    print(f"Chave: {args.chave}")
    print()

    from .consulta import consultar
    resultado = consultar(empresa, args.chave)

    for sit in resultado["situacao"]:
        print(f"  cStat={sit['status']}  {sit['motivo']}")

    print(f"  XML salvo em: {resultado['arquivo']}")


def cmd_consultar_nsu(args):
    empresa, estado = _carregar(args)
    cnpj = empresa.emitente.cnpj
    nsu = args.nsu

    print(f"Empresa: {empresa.nome} (CNPJ {cnpj})")
    print(f"Ambiente: {'Homologacao' if empresa.homologacao else 'Producao'}")
    print(f"Consultando distribuicao DFe (NSU: {nsu if nsu is not None else 'ultimo salvo'})...")
    print()

    def progresso(pagina, total_docs, ult_nsu, max_nsu):
        print(f"  Pagina {pagina}: {total_docs} docs ate agora (NSU {ult_nsu}/{max_nsu})")

    from .consulta import consultar_nsu
    resultado = consultar_nsu(empresa, estado, STATE_FILE, nsu=nsu, callback=progresso)

    if not resultado.get("sucesso") and "motivo" in resultado and not resultado.get("status"):
        print(f"BLOQUEADO: {resultado['motivo']}")
        sys.exit(1)

    print(f"Status: {resultado.get('status')}")
    print(f"Motivo: {resultado.get('motivo')}")
    print(f"Ultimo NSU: {resultado.get('ultimo_nsu')}")
    print(f"Max NSU: {resultado.get('max_nsu')}")

    for arq in resultado.get("respostas", []):
        print(f"Resposta salva em: {arq}")

    docs = resultado.get("documentos", [])
    if docs:
        print(f"Documentos: {len(docs)}")
        for doc in docs:
            if "erro" in doc:
                print(f"  NSU {doc['nsu']} ({doc['schema']}) — ERRO: {doc['erro']}")
            else:
                chave = doc.get("chave") or doc["nsu"]
                print(f"  NSU {doc['nsu']} ({doc['schema']}) chave={chave} — {doc['arquivo']}")


def cmd_manifestar(args):
    empresa, estado = _carregar(args)

    print(f"Empresa: {empresa.nome} (CNPJ {empresa.emitente.cnpj})")
    print(f"Ambiente: {'Homologacao' if empresa.homologacao else 'Producao'}")
    print(f"Operacao: {args.operacao}")
    print(f"Chave: {args.chave}")
    if args.justificativa:
        print(f"Justificativa: {args.justificativa}")
    print()

    from .manifestacao import manifestar
    resultado = manifestar(empresa, args.operacao, args.chave, args.justificativa)

    print("=== RESULTADO ===")
    for r in resultado["resultados"]:
        print(f"  cStat={r['status']}  {r['motivo']}")
    if resultado["protocolo"]:
        print(f"  Protocolo: {resultado['protocolo']}")
    print(f"  Resposta salva em: {resultado['arquivo']}")


def cmd_inutilizar(args):
    empresa, estado = _carregar(args)

    print(f"Empresa: {empresa.nome} (CNPJ {empresa.emitente.cnpj})")
    print(f"Ambiente: {'Homologacao' if empresa.homologacao else 'Producao'}")
    print(f"Serie: {args.serie}")
    print(f"Faixa: {args.inicio} a {args.fim}")
    print(f"Justificativa: {args.justificativa}")
    print()

    from .inutilizacao import inutilizar
    resultado = inutilizar(empresa, args.serie, args.inicio, args.fim, args.justificativa)

    print("=== RESULTADO ===")
    for r in resultado["resultados"]:
        print(f"  cStat={r['status']}  {r['motivo']}")
    if resultado["protocolo"]:
        print(f"  Protocolo: {resultado['protocolo']}")
    print(f"  Resposta salva em: {resultado['arquivo']}")


def cli(argv=None):
    parser = argparse.ArgumentParser(prog="nfe-sync", description="NF-e Sync CLI")
    amb = parser.add_mutually_exclusive_group()
    amb.add_argument("--producao", action="store_true", help="Forcar ambiente de producao")
    amb.add_argument("--homologacao", action="store_true", help="Forcar ambiente de homologacao")
    sub = parser.add_subparsers(dest="comando", required=True)

    # emitir
    p_emitir = sub.add_parser("emitir", help="Emitir NF-e")
    p_emitir.add_argument("empresa", help="Nome da empresa (secao no .ini)")
    p_emitir.add_argument("--serie", required=True, help="Serie da NF-e")
    p_emitir.set_defaults(func=cmd_emitir)

    # consultar
    p_consultar = sub.add_parser("consultar", help="Consultar NF-e")
    p_consultar.add_argument("empresa", help="Nome da empresa (secao no .ini)")
    p_consultar.add_argument("chave", help="Chave de acesso (44 digitos)")
    p_consultar.set_defaults(func=cmd_consultar)

    # consultar-nsu
    p_nsu = sub.add_parser("consultar-nsu", help="Consultar distribuicao DFe por NSU")
    p_nsu.add_argument("empresa", help="Nome da empresa (secao no .ini)")
    p_nsu.add_argument("--nsu", type=int, default=None, help="NSU inicial (default: ultimo salvo)")
    p_nsu.set_defaults(func=cmd_consultar_nsu)

    # manifestar
    p_manifestar = sub.add_parser("manifestar", help="Manifestar destinatario")
    p_manifestar.add_argument("empresa", help="Nome da empresa (secao no .ini)")
    p_manifestar.add_argument("operacao", choices=["ciencia", "confirmacao", "desconhecimento", "nao_realizada"])
    p_manifestar.add_argument("chave", help="Chave de acesso (44 digitos)")
    p_manifestar.add_argument("--justificativa", default="", help="Justificativa (obrigatoria para nao_realizada)")
    p_manifestar.set_defaults(func=cmd_manifestar)

    # inutilizar
    p_inutilizar = sub.add_parser("inutilizar", help="Inutilizar numeracao")
    p_inutilizar.add_argument("empresa", help="Nome da empresa (secao no .ini)")
    p_inutilizar.add_argument("--serie", required=True, help="Serie da NF-e")
    p_inutilizar.add_argument("--inicio", required=True, type=int, help="Numero inicial")
    p_inutilizar.add_argument("--fim", required=True, type=int, help="Numero final")
    p_inutilizar.add_argument("--justificativa", required=True, help="Justificativa (min 15 chars)")
    p_inutilizar.set_defaults(func=cmd_inutilizar)

    args = parser.parse_args(argv)

    try:
        args.func(args)
    except NfeConfigError as e:
        print(f"Erro de configuracao: {e}")
        sys.exit(1)
    except NfeValidationError as e:
        print(f"Erro de validacao: {e}")
        sys.exit(1)


if __name__ == "__main__":
    cli()
