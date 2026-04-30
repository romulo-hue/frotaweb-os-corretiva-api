package br.com.frotaweb.oscorretiva

import android.app.AlertDialog
import android.app.Activity
import android.content.ContentValues
import android.content.Context
import android.database.sqlite.SQLiteDatabase
import android.database.sqlite.SQLiteOpenHelper
import android.graphics.Typeface
import android.graphics.Color
import android.graphics.drawable.GradientDrawable
import android.content.res.ColorStateList
import android.net.ConnectivityManager
import android.net.NetworkCapabilities
import android.os.Bundle
import android.text.Editable
import android.text.InputFilter
import android.text.InputType
import android.text.TextWatcher
import android.view.Gravity
import android.view.View
import android.widget.Button
import android.widget.CheckBox
import android.widget.EditText
import android.widget.LinearLayout
import android.widget.ProgressBar
import android.widget.ScrollView
import android.widget.TextView
import org.json.JSONObject
import java.io.BufferedReader
import java.io.OutputStreamWriter
import java.net.HttpURLConnection
import java.net.URL
import java.text.SimpleDateFormat
import java.util.Date
import java.util.Locale

class MainActivity : Activity() {
    private lateinit var store: OrderStore
    private val prefs by lazy { getSharedPreferences("frotaweb-login", MODE_PRIVATE) }
    private val defaultApiUrl = "https://frotaweb-os-corretiva-api.onrender.com"
    private var currentPassword: String = ""
    private var currentApiUrl: String = defaultApiUrl
    private var currentEmpresa: String = "1"
    private var currentFilial: String = "1"
    private var currentUsuario: String = ""
    private var currentRecurso: String = ""
    private var activeOrderNumber: String = ""
    private var activeOrderPayload: JSONObject? = null
    private var loadingDialog: AlertDialog? = null
    private var pendingNetworkCalls = 0

    private lateinit var apiUrl: EditText
    private lateinit var empresa: EditText
    private lateinit var filial: EditText
    private lateinit var usuario: EditText
    private lateinit var recurso: EditText
    private lateinit var senha: EditText

