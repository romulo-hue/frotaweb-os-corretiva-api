from __future__ import annotations

from dataclasses import dataclass
from http.cookiejar import CookieJar
import re
from typing import Mapping
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode, urljoin
from urllib.request import HTTPCookieProcessor, Request, build_opener


DEFAULT_BASE_URL = "http://3.19.17.18/"
DEFAULT_ENCODING = "iso-8859-1"


class FrotaWebError(RuntimeError):
    """Raised when FrotaWeb returns an unexpected response."""


@dataclass(frozen=True)
class HttpResponse:
    url: str
    status: int
    headers: Mapping[str, str]
    text: str
    raw: bytes


@dataclass(frozen=True)
class LoginResult:
    logged_in: bool
    message: str
    response: HttpResponse


class FrotaWebClient:
    def __init__(self, base_url: str = DEFAULT_BASE_URL, timeout: int = 30):
        self.base_url = base_url.rstrip("/") + "/"
        self.timeout = timeout
        self.cookies = CookieJar()
        self.opener = build_opener(HTTPCookieProcessor(self.cookies))

    def open_home(self) -> HttpResponse:
        return self.get("default.asp")

    def login(
        self,
        empresa: str,
        usuario: str,
        senha: str,
        filial: str = "0",
        recurso: str = "",
    ) -> LoginResult:
        # Initial GET creates the ASP session cookie used by the login form.
        self.open_home()
        self.get("Telas/TL10320.asp")

        payload = {
            "hidpwd": senha,
            "txtcd_empresa": empresa,
            "txtcd_usuario": usuario,
            "txtcd_recurso": recurso,
            "txtcd_filial": filial or "0",
            # The browser-side JS clears pwdsenha and sends the real password in
            # hidpwd, so we mirror that behavior.
            "pwdsenha": "",
        }
        response = self.post(
            "Telas/TL10320.asp",
            data=payload,
            headers={"Referer": self._url("Telas/TL10320.asp")},
        )

        logged_in = self.check_session()
        alerts = extract_alerts(response.text)
        if logged_in:
            message = "Login realizado."
        elif alerts:
            message = " | ".join(alerts)
        else:
            message = "Login nao confirmado; confira empresa, usuario, filial e senha."
        return LoginResult(logged_in=logged_in, message=message, response=response)

    def check_session(self) -> bool:
        response = self.get("verificaSessao.asp")
        return response.text.strip() == "1"

    def get(
        self,
        path: str,
        params: Mapping[str, object] | None = None,
        headers: Mapping[str, str] | None = None,
    ) -> HttpResponse:
        return self.request("GET", path, params=params, headers=headers)

    def post(
        self,
        path: str,
        data: Mapping[str, object] | None = None,
        params: Mapping[str, object] | None = None,
        headers: Mapping[str, str] | None = None,
    ) -> HttpResponse:
        return self.request("POST", path, data=data, params=params, headers=headers)

    def request(
        self,
        method: str,
        path: str,
        data: Mapping[str, object] | None = None,
        params: Mapping[str, object] | None = None,
        headers: Mapping[str, str] | None = None,
    ) -> HttpResponse:
        url = self._url(path)
        if params:
            separator = "&" if "?" in url else "?"
            url = url + separator + urlencode(clean_payload(params), encoding=DEFAULT_ENCODING)

        body = None
        request_headers = {
            "User-Agent": "Mozilla/5.0 FrotaWebIntegration/0.1",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        }
        if headers:
            request_headers.update(headers)

        if data is not None:
            body = urlencode(clean_payload(data), encoding=DEFAULT_ENCODING).encode(DEFAULT_ENCODING)
            request_headers.setdefault(
                "Content-Type",
                "application/x-www-form-urlencoded; charset=iso-8859-1",
            )

        req = Request(url, data=body, headers=request_headers, method=method.upper())
        try:
            with self.opener.open(req, timeout=self.timeout) as resp:
                raw = resp.read()
                charset = resp.headers.get_content_charset() or DEFAULT_ENCODING
                text = raw.decode(charset, errors="replace")
                return HttpResponse(
                    url=resp.geturl(),
                    status=resp.status,
                    headers=dict(resp.headers.items()),
                    text=text,
                    raw=raw,
                )
        except HTTPError as exc:
            raw = exc.read()
            text = raw.decode(DEFAULT_ENCODING, errors="replace")
            raise FrotaWebError(f"HTTP {exc.code} ao acessar {url}: {text[:300]}") from exc
        except URLError as exc:
            raise FrotaWebError(f"Falha ao acessar {url}: {exc.reason}") from exc

    def _url(self, path: str) -> str:
        if path.startswith("http://") or path.startswith("https://"):
            return path
        return urljoin(self.base_url, path.lstrip("/"))


def clean_payload(payload: Mapping[str, object]) -> dict[str, str]:
    return {key: "" if value is None else str(value) for key, value in payload.items()}


def extract_alerts(html: str) -> list[str]:
    alerts: list[str] = []
    for match in re.finditer(r"alert\((['\"])(.*?)\1\)", html, flags=re.IGNORECASE | re.DOTALL):
        message = match.group(2).replace("\\n", " ").strip()
        if message:
            alerts.append(message)
    return alerts
