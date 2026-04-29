from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from frotaweb import FrotaWebClient
from scripts._env import load_dotenv, require_env


def main() -> int:
    load_dotenv()
    client = FrotaWebClient(require_env("FROTAWEB_BASE_URL"))
    result = client.login(
        empresa=require_env("FROTAWEB_EMPRESA"),
        usuario=require_env("FROTAWEB_USUARIO"),
        senha=require_env("FROTAWEB_SENHA"),
        filial=os_env("FROTAWEB_FILIAL", "0"),
    )
    print(
        json.dumps(
            {
                "logged_in": result.logged_in,
                "message": result.message,
                "response_url": result.response.url,
                "cookies": [cookie.name for cookie in client.cookies],
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0 if result.logged_in else 2


def os_env(name: str, default: str) -> str:
    import os

    return os.environ.get(name, default)


if __name__ == "__main__":
    raise SystemExit(main())
