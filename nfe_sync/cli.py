import argparse
import os
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
from .log import salvar_resposta_sefaz

CONFIG_FILE = "nfe-sync.conf.ini"
STATE_FILE = ".state.json"
GITHUB_RAW = "https://raw.githubusercontent.com/igor061/nfe-sync/main/pyproject.toml"
GITHUB_CHANGELOG = "https://raw.githubusercontent.com/igor061/nfe-sync/main/CHANGELOG.md"
GITHUB_README = "https://raw.githubusercontent.com/igor061/nfe-sync/main/README.md"
GITHUB_PKG = "git+https://github.com/igor061/nfe-sync.git"


# ---------------------------------------------------------------------------
# Helpers de I/O (usados pelos cmd_* para persistir o que a lib retorna)
# ---------------------------------------------------------------------------

def _salvar_xml(cnpj: str, nome: str, xml: str) -> str:
    """Cria downloads/{cnpj}/ e salva XML. Retorna o caminho do arquivo."""
    pasta = f"downloads/{cnpj}"
    os.makedirs(pasta, exist_ok=True)
    caminho = f"{pasta}/{nome}"
    with open(caminho, "w") as f:
        f.write(xml)
    return caminho


def _salvar_log_xml(xml_str: str, tipo: str, ref: str) -> str:
    """Salva resposta SEFAZ em log/. Wrapper sobre log.salvar_resposta_sefaz()."""
    from pynfe.utils import etree
    xml_el = etree.fromstring(xml_str.encode())
    return salvar_resposta_sefaz(xml_el, tipo, ref)


def _listar_resumos_pendentes(cnpj: str) -> list[str]:
    """Escaneia downloads/{cnpj}/ por arquivos resNFe (root tag = resNFe)."""
    from pynfe.utils import etree
    pasta = f"downloads/{cnpj}"
    if not os.path.isdir(pasta):
        return []
    resumos = []
    for nome in os.listdir(pasta):
        if not nome.endswith(".xml"):
            continue
        # chave tem 44 digitos; resNFe salvo como {chave}.xml = 48 chars
        if len(nome) != 48:
            continue
        try:
            tree = etree.parse(os.path.join(pasta, nome))
            root = tree.getroot()
            local = root.tag.split("}")[-1] if "}" in root.tag else root.tag
            if local == "resNFe":
                resumos.append(nome[:-4])
        except Exception:
            pass
    return resumos


# ---------------------------------------------------------------------------
# Versao / atualizacao
# ---------------------------------------------------------------------------

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
                    break
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


# ---------------------------------------------------------------------------
# Helpers de contexto
# ---------------------------------------------------------------------------

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


# ---------------------------------------------------------------------------
# Comandos SEFAZ
# ---------------------------------------------------------------------------

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
        _salvar_log_xml(resultado["xml"], "emissao", cnpj)
        os.makedirs("xml", exist_ok=True)
        arquivo = f"xml/{resultado['chave']}.xml"
        with open(arquivo, "w") as f:
            f.write(resultado["xml"])

        print(f"Status: {resultado['status']}")
        print(f"Motivo: {resultado['motivo']}")
        print(f"Protocolo: {resultado['protocolo']}")
        print(f"Chave: {resultado['chave']}")
        print(f"XML salvo em: {arquivo}")

        set_ultimo_numero_nf(estado, cnpj, serie, numero_nf)
        salvar_estado(STATE_FILE, estado)
        print(f"Numero NF {numero_nf} serie {serie} salvo em {STATE_FILE}")
    else:
        if resultado.get("xml_resposta"):
            _salvar_log_xml(resultado["xml_resposta"], "emissao-erro", cnpj)
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

    from .consulta import consultar, consultar_dfe_chave
    resultado = consultar(empresa, args.chave)

    _salvar_log_xml(resultado["xml_resposta"], "consulta", args.chave)

    for sit in resultado["situacao"]:
        print(f"  cStat={sit['status']}  {sit['motivo']}")

    if resultado["xml"]:
        arquivo = _salvar_xml(cnpj, f"{args.chave}-situacao.xml", resultado["xml"])
        print(f"  Protocolo salvo em: {arquivo}")

    # tenta baixar o XML completo via DFe
    print()
    print("Tentando baixar XML completo via distribuicao DFe...")
    dfe = consultar_dfe_chave(empresa, args.chave)
    _salvar_log_xml(dfe["xml_resposta"], "dist-dfe-chave", args.chave)
    print(f"  cStat={dfe.get('status')}  {dfe.get('motivo')}")

    if dfe.get("xml_cancelamento"):
        arq_cancel = _salvar_xml(cnpj, f"{args.chave}-cancelamento.xml", dfe["xml_cancelamento"])
        print(f"  Registro de cancelamento salvo em: {arq_cancel}")
        arq_cancelada = _tratar_arquivo_cancelado(cnpj, args.chave)
        if arq_cancelada:
            print(f"  NF-e renomeada para: {arq_cancelada}")

    for doc in dfe.get("documentos", []):
        if "erro" in doc:
            print(f"  ERRO: {doc['erro']}")
        else:
            chave_doc = doc.get("chave") or doc["nsu"]
            schema = doc["schema"]
            arquivo_existente = f"downloads/{cnpj}/{doc['nome']}"
            substituiu_resumo = os.path.exists(arquivo_existente) and "procNFe" in schema
            _salvar_xml(cnpj, doc["nome"], doc["xml"])
            if "procNFe" in schema and substituiu_resumo:
                tipo = "XML completo (substituiu resumo)"
            elif "procNFe" in schema:
                tipo = "XML completo"
            else:
                tipo = "resumo"
            print(f"  ({tipo}) — {arquivo_existente}")


