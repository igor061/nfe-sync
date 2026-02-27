import pytest
from nfe_sync.manifestacao import manifestar, OPERACOES
from nfe_sync.exceptions import NfeValidationError
from tests.conftest import CHAVE_VALIDA


class TestManifestarValidacao:
    def test_operacao_invalida(self, empresa_sul):
        with pytest.raises(NfeValidationError, match="invalida"):
            manifestar(empresa_sul, "invalida", CHAVE_VALIDA)

    def test_chave_invalida(self, empresa_sul):
        with pytest.raises(NfeValidationError, match="44 digitos"):
            manifestar(empresa_sul, "ciencia", "123")

    def test_nao_realizada_sem_justificativa(self, empresa_sul):
        with pytest.raises(NfeValidationError, match="15 caracteres"):
            manifestar(empresa_sul, "nao_realizada", CHAVE_VALIDA)

    def test_nao_realizada_justificativa_curta(self, empresa_sul):
        with pytest.raises(NfeValidationError, match="15 caracteres"):
            manifestar(empresa_sul, "nao_realizada", CHAVE_VALIDA, "curta")

    def test_operacoes_disponiveis(self):
        assert "ciencia" in OPERACOES
        assert "confirmacao" in OPERACOES
        assert "desconhecimento" in OPERACOES
        assert "nao_realizada" in OPERACOES
