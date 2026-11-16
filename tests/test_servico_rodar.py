"""Testes do servico/rodar.py (AC1 rodada, AC2 ler_xml, AC3 gravar idempotente).

AC3 precisa de Postgres: defina NFE_TEST_DB_URL (schema nfe e recriado a cada teste).
"""
import importlib.util
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

pytest.importorskip("psycopg")
pytest.importorskip("lxml")

RAIZ = Path(__file__).resolve().parent.parent
FIX = Path(__file__).parent / "fixtures" / "servico"
spec = importlib.util.spec_from_file_location("servico_rodar", RAIZ / "servico" / "rodar.py")
rodar = importlib.util.module_from_spec(spec)
spec.loader.exec_module(rodar)

CHAVE_COMPLETA = "35261172677370000179550010000254161000124160"
CHAVE_RESUMO = "35261154597638000180550010000574021000087124"
CHAVE_EVENTO = "13260904628426000145550010012775941537837376"
CNPJ = "05381344000101"

PROC_EVENTO = """<?xml version="1.0" encoding="UTF-8"?>
<procEventoNFe xmlns="http://www.portalfiscal.inf.br/nfe" versao="1.00">
  <evento versao="1.00"><infEvento Id="ID1">
    <chNFe>%s</chNFe><tpEvento>110111</tpEvento><nSeqEvento>2</nSeqEvento>
    <dhEvento>2026-09-12T10:00:00-03:00</dhEvento>
    <detEvento versao="1.00"><descEvento>Cancelamento</descEvento></detEvento>
  </infEvento></evento>
  <retEvento versao="1.00"><infEvento><cStat>135</cStat></infEvento></retEvento>
</procEventoNFe>
""" % CHAVE_COMPLETA


# ---------- AC2: ler_xml ----------

def test_ler_xml_nfeproc_completa():
    tipo, c = rodar.ler_xml(FIX / "nfeproc.xml")
    assert tipo == "documento"
    assert c["tipo"] == "completa"
    assert c["chave"] == CHAVE_COMPLETA  # sem prefixo "NFe"
    assert c["emitente_cnpj"] == "72677370000179"
    assert c["emitente_nome"] == "REAL GOLD INDUSTRIA E COMERCIO EIRELI"
    assert c["destinatario_cnpj"] == CNPJ
    assert (c["numero"], c["serie"]) == ("25416", "1")
    assert c["emitida_em"] == "2026-11-05T14:51:00-03:00"
    assert c["valor_total"] == "43.40"
    assert c["cstat"] == "100"
    assert c["protocolo"] == "135264730464381"


def test_ler_xml_resnfe_resumo():
    tipo, c = rodar.ler_xml(FIX / "resnfe.xml")
    assert tipo == "documento"
    assert c["tipo"] == "resumo"
    assert c["chave"] == CHAVE_RESUMO
    assert c["emitente_cnpj"] == "54597638000180"
    assert c["valor_total"] == "708.86"


def test_ler_xml_resevento():
    tipo, c = rodar.ler_xml(FIX / "resevento.xml")
    assert tipo == "evento"
    assert (c["chave"], c["tp_evento"], c["seq"]) == (CHAVE_EVENTO, "610600", "1")
    assert c["descricao"] == "Registro de Autorização de CT-e para a NF-e"
    assert c["ocorrido_em"] == "2026-09-11T19:16:49-03:00"


def test_ler_xml_proceventonfe(tmp_path):
    f = tmp_path / "ev.xml"
    f.write_text(PROC_EVENTO, encoding="utf-8")
    tipo, c = rodar.ler_xml(f)
    assert tipo == "evento"
    assert (c["chave"], c["tp_evento"], c["seq"]) == (CHAVE_COMPLETA, "110111", "2")
    assert c["descricao"] == "Cancelamento"
    assert c["ocorrido_em"] == "2026-09-12T10:00:00-03:00"
    assert c["cstat"] == "135"


def test_ler_xml_raiz_desconhecida_retorna_none(tmp_path):
    f = tmp_path / "x.xml"
    f.write_text('<?xml version="1.0"?><outra xmlns="http://www.portalfiscal.inf.br/nfe"/>', encoding="utf-8")
    assert rodar.ler_xml(f) is None


# ---------- AC1: main ----------

@pytest.fixture
def ambiente(tmp_path, monkeypatch):
    dados = tmp_path / "data"
    dados.mkdir()
    for k, v in {"NFE_EMPRESA": "DROCER", "NFE_CNPJ": CNPJ, "NFE_UF": "ba",
                 "NFE_DATA_DIR": str(dados), "NFE_DB_URL": "postgresql://x"}.items():
        monkeypatch.setenv(k, v)
    monkeypatch.setattr(rodar, "buscar_certificado", lambda nome: (b"PFXBYTES", "segredo"))
    monkeypatch.setattr(rodar, "processar_pedidos_ciencia", lambda *a: {"feito": 0, "erro": 0})
    monkeypatch.setattr(rodar, "baixar_completas_pedidas", lambda *a: 0)
    return dados


