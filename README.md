# nfe-sync

Biblioteca Python e CLI para emissão, consulta, manifestação e inutilização de NF-e via SEFAZ.

## Instalação

```bash
pip install git+https://github.com/seu-usuario/nfe-sync.git
```

Ou em modo de desenvolvimento:

```bash
git clone https://github.com/seu-usuario/nfe-sync.git
cd nfe-sync
pip install -e ".[dev]"
```

## Configuração

Copie o arquivo de exemplo e preencha com os dados da sua empresa:

```bash
cp nfe-sync.conf.ini.example nfe-sync.conf.ini
```

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

### Emitir NF-e

```bash
nfe-sync emitir MINHAEMPRESA --serie 1
```

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
api cnpja 33000167000101

# Com chave da CNPJá (configure apis.json para remover limite de requisições)
cp apis.json.example apis.json
api cnpja 33000167000101

# publica.cnpj.ws — inclui inscrições estaduais por UF
api cnpjws 33000167000101
```

## Requisitos

- Python 3.12+
- Certificado digital A1 (.pfx)
