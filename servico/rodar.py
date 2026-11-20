"""Rodada do servico: certificado do Infisical -> consultar-nsu -> grava XMLs no Postgres.

Nunca manifesta ciencia: o prompt [s/N] do consultar-nsu recebe stdin vazio (= nao).
"""
import base64
import fcntl
import json
import os
import re
import subprocess
import sys
import tempfile
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path

from lxml import etree
import psycopg

NS = {"n": "http://www.portalfiscal.inf.br/nfe"}
_PARSER = etree.XMLParser(resolve_entities=False, no_network=True)
_BRT = timezone(timedelta(hours=-3))  # mesmo fuso que o nfe-sync usa no cooldown
_SEGREDOS = ("INFISICAL_CLIENT_SECRET", "INFISICAL_CLIENT_ID", "NFE_DB_URL")


def _api(metodo, caminho, corpo=None, token=None):
    url = os.environ["INFISICAL_DOMAIN"].rstrip("/").removesuffix("/api") + caminho
    headers = {"User-Agent": "nfe-sync-servico", "Content-Type": "application/json"}
    if token:
        headers["Authorization"] = "Bearer " + token
    req = urllib.request.Request(url, method=metodo, headers=headers,
                                 data=json.dumps(corpo).encode() if corpo else None)
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.load(r)


def buscar_certificado(nome):
    token = _api("POST", "/api/v1/auth/universal-auth/login", {
        "clientId": os.environ["INFISICAL_CLIENT_ID"],
        "clientSecret": os.environ["INFISICAL_CLIENT_SECRET"],
    })["accessToken"]
    projeto = os.environ["NFE_CERT_PROJECT_ID"]
    segredos = {s["secretKey"]: s["secretValue"] for s in _api(
        "GET", f"/api/v3/secrets/raw?workspaceId={projeto}&environment=prod&secretPath=/", token=token)["secrets"]}
    return base64.b64decode(segredos[f"{nome}_PFX_B64"]), segredos[f"{nome}_PFX_SENHA"]


def _t(no, caminho):
    r = no.find(caminho, NS)
    return r.text if r is not None else None


def ler_xml(arquivo: Path):
    """Retorna ('documento'|'evento', campos) ou None se o XML nao for de NF-e/evento."""
    raiz = etree.parse(str(arquivo), _PARSER).getroot()
    tag = etree.QName(raiz).localname
    xml = arquivo.read_text(encoding="utf-8")
    if tag == "nfeProc":
        inf = raiz.find(".//n:infNFe", NS)
        return "documento", {
            "chave": inf.get("Id")[3:], "tipo": "completa",
            "emitente_cnpj": _t(inf, "n:emit/n:CNPJ") or _t(inf, "n:emit/n:CPF"),
            "emitente_nome": _t(inf, "n:emit/n:xNome"),
            "destinatario_cnpj": _t(inf, "n:dest/n:CNPJ") or _t(inf, "n:dest/n:CPF"),
            "numero": _t(inf, "n:ide/n:nNF"), "serie": _t(inf, "n:ide/n:serie"),
            "emitida_em": _t(inf, "n:ide/n:dhEmi"), "valor_total": _t(inf, "n:total/n:ICMSTot/n:vNF"),
            "cstat": _t(raiz, ".//n:infProt/n:cStat"), "protocolo": _t(raiz, ".//n:infProt/n:nProt"),
            "xml": xml,
        }
    if tag == "resNFe":
        return "documento", {
            "chave": _t(raiz, "n:chNFe"), "tipo": "resumo",
            "emitente_cnpj": _t(raiz, "n:CNPJ") or _t(raiz, "n:CPF"), "emitente_nome": _t(raiz, "n:xNome"),
            "destinatario_cnpj": None, "numero": None, "serie": None,
            "emitida_em": _t(raiz, "n:dhEmi"), "valor_total": _t(raiz, "n:vNF"),
            "cstat": None, "protocolo": _t(raiz, "n:nProt"), "xml": xml,
        }
    if tag in ("procEventoNFe", "resEvento"):
        ev = raiz.find(".//n:infEvento", NS) if tag == "procEventoNFe" else raiz
        return "evento", {
            "chave": _t(ev, "n:chNFe"), "tp_evento": _t(ev, "n:tpEvento"),
            "seq": _t(ev, "n:nSeqEvento"), "descricao": _t(ev, ".//n:descEvento") or _t(ev, "n:xEvento"),
            "ocorrido_em": _t(ev, "n:dhEvento"), "cstat": _t(raiz, ".//n:retEvento/n:infEvento/n:cStat"),
            "xml": xml,
        }
    return None


