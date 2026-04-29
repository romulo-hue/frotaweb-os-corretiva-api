package br.com.frotaweb.oscorretiva

import android.app.AlertDialog
import android.app.Activity
import android.content.ContentValues
import android.content.Context
import android.database.sqlite.SQLiteDatabase
import android.database.sqlite.SQLiteOpenHelper
import android.graphics.Typeface
import android.net.ConnectivityManager
import android.net.NetworkCapabilities
import android.os.Bundle
import android.text.Editable
import android.text.InputFilter
import android.text.InputType
import android.text.TextWatcher
import android.view.View
import android.widget.Button
import android.widget.CheckBox
import android.widget.EditText
import android.widget.LinearLayout
import android.widget.ScrollView
import android.widget.TextView
import org.json.JSONObject
import java.io.BufferedReader
import java.io.OutputStreamWriter
import java.net.HttpURLConnection
import java.net.URL

class MainActivity : Activity() {
    private lateinit var store: OrderStore
    private val prefs by lazy { getSharedPreferences("frotaweb-login", MODE_PRIVATE) }
    private var currentPassword: String = ""

    private lateinit var apiUrl: EditText
    private lateinit var empresa: EditText
    private lateinit var filial: EditText
    private lateinit var usuario: EditText
    private lateinit var senha: EditText

