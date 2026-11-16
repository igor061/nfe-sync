"""Escuta o gatilho do banco (LISTEN nfe_pedidos_ciencia) e atende pedidos da UI na hora.

Para cada aviso (payload = CNPJ interessado), roda `rodar.py` em modo 'pedidos' para as
instancias daquele CNPJ: registra a ciencia e baixa o XML completo pela chave. Varredura
a cada 10 min cobre aviso perdido (reinicio, queda de conexao). Nunca consulta por NSU.
"""
import os
import select
import subprocess
import sys
import time
from pathlib import Path

import psycopg

CANAL = "nfe_pedidos_ciencia"
VARREDURA_S = 600


def ler_env(arquivo: Path) -> dict:
    env = {}
    for linha in arquivo.read_text().splitlines():
        linha = linha.strip()
        if linha and not linha.startswith("#") and "=" in linha:
            k, v = linha.split("=", 1)
            env[k.strip()] = v.strip()
    return env


def instancias(dir_empresas: Path) -> dict:
    """{instancia: env da empresa}, a partir de empresas/<INSTANCIA>.env."""
    return {f.stem: ler_env(f) for f in sorted(dir_empresas.glob("*.env"))}


def atender(cnpj: str | None, dir_empresas: Path, raiz_dados: Path) -> list[str]:
    """Roda o modo 'pedidos' para as instancias do CNPJ (ou todas, se None). Retorna as rodadas."""
    rodadas = []
    for nome, emp in instancias(dir_empresas).items():
        if cnpj and emp.get("NFE_CNPJ") != cnpj:
            continue
        env = {**os.environ, **emp, "NFE_MODO": "pedidos", "NFE_DATA_DIR": str(raiz_dados / nome)}
        try:
            subprocess.run([sys.executable, str(Path(__file__).with_name("rodar.py"))], env=env,
                           stdin=subprocess.DEVNULL, timeout=900)
        except subprocess.TimeoutExpired:
            print(f"gatilho: rodada de {nome} passou de 15 min; abortada", flush=True)
        rodadas.append(nome)
    return rodadas


def main():
    dir_empresas = Path(os.environ.get("NFE_EMPRESAS_DIR", "/empresas"))
    raiz_dados = Path(os.environ.get("NFE_DADOS_RAIZ", "/dados"))
    while True:
        try:
            with psycopg.connect(os.environ["NFE_DB_URL"], autocommit=True) as con:
                con.execute(f"listen {CANAL}")
                print("gatilho: escutando", flush=True)
                atender(None, dir_empresas, raiz_dados)  # varredura inicial
                ultima = time.monotonic()
                while True:
                    espera = max(1.0, VARREDURA_S - (time.monotonic() - ultima))
                    if select.select([con.pgconn.socket], [], [], espera)[0]:
                        cnpjs = {n.payload for n in con.notifies(timeout=0)}
                        for cnpj in sorted(cnpjs):
                            print(f"gatilho: pedido para {cnpj}", flush=True)
                            atender(cnpj, dir_empresas, raiz_dados)
                    if time.monotonic() - ultima >= VARREDURA_S:
                        atender(None, dir_empresas, raiz_dados)
                        ultima = time.monotonic()
        except (psycopg.OperationalError, OSError) as e:
            print(f"gatilho: conexao caiu ({type(e).__name__}: {e}); reconectando em 10 s", flush=True)
            time.sleep(10)


if __name__ == "__main__":
    main()
