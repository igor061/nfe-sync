import pytest
from decimal import Decimal
from nfe_sync.models import (
    Certificado,
    Emitente,
    Endereco,
    EmpresaConfig,
    Destinatario,
    Produto,
    Pagamento,
    DadosEmissao,
)


CHAVE_VALIDA = "52260210755237000136550010000000031361413250"

ENDERECO_PADRAO = Endereco(
    logradouro="ROD BR 040 KM 12 GLEBA F",
    numero="SN",
    complemento="QUADRA01 LOTE 01 LOJA 259",
    bairro="PARQUE ESPLANADA III",
    municipio="VALPARAISO DE GOIAS",
    cod_municipio="5221858",
    uf="GO",
    cep="72876902",
)

EMITENTE_PADRAO = Emitente(
    cnpj="10755237000136",
    razao_social="RM VALPARAISO JOIAS LTDA",
    nome_fantasia="CORALLI JOIAS",
    inscricao_estadual="104452420",
    cnae_fiscal="4783101",
    regime_tributario="1",
    endereco=ENDERECO_PADRAO,
)


@pytest.fixture
def empresa_sul():
    return EmpresaConfig(
        nome="SUL",
        certificado=Certificado(path="/tmp/cert.pfx", senha="123456"),
        emitente=EMITENTE_PADRAO,
        uf="go",
        homologacao=True,
    )


@pytest.fixture
def dados_emissao_padrao():
    return DadosEmissao(
        destinatario=Destinatario(
            razao_social="NF-E EMITIDA EM AMBIENTE DE HOMOLOGACAO - SEM VALOR FISCAL",
            tipo_documento="CNPJ",
            numero_documento="10755237000136",
            indicador_ie=1,
            inscricao_estadual="104452420",
            endereco=ENDERECO_PADRAO,
        ),
        produtos=[
            Produto(
                codigo="0001",
                descricao="PRODUTO TESTE HOMOLOGACAO",
                ncm="71131100",
                cfop="5102",
                quantidade_comercial=Decimal("1.0000"),
                valor_unitario_comercial=Decimal("10.00"),
                quantidade_tributavel=Decimal("1.0000"),
                valor_unitario_tributavel=Decimal("10.00"),
                valor_total_bruto=Decimal("10.00"),
            ),
        ],
        pagamentos=[
            Pagamento(tipo="01", valor=Decimal("10.00")),
        ],
        informacoes_complementares="NF-e de teste emitida em homologacao.",
    )