def _tratar_arquivo_cancelado(cnpj: str, chave: str) -> str | None:
    """Trata arquivo existente quando NF-e foi cancelada (status 653).

    Se o arquivo existente for resNFe, apaga. Se for procNFe ou outro,
    renomeia para -cancelada.xml. Retorna o novo caminho ou None.
    """
    from pynfe.utils import etree
    existente = f"downloads/{cnpj}/{chave}.xml"
    if not os.path.exists(existente):
        return None
    try:
        root_tag = etree.parse(existente).getroot().tag.split("}")[-1]
    except Exception:
        root_tag = ""
    if root_tag == "resNFe":
        os.remove(existente)
        return None
    else:
        destino = f"downloads/{cnpj}/{chave}-cancelada.xml"
        os.rename(existente, destino)
        return destino


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

    from .consulta import consultar_nsu, consultar_dfe_chave

    if args.chave:
        resultado = consultar_dfe_chave(empresa, args.chave)
        arq_resp = _salvar_log_xml(resultado["xml_resposta"], "dist-dfe-chave", args.chave)
        print(f"Status: {resultado.get('status')}")
        print(f"Motivo: {resultado.get('motivo')}")
        print(f"Resposta salva em: {arq_resp}")

        if resultado.get("xml_cancelamento"):
            arq_cancel = _salvar_xml(cnpj, f"{args.chave}-cancelamento.xml", resultado["xml_cancelamento"])
            print(f"Registro de cancelamento salvo em: {arq_cancel}")
            arq_cancelada = _tratar_arquivo_cancelado(cnpj, args.chave)
            if arq_cancelada:
                print(f"NF-e renomeada para: {arq_cancelada}")

        docs = resultado.get("documentos", [])
        if docs:
            print(f"Documentos: {len(docs)}")
            for doc in docs:
                if "erro" in doc:
                    print(f"  NSU {doc['nsu']} ({doc['schema']}) — ERRO: {doc['erro']}")
                else:
                    chave_doc = doc.get("chave") or doc["nsu"]
                    schema = doc["schema"]
                    arquivo_existente = f"downloads/{cnpj}/{doc['nome']}"
                    substituiu_resumo = os.path.exists(arquivo_existente) and "procNFe" in schema
                    _salvar_xml(cnpj, doc["nome"], doc["xml"])
                    tipo = "XML completo (substituiu resumo)" if "procNFe" in schema and substituiu_resumo else ("XML completo" if "procNFe" in schema else "resumo")
                    print(f"  ({tipo}) chave={chave_doc} — {arquivo_existente}")
        return

    resultado = consultar_nsu(empresa, estado, STATE_FILE, nsu=nsu, callback=progresso)

    if not resultado.get("sucesso") and "motivo" in resultado and not resultado.get("status"):
        print(f"BLOQUEADO: {resultado['motivo']}")
        sys.exit(1)

    print(f"Status: {resultado.get('status')}")
    print(f"Motivo: {resultado.get('motivo')}")
    print(f"Ultimo NSU: {resultado.get('ultimo_nsu')}")
    print(f"Max NSU: {resultado.get('max_nsu')}")

    for i, xml_resp in enumerate(resultado.get("xmls_resposta", []), start=1):
        arq = _salvar_log_xml(xml_resp, "dist-dfe", f"{cnpj}-p{i:03d}")
        print(f"Resposta salva em: {arq}")

    docs = resultado.get("documentos", [])
    if docs:
        print(f"Documentos: {len(docs)}")
        for doc in docs:
            if "erro" in doc:
                print(f"  NSU {doc['nsu']} ({doc['schema']}) — ERRO: {doc['erro']}")
            else:
                chave = doc.get("chave") or doc["nsu"]
                schema = doc["schema"]
                arquivo_existente = f"downloads/{cnpj}/{doc['nome']}"
                substituiu_resumo = os.path.exists(arquivo_existente) and "procNFe" in schema
                _salvar_xml(cnpj, doc["nome"], doc["xml"])
                if "procNFe" in schema and substituiu_resumo:
                    tipo = "XML completo (substituiu resumo)"
                elif "procNFe" in schema:
                    tipo = "XML completo"
                else:
                    tipo = "resumo"
                print(f"  NSU {doc['nsu']} ({tipo}) chave={chave} — {arquivo_existente}")

    # verifica resNFe pendentes no disco (run atual + runs anteriores)
    pendentes = _listar_resumos_pendentes(cnpj)
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
                    _salvar_log_xml(res["xml_resposta"], "manifestacao", f"{cnpj}-ciencia")
                    _salvar_xml(cnpj, f"{chave}-evento-ciencia.xml", res["xml"])
                    for r in res["resultados"]:
                        print(f"  {chave[:8]}...  cStat={r['status']}  {r['motivo']}")
                except Exception as e:
                    print(f"  {chave[:8]}...  ERRO: {e}")
            print()
            print("Consultando novamente para baixar XML completo...")
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
                        schema = doc["schema"]
                        arquivo_existente = f"downloads/{cnpj}/{doc['nome']}"
                        substituiu_resumo = os.path.exists(arquivo_existente) and "procNFe" in schema
                        _salvar_xml(cnpj, doc["nome"], doc["xml"])
                        if "procNFe" in schema and substituiu_resumo:
                            tipo = "XML completo (substituiu resumo)"
                            completos.append(chave)
                        elif "procNFe" in schema:
                            tipo = "XML completo"
                        else:
                            tipo = "resumo"
                        print(f"  NSU {doc['nsu']} ({tipo}) chave={chave} — {arquivo_existente}")
            if completos:
                print()
                print(f"XML completo baixado para {len(completos)} NF-e(s).")
            ainda_pendentes = _listar_resumos_pendentes(cnpj)
            if ainda_pendentes:
                print()
                print(f"Ainda ha {len(ainda_pendentes)} resumo(s) pendente(s). Execute novamente para tentar novamente.")


