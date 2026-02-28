import argparse
import subprocess
import sys
import urllib3
from decimal import Decimal
from importlib.metadata import version, PackageNotFoundError

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

from .config import carregar_empresas
from .models import Destinatario, Produto, Pagamento, DadosEmissao, Endereco
from .state import (
    carregar_estado,
    salvar_estado,
    get_ultimo_numero_nf,
    set_ultimo_numero_nf,
    set_ultimo_nsu,
)
from .exceptions import NfeConfigError, NfeValidationError

CONFIG_FILE = "nfe-sync.conf.ini"
STATE_FILE = ".state.json"
GITHUB_RAW = "https://raw.githubusercontent.com/igor061/nfe-sync/main/pyproject.toml"
GITHUB_CHANGELOG = "https://raw.githubusercontent.com/igor061/nfe-sync/main/CHANGELOG.md"
GITHUB_README = "https://raw.githubusercontent.com/igor061/nfe-sync/main/README.md"
GITHUB_PKG = "git+https://github.com/igor061/nfe-sync.git"


def _versao_local() -> str:
    try:
        return version("nfe-sync")
    except PackageNotFoundError:
        return "desconhecida"


def _versao_remota() -> str | None:
    try:
        import urllib.request
        with urllib.request.urlopen(GITHUB_RAW, timeout=5) as r:
            for linha in r.read().decode().splitlines():
                if linha.startswith("version ="):
                    return linha.split('"')[1]
    except Exception:
        return None


def _changelog_novidades(versao_local: str) -> list[str]:
    try:
        import re
        import urllib.request
        with urllib.request.urlopen(GITHUB_CHANGELOG, timeout=5) as r:
            conteudo = r.read().decode()

        padrao_versao = re.compile(r"^## (\d+\.\d+\.\d+)")

        def ver_tuple(v):
            m = re.match(r"(\d+)\.(\d+)\.(\d+)", v)
            return tuple(int(x) for x in m.groups()) if m else (0, 0, 0)

        local_t = ver_tuple(versao_local)
        linhas = []
        capturando = False
        for linha in conteudo.splitlines():
            m = padrao_versao.match(linha)
            if m:
                if ver_tuple(m.group(1)) > local_t:
                    capturando = True
                    linhas.append(linha)
                else:
                    break  # chegou na versao local ou anterior, para
            elif capturando:
                linhas.append(linha)
        return linhas
    except Exception:
        return []


def cmd_versao(args):
    local = _versao_local()
    print(f"Versao instalada: {local}")
    print("Verificando atualizacoes...")
    remota = _versao_remota()
    if remota is None:
        print("Nao foi possivel verificar a versao remota.")
    elif remota == local:
        print(f"Voce esta na versao mais recente ({local}).")
    else:
        print(f"Nova versao disponivel: {remota}")
        novidades = _changelog_novidades(local)
        if novidades:
            print("\nNovidades:")
            for linha in novidades:
                print(linha)
        print(f"\nPara atualizar: nfe-sync atualizar")


def cmd_readme(args):
    try:
        import urllib.request
        with urllib.request.urlopen(GITHUB_README, timeout=5) as r:
            print(r.read().decode())
    except Exception:
        print("Nao foi possivel obter o README. Acesse: https://github.com/igor061/nfe-sync")


def cmd_atualizar(args):
    local = _versao_local()
    print(f"Versao atual: {local}")
    print("Verificando atualizacoes...")
    remota = _versao_remota()
    if remota is None:
        print("Nao foi possivel verificar a versao remota.")
        sys.exit(1)
    if remota == local:
        print(f"Voce ja esta na versao mais recente ({local}).")
        return
    print(f"Atualizando {local} -> {remota}...")
    subprocess.run([sys.executable, "-m", "pip", "install", "--upgrade", GITHUB_PKG], check=True)


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

    if resultado["arquivo"]:
        print(f"  Protocolo salvo em: {resultado['arquivo']}")
    else:
        primeiro_stat = resultado["situacao"][0]["status"] if resultado["situacao"] else ""
        if primeiro_stat.startswith("1"):
            print()
            print("  Nota: este comando retorna apenas o protocolo de autorizacao.")
            print("  Para baixar o XML completo da NF-e use o fluxo:")
            print(f"    1. nfe-sync manifestar {args.empresa} ciencia {args.chave}")
            print(f"    2. nfe-sync consultar-nsu {args.empresa}")


