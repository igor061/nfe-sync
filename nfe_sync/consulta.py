import os
from datetime import datetime, timedelta

from pynfe.processamento.comunicacao import ComunicacaoSefaz
from pynfe.utils import etree
from pynfe.utils.descompactar import DescompactaGzip

from .models import EmpresaConfig
from .state import get_ultimo_nsu, set_ultimo_nsu, get_cooldown, set_cooldown, salvar_estado
from .log import salvar_resposta_sefaz


COOLDOWN_MINUTOS = 61
NS = {"ns": "http://www.portalfiscal.inf.br/nfe"}

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
        agora = datetime.now()
        if agora < dt:
            restante = dt - agora
            mins = int(restante.total_seconds() / 60)
            return True, f"Distribuicao DFe bloqueada ate {dt.strftime('%H:%M:%S')} ({mins}min restantes)"
        return False, ""
    except ValueError:
        return False, ""


def calcular_proximo_cooldown(minutos: int = COOLDOWN_MINUTOS) -> str:
    return (datetime.now() + timedelta(minutes=minutos)).isoformat(timespec="seconds")


def consultar(empresa: EmpresaConfig, chave: str) -> dict:
    uf = _uf_da_chave(chave) or empresa.uf
    con = ComunicacaoSefaz(
        uf, empresa.certificado.path, empresa.certificado.senha, empresa.homologacao
    )

    resp_sit = con.consulta_nota(modelo="nfe", chave=chave)
    xml_sit = etree.fromstring(resp_sit.content)
    salvar_resposta_sefaz(xml_sit, "consulta", chave)
    stats = xml_sit.xpath("//ns:cStat", namespaces=NS)
    motivos = xml_sit.xpath("//ns:xMotivo", namespaces=NS)
    situacao = [{"status": s.text, "motivo": m.text} for s, m in zip(stats, motivos)]

    # salva o XML apenas se a SEFAZ retornou um status de sucesso (1xx)
    primeiro_stat = situacao[0]["status"] if situacao else ""
    arquivo = None
    if primeiro_stat.startswith("1"):
        cnpj = empresa.emitente.cnpj
        os.makedirs(f"downloads/{cnpj}", exist_ok=True)
        xml_sit_str = etree.tostring(xml_sit, encoding="unicode", pretty_print=True)
        arquivo = f"downloads/{cnpj}/{chave}-situacao.xml"
        with open(arquivo, "w") as f:
            f.write('<?xml version="1.0" encoding="UTF-8"?>\n')
            f.write(xml_sit_str)

    return {
        "situacao": situacao,
        "arquivo": arquivo,
    }


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


def _processar_docs(xml_resp, documentos, cnpj: str):
    docs_xml = xml_resp.xpath("//ns:docZip", namespaces=NS)

    for doc in docs_xml:
        doc_nsu = doc.get("NSU", "")
        schema = doc.get("schema", "")
        try:
            xml_doc = DescompactaGzip.descompacta(doc.text)
            xml_str = etree.tostring(xml_doc, encoding="unicode", pretty_print=True)
            nome, chave = nome_arquivo_nsu(xml_doc, schema, doc_nsu)
            arquivo = f"downloads/{cnpj}/{nome}.xml"
            substituiu_resumo = os.path.exists(arquivo) and "procNFe" in schema
            with open(arquivo, "w") as f:
                f.write('<?xml version="1.0" encoding="UTF-8"?>\n')
                f.write(xml_str)
            documentos.append({
                "nsu": doc_nsu,
                "chave": chave,
                "schema": schema,
                "arquivo": arquivo,
                "substituiu_resumo": substituiu_resumo,
            })
        except Exception as e:
            documentos.append({
                "nsu": doc_nsu,
                "schema": schema,
                "erro": str(e),
            })


def listar_resumos_pendentes(cnpj: str) -> list[str]:
    """Retorna chaves dos resNFe pendentes em downloads/{cnpj}/."""
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


