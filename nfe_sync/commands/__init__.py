import logging
import os
import sys
from abc import ABC, abstractmethod

from ..config import carregar_empresas
from ..state import carregar_estado, salvar_estado
from ..log import salvar_resposta_sefaz
from ..exceptions import NfeConfigError, NfeValidationError
from ..xml_utils import safe_fromstring
from ..storage import DocumentoStorage

_storage = DocumentoStorage()

# Issue #4: caminhos de config e estado configuráveis via variáveis de ambiente
CONFIG_FILE = os.environ.get("NFE_SYNC_CONFIG", "nfe-sync.conf.ini")
STATE_FILE = os.environ.get("NFE_SYNC_STATE", ".state.json")


class CliBlueprint(ABC):
    """Base para todos os grupos de comandos CLI. Cada subclasse registra seus subcomandos."""

    @abstractmethod
    def register(self, subparsers, parser, amb_parent=None) -> None:
        """Registra os subcomandos no argparse. parser é o parser raiz.
        amb_parent, quando fornecido, deve ser passado como parents= nos
        subparsers que aceitam --producao/--homologacao (issue #20)."""
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
    return _storage.salvar(cnpj, nome, xml)


def _salvar_log_xml(xml_str: str, tipo: str, ref: str) -> str:
    """Salva resposta SEFAZ em log/. Wrapper sobre log.salvar_resposta_sefaz()."""
    xml_el = safe_fromstring(xml_str.encode())
    return salvar_resposta_sefaz(xml_el, tipo, ref)


def _listar_resumos_pendentes(cnpj: str) -> list[str]:
    """Escaneia downloads/{cnpj}/ por arquivos resNFe (root tag = resNFe)."""
    return _storage.listar_resumos_pendentes(cnpj)