    private val orderInputs = linkedMapOf<String, EditText>()
    private val orderFormats = linkedMapOf<String, FieldFormat>()
    private val checks = linkedMapOf<String, CheckBox>()

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        store = OrderStore(this)
        showLoginScreen()
    }

    private fun showLoginScreen() {
        val root = page()
        root.addView(title("Login FrotaWeb"))
        root.addView(note("Informe as credenciais do mecanico. A senha fica somente na memoria enquanto o app esta aberto."))

        apiUrl = input("URL da API", prefs.getString("apiUrl", "https://SEU-SERVICO.onrender.com") ?: "")
        empresa = input("Empresa *", prefs.getString("empresa", "1") ?: "1")
        filial = input("Filial *", prefs.getString("filial", "1") ?: "1")
        usuario = input("Usuario *", prefs.getString("usuario", "") ?: "")
        senha = input("Senha *", "", InputType.TYPE_CLASS_TEXT or InputType.TYPE_TEXT_VARIATION_PASSWORD)

        listOf(apiUrl, empresa, filial, usuario, senha).forEach(root::addView)

        val enter = button("Continuar")
        enter.setOnClickListener {
            if (required(apiUrl, empresa, filial, usuario, senha)) {
                currentPassword = senha.text.toString()
                prefs.edit()
                    .putString("apiUrl", apiUrl.text.toString().trim().trimEnd('/'))
                    .putString("empresa", empresa.text.toString().trim())
                    .putString("filial", filial.text.toString().trim())
                    .putString("usuario", usuario.text.toString().trim())
                    .apply()
                showOrderScreen()
            }
        }
        root.addView(enter)

        val sync = button("Sincronizar pendentes")
        sync.setOnClickListener {
            if (required(apiUrl, empresa, filial, usuario, senha)) {
                currentPassword = senha.text.toString()
                syncPending()
            }
        }
        root.addView(sync)
        root.addView(note("Pendentes locais: ${store.countPending()}"))
        setContentView(scroll(root))
    }

    private fun showOrderScreen() {
        val root = page()
        root.addView(title("Nova O.S. corretiva"))
        root.addView(note("Campos com * sao obrigatorios. O app salva offline se estiver sem internet."))

        addOrderInput(root, "vehicle_code", "Veiculo *", "Ex.: 1682", FieldFormat.INTEGER)
        addOrderInput(root, "plate", "Placa", "Ex.: RKH1F96")
        addOrderInput(root, "defect_description", "Reclamacao livre", "Descreva a falha")
        addOrderInput(root, "opening_datetime", "Entrada - Data/Hora *", "dd/MM/aaaa HH:mm:ss", FieldFormat.DATETIME)
        addOrderInput(root, "entry_hourmeter", "Entrada - Horimetro *", "0.00", FieldFormat.DECIMAL)
        addOrderInput(root, "odometer", "Entrada - Km *", "103.345", FieldFormat.KM)
        addOrderInput(root, "exit_datetime", "Saida - Data/Hora *", "dd/MM/aaaa HH:mm:ss", FieldFormat.DATETIME)
        addOrderInput(root, "exit_hourmeter", "Saida - Horimetro *", "0.00", FieldFormat.DECIMAL)
        addOrderInput(root, "exit_odometer", "Saida - Km *", "103.345", FieldFormat.KM)
        addOrderInput(root, "start_datetime", "Data prevista para inicio *", "dd/MM/aaaa HH:mm:ss", FieldFormat.DATETIME)
        addOrderInput(root, "expected_release_datetime", "Data prevista de liberacao *", "dd/MM/aaaa HH:mm:ss", FieldFormat.DATETIME)
        addOrderInput(root, "expected_hours", "Horas previstas", "0.00", FieldFormat.DECIMAL)
        addOrderInput(root, "actual_hours", "Horas realizadas", "0.00", FieldFormat.DECIMAL)
        addOrderInput(root, "branch_code", "Filial da OS", "Ex.: 3", FieldFormat.INTEGER)
        addOrderInput(root, "department_code", "Departamento", "Ex.: 420112", FieldFormat.INTEGER)
        addOrderInput(root, "occurrence_number", "Ocorrencia", "0", FieldFormat.INTEGER)
        addOrderInput(root, "driver_code", "Motorista", "0", FieldFormat.INTEGER)
        addOrderInput(root, "surcharge_value", "Valor acrescimo", "0", FieldFormat.DECIMAL)
        addOrderInput(root, "return_order_number", "O.S retorno", "0", FieldFormat.INTEGER)
        addOrderInput(root, "observations", "Observacao (max 50)", "")

        root.addView(subtitle("Marcadores opcionais"))
        addCheck(root, "investment", "Investimento")
        addCheck(root, "accident", "Acidente")
        addCheck(root, "roadside_assistance", "Socorro")
        addCheck(root, "return_service", "Retorno")
        addCheck(root, "scheduled", "Programada")

        val save = button("Salvar e enviar")
        save.setOnClickListener { saveAndSend() }
        root.addView(save)

        val back = button("Voltar ao login")
        back.setOnClickListener { showLoginScreen() }
        root.addView(back)
        root.addView(note("Pendentes locais: ${store.countPending()}"))
        setContentView(scroll(root))
    }

    private fun saveAndSend() {
        val requiredNames = listOf(
            "vehicle_code", "opening_datetime", "entry_hourmeter",
            "odometer", "exit_datetime", "exit_hourmeter", "exit_odometer",
            "start_datetime", "expected_release_datetime"
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

        val payload = buildOrderPayload()
        val id = store.insert(payload.toString())
        if (!isOnline()) {
            showMessage("Salvo offline", "Sem internet. A O.S. ficou pendente para sincronizacao.")
            showOrderScreen()
            return
        }
        sendOrder(id, payload)
    }

    private fun syncPending() {
        if (!isOnline()) {
            showMessage("Sem internet", "Nao foi possivel sincronizar agora.")
            return
        }
        val pending = store.pending()
        if (pending.isEmpty()) {
            showMessage("Sincronizacao", "Nao ha O.S. pendente.")
            return
        }
        pending.forEach { sendOrder(it.id, JSONObject(it.payload)) }
    }

    private fun sendOrder(id: Long, payload: JSONObject) {
        Thread {
            try {
                val response = postJson(
                    "${apiUrl.text.toString().trim().trimEnd('/')}/os-corretiva?simulacao=false",
                    withCredentials(payload)
                )
                val body = response.asJsonOrThrow()
                val created = body.optBoolean("created", false)
                val message = body.optString("message", body.optString("detail", response.body))
                runOnUiThread {
                    if (created) {
                        store.markSynced(id, body.optString("order_number"))
                        showMessage("O.S. enviada", "Numero: ${body.optString("order_number")}\n$message")
                        showOrderScreen()
                    } else {
                        store.markFailed(id, message)
                        showMessage("Erro do FrotaWeb", message)
                    }
                }
            } catch (ex: Exception) {
                runOnUiThread {
                    store.markPending(id, ex.message ?: "Falha de rede")
                    showMessage("Salvo offline", "Nao foi possivel enviar agora. A O.S. ficou pendente.\n${ex.message}")
                }
            }
        }.start()
    }

    private fun buildOrderPayload(): JSONObject {
        val json = JSONObject()
        orderInputs.forEach { (name, edit) ->
            val value = payloadValue(name, edit.text.toString().trim(), orderFormats[name] ?: FieldFormat.TEXT)
            if (value.isNotEmpty()) json.put(name, value)
        }
        checks.forEach { (name, check) ->
            if (check.isChecked) json.put(name, true)
        }
        return json
    }

    private fun withCredentials(orderPayload: JSONObject): JSONObject {
        val json = JSONObject(orderPayload.toString())
        json.put("credentials", JSONObject().apply {
            put("empresa", empresa.text.toString().trim())
            put("filial", filial.text.toString().trim())
            put("usuario", usuario.text.toString().trim())
            put("senha", currentPassword)
        })
        return json
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

    private fun addOrderInput(root: LinearLayout, name: String, label: String, hint: String, format: FieldFormat = FieldFormat.TEXT) {
        val edit = input(label, "", inputTypeFor(format), hint)
        applyFormat(edit, format)
        orderInputs[name] = edit
        orderFormats[name] = format
        root.addView(edit)
    }

    private fun inputTypeFor(format: FieldFormat): Int = when (format) {
        FieldFormat.DATETIME, FieldFormat.INTEGER, FieldFormat.KM -> InputType.TYPE_CLASS_NUMBER
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

    private fun invalidFormats(): List<String> {
        return orderInputs.mapNotNull { (name, edit) ->
            val value = edit.text.toString().trim()
            if (value.isBlank()) return@mapNotNull null
            val valid = when (orderFormats[name] ?: FieldFormat.TEXT) {
                FieldFormat.DATETIME -> value.length == 19
                FieldFormat.DECIMAL -> value.replace(',', '.').matches(Regex("""\d+(\.\d{1,2})?"""))
                FieldFormat.INTEGER -> value.digitsOnly() == value
                FieldFormat.KM -> value.digitsOnly().isNotBlank()
                FieldFormat.TEXT -> true
            }
            if (valid) null else edit.hint.toString().substringBefore(" - ")
        }
    }

    private fun payloadValue(name: String, value: String, format: FieldFormat): String = when (format) {
        FieldFormat.KM -> value.digitsOnly()
        FieldFormat.DECIMAL -> value.replace(',', '.')
        else -> value
    }

    private fun String.digitsOnly(): String = filter { it.isDigit() }

    private fun addCheck(root: LinearLayout, name: String, label: String) {
        val check = CheckBox(this).apply { text = label; textSize = 16f }
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
        setPadding(28, 28, 28, 28)
    }

    private fun scroll(child: View) = ScrollView(this).apply { addView(child) }

    private fun title(text: String) = TextView(this).apply {
        this.text = text
        textSize = 24f
        setTypeface(typeface, Typeface.BOLD)
    }

    private fun subtitle(text: String) = TextView(this).apply {
        this.text = text
        textSize = 18f
        setTypeface(typeface, Typeface.BOLD)
        setPadding(0, 18, 0, 8)
    }

    private fun note(text: String) = TextView(this).apply {
        this.text = text
        textSize = 14f
        setPadding(0, 8, 0, 16)
    }

    private fun input(label: String, value: String, type: Int = InputType.TYPE_CLASS_TEXT, hint: String = "") =
        EditText(this).apply {
            this.hint = if (hint.isBlank()) label else "$label - $hint"
            setText(value)
            inputType = type
            textSize = 16f
            setSingleLine(!label.contains("Reclamacao"))
        }

    private fun button(text: String) = Button(this).apply {
        this.text = text
        textSize = 16f
        setPadding(0, 10, 0, 10)
    }

    private fun showMessage(title: String, message: String) {
        AlertDialog.Builder(this).setTitle(title).setMessage(message).setPositiveButton("OK", null).show()
    }
}

data class LocalOrder(val id: Long, val payload: String)

enum class FieldFormat {
    TEXT,
    DATETIME,
    DECIMAL,
    INTEGER,
    KM
}

data class ApiResponse(val status: Int, val body: String) {
    fun asJsonOrThrow(): JSONObject {
        val trimmed = body.trim()
        if (!trimmed.startsWith("{")) {
            throw IllegalStateException("API retornou HTTP $status sem JSON: ${trimmed.take(300)}")
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

    fun pending(): List<LocalOrder> {
        val cursor = readableDatabase.rawQuery("SELECT id, payload FROM orders WHERE status='PENDING' ORDER BY id", null)
        val items = mutableListOf<LocalOrder>()
        cursor.use {
            while (it.moveToNext()) items.add(LocalOrder(it.getLong(0), it.getString(1)))
        }
        return items
    }

    fun countPending(): Int {
        val cursor = readableDatabase.rawQuery("SELECT COUNT(*) FROM orders WHERE status='PENDING'", null)
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