def cmd_consultar_nsu(args):
    empresa, estado = _carregar(args)
    cnpj = empresa.emitente.cnpj
    nsu = args.nsu

    if args.zerar_nsu:
        set_ultimo_nsu(estado, cnpj, 0)
        salvar_estado(STATE_FILE, estado)
        nsu = 0
        print(f"NSU zerado para {cnpj}.")

    print(f"Empresa: {empresa.nome} (CNPJ {cnpj})")
    print(f"Ambiente: {'Homologacao' if empresa.homologacao else 'Producao'}")
    print(f"Consultando distribuicao DFe (NSU: {nsu if nsu is not None else 'ultimo salvo'})...")
    print()

    def progresso(pagina, total_docs, ult_nsu, max_nsu):
        print(f"  Pagina {pagina}: {total_docs} docs ate agora (NSU {ult_nsu}/{max_nsu})")

    from .consulta import consultar_nsu, consultar_dfe_chave, listar_resumos_pendentes

    if args.chave:
        resultado = consultar_dfe_chave(empresa, args.chave)
        print(f"Status: {resultado.get('status')}")
        print(f"Motivo: {resultado.get('motivo')}")
        print(f"Resposta salva em: {resultado['resposta']}")
        if resultado.get("arquivo_cancelada"):
            print(f"Registro de cancelamento salvo em: {resultado['arquivo_cancelada']}")
        docs = resultado.get("documentos", [])
        if docs:
            print(f"Documentos: {len(docs)}")
            for doc in docs:
                if "erro" in doc:
                    print(f"  NSU {doc['nsu']} ({doc['schema']}) — ERRO: {doc['erro']}")
                else:
                    chave_doc = doc.get("chave") or doc["nsu"]
                    schema = doc['schema']
                    tipo = "XML completo (substituiu resumo)" if "procNFe" in schema and doc.get("substituiu_resumo") else ("XML completo" if "procNFe" in schema else "resumo")
                    print(f"  ({tipo}) chave={chave_doc} — {doc['arquivo']}")
        return

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
                schema = doc['schema']
                if "procNFe" in schema and doc.get("substituiu_resumo"):
                    tipo = "XML completo (substituiu resumo)"
                elif "procNFe" in schema:
                    tipo = "XML completo"
                else:
                    tipo = "resumo"
                print(f"  NSU {doc['nsu']} ({tipo}) chave={chave} — {doc['arquivo']}")

    # verifica resNFe pendentes no disco (run atual + runs anteriores)
    pendentes = listar_resumos_pendentes(cnpj)
    if pendentes:
        print()
        print(f"NF-e com resumo pendente — {len(pendentes)} chave(s) aguardando XML completo:")
        for chave in pendentes:
            print(f"  {chave}")
        print()
        try:
            resposta = input("Registrar ciencia e baixar XML completo para todas? [s/N] ").strip().lower()
        except (EOFError, KeyboardInterrupt):
            resposta = ""
        if resposta == "s":
            from .manifestacao import manifestar
            print()
            print("Registrando ciencia da operacao...")
            for chave in pendentes:
                try:
                    res = manifestar(empresa, "ciencia", chave, "")
                    for r in res["resultados"]:
                        print(f"  {chave[:8]}...  cStat={r['status']}  {r['motivo']}")
                except Exception as e:
                    print(f"  {chave[:8]}...  ERRO: {e}")
            print()
            print("Consultando novamente para baixar XML completo...")
            from .state import carregar_estado
            estado2 = carregar_estado(STATE_FILE)
            resultado2 = consultar_nsu(empresa, estado2, STATE_FILE, callback=progresso)
            print(f"Status: {resultado2.get('status')}")
            print(f"Motivo: {resultado2.get('motivo')}")
            docs2 = resultado2.get("documentos", [])
            completos = []
            if docs2:
                print(f"Documentos: {len(docs2)}")
                for doc in docs2:
                    if "erro" in doc:
                        print(f"  NSU {doc['nsu']} ({doc['schema']}) — ERRO: {doc['erro']}")
                    else:
                        chave = doc.get("chave") or doc["nsu"]
                        schema = doc['schema']
                        if "procNFe" in schema and doc.get("substituiu_resumo"):
                            tipo = "XML completo (substituiu resumo)"
                            completos.append(chave)
                        elif "procNFe" in schema:
                            tipo = "XML completo"
                        else:
                            tipo = "resumo"
                        print(f"  NSU {doc['nsu']} ({tipo}) chave={chave} — {doc['arquivo']}")
            if completos:
                print()
                print(f"XML completo baixado para {len(completos)} NF-e(s).")
            ainda_pendentes = listar_resumos_pendentes(cnpj)
            if ainda_pendentes:
                print()
                print(f"Ainda ha {len(ainda_pendentes)} resumo(s) pendente(s). Execute novamente para tentar novamente.")


