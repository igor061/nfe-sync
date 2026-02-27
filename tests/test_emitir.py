from decimal import Decimal

import pytest
from pydantic import ValidationError

from nfe_sync.state import get_ultimo_numero_nf, set_ultimo_numero_nf
from nfe_sync.models import (
    Destinatario,
    Produto,
    Pagamento,
    DadosEmissao,
    Endereco,
)


class TestNumeroNF:
    def test_numero_nf_incrementa(self):
        estado = {}
        set_ultimo_numero_nf(estado, "10755237000136", "1", 5)
        ultimo = get_ultimo_numero_nf(estado, "10755237000136", "1")
        numero_nf = ultimo + 1
        assert numero_nf == 6

    def test_numero_nf_default_zero(self):
        estado = {}
        ultimo = get_ultimo_numero_nf(estado, "10755237000136", "1")
        assert ultimo == 0


class TestDestinatario:
    def test_criacao_com_defaults(self):
        dest = Destinatario(
            razao_social="Empresa Teste",
            numero_documento="12345678000190",
            endereco=Endereco(
                logradouro="Rua A",
                numero="10",
                bairro="Centro",
                municipio="Goiania",
                cod_municipio="5208707",
                uf="GO",
                cep="74000000",
            ),
        )
        assert dest.tipo_documento == "CNPJ"
        assert dest.indicador_ie == 9
        assert dest.inscricao_estadual == ""
        assert dest.email == ""

    def test_campo_obrigatorio_faltando(self):
        with pytest.raises(ValidationError):
            Destinatario(razao_social="Teste")


class TestProduto:
    def test_criacao_com_defaults(self):
        prod = Produto(
            codigo="0001",
            descricao="Produto X",
            ncm="71131100",
            cfop="5102",
            quantidade_comercial=Decimal("2.0000"),
            valor_unitario_comercial=Decimal("5.00"),
            quantidade_tributavel=Decimal("2.0000"),
            valor_unitario_tributavel=Decimal("5.00"),
            valor_total_bruto=Decimal("10.00"),
        )
        assert prod.unidade_comercial == "UN"
        assert prod.ean == "SEM GTIN"
        assert prod.icms_modalidade == "102"
        assert prod.pis_valor == Decimal("0.00")
        assert prod.cofins_valor == Decimal("0.00")

    def test_campo_obrigatorio_faltando(self):
        with pytest.raises(ValidationError):
            Produto(codigo="0001", descricao="X")


class TestPagamento:
    def test_criacao(self):
        pag = Pagamento(tipo="01", valor=Decimal("10.00"))
        assert pag.tipo == "01"
        assert pag.valor == Decimal("10.00")


class TestDadosEmissao:
    def test_criacao_com_defaults(self, dados_emissao_padrao):
        dados = dados_emissao_padrao
        assert dados.natureza_operacao == "VENDA DE MERCADORIA"
        assert dados.modelo == 55
        assert dados.transporte_modalidade_frete == 9
        assert len(dados.produtos) == 1
        assert len(dados.pagamentos) == 1

    def test_destinatario_acessivel(self, dados_emissao_padrao):
        dest = dados_emissao_padrao.destinatario
        assert dest.numero_documento == "10755237000136"
        assert dest.endereco.uf == "GO"

    def test_campo_obrigatorio_faltando(self):
        with pytest.raises(ValidationError):
            DadosEmissao(destinatario=None, produtos=[], pagamentos=[])
