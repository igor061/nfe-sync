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


@pytest.mark.slow
class TestEmitirHomologacao:
    def test_emitir_cria_xml(self, emitente, serie, backup_state, tmp_path):
        result = run_nfe("emitir", emitente, "--serie", serie)

        assert result.returncode == 0, f"stdout: {result.stdout}\nstderr: {result.stderr}"
        assert "Status:" in result.stdout
        assert "Protocolo:" in result.stdout
        assert "Chave:" in result.stdout

        # chave de 44 dígitos aparece na saída
        match = re.search(r"Chave: (\d{44})", result.stdout)
        assert match, f"Chave 44 dígitos não encontrada na saída:\n{result.stdout}"

        chave = match.group(1)
        xml_path = os.path.join(os.getcwd(), "xml", f"{chave}.xml")
        assert os.path.exists(xml_path), f"XML não criado em {xml_path}"

    def test_emitir_com_destinatario(self, emitente, destinatario, serie, backup_state):
        if destinatario is None:
            pytest.skip("--destinatario nao fornecido")

        result = run_nfe(
            "emitir", emitente,
            "--serie", serie,
            "--destinatario", destinatario,
        )

        assert result.returncode == 0, f"stdout: {result.stdout}\nstderr: {result.stderr}"
        assert "Status:" in result.stdout

    def test_emitir_incrementa_numero(self, emitente, serie, backup_state):
        result1 = run_nfe("emitir", emitente, "--serie", serie)
        assert result1.returncode == 0, result1.stdout

        match1 = re.search(r"Numero NF (\d+) serie", result1.stdout)
        assert match1
        numero1 = int(match1.group(1))

        result2 = run_nfe("emitir", emitente, "--serie", serie)
        assert result2.returncode == 0, result2.stdout

        match2 = re.search(r"Numero NF (\d+) serie", result2.stdout)
        assert match2
        numero2 = int(match2.group(1))

        assert numero2 == numero1 + 1


@pytest.mark.slow
class TestConsultarNsuHomologacao:
    def test_consultar_nsu_executa_sem_erro(self, emitente):
        result = run_nfe("consultar-nsu", emitente)

        # status 137 = nenhum documento localizado, 138 = documentos encontrados
        # ambos são sucesso (returncode 0)
        assert result.returncode == 0, f"stdout: {result.stdout}\nstderr: {result.stderr}"
        assert "Status:" in result.stdout

    def test_consultar_nsu_zerar_executa(self, emitente, backup_state):
        result = run_nfe("consultar-nsu", emitente, "--zerar-nsu")

        assert result.returncode == 0, f"stdout: {result.stdout}\nstderr: {result.stderr}"
        assert "NSU zerado" in result.stdout


@pytest.mark.slow
class TestPendentesHomologacao:
    def test_pendentes_executa_sem_erro(self, emitente):
        result = run_nfe("pendentes", emitente)
        assert result.returncode == 0, f"stdout: {result.stdout}\nstderr: {result.stderr}"
