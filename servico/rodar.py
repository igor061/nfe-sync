"""Rodada do servico: certificado do Infisical -> consultar-nsu -> grava XMLs no Postgres.

Nunca manifesta ciencia: o prompt [s/N] do consultar-nsu recebe stdin vazio (= nao).
"""
import base64
import json
import os
import re
import subprocess
import sys
import tempfile
import urllib.request
from pathlib import Path

from lxml import etree
import psycopg

NS = {"n": "http://www.portalfiscal.inf.br/nfe"}
_PARSER = etree.XMLParser(resolve_entities=False, no_network=True)
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


def processar_pedidos_ciencia(empresa: str, cnpj: str, dados: Path, env: dict, db_url: str) -> dict:
    """Registra a ciencia SO das chaves pedidas pela UI (status 'pendente') desta empresa."""
    cont = {"feito": 0, "erro": 0}
    with psycopg.connect(db_url, autocommit=True) as con:
        pendentes = [r[0] for r in con.execute(
            "select chave from nfe.pedidos_ciencia where cnpj_interessado = %s and status = 'pendente' "
            "order by solicitado_em", (cnpj,))]
        for chave in pendentes:
            proc = subprocess.run(
                [sys.executable, "-m", "nfe_sync.cli", "--producao", "manifestar", empresa, "ciencia", chave],
                cwd=dados, env=env, stdin=subprocess.DEVNULL, capture_output=True, text=True)
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


def main():
    empresa, cnpj, uf = os.environ["NFE_EMPRESA"], os.environ["NFE_CNPJ"], os.environ["NFE_UF"]
    dados = Path(os.environ.get("NFE_DATA_DIR", "/data"))
    # Filial usa o certificado da matriz (mesma raiz de CNPJ): NFE_CERT aponta o prefixo no Infisical.
    pfx, senha = buscar_certificado(os.environ.get("NFE_CERT", empresa))
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
        rc = subprocess.run([sys.executable, "-m", "nfe_sync.cli", "--producao", "consultar-nsu", empresa],
                            cwd=dados, env=env, stdin=subprocess.DEVNULL).returncode
    cont = gravar(dados / "downloads" / cnpj, cnpj, os.environ["NFE_DB_URL"])
    print(f"Banco: {cont}", flush=True)
    sys.exit(rc or (1 if cont.get("erro") else 0))


if __name__ == "__main__":
    main()