SQL_DOC = """
insert into nfe.documentos (cnpj_interessado, chave, tipo, emitente_cnpj, emitente_nome, destinatario_cnpj,
    numero, serie, emitida_em, valor_total, cstat, protocolo, arquivo, xml)
values (%(cnpj)s, %(chave)s, %(tipo)s, %(emitente_cnpj)s, %(emitente_nome)s, %(destinatario_cnpj)s,
    %(numero)s, %(serie)s, %(emitida_em)s, %(valor_total)s, %(cstat)s, %(protocolo)s, %(arquivo)s, %(xml)s)
on conflict (cnpj_interessado, chave) do update set
    tipo = excluded.tipo, emitente_cnpj = excluded.emitente_cnpj, emitente_nome = excluded.emitente_nome,
    destinatario_cnpj = excluded.destinatario_cnpj, numero = excluded.numero, serie = excluded.serie,
    emitida_em = excluded.emitida_em, valor_total = excluded.valor_total, cstat = excluded.cstat,
    protocolo = excluded.protocolo, arquivo = excluded.arquivo, xml = excluded.xml, atualizado_em = now()
where nfe.documentos.xml is distinct from excluded.xml
  and not (nfe.documentos.tipo = 'completa' and excluded.tipo = 'resumo')
"""

SQL_EVENTO = """
insert into nfe.eventos (cnpj_interessado, arquivo, chave, tp_evento, seq, descricao, ocorrido_em, cstat, xml)
values (%(cnpj)s, %(arquivo)s, %(chave)s, %(tp_evento)s, %(seq)s, %(descricao)s, %(ocorrido_em)s, %(cstat)s, %(xml)s)
on conflict (cnpj_interessado, arquivo) do update set
    chave = excluded.chave, tp_evento = excluded.tp_evento, seq = excluded.seq, descricao = excluded.descricao,
    ocorrido_em = excluded.ocorrido_em, cstat = excluded.cstat, xml = excluded.xml, atualizado_em = now()
where nfe.eventos.xml is distinct from excluded.xml
"""


def gravar(pasta: Path, cnpj: str, db_url: str) -> dict:
    """Upsert de cada XML em transacao propria: um arquivo ruim nao bloqueia os demais."""
    cont = {"documento": 0, "evento": 0, "ignorado": 0, "gravado": 0, "erro": 0}
    with psycopg.connect(db_url, autocommit=True) as con:
        for arquivo in sorted(pasta.glob("*.xml")):
            try:
                lido = ler_xml(arquivo)
                if lido is None:
                    cont["ignorado"] += 1
                    continue
                tipo, campos = lido
                with con.transaction(), con.cursor() as cur:
                    cur.execute(SQL_DOC if tipo == "documento" else SQL_EVENTO,
                                {**campos, "cnpj": cnpj, "arquivo": arquivo.name})
                    cont["gravado"] += cur.rowcount
                cont[tipo] += 1
            except (etree.XMLSyntaxError, UnicodeDecodeError, ValueError, psycopg.DataError, psycopg.IntegrityError, AttributeError, TypeError) as e:
                cont["erro"] += 1
                print(f"ERRO {arquivo.name}: {type(e).__name__}: {e}", flush=True)
    return cont


# cStat do evento de ciencia: 135/136 registrado; 573 ja existia (duplicidade) — ambos = feito.
_CIENCIA_OK = {"135", "136", "573"}
MAX_BUSCAS = 3
TIMEOUT_SEFAZ_S = 180


