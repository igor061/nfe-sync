"""Escuta o gatilho do banco (LISTEN nfe_pedidos_ciencia / nfe_pedidos_consulta) e atende pedidos da UI na hora.

Para cada aviso (payload = CNPJ interessado), roda `rodar.py` em modo 'pedidos' para as
instancias daquele CNPJ: registra a ciencia e baixa o XML completo pela chave. Varredura
a cada 10 min cobre aviso perdido (reinicio, queda de conexao). O modo 'pedidos' nunca consulta por NSU;
o pedido de consulta (nfe.pedidos_consulta) e validado aqui e entregue a unidade agendada da
instancia (arquivo .pedido-consulta.json + nfe-sync-pedido@.path), que consulta e marca feito/erro.
"""
import json
import os
import select
import subprocess
import sys
import time
from pathlib import Path

import psycopg

from rodar import _BRT, ARQ_PEDIDO, cooldown_ate, ler_pedido

CANAL = "nfe_pedidos_ciencia"
CANAL_CONSULTA = "nfe_pedidos_consulta"
VARREDURA_S = 600
FORCAR_INTERVALO_MIN = 30  # no maximo uma consulta forcada a cada 30 min por CNPJ
PEDIDO_PRAZO_S = 20 * 60  # pedido entregue a unidade e nao concluido nesse prazo vira erro


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
        elif forcar and (ant := con.execute(
                "select processado_em + make_interval(mins => %s) from nfe.pedidos_consulta where cnpj_interessado = %s "
                "and forcar and id <> %s and status in ('feito', 'erro') and not coalesce(mensagem, '') like 'consulta forçada recentemente%%' "
                "and processado_em > now() - make_interval(mins => %s) order by processado_em desc limit 1",
                (FORCAR_INTERVALO_MIN, c, pid, FORCAR_INTERVALO_MIN)).fetchone()):
            msg = f"consulta forçada recentemente; tente após {ant[0].astimezone(_BRT):%H:%M}"
        elif (ate := None if forcar else cooldown_ate(raiz_dados / insts[0][0], c)):
            msg = f"em espera até {ate.astimezone(_BRT):%H:%M}"
        else:
            # A consulta roda na propria unidade agendada (nfe-sync@<inst>.service, disparada pelo
            # nfe-sync-pedido@<inst>.path): assim o timer recomeca a contar 62 min a partir dela.
            nome = insts[0][0]
            arq = raiz_dados / nome / ARQ_PEDIDO
            atual = ler_pedido(arq.parent)
            try:
                idade = time.time() - arq.stat().st_mtime
            except OSError:  # o rodar.py acabou de concluir e apagar
                idade = 0
            if atual and atual.get("id") == pid and idade < PEDIDO_PRAZO_S:
                continue  # ja entregue a unidade; o rodar.py marca feito/erro
            if atual and atual.get("id") == pid:
                arq.unlink(missing_ok=True)
                msg = "rodada não concluiu o pedido; tente de novo"
            else:
                tmp = arq.with_suffix(".tmp")
                tmp.write_text(json.dumps({"id": pid, "forcar": bool(forcar), "por": quem}))
                tmp.replace(arq)
                print(f"gatilho: pedido de consulta {pid} ({c}) entregue a nfe-sync@{nome}", flush=True)
                continue
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
