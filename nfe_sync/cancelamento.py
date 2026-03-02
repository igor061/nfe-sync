from pynfe.entidades.fonte_dados import FonteDados
from pynfe.entidades.evento import EventoCancelarNota
from pynfe.processamento.serializacao import SerializacaoXML
from pynfe.processamento.assinatura import AssinaturaA1

from .models import EmpresaConfig, validar_cnpj_sefaz
from .exceptions import NfeValidationError
from .xml_utils import extract_status_motivo, agora_brt, chamar_sefaz
from .results import ResultadoCancelamento

NS = {"ns": "http://www.portalfiscal.inf.br/nfe"}


def cancelar(
    empresa: EmpresaConfig,
    chave: str,
    protocolo: str,
    justificativa: str,
) -> ResultadoCancelamento:
    if len(chave) != 44 or not chave.isdigit():
        raise NfeValidationError(f"[{empresa.nome}] Chave deve ter 44 digitos.")
    if len(justificativa) < 15:
        raise NfeValidationError(f"[{empresa.nome}] Justificativa minimo 15 chars.")
    validar_cnpj_sefaz(empresa.emitente.cnpj, empresa.nome)

    fonte = FonteDados()
    evento = EventoCancelarNota(
        _fonte_dados=fonte,
        cnpj=empresa.emitente.cnpj,
        chave=chave,
        data_emissao=agora_brt(),
        uf="AN",
        protocolo=protocolo,
        justificativa=justificativa,
        n_seq_evento=1,
    )

    xml_evento = SerializacaoXML(fonte, homologacao=empresa.homologacao).serializar_evento(evento)
    xml_assinado = AssinaturaA1(empresa.certificado.path, empresa.certificado.senha).assinar(xml_evento)

    xml_resp, xml_resp_str = chamar_sefaz(empresa, "evento", modelo="nfe", evento=xml_assinado)
    resultados = extract_status_motivo(xml_resp, NS)
    protocolos = xml_resp.xpath("//ns:nProt", namespaces=NS)

    return ResultadoCancelamento(
        sucesso=any(r["status"] in ("135", "136") for r in resultados),
        resultados=resultados,
        protocolo=protocolos[0].text if protocolos else None,
        xml=xml_resp_str,
        xml_resposta=xml_resp_str,
    )
