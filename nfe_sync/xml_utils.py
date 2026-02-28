from pynfe.processamento.comunicacao import ComunicacaoSefaz
from pynfe.utils import etree

from .models import EmpresaConfig


def to_xml_string(element) -> str:
    """Serializa elemento lxml para string com declaração XML."""
    return '<?xml version="1.0" encoding="UTF-8"?>\n' + etree.tostring(
        element, encoding="unicode", pretty_print=True
    )


def extract_status_motivo(xml_resp, ns: dict) -> list[dict]:
    """Extrai pares cStat/xMotivo de uma resposta XML da SEFAZ."""
    stats = xml_resp.xpath("//ns:cStat", namespaces=ns)
    motivos = xml_resp.xpath("//ns:xMotivo", namespaces=ns)
    return [{"status": s.text, "motivo": m.text} for s, m in zip(stats, motivos)]


def criar_comunicacao(empresa: EmpresaConfig, uf: str | None = None) -> ComunicacaoSefaz:
    """Factory para ComunicacaoSefaz. Usa empresa.uf salvo se uf não for fornecido."""
    return ComunicacaoSefaz(
        uf if uf is not None else empresa.uf,
        empresa.certificado.path,
        empresa.certificado.senha,
        empresa.homologacao,
    )
