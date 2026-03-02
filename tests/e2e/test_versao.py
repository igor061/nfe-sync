"""Smoke tests — verificam que o CLI responde sem chamar a SEFAZ."""
from .conftest import run_nfe


class TestSmoke:
    def test_help_retorna_zero(self):
        result = run_nfe("--help")
        assert result.returncode == 0

    def test_help_lista_subcomandos(self):
        result = run_nfe("--help")
        assert "emitir" in result.stdout
        assert "consultar" in result.stdout
        assert "manifestar" in result.stdout
        assert "inutilizar" in result.stdout

    def test_subcomando_inexistente_retorna_erro(self):
        result = run_nfe("subcomando-inexistente")
        assert result.returncode != 0
