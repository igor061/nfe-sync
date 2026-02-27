# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project

nfe-sync — biblioteca Python + CLI para emissão, consulta, manifestação e inutilização de NF-e via SEFAZ.

## Architecture

- `nfe_sync/` — pacote Python (biblioteca)
  - `models.py` — modelos Pydantic: Certificado, Endereco, Emitente, EmpresaConfig
  - `config.py` — lê `.certs.ini` → modelos Pydantic
  - `state.py` — lê/escreve `.state.json` (numeração por cnpj:serie, cooldown por cnpj)
  - `exceptions.py` — NfeConfigError, NfeValidationError
  - `emissao.py`, `consulta.py`, `manifestacao.py`, `inutilizacao.py` — operações NF-e
  - `cli.py` — CLI com subcomandos via argparse
- Config imutável: `.certs.ini` (dados da empresa/certificado)
- Estado mutável: `.state.json` (numeração NF, cooldowns)

## Commands

```bash
pyenv activate nfe-sync-314
pip install -e ".[dev]"
pytest tests/ -v
```

## CLI Usage

```bash
nfe-sync emitir <empresa> --serie 1
nfe-sync consultar <empresa> <chave>
nfe-sync manifestar <empresa> <operacao> <chave> [--justificativa "..."]
nfe-sync inutilizar <empresa> --serie 1 --inicio 5 --fim 8 --justificativa "..."
```
