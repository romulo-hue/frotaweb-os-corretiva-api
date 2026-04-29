const API_BASE = window.location.origin;

const fields = [
  {
    name: "vehicle_code",
    label: "Veiculo",
    frota: "txtcd_veiculo",
    required: true,
    placeholder: "1830",
  },
  {
    name: "plate",
    label: "Placa",
    frota: "txtplaca",
    placeholder: "THP2B33",
  },
  {
    name: "defect_description",
    label: "Reclamacao livre",
    frota: "TL11802.edtobserv",
    required: true,
    wide: true,
    textarea: true,
    placeholder: "Descreva a falha informada pela operacao",
  },
  {
    name: "opening_datetime",
    label: "Entrada - Data/Hora",
    frota: "txtdh_entrada",
    required: true,
    placeholder: "12/03/2026 15:45:00",
  },
  {
    name: "entry_hourmeter",
    label: "Entrada - Horimetro",
    frota: "txtqt_hr_ent",
    required: true,
    placeholder: "0.00",
  },
  {
    name: "odometer",
    label: "Entrada - Km",
    frota: "txtqt_km_ent",
    required: true,
    placeholder: "5",
  },
  {
    name: "exit_datetime",
    label: "Saida - Data/Hora",
    frota: "txtdh_saida",
    required: true,
    placeholder: "12/03/2026 15:55:00",
  },
  {
    name: "exit_hourmeter",
    label: "Saida - Horimetro",
    frota: "txtqt_hr_sai",
    required: true,
    placeholder: "0.00",
  },
  {
    name: "exit_odometer",
    label: "Saida - Km",
    frota: "txtqt_km_sai",
    required: true,
    placeholder: "5",
  },
  {
    name: "start_datetime",
    label: "Data prevista para inicio",
    frota: "txtdh_inicio",
    required: true,
    placeholder: "12/03/2026 15:45:00",
  },
  {
    name: "expected_release_datetime",
    label: "Data prevista de liberacao",
    frota: "txtdh_prev",
    required: true,
    placeholder: "12/03/2026 15:55:00",
  },
  {
    name: "expected_hours",
    label: "Horas previstas",
    frota: "txtqt_hr_prev",
    required: true,
    placeholder: "0.00",
  },
  {
    name: "actual_hours",
    label: "Horas realizadas",
    frota: "txtqt_hr_rea",
    placeholder: "0.00",
  },
  {
    name: "branch_code",
    label: "Filial",
    frota: "txtcd_filial / hidcd_filialVeic",
    placeholder: "4",
  },
  {
    name: "department_code",
    label: "Departamento",
    frota: "txtcd_ccusto / hidcd_ccustoveic",
    placeholder: "420115",
  },
  {
    name: "occurrence_number",
    label: "Ocorrencia",
    frota: "txtnr_ocorr",
    placeholder: "0",
  },
  {
    name: "driver_code",
    label: "Motorista",
    frota: "txtcd_moto",
    placeholder: "0",
  },
  {
    name: "surcharge_value",
    label: "Valor acrescimo",
    frota: "txtvl_acresc",
    placeholder: "0",
  },
  {
    name: "return_order_number",
    label: "O.S retorno",
    frota: "txtnr_os_ret",
    placeholder: "0",
  },
  {
    name: "observations",
    label: "Observacao",
    frota: "txtnm_observ",
    maxLength: 50,
    placeholder: "Maximo 50 caracteres",
  },
];

const examplePayload = {
  vehicle_code: "1830",
  plate: "THP2B33",
  defect_description: "Teste de integracao local - falha mecanica informada pela operacao.",
  opening_datetime: "12/03/2026 15:45:00",
  entry_hourmeter: "0.00",
  odometer: "5",
  exit_datetime: "12/03/2026 15:55:00",
  exit_hourmeter: "0.00",
  exit_odometer: "5",
  start_datetime: "12/03/2026 15:45:00",
  expected_release_datetime: "12/03/2026 15:55:00",
  expected_hours: "0.00",
  actual_hours: "0.00",
  branch_code: "4",
  department_code: "420115",
  occurrence_number: "0",
  driver_code: "0",
  surcharge_value: "0",
  return_order_number: "0",
  observations: "",
};

const grid = document.querySelector("#field-grid");
const form = document.querySelector("#order-form");
const jsonPreview = document.querySelector("#json-preview");
const resultPreview = document.querySelector("#result-preview");
const dryRun = document.querySelector("#dry-run");
const modeLabel = document.querySelector("#mode-label");
const statusBox = document.querySelector("#api-status");
const fillExample = document.querySelector("#fill-example");
const credentialNames = ["empresa", "filial", "usuario", "senha"];

