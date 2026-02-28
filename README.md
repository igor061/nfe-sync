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

Instale os git hooks para incremento automático de versão e CHANGELOG:

```bash
./scripts/install-hooks.sh
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

### Documentos na fila de distribuição DFe

O `consultar-nsu` retorna todos os documentos da fila do SEFAZ para o CNPJ consultado, incluindo:

- **resNFe** — resumo de NF-e recebida (emitida por terceiros para você). Requer manifestação de ciência para liberar o XML completo.
- **procNFe** — XML completo da NF-e, disponível após registrar ciência.
- **procEventoNFe** — evento vinculado a uma NF-e, como cancelamento, carta de correção ou **manifestação registrada pelo destinatário de uma NF-e emitida por você**.

> **Nota:** se aparecer um evento de ciência para uma chave cujo CNPJ do emitente é o seu próprio CNPJ, isso significa que o seu cliente (destinatário) registrou ciência na nota que você emitiu. Não há resNFe nem procNFe para baixar nesse caso — você já possui o XML por ser o emitente.

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

## API Python

O nfe-sync pode ser usado diretamente como biblioteca Python, sem passar pelo CLI. Isso é útil para integrações, automações e scripts personalizados.

### Configurando a empresa

```python
from nfe_sync import carregar_empresas, carregar_estado

empresas = carregar_empresas("nfe-sync.conf.ini")
empresa = empresas["MINHAEMPRESA"]
estado = carregar_estado(".state.json")   # {} se o arquivo não existir
```

Ou construindo o objeto manualmente:

```python
from nfe_sync import EmpresaConfig, Certificado, Emitente, Endereco

empresa = EmpresaConfig(
    nome="MINHAEMPRESA",
    uf="sp",
    homologacao=True,
    certificado=Certificado(path="certs/cert.pfx", senha="senha"),
    emitente=Emitente(
        cnpj="00000000000191",
        razao_social="Empresa Teste Ltda",
        nome_fantasia="Empresa Teste",
        inscricao_estadual="000000000",
        cnae_fiscal="6201501",
        regime_tributario="1",
        endereco=Endereco(
            logradouro="Rua Exemplo",
            numero="100",
            bairro="Centro",
            municipio="São Paulo",
            cod_municipio="3550308",
            uf="SP",
            cep="01310100",
        ),
    ),
)
```

### `consultar` — situação de uma NF-e por chave

Consulta o status de uma NF-e diretamente no webservice da SEFAZ da UF emitente.

```python
from nfe_sync import consultar

resultado = consultar(empresa, "52260200597587000168550010000019137351883177")

for sit in resultado["situacao"]:
    print(sit["status"], sit["motivo"])
# ex: 100  Autorizado o uso da NF-e

if resultado["xml"]:
    # XML da resposta de consulta (retConsSitNFe) disponível quando cStat = 1xx
    print(resultado["xml"])
```

**Retorno:**

| Chave | Tipo | Descrição |
|---|---|---|
| `situacao` | `list[dict]` | Lista com `status` (cStat) e `motivo` (xMotivo) |
| `xml` | `str \| None` | XML da resposta quando autorizada (cStat 1xx) |
| `xml_resposta` | `str` | XML bruto completo retornado pelo SEFAZ |

### `consultar_dfe_chave` — baixar XML completo por chave via DFe

Usa a API de distribuição DFe para baixar o procNFe (ou evento de cancelamento) de uma chave específica, sem avançar o NSU.

```python
from nfe_sync import consultar_dfe_chave

dfe = consultar_dfe_chave(empresa, "52260200597587000168550010000019137351883177")

print(dfe["status"], dfe["motivo"])
# 138  Documento localizado  /  137  Nenhum documento localizado  /  653  NF-e cancelada

for doc in dfe["documentos"]:
    print(doc["schema"], doc["nome"])
    # ex: procNFe_v4.00.xsd  52260200597587000168550010000019137351883177.xml
    with open(doc["nome"], "w") as f:
        f.write(doc["xml"])

