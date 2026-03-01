# Changelog

## 0.2.57
- fix: #20 — aceitar --producao/--homologacao antes ou depois do subcomando

## 0.2.56
- fix: #22 — exit code 1 para status de erro SEFAZ em cmd_consultar e cmd_consultar_nsu

## 0.2.55
- fix: #21 — validar chave de acesso localmente antes de enviar a SEFAZ

## 0.2.54
- fix: #23 — usar safe_fromstring em _salvar_log_xml (XXE)

## 0.2.53
- fix: resolver issues #16-#19 — XXE em emissao/manifestacao/inutilizacao, timezone BRT compartilhado, timeout SEFAZ via monkey-patch, dedup cmd_consultar_nsu

## 0.2.52
- fix: remover dependencia de packaging — usar ver_tuple interno

## 0.2.51
- fix: resolver issues #1-#15 — seguranca, validacao, resiliencia e logging

## 0.2.50
- docs: atualizar readme com instrucoes de hook e scripts/commit.sh

## 0.2.49
- chore: bloquear git commit direto — obrigar uso de scripts/commit.sh

## 0.2.48
- chore: adiciona scripts/commit.sh para commit manual sem dependencia do pre-commit hook\012\012Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>

## 0.2.47
- fix: adicionar modificacoes em emissao, inutilizacao e manifestacao (uso de xml_utils)\012\012Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>

## 0.2.46
- fix: adicionar xml_utils.py ao git (esquecido no commit de criacao)\012\012Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>

## 0.2.45
- fix: pular distribuicao DFe quando chave pertence ao proprio CNPJ da empresa\012\012Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>

## 0.2.44
- fix: aplicar cooldown apenas para status 137 (fila esgotada)\012\012Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>

## 0.2.43
- fix: aplicar cooldown apos qualquer consulta NSU, incluindo 137 (fila esgotada)\012\012Antes o cooldown so era setado para status de erro (nao 137/138).\012Agora e sempre aplicado, evitando rejeicao 656 por consumo indevido\012quando a fila esta vazia e o processo chama novamente em seguida.\012\012Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>

## 0.2.42
- fix: remover resNFe do disco quando ciencia e rejeitada por NF-e cancelada (cStat=650)\012\012Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>

## 0.2.41
- fix: adicionar arquivos commands/__init__, consulta e sistema ao git (esquecidos no commit anterior)\012\012Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>

## 0.2.40
- fix: incluir nfe_sync.commands no build (subpacote nao estava sendo empacotado)\012\012Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>

## 0.2.39
- docs: adiciona secao API Python com exemplos de consultar, consultar_dfe_chave e consultar_nsu\012\012Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>

## 0.2.38
- refactor: desacoplagem completa com blueprint pattern no CLI\012\012- Cria commands/manifestacao.py (ManifestacaoBlueprint)\012- Cria commands/inutilizacao.py (InutilizacaoBlueprint)\012- Cria commands/emissao.py (EmissaoBlueprint) — corrige bug: subparser emitir estava ausente no cli.py anterior\012- Reescreve cli.py (~80 linhas) como entry point fino que instancia e registra os blueprints\012\012Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>

## 0.2.37
- feat: valida CNPJ no inicio de cada chamada SEFAZ\012\012Adiciona validar_cnpj_sefaz() chamada em consultar, consultar_nsu,\012consultar_dfe_chave, manifestar, inutilizar e emitir antes de qualquer\012requisicao de rede. Lanca NfeValidationError com mensagem clara se o\012CNPJ nao tiver exatamente 14 digitos numericos.\012\012Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>

## 0.2.36
- fix: valida CNPJ ao carregar config (14 digitos, strip de formatacao)\012\012Previne cStat=215 do SEFAZ causado por CNPJ com numero errado de digitos\012no config. Aceita CNPJs formatados (10.755.237/0001-36) e converte para\012somente digitos. Erro claro na inicializacao em vez de rejeicao do SEFAZ.\012\012Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>

## 0.2.35
- refactor: separa biblioteca da CLI — funções retornam XML em memória\012\012- consulta, manifestacao, inutilizacao, emissao: removidos import os,\012  salvar_resposta_sefaz e toda escrita em disco\012- Funções retornam xml/xml_resposta como strings prontas para persistir\012- consultar_nsu: state_file=None (opcional), retorna estado atualizado\012  e xmls_resposta; salva estado somente se state_file for fornecido\012- cli.py: helpers _salvar_xml, _salvar_log_xml, _listar_resumos_pendentes,\012  _tratar_arquivo_cancelado centralizam todo I/O de arquivo\012- __init__.py: expõe API pública (consultar, consultar_nsu, manifestar, etc.)\012- Comportamento da CLI idêntico ao anterior (67 testes passando)\012\012Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>