def cmd_pendentes(args):
    if args.empresa:
        empresa, _ = _carregar(args)
        empresas_cnpj = [(args.empresa, empresa.emitente.cnpj)]
    else:
        todas = carregar_empresas(CONFIG_FILE)
        empresas_cnpj = [(nome, e.emitente.cnpj) for nome, e in todas.items()]

    total = 0
    for nome, cnpj in empresas_cnpj:
        pendentes = _listar_resumos_pendentes(cnpj)
        if not pendentes:
            print(f"{nome} ({cnpj}): nenhum resumo pendente.")
            continue
        print(f"{nome} ({cnpj}): {len(pendentes)} chave(s) pendente(s):")
        for chave in pendentes:
            print(f"  {chave}")
        print(f"  -> nfe-sync consultar-nsu {nome}")
        total += len(pendentes)

    if total == 0 and len(empresas_cnpj) > 1:
        print("Nenhum resumo pendente em nenhuma empresa.")


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

    from .manifestacao import manifestar
    resultado = manifestar(empresa, args.operacao, args.chave, args.justificativa)

    _salvar_log_xml(resultado["xml_resposta"], "manifestacao", f"{cnpj}-{args.operacao}")
    arquivo = _salvar_xml(cnpj, f"{args.chave}-evento-{args.operacao}.xml", resultado["xml"])

    print("=== RESULTADO ===")
    for r in resultado["resultados"]:
        print(f"  cStat={r['status']}  {r['motivo']}")
    if resultado["protocolo"]:
        print(f"  Protocolo: {resultado['protocolo']}")
    print(f"  Resposta salva em: {arquivo}")