def _roda(monkeypatch, rc, captura, gravados):
    def fake_run(cmd, **kw):
        cert = Path(kw["env"]["NFE_SYNC_CONFIG"]).parent / "cert.pfx"
        captura.update(cmd=cmd, kw=kw, cert_existia=cert.exists(), cert=cert,
                       conf=Path(kw["env"]["NFE_SYNC_CONFIG"]).read_text())
        return subprocess.CompletedProcess(cmd, rc)
    monkeypatch.setattr(rodar.subprocess, "run", fake_run)
    monkeypatch.setattr(rodar, "gravar", lambda *a: gravados.append(a) or {})


def test_main_chama_consultar_nsu_sem_registrar_ciencia(ambiente, monkeypatch):
    cap, grav = {}, []
    _roda(monkeypatch, 0, cap, grav)
    with pytest.raises(SystemExit) as e:
        rodar.main()
    assert e.value.code == 0
    assert cap["cmd"] == [sys.executable, "-m", "nfe_sync.cli", "--producao", "consultar-nsu", "DROCER"]
    assert cap["kw"]["stdin"] is subprocess.DEVNULL
    assert Path(cap["kw"]["cwd"]) == ambiente
    env = cap["kw"]["env"]
    assert Path(env["NFE_SYNC_STATE"]) == ambiente / ".state.json"
    assert Path(env["NFE_SYNC_LOG_DIR"]) == ambiente / "log"
    assert not str(env["NFE_SYNC_CONFIG"]).startswith(str(ambiente))


def test_main_certificado_so_existe_no_tempdir(ambiente, monkeypatch):
    cap, grav = {}, []
    _roda(monkeypatch, 0, cap, grav)
    with pytest.raises(SystemExit):
        rodar.main()
    assert cap["cert_existia"] is True
    assert not cap["cert"].exists()                      # apagado ao final
    assert not any(ambiente.rglob("*.pfx"))              # nunca em NFE_DATA_DIR
    assert "senha = segredo" in cap["conf"]


@pytest.mark.parametrize("rc", [0, 1, 7])
def test_main_exit_code_do_nfe_sync_e_banco_gravado_mesmo_com_falha(ambiente, monkeypatch, rc):
    cap, grav = {}, []
    _roda(monkeypatch, rc, cap, grav)
    with pytest.raises(SystemExit) as e:
        rodar.main()
    assert e.value.code == rc
    assert grav == [(ambiente / "downloads" / CNPJ, CNPJ, "postgresql://x")]


# ---------- AC3: gravar (Postgres real) ----------

DB_URL = os.environ.get("NFE_TEST_DB_URL")


@pytest.fixture
def db():
    if not DB_URL:
        pytest.skip("NFE_TEST_DB_URL nao definida")
    import psycopg
    with psycopg.connect(DB_URL, autocommit=True) as con:
        con.execute("drop schema if exists nfe cascade")
        con.execute((RAIZ / "servico" / "schema.sql").read_text())
    return DB_URL


def _consulta(db, sql):
    import psycopg
    with psycopg.connect(db) as con:
        return con.execute(sql).fetchall()


def _pasta(tmp_path, *nomes):
    p = tmp_path / "dl"
    p.mkdir(exist_ok=True)
    for n in nomes:
        shutil.copy(FIX / n, p / n)
    return p


def test_gravar_idempotente(db, tmp_path):
    p = _pasta(tmp_path, "nfeproc.xml", "resnfe.xml", "resevento.xml")
    (p / "lixo.xml").write_text("<outra/>")
    c1 = rodar.gravar(p, CNPJ, db)
    assert c1["documento"] == 2 and c1["evento"] == 1 and c1["ignorado"] == 1 and c1["gravado"] == 3
    c2 = rodar.gravar(p, CNPJ, db)
    assert c2["gravado"] == 0
    assert _consulta(db, "select count(*) from nfe.documentos") == [(2,)]
    assert _consulta(db, "select count(*) from nfe.eventos") == [(1,)]


def _resumo_da_completa(tmp_path):
    p = tmp_path / "res"
    p.mkdir()
    (p / "r.xml").write_text(
        '<?xml version="1.0"?><resNFe xmlns="http://www.portalfiscal.inf.br/nfe" versao="1.01">'
        f"<chNFe>{CHAVE_COMPLETA}</chNFe><CNPJ>72677370000179</CNPJ><xNome>X</xNome>"
        "<dhEmi>2026-11-05T14:51:00-03:00</dhEmi><vNF>43.40</vNF><nProt>1</nProt></resNFe>", encoding="utf-8")
    return p


def test_completa_nunca_sobrescrita_por_resumo(db, tmp_path):
    rodar.gravar(_pasta(tmp_path, "nfeproc.xml"), CNPJ, db)
    c = rodar.gravar(_resumo_da_completa(tmp_path), CNPJ, db)
    assert c["gravado"] == 0
    assert _consulta(db, "select tipo, cstat from nfe.documentos") == [("completa", "100")]


def test_resumo_promovido_a_completa(db, tmp_path):
    rodar.gravar(_resumo_da_completa(tmp_path), CNPJ, db)
    assert _consulta(db, "select tipo from nfe.documentos") == [("resumo",)]
    c = rodar.gravar(_pasta(tmp_path, "nfeproc.xml"), CNPJ, db)
    assert c["gravado"] == 1
    assert _consulta(db, "select tipo, numero, cstat from nfe.documentos") == [("completa", 25416, "100")]


