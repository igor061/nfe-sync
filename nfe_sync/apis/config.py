import json
from pathlib import Path

from ..exceptions import NfeConfigError

DEFAULT_CONFIG_FILE = "apis.json"


def carregar_apis(config_file=DEFAULT_CONFIG_FILE) -> dict:
    path = Path(config_file)
    if not path.exists():
        raise NfeConfigError(f"Arquivo de configuracao '{config_file}' nao encontrado.")
    with open(path) as f:
        return json.load(f)


def get_api_config(nome: str, config_file=DEFAULT_CONFIG_FILE) -> dict:
    apis = carregar_apis(config_file)
    if nome not in apis:
        raise NfeConfigError(
            f"API '{nome}' nao configurada em '{config_file}'. "
            f"APIs disponiveis: {', '.join(apis.keys())}"
        )
    return apis[nome]