if dfe["xml_cancelamento"]:
    # XML do evento de cancelamento quando cStat = 653
    print(dfe["xml_cancelamento"])
```

**Retorno:**

| Chave | Tipo | Descrição |
|---|---|---|
| `sucesso` | `bool` | `True` quando cStat = 138 (documento localizado) |
| `status` | `str` | cStat da resposta SEFAZ |
| `motivo` | `str` | xMotivo da resposta SEFAZ |
| `documentos` | `list[dict]` | Documentos encontrados (ver abaixo) |
| `xml_resposta` | `str` | XML bruto completo retornado pelo SEFAZ |
| `xml_cancelamento` | `str \| None` | XML de cancelamento quando cStat = 653 |

Cada item de `documentos`:

| Chave | Tipo | Descrição |
|---|---|---|
| `nsu` | `str` | NSU do documento |
| `chave` | `str \| None` | Chave de acesso (44 dígitos), quando disponível |
| `schema` | `str` | Nome do schema XSD (ex: `procNFe_v4.00.xsd`) |
| `nome` | `str` | Nome de arquivo sugerido (ex: `{chave}.xml`) |
| `xml` | `str` | XML descompactado do documento |
| `erro` | `str` | Presente somente em caso de erro de descompactação |

### `consultar_nsu` — distribuição DFe por NSU (paginado)

Baixa todos os documentos da fila de distribuição DFe do CNPJ a partir do último NSU salvo, paginando automaticamente até esgotar a fila.

```python
from nfe_sync import consultar_nsu, salvar_estado

STATE_FILE = ".state.json"

def progresso(pagina, total_docs, ult_nsu, max_nsu):
    print(f"Página {pagina}: {total_docs} docs até agora (NSU {ult_nsu}/{max_nsu})")

resultado = consultar_nsu(
    empresa,
    estado,
    state_file=STATE_FILE,   # salva NSU automaticamente a cada página
    nsu=None,                # None = usa o último NSU do estado; 0 = recomeça do início
    callback=progresso,      # opcional
)

if not resultado["sucesso"]:
    print("Bloqueado:", resultado["motivo"])
else:
    print(f"NSU final: {resultado['ultimo_nsu']} / {resultado['max_nsu']}")
    for doc in resultado["documentos"]:
        if "erro" in doc:
            print(f"ERRO NSU {doc['nsu']}: {doc['erro']}")
        else:
            print(doc["schema"], doc["nome"])
            with open(doc["nome"], "w") as f:
                f.write(doc["xml"])

# estado atualizado com o novo NSU (use para a próxima chamada)
estado = resultado["estado"]
salvar_estado(STATE_FILE, estado)
```

**Retorno:**

| Chave | Tipo | Descrição |
|---|---|---|
| `sucesso` | `bool` | `True` quando cStat = 137 ou 138 |
| `status` | `str` | cStat da última resposta SEFAZ |
| `motivo` | `str` | xMotivo da última resposta SEFAZ |
| `ultimo_nsu` | `int` | Último NSU processado |
| `max_nsu` | `int` | NSU máximo disponível na fila |
| `documentos` | `list[dict]` | Todos os documentos baixados (mesmo formato de `consultar_dfe_chave`) |
| `xmls_resposta` | `list[str]` | XMLs brutos de cada página retornada pelo SEFAZ |
| `estado` | `dict` | Estado atualizado com o novo NSU e eventual cooldown |

> **Cooldown:** se o SEFAZ retornar erro 656 (uso indevido), a distribuição DFe fica bloqueada por ~61 minutos. O nfe-sync registra automaticamente o tempo de bloqueio no `estado` e rejeita novas chamadas com `sucesso=False` e `motivo` indicando o horário de desbloqueio.

## Requisitos

- Python 3.12+
- Certificado digital A1 (.pfx)