    private val orderInputs = linkedMapOf<String, EditText>()
    private val orderFormats = linkedMapOf<String, FieldFormat>()
    private val serviceInputs = linkedMapOf<String, EditText>()
    private val serviceFormats = linkedMapOf<String, FieldFormat>()
    private val checks = linkedMapOf<String, CheckBox>()

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        store = OrderStore(this)
        loadSession()
        showLoginScreen()
    }

    private fun showLoginScreen() {
        val root = page()
        root.addView(hero("FrotaWeb OS", "Manutencao corretiva"))
        val card = formCard()
        card.addView(title("Login"))

        apiUrl = input("URL da API", currentApiUrl)
        empresa = input("Empresa *", currentEmpresa)
        filial = input("Filial *", currentFilial)
        usuario = input("Usuario *", currentUsuario)
        recurso = input("Recurso humano *", currentRecurso.ifBlank { currentUsuario })
        senha = input("Senha *", "", InputType.TYPE_CLASS_TEXT or InputType.TYPE_TEXT_VARIATION_PASSWORD)

        addInputView(card, "Empresa *", empresa)
        addInputView(card, "Filial *", filial)
        addInputView(card, "Usuario *", usuario)
        addInputView(card, "Recurso humano *", recurso)
        addInputView(card, "Senha *", senha)

        val enter = button("Continuar")
        enter.setOnClickListener {
            if (required(empresa, filial, usuario, recurso, senha)) {
                saveLoginSession()
                showOrderScreen()
            }
        }
        card.addView(enter)

        val sync = button("Sincronizar pendentes")
        sync.setOnClickListener {
            if (required(empresa, filial, usuario, recurso, senha)) {
                saveLoginSession()
                syncPending()
            }
        }
        card.addView(sync)

        val pending = button("Consultar O.S. nao enviadas")
        pending.setOnClickListener { showUnsentOrdersScreen() }
        card.addView(pending)
        card.addView(note("Lancamentos pendentes/com erro: ${store.countUnsent()}"))
        root.addView(card)
        setContentView(scroll(root))
    }

    private fun showOrderScreen(prefill: JSONObject? = activeOrderPayload, orderNumber: String = activeOrderNumber) {
        orderInputs.clear()
        orderFormats.clear()
        checks.clear()

        val root = page()
        root.addView(hero("Nova O.S.", "Corretiva"))
        val card = formCard()
        card.addView(title("Dados da O.S."))
        if (orderNumber.isNotBlank()) {
            card.addView(statusBanner("O.S. gerada: $orderNumber"))
        }
        card.addView(note("Campos com * sao obrigatorios. O app salva offline se estiver sem internet."))

        addOrderInput(card, "vehicle_code", "Veiculo *", "Ex.: 1682", FieldFormat.INTEGER, prefill?.optString("vehicle_code", ""))
        addOrderInput(card, "plate", "Placa", "Ex.: RKH1F96", FieldFormat.TEXT, prefill?.optString("plate", ""))
        addOrderInput(card, "defect_description", "Reclamacao livre", "Descreva a falha", FieldFormat.TEXT, prefill?.optString("defect_description", ""))
        addOrderInput(card, "opening_datetime", "Entrada - Data/Hora *", "dd/MM/aaaa HH:mm:ss", FieldFormat.DATETIME, prefill?.optString("opening_datetime", ""))
        addOrderInput(card, "entry_hourmeter", "Entrada - Horimetro", "0.00", FieldFormat.DECIMAL, prefill?.optString("entry_hourmeter", ""))
        addOrderInput(card, "odometer", "Entrada - Km *", "103.345", FieldFormat.KM, prefill?.optString("odometer", ""))
        addOrderInput(card, "exit_datetime", "Saida - Data/Hora *", "dd/MM/aaaa HH:mm:ss", FieldFormat.DATETIME, prefill?.optString("exit_datetime", ""))
        addOrderInput(card, "exit_hourmeter", "Saida - Horimetro", "0.00", FieldFormat.DECIMAL, prefill?.optString("exit_hourmeter", ""))
        addOrderInput(card, "branch_code", "Filial da O.S. *", "Ex.: 3", FieldFormat.INTEGER, prefill?.optString("branch_code", ""))
        addOrderInput(card, "department_code", "Departamento *", "Ex.: 420112", FieldFormat.INTEGER, prefill?.optString("department_code", ""))
        addOrderInput(card, "observations", "Observacao (max 50)", "", FieldFormat.TEXT, prefill?.optString("observations", ""))

        card.addView(subtitle("Marcadores opcionais"))
        addCheck(card, "investment", "Investimento", prefill?.optBoolean("investment", false) == true)
        addCheck(card, "accident", "Acidente", prefill?.optBoolean("accident", false) == true)
        addCheck(card, "roadside_assistance", "Socorro", prefill?.optBoolean("roadside_assistance", false) == true)
        addCheck(card, "return_service", "Retorno", prefill?.optBoolean("return_service", false) == true)
        addCheck(card, "scheduled", "Programada", prefill?.optBoolean("scheduled", false) == true)

        val save = button("Salvar e enviar")
        save.setOnClickListener { saveAndSend() }
        card.addView(save)

        if (orderNumber.isNotBlank()) {
            val service = button("Servicos realizados")
            service.setOnClickListener { showServiceScreen() }
            card.addView(service)
        } else {
            card.addView(note("Servicos realizados serao liberados apos gerar o numero da O.S."))
        }

        val back = button("Voltar ao login")
        back.setOnClickListener { showLoginScreen() }
        card.addView(back)
        val pending = button("Consultar O.S. nao enviadas")
        pending.setOnClickListener { showUnsentOrdersScreen() }
        card.addView(pending)
        card.addView(note("Lancamentos pendentes/com erro: ${store.countUnsent()}"))
        root.addView(card)
        setContentView(scroll(root))
    }

    private fun showServiceScreen(prefill: JSONObject? = null) {
        val orderNumber = prefill?.optString("order_number", activeOrderNumber).orEmpty().ifBlank { activeOrderNumber }
        if (orderNumber.isBlank()) {
            showMessage("O.S. obrigatoria", "Salve a O.S. primeiro para gerar o numero e liberar servicos.")
            showOrderScreen()
            return
        }
        activeOrderNumber = orderNumber
        serviceInputs.clear()
        serviceFormats.clear()

        val root = page()
        root.addView(hero("Servicos", "Realizados"))
        val card = formCard()
        card.addView(title("Servico da O.S."))
        card.addView(statusBanner("O.S. vinculada: $orderNumber"))
        card.addView(note("Campos com * sao obrigatorios. O servico sera vinculado a uma O.S. ja criada."))

        addServiceInput(card, "vehicle_code", "Veiculo", "Ex.: 1719", FieldFormat.INTEGER, serviceVehicle(prefill))
        addServiceInput(card, "plate", "Placa", "Ex.: SAX8C86", FieldFormat.TEXT, servicePlate(prefill))
        serviceInputs["vehicle_code"]?.isEnabled = false
        serviceInputs["plate"]?.isEnabled = false
        card.addView(note("Recurso humano: ${loginRecurso().ifBlank { loginUsuario() }}"))
        addServiceInput(card, "service_code", "Servico *", "Ex.: 0", FieldFormat.INTEGER, prefill?.optString("service_code", ""))
        addServiceInput(card, "spent_time", "Tempo gasto", "000:00", FieldFormat.TIME, prefill?.optString("spent_time", "000:00"))
        addServicesForOrder(card, orderNumber)

        card.addView(button("Salvar servico").apply { setOnClickListener { saveAndSendService() } })
        card.addView(button("Voltar a O.S.").apply { setOnClickListener { showOrderScreen() } })
        card.addView(button("Voltar ao login").apply { setOnClickListener { showLoginScreen() } })
        root.addView(card)
        setContentView(scroll(root))
    }

    private fun showUnsentOrdersScreen() {
        val root = page()
        root.addView(hero("Lancamentos", "Locais"))
        val card = formCard()
        card.addView(title("Consulta local"))
        card.addView(note("Pendentes e com erro podem ser reenviados. Sincronizados ficam como historico local."))
        val records = store.all()
        if (records.isEmpty()) {
            card.addView(note("Nao ha lancamentos salvos neste aparelho."))
        } else {
            records.forEach { order ->
                val payload = JSONObject(order.payload)
                val label = buildString {
                    val type = payload.optString("_local_type", "ORDER")
                    append("${statusText(order.status)} - #${order.id} - ")
                    append(if (type == "SERVICE") "Servico O.S. " else "O.S. ")
                    append(if (type == "SERVICE") payload.optString("order_number", "-") else order.orderNumber ?: "Veiculo ${payload.optString("vehicle_code", "-")}")
                    val plate = payload.optString("plate", "")
                    if (plate.isNotBlank()) append(" / $plate")
                    append("\n")
                    append(payload.optString("opening_datetime", payload.optString("service_code", "-")))
                    append(" - ")
                    append(order.status)
                }
                card.addView(button(label).apply {
                    setOnClickListener { showUnsentOrderDetail(order.id) }
                })
            }
        }
        card.addView(button("Voltar ao login").apply { setOnClickListener { showLoginScreen() } })
        root.addView(card)
        setContentView(scroll(root))
    }

    private fun showUnsentOrderDetail(orderId: Long) {
        val order = store.find(orderId)
        if (order == null) {
            showMessage("O.S. nao encontrada", "Essa O.S. nao esta mais na fila local.")
            showUnsentOrdersScreen()
            return
        }

        val payload = JSONObject(order.payload)
        val root = page()
        val type = payload.optString("_local_type", "ORDER")
        root.addView(hero(if (type == "SERVICE") "Servico #${order.id}" else "O.S. #${order.id}", order.status))
        val card = formCard()
        card.addView(title("Preenchimento"))
        order.error?.takeIf { it.isNotBlank() }?.let {
            card.addView(note("Ultimo retorno: $it"))
        }
        val labels = if (type == "SERVICE") serviceDetailLabels else orderDetailLabels
        labels.forEach { (key, label) ->
            if (payload.has(key)) card.addView(detailLine(label, detailValue(key, payload)))
        }
        val checked = checksDetail(payload)
        if (checked.isNotBlank()) card.addView(detailLine("Marcadores", checked))

        if (order.status != "SYNCED") {
            card.addView(button(if (type == "SERVICE") "Reenviar este servico" else "Reenviar esta O.S.").apply {
                setOnClickListener { sendLocalRecord(order.id, JSONObject(order.payload)) }
            })
        }
        if (type == "SERVICE") {
            card.addView(button("Editar servico").apply { setOnClickListener { showServiceScreen(payload) } })
        }
        if (type == "ORDER") {
            val orderNumber = order.orderNumber ?: payload.optString("order_number", "")
            if (orderNumber.isNotBlank()) {
                card.addView(detailLine("Ordem de Servico", orderNumber))
                addServicesForOrder(card, orderNumber)
            }
        }
        card.addView(button("Voltar a lista").apply { setOnClickListener { showUnsentOrdersScreen() } })
        card.addView(button("Voltar ao login").apply { setOnClickListener { showLoginScreen() } })
        root.addView(card)
        setContentView(scroll(root))
    }

    private fun saveAndSend() {
        val requiredNames = listOf(
            "vehicle_code", "opening_datetime", "odometer",
            "exit_datetime", "branch_code", "department_code"
        )
        val missing = requiredNames.filter { orderInputs[it]?.text.toString().trim().isEmpty() }
        if (missing.isNotEmpty()) {
            showMessage("Campos obrigatorios", "Preencha todos os campos marcados com *.")
            return
        }
        val invalid = invalidFormats()
        if (invalid.isNotEmpty()) {
            showMessage("Formato invalido", "Corrija os campos: ${invalid.joinToString(", ")}.")
            return
        }
        if (!validateOrderDates()) return

        val payload = buildOrderPayload()
        val id = store.insert(payload.toString())
        if (!isOnline()) {
            showMessage("Salvo offline", "Sem internet. A O.S. ficou pendente para sincronizacao.")
            showOrderScreen()
            return
        }
        sendLocalRecord(id, payload)
    }

    private fun syncPending() {
        if (!hasCredentials()) return
        if (!isOnline()) {
            showMessage("Sem internet", "Nao foi possivel sincronizar agora.")
            return
        }
        val pending = store.unsent()
        if (pending.isEmpty()) {
            showMessage("Sincronizacao", "Nao ha O.S. pendente.")
            return
        }
        pending.forEach { sendLocalRecord(it.id, JSONObject(it.payload)) }
    }

    private fun saveAndSendService() {
        if (activeOrderNumber.isBlank()) {
            showMessage("O.S. obrigatoria", "Salve a O.S. primeiro para gerar o numero e liberar servicos.")
            showOrderScreen()
            return
        }
        val requiredNames = listOf("service_code")
        val missing = requiredNames.filter { serviceInputs[it]?.text.toString().trim().isEmpty() }
        if (missing.isNotEmpty()) {
            showMessage("Campos obrigatorios", "Preencha o campo Servico.")
            return
        }
        val payload = buildServicePayload()
        val id = store.insert(payload.toString())
        if (!isOnline()) {
            showMessage("Salvo offline", "Sem internet. O servico ficou pendente para sincronizacao.")
            showServiceScreen()
            return
        }
        sendLocalRecord(id, payload)
    }

    private fun sendLocalRecord(id: Long, payload: JSONObject) {
        if (!hasCredentials()) return
        val isService = payload.optString("_local_type", "ORDER") == "SERVICE"
        showLoading(if (isService) "Enviando servico..." else "Enviando O.S....")
        Thread {
            try {
                val path = if (isService) "/os-corretiva/servicos?simulacao=false" else "/os-corretiva?simulacao=false"
                val endpoint = "${currentApiUrl.ifBlank { normalizeApiBaseUrl(apiUrl.text.toString()) }}$path"
                val response = postJson(
                    endpoint,
                    withCredentials(payload)
                )
                val body = response.asJsonOrThrow(endpoint)
                val created = body.optBoolean("created", false)
                val message = body.optString("message", body.optString("detail", response.body))
                runOnUiThread {
                    hideLoading()
                    if (created) {
                        val orderNumber = body.optString("order_number")
                        store.markSynced(id, orderNumber)
                        if (!isService && orderNumber.isNotBlank()) {
                            activeOrderNumber = orderNumber
                            activeOrderPayload = JSONObject(payload.toString()).apply {
                                put("order_number", orderNumber)
                            }
                            saveActiveOrder()
                        }
                        showMessage(if (isService) "Servico enviado" else "O.S. enviada", message)
                        if (isService) showServiceScreen() else showOrderScreen(activeOrderPayload, activeOrderNumber)
                    } else {
                        store.markFailed(id, message)
                        showMessage("Erro do FrotaWeb", message)
                    }
                }
            } catch (ex: Exception) {
                runOnUiThread {
                    hideLoading()
                    store.markPending(id, ex.message ?: "Falha de rede")
                    showMessage("Salvo offline", "Nao foi possivel enviar agora. O registro ficou pendente.\n${ex.message}")
                }
            }
        }.start()
    }

    private fun buildOrderPayload(): JSONObject {
        val json = JSONObject()
        json.put("_local_type", "ORDER")
        orderInputs.forEach { (name, edit) ->
            val value = payloadValue(name, edit.text.toString().trim(), orderFormats[name] ?: FieldFormat.TEXT)
            if (value.isNotEmpty()) json.put(name, value)
        }
        val opening = json.optString("opening_datetime", "")
        val exit = json.optString("exit_datetime", "")
        val odometer = json.optString("odometer", "")
        json.put("entry_hourmeter", json.optString("entry_hourmeter", "0").ifBlank { "0" })
        json.put("exit_hourmeter", json.optString("exit_hourmeter", "0").ifBlank { "0" })
        if (odometer.isNotBlank()) json.put("exit_odometer", odometer)
        if (opening.isNotBlank()) json.put("start_datetime", opening)
        if (exit.isNotBlank()) json.put("expected_release_datetime", exit)
        json.put("expected_hours", "0.00")
        checks.forEach { (name, check) ->
            if (check.isChecked) json.put(name, true)
        }
        return json
    }

    private fun buildServicePayload(): JSONObject {
        val json = JSONObject()
        json.put("_local_type", "SERVICE")
        json.put("order_number", activeOrderNumber)
        json.put("resource_code", loginRecurso().ifBlank { loginUsuario() })
        serviceInputs.forEach { (name, edit) ->
            val value = payloadValue(name, edit.text.toString().trim(), serviceFormats[name] ?: FieldFormat.TEXT)
            if (value.isNotEmpty()) json.put(name, value)
        }
        if (json.optString("vehicle_code").isBlank()) json.put("vehicle_code", serviceVehicle())
        if (json.optString("plate").isBlank()) json.put("plate", servicePlate())
        json.put("spent_time", json.optString("spent_time", "000:00").ifBlank { "000:00" })
        json.put("hourly_value", "0")
        return json
    }

    private fun withCredentials(orderPayload: JSONObject): JSONObject {
        val json = JSONObject(orderPayload.toString())
        json.remove("_local_type")
        json.put("credentials", JSONObject().apply {
            put("empresa", loginEmpresa())
            put("filial", loginFilial())
            put("usuario", loginUsuario())
            put("recurso", loginRecurso().ifBlank { loginUsuario() })
            put("senha", currentPassword)
        })
        return json
    }

    private fun hasCredentials(): Boolean {
        refreshLoginCacheFromViews()
        if (loginUsuario().isBlank() || loginRecurso().ifBlank { loginUsuario() }.isBlank() || currentPassword.isBlank()) {
            showMessage(
                "Login necessario",
                "Informe usuario, recurso humano e senha no login antes de enviar ou sincronizar."
            )
            showLoginScreen()
            return false
        }
        return true
    }

    private fun loadSession() {
        currentApiUrl = prefs.getString("apiUrl", defaultApiUrl) ?: defaultApiUrl
        currentEmpresa = prefs.getString("empresa", "1") ?: "1"
        currentFilial = prefs.getString("filial", "1") ?: "1"
        currentUsuario = prefs.getString("usuario", "") ?: ""
        currentRecurso = prefs.getString("recurso", currentUsuario) ?: currentUsuario
        activeOrderNumber = prefs.getString("activeOrderNumber", "") ?: ""
        activeOrderPayload = prefs.getString("activeOrderPayload", "")?.takeIf { it.isNotBlank() }?.let {
            runCatching { JSONObject(it) }.getOrNull()
        }
    }

    private fun saveLoginSession() {
        currentPassword = senha.text.toString()
        currentApiUrl = normalizeApiBaseUrl(apiUrl.text.toString())
        currentEmpresa = empresa.text.toString().trim()
        currentFilial = filial.text.toString().trim()
        currentUsuario = usuario.text.toString().trim()
        currentRecurso = recurso.text.toString().trim().ifBlank { currentUsuario }
        apiUrl.setText(currentApiUrl)
        prefs.edit()
            .putString("apiUrl", currentApiUrl)
            .putString("empresa", currentEmpresa)
            .putString("filial", currentFilial)
            .putString("usuario", currentUsuario)
            .putString("recurso", currentRecurso)
            .apply()
    }

    private fun saveActiveOrder() {
        prefs.edit()
            .putString("activeOrderNumber", activeOrderNumber)
            .putString("activeOrderPayload", activeOrderPayload?.toString().orEmpty())
            .apply()
    }

    private fun refreshLoginCacheFromViews() {
        if (::apiUrl.isInitialized) currentApiUrl = normalizeApiBaseUrl(apiUrl.text.toString())
        if (::empresa.isInitialized) currentEmpresa = empresa.text.toString().trim()
        if (::filial.isInitialized) currentFilial = filial.text.toString().trim()
        if (::usuario.isInitialized) currentUsuario = usuario.text.toString().trim()
        if (::recurso.isInitialized) currentRecurso = recurso.text.toString().trim().ifBlank { currentUsuario }
    }

    private fun loginEmpresa() = currentEmpresa.ifBlank {
        if (::empresa.isInitialized) empresa.text.toString().trim() else prefs.getString("empresa", "1").orEmpty()
    }

    private fun loginFilial() = currentFilial.ifBlank {
        if (::filial.isInitialized) filial.text.toString().trim() else prefs.getString("filial", "1").orEmpty()
    }

    private fun loginUsuario() = currentUsuario.ifBlank {
        if (::usuario.isInitialized) usuario.text.toString().trim() else prefs.getString("usuario", "").orEmpty()
    }

    private fun loginRecurso() = currentRecurso.ifBlank {
        if (::recurso.isInitialized) recurso.text.toString().trim() else prefs.getString("recurso", loginUsuario()).orEmpty()
    }

    private fun serviceVehicle(prefill: JSONObject? = null): String =
        prefill?.optString("vehicle_code", "")?.takeIf { it.isNotBlank() }
            ?: activeOrderPayload?.optString("vehicle_code", "")?.takeIf { it.isNotBlank() }
            ?: orderInputs["vehicle_code"]?.text?.toString()?.trim().orEmpty()

    private fun servicePlate(prefill: JSONObject? = null): String =
        prefill?.optString("plate", "")?.takeIf { it.isNotBlank() }
            ?: activeOrderPayload?.optString("plate", "")?.takeIf { it.isNotBlank() }
            ?: orderInputs["plate"]?.text?.toString()?.trim().orEmpty()

    private fun normalizeApiBaseUrl(rawUrl: String): String {
        var url = rawUrl.trim()
        if (url.endsWith("/")) url = url.trimEnd('/')
        url = url.substringBefore("?")
        val lower = url.lowercase()
        val suffixes = listOf("/docs", "/redoc", "/openapi.json", "/os-corretiva")
        suffixes.forEach { suffix ->
            if (lower.endsWith(suffix)) {
                url = url.dropLast(suffix.length).trimEnd('/')
            }
        }
        return url
    }

    private fun postJson(urlText: String, json: JSONObject): ApiResponse {
        val conn = (URL(urlText).openConnection() as HttpURLConnection).apply {
            requestMethod = "POST"
            connectTimeout = 30000
            readTimeout = 60000
            doOutput = true
            setRequestProperty("Content-Type", "application/json")
        }
        OutputStreamWriter(conn.outputStream, Charsets.UTF_8).use { it.write(json.toString()) }
        val status = conn.responseCode
        val stream = if (conn.responseCode in 200..299) conn.inputStream else conn.errorStream
        val body = stream?.let { BufferedReader(it.reader(Charsets.UTF_8)).use { reader -> reader.readText() } } ?: ""
        return ApiResponse(status, body)
    }

    private fun addOrderInput(
        root: LinearLayout,
        name: String,
        label: String,
        hint: String,
        format: FieldFormat = FieldFormat.TEXT,
        value: String? = ""
    ) {
        val edit = input(label, formatInitialValue(value.orEmpty(), format), inputTypeFor(format), hint)
        applyFormat(edit, format)
        orderInputs[name] = edit
        orderFormats[name] = format
        addInputView(root, label, edit)
    }

    private fun addServiceInput(
        root: LinearLayout,
        name: String,
        label: String,
        hint: String,
        format: FieldFormat = FieldFormat.TEXT,
        value: String? = ""
    ) {
        val edit = input(label, formatInitialValue(value.orEmpty(), format), inputTypeFor(format), hint)
        applyFormat(edit, format)
        serviceInputs[name] = edit
        serviceFormats[name] = format
        addInputView(root, label, edit)
    }

    private fun inputTypeFor(format: FieldFormat): Int = when (format) {
        FieldFormat.DATETIME, FieldFormat.INTEGER, FieldFormat.KM, FieldFormat.TIME -> InputType.TYPE_CLASS_NUMBER
        FieldFormat.DECIMAL -> InputType.TYPE_CLASS_NUMBER or InputType.TYPE_NUMBER_FLAG_DECIMAL
        FieldFormat.TEXT -> InputType.TYPE_CLASS_TEXT
    }

    private fun applyFormat(edit: EditText, format: FieldFormat) {
        when (format) {
            FieldFormat.DATETIME -> {
                edit.filters = arrayOf(InputFilter.LengthFilter(19))
                edit.addTextChangedListener(maskWatcher(edit, ::formatDateTimeDigits))
            }
            FieldFormat.KM -> edit.addTextChangedListener(maskWatcher(edit, ::formatThousandsDigits))
            FieldFormat.TIME -> {
                edit.filters = arrayOf(InputFilter.LengthFilter(6))
                edit.addTextChangedListener(maskWatcher(edit, ::formatTimeDigits))
            }
            else -> Unit
        }
    }

    private fun maskWatcher(edit: EditText, formatter: (String) -> String) = object : TextWatcher {
        private var editing = false

        override fun beforeTextChanged(s: CharSequence?, start: Int, count: Int, after: Int) = Unit
        override fun onTextChanged(s: CharSequence?, start: Int, before: Int, count: Int) = Unit

        override fun afterTextChanged(s: Editable?) {
            if (editing) return
            editing = true
            val formatted = formatter(s?.toString().orEmpty().digitsOnly())
            edit.setText(formatted)
            edit.setSelection(formatted.length)
            editing = false
        }
    }

    private fun formatDateTimeDigits(digits: String): String {
        val value = digits.take(14)
        val output = StringBuilder()
        value.forEachIndexed { index, char ->
            if (index == 2 || index == 4) output.append('/')
            if (index == 8) output.append(' ')
            if (index == 10 || index == 12) output.append(':')
            output.append(char)
        }
        return output.toString()
    }

    private fun formatThousandsDigits(digits: String): String {
        if (digits.isBlank()) return ""
        return digits.reversed().chunked(3).joinToString(".").reversed()
    }

    private fun formatTimeDigits(digits: String): String {
        val value = digits.take(5)
        if (value.isBlank()) return ""
        val padded = value.padStart(5, '0')
        return "${padded.take(3)}:${padded.takeLast(2)}"
    }

    private fun formatInitialValue(value: String, format: FieldFormat): String {
        if (value.isBlank()) return ""
        return when (format) {
            FieldFormat.KM -> formatThousandsDigits(value.digitsOnly())
            FieldFormat.DATETIME -> formatDateTimeDigits(value.digitsOnly())
            FieldFormat.TIME -> formatTimeDigits(value.digitsOnly())
            else -> value
        }
    }

    private fun invalidFormats(): List<String> {
        return orderInputs.mapNotNull { (name, edit) ->
            val value = edit.text.toString().trim()
            if (value.isBlank()) return@mapNotNull null
            val valid = when (orderFormats[name] ?: FieldFormat.TEXT) {
                FieldFormat.DATETIME -> value.length == 19
                FieldFormat.DECIMAL -> value.replace(',', '.').matches(Regex("""\d+(\.\d{1,2})?"""))
                FieldFormat.INTEGER -> value.digitsOnly() == value
                FieldFormat.KM -> value.digitsOnly().isNotBlank()
                FieldFormat.TIME -> value.matches(Regex("""\d{3}:\d{2}"""))
                FieldFormat.TEXT -> true
            }
            if (valid) null else edit.hint.toString().substringBefore(" - ")
        }
    }

    private fun validateOrderDates(): Boolean {
        val openingText = orderInputs["opening_datetime"]?.text?.toString()?.trim().orEmpty()
        val exitText = orderInputs["exit_datetime"]?.text?.toString()?.trim().orEmpty()
        val opening = parseDateTime(openingText)
        val exit = parseDateTime(exitText)
        if (opening == null || exit == null) return true
        val now = Date()

        if (opening.after(now)) {
            orderInputs["opening_datetime"]?.error = "Entrada nao pode ser maior que hoje"
            showMessage(
                "Data de entrada invalida",
                "A Entrada - Data/Hora nao pode ser maior que a data e hora de hoje."
            )
            return false
        }

        if (exit.after(now)) {
            orderInputs["exit_datetime"]?.error = "Saida nao pode ser maior que hoje"
            showMessage(
                "Data de saida invalida",
                "A Saida - Data/Hora nao pode ser maior que a data e hora de hoje."
            )
            return false
        }

        if (exit.before(opening)) {
            orderInputs["exit_datetime"]?.error = "Saida nao pode ser menor que a entrada"
            showMessage(
                "Data de saida invalida",
                "A Saida - Data/Hora nao pode ser menor que a Entrada - Data/Hora."
            )
            return false
        }
        return true
    }

    private fun parseDateTime(value: String) = try {
        SimpleDateFormat("dd/MM/yyyy HH:mm:ss", Locale("pt", "BR")).apply {
            isLenient = false
        }.parse(value)
    } catch (_: Exception) {
        null
    }

    private fun payloadValue(name: String, value: String, format: FieldFormat): String = when (format) {
        FieldFormat.KM -> value.digitsOnly()
        FieldFormat.DECIMAL -> value.replace(',', '.')
        else -> value
    }

    private fun String.digitsOnly(): String = filter { it.isDigit() }

    private fun statusText(status: String): String = when (status) {
        "SYNCED" -> "Sincronizado"
        "FAILED" -> "Com erro"
        else -> "Pendente"
    }

    private fun addServicesForOrder(root: LinearLayout, orderNumber: String) {
        val services = store.servicesForOrder(orderNumber)
        root.addView(subtitle("Servicos ja lancados"))
        if (services.isEmpty()) {
            root.addView(note("Nenhum servico salvo localmente para esta O.S."))
            return
        }
        services.forEach { service ->
            val payload = JSONObject(service.payload)
            val label = "${statusText(service.status)} - Servico ${payload.optString("service_code", "-")}\nTempo: ${payload.optString("spent_time", "000:00")}"
            root.addView(button(label).apply {
                setOnClickListener { showUnsentOrderDetail(service.id) }
            })
        }
    }

    private fun detailValue(key: String, payload: JSONObject): String {
        val value = payload.optString(key)
        return when (key) {
            "odometer", "exit_odometer" -> formatThousandsDigits(value.digitsOnly())
            else -> value
        }
    }

    private fun addCheck(root: LinearLayout, name: String, label: String, checked: Boolean = false) {
        val check = CheckBox(this).apply {
            text = label
            textSize = 16f
            setTextColor(Color.rgb(24, 24, 27))
            buttonTintList = ColorStateList.valueOf(Color.BLACK)
            setPadding(8, 6, 8, 6)
            isChecked = checked
        }
        checks[name] = check
        root.addView(check)
    }

    private fun required(vararg edits: EditText): Boolean {
        val ok = edits.all { it.text.toString().trim().isNotEmpty() }
        if (!ok) showMessage("Campos obrigatorios", "Preencha todos os campos com *.")
        return ok
    }

    private fun isOnline(): Boolean {
        val manager = getSystemService(CONNECTIVITY_SERVICE) as ConnectivityManager
        val network = manager.activeNetwork ?: return false
        val caps = manager.getNetworkCapabilities(network) ?: return false
        return caps.hasCapability(NetworkCapabilities.NET_CAPABILITY_INTERNET)
    }

    private fun page() = LinearLayout(this).apply {
        orientation = LinearLayout.VERTICAL
        setPadding(22, 72, 22, 22)
        setBackgroundColor(Color.rgb(238, 240, 244))
    }

    private fun scroll(child: View) = ScrollView(this).apply {
        setBackgroundColor(Color.rgb(238, 240, 244))
        addView(child)
    }

    private fun hero(title: String, subtitle: String) = LinearLayout(this).apply {
        orientation = LinearLayout.VERTICAL
        setPadding(30, 34, 30, 34)
        background = GradientDrawable().apply {
            color = ColorStateList.valueOf(Color.BLACK)
            cornerRadii = floatArrayOf(34f, 34f, 34f, 34f, 0f, 0f, 0f, 0f)
        }
        addView(TextView(this@MainActivity).apply {
            text = title
            textSize = 24f
            setTextColor(Color.WHITE)
            setTypeface(typeface, Typeface.BOLD)
        })
        addView(TextView(this@MainActivity).apply {
            text = subtitle
            textSize = 14f
            setTextColor(Color.rgb(210, 210, 210))
            setPadding(0, 8, 0, 0)
        })
    }

    private fun formCard() = LinearLayout(this).apply {
        orientation = LinearLayout.VERTICAL
        setPadding(26, 30, 26, 28)
        background = GradientDrawable().apply {
            color = ColorStateList.valueOf(Color.WHITE)
            cornerRadii = floatArrayOf(0f, 0f, 0f, 0f, 34f, 34f, 34f, 34f)
        }
        elevation = 8f
    }

    private fun title(text: String) = TextView(this).apply {
        this.text = text
        textSize = 24f
        setTextColor(Color.rgb(24, 24, 27))
        setTypeface(typeface, Typeface.BOLD)
        setPadding(0, 0, 0, 20)
    }

    private fun subtitle(text: String) = TextView(this).apply {
        this.text = text
        textSize = 18f
        setTextColor(Color.rgb(24, 24, 27))
        setTypeface(typeface, Typeface.BOLD)
        setPadding(0, 24, 0, 10)
    }

    private fun note(text: String) = TextView(this).apply {
        this.text = text
        textSize = 14f
        setTextColor(Color.rgb(113, 113, 122))
        setPadding(0, 4, 0, 18)
    }

    private fun statusBanner(text: String) = TextView(this).apply {
        this.text = text
        textSize = 16f
        setTextColor(Color.WHITE)
        setTypeface(typeface, Typeface.BOLD)
        setPadding(18, 14, 18, 14)
        background = GradientDrawable().apply {
            color = ColorStateList.valueOf(Color.rgb(22, 101, 52))
            cornerRadius = 18f
        }
        layoutParams = LinearLayout.LayoutParams(
            LinearLayout.LayoutParams.MATCH_PARENT,
            LinearLayout.LayoutParams.WRAP_CONTENT
        ).apply {
            setMargins(0, 0, 0, 16)
        }
    }

    private fun detailLine(label: String, value: String) = TextView(this).apply {
        text = "$label\n$value"
        textSize = 15f
        setTextColor(Color.rgb(24, 24, 27))
        setPadding(4, 8, 4, 12)
    }

    private fun addInputView(root: LinearLayout, label: String, edit: EditText) {
        root.addView(TextView(this).apply {
            text = label
            textSize = 13f
            setTextColor(Color.rgb(24, 24, 27))
            setTypeface(typeface, Typeface.BOLD)
            setPadding(4, 8, 4, 2)
        })
        root.addView(edit)
    }

    private fun input(label: String, value: String, type: Int = InputType.TYPE_CLASS_TEXT, hint: String = "") =
        EditText(this).apply {
            this.hint = hint.ifBlank { label }
            setText(value)
            inputType = type
            textSize = 15f
            setSingleLine(!label.contains("Reclamacao"))

            setTextColor(Color.rgb(24, 24, 27))
            setHintTextColor(Color.rgb(140, 140, 148))
            setPadding(22, 16, 22, 16)
            background = GradientDrawable().apply {
                color = ColorStateList.valueOf(Color.rgb(250, 250, 250))
                cornerRadius = 18f
                setStroke(1, Color.rgb(240, 240, 240))
            }

            layoutParams = LinearLayout.LayoutParams(
                LinearLayout.LayoutParams.MATCH_PARENT,
                LinearLayout.LayoutParams.WRAP_CONTENT
            ).apply {
                setMargins(0, 8, 0, 12)
            }
        }

    private fun button(text: String) = Button(this).apply {
        this.text = text
        textSize = 16f
        setTextColor(Color.WHITE)
        setPadding(0, 14, 0, 14)
        background = GradientDrawable().apply {
            color = ColorStateList.valueOf(Color.BLACK)
            cornerRadius = 22f
        }

        layoutParams = LinearLayout.LayoutParams(
            LinearLayout.LayoutParams.MATCH_PARENT,
            LinearLayout.LayoutParams.WRAP_CONTENT
        ).apply {
            setMargins(0, 10, 0, 10)
        }
    }

    private fun showMessage(title: String, message: String) {
        AlertDialog.Builder(this).setTitle(title).setMessage(message).setPositiveButton("OK", null).show()
    }

    private fun showLoading(message: String) {
        pendingNetworkCalls += 1
        if (loadingDialog?.isShowing == true) return
        val content = LinearLayout(this).apply {
            orientation = LinearLayout.HORIZONTAL
            gravity = Gravity.CENTER_VERTICAL
            setPadding(36, 30, 36, 30)
            addView(ProgressBar(this@MainActivity).apply {
                isIndeterminate = true
            })
            addView(TextView(this@MainActivity).apply {
                text = message
                textSize = 16f
                setTextColor(Color.rgb(24, 24, 27))
                setPadding(24, 0, 0, 0)
            })
        }
        loadingDialog = AlertDialog.Builder(this)
            .setView(content)
            .setCancelable(false)
            .create().apply {
                setCanceledOnTouchOutside(false)
                show()
            }
    }

    private fun hideLoading() {
        pendingNetworkCalls = (pendingNetworkCalls - 1).coerceAtLeast(0)
        if (pendingNetworkCalls == 0) {
            loadingDialog?.dismiss()
            loadingDialog = null
        }
    }

    private val orderDetailLabels = listOf(
        "_local_type" to "Tipo",
        "vehicle_code" to "Veiculo",
        "plate" to "Placa",
        "defect_description" to "Reclamacao livre",
        "opening_datetime" to "Entrada - Data/Hora",
        "entry_hourmeter" to "Entrada - Horimetro",
        "odometer" to "Entrada - Km",
        "exit_datetime" to "Saida - Data/Hora",
        "exit_hourmeter" to "Saida - Horimetro",
        "exit_odometer" to "Saida - Km",
        "start_datetime" to "Data prevista para inicio",
        "expected_release_datetime" to "Data prevista de liberacao",
        "expected_hours" to "Horas previstas",
        "branch_code" to "Filial da O.S.",
        "department_code" to "Departamento",
        "observations" to "Observacao"
    )

    private val serviceDetailLabels = listOf(
        "_local_type" to "Tipo",
        "order_number" to "Ordem de Servico",
        "vehicle_code" to "Veiculo",
        "plate" to "Placa",
        "service_code" to "Servico",
        "resource_code" to "Recurso humano",
        "spent_time" to "Tempo gasto",
        "hourly_value" to "Valor hora"
    )

    private fun checksDetail(payload: JSONObject): String {
        val labels = listOf(
            "investment" to "Investimento",
            "accident" to "Acidente",
            "roadside_assistance" to "Socorro",
            "return_service" to "Retorno",
            "scheduled" to "Programada"
        )
        return labels.filter { (key, _) -> payload.optBoolean(key, false) }
            .joinToString(", ") { (_, label) -> label }
    }
}

