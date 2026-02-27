import os
from datetime import datetime, timedelta

from pynfe.processamento.comunicacao import ComunicacaoSefaz
from pynfe.utils import etree
from pynfe.utils.descompactar import DescompactaGzip

from .models import EmpresaConfig
from .state import get_ultimo_nsu, set_ultimo_nsu, get_cooldown, set_cooldown, salvar_estado


COOLDOWN_MINUTOS = 61
NS = {"ns": "http://www.portalfiscal.inf.br/nfe"}


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
    con = ComunicacaoSefaz(
        empresa.uf, empresa.certificado.path, empresa.certificado.senha, empresa.homologacao
    )

    resp_sit = con.consulta_nota(modelo="nfe", chave=chave)
    xml_sit = etree.fromstring(resp_sit.content)
    stats = xml_sit.xpath("//ns:cStat", namespaces=NS)
    motivos = xml_sit.xpath("//ns:xMotivo", namespaces=NS)
    situacao = [{"status": s.text, "motivo": m.text} for s, m in zip(stats, motivos)]

    os.makedirs("downloads", exist_ok=True)
    xml_sit_str = etree.tostring(xml_sit, encoding="unicode", pretty_print=True)
    arquivo = f"downloads/{chave}-situacao.xml"
    with open(arquivo, "w") as f:
        f.write('<?xml version="1.0" encoding="UTF-8"?>\n')
        f.write(xml_sit_str)

    return {
        "situacao": situacao,
        "arquivo": arquivo,
    }


def consultar_nsu(
    empresa: EmpresaConfig, estado: dict, state_file: str, nsu: int | None = None
) -> dict:
    cnpj = empresa.emitente.cnpj

    bloqueado, msg = verificar_cooldown(get_cooldown(estado, cnpj))
    if bloqueado:
        return {"sucesso": False, "motivo": msg, "documentos": []}

    if nsu is None:
        nsu = get_ultimo_nsu(estado, cnpj)

    con = ComunicacaoSefaz(
        empresa.uf, empresa.certificado.path, empresa.certificado.senha, empresa.homologacao
    )
    resp = con.consulta_distribuicao(cnpj=cnpj, nsu=nsu)

    xml_resp = etree.fromstring(resp.content if hasattr(resp, "content") else resp)
    status = xml_resp.xpath("//ns:cStat", namespaces=NS)
    motivo = xml_resp.xpath("//ns:xMotivo", namespaces=NS)

    c_stat = status[0].text if status else None
    x_motivo = motivo[0].text if motivo else None

    # 137 = nenhum documento localizado
    # 138 = documento localizado
    if c_stat == "137":
        return {"sucesso": True, "status": c_stat, "motivo": x_motivo, "documentos": []}

    ult_nsu_el = xml_resp.xpath("//ns:ultNSU", namespaces=NS)
    max_nsu_el = xml_resp.xpath("//ns:maxNSU", namespaces=NS)
    ult_nsu = int(ult_nsu_el[0].text) if ult_nsu_el else nsu
    max_nsu = int(max_nsu_el[0].text) if max_nsu_el else ult_nsu

    docs_xml = xml_resp.xpath("//ns:docZip", namespaces=NS)
    documentos = []
    os.makedirs("downloads/nsu", exist_ok=True)

    for doc in docs_xml:
        doc_nsu = doc.get("NSU", "")
        schema = doc.get("schema", "")
        try:
            xml_doc = DescompactaGzip.descompacta(doc.text)
            xml_str = etree.tostring(xml_doc, encoding="unicode", pretty_print=True)
            arquivo = f"downloads/nsu/{doc_nsu}.xml"
            with open(arquivo, "w") as f:
                f.write('<?xml version="1.0" encoding="UTF-8"?>\n')
                f.write(xml_str)
            documentos.append({
                "nsu": doc_nsu,
                "schema": schema,
                "arquivo": arquivo,
            })
        except Exception as e:
            documentos.append({
                "nsu": doc_nsu,
                "schema": schema,
                "erro": str(e),
            })

    set_ultimo_nsu(estado, cnpj, ult_nsu)
    set_cooldown(estado, cnpj, calcular_proximo_cooldown())
    salvar_estado(state_file, estado)

    return {
        "sucesso": c_stat == "138",
        "status": c_stat,
        "motivo": x_motivo,
        "ultimo_nsu": ult_nsu,
        "max_nsu": max_nsu,
        "documentos": documentos,
    }
