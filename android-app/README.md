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

## Debug pelo VS Code

Pre-requisitos na maquina:

- JDK instalado e disponivel no PATH (`java -version`)
- Android SDK com `adb` no PATH (`adb devices`)
- Gradle ou Gradle Wrapper (`gradle -version` ou `gradlew.bat`)
- Extensao VS Code `Android Debug`

Passos:

1. Abra a pasta raiz do repositorio no VS Code.
2. Instale as extensoes recomendadas quando o VS Code pedir.
3. Conecte um celular com depuracao USB ou abra um emulador.
4. No terminal do VS Code, confirme:

```powershell
adb devices
```

5. Rode a task `Android: installDebug` ou inicie o debug `Android: Debug app`.

Se voce ainda nao tiver JDK/Android SDK/Gradle, instale o Android Studio uma vez.
Ele configura o SDK e permite gerar o Gradle Wrapper do projeto.