def cmd_pendentes(args):
    empresa, estado = _carregar(args)
    cnpj = empresa.emitente.cnpj

    from .consulta import listar_resumos_pendentes
    pendentes = listar_resumos_pendentes(cnpj)

    if not pendentes:
        print(f"Nenhum resumo pendente para {cnpj}.")
        return

    print(f"NF-e com resumo pendente — {len(pendentes)} chave(s) aguardando XML completo:")
    for chave in pendentes:
        print(f"  {chave}")
    print()
    print("Para baixar o XML completo:")
    print(f"  nfe-sync consultar-nsu {args.empresa}")


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
    parser = argparse.ArgumentParser(
        prog="nfe-sync",
        description="Integracao direta com a SEFAZ: consulta, manifestacao e inutilizacao de NF-e.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Exemplos de uso:\n"
            "  nfe-sync consultar      EMPRESA 12345678901234567890123456789012345678901234\n"
            "  nfe-sync consultar-nsu  EMPRESA\n"
            "  nfe-sync consultar-nsu  EMPRESA --nsu 0\n"
            "  nfe-sync consultar-nsu  EMPRESA --zerar-nsu\n"
            "  nfe-sync pendentes      EMPRESA\n"
            "  nfe-sync manifestar     EMPRESA ciencia CHAVE\n"
            "  nfe-sync manifestar     EMPRESA nao_realizada CHAVE --justificativa 'Motivo'\n"
            "  nfe-sync inutilizar     EMPRESA --serie 1 --inicio 5 --fim 8 --justificativa 'Motivo'\n"
            "  nfe-sync versao\n"
            "  nfe-sync atualizar\n"
            "  nfe-sync readme\n"
        ),
    )
    amb = parser.add_mutually_exclusive_group()
    amb.add_argument("--producao", action="store_true", help="Forcar ambiente de producao")
    amb.add_argument("--homologacao", action="store_true", help="Forcar ambiente de homologacao")
    sub = parser.add_subparsers(dest="comando", required=True)

    # consultar
    p_consultar = sub.add_parser(
        "consultar",
        help="Consultar situacao de uma NF-e pela chave de acesso",
        description="Consulta a situacao de uma NF-e diretamente na SEFAZ.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="Exemplo:\n  nfe-sync consultar MINHAEMPRESA 12345678901234567890123456789012345678901234",
    )
    p_consultar.add_argument("empresa", help="Nome da empresa (secao no nfe-sync.conf.ini)")
    p_consultar.add_argument("chave", help="Chave de acesso com 44 digitos")
    p_consultar.set_defaults(func=cmd_consultar)

    # consultar-nsu
    p_nsu = sub.add_parser(
        "consultar-nsu",
        help="Baixar NF-e e eventos recebidos via distribuicao DFe (NSU)",
        description="Consulta a distribuicao DFe na SEFAZ, baixando NF-e e eventos a partir do ultimo NSU salvo.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Exemplos:\n"
            "  nfe-sync consultar-nsu MINHAEMPRESA\n"
            "  nfe-sync consultar-nsu MINHAEMPRESA --nsu 0\n"
            "  nfe-sync consultar-nsu MINHAEMPRESA --zerar-nsu"
        ),
    )
    p_nsu.add_argument("empresa", help="Nome da empresa (secao no nfe-sync.conf.ini)")
    p_nsu.add_argument("--nsu", type=int, default=None, help="NSU inicial (padrao: ultimo NSU salvo)")
    p_nsu.add_argument("--zerar-nsu", action="store_true", help="Zera o NSU salvo e recomeça do inicio (ultimos 90 dias)")
    p_nsu.add_argument("--chave", default=None, help="Baixar documento DFe de uma chave especifica sem avançar o NSU")
    p_nsu.set_defaults(func=cmd_consultar_nsu)

    # pendentes
    p_pendentes = sub.add_parser(
        "pendentes",
        help="Listar NF-e com resumo pendente aguardando XML completo",
        description="Lista as NF-e cujo resumo (resNFe) ja foi baixado mas o XML completo ainda nao foi obtido.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="Exemplo:\n  nfe-sync pendentes MINHAEMPRESA",
    )
    p_pendentes.add_argument("empresa", help="Nome da empresa (secao no nfe-sync.conf.ini)")
    p_pendentes.set_defaults(func=cmd_pendentes)

    # manifestar
    p_manifestar = sub.add_parser(
        "manifestar",
        help="Manifestar ciencia, confirmacao, desconhecimento ou nao-realizacao",
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
    p_manifestar.add_argument("empresa", help="Nome da empresa (secao no nfe-sync.conf.ini)")
    p_manifestar.add_argument("operacao", choices=["ciencia", "confirmacao", "desconhecimento", "nao_realizada"], help="Tipo de manifestacao")
    p_manifestar.add_argument("chave", help="Chave de acesso com 44 digitos")
    p_manifestar.add_argument("--justificativa", default="", help="Justificativa (obrigatoria para nao_realizada, minimo 15 caracteres)")
    p_manifestar.set_defaults(func=cmd_manifestar)

    # inutilizar
    p_inutilizar = sub.add_parser(
        "inutilizar",
        help="Inutilizar faixa de numeracao de NF-e",
        description="Inutiliza uma faixa de numeros de NF-e na SEFAZ.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="Exemplo:\n  nfe-sync inutilizar MINHAEMPRESA --serie 1 --inicio 5 --fim 8 --justificativa 'Numeracao nao utilizada'",
    )
    p_inutilizar.add_argument("empresa", help="Nome da empresa (secao no nfe-sync.conf.ini)")
    p_inutilizar.add_argument("--serie", required=True, help="Serie da NF-e")
    p_inutilizar.add_argument("--inicio", required=True, type=int, help="Numero inicial da faixa")
    p_inutilizar.add_argument("--fim", required=True, type=int, help="Numero final da faixa")
    p_inutilizar.add_argument("--justificativa", required=True, help="Justificativa da inutilizacao (minimo 15 caracteres)")
    p_inutilizar.set_defaults(func=cmd_inutilizar)

    # versao
    p_versao = sub.add_parser(
        "versao",
        help="Exibir versao instalada e verificar atualizacoes disponiveis",
        description="Exibe a versao instalada e verifica se ha uma versao mais recente no repositorio.",
    )
    p_versao.set_defaults(func=cmd_versao)

    # atualizar
    p_atualizar = sub.add_parser(
        "atualizar",
        help="Atualizar o nfe-sync para a versao mais recente",
        description="Atualiza o nfe-sync para a versao mais recente disponivel no repositorio.",
    )
    p_atualizar.set_defaults(func=cmd_atualizar)

    # readme
    p_readme = sub.add_parser(
        "readme",
        help="Exibir o README com a documentacao completa",
        description="Exibe o README do repositorio com instrucoes de instalacao, configuracao e uso.",
    )
    p_readme.set_defaults(func=cmd_readme)

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
