from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping

from .client import FrotaWebClient, HttpResponse, extract_alerts
from .forms import parse_forms
from .os_correctiva import extract_iis_error


@dataclass
class PerformedService:
    order_number: str
    service_code: str
    vehicle_code: str | None = None
    plate: str | None = None
    resource_code: str | None = None
    spent_time: str = "000:00"
    hourly_value: str = "0"
    raw_fields: dict[str, str] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "PerformedService":
        return cls(
            order_number=str(data["order_number"]),
            service_code=str(data["service_code"]),
            vehicle_code=optional_str(data.get("vehicle_code")),
            plate=optional_str(data.get("plate")),
            resource_code=optional_str(data.get("resource_code")),
            spent_time=str(data.get("spent_time") or "000:00"),
            hourly_value=str(data.get("hourly_value") or "0"),
            raw_fields={str(k): str(v) for k, v in data.get("raw_fields", {}).items()},
        )


@dataclass(frozen=True)
class PerformedServiceResult:
    ok: bool
    message: str
    response: HttpResponse
    related_responses: dict[str, HttpResponse] = field(default_factory=dict)


class PerformedServiceLauncher:
    def __init__(self, client: FrotaWebClient):
        self.client = client

    def create(self, service: PerformedService, company_code: str = "1") -> PerformedServiceResult:
        if not service.order_number.strip():
            raise ValueError("Numero da O.S. deve ser informado.")
        if not service.service_code.strip():
            raise ValueError("Servico deve ser informado.")

        responses: dict[str, HttpResponse] = {}
        response = self.client.get(
            "Telas/TL11710.asp",
            params={"cd_empresa": company_code, "nr_ordserv": service.order_number},
        )
        form = self._select_form(response.text)

        fields = form.fields
        fields.update(
            {
                "txtcd_empresa": company_code,
                "txtnr_ordserv": service.order_number,
                "hidstatusreg": fields.get("hidstatusreg", "1") or "1",
            }
        )
        response = self.client.post(
            "Telas/TL11710.asp",
            params={"acao": "nr_ordserv"},
            data=fields,
        )
        responses["validate_order"] = response
        form = self._select_form(response.text)
        fields = form.fields

        fields.update(self._service_fields(service, company_code))
        if service.service_code.strip() not in {"", "0"}:
            response = self.client.post(
                "Telas/TL11710.asp",
                params={"acao": "cd_servico"},
                data=fields,
            )
            responses["validate_service"] = response
            form = self._select_form(response.text)
            fields = form.fields

        fields.update(self._service_fields(service, company_code))
        if (service.resource_code or "").strip() not in {"", "0"}:
            response = self.client.post(
                "Telas/TL11710.asp",
                params={"acao": "cd_recurso"},
                data=fields,
            )
            responses["validate_resource"] = response
            form = self._select_form(response.text)
            fields = form.fields

        fields.update(self._service_fields(service, company_code))
        fields.update(service.raw_fields)
        response = self.client.post("Telas/TL11710.asp", data=fields)

        iis_error = extract_iis_error(response.text)
        alerts = extract_alerts(response.text)
        session_ok = self.client.check_session()
        ok = not alerts and not iis_error and session_ok
        if iis_error:
            message = "Erro IIS do FrotaWeb ao salvar servico: " + iis_error
        elif alerts:
            message = " | ".join(alerts)
        elif not session_ok:
            message = "Servico nao confirmado: sessao FrotaWeb invalida apos o envio."
        else:
            message = "Servico realizado enviado."

        return PerformedServiceResult(ok=ok, message=message, response=response, related_responses=responses)

    def _service_fields(self, service: PerformedService, company_code: str) -> dict[str, str]:
        spent_time = normalize_time(service.spent_time)
        hourly_value = normalize_number(service.hourly_value)
        fields = {
            "txtcd_empresa": company_code,
            "txtnr_ordserv": service.order_number,
            "txtcd_servico": service.service_code,
            "txtqt_horas": spent_time,
            "txtvl_hora": hourly_value,
            "hidvl_padrao": hourly_value,
            "hidvl_serv_pr_aux": "0",
            "txtcd_priorid": "0",
            "txtcd_fornec": "0",
            "txtnr_nf": "0",
            "txtvl_serv_pr": "0",
            "txtvl_servico": "0",
            "txtdd_garanti": "0",
            "txtcd_motserv": "0",
            "txtcd_cparada": "0",
        }
        if service.vehicle_code:
            fields["hidcd_veiculo"] = service.vehicle_code
        if service.plate:
            fields["hidplaca"] = service.plate
        if service.resource_code is not None:
            fields["txtcd_recurso"] = normalize_number(service.resource_code)
        return fields

    def _select_form(self, html: str):
        forms = parse_forms(html)
        if not forms:
            raise ValueError("Nenhum formulario encontrado na TL11710.")
        return forms[0]


def optional_str(value: Any) -> str | None:
    if value is None:
        return None
    return str(value)


def normalize_number(value: Any, default: str = "0") -> str:
    text = str(value or "").strip()
    if "," in text:
        text = text.replace(".", "").replace(",", ".")
    return text or default


def normalize_time(value: Any) -> str:
    text = str(value or "").strip()
    return text if text else "000:00"
