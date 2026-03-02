"""Testes E2E com chamadas reais à SEFAZ — requerem certificado e empresas configuradas.

Executar com:
    pytest tests/e2e/test_e2e_homolog.py -m slow \
        --emitente MINHAEMPRESA \
        --destinatario OUTRAEMPRESA \
        --serie 99 \
        -v
"""
import os
import re
import pytest
from .conftest import run_nfe


@pytest.fixture(scope="session")
def nf_emitida(emitente, serie):
    """Emite uma NF-e de teste e retorna (chave, numero). Escopo session:
    emite uma única vez e compartilha entre testes — evita cStat=539 (#66).
    """
    result = run_nfe("emitir", emitente, "--serie", serie)
    assert result.returncode == 0, f"Falha ao emitir NF fixture:\n{result.stdout}"
    match = re.search(r"Chave: (\d{44})", result.stdout)
    assert match, f"Chave não encontrada:\n{result.stdout}"
    match_num = re.search(r"Numero NF (\d+) serie", result.stdout)
    assert match_num
    return match.group(1), int(match_num.group(1))


@pytest.mark.slow
class TestEmitirHomologacao:
    def test_emitir_cria_xml(self, nf_emitida):
        chave, _ = nf_emitida
        xml_path = os.path.join(os.getcwd(), "xml", f"{chave}.xml")
        assert os.path.exists(xml_path), f"XML não criado em {xml_path}"

    def test_emitir_com_destinatario(self, emitente, destinatario, serie):
        if destinatario is None:
            pytest.skip("--destinatario nao fornecido")

        result = run_nfe(
            "emitir", emitente,
            "--serie", serie,
            "--destinatario", destinatario,
        )

        assert result.returncode == 0, f"stdout: {result.stdout}\nstderr: {result.stderr}"
        assert "Status:" in result.stdout

    def test_emitir_incrementa_numero(self, emitente, serie):
        result1 = run_nfe("emitir", emitente, "--serie", serie)
        assert result1.returncode == 0, result1.stdout
        match1 = re.search(r"Numero NF (\d+) serie", result1.stdout)
        assert match1

        result2 = run_nfe("emitir", emitente, "--serie", serie)
        assert result2.returncode == 0, result2.stdout
        match2 = re.search(r"Numero NF (\d+) serie", result2.stdout)
        assert match2

        assert int(match2.group(1)) == int(match1.group(1)) + 1


@pytest.mark.slow
class TestConsultarNsuHomologacao:
    def test_consultar_nsu_executa_sem_erro(self, emitente):
        result = run_nfe("consultar-nsu", emitente)

        # 656 = consumo indevido (rate limit SEFAZ) — não é erro do CLI
        if "656" in result.stdout:
            pytest.skip("SEFAZ rate limit (cStat=656) — tente novamente apos 1 hora")

        # status 137 = nenhum documento localizado, 138 = documentos encontrados
        # ambos são sucesso (returncode 0)
        assert result.returncode == 0, f"stdout: {result.stdout}\nstderr: {result.stderr}"
        assert "Status:" in result.stdout

    def test_consultar_nsu_zerar_executa(self, emitente, backup_state):
        result = run_nfe("consultar-nsu", emitente, "--zerar-nsu")

        # 656 = consumo indevido (rate limit SEFAZ) — não é erro do CLI
        if "656" in result.stdout:
            pytest.skip("SEFAZ rate limit (cStat=656) — tente novamente apos 1 hora")

        assert result.returncode == 0, f"stdout: {result.stdout}\nstderr: {result.stderr}"
        assert "NSU zerado" in result.stdout


@pytest.mark.slow
class TestPendentesHomologacao:
    def test_pendentes_executa_sem_erro(self, emitente):
        result = run_nfe("pendentes", emitente)
        assert result.returncode == 0, f"stdout: {result.stdout}\nstderr: {result.stderr}"
