"""Testes do Pedagio (status da consulta por NSU + pedido de consulta pela UI).

ACs 1-8 do gauntlet. Precisam de Postgres: NFE_TEST_DB_URL (schema nfe recriado a cada teste).
O CLI do nfe-sync e substituido por um pacote falso (PYTHONPATH) que imprime o que o teste manda.
"""
import importlib.util
import json
import os
import subprocess
import sys
from datetime import datetime, timedelta
from pathlib import Path

import pytest

pytest.importorskip("psycopg")
pytest.importorskip("lxml")

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ / "servico"))
import rodar  # noqa: E402
import gatilho  # noqa: E402

CNPJ = "05381344000101"
DB_URL = os.environ.get("NFE_TEST_DB_URL")

CLI_FALSO = """import os, json
from pathlib import Path
est = Path(os.environ["NFE_SYNC_STATE"])
estado = json.loads(est.read_text()) if est.exists() else {}
Path(os.environ["CLI_REG"]).write_text(json.dumps({
    "cooldown_ao_iniciar": estado.get("cooldown", {}), "forcar": os.environ.get("NFE_FORCAR")}))
if os.environ.get("CLI_COOLDOWN"):
    estado.setdefault("cooldown", {})[os.environ["NFE_CNPJ"] + ":producao"] = os.environ["CLI_COOLDOWN"]
    est.write_text(json.dumps(estado))
for linha in os.environ.get("CLI_OUT", "").split("|"):
    print(linha, flush=True)
raise SystemExit(int(os.environ.get("CLI_RC", "0")))
"""


@pytest.fixture
def db():
    if not DB_URL:
        pytest.skip("NFE_TEST_DB_URL nao definida")
    import psycopg
    with psycopg.connect(DB_URL, autocommit=True) as con:
        con.execute("drop schema if exists nfe cascade")
        con.execute((RAIZ / "servico" / "schema.sql").read_text())
    return DB_URL


def q(db, sql, *a):
    import psycopg
    with psycopg.connect(db, autocommit=True) as con:
        cur = con.execute(sql, a)
        return cur.fetchall() if cur.description else None


@pytest.fixture
def amb(db, tmp_path, monkeypatch):
    """Ambiente de rodar.main() com CLI falso e banco real; devolve (dados, roda)."""
    pkg = tmp_path / "pkg" / "nfe_sync"
    pkg.mkdir(parents=True)
    (pkg / "__init__.py").write_text("")
    (pkg / "cli.py").write_text(CLI_FALSO)
    dados = tmp_path / "data"
    dados.mkdir()
    for k, v in {"NFE_EMPRESA": "DROCER", "NFE_CNPJ": CNPJ, "NFE_UF": "ba", "NFE_DATA_DIR": str(dados),
                 "NFE_DB_URL": db, "PYTHONPATH": str(tmp_path / "pkg"), "CLI_REG": str(tmp_path / "reg.json")}.items():
        monkeypatch.setenv(k, v)
    monkeypatch.setattr(rodar, "buscar_certificado", lambda nome: (b"PFX", "s"))
    monkeypatch.setattr(rodar, "processar_pedidos_ciencia", lambda *a: {"feito": 0, "erro": 0})
    monkeypatch.setattr(rodar, "baixar_completas_pedidas", lambda *a: 0)
    monkeypatch.setattr(rodar, "gravar", lambda *a: {})
    monkeypatch.setattr(rodar.fcntl, "flock", lambda f, op: None)   # varias rodadas no mesmo processo de teste

    def roda(out, rc=0, cooldown=None):
        monkeypatch.setenv("CLI_OUT", out)
        monkeypatch.setenv("CLI_RC", str(rc))
        if cooldown:
            monkeypatch.setenv("CLI_COOLDOWN", cooldown)
        with pytest.raises(SystemExit) as e:
            rodar.main()
        return e.value.code
    roda.reg = lambda: json.loads((tmp_path / "reg.json").read_text())
    return dados, roda


def _futuro(min_):
    return (datetime.now(rodar._BRT) + timedelta(minutes=min_)).isoformat()


def _status(db):
    return q(db, "select cstat, motivo, ult_nsu, max_nsu, consultado_em is not null, bloqueado_ate is not null, "
                 "ultimo_656_em is not null, empresa from nfe.consultas_status")