function createFields() {
  grid.innerHTML = "";
  for (const field of fields) {
    const wrapper = document.createElement("div");
    wrapper.className = `field${field.wide ? " wide" : ""}`;
    wrapper.dataset.name = field.name;

    const label = document.createElement("label");
    label.htmlFor = field.name;
    label.innerHTML = `<span>${field.label}${field.required ? ' <span class="required">*</span>' : ""}</span>`;

    const input = document.createElement(field.textarea ? "textarea" : "input");
    input.id = field.name;
    input.name = field.name;
    input.placeholder = field.placeholder || "";
    input.required = Boolean(field.required);
    if (!field.textarea) input.type = "text";
    if (field.maxLength) input.maxLength = field.maxLength;
    input.addEventListener("input", updatePreview);

    const hint = document.createElement("small");
    const limit = field.maxLength ? ` - max ${field.maxLength}` : "";
    hint.textContent = `${field.frota}${limit}`;

    wrapper.append(label, input, hint);
    grid.appendChild(wrapper);
  }
}

function payloadFromForm() {
  const payload = {};
  const credentials = {};
  for (const name of credentialNames) {
    const value = form.elements[name].value.trim();
    if (value !== "") credentials[name] = value;
  }
  if (Object.keys(credentials).length > 0) payload.credentials = credentials;

  for (const field of fields) {
    const value = form.elements[field.name].value.trim();
    if (value !== "") payload[field.name] = value;
  }

  for (const checkbox of form.querySelectorAll('input[type="checkbox"][name]')) {
    if (checkbox.checked) payload[checkbox.name] = true;
  }

  return payload;
}

function previewPayloadFromForm() {
  const payload = payloadFromForm();
  if (payload.credentials?.senha) {
    payload.credentials = { ...payload.credentials, senha: "********" };
  }
  return payload;
}

function updatePreview() {
  modeLabel.textContent = dryRun.checked ? "simulacao" : "gravacao real";
  modeLabel.className = dryRun.checked ? "" : "warning";
  jsonPreview.textContent = JSON.stringify(previewPayloadFromForm(), null, 2);
}

function fillFromPayload(payload) {
  for (const field of fields) {
    form.elements[field.name].value = payload[field.name] ?? "";
  }
  for (const checkbox of form.querySelectorAll('input[type="checkbox"][name]')) {
    checkbox.checked = Boolean(payload[checkbox.name]);
  }
  updatePreview();
}

function markInvalidFields() {
  let ok = true;
  for (const name of credentialNames) {
    const wrapper = form.querySelector(`[data-name="${name}"]`);
    const input = form.elements[name];
    const invalid = input.value.trim() === "";
    wrapper.classList.toggle("invalid", invalid);
    if (invalid) ok = false;
  }
  for (const field of fields) {
    const wrapper = grid.querySelector(`[data-name="${field.name}"]`);
    const input = form.elements[field.name];
    const invalid = field.required && input.value.trim() === "";
    wrapper.classList.toggle("invalid", invalid);
    if (invalid) ok = false;
  }
  return ok;
}

async function checkApi() {
  try {
    const response = await fetch(`${API_BASE}/health`);
    if (!response.ok) throw new Error(`HTTP ${response.status}`);
    statusBox.textContent = "API online";
    statusBox.className = "api-status ok";
  } catch (error) {
    statusBox.textContent = "API offline";
    statusBox.className = "api-status fail";
  }
}

async function submitOrder(event) {
  event.preventDefault();
  resultPreview.textContent = "Enviando...";

  if (!markInvalidFields()) {
    resultPreview.textContent = "Preencha os campos obrigatorios marcados com *.";
    return;
  }

  if (!dryRun.checked) {
    const confirmed = window.confirm("Confirmar gravacao real da O.S. corretiva no FrotaWeb?");
    if (!confirmed) {
      resultPreview.textContent = "Gravacao real cancelada.";
      return;
    }
  }

  const submitButton = form.querySelector('button[type="submit"]');
  submitButton.disabled = true;
  try {
    const response = await fetch(`${API_BASE}/os-corretiva?simulacao=${dryRun.checked}`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payloadFromForm()),
    });
    const text = await response.text();
    let body;
    try {
      body = JSON.parse(text);
    } catch {
      body = text;
    }
    resultPreview.textContent = JSON.stringify(body, null, 2);
    resultPreview.className = response.ok ? "success" : "error";
  } catch (error) {
    resultPreview.textContent = `Falha ao chamar API: ${error.message}`;
    resultPreview.className = "error";
  } finally {
    submitButton.disabled = false;
  }
}

createFields();
fillFromPayload(examplePayload);
checkApi();

form.addEventListener("submit", submitOrder);
for (const name of credentialNames) {
  form.elements[name].addEventListener("input", updatePreview);
}
dryRun.addEventListener("change", updatePreview);
fillExample.addEventListener("click", () => fillFromPayload(examplePayload));