# ---------- AC4: arquivo ruim nao bloqueia os demais ----------

RES_SEM_CHAVE = ('<?xml version="1.0"?><resNFe xmlns="http://www.portalfiscal.inf.br/nfe" versao="1.01">'
                 "<CNPJ>1</CNPJ><vNF>1.00</vNF></resNFe>")


def _pasta_com_ruins(tmp_path):
    # ruins ordenam antes e depois dos bons, para provar que nada aborta a rodada
    p = _pasta(tmp_path, "nfeproc.xml", "resnfe.xml", "resevento.xml")
    (p / "000-quebrado.xml").write_text("<resNFe><nao fecha", encoding="utf-8")
    (p / "001-sem-chave.xml").write_text(RES_SEM_CHAVE, encoding="utf-8")
    (p / "zzz-quebrado.xml").write_text("nem e xml", encoding="utf-8")
    return p


def test_gravar_arquivo_ruim_nao_impede_os_demais(db, tmp_path, capsys):
    c = rodar.gravar(_pasta_com_ruins(tmp_path), CNPJ, db)
    assert c["erro"] == 3
    assert c["gravado"] == 3 and c["documento"] == 2 and c["evento"] == 1
    assert _consulta(db, "select count(*) from nfe.documentos") == [(2,)]
    assert _consulta(db, "select count(*) from nfe.eventos") == [(1,)]
    out = capsys.readouterr().out
    for nome in ("000-quebrado.xml", "001-sem-chave.xml", "zzz-quebrado.xml"):
        assert nome in out


def test_gravar_sem_erro_contabiliza_zero(db, tmp_path):
    c = rodar.gravar(_pasta(tmp_path, "nfeproc.xml"), CNPJ, db)
    assert c["erro"] == 0


@pytest.mark.parametrize("rc,erro,esperado", [(0, 1, 1), (0, 0, 0), (7, 1, 7), (3, 0, 3)])
def test_main_exit_code_considera_erros_de_arquivo(ambiente, monkeypatch, rc, erro, esperado):
    cap = {}
    _roda(monkeypatch, rc, cap, [])
    monkeypatch.setattr(rodar, "gravar", lambda *a: {"erro": erro})
    with pytest.raises(SystemExit) as e:
        rodar.main()
    assert e.value.code == esperado


# ---------- AC5: filial usa o certificado da matriz ----------

@pytest.mark.parametrize("cert_env,esperado", [(None, "SRJK2"), ("SRJK", "SRJK")])
def test_main_certificado_por_nfe_cert(ambiente, monkeypatch, cert_env, esperado):
    monkeypatch.setenv("NFE_EMPRESA", "SRJK2")
    if cert_env:
        monkeypatch.setenv("NFE_CERT", cert_env)
    else:
        monkeypatch.delenv("NFE_CERT", raising=False)
    pedidos = []
    monkeypatch.setattr(rodar, "buscar_certificado", lambda nome: pedidos.append(nome) or (b"PFX", "s"))
    cap, grav = {}, []
    _roda(monkeypatch, 0, cap, grav)
    with pytest.raises(SystemExit):
        rodar.main()
    assert pedidos == [esperado]
    assert cap["cmd"][-1] == "SRJK2"          # secao do ini / consulta = instancia (CNPJ da filial)
    assert "[SRJK2]" in cap["conf"]


# ---------- AC6: pedidos de ciencia vindos da UI ----------

def _pedido(db, chave, status="pendente", cnpj=CNPJ, com_doc=True):
    import psycopg
    with psycopg.connect(db, autocommit=True) as con:
        if com_doc:
            con.execute("insert into nfe.documentos (cnpj_interessado, chave, tipo, arquivo, xml) "
                        "values (%s,%s,'resumo','a','<x/>') on conflict do nothing", (cnpj, chave))
        con.execute("insert into nfe.pedidos_ciencia (cnpj_interessado, chave, solicitado_por, status) "
                    "values (%s, %s, 'teste@x', %s)", (cnpj, chave, status))


def _fake_manifestar(monkeypatch, saidas, chamadas):
    def fake_run(cmd, **kw):
        chamadas.append((cmd, kw))
        return subprocess.CompletedProcess(cmd, 0, stdout=saidas[cmd[-1]], stderr="")
    monkeypatch.setattr(rodar.subprocess, "run", fake_run)


