import os
import shutil
import subprocess
import sys
import pytest


STATE_FILE = ".state.json"
DOWNLOADS_DIR = "downloads"


def pytest_configure(config):
    """Registra markers para evitar PytestUnknownMarkWarning (#65)."""
    config.addinivalue_line(
        "markers", "slow: testes que chamam a SEFAZ (requerem certificado e conexao real)"
    )


def pytest_addoption(parser):
    parser.addoption(
        "--emitente",
        default=None,
        help="Nome da empresa emitente (secao no nfe-sync.conf.ini)",
    )
    parser.addoption(
        "--destinatario",
        default=None,
        help="Nome da empresa destinataria (secao no nfe-sync.conf.ini)",
    )
    parser.addoption(
        "--serie",
        default="99",
        help="Serie da NF-e usada nos testes E2E (padrao: 99, para evitar colisao com serie 1)",
    )


@pytest.fixture(scope="session")
def emitente(request):
    val = request.config.getoption("--emitente")
    if val is None:
        pytest.skip("--emitente nao fornecido")
    return val


@pytest.fixture(scope="session")
def destinatario(request):
    return request.config.getoption("--destinatario")


@pytest.fixture(scope="session")
def serie(request):
    return request.config.getoption("--serie")


def run_nfe(*args, homologacao=True, cwd=None, timeout=30) -> subprocess.CompletedProcess:
    """Executa o CLI nfe-sync com os argumentos fornecidos.

    homologacao=True (padrão) injeta --homologacao antes do subcomando,
    garantindo que os testes nunca rodem contra produção (#64).
    """
    flags = ["--homologacao"] if homologacao else []
    cmd = [sys.executable, "-m", "nfe_sync.cli"] + flags + list(args)
    return subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        cwd=cwd or os.getcwd(),
        timeout=timeout,
    )


@pytest.fixture
def backup_state(tmp_path):
    """Salva e restaura o .state.json ao redor de cada teste.

    Usar apenas em testes que NÃO emitem NF-e: restaurar o contador
    após uma emissão bem-sucedida causa cStat=539 na SEFAZ (#66).
    """
    state_path = os.path.join(os.getcwd(), STATE_FILE)
    backup_path = tmp_path / "state_backup.json"

    if os.path.exists(state_path):
        shutil.copy2(state_path, backup_path)
        had_state = True
    else:
        had_state = False

    yield

    if had_state:
        shutil.copy2(backup_path, state_path)
    elif os.path.exists(state_path):
        os.remove(state_path)
