import os
from datetime import datetime, timedelta

from pynfe.processamento.comunicacao import ComunicacaoSefaz
from pynfe.utils import etree
from pynfe.utils.descompactar import DescompactaGzip

from .models import EmpresaConfig


COOLDOWN_MINUTOS = 61


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
    ns = {"ns": "http://www.portalfiscal.inf.br/nfe"}

    resp_sit = con.consulta_nota(modelo="nfe", chave=chave)
    xml_sit = etree.fromstring(resp_sit.content)
    stats = xml_sit.xpath("//ns:cStat", namespaces=ns)
    motivos = xml_sit.xpath("//ns:xMotivo", namespaces=ns)
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
