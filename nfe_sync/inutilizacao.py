from .models import EmpresaConfig, validar_cnpj_sefaz
from .exceptions import NfeValidationError
from .xml_utils import extract_status_motivo, chamar_sefaz
from .results import ResultadoInutilizacao


NS = {"ns": "http://www.portalfiscal.inf.br/nfe"}


def inutilizar(
    empresa: EmpresaConfig,
    serie: str,
    num_ini: int,
    num_fim: int,
    justificativa: str,
) -> ResultadoInutilizacao:
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

    xml_resp, xml_resp_str = chamar_sefaz(
        empresa, "inutilizacao",
        modelo="nfe", cnpj=cnpj,
        numero_inicial=num_ini, numero_final=num_fim,
        justificativa=justificativa, serie=serie,
    )
    resultados = extract_status_motivo(xml_resp, NS)
    protocolos = xml_resp.xpath("//ns:nProt", namespaces=NS)

    return ResultadoInutilizacao(
        sucesso=any(r["status"] == "102" for r in resultados),
        resultados=resultados,
        protocolo=protocolos[0].text if protocolos else None,
        xml=xml_resp_str,
        xml_resposta=xml_resp_str,
    )