OK137 = "Status: 137|Motivo: Nenhum documento localizado|Ultimo NSU: 100|Max NSU: 250"


# ---------- AC1 ----------

def test_ac1_rodada_137_grava_status_e_bloqueado_ate_do_state(amb, db):
    dados, roda = amb
    ate = _futuro(61)
    assert roda(OK137, cooldown=ate) == 0
    assert _status(db) == [("137", "Nenhum documento localizado", 100, 250, True, True, False, "DROCER")]
    bloq = q(db, "select bloqueado_ate from nfe.consultas_status")[0][0]
    assert abs((bloq - datetime.fromisoformat(ate)).total_seconds()) < 1


def test_ac1_rodada_138_sem_cooldown_bloqueado_ate_nulo(amb, db):
    dados, roda = amb
    assert roda("Status: 138|Motivo: Documento localizado|Ultimo NSU: 5|Max NSU: 5") == 0
    assert _status(db) == [("138", "Documento localizado", 5, 5, True, False, False, "DROCER")]


def test_ac1_segunda_rodada_atualiza_mesma_linha(amb, db):
    dados, roda = amb
    roda(OK137)
    roda("Status: 138|Motivo: Doc|Ultimo NSU: 120|Max NSU: 250")
    assert q(db, "select count(*), max(cstat), max(ult_nsu) from nfe.consultas_status") == [(1, "138", 120)]


def test_ac1_cooldown_ja_vencido_nao_vira_bloqueado_ate(amb, db):
    dados, roda = amb
    roda(OK137, cooldown=_futuro(-30))
    assert _status(db)[0][5] is False


# ---------- AC2 ----------

def test_ac2_656_preenche_ultimo_656_e_preserva_nsus(amb, db):
    dados, roda = amb
    roda(OK137)
    roda("Status: 656|Motivo: Consumo Indevido", rc=1, cooldown=_futuro(240))
    assert _status(db) == [("656", "Consumo Indevido", 100, 250, True, True, True, "DROCER")]


def test_ac2_ultimo_656_preservado_em_rodada_seguinte_ok(amb, db):
    dados, roda = amb
    roda("Status: 656|Motivo: Consumo Indevido", rc=1)
    t656 = q(db, "select ultimo_656_em from nfe.consultas_status")[0][0]
    roda(OK137)
    assert q(db, "select ultimo_656_em, cstat from nfe.consultas_status") == [(t656, "137")]


# ---------- AC3 ----------

def test_ac3_bloqueada_nao_muda_consulta_mas_atualiza_rodada_e_bloqueio(amb, db, capsys):
    dados, roda = amb
    roda(OK137)
    antes = q(db, "select consultado_em, cstat, motivo, rodada_em from nfe.consultas_status")[0]
    ate = _futuro(50)
    rc = roda("BLOQUEADO: cooldown ativo ate " + ate, rc=1, cooldown=ate)
    assert rc == 1
    dep = q(db, "select consultado_em, cstat, motivo, rodada_em, bloqueado_ate from nfe.consultas_status")[0]
    assert dep[:3] == antes[:3]
    assert dep[3] > antes[3]
    assert abs((dep[4] - datetime.fromisoformat(ate)).total_seconds()) < 1
    hhmm = datetime.fromisoformat(ate).astimezone(rodar._BRT).strftime("%H:%M")
    assert f"ESPERA: DROCER próxima consulta liberada às {hhmm}\n" in capsys.readouterr().out   # espera de 137 nao e pedagio


def test_ac3_bloqueada_com_656_anterior_imprime_hora_do_656(amb, db, capsys):
    dados, roda = amb
    roda("Status: 656|Motivo: x", rc=1, cooldown=_futuro(200))
    t656 = q(db, "select ultimo_656_em from nfe.consultas_status")[0][0].astimezone(rodar._BRT).strftime("%H:%M")
    capsys.readouterr()
    roda("BLOQUEADO: cooldown", rc=1)
    assert f" (656 às {t656})" in capsys.readouterr().out


