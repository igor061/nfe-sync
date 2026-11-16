# EXP-01 — Serviço nfe-sync no hg003 gravando NF-e no Postgres

**Data**: 2026-11-16 | **Branch**: `opencode/nfe-sync-servico-hg003` | **Modo**: Express

## Plano aprovado

- Rodada agendada no hg003 (produção) para a DROCER (CNPJ 05381344000101):
  certificado A1 lido do Infisical (`certificados/prod/DROCER_PFX_*`) a cada
  rodada, `nfe-sync --producao consultar-nsu DROCER` com stdin vazio (nunca
  registra ciência), upsert dos XMLs de `downloads/{cnpj}/` no Postgres.
- Banco: `supabase-db`, schema `nfe` (dono: role `nfe_sync`, sem outros
  privilégios). Tabelas `nfe.documentos` (completa/resumo) e `nfe.eventos`.
- Fora: manifestação automática, outras empresas, UI/API.
- Decisão do usuário: banco = supabase-db (o `postgres/erp` estava vazio;
  o rótulo inicial "erp (sapi)" estava errado e foi corrigido antes de agir).

## Arquivos

`servico/rodar.py`, `servico/schema.sql`, `servico/Dockerfile`,
`servico/nfe-sync-drocer.{service,timer}`, `servico/servico.env.example`,
`tests/test_servico_rodar.py`, `tests/fixtures/servico/`,
`tests/e2e/verificar_servico_hg003.sh`.

Deploy no hg003: código em `/opt/porv/nfe-sync/src`, dados em
`/opt/porv/nfe-sync/data` (`.state.json`, `downloads/`, `log/`), segredos em
`/opt/porv/nfe-sync/servico.env` (600, não versionado), imagem
`nfe-sync:hg003`, unidades em `/etc/systemd/system/`.

## Validação (fase 4)

- DEV: parse dos 101 XMLs reais → 42 completas, 1 resumo, 58 eventos, 0 ignorados.
- hg003: Infisical OK (pfx 9029 bytes); carga 101 gravados, recarga 0 (idempotente).
- Rodada automática 2026-11-16 10:00:20 em produção: cStat 137, NSU 3834/3834,
  `Banco: {documento: 43, evento: 58, gravado: 0}`, Result=success, sem ciência.
- Iteração aceita: timer em horário fixo (`*:17`) caía no cooldown de 1h que o
  nfe-sync grava após cStat 137 → trocado por `OnUnitInactiveSec` (relativo).
- Aprovado pelo usuário ("siga") após a evidência.

## Gauntlet

| Crítico | Tier | R1 | R2 |
|---|---|---|---|
| Arquitetura & Segurança | sonnet | ❌ B1: um XML ruim abortava a transação única e bloqueava todas as rodadas seguintes; traceback engolia o exit | ✅ (4 arquivos ruins + 101 reais → 101 gravados, 4 erros logados) |
| Qualidade & Testes | sonnet | ✅ 13 testes, 15 mutações vermelhas | ✅ AC4 (isolamento de erro), 7 mutações vermelhas |
| Aceitação (hg003, somente leitura) | sonnet | ✅ AC1–AC5 em produção | Cenário 0 re-executado após o deploy das correções (abaixo) |

Correções da R1 (commits `e06837b`, `be0bf22`, `6e0cc84`): transação por
arquivo; exit = rc do nfe-sync ou 1 se houve erro de arquivo; parser lxml sem
entidades/rede; segredos fora do env do nfe-sync; `%` da senha escapado;
`docker rm -f` antes/depois da rodada; XML fora de UTF-8 conta como erro.
Prova mecânica do SM: Postgres efêmero + 101 reais + truncado + resNFe sem
chave → `gravado 101, erro 2`; recarga `gravado 0`.

Achados de aceitação que não reprovam: folga do timer era 1 s sobre o
cooldown → 62 min (`d3c1450`); `/data/downloads` era `igor:igor` → root;
role `nfe_sync` herda via PUBLIC acesso ao schema `net` do Supabase
(padrão do Supabase, pré-existente).

Recusado / fora de escopo: `.dockerignore` (COPY já é específico); mensagem
limpa para erro HTTP do Infisical (falha sai com exit 1, rodada seguinte tenta
de novo).

## Pendências com dono

- Identidade Infisical própria para o serviço (hoje usa a read-only do portal
  PIX) — Igor.
- `scripts/commit.sh` usa `sed -i ''` (macOS) e falha no Linux.
- Resumo pendente `35261154597638000180550010000574021000087124` só vira
  XML completo com ciência — decisão do Igor.
- Não rodar `consultar-nsu` de produção na máquina DEV (mesma fila → risco 656).

## Iteração pós-gauntlet: várias empresas (2026-11-16)

Pedido do usuário: tirar NOG e SR JK do FSist e sincronizá-las no hg003.
Unidade virou template `nfe-sync@<INSTANCIA>.{service,timer}`, com env comum
(`servico.env`) + env por empresa (`empresas/<INSTANCIA>.env`) e estado/XMLs em
`data/<INSTANCIA>/` (rodadas não disputam o `.state.json`). `NFE_CERT` permite
à filial usar o certificado da matriz (mesma raiz de CNPJ). Instâncias:
DROCER, NOG (04064206000136), SRJK (18816825000144), SRJK2 (18816825000225,
cert SRJK). Teste novo `test_main_certificado_por_nfe_cert` (mutação: ignorar
NFE_CERT → vermelho).
