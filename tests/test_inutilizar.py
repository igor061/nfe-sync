import pytest
from nfe_sync.inutilizacao import inutilizar
from nfe_sync.exceptions import NfeValidationError


JUSTIFICATIVA_VALIDA = "Numero pulado por erro de sistema"


class TestInutilizarValidacao:
    def test_justificativa_curta(self, empresa_sul):
        with pytest.raises(NfeValidationError, match="15 caracteres"):
            inutilizar(empresa_sul, "1", 10, 10, "curta")

    def test_numero_inicial_maior_que_final(self, empresa_sul):
        with pytest.raises(NfeValidationError, match="menor ou igual"):
            inutilizar(empresa_sul, "1", 10, 5, JUSTIFICATIVA_VALIDA)