def processar_pedidos_ciencia(empresa: str, cnpj: str, dados: Path, env: dict, db_url: str) -> dict:
    """Registra a ciencia SO das chaves pedidas pela UI (status 'pendente') desta empresa."""
    cont = {"feito": 0, "erro": 0}
    with psycopg.connect(db_url, autocommit=True) as con:
        # Sem a nota como 'resumo' desta empresa no banco, nao manifesta: erro sem chamar a SEFAZ.
        con.execute(
            "update nfe.pedidos_ciencia p set status = 'erro', mensagem = 'Chave sem resumo desta empresa no banco', "
            "processado_em = now() where p.cnpj_interessado = %s and p.status = 'pendente' and not exists ("
            "select 1 from nfe.documentos d where d.cnpj_interessado = p.cnpj_interessado and d.chave = p.chave "
            "and d.tipo = 'resumo')", (cnpj,))
        pendentes = [r[0] for r in con.execute(
            "select chave from nfe.pedidos_ciencia where cnpj_interessado = %s and status = 'pendente' "
            "order by solicitado_em", (cnpj,))]
        for chave in pendentes:
            proc = subprocess.run(
                [sys.executable, "-m", "nfe_sync.cli", "--producao", "manifestar", empresa, "ciencia", chave],
                cwd=dados, env=env, stdin=subprocess.DEVNULL, capture_output=True, text=True, timeout=TIMEOUT_SEFAZ_S)
            saida = proc.stdout + proc.stderr
            print(saida, end="", flush=True)
            # A resposta traz o cStat do lote (128) e o do evento (135/136/573/...): vale o do evento.
            achados = [(c, m.strip()) for c, m in re.findall(r"cStat=(\d+)\s+(.*)", saida)]
            ok = [a for a in achados if a[0] in _CIENCIA_OK]
            evento = ok[0] if ok else next((a for a in reversed(achados) if a[0] != "128"), achados[-1] if achados else None)
            cstat, motivo = evento if evento else (None, saida.strip()[-300:])
            status = "feito" if cstat in _CIENCIA_OK else "erro"
            cont[status] += 1
            con.execute(
                "update nfe.pedidos_ciencia set status = %s, cstat = %s, mensagem = %s, processado_em = now() "
                "where cnpj_interessado = %s and chave = %s and status = 'pendente'",
                (status, cstat, motivo, cnpj, chave))
    return cont


def baixar_completas_pedidas(empresa: str, cnpj: str, dados: Path, env: dict, db_url: str) -> int:
    """Logo apos a ciencia a SEFAZ ja entrega o procNFe pela chave (medido: ~1 min).
    Busca por chave so as notas com ciencia feita nas ultimas 2 h que ainda estao como resumo;
    depois disso a distribuicao normal (de hora em hora) traz o XML, sem martelar a SEFAZ."""
    with psycopg.connect(db_url, autocommit=True) as con:
        # Reserva a tentativa ANTES de chamar (no maximo MAX_BUSCAS por pedido, 5 min entre elas);
        # processado_em no futuro nao conta (nao prolonga a janela).
        chaves = [r[0] for r in con.execute(
            "update nfe.pedidos_ciencia p set buscas = p.buscas + 1, ultima_busca_em = now() "
            "from nfe.documentos d where d.cnpj_interessado = p.cnpj_interessado and d.chave = p.chave "
            "and p.cnpj_interessado = %s and p.status = 'feito' and d.tipo = 'resumo' "
            "and p.processado_em between now() - interval '2 hours' and now() "
            "and p.buscas < %s and (p.ultima_busca_em is null or p.ultima_busca_em < now() - interval '5 minutes') "
            "returning p.chave", (cnpj, MAX_BUSCAS))]
    for chave in chaves:
        try:
            subprocess.run([sys.executable, "-m", "nfe_sync.cli", "--producao", "consultar-nsu", empresa, "--chave", chave],
                           cwd=dados, env=env, stdin=subprocess.DEVNULL, timeout=TIMEOUT_SEFAZ_S)
        except subprocess.TimeoutExpired:
            print(f"busca pela chave {chave}: timeout", flush=True)
    return len(chaves)


def ha_pedidos_a_fazer(cnpj: str, db_url: str) -> bool:
    """Modo 'pedidos' roda a cada 2 min: sem trabalho, sai sem tocar no Infisical nem na SEFAZ."""
    with psycopg.connect(db_url, autocommit=True) as con:
        return con.execute(
            "select exists (select 1 from nfe.pedidos_ciencia p join nfe.documentos d using (cnpj_interessado, chave) "
            "where p.cnpj_interessado = %s and (p.status = 'pendente' or (p.status = 'feito' and d.tipo = 'resumo' "
            "and p.processado_em between now() - interval '2 hours' and now() and p.buscas < %s "
            "and (p.ultima_busca_em is null or p.ultima_busca_em < now() - interval '5 minutes'))))",
            (cnpj, MAX_BUSCAS)).fetchone()[0]


ARQ_PEDIDO = ".pedido-consulta.json"  # pedido de "Consultar agora" entregue pelo gatilho


def ler_pedido(dados: Path):
    """Pedido de consulta entregue pelo gatilho ({id, forcar, por}) ou None."""
    try:
        return json.loads((dados / ARQ_PEDIDO).read_text())
    except (OSError, ValueError):
        return None


