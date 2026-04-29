from __future__ import annotations

import argparse
import asyncio
from datetime import datetime
import json
import os
from pathlib import Path
import subprocess
import sys
import time
from typing import Any
from urllib.error import URLError
from urllib.parse import quote
from urllib.request import Request
from urllib.request import urlopen

import websockets

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from api.main import with_tl11800_defaults
from scripts._env import load_dotenv, require_env


ROOT = Path(__file__).resolve().parents[1]
ARTIFACTS = ROOT / "artifacts"
SESSION_FILE = ARTIFACTS / "cdp_tl11800_session.json"
DEFAULT_PAYLOAD = ARTIFACTS / "payload_teste_1830.json"
PORT = 9333
BASE_URL = "http://3.19.17.18/"
CHROME_PATHS = [
    Path(r"C:\Program Files\Google\Chrome\Application\chrome.exe"),
    Path(r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe"),
    Path(os.environ.get("LOCALAPPDATA", "")) / "Google/Chrome/Application/chrome.exe",
]


class CDP:
    def __init__(self, ws):
        self.ws = ws
        self.next_id = 1
        self.pending: dict[int, asyncio.Future] = {}
        self.events: list[dict[str, Any]] = []
        self.network: dict[str, dict[str, Any]] = {}

    async def start(self):
        self.reader_task = asyncio.create_task(self._reader())

    async def _reader(self):
        async for raw in self.ws:
            msg = json.loads(raw)
            if "id" in msg:
                fut = self.pending.pop(msg["id"], None)
                if fut and not fut.done():
                    fut.set_result(msg)
            else:
                self.events.append(msg)
                self._capture_network(msg)

    def _capture_network(self, msg: dict[str, Any]) -> None:
        method = msg.get("method")
        params = msg.get("params", {})
        request_id = params.get("requestId")
        if not request_id:
            return

        entry = self.network.setdefault(request_id, {"requestId": request_id})
        if method == "Network.requestWillBeSent":
            req = params.get("request", {})
            entry["request"] = {
                "method": req.get("method"),
                "url": req.get("url"),
                "headers": sanitize_headers(req.get("headers", {})),
                "postData": sanitize_post_data(req.get("postData", "")),
            }
            entry["timestamp"] = params.get("timestamp")
            entry["type"] = params.get("type")
        elif method == "Network.responseReceived":
            resp = params.get("response", {})
            entry["response"] = {
                "status": resp.get("status"),
                "statusText": resp.get("statusText"),
                "url": resp.get("url"),
                "headers": sanitize_headers(resp.get("headers", {})),
                "mimeType": resp.get("mimeType"),
            }
        elif method == "Network.loadingFailed":
            entry["failure"] = {
                "errorText": params.get("errorText"),
                "canceled": params.get("canceled"),
            }

    async def send(self, method: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        msg_id = self.next_id
        self.next_id += 1
        fut = asyncio.get_running_loop().create_future()
        self.pending[msg_id] = fut
        await self.ws.send(json.dumps({"id": msg_id, "method": method, "params": params or {}}))
        response = await asyncio.wait_for(fut, timeout=30)
        if "error" in response:
            raise RuntimeError(f"CDP error {method}: {response['error']}")
        return response.get("result", {})

    async def eval(self, expression: str, await_promise: bool = True) -> Any:
        result = await self.send(
            "Runtime.evaluate",
            {
                "expression": expression,
                "awaitPromise": await_promise,
                "returnByValue": True,
            },
        )
        remote = result.get("result", {})
        if "exceptionDetails" in result:
            raise RuntimeError(json.dumps(result["exceptionDetails"], ensure_ascii=False))
        return remote.get("value")


async def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--payload", default=str(DEFAULT_PAYLOAD))
    parser.add_argument("--submit", action="store_true", help="Executa o clique final Salvar.")
    args = parser.parse_args()

    ARTIFACTS.mkdir(exist_ok=True)
    load_dotenv(ROOT / ".env")
    payload = with_tl11800_defaults(json.loads(Path(args.payload).read_text(encoding="utf-8-sig")))

    if args.submit:
        return await submit_existing(payload)
    return await prepare_until_save(payload)


async def prepare_until_save(payload: dict[str, Any]) -> int:
    proc = launch_chrome()
    wait_for_page_ws()
    ws_url = open_new_page_ws()

    async with websockets.connect(ws_url, max_size=None) as ws:
        cdp = CDP(ws)
        await cdp.start()
        await cdp.send("Page.enable")
        await cdp.send("Runtime.enable")

        await cdp.send("Page.navigate", {"url": BASE_URL + "default.asp"})
        await asyncio.sleep(2)
        await login(cdp)
        await asyncio.sleep(2)
        logged = await cdp.eval("fetch('/verificaSessao.asp', {credentials:'include'}).then(r => r.text())")
        if str(logged).strip() != "1":
            raise RuntimeError("Login nao confirmado pelo FrotaWeb.")

        # Capture only after login so the HAR does not contain credentials.
        await cdp.send("Network.enable")
        await cdp.send("Page.navigate", {"url": BASE_URL + "Telas/TL11800.asp"})
        await wait_for_form(cdp, "frmtl11800")

        await submit_form(cdp, "frmtl11800", {"hidstatusreg": "4"}, None)
        await wait_for_form(cdp, "frmtl11800")

        await submit_form(
            cdp,
            "frmtl11800",
            {"txtcd_veiculo": payload["vehicle_code"]},
            "tl11800.asp?acao=cd_veiculo",
        )
        await wait_for_form(cdp, "frmtl11800")

        await submit_form(
            cdp,
            "frmtl11800",
            {
                "txtdh_entrada": payload["opening_datetime"],
                "txtqt_hr_ent": payload["entry_hourmeter"],
                "txtqt_km_ent": payload["odometer"],
            },
            "tl11800.asp?acao=dh_entrada",
        )
        await wait_for_form(cdp, "frmtl11800")

        await submit_form(
            cdp,
            "frmtl11800",
            {
                "txtdh_saida": payload["exit_datetime"],
                "txtqt_hr_sai": payload["exit_hourmeter"],
                "txtqt_km_sai": payload["exit_odometer"],
            },
            "tl11800.asp?acao=dh_saida",
        )
        await wait_for_form(cdp, "frmtl11800")

        await fill_final_fields(cdp, payload)
        fields = await form_fields(cdp, "frmtl11800")
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        har_path = ARTIFACTS / f"tl11800_prepare_{stamp}.har.json"
        fields_path = ARTIFACTS / f"tl11800_prepare_fields_{stamp}.json"
        html_path = ARTIFACTS / f"tl11800_prepare_{stamp}.html"
        save_har(cdp.network, har_path)
        fields_path.write_text(json.dumps(fields, ensure_ascii=False, indent=2), encoding="utf-8")
        html_path.write_text(await page_html(cdp), encoding="utf-8")

        SESSION_FILE.write_text(
            json.dumps(
                {
                    "pid": proc.pid,
                    "port": PORT,
                    "payload": str(Path(DEFAULT_PAYLOAD).resolve()),
                    "har": str(har_path.resolve()),
                    "fields": str(fields_path.resolve()),
                    "html": str(html_path.resolve()),
                    "created_at": datetime.now().isoformat(),
                },
                indent=2,
            ),
            encoding="utf-8",
        )

        print(
            json.dumps(
                {
                    "ready_to_save": True,
                    "chrome_pid": proc.pid,
                    "har": str(har_path.resolve()),
                    "fields": str(fields_path.resolve()),
                    "html": str(html_path.resolve()),
                    "session": str(SESSION_FILE.resolve()),
                    "important_fields": pick_fields(fields),
                },
                ensure_ascii=False,
                indent=2,
            )
        )
    return 0


async def submit_existing(payload: dict[str, Any]) -> int:
    if not SESSION_FILE.exists():
        raise RuntimeError("Sessao CDP nao encontrada. Execute prepare primeiro.")
    session = json.loads(SESSION_FILE.read_text(encoding="utf-8"))
    ws_url = wait_for_page_ws(int(session["port"]))
    async with websockets.connect(ws_url, max_size=None) as ws:
        cdp = CDP(ws)
        await cdp.start()
        await cdp.send("Page.enable")
        await cdp.send("Runtime.enable")
        await cdp.send("Network.enable")
        await fill_final_fields(cdp, payload)
        await cdp.eval("window.__beforeSave = Object.fromEntries(Array.from(document.forms.frmtl11800.elements).filter(e => e.name).map(e => [e.name, e.type === 'checkbox' ? e.checked : e.value])); salvar();")
        await asyncio.sleep(3)
        fields = await form_fields(cdp, "frmtl11800")
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        har_path = ARTIFACTS / f"tl11800_submit_{stamp}.har.json"
        html_path = ARTIFACTS / f"tl11800_submit_{stamp}.html"
        save_har(cdp.network, har_path)
        html_path.write_text(await page_html(cdp), encoding="utf-8")
        print(
            json.dumps(
                {
                    "submitted": True,
                    "har": str(har_path.resolve()),
                    "html": str(html_path.resolve()),
                    "fields_after_submit": pick_fields(fields),
                },
                ensure_ascii=False,
                indent=2,
            )
        )
    return 0


def launch_chrome() -> subprocess.Popen:
    chrome = next((path for path in CHROME_PATHS if path.exists()), None)
    if not chrome:
        raise RuntimeError("chrome.exe nao encontrado.")
    profile = ARTIFACTS / "chrome-frotaweb-cdp-profile"
    profile.mkdir(exist_ok=True)
    return subprocess.Popen(
        [
            str(chrome),
            f"--remote-debugging-port={PORT}",
            f"--user-data-dir={profile}",
            "--no-first-run",
            "--disable-popup-blocking",
            "--new-window",
            "about:blank",
        ],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )


def wait_for_page_ws(port: int = PORT) -> str:
    deadline = time.time() + 20
    while time.time() < deadline:
        try:
            with urlopen(f"http://127.0.0.1:{port}/json/list", timeout=2) as resp:
                targets = json.loads(resp.read().decode("utf-8"))
            pages = [target for target in targets if target.get("type") == "page"]
            if pages:
                tl11800_pages = [
                    page
                    for page in pages
                    if "tl11800.asp" in page.get("url", "").lower()
                ]
                return (tl11800_pages or pages)[0]["webSocketDebuggerUrl"]
        except (URLError, ConnectionError, TimeoutError):
            pass
        time.sleep(0.3)
    raise RuntimeError("Nao consegui conectar ao Chrome CDP.")


def open_new_page_ws(port: int = PORT, url: str = "about:blank") -> str:
    target = f"http://127.0.0.1:{port}/json/new?{quote(url, safe=':/')}"
    request = Request(target, method="PUT")
    with urlopen(request, timeout=5) as resp:
        page = json.loads(resp.read().decode("utf-8"))
    return page["webSocketDebuggerUrl"]


async def login(cdp: CDP) -> None:
    try:
        logged = await cdp.eval("fetch('/verificaSessao.asp', {credentials:'include'}).then(r => r.text())")
        if str(logged).strip() == "1":
            return
    except Exception:
        pass

    empresa = require_env("FROTAWEB_EMPRESA")
    usuario = require_env("FROTAWEB_USUARIO")
    filial = os.environ.get("FROTAWEB_FILIAL", "1")
    senha = require_env("FROTAWEB_SENHA")
    script = f"""
(() => {{
  const menu = window.frames['menu'];
  const form = menu.document.forms['frmtl10320'];
  form.txtcd_empresa.value = {json.dumps(empresa)};
  form.txtcd_usuario.value = {json.dumps(usuario)};
  form.txtcd_filial.value = {json.dumps(filial)};
  form.hidpwd.value = {json.dumps(senha)};
  form.pwdsenha.value = '';
  form.submit();
  return true;
}})()
"""
    await wait_for_frame_form(cdp, "menu", "frmtl10320")
    await cdp.eval(script)


async def wait_for_frame_form(cdp: CDP, frame_name: str, form_name: str) -> None:
    expr = f"""
(async () => {{
  for (let i = 0; i < 80; i++) {{
    try {{
      const frame = window.frames[{json.dumps(frame_name)}];
      if (frame && frame.document && frame.document.forms[{json.dumps(form_name)}]) return true;
    }} catch (e) {{}}
    await new Promise(r => setTimeout(r, 100));
  }}
  return false;
}})()
"""
    ok = await cdp.eval(expr)
    if not ok:
        raise RuntimeError(f"Formulario {form_name} nao encontrado no frame {frame_name}.")


async def wait_for_form(cdp: CDP, form_name: str) -> None:
    expr = f"""
(async () => {{
  for (let i = 0; i < 80; i++) {{
    if (document.forms[{json.dumps(form_name)}]) return true;
    await new Promise(r => setTimeout(r, 100));
  }}
  return false;
}})()
"""
    ok = await cdp.eval(expr)
    if not ok:
        raise RuntimeError(f"Formulario {form_name} nao encontrado.")


async def submit_form(
    cdp: CDP,
    form_name: str,
    values: dict[str, Any],
    action: str | None,
) -> None:
    script = f"""
(() => {{
  const form = document.forms[{json.dumps(form_name)}];
  const values = {json.dumps(values)};
  for (const [name, value] of Object.entries(values)) {{
    if (form.elements[name]) form.elements[name].value = value;
  }}
  if ({json.dumps(action)} !== null) form.action = {json.dumps(action)};
  form.submit();
  return true;
}})()
"""
    await cdp.eval(script)
    await asyncio.sleep(1.5)


async def fill_final_fields(cdp: CDP, payload: dict[str, Any]) -> None:
    values = {
        "txtcd_veiculo": payload["vehicle_code"],
        "txtplaca": payload.get("plate", ""),
        "txtdh_entrada": payload["opening_datetime"],
        "txtqt_hr_ent": payload["entry_hourmeter"],
        "txtqt_km_ent": payload["odometer"],
        "txtdh_saida": payload["exit_datetime"],
        "txtqt_hr_sai": payload["exit_hourmeter"],
        "txtqt_km_sai": payload["exit_odometer"],
        "txtdh_inicio": payload["start_datetime"],
        "txtdh_prev": payload["expected_release_datetime"],
        "txtqt_hr_prev": payload["expected_hours"],
        "txtqt_hr_rea": payload.get("actual_hours", "0.00"),
        "txtcd_filial": payload.get("branch_code", ""),
        "txtcd_ccusto": payload.get("department_code", ""),
        "txtnr_ocorr": payload.get("occurrence_number", "0"),
        "txtcd_moto": payload.get("driver_code", "0"),
        "txtvl_acresc": payload.get("surcharge_value", "0"),
        "txtnr_os_ret": payload.get("return_order_number", "0"),
        "txtnm_observ": payload.get("observations", ""),
        "hiddh_entrada": payload["opening_datetime"],
        "hiddh_saida": payload["exit_datetime"],
        "hiddh_entrada_old": payload["opening_datetime"],
        "hiddh_saida_old": payload["exit_datetime"],
        "hidqt_km_ent_old": payload["odometer"],
        "hidqt_km_sai_old": payload["exit_odometer"],
        "hidqt_hr_ent_old": payload["entry_hourmeter"],
        "hidqt_hr_sai_old": payload["exit_hourmeter"],
        "hidcd_filialVeic": payload.get("branch_code", ""),
        "hidcd_ccustoveic": payload.get("department_code", ""),
        "hidbl_trava_os": "1",
    }
    script = f"""
(() => {{
  const form = document.forms['frmtl11800'];
  const values = {json.dumps(values)};
  for (const [name, value] of Object.entries(values)) {{
    const field = form.elements[name];
    if (!field) continue;
    const text = value == null ? '' : String(value);
    if (field.maxLength > -1 && text.length > field.maxLength) {{
      throw new Error(`${{name}} excede maxlength ${{field.maxLength}} (${{text.length}} caracteres)`);
    }}
    field.value = text;
  }}
  return Object.fromEntries(Array.from(form.elements).filter(e => e.name).map(e => [e.name, e.type === 'checkbox' ? e.checked : e.value]));
}})()
"""
    await cdp.eval(script)


async def form_fields(cdp: CDP, form_name: str) -> dict[str, Any]:
    script = f"""
(() => {{
  const form = document.forms[{json.dumps(form_name)}];
  if (!form) return {{}};
  return Object.fromEntries(Array.from(form.elements).filter(e => e.name).map(e => [e.name, e.type === 'checkbox' ? e.checked : e.value]));
}})()
"""
    return await cdp.eval(script)


async def page_html(cdp: CDP) -> str:
    return await cdp.eval("document.documentElement.outerHTML")


def save_har(network: dict[str, dict[str, Any]], path: Path) -> None:
    entries = []
    for entry in network.values():
        req = entry.get("request", {})
        url = req.get("url", "")
        if "3.19.17.18" not in url:
            continue
        entries.append(entry)
    path.write_text(json.dumps({"entries": entries}, ensure_ascii=False, indent=2), encoding="utf-8")


def pick_fields(fields: dict[str, Any]) -> dict[str, Any]:
    names = [
        "hidstatusreg",
        "txtnr_ordserv",
        "txtcd_veiculo",
        "txtplaca",
        "txtdh_entrada",
        "txtqt_hr_ent",
        "txtqt_km_ent",
        "txtdh_saida",
        "txtqt_hr_sai",
        "txtqt_km_sai",
        "txtdh_inicio",
        "txtdh_prev",
        "txtqt_hr_prev",
        "txtqt_hr_rea",
        "txtcd_filial",
        "txtcd_ccusto",
        "txtnr_ocorr",
        "txtcd_moto",
        "txtvl_acresc",
        "txtnr_os_ret",
        "hidcd_filialVeic",
        "hidcd_ccustoveic",
        "hidbl_trava_os",
    ]
    return {name: fields.get(name) for name in names if name in fields}


def sanitize_headers(headers: dict[str, Any]) -> dict[str, Any]:
    redacted = {}
    for key, value in headers.items():
        if key.lower() in {"cookie", "set-cookie", "authorization", "proxy-authorization"}:
            redacted[key] = "<redacted>"
        else:
            redacted[key] = value
    return redacted


def sanitize_post_data(post_data: str) -> str:
    if not post_data:
        return post_data
    return post_data.replace(require_env("FROTAWEB_SENHA"), "<redacted>")


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
