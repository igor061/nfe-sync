from datetime import datetime, timedelta
import pytest

from nfe_sync.consulta import verificar_cooldown, calcular_proximo_cooldown


class TestVerificarCooldown:
    def test_sem_bloqueio(self):
        bloqueado, msg = verificar_cooldown(None)
        assert bloqueado is False
        assert msg == ""

    def test_string_vazia(self):
        bloqueado, msg = verificar_cooldown("")
        assert bloqueado is False
        assert msg == ""

    def test_expirado(self):
        passado = (datetime.now() - timedelta(hours=2)).isoformat(timespec="seconds")
        bloqueado, msg = verificar_cooldown(passado)
        assert bloqueado is False
        assert msg == ""

    def test_ativo(self):
        futuro = (datetime.now() + timedelta(hours=1)).isoformat(timespec="seconds")
        bloqueado, msg = verificar_cooldown(futuro)
        assert bloqueado is True
        assert "bloqueada ate" in msg

    def test_valor_invalido(self):
        bloqueado, msg = verificar_cooldown("lixo")
        assert bloqueado is False
        assert msg == ""


class TestCalcularProximoCooldown:
    def test_retorna_iso_futuro(self):
        resultado = calcular_proximo_cooldown(60)
        dt = datetime.fromisoformat(resultado)
        assert dt > datetime.now()
