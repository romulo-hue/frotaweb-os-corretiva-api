import unittest

from frotaweb.forms import parse_forms


class FormParserTest(unittest.TestCase):
    def test_parse_inputs_select_and_textarea(self):
        html = """
        <form name="frm" id="frm" action="TL.asp" method="post">
          <input type="hidden" name="hidacao" value="gravar">
          <input type="text" name="txtcd_veiculo" value="123">
          <select name="cmbtipo">
            <option value="A">A</option>
            <option value="B" selected>B</option>
          </select>
          <textarea name="obs">texto</textarea>
          <input type="button" name="btn" value="Salvar">
        </form>
        """
        forms = parse_forms(html)
        self.assertEqual(len(forms), 1)
        self.assertEqual(forms[0].action, "TL.asp")
        self.assertEqual(forms[0].method, "post")
        self.assertEqual(
            forms[0].fields,
            {
                "hidacao": "gravar",
                "txtcd_veiculo": "123",
                "cmbtipo": "B",
                "obs": "texto",
            },
        )

    def test_unchecked_checkbox_is_not_in_default_fields(self):
        html = """
        <form>
          <input type="checkbox" name="unchecked" value="1">
          <input type="checkbox" name="checked" value="1" checked>
        </form>
        """
        forms = parse_forms(html)
        self.assertEqual(forms[0].fields, {"checked": "1"})


if __name__ == "__main__":
    unittest.main()
