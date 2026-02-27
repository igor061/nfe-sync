"""
Script utilitario para renomear arquivos ja baixados em downloads/nsu/
usando a mesma logica de nomenclatura do consulta.py.

Uso:
    python utils/renomear_nsu.py <empresa> [--executar]

Por padrao apenas exibe o que seria renomeado (dry-run).
Use --executar para aplicar as mudancas.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from pynfe.utils import etree
from nfe_sync.consulta import nome_arquivo_nsu
from nfe_sync.config import carregar_empresas

SRC_DIR = Path("downloads/nsu")
DEST_DIR = Path("downloads")
INI_FILE = "nfe-sync.conf.ini"

args = [a for a in sys.argv[1:] if not a.startswith("--")]
dry_run = "--executar" not in sys.argv

if not args:
    print("Uso: python utils/renomear_nsu.py <empresa> [--executar]")
    sys.exit(1)

empresas = carregar_empresas(INI_FILE)
nome_empresa = args[0]
if nome_empresa not in empresas:
    print(f"Empresa '{nome_empresa}' nao encontrada. Disponiveis: {', '.join(empresas)}")
    sys.exit(1)

cnpj = empresas[nome_empresa].emitente.cnpj


def inferir_schema(xml_doc) -> str:
    tag = xml_doc.tag if hasattr(xml_doc, "tag") else ""
    if "procEventoNFe" in tag or "retEnvEvento" in tag:
        return "procEventoNFe_v1.00.xsd"
    if "resEvento" in tag:
        return "resEvento_v1.01.xsd"
    return ""


for arquivo in sorted(SRC_DIR.glob("*.xml")):
    try:
        tree = etree.parse(str(arquivo))
        xml_doc = tree.getroot()
        schema = inferir_schema(xml_doc)
        nome, _ = nome_arquivo_nsu(xml_doc, schema, arquivo.stem)
        destino = DEST_DIR / cnpj / f"{nome}.xml"
        print(f"{arquivo.name}  →  {destino}")

        if not dry_run:
            destino.parent.mkdir(parents=True, exist_ok=True)
            arquivo.rename(destino)

    except Exception as e:
        print(f"{arquivo.name}  →  ERRO: {e}")

if dry_run:
    print("\n[dry-run] Use --executar para aplicar as mudancas.")
