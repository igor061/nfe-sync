from pynfe.entidades.fonte_dados import FonteDados
from pynfe.entidades.evento import EventoManifestacaoDest
from pynfe.processamento.serializacao import SerializacaoXML
from pynfe.processamento.assinatura import AssinaturaA1

from .models import EmpresaConfig, validar_cnpj_sefaz
from .exceptions import NfeValidationError
from .xml_utils import extract_status_motivo, agora_brt, chamar_sefaz
from .results import ResultadoManifestacao


NS = {"ns": "http://www.portalfiscal.inf.br/nfe"}

OPERACOES = {
    "ciencia": (2, "Ciencia da Operacao"),
    "confirmacao": (1, "Confirmacao da Operacao"),
    "desconhecimento": (3, "Desconhecimento da Operacao"),
    "nao_realizada": (4, "Operacao nao Realizada"),
}


def manifestar(
    empresa: EmpresaConfig,
    operacao: str,
    chave: str,
    justificativa: str = "",
) -> ResultadoManifestacao:
    if operacao not in OPERACOES:
        raise NfeValidationError(
            f"[{empresa.nome}] Operacao '{operacao}' invalida. "
            f"Validas: {', '.join(OPERACOES.keys())}"
        )

    if len(chave) != 44 or not chave.isdigit():
        raise NfeValidationError(
            f"[{empresa.nome}] Chave de acesso deve ter 44 digitos, recebeu: '{chave}'"
        )

    if operacao == "nao_realizada" and len(justificativa) < 15:
        raise NfeValidationError(
            f"[{empresa.nome}] Operacao 'nao_realizada' exige justificativa "
            f"com minimo 15 caracteres (recebeu {len(justificativa)})."
        )

    validar_cnpj_sefaz(empresa.emitente.cnpj, empresa.nome)
    operacao_num, operacao_desc = OPERACOES[operacao]
    cnpj = empresa.emitente.cnpj

    fonte = FonteDados()
    evento_kwargs = dict(
        _fonte_dados=fonte,
        cnpj=cnpj,
        chave=chave,
        data_emissao=agora_brt(),
        uf="AN",
        operacao=operacao_num,
        n_seq_evento=1,
    )
    if operacao == "nao_realizada":
        evento_kwargs["justificativa"] = justificativa

    evento = EventoManifestacaoDest(**evento_kwargs)

    serializar = SerializacaoXML(fonte, homologacao=empresa.homologacao)
    xml_evento = serializar.serializar_evento(evento)

    assinatura = AssinaturaA1(empresa.certificado.path, empresa.certificado.senha)
    xml_assinado = assinatura.assinar(xml_evento)

    xml_resp, xml_resp_str = chamar_sefaz(empresa, "evento", modelo="nfe", evento=xml_assinado)
    resultados = extract_status_motivo(xml_resp, NS)
    protocolos = xml_resp.xpath("//ns:nProt", namespaces=NS)

    return ResultadoManifestacao(
        resultados=resultados,
        protocolo=protocolos[0].text if protocolos else None,
        xml=xml_resp_str,
        xml_resposta=xml_resp_str,
    )