def test_ciencia_so_das_chaves_pedidas_e_pendentes(db, monkeypatch, tmp_path):
    k_ok, k_dup, k_erro, k_feito, k_outra = ("1" * 44, "2" * 44, "3" * 44, "4" * 44, "5" * 44)
    _pedido(db, k_ok); _pedido(db, k_dup); _pedido(db, k_erro)
    _pedido(db, k_feito, status="feito")             # ja processado: nao repete
    _pedido(db, k_outra, cnpj="99999999000199")      # outra empresa: nao e desta rodada
    saidas = {k_ok: "  cStat=135  Evento registrado e vinculado a NF-e\n",
              k_dup: "  cStat=573  Rejeicao: Duplicidade de evento\n",
              k_erro: "  cStat=650  Rejeicao: NF-e cancelada\n"}
    chamadas = []
    _fake_manifestar(monkeypatch, saidas, chamadas)
    cont = rodar.processar_pedidos_ciencia("DROCER", CNPJ, tmp_path, {"X": "1"}, db)
    assert cont == {"feito": 2, "erro": 1}
    chaves = [c[0][-1] for c in chamadas]
    assert sorted(chaves) == sorted([k_ok, k_dup, k_erro])
    for cmd, kw in chamadas:
        assert cmd[-4:-1] == ["manifestar", "DROCER", "ciencia"] and "--producao" in cmd
        assert kw["stdin"] is subprocess.DEVNULL
    st = dict((r[0], (r[1], r[2])) for r in _consulta(db, "select chave, status, cstat from nfe.pedidos_ciencia"))
    assert st[k_ok] == ("feito", "135") and st[k_dup] == ("feito", "573") and st[k_erro] == ("erro", "650")
    assert st[k_feito] == ("feito", None) and st[k_outra] == ("pendente", None)


def test_ciencia_saida_sem_cstat_vira_erro(db, monkeypatch, tmp_path):
    k = "6" * 44
    _pedido(db, k)
    _fake_manifestar(monkeypatch, {k: "Traceback: certificado invalido"}, [])
    assert rodar.processar_pedidos_ciencia("DROCER", CNPJ, tmp_path, {}, db) == {"feito": 0, "erro": 1}
    status, msg = _consulta(db, "select status, mensagem from nfe.pedidos_ciencia")[0]
    assert status == "erro" and "certificado invalido" in msg


def test_main_processa_pedidos_antes_de_consultar(ambiente, monkeypatch):
    ordem = []
    monkeypatch.setattr(rodar, "processar_pedidos_ciencia", lambda *a: ordem.append("ciencia") or {"feito": 0, "erro": 0})
    monkeypatch.setattr(rodar.subprocess, "run", lambda cmd, **kw: ordem.append(cmd[4]) or subprocess.CompletedProcess(cmd, 0))
    monkeypatch.setattr(rodar, "gravar", lambda *a: {})
    with pytest.raises(SystemExit):
        rodar.main()
    assert ordem == ["ciencia", "consultar-nsu"]


def test_ciencia_usa_cstat_do_evento_e_nao_o_do_lote(db, monkeypatch, tmp_path):
    k_ok, k_rej = "7" * 44, "8" * 44
    _pedido(db, k_ok); _pedido(db, k_rej)
    saidas = {  # formato real do nfe-sync manifestar (hg003, 2026-11-16 12:13)
        k_ok: "=== RESULTADO ===\n  cStat=128  Lote de evento processado\n  cStat=135  Evento registrado e vinculado a NF-e\n  Protocolo: 591267668903764\n",
        k_rej: "=== RESULTADO ===\n  cStat=128  Lote de evento processado\n  cStat=650  Rejeicao: NF-e cancelada\n"}
    _fake_manifestar(monkeypatch, saidas, [])
    assert rodar.processar_pedidos_ciencia("DROCER", CNPJ, tmp_path, {}, db) == {"feito": 1, "erro": 1}
    st = {r[0]: (r[1], r[2], r[3]) for r in _consulta(db, "select chave, status, cstat, mensagem from nfe.pedidos_ciencia")}
    assert st[k_ok] == ("feito", "135", "Evento registrado e vinculado a NF-e")
    assert st[k_rej] == ("erro", "650", "Rejeicao: NF-e cancelada")



# ---------- AC7: XML completo logo apos a ciencia + modo 'pedidos' ----------

def _doc(db, chave, tipo="resumo", cnpj=CNPJ):
    import psycopg
    with psycopg.connect(db, autocommit=True) as con:
        con.execute("insert into nfe.documentos (cnpj_interessado, chave, tipo, arquivo, xml) values (%s,%s,%s,'a','<x/>') "
                    "on conflict (cnpj_interessado, chave) do update set tipo = excluded.tipo", (cnpj, chave, tipo))


def test_baixa_pela_chave_so_ciencia_feita_recente_e_ainda_resumo(db, monkeypatch, tmp_path):
    import psycopg
    k_sim, k_ja_completa, k_antiga, k_pendente = "1" * 44, "2" * 44, "3" * 44, "4" * 44
    for k in (k_sim, k_antiga, k_pendente):
        _doc(db, k)
    _doc(db, k_ja_completa, tipo="completa")
    for k in (k_sim, k_ja_completa, k_antiga):
        _pedido(db, k, status="feito")
    _pedido(db, k_pendente)
    with psycopg.connect(db, autocommit=True) as con:
        con.execute("update nfe.pedidos_ciencia set processado_em = now()")
        con.execute("update nfe.pedidos_ciencia set processado_em = now() - interval '3 hours' where chave = %s", (k_antiga,))
        con.execute("update nfe.pedidos_ciencia set processado_em = null where status = 'pendente'")
    chamadas = []
    monkeypatch.setattr(rodar.subprocess, "run", lambda cmd, **kw: chamadas.append((cmd, kw)) or subprocess.CompletedProcess(cmd, 0))
    assert rodar.baixar_completas_pedidas("DROCER", CNPJ, tmp_path, {}, db) == 1
    cmd, kw = chamadas[0]
    assert cmd[-4:] == ["consultar-nsu", "DROCER", "--chave", k_sim] and "--producao" in cmd
    assert kw["stdin"] is subprocess.DEVNULL


