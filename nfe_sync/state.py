import json
from pathlib import Path


def carregar_estado(state_file: str) -> dict:
    path = Path(state_file)
    if not path.exists():
        return {}
    return json.loads(path.read_text())


def salvar_estado(state_file: str, estado: dict) -> None:
    Path(state_file).write_text(json.dumps(estado, indent=2, ensure_ascii=False) + "\n")


def get_ultimo_numero_nf(estado: dict, cnpj: str, serie: str) -> int:
    chave = f"{cnpj}:{serie}"
    return estado.get("numeracao", {}).get(chave, 0)


def set_ultimo_numero_nf(estado: dict, cnpj: str, serie: str, numero: int) -> None:
    estado.setdefault("numeracao", {})[f"{cnpj}:{serie}"] = numero


def get_cooldown(estado: dict, cnpj: str) -> str | None:
    return estado.get("cooldown", {}).get(cnpj)


def set_cooldown(estado: dict, cnpj: str, iso_str: str) -> None:
    estado.setdefault("cooldown", {})[cnpj] = iso_str


def limpar_cooldown(estado: dict, cnpj: str) -> None:
    cooldowns = estado.get("cooldown", {})
    cooldowns.pop(cnpj, None)
