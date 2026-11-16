#!/usr/bin/env bash
# E2E de aceitacao do servico nfe-sync-drocer no hg003 (PRODUCAO). SOMENTE LEITURA.
# Nao roda o servico, nao chama SEFAZ/Infisical, nao escreve no banco/host, nao imprime segredos.
# Uso: bash verificar_servico_hg003.sh [host-ssh]   (default hg003-agent). Sai 1 se algum AC falhar.
H="${1:-hg003-agent}"; CNPJ=05381344000101
D=/opt/porv/nfe-sync/data/downloads/$CNPJ
r() { ssh -o BatchMode=yes "$H" "$@"; }
q() { r "docker exec supabase-db psql -U supabase_admin -d postgres -Atc \"$1\""; }
FAIL=0
ck() { if [ "$2" = "$3" ]; then echo "PASS $1 ($2)"; else echo "FAIL $1: obtido='$2' esperado='$3'"; FAIL=1; fi; }

echo "== Ambiente"; r 'hostname; date'
q "select coalesce(inet_server_addr()::text,'socket-unix'), current_database()"
ck host "$(r hostname)" hg003

echo "== AC1 rodada consultou SEFAZ, sem ciencia, success"
ck result "$(r 'systemctl show nfe-sync-drocer.service -p Result --value')" success
ck exit "$(r 'systemctl show nfe-sync-drocer.service -p ExecMainStatus --value')" 0
J=$(r 'sudo journalctl -u nfe-sync-drocer.service --no-pager -o cat')
ck consultou_sefaz "$(grep -c 'Consultando distribuicao DFe' <<<"$J" | sed 's/^0$/0/;s/^[1-9].*/>=1/')" '>=1'
ck sem_log_manifestacao "$(grep -ciE 'ciencia registrada|manifestacao (registrada|enviada)|evento 210210' <<<"$J")" 0
ck sem_xml_ciencia "$(r "sudo find $D -iname '*evento-ciencia*.xml' | wc -l")" 0

echo "== AC2 arquivos x banco"
NF=$(r "sudo ls $D | wc -l"); ND=$(q "select (select count(*) from nfe.documentos)+(select count(*) from nfe.eventos)")
ck total_arquivos_vs_banco "$NF" "$ND"
ck docs_completa "$(r "sudo sh -c \"grep -l '<nfeProc' $D/*.xml\" | grep -vc evento")" "$(q "select count(*) from nfe.documentos where tipo='completa'")"
ck docs_resumo "$(r "sudo sh -c \"grep -l '<resNFe' $D/*.xml\" | grep -vc evento")" "$(q "select count(*) from nfe.documentos where tipo='resumo'")"
ck eventos "$(r "sudo ls $D | grep -c evento")" "$(q "select count(*) from nfe.eventos")"
ck arquivo_sem_linha "$(comm -23 <(r "sudo ls $D" | sort) <(q "select arquivo from nfe.documentos union all select arquivo from nfe.eventos" | sort) | wc -l)" 0
echo "-- amostra: campos do XML x linha"
for k in nfeProc resNFe; do
  f=$(r "sudo sh -c \"grep -l '<$k' $D/*.xml\" | grep -v evento | head -1 | xargs -r basename")
  echo "$k $f"
  r "sudo grep -oE '<(chNFe|vNF|dhEmi)>[^<]*' $D/$f | sort -u | head -3; sudo grep -oE '<emit>.{0,200}' $D/$f | head -c 120; echo"
  q "select chave,tipo,emitente_cnpj,valor_total,emitida_em from nfe.documentos where arquivo='$f'"
done

echo "== AC3 segredos"
ck env_modo "$(r 'sudo stat -c %a /opt/porv/nfe-sync/servico.env')" 600
ck pfx_no_host "$(r "sudo find /opt/porv /tmp /var/tmp /dev/shm /home \( -name '*.pfx' -o -name '*.p12' \) -not -path '*/node_modules/*' 2>/dev/null | wc -l")" 0
ck ini_em_data "$(r "sudo find /opt/porv/nfe-sync/data -name '*.ini' | wc -l")" 0
r "sudo sed 's/=.*//' /opt/porv/nfe-sync/servico.env" | tr '\n' ' '; echo

echo "== AC4 timer"
ck timer_enabled "$(r 'systemctl is-enabled nfe-sync-drocer.timer')" enabled
ck unit_inactive_62 "$(r "systemctl cat nfe-sync-drocer.timer | grep -c '^OnUnitInactiveSec=62min'")" 1
CD=$(r "sudo python3 -c \"import json;print(list(json.load(open('/opt/porv/nfe-sync/data/.state.json'))['cooldown'].values())[0])\"")
NX=$(r "systemctl list-timers nfe-sync-drocer.timer --no-pager | awk 'NR==2{print \$2\" \"\$3\" \"\$4}'")
echo "cooldown=$CD proximo=$NX"
[ "$(date -d "$NX" +%s)" -gt "$(date -d "$CD" +%s)" ] && echo "PASS proximo_apos_cooldown" || { echo "FAIL proximo_apos_cooldown"; FAIL=1; }

echo "== AC5 role nfe_sync"
ck flags "$(q "select concat(rolsuper::int,rolcreatedb::int,rolcreaterole::int,rolreplication::int,rolbypassrls::int) from pg_roles where rolname='nfe_sync'")" "00000"
ck dono_schema "$(q "select pg_get_userbyid(nspowner) from pg_namespace where nspname='nfe'")" nfe_sync
ck grants_diretos_fora_nfe "$(q "select count(*) from information_schema.role_table_grants where grantee='nfe_sync' and table_schema<>'nfe'")" 0
ck create_fora_nfe "$(q "select count(*) from pg_namespace where nspname<>'nfe' and has_schema_privilege('nfe_sync',oid,'CREATE')")" 0
ck tabelas_public_legiveis "$(q "select count(*) from pg_class c where relnamespace='public'::regnamespace and relkind in ('r','v') and has_table_privilege('nfe_sync',c.oid,'SELECT')")" 0
ck membro_de_roles "$(q "select count(*) from pg_auth_members m join pg_roles u on u.oid=m.member where u.rolname='nfe_sync'")" 0
ck createdb_banco "$(q "select has_database_privilege('nfe_sync','postgres','CREATE')")" f
exit $FAIL
