# Changelog

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
