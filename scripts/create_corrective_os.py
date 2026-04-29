from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from frotaweb import CorrectiveOrder, CorrectiveOrderService, FrotaWebClient
from scripts._env import load_dotenv, require_env


def main() -> int:
    parser = argparse.ArgumentParser(description="Cria OS corretiva no FrotaWeb.")
    parser.add_argument("--order", required=True, help="Arquivo JSON com os dados da OS.")
    parser.add_argument("--mapping", required=True, help="Arquivo JSON com o mapeamento da tela.")
    parser.add_argument("--save-response", help="Opcional: salva HTML de retorno.")
    args = parser.parse_args()

    load_dotenv()
    order = CorrectiveOrder.from_dict(load_json(args.order))
    mapping = load_json(args.mapping)

    client = FrotaWebClient(require_env("FROTAWEB_BASE_URL"))
    login = client.login(
        empresa=require_env("FROTAWEB_EMPRESA"),
        usuario=require_env("FROTAWEB_USUARIO"),
        senha=require_env("FROTAWEB_SENHA"),
        filial=os.environ.get("FROTAWEB_FILIAL", "0"),
    )
    if not login.logged_in:
        print(json.dumps({"created": False, "message": login.message}, ensure_ascii=False, indent=2))
        return 2

    service = CorrectiveOrderService(client, mapping)
    result = service.create(order)
    if args.save_response:
        Path(args.save_response).write_text(result.response.text, encoding="utf-8")

    print(
        json.dumps(
            {
                "created": result.ok,
                "message": result.message,
                "order_number": result.order_number,
                "response_url": result.response.url,
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0 if result.ok else 3


def load_json(path: str):
    return json.loads(Path(path).read_text(encoding="utf-8"))


if __name__ == "__main__":
    raise SystemExit(main())