def test_ac3_bloqueada_sem_656_nao_imprime_parenteses(amb, db, capsys):
    dados, roda = amb
    ate = _futuro(30)
    roda("BLOQUEADO: cooldown", rc=1, cooldown=ate)
    saida = capsys.readouterr().out
    assert "ESPERA: DROCER próxima consulta liberada às " in saida and "PEDÁGIO" not in saida and "656 às" not in saida


def test_ac3_bloqueada_primeira_vez_nao_inventa_consulta(amb, db):
    dados, roda = amb
    roda("BLOQUEADO: cooldown", rc=1, cooldown=_futuro(30))
    assert _status(db) == [(None, None, None, None, False, True, False, "DROCER")]


def test_ac3_bloqueado_vence_mesmo_com_linha_status_na_saida(amb, db):
    dados, roda = amb
    roda(OK137)
    roda("Status: 137|Motivo: outro|Ultimo NSU: 999|Max NSU: 999|BLOQUEADO: cooldown", rc=1, cooldown=_futuro(30))
    assert _status(db)[0][:4] == ("137", "Nenhum documento localizado", 100, 250)


# ---------- AC4 ----------

def _grava_cooldown(dados, ate):
    (dados / ".state.json").write_text(json.dumps(
        {"cooldown": {f"{CNPJ}:producao": ate, "99999999000199:producao": ate}, "nsu": {f"{CNPJ}:producao": 7}}))


def test_ac4_forcar_remove_cooldown_antes_do_cli_e_loga(amb, db, monkeypatch, capsys):
    dados, roda = amb
    _grava_cooldown(dados, _futuro(100))
    monkeypatch.setenv("NFE_FORCAR", "1")
    monkeypatch.setenv("NFE_SOLICITADO_POR", "maria")
    roda(OK137)
    assert f"{CNPJ}:producao" not in roda.reg()["cooldown_ao_iniciar"]       # so o do CNPJ; o outro fica
    assert "99999999000199:producao" in roda.reg()["cooldown_ao_iniciar"]
    assert json.loads((dados / ".state.json").read_text())["nsu"] == {f"{CNPJ}:producao": 7}
    assert "FORÇADO: cooldown removido a pedido de maria" in capsys.readouterr().out


def test_ac4_sem_forcar_cooldown_segue_para_o_cli(amb, db, monkeypatch, capsys):
    dados, roda = amb
    _grava_cooldown(dados, _futuro(100))
    monkeypatch.delenv("NFE_FORCAR", raising=False)
    roda(OK137)
    assert f"{CNPJ}:producao" in roda.reg()["cooldown_ao_iniciar"]
    assert "FORÇADO" not in capsys.readouterr().out


def test_ac4_forcar_sem_state_nao_quebra(amb, db, monkeypatch, capsys):
    dados, roda = amb
    monkeypatch.setenv("NFE_FORCAR", "1")
    monkeypatch.setenv("NFE_SOLICITADO_POR", "joao")
    assert roda(OK137) == 0          # observacao: sem .state.json nao ha o que remover e o log FORÇADO nao sai
    assert roda.reg()["forcar"] == "1" and _status(db)[0][0] == "137"


def test_ac4_forcar_so_com_valor_1(amb, db, monkeypatch, capsys):
    dados, roda = amb
    _grava_cooldown(dados, _futuro(100))
    monkeypatch.setenv("NFE_FORCAR", "0")
    roda(OK137)
    assert f"{CNPJ}:producao" in roda.reg()["cooldown_ao_iniciar"]


# ---------- AC5 ----------

def test_ac5_falha_ao_gravar_status_nao_impede_gravar_xmls(amb, db, monkeypatch, capsys):
    dados, roda = amb
    gravados = []
    monkeypatch.setattr(rodar, "gravar", lambda *a: gravados.append(a) or {})

    def quebra(*a, **k):
        raise RuntimeError("banco fora")
    monkeypatch.setattr(rodar, "gravar_status", quebra)
    assert roda(OK137) == 0
    assert gravados == [(dados / "downloads" / CNPJ, CNPJ, db)]
    assert "ERRO ao gravar consultas_status: RuntimeError: banco fora" in capsys.readouterr().out


