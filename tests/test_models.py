"""Testes para models.py — Issue #6 (CNPJ mod-11)."""
import pytest
from pydantic import ValidationError

from nfe_sync.models import Emitente, validar_cnpj_sefaz, _calcular_dv_cnpj
from nfe_sync.exceptions import NfeValidationError


class TestCalcularDvCnpj:
    def test_cnpj_valido_conhecido(self):
        # CNPJ válido: 11.222.333/0001-81
        assert _calcular_dv_cnpj("11222333000181") is True

    def test_cnpj_dv_incorreto(self):
        assert _calcular_dv_cnpj("11222333000199") is False

    def test_cnpj_todos_zeros_exceto_dv(self):
        # 00000000000000 tem todos zeros — dv incorreto (seria 00 mas algoritmo dá 0/0)
        # Esse CNPJ seria válido matematicamente (0*pesos todos dão 0)
        assert _calcular_dv_cnpj("00000000000000") is True


class TestValidarCnpjSefaz:
    def test_cnpj_valido(self):
        validar_cnpj_sefaz("11222333000181")  # nao deve levantar

    def test_cnpj_curto(self):
        with pytest.raises(NfeValidationError, match="14 digitos"):
            validar_cnpj_sefaz("123")

    def test_cnpj_com_letras(self):
        with pytest.raises(NfeValidationError, match="14 digitos"):
            validar_cnpj_sefaz("1122233300018X")

    def test_cnpj_digitos_iguais(self):
        with pytest.raises(NfeValidationError, match="digitos iguais"):
            validar_cnpj_sefaz("11111111111111")

    def test_cnpj_mod11_invalido(self):
        with pytest.raises(NfeValidationError, match="verificadores"):
            validar_cnpj_sefaz("11222333000199")

    def test_contexto_no_erro(self):
        with pytest.raises(NfeValidationError, match=r"\[MinhaEmpresa\]"):
            validar_cnpj_sefaz("123", contexto="MinhaEmpresa")


class TestEmitenteValidarCnpj:
    def test_cnpj_valido_formatado(self):
        e = Emitente(cnpj="11.222.333/0001-81", razao_social="Teste")
        assert e.cnpj == "11222333000181"

    def test_cnpj_valido_sem_formatacao(self):
        e = Emitente(cnpj="11222333000181", razao_social="Teste")
        assert e.cnpj == "11222333000181"

    def test_cnpj_curto(self):
        with pytest.raises(ValidationError, match="14 digitos"):
            Emitente(cnpj="123")

    def test_cnpj_digitos_iguais(self):
        with pytest.raises(ValidationError, match="todos os digitos sao iguais"):
            Emitente(cnpj="11111111111111")

    def test_cnpj_mod11_invalido(self):
        with pytest.raises(ValidationError, match="verificadores"):
            Emitente(cnpj="11222333000199")
