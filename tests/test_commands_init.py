"""Testes para commands/__init__.py — Issue #23: XXE em _salvar_log_xml."""
from unittest.mock import patch, MagicMock

import nfe_sync.commands as cmds_mod


class TestSalvarLogXmlSeguro:
    """Issue #23: _salvar_log_xml deve usar safe_fromstring, não etree.fromstring."""

    XML_SIMPLES = '<?xml version="1.0"?><retConsSitNFe><cStat>100</cStat></retConsSitNFe>'

    def test_usa_safe_fromstring_nao_etree(self):
        """Garantia: safe_fromstring é chamado (sem vulnerabilidade XXE)."""
        with patch.object(cmds_mod, "safe_fromstring") as mock_safe, \
             patch("nfe_sync.commands.salvar_resposta_sefaz", return_value="log/x.xml") as mock_salvar:
            mock_safe.return_value = MagicMock()
            cmds_mod._salvar_log_xml(self.XML_SIMPLES, "consulta", "chave123")

        mock_safe.assert_called_once()
        args = mock_safe.call_args[0]
        assert args[0] == self.XML_SIMPLES.encode()

    def test_nao_usa_etree_fromstring(self):
        """Garantia: etree.fromstring NÃO é chamado (removido do módulo)."""
        from pynfe.utils import etree
        with patch.object(etree, "fromstring") as mock_etree, \
             patch.object(cmds_mod, "safe_fromstring", return_value=MagicMock()), \
             patch("nfe_sync.commands.salvar_resposta_sefaz", return_value="log/x.xml"):
            cmds_mod._salvar_log_xml(self.XML_SIMPLES, "consulta", "chave123")

        mock_etree.assert_not_called()
