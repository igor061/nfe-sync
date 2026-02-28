import argparse
import os
import sys
from decimal import Decimal

from . import CliBlueprint, _carregar, _salvar_log_xml
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

    dados = DadosEmissao(
        destinatario=Destinatario(
            razao_social="NF-E EMITIDA EM AMBIENTE DE HOMOLOGACAO - SEM VALOR FISCAL",
            tipo_documento="CNPJ",
            numero_documento=emi.cnpj,
            indicador_ie=1,
            inscricao_estadual=emi.inscricao_estadual,
            endereco=Endereco(
                logradouro=end.logradouro,
                numero=end.numero,
                bairro=end.bairro,
                municipio=end.municipio,
                cod_municipio=end.cod_municipio,
                uf=end.uf,
                cep=end.cep,
            ),
        ),
        produtos=[
            Produto(
                codigo="0001",
                descricao="PRODUTO TESTE HOMOLOGACAO",
                ncm="71131100",
                cfop="5102",
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

    if resultado.get("sucesso"):
        _salvar_log_xml(resultado["xml"], "emissao", cnpj)
        os.makedirs("xml", exist_ok=True)
        arquivo = f"xml/{resultado['chave']}.xml"
        with open(arquivo, "w") as f:
            f.write(resultado["xml"])

        print(f"Status: {resultado['status']}")
        print(f"Motivo: {resultado['motivo']}")
        print(f"Protocolo: {resultado['protocolo']}")
        print(f"Chave: {resultado['chave']}")
        print(f"XML salvo em: {arquivo}")

        set_ultimo_numero_nf(estado, cnpj, serie, numero_nf)
        salvar_estado(STATE_FILE, estado)
        print(f"Numero NF {numero_nf} serie {serie} salvo em {STATE_FILE}")
    else:
        if resultado.get("xml_resposta"):
            _salvar_log_xml(resultado["xml_resposta"], "emissao-erro", cnpj)
        print("ERRO na emissao:")
        for erro in resultado.get("erros", []):
            print(f"  cStat={erro['status']}  {erro['motivo']}")
        sys.exit(1)


class EmissaoBlueprint(CliBlueprint):
    def register(self, subparsers, parser) -> None:
        p = subparsers.add_parser(
            "emitir",
            help=argparse.SUPPRESS,
            description="Emite uma NF-e de teste em homologacao na SEFAZ.",
            formatter_class=argparse.RawDescriptionHelpFormatter,
            epilog="Exemplo:\n  nfe-sync emitir MINHAEMPRESA --serie 1",
        )
        p.add_argument("empresa", help="Nome da empresa (secao no nfe-sync.conf.ini)")
        p.add_argument("--serie", required=True, help="Serie da NF-e")
        p.set_defaults(func=cmd_emitir)