def cmd_inutilizar(args):
    empresa, estado = _carregar(args)
    cnpj = empresa.emitente.cnpj

    print(f"Empresa: {empresa.nome} (CNPJ {cnpj})")
    print(f"Ambiente: {'Homologacao' if empresa.homologacao else 'Producao'}")
    print(f"Serie: {args.serie}")
    print(f"Faixa: {args.inicio} a {args.fim}")
    print(f"Justificativa: {args.justificativa}")
    print()

    from .inutilizacao import inutilizar
    resultado = inutilizar(empresa, args.serie, args.inicio, args.fim, args.justificativa)

    _salvar_log_xml(resultado["xml_resposta"], "inutilizacao", f"{cnpj}-serie{args.serie}-{args.inicio}-{args.fim}")
    os.makedirs("xml/inutilizacao", exist_ok=True)
    arquivo = f"xml/inutilizacao/inut-serie{args.serie}-{args.inicio}-{args.fim}.xml"
    with open(arquivo, "w") as f:
        f.write(resultado["xml"])

    print("=== RESULTADO ===")
    for r in resultado["resultados"]:
        print(f"  cStat={r['status']}  {r['motivo']}")
    if resultado["protocolo"]:
        print(f"  Protocolo: {resultado['protocolo']}")
    print(f"  Resposta salva em: {arquivo}")


# ---------------------------------------------------------------------------
# Parser
# ---------------------------------------------------------------------------

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

    # consultar
    p_consultar = sub.add_parser(
        "consultar",
        help=argparse.SUPPRESS,
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
        help=argparse.SUPPRESS,
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
        help=argparse.SUPPRESS,
        description="Lista as NF-e cujo resumo (resNFe) ja foi baixado mas o XML completo ainda nao foi obtido.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="Exemplos:\n  nfe-sync pendentes\n  nfe-sync pendentes MINHAEMPRESA",
    )
    p_pendentes.add_argument("empresa", nargs="?", default=None, help="Nome da empresa (omitir para consultar todas)")
    p_pendentes.set_defaults(func=cmd_pendentes)

    # manifestar
    p_manifestar = sub.add_parser(
        "manifestar",
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
    p_manifestar.add_argument("empresa", help="Nome da empresa (secao no nfe-sync.conf.ini)")
    p_manifestar.add_argument("operacao", choices=["ciencia", "confirmacao", "desconhecimento", "nao_realizada"], help="Tipo de manifestacao")
    p_manifestar.add_argument("chave", help="Chave de acesso com 44 digitos")
    p_manifestar.add_argument("--justificativa", default="", help="Justificativa (obrigatoria para nao_realizada, minimo 15 caracteres)")
    p_manifestar.set_defaults(func=cmd_manifestar)

    # inutilizar
    p_inutilizar = sub.add_parser(
        "inutilizar",
        help=argparse.SUPPRESS,
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
        help=argparse.SUPPRESS,
        description="Exibe a versao instalada e verifica se ha uma versao mais recente no repositorio.",
    )
    p_versao.set_defaults(func=cmd_versao)

    # atualizar
    p_atualizar = sub.add_parser(
        "atualizar",
        help=argparse.SUPPRESS,
        description="Atualiza o nfe-sync para a versao mais recente disponivel no repositorio.",
    )
    p_atualizar.set_defaults(func=cmd_atualizar)

    # readme
    p_readme = sub.add_parser(
        "readme",
        help=argparse.SUPPRESS,
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
