import logging
import os

from .xml_utils import safe_parse


class DocumentoStorage:
    """Centraliza todo I/O de arquivos de NF-e em downloads/{cnpj}/."""

    BASE = "downloads"

    def _pasta(self, cnpj: str) -> str:
        return f"{self.BASE}/{cnpj}"

    def salvar(self, cnpj: str, nome: str, xml: str) -> str:
        pasta = self._pasta(cnpj)
        os.makedirs(pasta, exist_ok=True)
        caminho = f"{pasta}/{nome}"
        with open(caminho, "w") as f:
            f.write(xml)
        return caminho

    def existe(self, cnpj: str, nome: str) -> bool:
        return os.path.exists(f"{self._pasta(cnpj)}/{nome}")

    def root_tag(self, cnpj: str, nome: str) -> str | None:
        try:
            tree = safe_parse(f"{self._pasta(cnpj)}/{nome}")
            tag = tree.getroot().tag
            return tag.split("}")[-1] if "}" in tag else tag
        except Exception as e:
            logging.warning("Nao foi possivel ler %s/%s: %s", cnpj, nome, e)
            return None

    def listar_resumos_pendentes(self, cnpj: str) -> list[str]:
        pasta = self._pasta(cnpj)
        if not os.path.isdir(pasta):
            return []
        resumos = []
        for nome in os.listdir(pasta):
            if not nome.endswith(".xml"):
                continue
            try:
                tag = self.root_tag(cnpj, nome)
                if tag == "resNFe":
                    resumos.append(nome[:-4])
            except Exception as e:
                logging.warning("Arquivo %s ignorado: %s", nome, e)
        return resumos

    def renomear(self, cnpj: str, origem: str, destino: str) -> str:
        pasta = self._pasta(cnpj)
        caminho_destino = f"{pasta}/{destino}"
        os.rename(f"{pasta}/{origem}", caminho_destino)
        return caminho_destino

    def remover(self, cnpj: str, nome: str) -> None:
        caminho = f"{self._pasta(cnpj)}/{nome}"
        if os.path.exists(caminho):
            os.remove(caminho)
