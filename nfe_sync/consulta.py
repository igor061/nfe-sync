import logging
import time
import traceback
from datetime import datetime, timedelta, timezone

from .models import EmpresaConfig, validar_cnpj_sefaz
from .state import get_ultimo_nsu, set_ultimo_nsu, get_cooldown, set_cooldown, salvar_estado
from .xml_utils import to_xml_string, extract_status_motivo, criar_comunicacao, safe_fromstring


COOLDOWN_MINUTOS = 61
NS = {"ns": "http://www.portalfiscal.inf.br/nfe"}

# Issue #14: timezone BRT (UTC-3) para timestamps consistentes
_BRT = timezone(timedelta(hours=-3))


def _agora_brt() -> datetime:
    """Retorna o datetime atual no fuso BRT (UTC-3) sem informação de timezone."""
    return datetime.now(_BRT).replace(tzinfo=None)


COD_UF = {
    "11": "ro", "12": "ac", "13": "am", "14": "rr", "15": "pa",
    "16": "ap", "17": "to", "21": "ma", "22": "pi", "23": "ce",
    "24": "rn", "25": "pb", "26": "pe", "27": "al", "28": "se",
    "29": "ba", "31": "mg", "32": "es", "33": "rj", "35": "sp",
    "41": "pr", "42": "sc", "43": "rs", "50": "ms", "51": "mt",
    "52": "go", "53": "df",
}


def _uf_da_chave(chave: str) -> str | None:
    return COD_UF.get(chave[:2])


def verificar_cooldown(bloqueado_ate: str | None) -> tuple[bool, str]:
    if not bloqueado_ate:
        return False, ""
    try:
        dt = datetime.fromisoformat(bloqueado_ate)
        agora = _agora_brt()
        if agora < dt:
            restante = dt - agora
            mins = int(restante.total_seconds() / 60)
            return True, f"Distribuicao DFe bloqueada ate {dt.strftime('%H:%M:%S')} ({mins}min restantes)"
        return False, ""
    except ValueError:
        return False, ""


def calcular_proximo_cooldown(minutos: int = COOLDOWN_MINUTOS) -> str:
    return (_agora_brt() + timedelta(minutes=minutos)).isoformat(timespec="seconds")


# Issue #5: retry com backoff exponencial
def _com_retry(fn, *args, tentativas=3, base=5, **kwargs):
    """Chama fn(*args, **kwargs) com retry exponencial (tentativas x, delay base*2^n segundos)."""
    for n in range(tentativas):
        try:
            return fn(*args, **kwargs)
        except Exception:
            if n == tentativas - 1:
                raise
            time.sleep(base * (2 ** n))


# Issue #7: salvar estado a cada N páginas
_SALVAR_A_CADA = 10

TIPOS_EVENTO = {
    "110110": "carta-correcao",
    "110111": "cancelamento",
    "110140": "epec",
    "210200": "confirmacao",
    "210210": "ciencia",
    "210220": "desconhecimento",
    "210240": "nao-realizada",
    "510630": "registro-passagem",
    "610600": "cancelamento-substituicao",
    "610614": "cancelamento-ct",
    "790700": "averbacao",
    "990900": "vistoria-suframa",
    "990910": "internalizacao-suframa",
}


def nome_arquivo_nsu(xml_doc, schema: str, fallback: str) -> tuple[str, str | None]:
    """Retorna (nome_sem_extensao, chave_ou_None) para um documento NSU."""
    chaves = xml_doc.xpath("//*[local-name()='chNFe']/text()")
    if chaves:
        chave = chaves[0]
        is_evento = "Evento" in schema or "evento" in schema
        if is_evento:
            tp_evento = (xml_doc.xpath("//*[local-name()='tpEvento']/text()") or [""])[0]
            n_seq = (xml_doc.xpath("//*[local-name()='nSeqEvento']/text()") or ["1"])[0]
            tipo = TIPOS_EVENTO.get(tp_evento, tp_evento)
            return f"{chave}-evento-{tipo}-{n_seq}", chave
        return chave, chave

    cnpj_dest = (xml_doc.xpath("//*[local-name()='dest']/*[local-name()='CNPJ']/text()") or [""])[0]
    cnpj_emit = (xml_doc.xpath("//*[local-name()='emit']/*[local-name()='CNPJ']/text()") or [""])[0]
    serie = (xml_doc.xpath("//*[local-name()='ide']/*[local-name()='serie']/text()") or [""])[0]
    numero = (xml_doc.xpath("//*[local-name()='ide']/*[local-name()='nNF']/text()") or [""])[0]
    nome = f"{cnpj_dest}-{cnpj_emit}-{serie}-{numero}" if any([cnpj_dest, cnpj_emit, serie, numero]) else fallback
    return nome, None


def _processar_docs(xml_resp) -> list[dict]:
    from pynfe.utils.descompactar import DescompactaGzip
    docs_xml = xml_resp.xpath("//ns:docZip", namespaces=NS)
    documentos = []

    for doc in docs_xml:
        doc_nsu = doc.get("NSU", "")
        schema = doc.get("schema", "")
        try:
            xml_doc = DescompactaGzip.descompacta(doc.text)
            nome, chave = nome_arquivo_nsu(xml_doc, schema, doc_nsu)
            documentos.append({
                "nsu": doc_nsu,
                "chave": chave,
                "schema": schema,
                "nome": f"{nome}.xml",
                "xml": to_xml_string(xml_doc),
            })
        except Exception as e:
            # Issue #1: logar traceback completo para diagnóstico
            logging.warning(
                "NSU %s: erro ao processar documento\n%s", doc_nsu, traceback.format_exc()
            )
            documentos.append({
                "nsu": doc_nsu,
                "schema": schema,
                "erro": str(e),
            })

    return documentos


