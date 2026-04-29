# FrotaWeb OS Corretiva Android

Aplicativo Android nativo em Kotlin para abertura de O.S. corretiva.

## Fluxo

1. Tela de login:
   - URL da API
   - Empresa
   - Filial
   - Usuario
   - Senha

2. Tela de O.S.:
   - Campos obrigatorios marcados com `*`
   - Salvamento local offline
   - Envio para a API quando houver internet
   - Retorno do erro do FrotaWeb exibido em dialogo

## Offline

Quando nao ha internet ou a API nao responde, a O.S. fica no SQLite local com
status `PENDING`. Ao voltar para a tela de login, informe a senha e toque em
`Sincronizar pendentes`.

Por seguranca, a senha nao e persistida no banco local. Ela so fica em memoria
enquanto o app esta aberto.

## Compilar

Abra a pasta `android-app` no Android Studio e rode `app`.

Este ambiente Codex nao possui Java/Gradle instalado, entao a compilacao deve
ser feita pelo Android Studio.
