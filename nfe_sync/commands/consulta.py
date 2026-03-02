import argparse
import sys

from ..state import carregar_estado, salvar_estado, set_ultimo_nsu
from ..config import carregar_empresas
from ..consulta import consultar, consultar_dfe_chave, consultar_nsu
from ..manifestacao import manifestar
from . import CliBlueprint, _carregar, _salvar_xml, _salvar_log_xml, _listar_resumos_pendentes, STATE_FILE, CONFIG_FILE, _storage


def _tratar_arquivo_cancelado(cnpj: str, chave: str) -> str | None:
    """Trata arquivo existente quando NF-e foi cancelada (status 653).

    Se o arquivo existente for resNFe, apaga. Se for procNFe ou outro,
    renomeia para -cancelada.xml. Retorna o novo caminho ou None.
    """
    nome = f"{chave}.xml"
    if not _storage.existe(cnpj, nome):
        return None
    root_tag = _storage.root_tag(cnpj, nome) or ""
    if root_tag == "resNFe":
        _storage.remover(cnpj, nome)
        return None
    else:
        destino = f"{chave}-cancelada.xml"
        return _storage.renomear(cnpj, nome, destino)


def _processar_e_salvar_docs(cnpj: str, docs: list, prefixo: str = "") -> list[str]:
    """Salva XMLs e imprime tipo/chave. Retorna chaves de procNFe baixados.

    Issue #8: elimina duplicação de blocos de processamento de documentos.
    """
    completos = []
    for doc in docs:
        if doc.erro is not None:
            print(f"  {prefixo}NSU {doc.nsu} ({doc.schema}) — ERRO: {doc.erro}")
        else:
            chave = doc.chave or doc.nsu
            schema = doc.schema
            substituiu = _storage.existe(cnpj, doc.nome) and "procNFe" in schema
            arquivo = _salvar_xml(cnpj, doc.nome, doc.xml)
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

    _salvar_log_xml(resultado.xml_resposta, "consulta", args.chave)

    for sit in resultado.situacao:
        print(f"  cStat={sit['status']}  {sit['motivo']}")

    if resultado.xml:
        arquivo = _salvar_xml(cnpj, f"{args.chave}-situacao.xml", resultado.xml)
        print(f"  Protocolo salvo em: {arquivo}")

    primeiro = resultado.situacao[0]["status"] if resultado.situacao else ""
    if not primeiro.startswith("1"):
        sys.exit(1)

    print()
    cnpj_chave = args.chave[6:20]
    if cnpj_chave == cnpj:
        print("XML completo via distribuicao DFe nao disponivel para NF-e emitida pelo proprio CNPJ.")
        return
    print("Tentando baixar XML completo via distribuicao DFe...")
    dfe = consultar_dfe_chave(empresa, args.chave)
    _salvar_log_xml(dfe.xml_resposta, "dist-dfe-chave", args.chave)
    print(f"  cStat={dfe.status}  {dfe.motivo}")

    if dfe.xml_cancelamento:
        arq_cancel = _salvar_xml(cnpj, f"{args.chave}-cancelamento.xml", dfe.xml_cancelamento)
        print(f"  Registro de cancelamento salvo em: {arq_cancel}")
        arq_cancelada = _tratar_arquivo_cancelado(cnpj, args.chave)
        if arq_cancelada:
            print(f"  NF-e renomeada para: {arq_cancelada}")

    docs = dfe.documentos
    if docs:
        _processar_e_salvar_docs(cnpj, docs)


