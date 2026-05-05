from __future__ import annotations

import json
import os
from pathlib import Path
from datetime import datetime
from typing import Any

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field, ConfigDict

from frotaweb import CorrectiveOrder, CorrectiveOrderService, FrotaWebClient, FrotaWebError
from frotaweb import PerformedService, PerformedServiceLauncher
from frotaweb.os_correctiva import order_value, order_value_with_number, render_mapping
from api.panel_store import PanelStore
from scripts._env import load_dotenv


ROOT_DIR = Path(__file__).resolve().parents[1]
MAPPING_PATH = ROOT_DIR / "config" / "os_correctiva.tl11800.json"
STATIC_DIR = ROOT_DIR / "static"
PANEL_DB_PATH = ROOT_DIR / "data" / "panel.db"


class FrotaWebCredentials(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    empresa: str = Field(..., examples=["1"])
    usuario: str = Field(..., examples=["232"])
    senha: str = Field(..., repr=False)
    filial: str = Field("0", examples=["1"])
    recurso: str = Field("", alias="recurso_humano", examples=["232"])


class CorrectiveOrderRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    credentials: FrotaWebCredentials | None = Field(None, alias="credenciais")
    vehicle_code: str = Field(..., alias="codigo_veiculo", examples=["0973"])
    defect_description: str = Field("", alias="descricao_defeito", examples=["Falha mecanica informada pela operacao."])
    order_number: str | None = Field(None, alias="numero_os")
    plate: str | None = Field(None, alias="placa")
    component_code: str | None = Field(None, alias="codigo_componente")
    opening_date: str | None = Field(None, alias="data_abertura")
    opening_datetime: str | None = Field(None, alias="data_hora_abertura", examples=["28/04/2026 08:00:00"])
    odometer: str | None = Field(None, alias="hodometro", examples=["137839"])
    entry_hourmeter: str | None = Field(None, alias="horimetro_entrada")
    exit_datetime: str | None = Field(None, alias="data_hora_saida", examples=["28/04/2026 10:00:00"])
    exit_odometer: str | None = Field(None, alias="hodometro_saida")
    exit_hourmeter: str | None = Field(None, alias="horimetro_saida")
    start_datetime: str | None = Field(None, alias="data_hora_inicio")
    expected_release_datetime: str | None = Field(None, alias="data_hora_previsao_liberacao")
    expected_hours: str | None = Field(None, alias="horas_previstas")
    actual_hours: str | None = Field(None, alias="horas_realizadas")
    branch_code: str | None = Field(None, alias="codigo_filial")
    department_code: str | None = Field(None, alias="codigo_departamento")
    workshop_code: str | None = Field(None, alias="codigo_oficina")
    service_code: str | None = Field(None, alias="codigo_servico")
    requester_code: str | None = Field(None, alias="codigo_solicitante")
    driver_code: str | None = Field(None, alias="codigo_motorista")
    occurrence_number: str | None = Field(None, alias="numero_ocorrencia")
    contract_number: str | None = Field(None, alias="numero_contrato")
    surcharge_value: str | None = Field(None, alias="valor_acrescimo")
    return_order_number: str | None = Field(None, alias="numero_os_retorno")
    observations: str | None = Field(None, alias="observacoes", max_length=50)
    investment: bool | None = Field(None, alias="investimento")
    accident: bool | None = Field(None, alias="acidente")
    roadside_assistance: bool | None = Field(None, alias="socorro")
    return_service: bool | None = Field(None, alias="servico_retorno")
    scheduled: bool | None = Field(None, alias="programada")
    raw_fields: dict[str, str] = Field(default_factory=dict, alias="campos_brutos")


class PerformedServiceRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    credentials: FrotaWebCredentials | None = Field(None, alias="credenciais")
    order_number: str = Field(..., alias="numero_os", examples=["64926"])
    vehicle_code: str | None = Field(None, alias="codigo_veiculo")
    plate: str | None = Field(None, alias="placa")
    service_code: str = Field(..., alias="codigo_servico", examples=["0"])
    resource_code: str | None = Field(None, alias="codigo_recurso_humano")
    spent_time: str = Field("000:00", alias="tempo_gasto")
    hourly_value: str = Field("0", alias="valor_hora")
    raw_fields: dict[str, str] = Field(default_factory=dict, alias="campos_brutos")


class LoginStatus(BaseModel):
    configured: bool
    missing_env: list[str]


class PanelLaunchRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True)
    credentials: FrotaWebCredentials = Field(..., alias="credenciais")


class PanelBatchLaunchRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True)
    order_ids: list[int]
    credentials: FrotaWebCredentials = Field(..., alias="credenciais")


