# Integracao FrotaWeb - OS corretiva

Base inicial para automatizar o lancamento de ordem de servico corretiva no
FrotaWeb.

O FrotaWeb neste ambiente usa ASP classico, frames e sessao por cookie
`ASPSESSIONID...`. O login fica em `Telas/TL10320.asp`. A tela exata de
ordem de servico corretiva so aparece apos login, entao este projeto separa:

- login e manutencao da sessao;
- inspecao de telas/forms depois de autenticado;
- envio da OS corretiva usando um mapeamento de campos configuravel.

## Estrutura

- `frotaweb/client.py`: cliente HTTP com cookies e login.
- `frotaweb/forms.py`: parser simples de formularios HTML/ASP.
- `frotaweb/os_correctiva.py`: modelo e envio da OS corretiva.
- `scripts/probe_login.py`: valida se as credenciais entram no FrotaWeb.
- `scripts/inspect_screen.py`: lista forms/campos de uma tela `Telas/TLxxxxx.asp`.
- `scripts/create_corrective_os.py`: cria uma OS usando JSON de pedido e mapeamento.
- `config/os_correctiva.mapping.example.json`: exemplo de mapeamento.
- `examples/order.corrective.example.json`: exemplo de payload.

## Configuracao

Copie `.env.example` para `.env` ou exporte as variaveis no terminal:

```powershell
$env:FROTAWEB_BASE_URL = "http://3.19.17.18/"
$env:FROTAWEB_EMPRESA = "1"
$env:FROTAWEB_USUARIO = "123"
$env:FROTAWEB_FILIAL = "0"
$env:FROTAWEB_SENHA = "sua-senha"
```

Evite colocar senha em linha de comando, porque ela pode aparecer no historico.

## 1. Testar login

Use o Python empacotado pelo Codex:

```powershell
& "C:\Users\benel.FRZNBIGOR\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe" scripts\probe_login.py
```

Se retornar `logged_in: true`, a sessao HTTP esta funcionando.

## 2. Descobrir a tela de OS corretiva

No FrotaWeb, abra manualmente a tela de ordem de servico corretiva e observe a
URL do iframe/tela. Normalmente o padrao e algo como:

```text
Telas/TL12345.asp
```

Depois rode:

```powershell
& "C:\Users\benel.FRZNBIGOR\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe" scripts\inspect_screen.py Telas/TL12345.asp
```

O script imprime os forms, actions e nomes dos campos. Com isso, preencha
`config/os_correctiva.mapping.example.json`.

## 3. Criar OS corretiva

Para a tela informada no print, use o mapeamento base:

```text
config/os_correctiva.tl11800.json
```

Ele ja aponta para `Telas/TL11800.asp`. O formulario principal foi mapeado a
partir da tela capturada, e a reclamacao livre usa a tela relacionada
`Telas/TL11802.asp`.

Depois de configurar o `.env` e revisar `examples/order.corrective.example.json`:

```powershell
& "C:\Users\benel.FRZNBIGOR\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe" scripts\create_corrective_os.py `
  --order examples\order.corrective.example.json `
  --mapping config\os_correctiva.tl11800.json
```

## Validacao antes de producao

O fluxo HTTP esta preparado, mas o primeiro envio real deve ser feito com um
pedido de teste controlado, porque `scripts/create_corrective_os.py` envia dados
para o FrotaWeb e pode gravar uma OS de verdade.

## API local FastAPI

Instale as dependencias:

```powershell
& "C:\Users\benel.FRZNBIGOR\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe" -m pip install -r requirements.txt
```

Suba a API:

```powershell
& "C:\Users\benel.FRZNBIGOR\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe" scripts\run_api.py
```

Endpoints:

- `GET http://127.0.0.1:8000/health`
- `GET http://127.0.0.1:8000/docs`
- `POST http://127.0.0.1:8000/os-corretiva?simulacao=true`
- `POST http://127.0.0.1:8000/os-corretiva?simulacao=false`

`simulacao=true` e o padrao e nao grava no FrotaWeb. `simulacao=false` faz login
com as credenciais informadas na requisicao e envia a OS corretiva.

Exemplo resumido de payload para gravacao real:

```json
{
  "credentials": {
    "empresa": "1",
    "filial": "1",
    "usuario": "232",
    "senha": "senha-do-usuario"
  },
  "vehicle_code": "1682",
  "plate": "RKH1F96",
  "defect_description": "Falha informada pela operacao.",
  "opening_datetime": "08/04/2026 16:20:00",
  "entry_hourmeter": "0.00",
  "odometer": "32873",
  "exit_datetime": "10/04/2026 10:50:00",
  "exit_hourmeter": "0.00",
  "exit_odometer": "32873",
  "start_datetime": "08/04/2026 16:20:00",
  "expected_release_datetime": "10/04/2026 10:50:00",
  "expected_hours": "0.00"
}
```

## Tela local

Com a API em execucao, acesse:

```text
http://127.0.0.1:8000/ui/
```

A tela monta o JSON esperado pela API, mostra os nomes tecnicos do FrotaWeb e
mantem a simulacao ligada por padrao.

## Deploy no Render

O projeto ja possui `render.yaml`, `Procfile` e `runtime.txt`.

No Render, crie um Web Service apontando para o repositorio GitHub e configure:

- Build command: `pip install -r requirements.txt`
- Start command: `uvicorn api.main:app --host 0.0.0.0 --port $PORT`
- Health check path: `/health`

Configure apenas a URL base no painel do Render, sem commitar `.env`:

```text
FROTAWEB_BASE_URL
```

As credenciais do FrotaWeb (`empresa`, `filial`, `usuario` e `senha`) sao
informadas pelo mecanico na tela a cada lancamento. A API usa a senha somente
naquela requisicao e nao a retorna no JSON de resposta.

Depois do deploy, a tela fica em:

```text
https://SEU-SERVICO.onrender.com/ui/
```

## Aplicativo Android

O projeto Android fica em:

```text
android-app/
```

Ele foi criado em Kotlin nativo e possui:

- tela de login com URL da API, empresa, filial, usuario e senha;
- tela de preenchimento da O.S. com campos obrigatorios indicados;
- salvamento offline em SQLite local;
- sincronizacao manual de pendentes;
- exibicao do retorno de erro enviado pela API/FrotaWeb.

Abra `android-app/` no Android Studio para compilar e gerar o APK.
