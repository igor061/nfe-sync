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

def _pedido(db, chave, status="pendente", cnpj=CNPJ):
    import psycopg
    with psycopg.connect(db, autocommit=True) as con:
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