def consultar(empresa: EmpresaConfig, chave: str) -> dict:
    validar_cnpj_sefaz(empresa.emitente.cnpj, empresa.nome)
    uf = _uf_da_chave(chave) or empresa.uf
    con = criar_comunicacao(empresa, uf=uf)

    resp_sit = _com_retry(con.consulta_nota, modelo="nfe", chave=chave)
    xml_sit = safe_fromstring(resp_sit.content)
    xml_resposta = to_xml_string(xml_sit)
    situacao = extract_status_motivo(xml_sit, NS)

    primeiro_stat = situacao[0]["status"] if situacao else ""
    xml = xml_resposta if primeiro_stat.startswith("1") else None

    return {
        "situacao": situacao,
        "xml": xml,
        "xml_resposta": xml_resposta,
    }


def consultar_dfe_chave(empresa: EmpresaConfig, chave: str) -> dict:
    """Baixa o documento DFe (procNFe) diretamente pela chave de acesso."""
    validar_cnpj_sefaz(empresa.emitente.cnpj, empresa.nome)
    cnpj = empresa.emitente.cnpj
    uf = _uf_da_chave(chave) or empresa.uf
    con = criar_comunicacao(empresa, uf=uf)

    resp = _com_retry(con.consulta_distribuicao, cnpj=cnpj, chave=chave)
    xml_resp = safe_fromstring(resp.content if hasattr(resp, "content") else resp)
    xml_resposta = to_xml_string(xml_resp)

    # escalares — não lista; manter inline
    status = xml_resp.xpath("//ns:cStat", namespaces=NS)
    motivo = xml_resp.xpath("//ns:xMotivo", namespaces=NS)
    c_stat = status[0].text if status else None
    x_motivo = motivo[0].text if motivo else None

    documentos = []
    xml_cancelamento = None

    if c_stat == "138":
        documentos = _processar_docs(xml_resp)
    elif c_stat == "653":
        xml_cancelamento = xml_resposta

    return {
        "sucesso": c_stat == "138",
        "status": c_stat,
        "motivo": x_motivo,
        "documentos": documentos,
        "xml_resposta": xml_resposta,
        "xml_cancelamento": xml_cancelamento,
    }


def consultar_nsu(
    empresa: EmpresaConfig, estado: dict, state_file: str | None = None,
    nsu: int | None = None, callback=None,
) -> dict:
    validar_cnpj_sefaz(empresa.emitente.cnpj, empresa.nome)
    cnpj = empresa.emitente.cnpj
    ambiente = "homologacao" if empresa.homologacao else "producao"

    bloqueado, msg = verificar_cooldown(get_cooldown(estado, cnpj, ambiente))
    if bloqueado:
        return {"sucesso": False, "motivo": msg, "documentos": [], "estado": estado, "xmls_resposta": []}

    if nsu is None:
        nsu = get_ultimo_nsu(estado, cnpj)

    con = criar_comunicacao(empresa)

    documentos = []
    xmls_resposta = []
    ult_nsu = nsu
    max_nsu = nsu
    c_stat = None
    x_motivo = None
    pagina = 0

    while True:
        pagina += 1
        resp = _com_retry(con.consulta_distribuicao, cnpj=cnpj, nsu=ult_nsu)

        xml_resp = safe_fromstring(resp.content if hasattr(resp, "content") else resp)

        # escalares — não lista
        status = xml_resp.xpath("//ns:cStat", namespaces=NS)
        motivo = xml_resp.xpath("//ns:xMotivo", namespaces=NS)
        c_stat = status[0].text if status else None
        x_motivo = motivo[0].text if motivo else None

        ult_nsu_el = xml_resp.xpath("//ns:ultNSU", namespaces=NS)
        max_nsu_el = xml_resp.xpath("//ns:maxNSU", namespaces=NS)
        ult_nsu = int(ult_nsu_el[0].text) if ult_nsu_el else ult_nsu
        max_nsu = int(max_nsu_el[0].text) if max_nsu_el else ult_nsu

        xmls_resposta.append(to_xml_string(xml_resp))

        if c_stat != "138":
            break

        docs = _processar_docs(xml_resp)
        documentos.extend(docs)

        set_ultimo_nsu(estado, cnpj, ult_nsu)
        # Issue #7: salvar estado a cada _SALVAR_A_CADA páginas ou na última
        if pagina % _SALVAR_A_CADA == 0 or ult_nsu >= max_nsu:
            if state_file:
                salvar_estado(state_file, estado)

        if callback:
            callback(pagina, len(documentos), ult_nsu, max_nsu)

        if ult_nsu >= max_nsu:
            break

    if c_stat == "137":
        set_cooldown(estado, cnpj, calcular_proximo_cooldown(), ambiente)
        if state_file:
            salvar_estado(state_file, estado)

    return {
        "sucesso": c_stat in ("137", "138"),
        "status": c_stat,
        "motivo": x_motivo,
        "ultimo_nsu": ult_nsu,
        "max_nsu": max_nsu,
        "documentos": documentos,
        "xmls_resposta": xmls_resposta,
        "estado": estado,
    }
