import time
from datetime import datetime, timedelta, timezone

from pynfe.processamento.comunicacao import ComunicacaoSefaz
from pynfe.utils import etree

from .models import EmpresaConfig

_BRT = timezone(timedelta(hours=-3))


def agora_brt() -> datetime:
    """Retorna o datetime atual no fuso BRT (UTC-3), com tzinfo preservado."""
    return datetime.now(_BRT)


def agora_local() -> datetime:
    """Retorna o datetime atual no fuso horário LOCAL do sistema.

    Necessário para eventos pynfe: SerializacaoXML.serializar_evento() usa o
    timezone do SISTEMA (datetime.now().astimezone()) para montar o offset do
    campo dhEvento, ignorando o tzinfo do datetime recebido. Passar um datetime
    já convertido para o timezone local garante que o valor horário e o offset
    sejam consistentes — evitando cStat=577 quando o servidor está em fuso
    diferente do BRT. Issue #79.
    """
    return datetime.now().astimezone()

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


def _com_retry(fn, *args, tentativas=3, base=5, **kwargs):
    """Chama fn(*args, **kwargs) com retry exponencial (tentativas x, delay base*2^n segundos)."""
    for n in range(tentativas):
        try:
            return fn(*args, **kwargs)
        except Exception:
            if n == tentativas - 1:
                raise
            time.sleep(base * (2 ** n))


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


def chamar_sefaz(empresa: EmpresaConfig, fn_nome: str, *args,
                 uf: str | None = None, **kwargs):
    """Executa fn_nome na ComunicacaoSefaz com retry e retorna (xml_element, xml_string).

    fn_nome: nome do método de ComunicacaoSefaz (ex: 'consulta_nota', 'consulta_distribuicao').
    Centraliza: criar_comunicacao → _com_retry → safe_fromstring → to_xml_string.
    """
    con = criar_comunicacao(empresa, uf=uf or empresa.uf)
    fn = getattr(con, fn_nome)
    resp = _com_retry(fn, *args, **kwargs)
    content = resp.content if hasattr(resp, "content") else resp
    xml_el = safe_fromstring(content)
    return xml_el, to_xml_string(xml_el)
