import argparse
import logging
import os
import sys

from ..state import carregar_estado, salvar_estado, set_ultimo_nsu
from ..config import carregar_empresas
from ..xml_utils import safe_parse
from ..consulta import consultar, consultar_dfe_chave, consultar_nsu
from ..manifestacao import manifestar
from . import CliBlueprint, _carregar, _salvar_xml, _salvar_log_xml, _listar_resumos_pendentes, STATE_FILE, CONFIG_FILE


def _tratar_arquivo_cancelado(cnpj: str, chave: str) -> str | None:
    """Trata arquivo existente quando NF-e foi cancelada (status 653).

    Se o arquivo existente for resNFe, apaga. Se for procNFe ou outro,
    renomeia para -cancelada.xml. Retorna o novo caminho ou None.
    """
    existente = f"downloads/{cnpj}/{chave}.xml"
    if not os.path.exists(existente):
        return None
    try:
        root_tag = safe_parse(existente).getroot().tag.split("}")[-1]
    except Exception as e:
        logging.warning("Nao foi possivel ler %s: %s", existente, e)
        root_tag = ""
    if root_tag == "resNFe":
        os.remove(existente)
        return None
    else:
        destino = f"downloads/{cnpj}/{chave}-cancelada.xml"
        os.rename(existente, destino)
        return destino


def _processar_e_salvar_docs(cnpj: str, docs: list, prefixo: str = "") -> list[str]:
    """Salva XMLs e imprime tipo/chave. Retorna chaves de procNFe baixados.

    Issue #8: elimina duplicação de blocos de processamento de documentos.
    """
    completos = []
    for doc in docs:
        if "erro" in doc:
            print(f"  {prefixo}NSU {doc['nsu']} ({doc['schema']}) — ERRO: {doc['erro']}")
        else:
            chave = doc.get("chave") or doc["nsu"]
            schema = doc["schema"]
            arquivo = f"downloads/{cnpj}/{doc['nome']}"
            substituiu = os.path.exists(arquivo) and "procNFe" in schema
            _salvar_xml(cnpj, doc["nome"], doc["xml"])
            if "procNFe" in schema:
                tipo = "XML completo (substituiu resumo)" if substituiu else "XML completo"
                completos.append(chave)
            else:
                tipo = "resumo"
            print(f"  {prefixo}({tipo}) chave={chave} — {arquivo}")
    return completos


def cmd_consultar(args):
    empresa, estado = _carregar(args)
    cnpj = empresa.emitente.cnpj

    print(f"Empresa: {empresa.nome} (CNPJ {cnpj})")
    print(f"Ambiente: {'Homologacao' if empresa.homologacao else 'Producao'}")
    print(f"Consultando situacao da NF-e...")
    print(f"Chave: {args.chave}")
    print()

    resultado = consultar(empresa, args.chave)

    _salvar_log_xml(resultado["xml_resposta"], "consulta", args.chave)

    for sit in resultado["situacao"]:
        print(f"  cStat={sit['status']}  {sit['motivo']}")

    if resultado["xml"]:
        arquivo = _salvar_xml(cnpj, f"{args.chave}-situacao.xml", resultado["xml"])
        print(f"  Protocolo salvo em: {arquivo}")

    primeiro = resultado["situacao"][0]["status"] if resultado["situacao"] else ""
    if not primeiro.startswith("1"):
        sys.exit(1)

    print()
    cnpj_chave = args.chave[6:20]
    if cnpj_chave == cnpj:
        print("XML completo via distribuicao DFe nao disponivel para NF-e emitida pelo proprio CNPJ.")
        return
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

    docs = dfe.get("documentos", [])
    if docs:
        _processar_e_salvar_docs(cnpj, docs)


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
            _processar_e_salvar_docs(cnpj, docs)
        return

    resultado = consultar_nsu(empresa, estado, STATE_FILE, nsu=nsu, callback=progresso)

    if not resultado.get("sucesso") and "motivo" in resultado and not resultado.get("status"):
        print(f"BLOQUEADO: {resultado['motivo']}")
        sys.exit(1)

    if not resultado.get("sucesso"):
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
        _processar_e_salvar_docs(cnpj, docs)

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
            print()
            print("Registrando ciencia da operacao...")
            canceladas = []
            for chave in pendentes:
                try:
                    res = manifestar(empresa, "ciencia", chave, "")
                    _salvar_log_xml(res["xml_resposta"], "manifestacao", f"{cnpj}-ciencia")
                    _salvar_xml(cnpj, f"{chave}-evento-ciencia.xml", res["xml"])
                    for r in res["resultados"]:
                        print(f"  {chave[:8]}...  cStat={r['status']}  {r['motivo']}")
                        if r["status"] == "650":
                            canceladas.append(chave)
                except Exception as e:
                    print(f"  {chave[:8]}...  ERRO: {e}")
            for chave in canceladas:
                resumo = f"downloads/{cnpj}/{chave}.xml"
                if os.path.exists(resumo):
                    os.remove(resumo)
                    print(f"  {chave[:8]}...  resNFe removido (NF-e cancelada/denegada)")
            print()
            print("Consultando novamente para baixar XML completo...")
            estado2 = carregar_estado(STATE_FILE)
            resultado2 = consultar_nsu(empresa, estado2, STATE_FILE, callback=progresso)
            print(f"Status: {resultado2.get('status')}")
            print(f"Motivo: {resultado2.get('motivo')}")
            docs2 = resultado2.get("documentos", [])
            if docs2:
                print(f"Documentos: {len(docs2)}")
                completos = _processar_e_salvar_docs(cnpj, docs2, prefixo=f"NSU ... ")
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


class ConsultaBlueprint(CliBlueprint):
    def register(self, subparsers, parser, amb_parent=None) -> None:
        parents = [amb_parent] if amb_parent else []

        p_consultar = subparsers.add_parser(
            "consultar",
            parents=parents,
            help=argparse.SUPPRESS,
            description="Consulta a situacao de uma NF-e diretamente na SEFAZ.",
            formatter_class=argparse.RawDescriptionHelpFormatter,
            epilog="Exemplo:\n  nfe-sync consultar MINHAEMPRESA 12345678901234567890123456789012345678901234",
        )
        p_consultar.add_argument("empresa", help="Nome da empresa (secao no nfe-sync.conf.ini)")
        p_consultar.add_argument("chave", help="Chave de acesso com 44 digitos")
        p_consultar.set_defaults(func=cmd_consultar)

        p_nsu = subparsers.add_parser(
            "consultar-nsu",
            parents=parents,
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

        p_pendentes = subparsers.add_parser(
            "pendentes",
            parents=parents,
            help=argparse.SUPPRESS,
            description="Lista as NF-e cujo resumo (resNFe) ja foi baixado mas o XML completo ainda nao foi obtido.",
            formatter_class=argparse.RawDescriptionHelpFormatter,
            epilog="Exemplos:\n  nfe-sync pendentes\n  nfe-sync pendentes MINHAEMPRESA",
        )
        p_pendentes.add_argument("empresa", nargs="?", default=None, help="Nome da empresa (omitir para consultar todas)")
        p_pendentes.set_defaults(func=cmd_pendentes)
