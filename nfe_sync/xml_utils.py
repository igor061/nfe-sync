from pynfe.processamento.comunicacao import ComunicacaoSefaz
from pynfe.utils import etree

from .models import EmpresaConfig

# Seguro contra ataques XXE: sem resolucao de entidades externas ou DTD
# Issue #3
_PARSER = etree.XMLParser(resolve_entities=False, no_network=True, load_dtd=False)


def safe_fromstring(data: bytes):
    """Parse XML a partir de bytes usando parser seguro (sem XXE)."""
    return etree.fromstring(data, parser=_PARSER)


def safe_parse(path: str):
    """Parse XML a partir de arquivo usando parser seguro (sem XXE)."""
    return etree.parse(path, parser=_PARSER)


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
    # pynfe nao expoe parametro timeout em ComunicacaoSefaz — limitacao conhecida (Issue #11)
    return ComunicacaoSefaz(
        uf if uf is not None else empresa.uf,
        empresa.certificado.path,
        empresa.certificado.senha,
        empresa.homologacao,
    )
