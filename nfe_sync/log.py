import logging
import os
from datetime import datetime, timedelta, timezone

from pynfe.utils import etree

# Issue #4: diretório de log configurável via variável de ambiente
LOG_DIR = os.environ.get("NFE_SYNC_LOG_DIR", "log")
LOG_RETENCAO_DIAS = 7

# Issue #14: timezone BRT para timestamps de log
_BRT = timezone(timedelta(hours=-3))


def _agora_brt() -> datetime:
    """Retorna o datetime atual no fuso BRT (UTC-3) sem informação de timezone."""
    return datetime.now(_BRT).replace(tzinfo=None)


def _limpar_logs_antigos():
    limite = _agora_brt() - timedelta(days=LOG_RETENCAO_DIAS)
    for nome in os.listdir(LOG_DIR):
        caminho = os.path.join(LOG_DIR, nome)
        if os.path.isfile(caminho):
            modificado = datetime.fromtimestamp(os.path.getmtime(caminho))
            if modificado < limite:
                # Issue #13: tratar erros de remoção individualmente
                try:
                    os.remove(caminho)
                except OSError as e:
                    logging.warning("Nao foi possivel remover log %s: %s", caminho, e)


def salvar_resposta_sefaz(xml_resp, operacao: str, identificador: str = "") -> str:
    os.makedirs(LOG_DIR, exist_ok=True)
    _limpar_logs_antigos()
    timestamp = _agora_brt().strftime("%Y%m%d-%H%M%S")
    sufixo = f"-{identificador}" if identificador else ""
    arquivo = f"{LOG_DIR}/{operacao}{sufixo}-{timestamp}.xml"
    xml_str = etree.tostring(xml_resp, encoding="unicode", pretty_print=True)
    with open(arquivo, "w") as f:
        f.write('<?xml version="1.0" encoding="UTF-8"?>\n')
        f.write(xml_str)
    return arquivo
