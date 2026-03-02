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
        set_ultimo_numero_nf(estado, "99999999000191", "1", 5)
        ultimo = get_ultimo_numero_nf(estado, "99999999000191", "1")
        numero_nf = ultimo + 1
        assert numero_nf == 6

    def test_numero_nf_default_zero(self):
        estado = {}
        ultimo = get_ultimo_numero_nf(estado, "99999999000191", "1")
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
        assert dest.numero_documento == "99999999000191"
        assert dest.endereco.uf == "SP"

    def test_campo_obrigatorio_faltando(self):
        with pytest.raises(ValidationError):
            DadosEmissao(destinatario=None, produtos=[], pagamentos=[])


class TestEmitirValidacaoEndereco:
    """#81: emitir() deve levantar NfeValidationError quando emitente.endereco é None.

    Destinatario.endereco é Endereco (obrigatório no Pydantic) — não pode ser None.
    A validação do destinatário sem endereço é lógica de montagem do CLI e fica em
    commands/emissao.py.
    """

    def test_emitente_sem_endereco_levanta_validation_error(self, dados_emissao_padrao):
        from nfe_sync.emissao import emitir
        from nfe_sync.exceptions import NfeValidationError
        from nfe_sync.models import EmpresaConfig, Certificado, Emitente
        empresa = EmpresaConfig(
            nome="SUL",
            certificado=Certificado(path="/tmp/cert.pfx", senha="123456"),
            emitente=Emitente(cnpj="99999999000191", endereco=None),
            uf="sp", homologacao=True,
        )
        with pytest.raises(NfeValidationError, match="endereco"):
            emitir(empresa, "1", 1, dados_emissao_padrao)


class TestComplementoTruncado:
    """Issue #54: complemento truncado a 60 chars na serialização para pynfe."""

    def test_complemento_longo_truncado(self):
        """Emitente com complemento > 60 chars: pynfe deve receber no máx 60."""
        from unittest.mock import patch, MagicMock, call
        from nfe_sync.models import EmpresaConfig, Certificado, Emitente

        complemento_longo = "QUADRA01                  LOTE  01                  LOJA  259"
        assert len(complemento_longo) > 60

        end = Endereco(
            logradouro="RUA EXEMPLO", numero="100",
            complemento=complemento_longo,
            bairro="CENTRO", municipio="SAO PAULO",
            cod_municipio="3550308", uf="SP", cep="01310100",
        )
        empresa = EmpresaConfig(
            nome="SUL",
            certificado=Certificado(path="/tmp/cert.pfx", senha="123456"),
            emitente=Emitente(cnpj="99999999000191", endereco=end),
            uf="sp", homologacao=True,
        )

        capturado = {}
        PynfeEmitenteMock = MagicMock(side_effect=lambda **kw: capturado.update(kw) or MagicMock())

        with patch("nfe_sync.emissao.PynfeEmitente", PynfeEmitenteMock):
            try:
                from nfe_sync.emissao import emitir
                from nfe_sync.models import DadosEmissao, Destinatario, Produto, Pagamento
                from decimal import Decimal
                dados = DadosEmissao(
                    destinatario=Destinatario(
                        razao_social="NF-E EMITIDA EM AMBIENTE DE HOMOLOGACAO - SEM VALOR FISCAL",
                        numero_documento="99999999000191",
                        endereco=end,
                    ),
                    produtos=[Produto(
                        codigo="0001", descricao="TESTE", ncm="71131100", cfop="5102",
                        quantidade_comercial=Decimal("1"), valor_unitario_comercial=Decimal("10"),
                        quantidade_tributavel=Decimal("1"), valor_unitario_tributavel=Decimal("10"),
                        valor_total_bruto=Decimal("10"),
                    )],
                    pagamentos=[Pagamento(tipo="01", valor=Decimal("10"))],
                )
                emitir(empresa, "1", 1, dados)
            except Exception:
                pass  # interessa apenas o argumento passado ao PynfeEmitente

        assert len(capturado.get("endereco_complemento", "")) <= 60