def test_ac5_falha_real_no_banco_de_status_rodada_segue(amb, db, monkeypatch):
    dados, roda = amb
    import psycopg
    with psycopg.connect(db, autocommit=True) as con:
        con.execute("drop table nfe.consultas_status")
    gravados = []
    monkeypatch.setattr(rodar, "gravar", lambda *a: gravados.append(a) or {})
    assert roda(OK137) == 0
    assert len(gravados) == 1


def test_ac5_exit_code_do_cli_preservado_mesmo_com_falha_de_status(amb, db, monkeypatch):
    dados, roda = amb
    monkeypatch.setattr(rodar, "gravar_status", lambda *a: 1 / 0)
    assert roda("Status: 656|Motivo: x", rc=1) == 1


# ---------- AC6 ----------

def test_ac6_schema_idempotente(db):
    import psycopg
    sql = (RAIZ / "servico" / "schema.sql").read_text()
    with psycopg.connect(db, autocommit=True) as con:
        con.execute(sql)
        con.execute(sql)
        con.execute("insert into nfe.pedidos_consulta (cnpj_interessado, solicitado_por) values (%s, 'x')", (CNPJ,))
        con.execute(sql)
    assert q(db, "select count(*) from nfe.pedidos_consulta") == [(1,)]
    assert q(db, "select count(*) from pg_trigger where tgname = 'avisar_pedido_consulta'") == [(1,)]


def test_ac6_um_pendente_por_cnpj(db):
    import psycopg
    ins = "insert into nfe.pedidos_consulta (cnpj_interessado, solicitado_por, status) values (%s, 'u', %s)"
    with psycopg.connect(db, autocommit=True) as con:
        con.execute(ins, (CNPJ, "pendente"))
        with pytest.raises(psycopg.errors.UniqueViolation):
            con.execute(ins, (CNPJ, "pendente"))
        con.execute(ins, ("99999999000199", "pendente"))            # outro CNPJ pode
        con.execute("update nfe.pedidos_consulta set status = 'feito' where cnpj_interessado = %s", (CNPJ,))
        con.execute(ins, (CNPJ, "pendente"))                        # feito liberou o slot
        con.execute(ins, (CNPJ, "feito"))                           # varios feitos ok
        con.execute(ins, (CNPJ, "erro"))


def test_ac6_status_invalido_e_cnpj_invalido_rejeitados(db):
    import psycopg
    with psycopg.connect(db, autocommit=True) as con:
        with pytest.raises(psycopg.errors.CheckViolation):
            con.execute("insert into nfe.pedidos_consulta (cnpj_interessado, solicitado_por, status) values (%s,'u','xx')", (CNPJ,))
        with pytest.raises(psycopg.errors.CheckViolation):
            con.execute("insert into nfe.pedidos_consulta (cnpj_interessado, solicitado_por) values ('123','u')")


def test_ac6_trigger_notify_insert_e_reabertura_nao_em_feito(db):
    import psycopg
    with psycopg.connect(db, autocommit=True) as ouvinte, psycopg.connect(db, autocommit=True) as app:
        ouvinte.execute("listen nfe_pedidos_consulta")
        app.execute("insert into nfe.pedidos_consulta (cnpj_interessado, solicitado_por) values (%s,'ui')", (CNPJ,))
        assert [n.payload for n in ouvinte.notifies(timeout=2, stop_after=1)] == [CNPJ]
        app.execute("update nfe.pedidos_consulta set status='feito'")
        assert list(ouvinte.notifies(timeout=1)) == []
        app.execute("update nfe.pedidos_consulta set status='pendente'")
        assert [n.payload for n in ouvinte.notifies(timeout=2, stop_after=1)] == [CNPJ]
        app.execute("insert into nfe.pedidos_consulta (cnpj_interessado, solicitado_por, status) values (%s,'ui','erro')", (CNPJ,))
        assert list(ouvinte.notifies(timeout=1)) == []


def test_ac6_trigger_nao_cruza_canal_da_ciencia(db):
    import psycopg
    with psycopg.connect(db, autocommit=True) as ouvinte, psycopg.connect(db, autocommit=True) as app:
        ouvinte.execute("listen nfe_pedidos_ciencia")
        app.execute("insert into nfe.pedidos_consulta (cnpj_interessado, solicitado_por) values (%s,'ui')", (CNPJ,))
        assert list(ouvinte.notifies(timeout=1)) == []