data class LocalOrder(
    val id: Long,
    val payload: String,
    val status: String = "PENDING",
    val error: String? = null,
    val createdAt: Long = 0L,
    val orderNumber: String? = null
)

enum class FieldFormat {
    TEXT,
    DATETIME,
    DECIMAL,
    INTEGER,
    KM,
    TIME
}

data class ApiResponse(val status: Int, val body: String) {
    fun asJsonOrThrow(endpoint: String): JSONObject {
        val trimmed = body.trim()
        if (!trimmed.startsWith("{")) {
            throw IllegalStateException("API retornou HTTP $status sem JSON em $endpoint: ${trimmed.take(300)}")
        }
        return JSONObject(trimmed)
    }
}

class OrderStore(context: Context) : SQLiteOpenHelper(context, "orders.db", null, 1) {
    override fun onCreate(db: SQLiteDatabase) {
        db.execSQL(
            """
            CREATE TABLE orders (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                payload TEXT NOT NULL,
                status TEXT NOT NULL,
                error TEXT,
                order_number TEXT,
                created_at INTEGER NOT NULL
            )
            """.trimIndent()
        )
    }

    override fun onUpgrade(db: SQLiteDatabase, oldVersion: Int, newVersion: Int) = Unit

    fun insert(payload: String): Long = writableDatabase.insert("orders", null, ContentValues().apply {
        put("payload", payload)
        put("status", "PENDING")
        put("created_at", System.currentTimeMillis())
    })

