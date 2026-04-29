from __future__ import annotations

from dataclasses import dataclass, field
import re
from typing import Any, Mapping

from .client import FrotaWebClient, HttpResponse, extract_alerts
from .forms import parse_forms


@dataclass
class CorrectiveOrder:
    vehicle_code: str
    defect_description: str
    order_number: str | None = None
    plate: str | None = None
    component_code: str | None = None
    opening_date: str | None = None
    opening_datetime: str | None = None
    odometer: str | None = None
    entry_hourmeter: str | None = None
    exit_datetime: str | None = None
    exit_odometer: str | None = None
    exit_hourmeter: str | None = None
    start_datetime: str | None = None
    expected_release_datetime: str | None = None
    expected_hours: str | None = None
    actual_hours: str | None = None
    branch_code: str | None = None
    department_code: str | None = None
    workshop_code: str | None = None
    service_code: str | None = None
    requester_code: str | None = None
    driver_code: str | None = None
    occurrence_number: str | None = None
    contract_number: str | None = None
    surcharge_value: str | None = None
    return_order_number: str | None = None
    observations: str | None = None
    investment: bool | None = None
    accident: bool | None = None
    roadside_assistance: bool | None = None
    return_service: bool | None = None
    scheduled: bool | None = None
    raw_fields: dict[str, str] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "CorrectiveOrder":
        return cls(
            vehicle_code=str(data["vehicle_code"]),
            defect_description=str(data["defect_description"]),
            order_number=optional_str(data.get("order_number")),
            plate=optional_str(data.get("plate")),
            component_code=optional_str(data.get("component_code")),
            opening_date=optional_str(data.get("opening_date")),
            opening_datetime=optional_str(data.get("opening_datetime")),
            odometer=optional_str(data.get("odometer")),
            entry_hourmeter=optional_str(data.get("entry_hourmeter")),
            exit_datetime=optional_str(data.get("exit_datetime")),
            exit_odometer=optional_str(data.get("exit_odometer")),
            exit_hourmeter=optional_str(data.get("exit_hourmeter")),
            start_datetime=optional_str(data.get("start_datetime")),
            expected_release_datetime=optional_str(data.get("expected_release_datetime")),
            expected_hours=optional_str(data.get("expected_hours")),
            actual_hours=optional_str(data.get("actual_hours")),
            branch_code=optional_str(data.get("branch_code")),
            department_code=optional_str(data.get("department_code")),
            workshop_code=optional_str(data.get("workshop_code")),
            service_code=optional_str(data.get("service_code")),
            requester_code=optional_str(data.get("requester_code")),
            driver_code=optional_str(data.get("driver_code")),
            occurrence_number=optional_str(data.get("occurrence_number")),
            contract_number=optional_str(data.get("contract_number")),
            surcharge_value=optional_str(data.get("surcharge_value")),
            return_order_number=optional_str(data.get("return_order_number")),
            observations=optional_str(data.get("observations")),
            investment=optional_bool(data.get("investment")),
            accident=optional_bool(data.get("accident")),
            roadside_assistance=optional_bool(data.get("roadside_assistance")),
            return_service=optional_bool(data.get("return_service")),
            scheduled=optional_bool(data.get("scheduled")),
            raw_fields={str(k): str(v) for k, v in data.get("raw_fields", {}).items()},
        )


@dataclass(frozen=True)
class CreateOrderResult:
    ok: bool
    message: str
    response: HttpResponse
    order_number: str | None = None
    related_responses: dict[str, HttpResponse] = field(default_factory=dict)


