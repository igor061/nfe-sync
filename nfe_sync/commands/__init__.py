import logging
import os
import sys
from abc import ABC, abstractmethod

from ..config import carregar_empresas
from ..state import carregar_estado, salvar_estado
from ..log import salvar_resposta_sefaz
from ..exceptions import NfeConfigError, NfeValidationError
from ..xml_utils import safe_parse, safe_fromstring

# Issue #4: caminhos de config e estado configuráveis via variáveis de ambiente
CONFIG_FILE = os.environ.get("NFE_SYNC_CONFIG", "nfe-sync.conf.ini")
STATE_FILE = os.environ.get("NFE_SYNC_STATE", ".state.json")


class CliBlueprint(ABC):
    """Base para todos os grupos de comandos CLI. Cada subclasse registra seus subcomandos."""

    @abstractmethod
    def register(self, subparsers, parser) -> None:
        """Registra os subcomandos no argparse. parser é o parser raiz."""
        ...


# ---------------------------------------------------------------------------
# Helpers de contexto e I/O — compartilhados por todos os blueprints
# ---------------------------------------------------------------------------

def _carregar(args):
    empresas = carregar_empresas(CONFIG_FILE)
    nome = args.empresa
    if nome not in empresas:
        print(f"Erro: empresa '{nome}' nao encontrada.")
        print(f"Empresas disponiveis: {', '.join(empresas.keys())}")
        sys.exit(1)
    empresa = empresas[nome]
    if args.producao:
        empresa = empresa.model_copy(update={"homologacao": False})
    elif args.homologacao:
        empresa = empresa.model_copy(update={"homologacao": True})
    estado = carregar_estado(STATE_FILE)
    return empresa, estado


def _salvar_xml(cnpj: str, nome: str, xml: str) -> str:
    """Cria downloads/{cnpj}/ e salva XML. Retorna o caminho do arquivo."""
    pasta = f"downloads/{cnpj}"
    os.makedirs(pasta, exist_ok=True)
    caminho = f"{pasta}/{nome}"
    with open(caminho, "w") as f:
        f.write(xml)
    return caminho


def _salvar_log_xml(xml_str: str, tipo: str, ref: str) -> str:
    """Salva resposta SEFAZ em log/. Wrapper sobre log.salvar_resposta_sefaz()."""
    xml_el = safe_fromstring(xml_str.encode())
    return salvar_resposta_sefaz(xml_el, tipo, ref)


def _listar_resumos_pendentes(cnpj: str) -> list[str]:
    """Escaneia downloads/{cnpj}/ por arquivos resNFe (root tag = resNFe)."""
    pasta = f"downloads/{cnpj}"
    if not os.path.isdir(pasta):
        return []
    resumos = []
    for nome in os.listdir(pasta):
        if not nome.endswith(".xml"):
            continue
        # Issue #9: confiar apenas no root tag XML, sem filtrar por len(nome)
        try:
            tree = safe_parse(os.path.join(pasta, nome))
            root = tree.getroot()
            local = root.tag.split("}")[-1] if "}" in root.tag else root.tag
            if local == "resNFe":
                resumos.append(nome[:-4])
        except Exception as e:
            # Issue #10: logar em vez de engolir silenciosamente
            logging.warning("Arquivo %s ignorado: %s", nome, e)
    return resumos
