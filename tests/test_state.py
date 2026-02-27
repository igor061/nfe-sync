import json
import pytest
from nfe_sync.state import (
    carregar_estado,
    salvar_estado,
    get_ultimo_numero_nf,
    set_ultimo_numero_nf,
    get_cooldown,
    set_cooldown,
    limpar_cooldown,
)


class TestCarregarEstado:
    def test_arquivo_inexistente(self, tmp_path):
        estado = carregar_estado(str(tmp_path / "nao_existe.json"))
        assert estado == {}

    def test_arquivo_existente(self, tmp_path):
        f = tmp_path / "state.json"
        f.write_text('{"numeracao": {"123:1": 5}}')
        estado = carregar_estado(str(f))
        assert estado["numeracao"]["123:1"] == 5


class TestSalvarEstado:
    def test_salvar_e_recarregar(self, tmp_path):
        f = str(tmp_path / "state.json")
        estado = {"numeracao": {"123:1": 10}}
        salvar_estado(f, estado)
        recarregado = carregar_estado(f)
        assert recarregado == estado


class TestNumeracao:
    def test_get_inexistente(self):
        assert get_ultimo_numero_nf({}, "123", "1") == 0

    def test_set_e_get(self):
        estado = {}
        set_ultimo_numero_nf(estado, "123", "1", 5)
        assert get_ultimo_numero_nf(estado, "123", "1") == 5

    def test_multiplas_series(self):
        estado = {}
        set_ultimo_numero_nf(estado, "123", "1", 5)
        set_ultimo_numero_nf(estado, "123", "2", 12)
        assert get_ultimo_numero_nf(estado, "123", "1") == 5
        assert get_ultimo_numero_nf(estado, "123", "2") == 12


class TestCooldown:
    def test_get_inexistente(self):
        assert get_cooldown({}, "123") is None

    def test_set_e_get(self):
        estado = {}
        set_cooldown(estado, "123", "2026-02-26T18:37:32")
        assert get_cooldown(estado, "123") == "2026-02-26T18:37:32"

    def test_limpar(self):
        estado = {"cooldown": {"123": "2026-02-26T18:37:32"}}
        limpar_cooldown(estado, "123")
        assert get_cooldown(estado, "123") is None

    def test_limpar_inexistente(self):
        estado = {}
        limpar_cooldown(estado, "123")  # nao deve dar erro