# ---------- AC7: gatilho.atender_consultas ----------

@pytest.fixture
def gat(db, tmp_path, monkeypatch):
    emp = tmp_path / "emp"
    emp.mkdir()
    (emp / "DROCER.env").write_text(f"NFE_EMPRESA=DROCER\nNFE_CNPJ={CNPJ}\nNFE_UF=ba\n")
    raiz = tmp_path / "raiz"
    (raiz / "DROCER").mkdir(parents=True)
    chamadas = []

    def fake_run(cmd, **kw):
        chamadas.append((cmd, kw))
        import psycopg
        if kw["env"].get("FAKE_GRAVA", "1") == "1" and "rodar.py" in cmd[-1]:
            with psycopg.connect(db, autocommit=True) as con:
                con.execute("insert into nfe.consultas_status (cnpj_interessado, empresa, rodada_em, consultado_em, cstat, motivo) "
                            "values (%s,'DROCER',now(),now(),'137','Nenhum documento') on conflict (cnpj_interessado) do update "
                            "set consultado_em = now(), cstat = '137', motivo = 'Nenhum documento'", (CNPJ,))
        return subprocess.CompletedProcess(cmd, 0)
    monkeypatch.setattr(gatilho.subprocess, "run", fake_run)
    return emp, raiz, chamadas


def _pedir(db, forcar=False, cnpj=CNPJ, quem="ana"):
    q(db, "insert into nfe.pedidos_consulta (cnpj_interessado, solicitado_por, forcar) values (%s,%s,%s)", cnpj, quem, forcar)


def _pedido_row(db):
    return q(db, "select status, cstat, mensagem, processado_em is not null from nfe.pedidos_consulta order by id")


def _atende(db, gat_, cnpj=None):
    import psycopg
    emp, raiz, _ = gat_
    with psycopg.connect(db, autocommit=True) as con:
        gatilho.atender_consultas(con, cnpj, emp, raiz)


def test_ac7_sem_forcar_com_cooldown_ativo_vira_erro_sem_rodar_cli(db, gat):
    emp, raiz, chamadas = gat
    ate = _futuro(90)
    _grava_cooldown(raiz / "DROCER", ate)
    _pedir(db)
    _atende(db, gat)
    hhmm = datetime.fromisoformat(ate).astimezone(rodar._BRT).strftime("%H:%M")
    assert _pedido_row(db) == [("erro", None, f"em espera até {hhmm}", True)]
    assert chamadas == []


def test_ac7_sem_cooldown_roda_e_marca_feito_com_cstat_e_mensagem(db, gat):
    emp, raiz, chamadas = gat
    _pedir(db, quem="ana")
    _atende(db, gat)
    assert _pedido_row(db) == [("feito", "137", "Nenhum documento", True)]
    (cmd, kw), = chamadas
    assert cmd[-1].endswith("rodar.py")
    assert "NFE_FORCAR" not in kw["env"] and "NFE_MODO" not in kw["env"]
    assert kw["env"]["NFE_SOLICITADO_POR"] == "ana"
    assert kw["env"]["NFE_DATA_DIR"] == str(raiz / "DROCER") and kw["env"]["NFE_EMPRESA"] == "DROCER"


def test_ac7_cooldown_vencido_nao_bloqueia(db, gat):
    emp, raiz, chamadas = gat
    _grava_cooldown(raiz / "DROCER", _futuro(-5))
    _pedir(db)
    _atende(db, gat)
    assert _pedido_row(db)[0][0] == "feito" and len(chamadas) == 1


def test_ac7_forcar_roda_com_nfe_forcar_mesmo_com_cooldown(db, gat, monkeypatch):
    emp, raiz, chamadas = gat
    monkeypatch.setenv("NFE_MODO", "pedidos")                    # herdado do ambiente: deve ser removido
    _grava_cooldown(raiz / "DROCER", _futuro(90))
    _pedir(db, forcar=True, quem="bia")
    _atende(db, gat)
    (cmd, kw), = chamadas
    assert kw["env"]["NFE_FORCAR"] == "1" and kw["env"]["NFE_SOLICITADO_POR"] == "bia"
    assert "NFE_MODO" not in kw["env"]
    assert _pedido_row(db)[0][0] == "feito"


