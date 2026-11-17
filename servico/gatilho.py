"""Escuta o gatilho do banco (LISTEN nfe_pedidos_ciencia / nfe_pedidos_consulta) e atende pedidos da UI na hora.

Para cada aviso (payload = CNPJ interessado), roda `rodar.py` em modo 'pedidos' para as
instancias daquele CNPJ: registra a ciencia e baixa o XML completo pela chave. Varredura
a cada 10 min cobre aviso perdido (reinicio, queda de conexao). O modo 'pedidos' nunca consulta por NSU;
so o pedido de consulta (nfe.pedidos_consulta) roda a rodada normal da instancia, com o cooldown
respeitado (ou removido, se forcar).
"""
import os
import select
import subprocess
import sys
import time
from pathlib import Path

import psycopg

from rodar import _BRT, cooldown_ate

CANAL = "nfe_pedidos_ciencia"
CANAL_CONSULTA = "nfe_pedidos_consulta"
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


def atender_consultas(con, cnpj: str | None, dir_empresas: Path, raiz_dados: Path):
    """Pedidos de consulta pendentes: rodada normal da instancia do CNPJ; marca feito/erro."""
    pedidos = con.execute(
        "select id, cnpj_interessado, solicitado_por, forcar from nfe.pedidos_consulta "
        "where status = 'pendente' and (%s::text is null or cnpj_interessado = %s) order by id", (cnpj, cnpj)).fetchall()
    for pid, c, quem, forcar in pedidos:
        insts = [(n, e) for n, e in instancias(dir_empresas).items() if e.get("NFE_CNPJ") == c]
        cstat, msg, status = None, None, "erro"
        if not insts:
            msg = "CNPJ sem instancia configurada"
        elif (ate := None if forcar else cooldown_ate(raiz_dados / insts[0][0], c)):
            msg = f"em espera até {ate.astimezone(_BRT):%H:%M}"
        else:
            nome, emp = insts[0]
            t0 = con.execute("select now()").fetchone()[0]
            env = {**os.environ, **emp, "NFE_DATA_DIR": str(raiz_dados / nome), "NFE_SOLICITADO_POR": quem,
                   **({"NFE_FORCAR": "1"} if forcar else {})}
            env.pop("NFE_MODO", None)
            try:
                rc = subprocess.run([sys.executable, str(Path(__file__).with_name("rodar.py"))], env=env,
                                    stdin=subprocess.DEVNULL, timeout=900).returncode
                st = con.execute("select consultado_em, cstat, motivo, bloqueado_ate > now(), to_char(bloqueado_ate at time zone "
                                 "'America/Sao_Paulo', 'HH24:MI') from nfe.consultas_status where cnpj_interessado = %s", (c,)).fetchone()
                if st and st[0] and st[0] >= t0:
                    status, cstat, msg = "feito", st[1], st[2]
                else:
                    msg = f"em espera até {st[4]}" if st and st[3] else f"rodada sem consulta (rc={rc})"
            except subprocess.TimeoutExpired:
                msg = "rodada passou de 15 min; abortada"
        print(f"gatilho: pedido de consulta {pid} ({c}) -> {status}: {msg}", flush=True)
        con.execute("update nfe.pedidos_consulta set status = %s, cstat = %s, mensagem = %s, processado_em = now() "
                    "where id = %s", (status, cstat, msg, pid))


def main():
    dir_empresas = Path(os.environ.get("NFE_EMPRESAS_DIR", "/empresas"))
    raiz_dados = Path(os.environ.get("NFE_DADOS_RAIZ", "/dados"))
    while True:
        try:
            with psycopg.connect(os.environ["NFE_DB_URL"], autocommit=True) as con:
                con.execute(f"listen {CANAL}")
                con.execute(f"listen {CANAL_CONSULTA}")
                print("gatilho: escutando", flush=True)
                atender(None, dir_empresas, raiz_dados)  # varredura inicial
                atender_consultas(con, None, dir_empresas, raiz_dados)
                ultima = time.monotonic()
                while True:
                    espera = max(1.0, VARREDURA_S - (time.monotonic() - ultima))
                    if select.select([con.pgconn.socket], [], [], espera)[0]:
                        avisos = list(con.notifies(timeout=0))
                        for cnpj in sorted({n.payload for n in avisos if n.channel == CANAL}):
                            print(f"gatilho: pedido para {cnpj}", flush=True)
                            atender(cnpj, dir_empresas, raiz_dados)
                        for cnpj in sorted({n.payload for n in avisos if n.channel == CANAL_CONSULTA}):
                            print(f"gatilho: pedido de consulta para {cnpj}", flush=True)
                            atender_consultas(con, cnpj, dir_empresas, raiz_dados)
                    if time.monotonic() - ultima >= VARREDURA_S:
                        atender(None, dir_empresas, raiz_dados)
                        atender_consultas(con, None, dir_empresas, raiz_dados)
                        ultima = time.monotonic()
        except (psycopg.OperationalError, OSError) as e:
            print(f"gatilho: conexao caiu ({type(e).__name__}: {e}); reconectando em 10 s", flush=True)
            time.sleep(10)


if __name__ == "__main__":
    main()
