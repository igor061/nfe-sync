import fcntl
import json
from pathlib import Path


def carregar_estado(state_file: str) -> dict:
    path = Path(state_file)
    if not path.exists():
        return {}
    with open(path) as f:
        fcntl.flock(f, fcntl.LOCK_SH)
        try:
            return json.loads(f.read())
        finally:
            fcntl.flock(f, fcntl.LOCK_UN)


def salvar_estado(state_file: str, estado: dict) -> None:
    with open(state_file, "a+") as f:
        fcntl.flock(f, fcntl.LOCK_EX)
        try:
            f.seek(0)
            f.truncate()
            f.write(json.dumps(estado, indent=2, ensure_ascii=False) + "\n")
        finally:
            fcntl.flock(f, fcntl.LOCK_UN)


def get_ultimo_numero_nf(estado: dict, cnpj: str, serie: str, ambiente: str = "producao") -> int:
    return estado.get("numeracao", {}).get(f"{cnpj}:{serie}:{ambiente}", 0)


def set_ultimo_numero_nf(estado: dict, cnpj: str, serie: str, numero: int, ambiente: str = "producao") -> None:
    estado.setdefault("numeracao", {})[f"{cnpj}:{serie}:{ambiente}"] = numero


def _chave_cooldown(cnpj: str, ambiente: str) -> str:
    return f"{cnpj}:{ambiente}"


def get_cooldown(estado: dict, cnpj: str, ambiente: str = "homologacao") -> str | None:
    return estado.get("cooldown", {}).get(_chave_cooldown(cnpj, ambiente))


def set_cooldown(estado: dict, cnpj: str, iso_str: str, ambiente: str = "homologacao") -> None:
    estado.setdefault("cooldown", {})[_chave_cooldown(cnpj, ambiente)] = iso_str


def limpar_cooldown(estado: dict, cnpj: str, ambiente: str = "homologacao") -> None:
    cooldowns = estado.get("cooldown", {})
    cooldowns.pop(_chave_cooldown(cnpj, ambiente), None)


def get_ultimo_nsu(estado: dict, cnpj: str, ambiente: str = "producao") -> int:
    return estado.get("nsu", {}).get(f"{cnpj}:{ambiente}", 0)


def set_ultimo_nsu(estado: dict, cnpj: str, nsu: int, ambiente: str = "producao") -> None:
    estado.setdefault("nsu", {})[f"{cnpj}:{ambiente}"] = nsu
