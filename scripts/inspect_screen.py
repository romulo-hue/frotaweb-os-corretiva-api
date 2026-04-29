from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from frotaweb import FrotaWebClient
from frotaweb.forms import parse_forms
from scripts._env import load_dotenv, require_env


def main() -> int:
    parser = argparse.ArgumentParser(description="Inspeciona forms/campos de uma tela FrotaWeb.")
    parser.add_argument("screen_path", help="Ex.: Telas/TL12345.asp")
    parser.add_argument("--save-html", help="Caminho para salvar o HTML bruto da tela.")
    args = parser.parse_args()

    load_dotenv()
    client = FrotaWebClient(require_env("FROTAWEB_BASE_URL"))
    login = client.login(
        empresa=require_env("FROTAWEB_EMPRESA"),
        usuario=require_env("FROTAWEB_USUARIO"),
        senha=require_env("FROTAWEB_SENHA"),
        filial=os.environ.get("FROTAWEB_FILIAL", "0"),
    )
    if not login.logged_in:
        print(json.dumps({"logged_in": False, "message": login.message}, ensure_ascii=False, indent=2))
        return 2

    response = client.get(args.screen_path)
    if args.save_html:
        Path(args.save_html).write_text(response.text, encoding="utf-8")

    forms = parse_forms(response.text)
    print(
        json.dumps(
            {
                "url": response.url,
                "forms": [
                    {
                        "index": index,
                        "name": form.name,
                        "id": form.form_id,
                        "method": form.method,
                        "action": form.action,
                        "fields": [
                            {
                                "name": control.name,
                                "tag": control.tag,
                                "type": control.control_type,
                                "value": control.value,
                            }
                            for control in form.controls
                        ],
                    }
                    for index, form in enumerate(forms)
                ],
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
