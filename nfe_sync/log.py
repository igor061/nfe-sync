import os
from datetime import datetime, timedelta

from pynfe.utils import etree

LOG_DIR = "log"
LOG_RETENCAO_DIAS = 7


def _limpar_logs_antigos():
    limite = datetime.now() - timedelta(days=LOG_RETENCAO_DIAS)
    for nome in os.listdir(LOG_DIR):
        caminho = os.path.join(LOG_DIR, nome)
        if os.path.isfile(caminho):
            modificado = datetime.fromtimestamp(os.path.getmtime(caminho))
            if modificado < limite:
                os.remove(caminho)


def salvar_resposta_sefaz(xml_resp, operacao: str, identificador: str = "") -> str:
    os.makedirs(LOG_DIR, exist_ok=True)
    _limpar_logs_antigos()
    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    sufixo = f"-{identificador}" if identificador else ""
    arquivo = f"{LOG_DIR}/{operacao}{sufixo}-{timestamp}.xml"
    xml_str = etree.tostring(xml_resp, encoding="unicode", pretty_print=True)
    with open(arquivo, "w") as f:
        f.write('<?xml version="1.0" encoding="UTF-8"?>\n')
        f.write(xml_str)
    return arquivo