## 0.2.34
- consultar: tentar baixar XML completo via DFe apos consulta de situacao\012\012Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>

## 0.2.33
- consultar-nsu --chave: usar UF do emitente (da chave) como cUFAutor\012\012Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>

## 0.2.32
- install-hooks: usar link simbolico em vez de copia\012\012Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>

## 0.2.31
- adicionar scripts/hooks/pre-commit e install-hooks.sh para versionamento automatico\012\012Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>

## 0.2.30
- readme: explicar tipos de documento DFe e evento de ciencia do emitente\012\012Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>

## 0.2.29
- pendentes: empresa opcional, sem argumento consulta todas as empresas\012\012Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>

## 0.2.28
- separar help em grupos: Comandos SEFAZ e Sistema\012\012Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>

## 0.2.27
- cancelamento 653: renomear procNFe para -cancelada.xml e salvar -cancelamento.xml\012\012Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>

## 0.2.26
- salvar registro de cancelamento (653) e remover resNFe pendente\012\012Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>

## 0.2.25
- consultar-nsu --chave: baixar procNFe diretamente pela chave sem avançar NSU\012\012Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>

## 0.2.24
- consultar: usar UF da chave para conectar ao servidor correto da SEFAZ\012\012Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>

## 0.2.23
- adicionar subcomando pendentes para listar resNFe aguardando XML completo\012\012Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>

## 0.2.22
- fluxo automatico resNFe: listar pendentes, manifestar ciencia e baixar procNFe\012\012Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>

## 0.2.21
- corrigir cooldown: ativar apenas em erros, nao em fim normal da fila (137)

## 0.2.20
- explicar fluxo para download do XML completo apos consultar e consultar-nsu

## 0.2.19
- confirmar estabilidade do hook de versao

## 0.2.18
- corrigir hook: ler mensagem via ps para garantir versao unica por commit

## 0.2.17
- bump versao para garantir atualizacao do fix de nao salvar XML em erros

## 0.2.16
- nao salvar XML em downloads quando SEFAZ retornar erro ou rejeicao

## 0.2.15
- corrigir leitura de comentarios inline no ini e adicionar signxml as dependencias

## 0.2.14
- alinhar conteudo do ini a esquerda para facilitar copia

## 0.2.13
- melhorar ajuda de configuracao: mostrar conteudo do ini e caminho do arquivo

## 0.2.12
- mostrar ajuda de configuracao quando nfe-sync.conf.ini nao for encontrado

## 0.2.11
- adicionar subcomando readme para exibir documentacao

## 0.2.10
- corrigir hook: usar post-commit com amend para mensagem correta no CHANGELOG

## 0.2.9
- corrigir entrada 0.2.8 no CHANGELOG e mover hook para commit-msg

## 0.2.8
- ajustar help com sintaxe dos comandos e mensagens em portugues

## 0.2.7
- adicionar comandos versao e atualizar, CHANGELOG automatico e novidades no check de update

## 0.2.6
- adicionar --zerar-nsu ao consultar-nsu e documentar no README

## 0.2.5
- Adicionado `--zerar-nsu` ao `consultar-nsu` para baixar NF-es dos últimos 90 dias
- Documentado comportamento de penalidade do SEFAZ ao zerar NSU

## 0.2.4
- Logs antigos (mais de 7 dias) são apagados automaticamente
- Lógica de nomenclatura de arquivos NSU extraída para `nome_arquivo_nsu()`
- Script `utils/renomear_nsu.py` para renomear arquivos já baixados
- Mapeamento de tipos de evento no nome do arquivo (cancelamento, carta-correção, etc.)
- Número de sequência do evento incluído no nome do arquivo

## 0.2.3
- Eventos de manifestação salvos em `downloads/{cnpj}/{chave}-evento-{operacao}.xml`

## 0.2.2
- Descrição do README melhorada

## 0.2.1
- Corrigido hook de versão para incrementar patch em vez de minor

## 0.2.0
- Hook de pre-commit para incremento automático de versão

## 0.1.0 — versão inicial
- Consulta de NF-e por chave
- Consulta de distribuição DFe por NSU com loop automático
- Manifestação de destinatário (ciência, confirmação, desconhecimento, não realizada)
- Inutilização de numeração
- Downloads organizados em `downloads/{cnpj}/`
- Respostas SEFAZ salvas em `log/` com timestamp
- CLI `api_cli` para consulta de CNPJ via CNPJá e publica.cnpj.ws
- `api_cli cnpjws --salvar-ini` para criar/atualizar entrada no nfe-sync.conf.ini
- Configuração simplificada: apenas cnpj, path, senha, uf e homologacao obrigatórios
- Scripts `run_nfesync` e `run_api_cli` para uso em desenvolvimento