    fun unsent(): List<LocalOrder> {
        val cursor = readableDatabase.rawQuery(
            "SELECT id, payload, status, error, created_at, order_number FROM orders WHERE status IN ('PENDING', 'FAILED') ORDER BY id",
            null
        )
        return readOrders(cursor)
    }

    fun all(): List<LocalOrder> {
        val cursor = readableDatabase.rawQuery(
            "SELECT id, payload, status, error, created_at, order_number FROM orders ORDER BY id DESC",
            null
        )
        return readOrders(cursor)
    }

    fun servicesForOrder(orderNumber: String): List<LocalOrder> =
        all().filter { order ->
            runCatching {
                val payload = JSONObject(order.payload)
                payload.optString("_local_type", "ORDER") == "SERVICE" &&
                    payload.optString("order_number") == orderNumber
            }.getOrDefault(false)
        }

    private fun readOrders(cursor: android.database.Cursor): List<LocalOrder> {
        val items = mutableListOf<LocalOrder>()
        cursor.use {
            while (it.moveToNext()) {
                items.add(
                    LocalOrder(
                        id = it.getLong(0),
                        payload = it.getString(1),
                        status = it.getString(2),
                        error = it.getString(3),
                        createdAt = it.getLong(4),
                        orderNumber = it.getString(5)
                    )
                )
            }
        }
        return items
    }