panel_store = PanelStore(PANEL_DB_PATH)


app = FastAPI(
    title="FrotaWeb Local API",
    version="0.1.0",
    description="API local para testar e lançar OS corretiva na TL11800 do FrotaWeb.",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost", "http://127.0.0.1", "http://localhost:8000"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/config/status", response_model=LoginStatus)
def config_status() -> LoginStatus:
    load_dotenv(ROOT_DIR / ".env")
    required = ["FROTAWEB_BASE_URL"]
    missing = [name for name in required if not os.environ.get(name)]
    return LoginStatus(configured=not missing, missing_env=missing)


@app.get("/mapping/tl11800")
def mapping_tl11800() -> dict[str, Any]:
    return load_mapping()


if STATIC_DIR.exists():
    app.mount("/ui", StaticFiles(directory=STATIC_DIR, html=True), name="ui")


@app.post("/panel/os")
def panel_create_order(payload: CorrectiveOrderRequest) -> dict[str, Any]:
    payload_data = payload.model_dump(exclude_none=True, by_alias=False)
    credentials = payload_data.pop("credentials", None) or {}
    record = panel_store.create_order(
        kind="ORDER",
        payload=with_tl11800_defaults(payload_data),
        submitted_by=str(credentials.get("usuario", "")),
        source="android" if payload.raw_fields.get("origem") == "android" else "web",
    )
    return {
        "accepted": True,
        "panel_id": str(record["id"]),
        "created": False,
        "message": "O.S. recebida pelo painel e aguardando lancamento no FrotaWeb.",
        "status": record["status"],
    }


@app.post("/panel/os/servicos")
def panel_create_service(payload: PerformedServiceRequest) -> dict[str, Any]:
    payload_data = payload.model_dump(exclude_none=True, by_alias=False)
    credentials = payload_data.pop("credentials", None) or {}
    record = panel_store.create_order(
        kind="SERVICE",
        payload=payload_data,
        submitted_by=str(credentials.get("usuario", "")),
        source="android" if payload.raw_fields.get("origem") == "android" else "web",
        linked_order_number=payload.order_number,
    )
    return {
        "accepted": True,
        "panel_id": str(record["id"]),
        "created": False,
        "message": "Servico recebido pelo painel e aguardando lancamento no FrotaWeb.",
        "status": record["status"],
    }


@app.get("/panel/os")
def panel_list_orders(
    kind: str | None = Query(None, description="ORDER ou SERVICE"),
    status: str | None = Query(None, description="PENDING_REVIEW, FAILED ou LAUNCHED"),
) -> dict[str, Any]:
    return {"items": panel_store.list_orders(kind=kind, status=status)}


@app.post("/panel/os/{order_id}/launch")
def launch_panel_order(
    order_id: int,
    payload: PanelLaunchRequest,
) -> dict[str, Any]:
    try:
        record = panel_store.get_order(order_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=f"Registro do painel {order_id} nao encontrado.") from exc

    if record["kind"] == "SERVICE":
        request_payload = PerformedServiceRequest.model_validate(
            {"credenciais": payload.credentials.model_dump(by_alias=True), **record["payload"]}
        )
        try:
            result = create_performed_service(request_payload, dry_run=False)
        except HTTPException as exc:
            message = str(exc.detail)
            panel_store.mark_failed(order_id, message)
            return {
                "panel_id": order_id,
                "created": False,
                "message": message,
                "order_number": record["linked_order_number"],
            }
        except Exception as exc:  # pragma: no cover
            message = str(exc)
            panel_store.mark_failed(order_id, message)
            return {
                "panel_id": order_id,
                "created": False,
                "message": message,
                "order_number": record["linked_order_number"],
            }
        if result.get("created"):
            panel_store.mark_launched(order_id, order_number=record["linked_order_number"], message=result.get("message", ""))
        else:
            panel_store.mark_failed(order_id, result.get("message", "Falha ao lancar servico."))
        return {
            "panel_id": order_id,
            "created": bool(result.get("created")),
            "message": result.get("message", ""),
            "order_number": record["linked_order_number"],
        }

    request_payload = CorrectiveOrderRequest.model_validate(
        {"credenciais": payload.credentials.model_dump(by_alias=True), **record["payload"]}
    )
    try:
        result = create_corrective_order(request_payload, dry_run=False)
    except HTTPException as exc:
        message = str(exc.detail)
        panel_store.mark_failed(order_id, message)
        return {
            "panel_id": order_id,
            "created": False,
            "message": message,
            "order_number": "",
        }
    except Exception as exc:  # pragma: no cover
        message = str(exc)
        panel_store.mark_failed(order_id, message)
        return {
            "panel_id": order_id,
            "created": False,
            "message": message,
            "order_number": "",
        }

    order_number = str(result.get("order_number", "") or "")
    if result.get("created"):
        panel_store.mark_launched(order_id, order_number=order_number, message=result.get("message", ""))
    else:
        panel_store.mark_failed(order_id, result.get("message", "Falha ao lancar O.S."))
    return {
        "panel_id": order_id,
        "created": bool(result.get("created")),
        "message": result.get("message", ""),
        "order_number": order_number,
    }


@app.post("/panel/os/launch-batch")
def launch_panel_orders_batch(payload: PanelBatchLaunchRequest) -> dict[str, Any]:
    launch_payload = PanelLaunchRequest(credentials=payload.credentials)
    results = [launch_panel_order(order_id, launch_payload) for order_id in payload.order_ids]
    return {
        "results": results,
        "success_count": sum(1 for item in results if item.get("created")),
        "failure_count": sum(1 for item in results if not item.get("created")),
    }


@app.post("/os-corretiva")
def create_corrective_order(
    payload: CorrectiveOrderRequest,
    dry_run: bool = Query(
        True,
        alias="simulacao",
        description="Quando true, nao grava no FrotaWeb; apenas retorna os campos mapeados.",
    ),
) -> dict[str, Any]:
    mapping = load_mapping()
    payload_data = payload.model_dump(exclude_none=True, by_alias=False, exclude={"credentials"})
    order = CorrectiveOrder.from_dict(with_tl11800_defaults(payload_data))
    service = CorrectiveOrderService(FrotaWebClient(), mapping)

    if dry_run:
        return build_dry_run_response(service, mapping, order)

    client = make_logged_client(payload.credentials)
    service = CorrectiveOrderService(client, mapping)
    try:
        result = service.create(order)
    except (FrotaWebError, ValueError, KeyError) as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    debug_dir = ROOT_DIR / "artifacts" / "api_responses"
    debug_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    (debug_dir / f"os_corretiva_{stamp}.html").write_text(result.response.text, encoding="utf-8")
    for name, response in result.related_responses.items():
        (debug_dir / f"os_corretiva_{stamp}_{name}.html").write_text(
            response.text,
            encoding="utf-8",
        )

    return {
        "created": result.ok,
        "message": result.message,
        "order_number": result.order_number,
        "response_url": result.response.url,
        "debug_response_file": str((debug_dir / f"os_corretiva_{stamp}.html").resolve()),
        "related": {
            name: {
                "status": response.status,
                "url": response.url,
            }
            for name, response in result.related_responses.items()
        },
    }


@app.post("/os-corretiva/servicos")
def create_performed_service(
    payload: PerformedServiceRequest,
    dry_run: bool = Query(
        True,
        alias="simulacao",
        description="Quando true, nao grava no FrotaWeb; apenas retorna os campos que seriam enviados.",
    ),
) -> dict[str, Any]:
    payload_data = payload.model_dump(exclude_none=True, by_alias=False, exclude={"credentials"})
    service = PerformedService.from_dict(payload_data)
    company_code = payload.credentials.empresa if payload.credentials else os.environ.get("FROTAWEB_EMPRESA", "1")

    if dry_run:
        return {
            "dry_run": True,
            "would_submit": False,
            "screen_path": "Telas/TL11710.asp",
            "open_query": {"cd_empresa": company_code, "nr_ordserv": service.order_number},
            "main_fields": {
                "txtcd_empresa": company_code,
                "txtnr_ordserv": service.order_number,
                "txtcd_servico": service.service_code,
                "txtcd_recurso": service.resource_code or "",
                "txtqt_horas": service.spent_time,
                "txtvl_hora": service.hourly_value,
                "hidcd_veiculo": service.vehicle_code or "",
                "hidplaca": service.plate or "",
                "txtcd_priorid": "0",
                "txtcd_fornec": "0",
                "txtnr_nf": "0",
                "txtvl_serv_pr": "0",
                "txtvl_servico": "0",
                "txtdd_garanti": "0",
                "txtcd_motserv": "0",
                "txtcd_cparada": "0",
            },
        }

    client = make_logged_client(payload.credentials)
    launcher = PerformedServiceLauncher(client)
    try:
        result = launcher.create(service, company_code=company_code)
    except (FrotaWebError, ValueError, KeyError) as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    debug_dir = ROOT_DIR / "artifacts" / "api_responses"
    debug_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    (debug_dir / f"servico_realizado_{stamp}.html").write_text(result.response.text, encoding="utf-8")
    for name, response in result.related_responses.items():
        (debug_dir / f"servico_realizado_{stamp}_{name}.html").write_text(
            response.text,
            encoding="utf-8",
        )

    return {
        "created": result.ok,
        "message": result.message,
        "response_url": result.response.url,
        "debug_response_file": str((debug_dir / f"servico_realizado_{stamp}.html").resolve()),
        "related": {
            name: {
                "status": response.status,
                "url": response.url,
            }
            for name, response in result.related_responses.items()
        },
    }


def build_dry_run_response(
    service: CorrectiveOrderService,
    mapping: dict[str, Any],
    order: CorrectiveOrder,
) -> dict[str, Any]:
    main_fields = service._map_order(order)
    main_fields.update(service._map_order(order, mapping.get("derived_hidden_field_map", {})))
    main_fields.update({str(k): str(v) for k, v in mapping.get("extra_fields", {}).items()})
    fake_order_number = order.order_number or "<gerado-pelo-frotaweb>"
    related = {}
    for name, config in mapping.get("related_screens", {}).items():
        related_fields = {
            str(field_name): str(order_value_with_number(order, canonical_name, fake_order_number))
            for canonical_name, field_name in config.get("field_map", {}).items()
            if field_name and order_value_with_number(order, canonical_name, fake_order_number) is not None
        }
        related_fields.update(render_mapping(config.get("extra_fields", {}), order, fake_order_number))
        related[name] = {
            "screen_path": config.get("screen_path"),
            "open_query": render_mapping(config.get("open_query", {}), order, fake_order_number),
            "submit_fields": related_fields,
        }

    return {
        "dry_run": True,
        "would_submit": False,
        "screen_path": mapping["screen_path"],
        "prepare_new_fields": mapping.get("prepare_new_fields", {}),
        "pre_submit_steps": mapping.get("pre_submit_steps", []),
        "main_fields": main_fields,
        "checkboxes": {
            field_name: bool(order_value(order, canonical_name))
            for canonical_name, field_name in mapping.get("checkbox_map", {}).items()
            if field_name and order_value(order, canonical_name) is not None
        },
        "related": related,
    }


def with_tl11800_defaults(data: dict[str, Any]) -> dict[str, Any]:
    defaults = {
        "defect_description": "",
        "entry_hourmeter": "0.00",
        "exit_hourmeter": "0.00",
        "expected_hours": "0.00",
        "actual_hours": "0.00",
        "occurrence_number": "0",
        "driver_code": "0",
        "surcharge_value": "0",
        "return_order_number": "0",
    }
    merged = defaults.copy()
    merged.update(data)
    if not merged.get("exit_odometer") and merged.get("odometer"):
        merged["exit_odometer"] = merged["odometer"]
    if not merged.get("start_datetime") and merged.get("opening_datetime"):
        merged["start_datetime"] = merged["opening_datetime"]
    if not merged.get("expected_release_datetime") and merged.get("exit_datetime"):
        merged["expected_release_datetime"] = merged["exit_datetime"]
    return merged


def make_logged_client(credentials: FrotaWebCredentials | None = None) -> FrotaWebClient:
    load_dotenv(ROOT_DIR / ".env")
    base_url = os.environ.get("FROTAWEB_BASE_URL")
    if not base_url:
        raise HTTPException(
            status_code=500,
            detail="Variavel ausente no ambiente: FROTAWEB_BASE_URL",
        )

    if credentials is None:
        required = ["FROTAWEB_EMPRESA", "FROTAWEB_USUARIO", "FROTAWEB_SENHA"]
        missing = [name for name in required if not os.environ.get(name)]
        if missing:
            raise HTTPException(
                status_code=400,
                detail=(
                    "Credenciais do FrotaWeb ausentes na requisicao. "
                    "Informe credenciais.empresa, credenciais.usuario, "
                    "credenciais.senha e credenciais.filial."
                ),
            )
        credentials = FrotaWebCredentials(
            empresa=os.environ["FROTAWEB_EMPRESA"],
            usuario=os.environ["FROTAWEB_USUARIO"],
            senha=os.environ["FROTAWEB_SENHA"],
            filial=os.environ.get("FROTAWEB_FILIAL", "0"),
        )

    client = FrotaWebClient(base_url)
    login = client.login(
        empresa=credentials.empresa,
        usuario=credentials.usuario,
        senha=credentials.senha,
        filial=credentials.filial,
        recurso=credentials.recurso,
    )
    if not login.logged_in:
        raise HTTPException(status_code=401, detail=login.message)
    return client


def load_mapping() -> dict[str, Any]:
    return json.loads(MAPPING_PATH.read_text(encoding="utf-8"))