def _cmd_consultar_nsu_empresa(empresa, args):
    """Executa consultar-nsu para uma única empresa. Retorna True se sucesso."""
    estado = carregar_estado(STATE_FILE)
    cnpj = empresa.emitente.cnpj
    nsu = args.nsu

    if args.zerar_nsu:
        ambiente = "homologacao" if empresa.homologacao else "producao"
        set_ultimo_nsu(estado, cnpj, 0, ambiente)
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
        arq_resp = _salvar_log_xml(resultado.xml_resposta, "dist-dfe-chave", args.chave)
        print(f"Status: {resultado.status}")
        print(f"Motivo: {resultado.motivo}")
        print(f"Resposta salva em: {arq_resp}")

        if resultado.xml_cancelamento:
            arq_cancel = _salvar_xml(cnpj, f"{args.chave}-cancelamento.xml", resultado.xml_cancelamento)
            print(f"Registro de cancelamento salvo em: {arq_cancel}")
            arq_cancelada = _tratar_arquivo_cancelado(cnpj, args.chave)
            if arq_cancelada:
                print(f"NF-e renomeada para: {arq_cancelada}")

        docs = resultado.documentos
        if docs:
            print(f"Documentos: {len(docs)}")
            _processar_e_salvar_docs(cnpj, docs)
        return True

    resultado = consultar_nsu(empresa, estado, STATE_FILE, nsu=nsu, callback=progresso)

    if not resultado.sucesso and resultado.motivo and resultado.status is None:
        print(f"BLOQUEADO: {resultado.motivo}")
        return False

    if not resultado.sucesso:
        if resultado.status:
            print(f"Status: {resultado.status}")
        if resultado.motivo:
            print(f"Motivo: {resultado.motivo}")
        return False

    print(f"Status: {resultado.status}")
    print(f"Motivo: {resultado.motivo}")
    print(f"Ultimo NSU: {resultado.ultimo_nsu}")
    print(f"Max NSU: {resultado.max_nsu}")

    for i, xml_resp in enumerate(resultado.xmls_resposta, start=1):
        arq = _salvar_log_xml(xml_resp, "dist-dfe", f"{cnpj}-p{i:03d}")
        print(f"Resposta salva em: {arq}")

    docs = resultado.documentos
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
                    _salvar_log_xml(res.xml_resposta, "manifestacao", f"{cnpj}-ciencia")
                    _salvar_xml(cnpj, f"{chave}-evento-ciencia.xml", res.xml)
                    for r in res.resultados:
                        print(f"  {chave[:8]}...  cStat={r['status']}  {r['motivo']}")
                        if r["status"] == "650":
                            canceladas.append(chave)
                except Exception as e:
                    print(f"  {chave[:8]}...  ERRO: {e}")
            for chave in canceladas:
                if _storage.existe(cnpj, f"{chave}.xml"):
                    _storage.remover(cnpj, f"{chave}.xml")
                    print(f"  {chave[:8]}...  resNFe removido (NF-e cancelada/denegada)")
            print()
            print("Consultando novamente para baixar XML completo...")
            estado2 = carregar_estado(STATE_FILE)
            resultado2 = consultar_nsu(empresa, estado2, STATE_FILE, callback=progresso)
            print(f"Status: {resultado2.status}")
            print(f"Motivo: {resultado2.motivo}")
            docs2 = resultado2.documentos
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

    return True


def cmd_consultar_nsu(args):
    if args.empresa:
        empresa, _ = _carregar(args)
        sucesso = _cmd_consultar_nsu_empresa(empresa, args)
        if not sucesso:
            sys.exit(1)
    else:
        if args.chave or args.zerar_nsu:
            print("Erro: --chave e --zerar-nsu requerem empresa especificada.")
            sys.exit(1)
        todas = carregar_empresas(CONFIG_FILE)
        if not todas:
            print("Nenhuma empresa configurada.")
            sys.exit(1)
        falhas = []
        for i, (nome, empresa_cfg) in enumerate(todas.items()):
            if i > 0:
                print()
                print("=" * 60)
                print()
            if args.producao:
                empresa_cfg = empresa_cfg.model_copy(update={"homologacao": False})
            elif args.homologacao:
                empresa_cfg = empresa_cfg.model_copy(update={"homologacao": True})
            sucesso = _cmd_consultar_nsu_empresa(empresa_cfg, args)
            if not sucesso:
                falhas.append(nome)
        if falhas:
            print()
            print(f"Falha em: {', '.join(falhas)}")
            sys.exit(1)


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
        p_nsu.add_argument("empresa", nargs="?", default=None, help="Nome da empresa (omitir para consultar todas)")
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
