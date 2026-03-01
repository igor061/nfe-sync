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
    get_ultimo_nsu,
    set_ultimo_nsu,
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

    def test_salvar_sobrescreve_conteudo_anterior(self, tmp_path):
        """Issue #2: salvar_estado deve truncar antes de escrever."""
        f = str(tmp_path / "state.json")
        salvar_estado(f, {"a": 1})
        salvar_estado(f, {"b": 2})
        recarregado = carregar_estado(f)
        assert recarregado == {"b": 2}
        assert "a" not in recarregado

    def test_file_locking_sequencial(self, tmp_path):
        """Issue #2: múltiplas escritas sequenciais devem manter consistência."""
        import threading
        f = str(tmp_path / "state.json")
        erros = []

        def escrever(valor):
            try:
                salvar_estado(f, {"v": valor})
            except Exception as e:
                erros.append(e)

        threads = [threading.Thread(target=escrever, args=(i,)) for i in range(5)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert erros == []
        resultado = carregar_estado(f)
        assert "v" in resultado


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
        assert get_cooldown({}, "123", "homologacao") is None

    def test_set_e_get(self):
        estado = {}
        set_cooldown(estado, "123", "2026-02-26T18:37:32", "homologacao")
        assert get_cooldown(estado, "123", "homologacao") == "2026-02-26T18:37:32"

    def test_ambientes_independentes(self):
        estado = {}
        set_cooldown(estado, "123", "2026-02-26T18:00:00", "homologacao")
        set_cooldown(estado, "123", "2026-02-26T19:00:00", "producao")
        assert get_cooldown(estado, "123", "homologacao") == "2026-02-26T18:00:00"
        assert get_cooldown(estado, "123", "producao") == "2026-02-26T19:00:00"

    def test_limpar(self):
        estado = {"cooldown": {"123:homologacao": "2026-02-26T18:37:32"}}
        limpar_cooldown(estado, "123", "homologacao")
        assert get_cooldown(estado, "123", "homologacao") is None

    def test_limpar_nao_afeta_outro_ambiente(self):
        estado = {}
        set_cooldown(estado, "123", "2026-02-26T18:00:00", "homologacao")
        set_cooldown(estado, "123", "2026-02-26T19:00:00", "producao")
        limpar_cooldown(estado, "123", "homologacao")
        assert get_cooldown(estado, "123", "homologacao") is None
        assert get_cooldown(estado, "123", "producao") == "2026-02-26T19:00:00"

    def test_limpar_inexistente(self):
        estado = {}
        limpar_cooldown(estado, "123", "homologacao")  # nao deve dar erro


class TestNsu:
    def test_get_inexistente(self):
        assert get_ultimo_nsu({}, "123") == 0

    def test_set_e_get(self):
        estado = {}
        set_ultimo_nsu(estado, "123", 42)
        assert get_ultimo_nsu(estado, "123") == 42

    def test_multiplos_cnpjs(self):
        estado = {}
        set_ultimo_nsu(estado, "111", 10)
        set_ultimo_nsu(estado, "222", 20)
        assert get_ultimo_nsu(estado, "111") == 10
        assert get_ultimo_nsu(estado, "222") == 20