def test_ha_pedidos_a_fazer(db):
    assert rodar.ha_pedidos_a_fazer(CNPJ, db) is False
    _doc(db, "5" * 44); _pedido(db, "5" * 44)
    assert rodar.ha_pedidos_a_fazer(CNPJ, db) is True
    assert rodar.ha_pedidos_a_fazer("99999999000199", db) is False


def test_modo_pedidos_sem_trabalho_nao_toca_infisical_nem_sefaz(ambiente, monkeypatch):
    monkeypatch.setenv("NFE_MODO", "pedidos")
    monkeypatch.setattr(rodar, "ha_pedidos_a_fazer", lambda *a: False)
    monkeypatch.setattr(rodar, "buscar_certificado", lambda *a: pytest.fail("nao devia buscar certificado"))
    monkeypatch.setattr(rodar.subprocess, "run", lambda *a, **k: pytest.fail("nao devia chamar o nfe-sync"))
    with pytest.raises(SystemExit) as e:
        rodar.main()
    assert e.value.code == 0


def test_modo_pedidos_com_trabalho_nao_consulta_por_nsu(ambiente, monkeypatch):
    monkeypatch.setenv("NFE_MODO", "pedidos")
    monkeypatch.setattr(rodar, "ha_pedidos_a_fazer", lambda *a: True)
    ordem = []
    monkeypatch.setattr(rodar, "processar_pedidos_ciencia", lambda *a: ordem.append("ciencia") or {"feito": 1, "erro": 0})
    monkeypatch.setattr(rodar, "baixar_completas_pedidas", lambda *a: ordem.append("chave") or 1)
    monkeypatch.setattr(rodar.subprocess, "run", lambda cmd, **kw: ordem.append("nsu") or subprocess.CompletedProcess(cmd, 0))
    monkeypatch.setattr(rodar, "gravar", lambda *a: ordem.append("gravar") or {})
    with pytest.raises(SystemExit) as e:
        rodar.main()
    assert ordem == ["ciencia", "chave", "gravar"] and e.value.code == 0


# ---------- AC8: gatilho (LISTEN/NOTIFY) ----------

sys.path.insert(0, str(RAIZ / "servico"))
import gatilho  # noqa: E402


def test_trigger_avisa_so_pedido_pendente(db):
    import psycopg
    k = "9" * 44
    _doc(db, k)
    with psycopg.connect(db, autocommit=True) as ouvinte, psycopg.connect(db, autocommit=True) as app:
        ouvinte.execute("listen nfe_pedidos_ciencia")
        app.execute("insert into nfe.pedidos_ciencia (cnpj_interessado, chave, solicitado_por) values (%s,%s,'ui')", (CNPJ, k))
        assert [n.payload for n in ouvinte.notifies(timeout=2, stop_after=1)] == [CNPJ]
        app.execute("update nfe.pedidos_ciencia set status='feito'")
        assert list(ouvinte.notifies(timeout=1)) == []          # processado: nao avisa
        app.execute("update nfe.pedidos_ciencia set status='pendente'")
        assert [n.payload for n in ouvinte.notifies(timeout=2, stop_after=1)] == [CNPJ]  # reaberto: avisa


def test_atender_roda_modo_pedidos_so_das_instancias_do_cnpj(tmp_path, monkeypatch):
    emp = tmp_path / "empresas"; emp.mkdir()
    (emp / "SRJK.env").write_text("NFE_EMPRESA=SRJK\nNFE_CERT=SRJK\nNFE_CNPJ=18816825000144\nNFE_UF=df\n")
    (emp / "SRJK2.env").write_text("# filial\nNFE_EMPRESA=SRJK2\nNFE_CERT=SRJK\nNFE_CNPJ=18816825000225\nNFE_UF=df\n")
    (emp / "DROCER.env").write_text(f"NFE_EMPRESA=DROCER\nNFE_CNPJ={CNPJ}\nNFE_UF=df\n")
    chamadas = []
    monkeypatch.setattr(gatilho.subprocess, "run", lambda cmd, **kw: chamadas.append((cmd, kw)))
    assert gatilho.atender("18816825000225", emp, tmp_path / "dados") == ["SRJK2"]
    cmd, kw = chamadas[0]
    assert cmd[-1].endswith("rodar.py")
    assert kw["env"]["NFE_MODO"] == "pedidos" and kw["env"]["NFE_EMPRESA"] == "SRJK2" and kw["env"]["NFE_CERT"] == "SRJK"
    assert kw["env"]["NFE_DATA_DIR"] == str(tmp_path / "dados" / "SRJK2")
    assert kw["stdin"] is subprocess.DEVNULL
    chamadas.clear()
    assert gatilho.atender(None, emp, tmp_path / "dados") == ["DROCER", "SRJK", "SRJK2"]   # varredura


