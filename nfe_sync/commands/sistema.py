import argparse
import re
import subprocess
import sys
import urllib.request
from importlib.metadata import version, PackageNotFoundError

from . import CliBlueprint

GITHUB_RAW = "https://raw.githubusercontent.com/igor061/nfe-sync/main/pyproject.toml"
GITHUB_CHANGELOG = "https://raw.githubusercontent.com/igor061/nfe-sync/main/CHANGELOG.md"
GITHUB_README = "https://raw.githubusercontent.com/igor061/nfe-sync/main/README.md"
GITHUB_PKG = "git+https://github.com/igor061/nfe-sync.git"


def _versao_local() -> str:
    try:
        return version("nfe-sync")
    except PackageNotFoundError:
        return "desconhecida"


def _versao_remota() -> str | None:
    try:
        with urllib.request.urlopen(GITHUB_RAW, timeout=5) as r:
            for linha in r.read().decode().splitlines():
                if linha.startswith("version ="):
                    return linha.split('"')[1]
    except Exception:
        return None


def _changelog_novidades(versao_local: str) -> list[str]:
    try:
        with urllib.request.urlopen(GITHUB_CHANGELOG, timeout=5) as r:
            conteudo = r.read().decode()

        padrao_versao = re.compile(r"^## (\d+\.\d+\.\d+)")

        def ver_tuple(v):
            m = re.match(r"(\d+)\.(\d+)\.(\d+)", v)
            return tuple(int(x) for x in m.groups()) if m else (0, 0, 0)

        local_t = ver_tuple(versao_local)
        linhas = []
        capturando = False
        for linha in conteudo.splitlines():
            m = padrao_versao.match(linha)
            if m:
                if ver_tuple(m.group(1)) > local_t:
                    capturando = True
                    linhas.append(linha)
                else:
                    break
            elif capturando:
                linhas.append(linha)
        return linhas
    except Exception:
        return []


def cmd_versao(args):
    local = _versao_local()
    print(f"Versao instalada: {local}")
    print("Verificando atualizacoes...")
    remota = _versao_remota()
    if remota is None:
        print("Nao foi possivel verificar a versao remota.")
    elif remota == local:
        print(f"Voce esta na versao mais recente ({local}).")
    else:
        print(f"Nova versao disponivel: {remota}")
        novidades = _changelog_novidades(local)
        if novidades:
            print("\nNovidades:")
            for linha in novidades:
                print(linha)
        print(f"\nPara atualizar: nfe-sync atualizar")


def cmd_readme(args):
    try:
        with urllib.request.urlopen(GITHUB_README, timeout=5) as r:
            print(r.read().decode())
    except Exception:
        print("Nao foi possivel obter o README. Acesse: https://github.com/igor061/nfe-sync")


def cmd_atualizar(args):
    local = _versao_local()
    print(f"Versao atual: {local}")
    print("Verificando atualizacoes...")
    remota = _versao_remota()
    if remota is None:
        print("Nao foi possivel verificar a versao remota.")
        sys.exit(1)
    if remota == local:
        print(f"Voce ja esta na versao mais recente ({local}).")
        return
    print(f"Atualizando {local} -> {remota}...")
    subprocess.run([sys.executable, "-m", "pip", "install", "--upgrade", GITHUB_PKG], check=True)


class SistemaBlueprint(CliBlueprint):
    def register(self, subparsers, parser) -> None:
        p_versao = subparsers.add_parser(
            "versao",
            help=argparse.SUPPRESS,
            description="Exibe a versao instalada e verifica se ha uma versao mais recente no repositorio.",
        )
        p_versao.set_defaults(func=cmd_versao)

        p_atualizar = subparsers.add_parser(
            "atualizar",
            help=argparse.SUPPRESS,
            description="Atualiza o nfe-sync para a versao mais recente disponivel no repositorio.",
        )
        p_atualizar.set_defaults(func=cmd_atualizar)

        p_readme = subparsers.add_parser(
            "readme",
            help=argparse.SUPPRESS,
            description="Exibe o README do repositorio com instrucoes de instalacao, configuracao e uso.",
        )
        p_readme.set_defaults(func=cmd_readme)