def consultar_dfe_chave(empresa: EmpresaConfig, chave: str) -> dict:
    """Baixa o documento DFe (procNFe) diretamente pela chave de acesso."""
    cnpj = empresa.emitente.cnpj
    con = ComunicacaoSefaz(
        empresa.uf, empresa.certificado.path, empresa.certificado.senha, empresa.homologacao
    )

    os.makedirs(f"downloads/{cnpj}", exist_ok=True)
    resp = con.consulta_distribuicao(cnpj=cnpj, chave=chave)
    xml_resp = etree.fromstring(resp.content if hasattr(resp, "content") else resp)

    status = xml_resp.xpath("//ns:cStat", namespaces=NS)
    motivo = xml_resp.xpath("//ns:xMotivo", namespaces=NS)
    c_stat = status[0].text if status else None
    x_motivo = motivo[0].text if motivo else None

    arquivo_resp = salvar_resposta_sefaz(xml_resp, "dist-dfe-chave", chave)

    documentos = []
    arquivo_cancelada = None
    if c_stat == "138":
        _processar_docs(xml_resp, documentos, cnpj)
    elif c_stat == "653":
        arquivo_cancelada = f"downloads/{cnpj}/{chave}-cancelada.xml"
        xml_str = etree.tostring(xml_resp, encoding="unicode", pretty_print=True)
        with open(arquivo_cancelada, "w") as f:
            f.write('<?xml version="1.0" encoding="UTF-8"?>\n')
            f.write(xml_str)
        resumo = f"downloads/{cnpj}/{chave}.xml"
        if os.path.exists(resumo):
            os.remove(resumo)

    return {
        "sucesso": c_stat == "138",
        "status": c_stat,
        "motivo": x_motivo,
        "documentos": documentos,
        "resposta": arquivo_resp,
        "arquivo_cancelada": arquivo_cancelada,
    }


def consultar_nsu(
    empresa: EmpresaConfig, estado: dict, state_file: str, nsu: int | None = None,
    callback=None,
) -> dict:
    cnpj = empresa.emitente.cnpj
    ambiente = "homologacao" if empresa.homologacao else "producao"

    bloqueado, msg = verificar_cooldown(get_cooldown(estado, cnpj, ambiente))
    if bloqueado:
        return {"sucesso": False, "motivo": msg, "documentos": []}

    if nsu is None:
        nsu = get_ultimo_nsu(estado, cnpj)

    con = ComunicacaoSefaz(
        empresa.uf, empresa.certificado.path, empresa.certificado.senha, empresa.homologacao
    )

    documentos = []
    ult_nsu = nsu
    max_nsu = nsu
    c_stat = None
    x_motivo = None
    pagina = 0

    os.makedirs(f"downloads/{cnpj}", exist_ok=True)
    respostas = []

    while True:
        pagina += 1
        resp = con.consulta_distribuicao(cnpj=cnpj, nsu=ult_nsu)

        xml_resp = etree.fromstring(resp.content if hasattr(resp, "content") else resp)
        status = xml_resp.xpath("//ns:cStat", namespaces=NS)
        motivo = xml_resp.xpath("//ns:xMotivo", namespaces=NS)

        c_stat = status[0].text if status else None
        x_motivo = motivo[0].text if motivo else None

        ult_nsu_el = xml_resp.xpath("//ns:ultNSU", namespaces=NS)
        max_nsu_el = xml_resp.xpath("//ns:maxNSU", namespaces=NS)
        ult_nsu = int(ult_nsu_el[0].text) if ult_nsu_el else ult_nsu
        max_nsu = int(max_nsu_el[0].text) if max_nsu_el else ult_nsu

        # salvar resposta bruta do servidor
        arquivo_resp = salvar_resposta_sefaz(xml_resp, "dist-dfe", f"{cnpj}-p{pagina:03d}")
        respostas.append(arquivo_resp)

        # qualquer status != 138 interrompe o loop
        if c_stat != "138":
            break

        _processar_docs(xml_resp, documentos, cnpj)

        set_ultimo_nsu(estado, cnpj, ult_nsu)
        salvar_estado(state_file, estado)

        if callback:
            callback(pagina, len(documentos), ult_nsu, max_nsu)

        # se ultNSU == maxNSU, nao ha mais documentos
        if ult_nsu >= max_nsu:
            break

    # cooldown so ativa em erros reais (656, etc.) — nao em 137 (fim normal) nem 138 (sucesso)
    if c_stat not in ("137", "138"):
        set_cooldown(estado, cnpj, calcular_proximo_cooldown(), ambiente)
        salvar_estado(state_file, estado)

    return {
        "sucesso": c_stat in ("137", "138"),
        "status": c_stat,
        "motivo": x_motivo,
        "ultimo_nsu": ult_nsu,
        "max_nsu": max_nsu,
        "documentos": documentos,
        "respostas": respostas,
    }