def test_main_trava_por_empresa(ambiente, monkeypatch):
    travas = []
    monkeypatch.setattr(rodar.fcntl, "flock", lambda f, op: travas.append((Path(f.name).name, op)))
    cap, grav = {}, []
    _roda(monkeypatch, 0, cap, grav)
    with pytest.raises(SystemExit):
        rodar.main()
    assert travas == [(".lock", rodar.fcntl.LOCK_EX)]


# ---------- QA R3: ler_env, ciencia (env/cwd), trava real, loop main do gatilho ----------

def test_ler_env_ignora_comentario_e_vazio_e_preserva_igual_no_valor(tmp_path):
    f = tmp_path / "A.env"
    f.write_text("# c\n\n  NFE_EMPRESA = A \nSENHA=a=b=c\nsem_igual\n#X=1\n")
    assert gatilho.ler_env(f) == {"NFE_EMPRESA": "A", "SENHA": "a=b=c"}


def test_ciencia_passa_env_e_cwd_do_chamador(db, monkeypatch, tmp_path):
    k = "60" * 22
    _pedido(db, k)
    chamadas = []
    _fake_manifestar(monkeypatch, {k: "cStat=135  ok\n"}, chamadas)
    rodar.processar_pedidos_ciencia("DROCER", CNPJ, tmp_path, {"NFE_SYNC_CONFIG": "/c.ini"}, db)
    assert chamadas[0][1]["env"] == {"NFE_SYNC_CONFIG": "/c.ini"} and chamadas[0][1]["cwd"] == tmp_path


def test_ciencia_so_lote_128_vira_erro_com_cstat_e_motivo(db, monkeypatch, tmp_path):
    k = "61" * 22
    _pedido(db, k)
    _fake_manifestar(monkeypatch, {k: "cStat=128  Lote de evento processado\n"}, [])
    assert rodar.processar_pedidos_ciencia("DROCER", CNPJ, tmp_path, {}, db) == {"feito": 0, "erro": 1}
    assert _consulta(db, "select status, cstat, mensagem from nfe.pedidos_ciencia") == [
        ("erro", "128", "Lote de evento processado")]


def test_ciencia_feito_nao_repete_na_segunda_rodada(db, monkeypatch, tmp_path):
    k = "62" * 22
    _pedido(db, k)
    chamadas = []
    _fake_manifestar(monkeypatch, {k: "cStat=135  ok\n"}, chamadas)
    rodar.processar_pedidos_ciencia("DROCER", CNPJ, tmp_path, {}, db)
    assert rodar.processar_pedidos_ciencia("DROCER", CNPJ, tmp_path, {}, db) == {"feito": 0, "erro": 0}
    assert len(chamadas) == 1


def test_baixa_pela_chave_ignora_outro_cnpj(db, monkeypatch, tmp_path):
    k = "63" * 22
    _doc(db, k, cnpj="99999999000199"); _pedido(db, k, status="feito", cnpj="99999999000199")
    import psycopg
    with psycopg.connect(db, autocommit=True) as con:
        con.execute("update nfe.pedidos_ciencia set processado_em = now()")
    chamadas = []
    monkeypatch.setattr(rodar.subprocess, "run", lambda cmd, **kw: chamadas.append(cmd))
    assert rodar.baixar_completas_pedidas("DROCER", CNPJ, tmp_path, {}, db) == 0 and chamadas == []


def test_ha_pedidos_feito_antigo_ou_ja_completa_nao_conta(db):
    import psycopg
    for k, tipo, idade in (("64" * 22, "resumo", "3 hours"), ("65" * 22, "completa", "1 minute")):
        _doc(db, k, tipo=tipo); _pedido(db, k, status="feito")
        with psycopg.connect(db, autocommit=True) as con:
            con.execute(f"update nfe.pedidos_ciencia set processado_em = now() - interval '{idade}' where chave=%s", (k,))
    assert rodar.ha_pedidos_a_fazer(CNPJ, db) is False
    _doc(db, "66" * 22); _pedido(db, "66" * 22, status="erro")      # erro nao reabre sozinho
    assert rodar.ha_pedidos_a_fazer(CNPJ, db) is False


def test_trigger_insert_feito_ou_erro_nao_avisa(db):
    import psycopg
    with psycopg.connect(db, autocommit=True) as ouvinte, psycopg.connect(db, autocommit=True) as app:
        ouvinte.execute("listen nfe_pedidos_ciencia")
        _pedido(db, "67" * 22, status="feito"); _pedido(db, "68" * 22, status="erro")
        app.execute("update nfe.pedidos_ciencia set mensagem='x'")   # update sem mexer em status
        assert list(ouvinte.notifies(timeout=1)) == []


