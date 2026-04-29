import unittest

from frotaweb.client import extract_alerts, FrotaWebClient


class ClientTest(unittest.TestCase):
    def test_url_join(self):
        client = FrotaWebClient("http://3.19.17.18//")
        self.assertEqual(client._url("Telas/TL10320.asp"), "http://3.19.17.18/Telas/TL10320.asp")

    def test_extract_alerts(self):
        html = "<script>alert('Erro de login'); alert(\"Outro erro\")</script>"
        self.assertEqual(extract_alerts(html), ["Erro de login", "Outro erro"])


if __name__ == "__main__":
    unittest.main()
