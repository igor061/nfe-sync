from .models import EmpresaConfig, validar_cnpj_sefaz
from .exceptions import NfeValidationError
from .xml_utils import to_xml_string, extract_status_motivo, criar_comunicacao, safe_fromstring
from .results import ResultadoInutilizacao


NS = {"ns": "http://www.portalfiscal.inf.br/nfe"}


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

    validar_cnpj_sefaz(empresa.emitente.cnpj, empresa.nome)
    cnpj = empresa.emitente.cnpj

    con = criar_comunicacao(empresa)
    resposta = con.inutilizacao(
        modelo="nfe",
        cnpj=cnpj,
        numero_inicial=num_ini,
        numero_final=num_fim,
        justificativa=justificativa,
        serie=serie,
    )

    xml_resp = safe_fromstring(resposta.content)
    xml_resp_str = to_xml_string(xml_resp)
    resultados = extract_status_motivo(xml_resp, NS)
    protocolos = xml_resp.xpath("//ns:nProt", namespaces=NS)

    return ResultadoInutilizacao(
        resultados=resultados,
        protocolo=protocolos[0].text if protocolos else None,
        xml=xml_resp_str,
        xml_resposta=xml_resp_str,
    )
