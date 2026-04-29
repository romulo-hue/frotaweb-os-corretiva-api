from __future__ import annotations

from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import subprocess
import sys
import threading
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from frotaweb.forms import parse_forms


HOST = "127.0.0.1"
PORT = 8765


CAPTURE_JS = r"""
(function () {
  function htmlOf(doc) {
    return "<!doctype html>\n" + doc.documentElement.outerHTML;
  }

  const docs = [];

  function addWindow(label, win) {
    try {
      const doc = win.document;
      docs.push({
        label,
        url: String(win.location.href),
        title: doc.title || "",
        html: htmlOf(doc)
      });

      for (let i = 0; i < win.frames.length; i++) {
        addWindow(label + "/frame" + i, win.frames[i]);
      }
    } catch (error) {
      docs.push({ label, error: String(error) });
    }
  }

  addWindow("top", window.top);

  fetch("http://127.0.0.1:8765/capture", {
    method: "POST",
    mode: "no-cors",
    body: JSON.stringify({
      capturedAt: new Date().toISOString(),
      href: String(window.location.href),
      docs
    })
  });
})();
"""


BOOKMARKLET = (
    "javascript:(()=>{let s=document.createElement('script');"
    "s.src='http://127.0.0.1:8765/capture-frame.js?'+Date.now();"
    "document.documentElement.appendChild(s)})()"
)


class CaptureHandler(BaseHTTPRequestHandler):
    server_version = "FrotaWebCapture/0.1"

    def do_GET(self) -> None:  # noqa: N802
        if self.path.startswith("/capture-frame.js"):
            payload = CAPTURE_JS.encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/javascript; charset=utf-8")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)
            return

        self.send_response(404)
        self.end_headers()

    def do_POST(self) -> None:  # noqa: N802
        if self.path != "/capture":
            self.send_response(404)
            self.end_headers()
            return

        length = int(self.headers.get("Content-Length", "0"))
        raw = self.rfile.read(length)
        self.server.capture_body = raw.decode("utf-8", errors="replace")  # type: ignore[attr-defined]
        self.server.capture_event.set()  # type: ignore[attr-defined]

        self.send_response(204)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()

    def log_message(self, format: str, *args) -> None:  # noqa: A002
        return


def main() -> int:
    output_dir = Path("artifacts")
    output_dir.mkdir(exist_ok=True)

    server = ThreadingHTTPServer((HOST, PORT), CaptureHandler)
    server.capture_event = threading.Event()  # type: ignore[attr-defined]
    server.capture_body = ""  # type: ignore[attr-defined]

    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()

    try:
        activate_and_run_bookmarklet()
        if not server.capture_event.wait(30):  # type: ignore[attr-defined]
            print(
                json.dumps(
                    {
                        "ok": False,
                        "message": "Nao recebi HTML da aba. Confirme se a aba ativa e a TL11800 do FrotaWeb.",
                    },
                    ensure_ascii=False,
                    indent=2,
                )
            )
            return 2

        data = json.loads(server.capture_body)  # type: ignore[attr-defined]
        capture_json = output_dir / "tl11800.browser.capture.json"
        capture_json.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

        docs = data.get("docs", [])
        target = find_tl11800_doc(docs)
        if not target:
            print(
                json.dumps(
                    {
                        "ok": False,
                        "message": "Capturei a pagina, mas nao achei a frame TL11800.",
                        "capture": str(capture_json.resolve()),
                        "docs": summarize_docs(docs),
                    },
                    ensure_ascii=False,
                    indent=2,
                )
            )
            return 3

        html = target.get("html", "")
        output_html = output_dir / "tl11800.logged.html"
        output_html.write_text(html, encoding="utf-8")

        forms = parse_forms(html)
        print(
            json.dumps(
                {
                    "ok": True,
                    "target": {
                        "label": target.get("label"),
                        "url": target.get("url"),
                        "title": target.get("title"),
                    },
                    "output_html": str(output_html.resolve()),
                    "capture": str(capture_json.resolve()),
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
    finally:
        server.shutdown()


def activate_and_run_bookmarklet() -> None:
    ps_script = f"""
Add-Type -AssemblyName UIAutomationClient
Add-Type -AssemblyName System.Windows.Forms

$proc = Get-Process chrome -ErrorAction SilentlyContinue | Where-Object {{ $_.MainWindowTitle }} | Select-Object -First 1
if ($null -eq $proc) {{ throw 'Chrome nao encontrado.' }}

$ws = New-Object -ComObject WScript.Shell
$ws.AppActivate($proc.MainWindowTitle) | Out-Null
Start-Sleep -Milliseconds 500

$root = [System.Windows.Automation.AutomationElement]::FromHandle($proc.MainWindowHandle)
$tabCond = New-Object System.Windows.Automation.PropertyCondition(
  [System.Windows.Automation.AutomationElement]::ControlTypeProperty,
  [System.Windows.Automation.ControlType]::TabItem
)
$tabs = $root.FindAll([System.Windows.Automation.TreeScope]::Descendants, $tabCond)
for ($i = 0; $i -lt $tabs.Count; $i++) {{
  $tabItem = $tabs.Item($i)
  if ($tabItem.Current.Name -like 'FrotaWeb*') {{
    $selection = $tabItem.GetCurrentPattern([System.Windows.Automation.SelectionItemPattern]::Pattern)
    $selection.Select()
    break
  }}
}}

Start-Sleep -Milliseconds 600
$root = [System.Windows.Automation.AutomationElement]::FromHandle($proc.MainWindowHandle)
$editCond = New-Object System.Windows.Automation.PropertyCondition(
  [System.Windows.Automation.AutomationElement]::ControlTypeProperty,
  [System.Windows.Automation.ControlType]::Edit
)
$edits = $root.FindAll([System.Windows.Automation.TreeScope]::Descendants, $editCond)
if ($edits.Count -lt 1) {{ throw 'Barra de endereco nao encontrada.' }}
$addressBar = $edits.Item(0)
$addressBar.SetFocus()
Start-Sleep -Milliseconds 200
$value = $addressBar.GetCurrentPattern([System.Windows.Automation.ValuePattern]::Pattern)
$value.SetValue(@'
{BOOKMARKLET}
'@)
Start-Sleep -Milliseconds 200
[System.Windows.Forms.SendKeys]::SendWait('{{ENTER}}')
"""
    result = subprocess.run(
        [
            "powershell.exe",
            "-STA",
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-Command",
            ps_script,
        ],
        text=True,
        capture_output=True,
        check=False,
    )
    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip() or "Falha ao automatizar Chrome.")
    time.sleep(1)


def find_tl11800_doc(docs: list[dict]) -> dict | None:
    for doc in docs:
        url = str(doc.get("url", "")).lower()
        html = str(doc.get("html", "")).lower()
        if "tl11800" in url or "realiza" in html and "manuten" in html and "corretiva" in html:
            return doc
    return None


def summarize_docs(docs: list[dict]) -> list[dict[str, str]]:
    summary = []
    for doc in docs:
        summary.append(
            {
                "label": str(doc.get("label", "")),
                "url": str(doc.get("url", "")),
                "title": str(doc.get("title", "")),
                "error": str(doc.get("error", "")),
            }
        )
    return summary


if __name__ == "__main__":
    raise SystemExit(main())
