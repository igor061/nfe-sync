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

-- Pedidos de ciencia da operacao feitos pela UI (ranchoapp). O servico processa os
-- 'pendente' da sua empresa no inicio de cada rodada; o XML completo chega depois
-- pela distribuicao DFe normal. Nada e manifestado sem um pedido explicito.
create table if not exists nfe.pedidos_ciencia (
    cnpj_interessado char(14)    not null,
    chave            char(44)    not null,
    solicitado_por   text        not null,
    solicitado_em    timestamptz not null default now(),
    status           text        not null default 'pendente'
                     check (status in ('pendente', 'feito', 'erro')),
    cstat            text,
    mensagem         text,
    processado_em    timestamptz,
    primary key (cnpj_interessado, chave)
);

-- Limite da busca do XML pela chave depois da ciencia (evita martelar a SEFAZ) e formato.
alter table nfe.pedidos_ciencia add column if not exists buscas int not null default 0;
alter table nfe.pedidos_ciencia add column if not exists ultima_busca_em timestamptz;
do $$ begin
    alter table nfe.pedidos_ciencia add constraint pedidos_ciencia_chave_fmt check (chave ~ '^[0-9]{44}$');
exception when duplicate_object then null; end $$;
do $$ begin
    alter table nfe.pedidos_ciencia add constraint pedidos_ciencia_cnpj_fmt check (cnpj_interessado ~ '^[0-9]{14}$');
exception when duplicate_object then null; end $$;

-- Gatilho: pedido pendente novo (ou reaberto) avisa o servico na hora (LISTEN nfe_pedidos_ciencia).
create or replace function nfe.avisar_pedido_ciencia() returns trigger language plpgsql as $$
begin
    perform pg_notify('nfe_pedidos_ciencia', new.cnpj_interessado);
    return new;
end $$;
drop trigger if exists avisar_pedido_ciencia on nfe.pedidos_ciencia;
create trigger avisar_pedido_ciencia after insert or update of status on nfe.pedidos_ciencia
    for each row when (new.status = 'pendente') execute function nfe.avisar_pedido_ciencia();