def concluir_pedido(dados: Path, pedido: dict, rc_info: tuple, db_url: str):
    """Marca o pedido feito/erro conforme o resultado desta rodada e apaga o arquivo."""
    rc, info = rc_info
    if "Status" in info and "BLOQUEADO" not in info:
        status, cstat, msg = "feito", info["Status"], info.get("Motivo")
    elif "BLOQUEADO" in info:
        ate = cooldown_ate(dados, os.environ["NFE_CNPJ"])
        status, cstat, msg = "erro", None, f"em espera até {ate.astimezone(_BRT):%H:%M}" if ate else "em espera"
    else:
        status, cstat, msg = "erro", None, f"rodada sem consulta (rc={rc})"
    with psycopg.connect(db_url, autocommit=True) as con:
        con.execute("update nfe.pedidos_consulta set status = %s, cstat = %s, mensagem = %s, processado_em = now() "
                    "where id = %s and status = 'pendente'", (status, cstat, msg, pedido["id"]))
    (dados / ARQ_PEDIDO).unlink(missing_ok=True)
    print(f"Pedido de consulta {pedido['id']} -> {status}: {msg}", flush=True)


def cooldown_ate(dados: Path, cnpj: str):
    """Fim do cooldown (datetime com fuso) deste CNPJ no .state.json, ou None se nao ha/ja passou."""
    try:
        iso = json.loads((dados / ".state.json").read_text()).get("cooldown", {}).get(f"{cnpj}:producao")
        dt = datetime.fromisoformat(iso)
    except (OSError, ValueError, TypeError):
        return None
    dt = dt if dt.tzinfo else dt.replace(tzinfo=_BRT)
    return dt if dt > datetime.now(_BRT) else None


def remover_cooldown(dados: Path, cnpj: str, quem: str):
    """NFE_FORCAR=1: tira o cooldown do CNPJ do estado antes de consultar (chamar com a trava)."""
    arq = dados / ".state.json"
    try:
        estado = json.loads(arq.read_text())
    except (OSError, ValueError):
        return
    if estado.get("cooldown", {}).pop(f"{cnpj}:producao", None):
        arq.write_text(json.dumps(estado, indent=2, ensure_ascii=False) + "\n")
    print(f"FORÇADO: cooldown removido a pedido de {quem}", flush=True)


def consultar_nsu(empresa: str, dados: Path, env: dict):
    """Roda o consultar-nsu repassando a saida linha a linha ao journal. Retorna (rc, info)."""
    info = {}
    proc = subprocess.Popen([sys.executable, "-m", "nfe_sync.cli", "--producao", "consultar-nsu", empresa],
                            cwd=dados, env=env, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                            stderr=subprocess.STDOUT, text=True)
    for linha in proc.stdout:
        print(linha, end="", flush=True)
        m = re.match(r"(Status|Motivo|Ultimo NSU|Max NSU|BLOQUEADO): ?(.*)", linha.strip())
        if m:
            info[m.group(1)] = m.group(2)
    return proc.wait(), info


def gravar_status(empresa: str, cnpj: str, dados: Path, rc_info: tuple, db_url: str):
    """Upsert em nfe.consultas_status. Bloqueado (sem consulta): so rodada_em/bloqueado_ate mudam."""
    rc, info = rc_info
    ate = cooldown_ate(dados, cnpj)
    consultou = "Status" in info and "BLOQUEADO" not in info
    cstat = info.get("Status") if consultou else None
    with psycopg.connect(db_url, autocommit=True) as con:
        r = con.execute(
            "insert into nfe.consultas_status (cnpj_interessado, empresa, rodada_em, consultado_em, cstat, motivo, "
            "ult_nsu, max_nsu, bloqueado_ate, ultimo_656_em) "
            "values (%(c)s, %(e)s, now(), case when %(q)s then now() end, %(cs)s, %(mo)s, %(u)s, %(mx)s, %(b)s, "
            "case when %(cs)s = '656' then now() end) "
            "on conflict (cnpj_interessado) do update set empresa = excluded.empresa, rodada_em = now(), "
            "bloqueado_ate = excluded.bloqueado_ate, "
            "consultado_em = coalesce(excluded.consultado_em, nfe.consultas_status.consultado_em), "
            "cstat = case when %(q)s then excluded.cstat else nfe.consultas_status.cstat end, "
            "motivo = case when %(q)s then excluded.motivo else nfe.consultas_status.motivo end, "
            "ult_nsu = coalesce(excluded.ult_nsu, nfe.consultas_status.ult_nsu), "
            "max_nsu = coalesce(excluded.max_nsu, nfe.consultas_status.max_nsu), "
            "ultimo_656_em = coalesce(excluded.ultimo_656_em, nfe.consultas_status.ultimo_656_em) "
            "returning ultimo_656_em, consultado_em",
            {"c": cnpj, "e": empresa, "q": consultou, "cs": cstat, "mo": info.get("Motivo") if consultou else None,
             "u": int(info["Ultimo NSU"]) if consultou and "Ultimo NSU" in info else None,
             "mx": int(info["Max NSU"]) if consultou and "Max NSU" in info else None, "b": ate}).fetchone()
    if "BLOQUEADO" in info:
        hora = f"{ate.astimezone(_BRT):%H:%M}" if ate else None
        if r[0] and r[1] and r[0] >= r[1]:  # ultimo resultado foi 656: pedagio
            print(f"PEDÁGIO: {empresa} em espera até {hora or '?'} (656 às {r[0].astimezone(_BRT):%H:%M})", flush=True)
        else:  # espera normal (137)
            print(f"ESPERA: {empresa} próxima consulta liberada às {hora or '?'}", flush=True)