def test_ac7_rodada_sem_consulta_vira_erro_com_rc(db, gat, monkeypatch):
    emp, raiz, chamadas = gat
    monkeypatch.setenv("FAKE_GRAVA", "0")
    _pedir(db)
    _atende(db, gat)
    assert _pedido_row(db) == [("erro", None, "rodada sem consulta (rc=0)", True)]


def test_ac7_status_antigo_nao_conta_como_feito(db, gat, monkeypatch):
    emp, raiz, chamadas = gat
    monkeypatch.setenv("FAKE_GRAVA", "0")
    q(db, "insert into nfe.consultas_status (cnpj_interessado, empresa, rodada_em, consultado_em, cstat) "
          "values (%s,'D',now() - interval '1 hour', now() - interval '1 hour','137')", CNPJ)
    _pedir(db)
    _atende(db, gat)
    assert _pedido_row(db)[0][0] == "erro"


def test_ac7_bloqueio_surgido_durante_a_rodada_vira_erro_em_espera(db, gat, monkeypatch):
    emp, raiz, chamadas = gat
    monkeypatch.setenv("FAKE_GRAVA", "0")
    q(db, "insert into nfe.consultas_status (cnpj_interessado, empresa, rodada_em, consultado_em, bloqueado_ate) "
          "values (%s,'D',now() - interval '1 hour', now() - interval '1 hour', now() + interval '1 hour')", CNPJ)
    _pedir(db)
    _atende(db, gat)
    st, _, msg, _ = _pedido_row(db)[0]
    assert st == "erro" and msg.startswith("em espera até ")


def test_ac7_cnpj_sem_instancia_vira_erro(db, gat):
    _pedir(db, cnpj="99999999000199")
    _atende(db, gat)
    assert _pedido_row(db) == [("erro", None, "CNPJ sem instancia configurada", True)]


def test_ac7_timeout_vira_erro(db, gat, monkeypatch):
    def estoura(cmd, **kw):
        raise subprocess.TimeoutExpired(cmd, 900)
    monkeypatch.setattr(gatilho.subprocess, "run", estoura)
    _pedir(db)
    _atende(db, gat)
    assert _pedido_row(db) == [("erro", None, "rodada passou de 15 min; abortada", True)]


def test_ac7_filtra_por_cnpj_e_ignora_nao_pendentes(db, gat):
    emp, raiz, chamadas = gat
    (emp / "BBB.env").write_text("NFE_EMPRESA=BBB\nNFE_CNPJ=99999999000199\nNFE_UF=df\n")
    _pedir(db)
    _pedir(db, cnpj="99999999000199")
    q(db, "insert into nfe.pedidos_consulta (cnpj_interessado, solicitado_por, status) values (%s,'x','feito')", CNPJ)
    _atende(db, gat, cnpj="99999999000199")
    assert [r[0] for r in _pedido_row(db)] == ["pendente", "erro", "feito"] or len(chamadas) == 1
    assert [c[1]["env"]["NFE_EMPRESA"] for c in chamadas] == ["BBB"]
    assert _pedido_row(db)[0][0] == "pendente"                    # o da DROCER segue pendente
    _atende(db, gat)                                              # varredura (None) pega o restante
    assert _pedido_row(db)[0][0] != "pendente"
    assert len(chamadas) == 2                                     # feito antigo nao foi reprocessado
    assert _pedido_row(db)[2] == ("feito", None, None, False)     # intacto (sem processado_em/mensagem)


# ---------- AC8 ----------

def test_ac8_saida_do_cli_repassada_linha_a_linha(amb, db, capfd):
    dados, roda = amb
    roda("linha um|linha dois|Status: 137|Motivo: M|Ultimo NSU: 1|Max NSU: 2")
    saida = capfd.readouterr().out.splitlines()
    i = saida.index("linha um")
    assert saida[i:i + 6] == ["linha um", "linha dois", "Status: 137", "Motivo: M", "Ultimo NSU: 1", "Max NSU: 2"]


def test_ac8_stderr_do_cli_tambem_vai_ao_journal(amb, db, capfd, tmp_path):
    dados, roda = amb
    (tmp_path / "pkg" / "nfe_sync" / "cli.py").write_text(
        "import sys\nprint('so-no-stderr', file=sys.stderr)\nprint('Status: 137')\n")
    roda("")
    assert "so-no-stderr" in capfd.readouterr().out


