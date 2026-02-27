# nfe-sync

Biblioteca Python e CLI para emissão, consulta, manifestação e inutilização de NF-e via SEFAZ.

## Instalação

### Pacote instalado via pip

```bash
pip install git+https://github.com/igor061/nfe-sync.git
```

Os comandos `nfe-sync` e `api_cli` ficam disponíveis diretamente no terminal:

```bash
nfe-sync --help
api_cli --help
```

### Modo desenvolvimento (clone do repositório)

```bash
git clone https://github.com/igor061/nfe-sync.git
cd nfe-sync
pip install -e ".[dev]"
```

Use os scripts na raiz do projeto, que ativam a virtualenv automaticamente:

```bash
./run_nfesync --help
./run_api_cli --help
```

## Configuração

Copie o arquivo de exemplo e preencha com os dados da sua empresa:

```bash
cp nfe-sync.conf.ini.example nfe-sync.conf.ini
```

> **Dica:** use `api_cli cnpjws <cnpj> --salvar-ini NOME` para preencher automaticamente
> os dados cadastrais da empresa no `nfe-sync.conf.ini`. Após isso, preencha manualmente
> apenas `path` (caminho do certificado .pfx) e `senha`.

Cada seção do arquivo representa uma empresa:

```ini
[MINHAEMPRESA]
path = certs/certificado.pfx
senha = senha_do_certificado
uf = sp
homologacao = true
cnpj = 00000000000191
razao_social = EMPRESA EXEMPLO LTDA
...
```

## CLI

> Em modo desenvolvimento substitua `nfe-sync` por `./run_nfesync` e `api_cli` por `./run_api_cli`.

### Consultar situação por chave

```bash
nfe-sync consultar MINHAEMPRESA 12345678901234567890123456789012345678901234
```

### Consultar documentos recebidos (distribuição DFe)

```bash
# A partir do último NSU salvo
nfe-sync consultar-nsu MINHAEMPRESA

# A partir de um NSU específico
nfe-sync consultar-nsu MINHAEMPRESA --nsu 0
```

### Manifestar destinatário

```bash
nfe-sync manifestar MINHAEMPRESA ciencia 12345678901234567890123456789012345678901234
nfe-sync manifestar MINHAEMPRESA confirmacao 12345678901234567890123456789012345678901234
nfe-sync manifestar MINHAEMPRESA desconhecimento 12345678901234567890123456789012345678901234
nfe-sync manifestar MINHAEMPRESA nao_realizada 12345678901234567890123456789012345678901234 --justificativa "Motivo com no minimo 15 caracteres"
```

### Inutilizar numeração

```bash
nfe-sync inutilizar MINHAEMPRESA --serie 1 --inicio 5 --fim 8 --justificativa "Motivo com no minimo 15 caracteres"
```

### Forçar ambiente

```bash
nfe-sync --producao consultar-nsu MINHAEMPRESA
nfe-sync --homologacao emitir MINHAEMPRESA --serie 1
```

## Saídas

| Diretório | Conteúdo |
|---|---|
| `downloads/{cnpj}/` | XMLs de NF-e recebidas e consultas por chave |
| `log/` | Respostas brutas do SEFAZ (para diagnóstico) |
| `.state.json` | Estado interno: último NSU, cooldowns, numeração |

## Consulta de CNPJ

```bash
# CNPJá — dados cadastrais, CNAE, sócios, endereço (open.cnpja.com)
api_cli cnpja 33000167000101

# Com chave da CNPJá (configure apis.json para remover limite de requisições)
cp apis.json.example apis.json
api_cli cnpja 33000167000101

# publica.cnpj.ws — inclui inscrições estaduais por UF
api_cli cnpjws 33000167000101

# Consultar e já salvar no nfe-sync.conf.ini
api_cli cnpjws 33000167000101 --salvar-ini MINHAEMPRESA
```

## Requisitos

- Python 3.12+
- Certificado digital A1 (.pfx)
