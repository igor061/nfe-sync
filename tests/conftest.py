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


CHAVE_VALIDA = "52991299999999999999550010000000011000000010"

ENDERECO_PADRAO = Endereco(
    logradouro="RUA EXEMPLO",
    numero="100",
    complemento="SALA 01",
    bairro="CENTRO",
    municipio="SAO PAULO",
    cod_municipio="3550308",
    uf="SP",
    cep="01310100",
)

EMITENTE_PADRAO = Emitente(
    cnpj="99999999000191",
    razao_social="EMPRESA TESTE LTDA",
    nome_fantasia="EMPRESA TESTE",
    inscricao_estadual="111111111111",
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
        uf="sp",
        homologacao=True,
    )


@pytest.fixture
def dados_emissao_padrao():
    return DadosEmissao(
        destinatario=Destinatario(
            razao_social="NF-E EMITIDA EM AMBIENTE DE HOMOLOGACAO - SEM VALOR FISCAL",
            tipo_documento="CNPJ",
            numero_documento="99999999000191",
            indicador_ie=1,
            inscricao_estadual="111111111111",
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