def test_trava_real_serializa_rodadas_da_mesma_empresa(tmp_path):
    """Dois processos reais de rodar.py na mesma NFE_DATA_DIR: o 2o espera o 1o (flock de verdade)."""
    import time
    bin_ = tmp_path / "pkg" / "nfe_sync"; bin_.mkdir(parents=True)
    (bin_ / "__init__.py").write_text("")
    (bin_ / "cli.py").write_text(
        "import os,time\nlog=open(os.environ['LOGF'],'a')\nlog.write('ini\\n');log.flush()\n"
        "time.sleep(1.5)\nlog.write('fim\\n');log.flush()\n")
    runner = tmp_path / "runner.py"
    runner.write_text(
        "import sys,importlib.util\nsys.path.insert(0,%r)\n" % str(tmp_path / "pkg") +
        "s=importlib.util.spec_from_file_location('r',%r)\nr=importlib.util.module_from_spec(s);s.loader.exec_module(r)\n" % str(RAIZ / "servico" / "rodar.py") +
        "r.buscar_certificado=lambda n:(b'x','s')\nr.gravar=lambda *a:{}\nr.processar_pedidos_ciencia=lambda *a:{}\n"
        "r.baixar_completas_pedidas=lambda *a:0\nr.main()\n")
    dados = tmp_path / "d"
    env = {**os.environ, "NFE_EMPRESA": "E", "NFE_CNPJ": CNPJ, "NFE_UF": "df", "NFE_DATA_DIR": str(dados),
           "NFE_DB_URL": "x", "LOGF": str(tmp_path / "log.txt"), "PYTHONPATH": str(tmp_path / "pkg")}
    ps = [subprocess.Popen([sys.executable, str(runner)], env=env) for _ in range(2)]
    for p in ps:
        assert p.wait(30) == 0
    assert (tmp_path / "log.txt").read_text().split() == ["ini", "fim", "ini", "fim"]


# loop main do gatilho com Postgres real e rodar.py de mentira (grava env num log)

STUB = ("import os,json\nopen(os.environ['LOGF'],'a').write(json.dumps({k:os.environ.get(k) for k in "
        "('NFE_EMPRESA','NFE_MODO','NFE_DATA_DIR')})+'\\n')\n")


@pytest.fixture
def gatilho_proc(db, tmp_path, request):
    import json, time
    d = tmp_path / "g"; d.mkdir()
    src = (RAIZ / "servico" / "gatilho.py").read_text()
    assert "VARREDURA_S = 600" in src
    varredura = getattr(request, "param", 60)
    (d / "gatilho.py").write_text(src.replace("VARREDURA_S = 600", f"VARREDURA_S = {varredura}"))
    (d / "rodar.py").write_text(STUB)
    emp = tmp_path / "emp"; emp.mkdir()
    (emp / "AAA.env").write_text(f"NFE_EMPRESA=AAA\nNFE_CNPJ={CNPJ}\n")
    (emp / "BBB.env").write_text("NFE_EMPRESA=BBB\nNFE_CNPJ=99999999000199\n")
    log = tmp_path / "log.jsonl"
    env = {**os.environ, "NFE_DB_URL": db, "NFE_EMPRESAS_DIR": str(emp), "NFE_DADOS_RAIZ": str(tmp_path / "raiz"), "LOGF": str(log)}
    p = subprocess.Popen([sys.executable, "-u", str(d / "gatilho.py")], env=env, stdout=subprocess.PIPE, text=True)

    def linhas():
        return [json.loads(x) for x in log.read_text().splitlines()] if log.exists() else []

    def espera(cond, t=20):
        fim = time.monotonic() + t
        while time.monotonic() < fim:
            if cond():
                return True
            time.sleep(0.1)
        return False
    yield p, linhas, espera, tmp_path
    p.kill(); p.wait()


def test_gatilho_main_varredura_inicial_e_notify_so_do_cnpj(gatilho_proc, db):
    p, linhas, espera, tmp = gatilho_proc                            # varredura periodica = 60 s: nao interfere
    assert espera(lambda: len(linhas()) >= 2, 8)                     # varredura inicial: todas as instancias
    assert sorted(x["NFE_EMPRESA"] for x in linhas()[:2]) == ["AAA", "BBB"]
    import time; time.sleep(0.5)
    base = len(linhas())
    _doc(db, "69" * 22); _pedido(db, "69" * 22)                        # NOTIFY payload = CNPJ da AAA
    assert espera(lambda: len(linhas()) > base, 5)
    time.sleep(1.5)                                                  # tempo para um atender(None) indevido rodar BBB
    assert linhas()[base:] == [{"NFE_EMPRESA": "AAA", "NFE_MODO": "pedidos", "NFE_DATA_DIR": str(tmp / "raiz" / "AAA")}]


@pytest.mark.parametrize("gatilho_proc", [3], indirect=True)
def test_gatilho_main_varredura_periodica(gatilho_proc, db):
    p, linhas, espera, tmp = gatilho_proc
    assert espera(lambda: len(linhas()) >= 2, 8)
    n = len(linhas())
    assert espera(lambda: len(linhas()) >= n + 2, 8)                 # sem nenhum NOTIFY, a varredura roda todas
    assert {x["NFE_EMPRESA"] for x in linhas()[n:n + 2]} == {"AAA", "BBB"}


