from decimal import Decimal

from pynfe.entidades.fonte_dados import FonteDados
from pynfe.entidades.emitente import Emitente as PynfeEmitente
from pynfe.entidades.cliente import Cliente
from pynfe.entidades.notafiscal import NotaFiscal
from pynfe.processamento.serializacao import SerializacaoXML
from pynfe.processamento.assinatura import AssinaturaA1

from .models import EmpresaConfig, DadosEmissao, validar_cnpj_sefaz
from .xml_utils import to_xml_string, extract_status_motivo, criar_comunicacao, safe_fromstring, agora_brt
from .results import ResultadoEmissao


NS = {"ns": "http://www.portalfiscal.inf.br/nfe"}


def emitir(empresa: EmpresaConfig, serie: str, numero_nf: int, dados: DadosEmissao) -> ResultadoEmissao:
    validar_cnpj_sefaz(empresa.emitente.cnpj, empresa.nome)
    fonte = FonteDados()
    emi = empresa.emitente
    end = emi.endereco

    emitente = PynfeEmitente(
        _fonte_dados=fonte,
        razao_social=emi.razao_social,
        nome_fantasia=emi.nome_fantasia,
        cnpj=emi.cnpj,
        inscricao_estadual=emi.inscricao_estadual,
        cnae_fiscal=emi.cnae_fiscal,
        codigo_de_regime_tributario=emi.regime_tributario,
        endereco_logradouro=end.logradouro,
        endereco_numero=end.numero,
        endereco_complemento=end.complemento,
        endereco_bairro=end.bairro,
        endereco_municipio=end.municipio,
        endereco_cod_municipio=end.cod_municipio,
        endereco_uf=end.uf,
        endereco_cep=end.cep,
    )

    dest = dados.destinatario
    dest_end = dest.endereco
    cliente = Cliente(
        _fonte_dados=fonte,
        razao_social=dest.razao_social,
        tipo_documento=dest.tipo_documento,
        numero_documento=dest.numero_documento,
        inscricao_estadual=dest.inscricao_estadual,
        indicador_ie=dest.indicador_ie,
        endereco_logradouro=dest_end.logradouro,
        endereco_numero=dest_end.numero,
        endereco_bairro=dest_end.bairro,
        endereco_municipio=dest_end.municipio,
        endereco_cod_municipio=dest_end.cod_municipio,
        endereco_uf=dest_end.uf,
        endereco_cep=dest_end.cep,
        endereco_pais="1058",
    )

    nota = NotaFiscal(
        _fonte_dados=fonte,
        emitente=emitente,
        cliente=cliente,
        uf=end.uf,
        natureza_operacao=dados.natureza_operacao,
        forma_emissao=dados.forma_emissao,
        finalidade_emissao=dados.finalidade_emissao,
        processo_emissao=dados.processo_emissao,
        modelo=dados.modelo,
        serie=serie,
        numero_nf=str(numero_nf),
        tipo_documento=dados.tipo_documento,
        tipo_impressao_danfe=dados.tipo_impressao_danfe,
        cliente_final=dados.cliente_final,
        indicador_destino=dados.indicador_destino,
        indicador_presencial=dados.indicador_presencial,
        indicador_intermediador=dados.indicador_intermediador,
        transporte_modalidade_frete=dados.transporte_modalidade_frete,
        informacoes_complementares_interesse_contribuinte=dados.informacoes_complementares,
        data_emissao=agora_brt(),
        data_saida_entrada=agora_brt(),
        municipio=end.cod_municipio,
    )

    for prod in dados.produtos:
        nota.adicionar_produto_servico(
            codigo=prod.codigo,
            descricao=prod.descricao,
            ncm=prod.ncm,
            cfop=prod.cfop,
            unidade_comercial=prod.unidade_comercial,
            quantidade_comercial=prod.quantidade_comercial,
            valor_unitario_comercial=prod.valor_unitario_comercial,
            unidade_tributavel=prod.unidade_tributavel,
            quantidade_tributavel=prod.quantidade_tributavel,
            valor_unitario_tributavel=prod.valor_unitario_tributavel,
            ean=prod.ean,
            ean_tributavel=prod.ean_tributavel,
            ind_total=prod.ind_total,
            valor_total_bruto=prod.valor_total_bruto,
            valor_tributos_aprox=prod.valor_tributos_aprox,
            icms_modalidade=prod.icms_modalidade,
            icms_csosn=prod.icms_csosn,
            icms_origem=prod.icms_origem,
            pis_modalidade=prod.pis_modalidade,
            pis_valor_base_calculo=prod.pis_valor_base_calculo,
            pis_aliquota_percentual=prod.pis_aliquota_percentual,
            pis_aliquota_reais=prod.pis_aliquota_reais,
            pis_valor=prod.pis_valor,
            cofins_modalidade=prod.cofins_modalidade,
            cofins_valor_base_calculo=prod.cofins_valor_base_calculo,
            cofins_aliquota_percentual=prod.cofins_aliquota_percentual,
            cofins_aliquota_reais=prod.cofins_aliquota_reais,
            cofins_valor=prod.cofins_valor,
        )

    for pag in dados.pagamentos:
        nota.adicionar_pagamento(t_pag=pag.tipo, v_pag=pag.valor)

    serializar = SerializacaoXML(fonte, homologacao=empresa.homologacao)
    xml = serializar.exportar(limpar=False)

    assinatura = AssinaturaA1(empresa.certificado.path, empresa.certificado.senha)
    xml_assinado = assinatura.assinar(xml)

    con = criar_comunicacao(empresa)
    resposta = con.autorizacao(modelo="nfe", nota_fiscal=xml_assinado)

    if isinstance(resposta, tuple):
        codigo = resposta[0]
        if codigo == 0:
            nfe_proc = resposta[1]
            status = nfe_proc.xpath("//ns:protNFe/ns:infProt/ns:cStat", namespaces=NS)
            motivo = nfe_proc.xpath("//ns:protNFe/ns:infProt/ns:xMotivo", namespaces=NS)
            protocolo = nfe_proc.xpath("//ns:protNFe/ns:infProt/ns:nProt", namespaces=NS)
            chave = nfe_proc.xpath("//ns:protNFe/ns:infProt/ns:chNFe", namespaces=NS)
            chave_txt = chave[0].text if chave else "nfe"

            return ResultadoEmissao(
                sucesso=True,
                status=status[0].text if status else None,
                motivo=motivo[0].text if motivo else None,
                protocolo=protocolo[0].text if protocolo else None,
                chave=chave_txt,
                xml=to_xml_string(nfe_proc),
                xml_resposta=None,
                erros=[],
            )
        else:
            http_resp = resposta[1]
            xml_resposta = None
            try:
                body = safe_fromstring(
                    http_resp.content if hasattr(http_resp, "content") else http_resp
                )
                erros = extract_status_motivo(body, NS)
                xml_resposta = to_xml_string(body)
            except Exception:
                erros = [{"status": str(codigo), "motivo": "Erro ao parsear resposta"}]
            return ResultadoEmissao(
                sucesso=False, status=None, motivo=None,
                protocolo=None, chave=None, xml=None,
                xml_resposta=xml_resposta, erros=erros,
            )
    else:
        return ResultadoEmissao(
            sucesso=False, status=None, motivo=None,
            protocolo=None, chave=None, xml=None,
            xml_resposta=None, erros=[{"status": None, "motivo": str(resposta)}],
        )