    fun find(id: Long): LocalOrder? {
        val cursor = readableDatabase.rawQuery(
            "SELECT id, payload, status, error, created_at, order_number FROM orders WHERE id=?",
            arrayOf(id.toString())
        )
        cursor.use {
            if (!it.moveToFirst()) return null
            return LocalOrder(
                id = it.getLong(0),
                payload = it.getString(1),
                status = it.getString(2),
                error = it.getString(3),
                createdAt = it.getLong(4),
                orderNumber = it.getString(5)
            )
        }
    }

    fun countUnsent(): Int {
        val cursor = readableDatabase.rawQuery("SELECT COUNT(*) FROM orders WHERE status IN ('PENDING', 'FAILED')", null)
        cursor.use { return if (it.moveToFirst()) it.getInt(0) else 0 }
    }

    fun markSynced(id: Long, orderNumber: String) = update(id, "SYNCED", null, orderNumber)
    fun markFailed(id: Long, error: String) = update(id, "FAILED", error, null)
    fun markPending(id: Long, error: String) = update(id, "PENDING", error, null)

    private fun update(id: Long, status: String, error: String?, orderNumber: String?) {
        writableDatabase.update("orders", ContentValues().apply {
            put("status", status)
            put("error", error)
            put("order_number", orderNumber)
        }, "id=?", arrayOf(id.toString()))
    }
}
