from pynfe.processamento.comunicacao import ComunicacaoSefaz
from pynfe.utils import etree

from .models import EmpresaConfig
from .exceptions import NfeValidationError


def inutilizar(
    empresa: EmpresaConfig,
    serie: str,
    num_ini: int,
    num_fim: int,
    justificativa: str,
) -> dict:
    if len(justificativa) < 15:
        raise NfeValidationError(
            f"[{empresa.nome}] Justificativa deve ter no minimo 15 caracteres "
            f"(recebeu {len(justificativa)})."
        )

    if num_ini > num_fim:
        raise NfeValidationError(
            f"[{empresa.nome}] numero_inicial ({num_ini}) deve ser "
            f"menor ou igual a numero_final ({num_fim})."
        )

    cnpj = empresa.emitente.cnpj

    con = ComunicacaoSefaz(
        empresa.uf, empresa.certificado.path, empresa.certificado.senha, empresa.homologacao
    )
    resposta = con.inutilizacao(
        modelo="nfe",
        cnpj=cnpj,
        numero_inicial=num_ini,
        numero_final=num_fim,
        justificativa=justificativa,
        serie=serie,
    )

    ns = {"ns": "http://www.portalfiscal.inf.br/nfe"}
    xml_resp = etree.fromstring(resposta.content)
    xml_resp_str = '<?xml version="1.0" encoding="UTF-8"?>\n' + etree.tostring(xml_resp, encoding="unicode", pretty_print=True)

    stats = xml_resp.xpath("//ns:cStat", namespaces=ns)
    motivos = xml_resp.xpath("//ns:xMotivo", namespaces=ns)
    protocolos = xml_resp.xpath("//ns:nProt", namespaces=ns)

    return {
        "resultados": [{"status": s.text, "motivo": m.text} for s, m in zip(stats, motivos)],
        "protocolo": protocolos[0].text if protocolos else None,
        "xml": xml_resp_str,
        "xml_resposta": xml_resp_str,
    }
