import os
from datetime import datetime

from pynfe.entidades.fonte_dados import FonteDados
from pynfe.entidades.evento import EventoManifestacaoDest
from pynfe.processamento.serializacao import SerializacaoXML
from pynfe.processamento.assinatura import AssinaturaA1
from pynfe.processamento.comunicacao import ComunicacaoSefaz
from pynfe.utils import etree

from .models import EmpresaConfig
from .exceptions import NfeValidationError


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
) -> dict:
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

    operacao_num, operacao_desc = OPERACOES[operacao]
    cnpj = empresa.emitente.cnpj

    fonte = FonteDados()
    evento_kwargs = dict(
        _fonte_dados=fonte,
        cnpj=cnpj,
        chave=chave,
        data_emissao=datetime.now(),
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

    con = ComunicacaoSefaz(
        empresa.uf, empresa.certificado.path, empresa.certificado.senha, empresa.homologacao
    )
    resposta = con.evento(modelo="nfe", evento=xml_assinado)

    ns = {"ns": "http://www.portalfiscal.inf.br/nfe"}
    xml_resp = etree.fromstring(resposta.content)

    stats = xml_resp.xpath("//ns:cStat", namespaces=ns)
    motivos = xml_resp.xpath("//ns:xMotivo", namespaces=ns)
    protocolos = xml_resp.xpath("//ns:nProt", namespaces=ns)

    os.makedirs("xml/eventos", exist_ok=True)
    arquivo = f"xml/eventos/{chave}-{operacao}.xml"
    xml_resp_str = etree.tostring(xml_resp, encoding="unicode", pretty_print=True)
    with open(arquivo, "w") as f:
        f.write('<?xml version="1.0" encoding="UTF-8"?>\n')
        f.write(xml_resp_str)

    return {
        "operacao": operacao_desc,
        "resultados": [{"status": s.text, "motivo": m.text} for s, m in zip(stats, motivos)],
        "protocolo": protocolos[0].text if protocolos else None,
        "arquivo": arquivo,
    }
