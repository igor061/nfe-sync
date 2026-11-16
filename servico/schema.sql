-- Schema das NF-e recebidas via distribuicao DFe (nfe-sync). Idempotente.
create schema if not exists nfe;

create table if not exists nfe.documentos (
    cnpj_interessado  char(14)    not null,
    chave             char(44)    not null,
    tipo              text        not null check (tipo in ('completa', 'resumo')),
    emitente_cnpj     text,
    emitente_nome     text,
    destinatario_cnpj text,
    numero            bigint,
    serie             int,
    emitida_em        timestamptz,
    valor_total       numeric(15, 2),
    cstat             text,
    protocolo         text,
    arquivo           text        not null,
    xml               text        not null,
    atualizado_em     timestamptz not null default now(),
    primary key (cnpj_interessado, chave)
);

create table if not exists nfe.eventos (
    cnpj_interessado char(14)    not null,
    arquivo          text        not null,
    chave            char(44)    not null,
    tp_evento        text,
    seq              int,
    descricao        text,
    ocorrido_em      timestamptz,
    cstat            text,
    xml              text        not null,
    atualizado_em    timestamptz not null default now(),
    primary key (cnpj_interessado, arquivo)
);
create index if not exists eventos_chave_idx on nfe.eventos (chave);
