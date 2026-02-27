# nfe-sync

Integração direta com a SEFAZ via linha de comando. Com o nfe-sync você consulta NF-e recebidas, manifesta documentos fiscais, inutiliza numerações e pesquisa dados de CNPJ — tudo sem depender de plataformas intermediárias, pagando apenas pelo certificado digital que você já tem.

Ideal para empresas que querem automatizar o fluxo fiscal sem depender de ERP ou plataformas de terceiros.

## Instalação

### Pacote instalado via pip

```bash
pip install git+https://github.com/igor061/nfe-sync.git
```

Para atualizar:

```bash
pip install --upgrade git+https://github.com/igor061/nfe-sync.git
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

Cada seção do arquivo representa uma empresa. Apenas 5 campos são obrigatórios:

```ini
[MINHAEMPRESA]
path = certs/certificado.pfx   # caminho do certificado A1
senha = senha_do_certificado   # senha do certificado
uf = sp                        # UF da empresa
homologacao = true             # true = testes, false = producao
cnpj = 00000000000191          # CNPJ somente numeros
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

# Zera o NSU e recomeça do início (busca NF-es dos últimos 90 dias)
nfe-sync consultar-nsu MINHAEMPRESA --zerar-nsu
```

> **`--zerar-nsu`:** permite baixar todas as NF-es dos últimos 90 dias disponíveis no SEFAZ, útil na primeira execução ou para reprocessar o histórico. O SEFAZ pode retornar erro 656 (uso indevido) na primeira tentativa, bloqueando as consultas por 1 a 4 horas. Após o bloqueio expirar, as consultas voltam a funcionar normalmente e todos os documentos disponíveis serão baixados.

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
