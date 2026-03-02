"""Teste E2E de fluxo completo: emissão → consulta → manifestação → cancelamento.

Requer emitente e destinatário configurados:

    pytest tests/e2e/test_fluxo_completo.py -v \\
        --emitente SUL --destinatario SRNACIONAL --serie 99
"""
import re
import pytest
from .conftest import run_nfe


@pytest.fixture(scope="class")
def nf_fluxo(emitente, destinatario, serie):
    """Emite uma NF-e com destinatário e retorna {"chave": ..., "protocolo": ...}.

    Escopo class: emissão única compartilhada entre todos os testes da classe.
    Falha explicitamente se --destinatario não for fornecido.
    """
    if destinatario is None:
        pytest.fail("--destinatario e obrigatorio para TestFluxoCompleto")

    result = run_nfe("emitir", emitente, "--serie", serie, "--destinatario", destinatario)
    assert result.returncode == 0, f"Falha ao emitir NF-e:\n{result.stdout}\n{result.stderr}"

    match_chave = re.search(r"Chave: (\d{44})", result.stdout)
    assert match_chave, f"Chave nao encontrada na saida:\n{result.stdout}"

    match_prot = re.search(r"Protocolo: (\d+)", result.stdout)
    assert match_prot, f"Protocolo nao encontrado na saida:\n{result.stdout}"

    return {"chave": match_chave.group(1), "protocolo": match_prot.group(1)}


@pytest.mark.slow
class TestFluxoCompleto:
    """Fluxo E2E: emissão → consulta (emitente+dest) → manifestação → cancelamento → sincronização."""

    def test_emitir(self, nf_fluxo):
        """Etapa 1: NF-e emitida com sucesso, chave e protocolo capturados."""
        assert len(nf_fluxo["chave"]) == 44
        assert nf_fluxo["chave"].isdigit()
        assert nf_fluxo["protocolo"]

    def test_consultar_emitente(self, nf_fluxo, emitente):
        """Etapa 2: EMITENTE consulta a NF-e emitida — deve estar autorizada (cStat=100)."""
        result = run_nfe("consultar", emitente, nf_fluxo["chave"])
        assert result.returncode == 0, f"stdout: {result.stdout}\nstderr: {result.stderr}"
        assert re.search(r"cStat=100\b", result.stdout), f"cStat=100 nao encontrado:\n{result.stdout}"

    def test_consultar_destinatario(self, nf_fluxo, destinatario):
        """Etapa 3: DESTINATARIO consulta a mesma NF-e — deve estar autorizada (cStat=100)."""
        result = run_nfe("consultar", destinatario, nf_fluxo["chave"])
        assert result.returncode == 0, f"stdout: {result.stdout}\nstderr: {result.stderr}"
        assert re.search(r"cStat=100\b", result.stdout), f"cStat=100 nao encontrado:\n{result.stdout}"

    def test_manifestar_ciencia(self, nf_fluxo, destinatario):
        """Etapa 4: DESTINATARIO manifesta ciência da operação."""
        result = run_nfe("manifestar", destinatario, "ciencia", nf_fluxo["chave"])
        assert result.returncode == 0, f"stdout: {result.stdout}\nstderr: {result.stderr}"
        assert re.search(r"cStat=13[56]\b", result.stdout), f"cStat=135/136 nao encontrado:\n{result.stdout}"

    def test_cancelar(self, nf_fluxo, emitente):
        """Etapa 5: EMITENTE cancela a NF-e."""
        result = run_nfe(
            "cancelar", emitente, nf_fluxo["chave"],
            "--protocolo", nf_fluxo["protocolo"],
            "--justificativa", "Cancelamento de NF-e de teste E2E fluxo completo",
        )
        assert result.returncode == 0, f"stdout: {result.stdout}\nstderr: {result.stderr}"
        assert re.search(r"cStat=13[56]\b", result.stdout), f"cStat=135/136 nao encontrado:\n{result.stdout}"

    def test_consultar_cancelada(self, nf_fluxo, emitente):
        """Etapa 6: EMITENTE confirma que a NF-e está cancelada (cStat=101)."""
        result = run_nfe("consultar", emitente, nf_fluxo["chave"])
        assert result.returncode == 0, f"stdout: {result.stdout}\nstderr: {result.stderr}"
        assert re.search(r"cStat=101\b", result.stdout), f"cStat=101 nao encontrado:\n{result.stdout}"

