from contextlib import contextmanager
from decimal import Decimal
import re
import tempfile
import os

from pydantic import BaseModel, field_validator

from .exceptions import NfeValidationError


def _calcular_dv_cnpj(cnpj14: str) -> bool:
    """Valida os dois dígitos verificadores do CNPJ pelo algoritmo mod-11."""
    pesos1 = [5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2]
    pesos2 = [6, 5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2]

    def _dv(digitos, pesos):
        soma = sum(int(d) * p for d, p in zip(digitos, pesos))
        resto = soma % 11
        return 0 if resto < 2 else 11 - resto

    dv1 = _dv(cnpj14[:12], pesos1)
    dv2 = _dv(cnpj14[:13], pesos2)
    return int(cnpj14[12]) == dv1 and int(cnpj14[13]) == dv2


def validar_cnpj_sefaz(cnpj: str, contexto: str = "") -> None:
    """Lança NfeValidationError se o CNPJ não for válido (14 dígitos + mod-11)."""
    prefixo = f"[{contexto}] " if contexto else ""
    if len(cnpj) != 14 or not cnpj.isdigit():
        raise NfeValidationError(
            f"{prefixo}CNPJ invalido para chamada SEFAZ: '{cnpj}' "
            f"(deve ter 14 digitos numericos, tem {len(cnpj)})"
        )
    if cnpj == cnpj[0] * 14:
        raise NfeValidationError(
            f"{prefixo}CNPJ invalido para chamada SEFAZ: '{cnpj}' "
            f"(todos os digitos iguais)"
        )
    if not _calcular_dv_cnpj(cnpj):
        raise NfeValidationError(
            f"{prefixo}CNPJ invalido para chamada SEFAZ: '{cnpj}' "
            f"(digitos verificadores incorretos)"
        )


class Certificado(BaseModel):
    path: str
    senha: str
    conteudo: bytes | None = None

    @contextmanager
    def cert_path(self):
        """Context manager que resolve o path do certificado.

        Se `conteudo` estiver preenchido (certificado vindo de banco de dados),
        grava em arquivo temporário e retorna o path. O arquivo é removido ao sair.
        Se não, retorna `path` diretamente sem criar arquivo temporário.
        """
        if self.conteudo is not None:
            fd, tmp = tempfile.mkstemp(suffix=".pfx")
            try:
                os.write(fd, self.conteudo)
                os.close(fd)
                yield tmp
            finally:
                os.unlink(tmp)
        else:
            yield self.path


class Endereco(BaseModel):
    logradouro: str
    numero: str
    complemento: str = ""
    bairro: str
    municipio: str
    cod_municipio: str
    uf: str
    cep: str


class Emitente(BaseModel):
    cnpj: str
    razao_social: str = ""

    @field_validator("cnpj")
    @classmethod
    def validar_cnpj(cls, v: str) -> str:
        apenas_digitos = re.sub(r"\D", "", v)
        if len(apenas_digitos) != 14:
            raise ValueError(
                f"CNPJ deve ter 14 digitos (recebeu '{v}' → {len(apenas_digitos)} digitos apos remover formatacao)"
            )
        if apenas_digitos == apenas_digitos[0] * 14:
            raise ValueError(
                f"CNPJ invalido: todos os digitos sao iguais ('{apenas_digitos}')"
            )
        if not _calcular_dv_cnpj(apenas_digitos):
            raise ValueError(
                f"CNPJ invalido: digitos verificadores incorretos ('{apenas_digitos}')"
            )
        return apenas_digitos
    nome_fantasia: str = ""
    inscricao_estadual: str = ""
    cnae_fiscal: str = ""
    regime_tributario: str = ""
    endereco: Endereco | None = None


class EmpresaConfig(BaseModel):
    nome: str
    certificado: Certificado
    emitente: Emitente
    uf: str
    homologacao: bool


class Destinatario(BaseModel):
    razao_social: str
    tipo_documento: str = "CNPJ"
    numero_documento: str
    indicador_ie: int = 9
    inscricao_estadual: str = ""
    email: str = ""
    endereco: Endereco


class Produto(BaseModel):
    codigo: str
    descricao: str
    ncm: str
    cfop: str
    unidade_comercial: str = "UN"
    quantidade_comercial: Decimal
    valor_unitario_comercial: Decimal
    unidade_tributavel: str = "UN"
    quantidade_tributavel: Decimal
    valor_unitario_tributavel: Decimal
    ean: str = "SEM GTIN"
    ean_tributavel: str = "SEM GTIN"
    ind_total: int = 1
    valor_total_bruto: Decimal
    valor_tributos_aprox: str = "0.00"
    icms_modalidade: str = "102"
    icms_csosn: str = "102"
    icms_origem: int = 0
    pis_modalidade: str = "99"
    pis_valor_base_calculo: Decimal = Decimal("0.00")
    pis_aliquota_percentual: Decimal = Decimal("0.00")
    pis_aliquota_reais: Decimal = Decimal("0.00")
    pis_valor: Decimal = Decimal("0.00")
    cofins_modalidade: str = "99"
    cofins_valor_base_calculo: Decimal = Decimal("0.00")
    cofins_aliquota_percentual: Decimal = Decimal("0.00")
    cofins_aliquota_reais: Decimal = Decimal("0.00")
    cofins_valor: Decimal = Decimal("0.00")


class Pagamento(BaseModel):
    tipo: str
    valor: Decimal


class DadosEmissao(BaseModel):
    destinatario: Destinatario
    produtos: list[Produto]
    pagamentos: list[Pagamento]
    natureza_operacao: str = "VENDA DE MERCADORIA"
    forma_emissao: str = "1"
    finalidade_emissao: int = 1
    processo_emissao: int = 0
    modelo: int = 55
    tipo_documento: int = 1
    tipo_impressao_danfe: int = 1
    cliente_final: int = 1
    indicador_destino: int = 1
    indicador_presencial: int = 1
    indicador_intermediador: int = 0
    transporte_modalidade_frete: int = 9
    informacoes_complementares: str = ""
