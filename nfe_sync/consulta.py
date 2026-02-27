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
    salvar_resposta_sefaz(xml_sit, "consulta", chave)
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


def _processar_docs(xml_resp, documentos):
    docs_xml = xml_resp.xpath("//ns:docZip", namespaces=NS)

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

    os.makedirs("downloads/nsu", exist_ok=True)
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

        _processar_docs(xml_resp, documentos)

        set_ultimo_nsu(estado, cnpj, ult_nsu)
        salvar_estado(state_file, estado)

        if callback:
            callback(pagina, len(documentos), ult_nsu, max_nsu)

        # se ultNSU == maxNSU, nao ha mais documentos
        if ult_nsu >= max_nsu:
            break

    # cooldown so ativa quando nao ha mais documentos (137) ou erro (656 etc)
    if not documentos or c_stat != "138":
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