class CorrectiveOrderService:
    def __init__(self, client: FrotaWebClient, mapping: Mapping[str, Any]):
        self.client = client
        self.mapping = mapping

    def create(self, order: CorrectiveOrder) -> CreateOrderResult:
        screen_path = self._required("screen_path")
        self._validate_required_field_map(order)
        form_response = self.client.get(screen_path, params=self.mapping.get("open_query"))
        form = self._select_form(form_response.text, screen_path)

        prepare_fields = self.mapping.get("prepare_new_fields")
        if prepare_fields:
            fields = form.fields
            fields.update({str(k): str(v) for k, v in prepare_fields.items()})
            action = str(self.mapping.get("prepare_path") or form.action or screen_path)
            form_response = self.client.post(
                action,
                data=fields,
                params=self.mapping.get("prepare_query"),
            )
            form = self._select_form(form_response.text, screen_path)

        for step in self.mapping.get("pre_submit_steps", []):
            fields = form.fields
            fields.update(self._map_order(order, step.get("field_map")))
            fields.update({str(k): str(v) for k, v in step.get("extra_fields", {}).items()})
            action = str(step.get("path") or form.action or screen_path)
            if action.startswith("./"):
                action = action[2:]
            form_response = self.client.post(
                action,
                data=fields,
                params=step.get("query"),
            )
            form = self._select_form(form_response.text, screen_path)

        fields = form.fields
        fields.update({str(k): str(v) for k, v in self.mapping.get("extra_fields", {}).items()})
        fields.update(self._map_order(order))
        fields.update(self._map_order(order, self.mapping.get("derived_hidden_field_map", {})))
        fields.update({str(k): str(v) for k, v in self.mapping.get("save_fields", {}).items()})
        fields.update(order.raw_fields)

        action = str(self.mapping.get("submit_path") or form.action or screen_path)
        if action.startswith("./"):
            action = action[2:]
        response = self.client.post(action, data=fields, params=self.mapping.get("submit_query"))

        iis_error = extract_iis_error(response.text)
        km_warning = extract_km_warning(response.text)
        order_number = extract_order_number(response.text)
        alerts = [] if (order_number or km_warning) else extract_alerts(response.text)
        session_ok = self.client.check_session()
        ok = not alerts and not iis_error and not km_warning and session_ok and bool(order_number)
        if iis_error:
            message = "Erro IIS do FrotaWeb ao salvar OS: " + iis_error
        elif km_warning:
            message = "OS nao gravada: critica de KM/Horimetro do FrotaWeb: " + km_warning
        elif alerts:
            message = " | ".join(alerts)
        elif order_number:
            message = f"OS enviada. Numero detectado: {order_number}"
        elif not session_ok:
            message = "OS nao confirmada: sessao FrotaWeb invalida apos o envio."
        else:
            message = (
                "OS nao confirmada: o FrotaWeb nao retornou numero de O.S. "
                "O lancamento provavelmente nao foi gravado."
            )

        related_responses: dict[str, HttpResponse] = {}
        if ok and order.defect_description and order_number:
            related_ok, related_message, related_responses = self._submit_related_screens(
                order,
                order_number,
            )
            ok = related_ok
            if related_message:
                message = message + " " + related_message

        return CreateOrderResult(
            ok=ok,
            message=message,
            response=response,
            order_number=order_number,
            related_responses=related_responses,
        )

    def _select_form(self, html: str, screen_path: str):
        forms = parse_forms(html)
        if not forms:
            raise ValueError(f"Nenhum formulario encontrado em {screen_path}.")
        form_index = int(self.mapping.get("form_index", 0))
        try:
            return forms[form_index]
        except IndexError as exc:
            raise ValueError(f"Formulario index {form_index} nao existe em {screen_path}.") from exc

    def _map_order(
        self,
        order: CorrectiveOrder,
        field_map: Mapping[str, Any] | None = None,
    ) -> dict[str, str]:
        if field_map is None:
            field_map = self.mapping.get("field_map", {})
        payload: dict[str, str] = {}
        for canonical_name, field_name in field_map.items():
            value = order_value(order, canonical_name)
            if value is not None and field_name:
                payload[str(field_name)] = str(value)

        if field_map is self.mapping.get("field_map", {}):
            checkbox_map = self.mapping.get("checkbox_map", {})
            for canonical_name, field_name in checkbox_map.items():
                value = order_value(order, canonical_name)
                if value is True and field_name:
                    payload[str(field_name)] = "1"
                elif value is False and field_name:
                    payload.pop(str(field_name), None)
        return payload

    def _submit_related_screens(
        self,
        order: CorrectiveOrder,
        order_number: str,
    ) -> tuple[bool, str, dict[str, HttpResponse]]:
        responses: dict[str, HttpResponse] = {}
        related_screens = self.mapping.get("related_screens", {})

        free_complaint = related_screens.get("free_complaint")
        if not free_complaint:
            return True, "", responses

        response = self._submit_related_screen(
            name="free_complaint",
            config=free_complaint,
            order=order,
            order_number=order_number,
        )
        responses["free_complaint"] = response
        alerts = extract_alerts(response.text)
        if alerts:
            return False, "Falha ao salvar reclamacao livre: " + " | ".join(alerts), responses
        return True, "Reclamacao livre enviada.", responses

    def _submit_related_screen(
        self,
        name: str,
        config: Mapping[str, Any],
        order: CorrectiveOrder,
        order_number: str,
    ) -> HttpResponse:
        screen_path = str(config.get("screen_path") or "")
        if not screen_path:
            raise ValueError(f"Tela relacionada sem screen_path: {name}")

        params = render_mapping(config.get("open_query", {}), order, order_number)
        form_response = self.client.get(screen_path, params=params)
        forms = parse_forms(form_response.text)
        if not forms:
            raise ValueError(f"Nenhum formulario encontrado na tela relacionada: {screen_path}")

        form_index = int(config.get("form_index", 0))
        form = forms[form_index]
        fields = form.fields
        fields.update(render_mapping(config.get("extra_fields", {}), order, order_number))
        for canonical_name, field_name in config.get("field_map", {}).items():
            value = order_value_with_number(order, canonical_name, order_number)
            if value is not None and field_name:
                fields[str(field_name)] = str(value)

        action = str(config.get("submit_path") or form.action or screen_path)
        submit_query = render_mapping(config.get("submit_query", {}), order, order_number)
        return self.client.post(action, data=fields, params=submit_query)

    def _required(self, key: str) -> str:
        value = self.mapping.get(key)
        if not value:
            raise ValueError(f"Campo obrigatorio ausente no mapping: {key}")
        return str(value)

    def _validate_required_field_map(self, order: CorrectiveOrder) -> None:
        field_map = self.mapping.get("field_map", {})
        required_fields = self.mapping.get(
            "required_field_map",
            ["vehicle_code", "defect_description"],
        )
        missing = []
        for canonical_name in required_fields:
            value = order_value(order, canonical_name)
            if value is None or str(value).strip() == "":
                missing.append(canonical_name)
                continue
            if value is not None and not field_map.get(canonical_name):
                missing.append(canonical_name)
        if missing:
            raise ValueError(
                "Mapeamento incompleto para criar OS corretiva. "
                "Campos canonicos sem nome tecnico FrotaWeb: "
                + ", ".join(missing)
            )