def main():
    empresa, cnpj, uf = os.environ["NFE_EMPRESA"], os.environ["NFE_CNPJ"], os.environ["NFE_UF"]
    dados = Path(os.environ.get("NFE_DATA_DIR", "/data"))
    # NFE_MODO=pedidos: so atende pedidos da UI (ciencia + XML pela chave), sem a consulta por NSU.
    so_pedidos = os.environ.get("NFE_MODO") == "pedidos"
    if so_pedidos and not ha_pedidos_a_fazer(cnpj, os.environ["NFE_DB_URL"]):
        sys.exit(0)
    # Filial usa o certificado da matriz (mesma raiz de CNPJ): NFE_CERT aponta o prefixo no Infisical.
    pfx, senha = buscar_certificado(os.environ.get("NFE_CERT", empresa))
    # Uma rodada por empresa de cada vez (rodada de hora em hora x gatilho de pedidos): mesmo .state.json/downloads.
    dados.mkdir(parents=True, exist_ok=True)
    trava = open(dados / ".lock", "w")
    fcntl.flock(trava, fcntl.LOCK_EX)
    with tempfile.TemporaryDirectory() as tmp:
        cert = Path(tmp, "cert.pfx")
        cert.write_bytes(pfx)
        conf = Path(tmp, "nfe-sync.conf.ini")
        conf.write_text(f"[{empresa}]\npath = {cert}\nsenha = {senha.replace('%', '%%')}\nuf = {uf}\nhomologacao = false\ncnpj = {cnpj}\n")
        env = {**{k: v for k, v in os.environ.items() if k not in _SEGREDOS}, "NFE_SYNC_CONFIG": str(conf), "NFE_SYNC_STATE": str(dados / ".state.json"),
               "NFE_SYNC_LOG_DIR": str(dados / "log")}
        pedidos = processar_pedidos_ciencia(empresa, cnpj, dados, env, os.environ["NFE_DB_URL"])
        if any(pedidos.values()):
            print(f"Pedidos de ciencia: {pedidos}", flush=True)
        baixadas = baixar_completas_pedidas(empresa, cnpj, dados, env, os.environ["NFE_DB_URL"])
        if baixadas:
            print(f"XML completo pedido pela chave: {baixadas}", flush=True)
        pedido = None if so_pedidos else ler_pedido(dados)
        if not so_pedidos and (os.environ.get("NFE_FORCAR") == "1" or (pedido and pedido.get("forcar"))):
            remover_cooldown(dados, cnpj, (pedido or {}).get("por") or os.environ.get("NFE_SOLICITADO_POR", "?"))
        rc, info = (0, {}) if so_pedidos else consultar_nsu(empresa, dados, env)
        if not so_pedidos:
            try:
                gravar_status(empresa, cnpj, dados, (rc, info), os.environ["NFE_DB_URL"])
            except Exception as e:  # status e acessorio: nao pode impedir a gravacao dos XMLs
                print(f"ERRO ao gravar consultas_status: {type(e).__name__}: {e}", flush=True)
            if pedido:
                try:
                    concluir_pedido(dados, pedido, (rc, info), os.environ["NFE_DB_URL"])
                except Exception as e:  # idem: o gatilho vence o pedido em 20 min
                    print(f"ERRO ao concluir pedido de consulta: {type(e).__name__}: {e}", flush=True)
    cont = gravar(dados / "downloads" / cnpj, cnpj, os.environ["NFE_DB_URL"])
    print(f"Banco: {cont}", flush=True)
    sys.exit(rc or (1 if cont.get("erro") else 0))


if __name__ == "__main__":
    main()
