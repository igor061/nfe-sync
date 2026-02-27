import os

from pynfe.processamento.comunicacao import ComunicacaoSefaz
from pynfe.utils import etree

from .models import EmpresaConfig
from .exceptions import NfeValidationError
from .log import salvar_resposta_sefaz


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
    salvar_resposta_sefaz(xml_resp, "inutilizacao", f"{cnpj}-serie{serie}-{num_ini}-{num_fim}")

    stats = xml_resp.xpath("//ns:cStat", namespaces=ns)
    motivos = xml_resp.xpath("//ns:xMotivo", namespaces=ns)
    protocolos = xml_resp.xpath("//ns:nProt", namespaces=ns)

    os.makedirs("xml/inutilizacao", exist_ok=True)
    arquivo = f"xml/inutilizacao/inut-serie{serie}-{num_ini}-{num_fim}.xml"
    xml_resp_str = etree.tostring(xml_resp, encoding="unicode", pretty_print=True)
    with open(arquivo, "w") as f:
        f.write('<?xml version="1.0" encoding="UTF-8"?>\n')
        f.write(xml_resp_str)

    return {
        "resultados": [{"status": s.text, "motivo": m.text} for s, m in zip(stats, motivos)],
        "protocolo": protocolos[0].text if protocolos else None,
        "arquivo": arquivo,
    }