def optional_str(value: Any) -> str | None:
    if value is None:
        return None
    return str(value)


def optional_bool(value: Any) -> bool | None:
    if value is None:
        return None
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in {"1", "true", "sim", "s", "yes", "y"}:
            return True
        if normalized in {"0", "false", "nao", "não", "n", "no"}:
            return False
    return bool(value)


def order_value(order: CorrectiveOrder, canonical_name: str) -> Any:
    if canonical_name == "opening_datetime":
        return order.opening_datetime or order.opening_date
    if canonical_name == "opening_datetime_old":
        return order.opening_datetime or order.opening_date
    if canonical_name == "exit_datetime_old":
        return order.exit_datetime
    if canonical_name == "odometer_old":
        return order.odometer
    if canonical_name == "exit_odometer_old":
        return order.exit_odometer
    if canonical_name == "entry_hourmeter_old":
        return order.entry_hourmeter
    if canonical_name == "exit_hourmeter_old":
        return order.exit_hourmeter
    return getattr(order, canonical_name, None)


def order_value_with_number(
    order: CorrectiveOrder,
    canonical_name: str,
    order_number: str,
) -> Any:
    if canonical_name == "order_number":
        return order.order_number or order_number
    return order_value(order, canonical_name)


def render_mapping(
    values: Mapping[str, Any],
    order: CorrectiveOrder,
    order_number: str,
) -> dict[str, str]:
    rendered = {}
    for key, value in values.items():
        text = str(value)
        text = text.replace("{order_number}", order_number)
        text = text.replace("{vehicle_code}", order.vehicle_code)
        rendered[str(key)] = text
    return rendered


def extract_order_number(html: str) -> str | None:
    patterns = [
        r"name=[\"']?txtnr_ordserv[\"']?[^>]*value=[\"']?(\d+)",
        r"id=[\"']?txtnr_ordserv[\"']?[^>]*value=[\"']?(\d+)",
        r"nr_ordserv=(\d{2,})",
        r"\.val\((\d{2,})\)",
        r"name=[\"']?txtnr_os[\"']?[^>]*value=[\"']?(\d+)",
        r"id=[\"']?txtnr_os[\"']?[^>]*value=[\"']?(\d+)",
        r"(?:OS|O\.S\.|ordem de servico)\D{0,30}(\d{2,})",
    ]
    for pattern in patterns:
        match = re.search(pattern, html, flags=re.IGNORECASE)
        if not match:
            continue
        number = match.group(1)
        if number not in {"0", "11800"}:
            return number
    return None


def extract_iis_error(html: str) -> str | None:
    match = re.search(
        r"<b>Erro IIS\s*:</b></td><td>(.*?)</td>",
        html,
        flags=re.IGNORECASE | re.DOTALL,
    )
    if not match:
        return None
    text = re.sub(r"<[^>]+>", " ", match.group(1))
    text = re.sub(r"\s+", " ", text).strip()
    return text or None


def extract_km_warning(html: str) -> str | None:
    match = re.search(r"critica_km\('([^']+)'", html, flags=re.IGNORECASE | re.DOTALL)
    if not match:
        return None
    text = match.group(1)
    text = text.replace("\\n", " ")
    text = re.sub(r"\s+", " ", text).strip()
    try:
        text = text.encode("latin1", errors="ignore").decode("utf-8", errors="ignore")
    except UnicodeError:
        pass
    return text or None
