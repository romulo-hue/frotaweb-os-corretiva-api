from __future__ import annotations

import argparse
import base64
import ctypes
from ctypes import wintypes
import json
import os
from pathlib import Path
import sqlite3
import subprocess
import sys
from typing import Iterable
from urllib.request import Request, urlopen

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from frotaweb.forms import parse_forms


HOST = "3.19.17.18"
BASE_URL = f"http://{HOST}/"
PY_ENCODING = "iso-8859-1"
NODE_PATH = (
    Path.home()
    / ".cache/codex-runtimes/codex-primary-runtime/dependencies/node/bin/node.exe"
)


class DATA_BLOB(ctypes.Structure):
    _fields_ = [
        ("cbData", wintypes.DWORD),
        ("pbData", ctypes.POINTER(ctypes.c_char)),
    ]


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Usa apenas o cookie Chrome de 3.19.17.18 para baixar a TL11800 logada."
    )
    parser.add_argument(
        "--output",
        default="artifacts/tl11800.logged.html",
        help="Arquivo onde o HTML da tela sera salvo.",
    )
    args = parser.parse_args()

    user_data = Path(os.environ["LOCALAPPDATA"]) / "Google" / "Chrome" / "User Data"
    master_key = load_chrome_master_key(user_data)

    cookies = {}
    profiles_checked = []
    decrypt_errors = []
    for profile, db_path in cookie_databases(user_data):
        profiles_checked.append(profile)
        for row in query_frotaweb_cookies(db_path):
            name = row["name"]
            try:
                value = decrypt_cookie_value(row, master_key)
            except Exception as exc:  # noqa: BLE001
                decrypt_errors.append({"profile": profile, "cookie": name, "error": str(exc)})
                continue
            if value:
                cookies[name] = value

    if not cookies:
        print(
            json.dumps(
                {
                    "ok": False,
                    "message": "Nenhum cookie legivel do FrotaWeb foi encontrado no Chrome.",
                    "profiles_checked": profiles_checked,
                    "decrypt_errors": decrypt_errors,
                },
                ensure_ascii=False,
                indent=2,
            )
        )
        return 2

    session_text = fetch("verificaSessao.asp", cookies).strip()
    html = fetch("Telas/TL11800.asp", cookies)
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(html, encoding="utf-8")

    forms = parse_forms(html)
    print(
        json.dumps(
            {
                "ok": session_text == "1" and len(forms) > 0,
                "session_valid": session_text == "1",
                "cookies_used": sorted(cookies.keys()),
                "profiles_checked": profiles_checked,
                "output": str(output.resolve()),
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
                "decrypt_errors": decrypt_errors,
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0 if session_text == "1" and forms else 3


def cookie_databases(user_data: Path) -> Iterable[tuple[str, Path]]:
    for profile_dir in user_data.iterdir():
        if not profile_dir.is_dir():
            continue
        if profile_dir.name != "Default" and not profile_dir.name.startswith("Profile "):
            continue
        for rel in ("Network/Cookies", "Cookies"):
            db_path = profile_dir / rel
            if db_path.exists():
                yield profile_dir.name, db_path


def query_frotaweb_cookies(db_path: Path) -> list[dict[str, object]]:
    uri = db_path.resolve().as_uri() + "?mode=ro"
    try:
        con = sqlite3.connect(uri, uri=True)
    except sqlite3.OperationalError:
        # Some Windows SQLite builds are fussy about file:// URIs with spaces.
        con = sqlite3.connect(str(db_path))
    con.row_factory = sqlite3.Row
    try:
        rows = con.execute(
            """
            select host_key, name, value, encrypted_value, path, is_secure, expires_utc
            from cookies
            where host_key = ? or host_key = ?
            """,
            (HOST, f".{HOST}"),
        ).fetchall()
        return [dict(row) for row in rows]
    finally:
        con.close()


def load_chrome_master_key(user_data: Path) -> bytes | None:
    local_state = user_data / "Local State"
    if not local_state.exists():
        return None
    data = json.loads(local_state.read_text(encoding="utf-8"))
    encrypted_key = data.get("os_crypt", {}).get("encrypted_key")
    if not encrypted_key:
        return None
    key_blob = base64.b64decode(encrypted_key)
    if key_blob.startswith(b"DPAPI"):
        key_blob = key_blob[5:]
    return dpapi_decrypt(key_blob)


def decrypt_cookie_value(row: dict[str, object], master_key: bytes | None) -> str:
    plain_value = row.get("value")
    if plain_value:
        return str(plain_value)

    encrypted_value = row.get("encrypted_value") or b""
    if isinstance(encrypted_value, memoryview):
        encrypted_value = encrypted_value.tobytes()
    if isinstance(encrypted_value, str):
        encrypted_value = encrypted_value.encode(PY_ENCODING)

    encrypted_bytes = bytes(encrypted_value)
    if encrypted_bytes.startswith((b"v10", b"v11", b"v20")):
        if not master_key:
            raise RuntimeError("Chrome master key ausente.")
        return aes_gcm_decrypt_with_node(encrypted_bytes, master_key)

    return dpapi_decrypt(encrypted_bytes).decode("utf-8", errors="replace")


def dpapi_decrypt(encrypted: bytes) -> bytes:
    if not encrypted:
        return b""

    in_blob = DATA_BLOB(len(encrypted), ctypes.cast(ctypes.create_string_buffer(encrypted), ctypes.POINTER(ctypes.c_char)))
    out_blob = DATA_BLOB()
    if not ctypes.windll.crypt32.CryptUnprotectData(
        ctypes.byref(in_blob),
        None,
        None,
        None,
        None,
        0,
        ctypes.byref(out_blob),
    ):
        raise ctypes.WinError()
    try:
        return ctypes.string_at(out_blob.pbData, out_blob.cbData)
    finally:
        ctypes.windll.kernel32.LocalFree(out_blob.pbData)


def aes_gcm_decrypt_with_node(encrypted: bytes, master_key: bytes) -> str:
    if not NODE_PATH.exists():
        raise RuntimeError(f"Node runtime nao encontrado: {NODE_PATH}")

    nonce = encrypted[3:15]
    payload = encrypted[15:]
    ciphertext = payload[:-16]
    tag = payload[-16:]
    request = {
        "key": base64.b64encode(master_key).decode("ascii"),
        "nonce": base64.b64encode(nonce).decode("ascii"),
        "ciphertext": base64.b64encode(ciphertext).decode("ascii"),
        "tag": base64.b64encode(tag).decode("ascii"),
    }
    code = r"""
const crypto = require("crypto");
let input = "";
process.stdin.setEncoding("utf8");
process.stdin.on("data", chunk => input += chunk);
process.stdin.on("end", () => {
  const data = JSON.parse(input);
  const decipher = crypto.createDecipheriv(
    "aes-256-gcm",
    Buffer.from(data.key, "base64"),
    Buffer.from(data.nonce, "base64")
  );
  decipher.setAuthTag(Buffer.from(data.tag, "base64"));
  const out = Buffer.concat([
    decipher.update(Buffer.from(data.ciphertext, "base64")),
    decipher.final()
  ]);
  process.stdout.write(out.toString("utf8"));
});
"""
    result = subprocess.run(
        [str(NODE_PATH), "-e", code],
        input=json.dumps(request),
        text=True,
        capture_output=True,
        check=False,
    )
    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip() or "Falha no AES-GCM via Node.")
    return result.stdout


def fetch(path: str, cookies: dict[str, str]) -> str:
    cookie_header = "; ".join(f"{name}={value}" for name, value in cookies.items())
    req = Request(
        BASE_URL + path.lstrip("/"),
        headers={
            "Cookie": cookie_header,
            "User-Agent": "Mozilla/5.0 FrotaWebIntegration/0.1",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        },
    )
    with urlopen(req, timeout=30) as resp:
        raw = resp.read()
        charset = resp.headers.get_content_charset() or PY_ENCODING
        return raw.decode(charset, errors="replace")


if __name__ == "__main__":
    raise SystemExit(main())