def test_gatilho_main_reconecta_apos_queda_e_volta_a_atender(gatilho_proc, db):
    import psycopg
    p, linhas, espera, tmp = gatilho_proc
    assert espera(lambda: len(linhas()) >= 2)
    with psycopg.connect(db, autocommit=True) as con:
        con.execute("select pg_terminate_backend(pid) from pg_stat_activity where pid <> pg_backend_pid() "
                    "and datname = current_database()")
    import time; time.sleep(1)
    assert p.poll() is None                                          # nao morreu
    n = len(linhas())
    assert espera(lambda: len(linhas()) >= n + 2, 20)                # reconectou: nova varredura inicial
    time.sleep(0.5); base = len(linhas())
    _doc(db, "70" * 22); _pedido(db, "70" * 22)
    assert espera(lambda: len(linhas()) > base, 2.5)
    assert linhas()[base]["NFE_EMPRESA"] == "AAA"


def test_ciencia_resultado_nao_sobrescreve_pedido_que_deixou_de_ser_pendente(db, monkeypatch, tmp_path):
    import psycopg
    k = "71" * 22
    _pedido(db, k)

    def fake_run(cmd, **kw):                                       # outro processo conclui o pedido durante a chamada
        with psycopg.connect(db, autocommit=True) as con:
            con.execute("update nfe.pedidos_ciencia set status='feito', cstat='135', mensagem='outro'")
        return subprocess.CompletedProcess(cmd, 0, stdout="cStat=650  Rejeicao\n", stderr="")
    monkeypatch.setattr(rodar.subprocess, "run", fake_run)
    rodar.processar_pedidos_ciencia("DROCER", CNPJ, tmp_path, {}, db)
    assert _consulta(db, "select status, cstat, mensagem from nfe.pedidos_ciencia") == [("feito", "135", "outro")]

# ---------- R3: limites (gauntlet arquitetura B1 e nao-bloqueantes) ----------

def test_ciencia_sem_resumo_no_banco_vira_erro_sem_chamar_sefaz(db, monkeypatch, tmp_path):
    k_sem, k_completa = "1" * 44, "2" * 44
    _pedido(db, k_sem, com_doc=False)
    _doc(db, k_completa, tipo="completa"); _pedido(db, k_completa, com_doc=False)
    monkeypatch.setattr(rodar.subprocess, "run", lambda *a, **k: pytest.fail("nao devia chamar a SEFAZ"))
    assert rodar.processar_pedidos_ciencia("DROCER", CNPJ, tmp_path, {}, db) == {"feito": 0, "erro": 0}
    st = {r[0]: (r[1], r[2]) for r in _consulta(db, "select chave, status, mensagem from nfe.pedidos_ciencia")}
    assert st[k_sem][0] == "erro" and "sem resumo" in st[k_sem][1]
    assert st[k_completa][0] == "erro"


def test_busca_por_chave_tem_limite_de_tentativas_e_intervalo(db, monkeypatch, tmp_path):
    import psycopg
    k = "3" * 44
    _pedido(db, k, status="feito")
    with psycopg.connect(db, autocommit=True) as con:
        con.execute("update nfe.pedidos_ciencia set processado_em = now()")
    chamadas = []
    monkeypatch.setattr(rodar.subprocess, "run", lambda cmd, **kw: chamadas.append(cmd) or subprocess.CompletedProcess(cmd, 0))
    assert rodar.baixar_completas_pedidas("DROCER", CNPJ, tmp_path, {}, db) == 1
    assert rodar.baixar_completas_pedidas("DROCER", CNPJ, tmp_path, {}, db) == 0      # < 5 min: nao repete
    assert rodar.ha_pedidos_a_fazer(CNPJ, db) is False
    for _ in range(5):                                                               # passa o intervalo varias vezes
        with psycopg.connect(db, autocommit=True) as con:
            con.execute("update nfe.pedidos_ciencia set ultima_busca_em = now() - interval '6 minutes'")
        rodar.baixar_completas_pedidas("DROCER", CNPJ, tmp_path, {}, db)
    assert len(chamadas) == rodar.MAX_BUSCAS == 3                                    # nunca passa do limite
    assert rodar.ha_pedidos_a_fazer(CNPJ, db) is False


def test_processado_em_no_futuro_nao_prolonga_a_busca(db, monkeypatch, tmp_path):
    import psycopg
    k = "4" * 44
    _pedido(db, k, status="feito")
    with psycopg.connect(db, autocommit=True) as con:
        con.execute("update nfe.pedidos_ciencia set processado_em = now() + interval '100 years'")
    monkeypatch.setattr(rodar.subprocess, "run", lambda *a, **k: pytest.fail("nao devia buscar"))
    assert rodar.baixar_completas_pedidas("DROCER", CNPJ, tmp_path, {}, db) == 0
    assert rodar.ha_pedidos_a_fazer(CNPJ, db) is False


def test_pedidos_ciencia_recusa_chave_e_cnpj_mal_formados(db):
    import psycopg
    with psycopg.connect(db, autocommit=True) as con:
        for cnpj, chave in ((CNPJ, "abc"), ("123", "5" * 44)):
            with pytest.raises(psycopg.errors.CheckViolation):
                con.execute("insert into nfe.pedidos_ciencia (cnpj_interessado, chave, solicitado_por) values (%s,%s,'x')",
                            (cnpj, chave))
