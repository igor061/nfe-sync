import argparse
import os
import sys
from decimal import Decimal

from . import CliBlueprint, _carregar, _salvar_log_xml, CONFIG_FILE
from ..config import carregar_empresas
from ..state import get_ultimo_numero_nf, set_ultimo_numero_nf, salvar_estado
from ..models import Destinatario, Produto, Pagamento, DadosEmissao, Endereco

STATE_FILE = ".state.json"


def cmd_emitir(args):
    empresa, estado = _carregar(args)
    cnpj = empresa.emitente.cnpj
    serie = args.serie

    ultimo = get_ultimo_numero_nf(estado, cnpj, serie)
    numero_nf = ultimo + 1

    print(f"Empresa: {empresa.nome} (CNPJ {cnpj})")
    print(f"UF: {empresa.uf.upper()}")
    print(f"Ambiente: {'Homologacao' if empresa.homologacao else 'Producao'}")
    print(f"Serie: {serie}  Numero NF: {numero_nf}")
    print()

    emi = empresa.emitente
    end = emi.endereco

    if end is None:
        print("Erro: Emitente sem endereco configurado.")
        print("Preencha os dados cadastrais com:")
        print(f"  api_cli cnpjws {emi.cnpj} --salvar-ini {empresa.nome}")
        sys.exit(1)

    # Destinatário: empresa especificada via --destinatario ou o próprio emitente
    if args.destinatario:
        todas_empresas = carregar_empresas(CONFIG_FILE)
        if args.destinatario not in todas_empresas:
            print(f"Erro: destinatario '{args.destinatario}' nao encontrado.")
            print(f"Empresas disponiveis: {', '.join(todas_empresas.keys())}")
            sys.exit(1)
        dest_emi = todas_empresas[args.destinatario].emitente
        dest_end = dest_emi.endereco
        if dest_end is None:
            print(f"Erro: Destinatario '{args.destinatario}' sem endereco configurado.")
            print(f"Preencha os dados cadastrais com:")
            print(f"  api_cli cnpjws {dest_emi.cnpj} --salvar-ini {args.destinatario}")
            sys.exit(1)
    else:
        dest_emi = emi
        dest_end = end

    # Issues #50, #51, #52: ajustar indicador_destino, indicador_ie e CFOP
    # conforme UF do destinatário vs emitente
    interestadual = dest_end.uf.upper() != end.uf.upper()
    indicador_destino = 2 if interestadual else 1
    indicador_ie = 1 if dest_emi.inscricao_estadual else 9
    cfop = "6102" if interestadual else "5102"

    dados = DadosEmissao(
        indicador_destino=indicador_destino,
        destinatario=Destinatario(
            razao_social="NF-E EMITIDA EM AMBIENTE DE HOMOLOGACAO - SEM VALOR FISCAL",
            tipo_documento="CNPJ",
            numero_documento=dest_emi.cnpj,
            indicador_ie=indicador_ie,
            inscricao_estadual=dest_emi.inscricao_estadual,
            endereco=Endereco(
                logradouro=dest_end.logradouro,
                numero=dest_end.numero,
                bairro=dest_end.bairro,
                municipio=dest_end.municipio,
                cod_municipio=dest_end.cod_municipio,
                uf=dest_end.uf,
                cep=dest_end.cep,
            ),
        ),
        produtos=[
            Produto(
                codigo="0001",
                descricao="PRODUTO TESTE HOMOLOGACAO",
                ncm="71131100",
                cfop=cfop,
                quantidade_comercial=Decimal("1.0000"),
                valor_unitario_comercial=Decimal("10.00"),
                quantidade_tributavel=Decimal("1.0000"),
                valor_unitario_tributavel=Decimal("10.00"),
                valor_total_bruto=Decimal("10.00"),
            ),
        ],
        pagamentos=[
            Pagamento(tipo="01", valor=Decimal("10.00")),
        ],
        informacoes_complementares="NF-e de teste emitida em homologacao.",
    )

    from ..emissao import emitir
    resultado = emitir(empresa, serie, numero_nf, dados)

    if resultado.sucesso:
        _salvar_log_xml(resultado.xml, "emissao", cnpj)
        os.makedirs("xml", exist_ok=True)
        arquivo = f"xml/{resultado.chave}.xml"
        with open(arquivo, "w") as f:
            f.write(resultado.xml)

        print(f"Status: {resultado.status}")
        print(f"Motivo: {resultado.motivo}")
        print(f"Protocolo: {resultado.protocolo}")
        print(f"Chave: {resultado.chave}")
        print(f"XML salvo em: {arquivo}")

        set_ultimo_numero_nf(estado, cnpj, serie, numero_nf)
        salvar_estado(STATE_FILE, estado)
        print(f"Numero NF {numero_nf} serie {serie} salvo em {STATE_FILE}")
    else:
        if resultado.xml_resposta:
            _salvar_log_xml(resultado.xml_resposta, "emissao-erro", cnpj)
        print("ERRO na emissao:")
        for erro in resultado.erros:
            print(f"  cStat={erro['status']}  {erro['motivo']}")
        sys.exit(1)


class EmissaoBlueprint(CliBlueprint):
    def register(self, subparsers, parser, amb_parent=None) -> None:
        parents = [amb_parent] if amb_parent else []
        p = subparsers.add_parser(
            "emitir",
            parents=parents,
            help=argparse.SUPPRESS,
            description="Emite uma NF-e de teste em homologacao na SEFAZ.",
            formatter_class=argparse.RawDescriptionHelpFormatter,
            epilog="Exemplo:\n  nfe-sync emitir MINHAEMPRESA --serie 1",
        )
        p.add_argument("empresa", help="Nome da empresa (secao no nfe-sync.conf.ini)")
        p.add_argument("--serie", required=True, help="Serie da NF-e")
        p.add_argument("--destinatario", default=None,
                       help="Empresa destinataria (secao no nfe-sync.conf.ini). Se omitido, usa o emitente.")
        p.set_defaults(func=cmd_emitir)
