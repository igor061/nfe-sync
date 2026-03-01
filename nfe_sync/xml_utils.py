from datetime import datetime, timedelta, timezone

from pynfe.processamento.comunicacao import ComunicacaoSefaz
from pynfe.utils import etree

from .models import EmpresaConfig

_BRT = timezone(timedelta(hours=-3))


def agora_brt() -> datetime:
    """Retorna o datetime atual no fuso BRT (UTC-3) sem informação de timezone."""
    return datetime.now(_BRT).replace(tzinfo=None)

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


_SEFAZ_TIMEOUT = 30  # segundos


def criar_comunicacao(empresa: EmpresaConfig, uf: str | None = None) -> ComunicacaoSefaz:
    """Factory para ComunicacaoSefaz com timeout de 30s injetado via monkey-patch em _post.

    pynfe nao expoe timeout nos metodos publicos (exceto autorizacao/status_servico),
    mas _post() ja aceita o parametro — envolvemos para garantir timeout em todas as chamadas.
    Issue #11 / #19.
    """
    con = ComunicacaoSefaz(
        uf if uf is not None else empresa.uf,
        empresa.certificado.path,
        empresa.certificado.senha,
        empresa.homologacao,
    )
    _original_post = con._post

    def _post_com_timeout(url, xml, timeout=None):
        return _original_post(url, xml, timeout=timeout if timeout is not None else _SEFAZ_TIMEOUT)

    con._post = _post_com_timeout
    return con