def test_ac8_saida_em_tempo_real_nao_so_no_fim(tmp_path):
    """consultar_nsu imprime a 1a linha enquanto o CLI ainda esta rodando."""
    pkg = tmp_path / "pkg" / "nfe_sync"
    pkg.mkdir(parents=True)
    (pkg / "__init__.py").write_text("")
    (pkg / "cli.py").write_text("import time\nprint('primeira', flush=True)\ntime.sleep(3)\nprint('Status: 137', flush=True)\n")
    runner = tmp_path / "r.py"
    runner.write_text("import sys,pathlib\nsys.path.insert(0,%r)\nimport rodar\n"
                      "print(rodar.consultar_nsu('E', pathlib.Path('.'), __import__('os').environ.copy()))\n" % str(RAIZ / "servico"))
    import time
    p = subprocess.Popen([sys.executable, "-u", str(runner)], cwd=tmp_path, stdout=subprocess.PIPE, text=True,
                         env={**os.environ, "PYTHONPATH": str(tmp_path / "pkg")})
    t0 = time.monotonic()
    assert p.stdout.readline().strip() == "primeira"
    assert time.monotonic() - t0 < 2.5
    p.wait(10)


def test_consultar_nsu_parseia_info(tmp_path, monkeypatch):
    pkg = tmp_path / "pkg" / "nfe_sync"
    pkg.mkdir(parents=True)
    (pkg / "__init__.py").write_text("")
    (pkg / "cli.py").write_text("print('Status: 137');print('Motivo: a: b');print('Ultimo NSU: 3');print('Max NSU: 9');"
                                "print('BLOQUEADO: x');raise SystemExit(4)\n")
    rc, info = rodar.consultar_nsu("E", tmp_path, {**os.environ, "PYTHONPATH": str(tmp_path / "pkg")})
    assert rc == 4
    assert info == {"Status": "137", "Motivo": "a: b", "Ultimo NSU": "3", "Max NSU": "9", "BLOQUEADO": "x"}


def test_ac3_pedagio_so_quando_ultima_consulta_foi_656(amb, db, capsys):
    """656 antigo seguido de 137: a espera seguinte e ESPERA, nao PEDAGIO com o 656 velho."""
    dados, roda = amb
    roda("Status: 656|Motivo: x", rc=1, cooldown=_futuro(200))
    roda(OK137)
    capsys.readouterr()
    roda("BLOQUEADO: cooldown", rc=1, cooldown=_futuro(30))
    saida = capsys.readouterr().out
    assert "ESPERA: DROCER" in saida and "PEDÁGIO" not in saida


# ---------- B1: limite de consulta forcada ----------

def _processado_ha(db, minutos):
    q(db, "update nfe.pedidos_consulta set processado_em = now() - make_interval(mins => %s)", minutos)


def test_b1_segundo_forcar_em_30min_recusado_sem_rodar(db, gat):
    emp, raiz, chamadas = gat
    _pedir(db, forcar=True)
    _atende(db, gat)
    _processado_ha(db, 5)
    _pedir(db, forcar=True)
    _atende(db, gat)
    linhas = _pedido_row(db)
    assert linhas[0][0] == "feito"
    assert linhas[1][0] == "erro" and linhas[1][2].startswith("consulta forçada recentemente; tente após ")
    assert len(chamadas) == 1


def test_b1_forcar_apos_30min_roda(db, gat):
    emp, raiz, chamadas = gat
    _pedir(db, forcar=True)
    _atende(db, gat)
    _processado_ha(db, 31)
    _pedir(db, forcar=True)
    _atende(db, gat)
    assert [r[0] for r in _pedido_row(db)] == ["feito", "feito"] and len(chamadas) == 2


def test_b1_pedido_sem_forcar_nao_conta_no_limite(db, gat):
    emp, raiz, chamadas = gat
    _pedir(db)
    _atende(db, gat)
    _processado_ha(db, 5)
    _pedir(db, forcar=True)
    _atende(db, gat)
    assert [r[0] for r in _pedido_row(db)] == ["feito", "feito"]
