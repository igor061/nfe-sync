# EXP-02 — Pedágio do 656: recuo de 4h, status por CNPJ e "Consultar agora"

**Data**: 2026-11-17 | **PRs**: nfe-sync #98 (`b1c4be1`), #99 (`5cc04dc`); ranchoapp #730 (`0809858e`) | **Modo**: Express

## Contexto

A NOG (04064206000136) recebia cStat 656 (Consumo Indevido) em horário
comercial mesmo depois de: o certificado do agente FSist dela ter vencido
(25/01/2026), a CORALLI/NOG ter sido removida do site FSist e 16 certificados
vencidos terem sido removidos do Windows do FSist. Conclusão: outro sistema com
o certificado atual da NOG (contador/ERP) consulta o mesmo CNPJ — fila do
NSU é única por CNPJ (NT 2014.002 §3.11.4). Zerar o NSU **não** resolve
(consulta fora de sequência também gera 656).

## Plano aprovado

1. **#98** — após 656, cooldown de 240 min (após 137 segue 61 min).
2. **#99** — `nfe.consultas_status` (última consulta por CNPJ: cStat, motivo,
   NSU, `bloqueado_ate`, `ultimo_656_em`) gravada pelo `rodar.py`; log
   `PEDÁGIO: ...` quando bloqueado por 656, `ESPERA: ...` quando por 137; a
   rodada bloqueada continua saindo com exit 1 (falha visível no systemd).
   `nfe.pedidos_consulta` + `pg_notify` → o `gatilho.py` atende "Consultar
   agora": sem `forcar` em cooldown responde `em espera até HH:MM` sem tocar a
   SEFAZ; com `forcar` remove o cooldown (log `FORÇADO`), limitado a 1 por CNPJ
   a cada 30 min.
3. **ranchoapp #730** — tela NF-e recebidas: faixa âmbar de pedágio, linha
   discreta "última consulta / próxima liberada", botão "Consultar agora"
   (confirmação para forçar em espera). Mesmo escopo de acesso da ciência.

Fora: descobrir/desligar o outro consumidor da NOG (depende do contador).

## Validação (fase 4)

- hg003: rodada NOG 13:33 com o código novo → `ESPERA: NOG próxima consulta
  liberada às 13:47`, linha em `nfe.consultas_status` gravada.
- Prints da tela servidos na WG (`10.202.0.5:8766/pedagio-nfe/`); aprovado
  pelo usuário ("siga").

## Gauntlet

| Crítico | Tier | R1 | R2/R3 |
|---|---|---|---|
| Arquitetura & Segurança | sonnet | ❌ B1 (falha ao gravar status abortava a gravação dos XMLs) | ✅ |
| Qualidade & Testes (nfe-sync) | sonnet | ❌ teste asseverava PEDÁGIO após 137 (N2) | ✅ invertido para ESPERA; 41 testes `test_pedagio.py`, mutações vermelhas |
| Qualidade & Testes (ranchoapp) | sonnet | ✅ com mutação | — |
| Aceitação E2E (ranchoapp) | sonnet | ✅ | — |

Suíte nfe-sync: 320 passed; 1 falha pré-existente
(`tests/e2e/test_validacoes.py::TestEmitirValidacao::test_empresa_inexistente_retorna_erro`).

## Deploy

Schema aplicado no `supabase-db`; grants ao role `postgres` (o ranchoapp usa):
`select` em `consultas_status`/`pedidos_consulta`, `insert (cnpj_interessado,
solicitado_por, forcar)` em `pedidos_consulta`, `usage` na sequence. Imagem
`nfe-sync:hg003` reconstruída, gatilho reiniciado. Linha da NOG semeada com o
656 das 09:47 (anterior à tabela).

## Pendências com dono

- Perguntar ao contador/ERP da NOG se consultam a distribuição DFe com o
  certificado dela — Igor.
- Janela do 429 no app conta também as recusas do próprio gatilho; alinhar com
  `not like 'consulta forçada recentemente%'` (não bloqueia).
- Usuário root vê uma faixa por empresa (aceito).

## Iteração 2026-11-20: "Consultar agora" roda a unidade agendada

Pedido do usuário: a consulta forçada deve reagendar a rodada. Antes o gatilho
rodava `rodar.py` no próprio container e o timer (`OnUnitInactiveSec`) não via;
a rodada seguinte caía na espera e falhava à toa. Agora o gatilho valida e grava
`data/<INST>/.pedido-consulta.json`; `nfe-sync-pedido@<INST>.path` dispara
`nfe-sync@<INST>.service`, que consulta, marca o pedido e apaga o arquivo.
Pedido entregue e não concluído em 20 min vira erro.

Validação (hg003): NOG 03:38 — 1 execução, pedido feito, próximo disparo
04:19 → 04:53 (NOG tem drop-in de 75 min). Cenário 0 após as correções: DROCER
07:37 — pedido feito, 07:38:30 → 08:39:46, arquivo apagado.

Gauntlet R1 (sonnet): Arquitetura ✅ (corrigidos: arquivo que não é objeto com
id; `stat` de arquivo recém-apagado). Testes ✅ — AC1–AC8 com mutação vermelha;
testes do contrato antigo invertidos; suíte 316 passed com Postgres efêmero.
Questões registradas, sem mudança: erro "rodada não concluiu" conta na janela de
30 min do forçar.
