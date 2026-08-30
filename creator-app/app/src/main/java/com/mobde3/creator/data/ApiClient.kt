package com.mobde3.creator.data

import com.mobde3.creator.BuildConfig
import org.json.JSONArray
import org.json.JSONObject
import java.io.OutputStreamWriter
import java.net.HttpURLConnection
import java.net.URL

/**
 * عميل خادم المنصة.
 *
 * لا يمر بهذا العميل أي توكن من TikTok إطلاقًا: التوكنات تبقى على الخادم
 * مشفّرة، والجهاز لا يحمل إلا رمز جلسته الخاص.
 */
class ApiClient(private val session: SessionStore) {

    class ApiException(val code: String, message: String, val status: Int) : Exception(message)

    private val base = BuildConfig.API_BASE_URL.trimEnd('/') + "/api/v1"

    // --- المصادقة ---------------------------------------------------------

    /** تبادل كود Login Kit. يعيد رمزًا تمهيديًا أو جلسة كاملة. */
    fun exchangeTikTokCode(code: String, codeVerifier: String, deviceId: String): JSONObject =
        post(
            "/auth/tiktok/exchange",
            JSONObject()
                .put("code", code)
                .put("code_verifier", codeVerifier)
                .put("device_id", deviceId),
            auth = null,
        )

    /** بلا رمز: يطلب إرسال رمز تحقق. مع رمز: يؤكده ويصدر الجلسة. */
    fun verifyPhone(
        preauthToken: String,
        phone: String,
        code: String? = null,
        deviceId: String? = null,
    ): JSONObject {
        val body = JSONObject().put("phone", phone)
        code?.let { body.put("code", it) }
        deviceId?.let { body.put("device_id", it) }
        return post("/auth/phone/verify", body, auth = "Bearer $preauthToken")
    }

    fun refresh(refreshToken: String): JSONObject =
        post("/auth/refresh", JSONObject().put("refresh", refreshToken), auth = null)

    // --- المبدع -----------------------------------------------------------

    fun me(): JSONObject = get("/creators/me")

    fun recordConsent(termsVersion: String, contentHash: String, fingerprint: String): JSONObject =
        post(
            "/creators/me/consent",
            JSONObject()
                .put("terms_version", termsVersion)
                .put("content_hash", contentHash)
                .put("device_fingerprint", fingerprint)
                .put("language", "ar"),
        )

    fun registerDevice(
        deviceId: String,
        integrityToken: String,
        fcmToken: String,
        permissions: Map<String, Boolean>,
    ): JSONObject = post(
        "/creators/me/devices",
        JSONObject()
            .put("device_id", deviceId)
            .put("integrity_token", integrityToken)
            .put("fcm_token", fcmToken)
            .put("model", android.os.Build.MODEL)
            .put("os_version", android.os.Build.VERSION.RELEASE)
            .put("app_version", BuildConfig.VERSION_NAME)
            .put("permissions", JSONObject(permissions as Map<*, *>)),
    )

    // --- التجهيز ----------------------------------------------------------

    /** بيانات حساب الاستلام: تُطلب عند التعبئة فقط ولا تُخزَّن على الجهاز. */
    fun autofillDataset(): JSONObject = get("/setup/autofill-dataset")

    fun completeSetup(): JSONObject = post("/setup/complete", JSONObject())

    // --- السحب ------------------------------------------------------------

    /** ضغطة «سحب»: بلا مبلغ ولا أي حقل. */
    fun createWithdrawal(): JSONObject = post("/withdrawals", JSONObject())

    fun withdrawal(code: String): JSONObject = get("/withdrawals/$code")

    /** إشارة ملتقطة من إشعار TikTok. */
    fun sendSignal(
        kind: String,
        packageName: String,
        signatureOk: Boolean,
        amount: String? = null,
        currency: String? = null,
        txnId: String? = null,
        code: String? = null,
        raw: String = "",
        source: String = "notification",
        transferId: String? = null,
    ): JSONObject {
        val payload = JSONObject().put("text", raw)
        transferId?.let { payload.put("transfer_id", it) }

        val body = JSONObject()
            .put("source", source)
            .put("kind", kind)
            .put("package_name", packageName)
            .put("package_sig_ok", signatureOk)
            .put("payload", payload)
        amount?.let { body.put("amount", it) }
        currency?.let { body.put("currency", it) }
        txnId?.let { body.put("txn_id", it) }
        code?.let { body.put("code", it) }
        return post("/withdrawals/signals", body)
    }

    // --- النقل ------------------------------------------------------------

    private fun get(path: String): JSONObject = request("GET", path, null, session.authHeader())

    private fun post(path: String, body: JSONObject, auth: String? = session.authHeader()) =
        request("POST", path, body, auth)

    private fun request(
        method: String,
        path: String,
        body: JSONObject?,
        auth: String?,
    ): JSONObject {
        val connection = (URL(base + path).openConnection() as HttpURLConnection).apply {
            requestMethod = method
            connectTimeout = 20_000
            readTimeout = 20_000
            setRequestProperty("Content-Type", "application/json")
            setRequestProperty("Accept-Language", "ar")
            auth?.let { setRequestProperty("Authorization", it) }
            if (body != null) doOutput = true
        }

        try {
            if (body != null) {
                OutputStreamWriter(connection.outputStream, Charsets.UTF_8)
                    .use { it.write(body.toString()) }
            }
            val status = connection.responseCode
            val stream = if (status in 200..299) connection.inputStream else connection.errorStream
            val text = stream?.bufferedReader(Charsets.UTF_8)?.use { it.readText() }.orEmpty()

            if (status in 200..299) {
                return if (text.isBlank()) JSONObject() else parse(text)
            }
            val parsed = runCatching { JSONObject(text) }.getOrNull()
            val error = parsed?.optJSONObject("error")
            throw ApiException(
                error?.optString("code") ?: "http_error",
                error?.optString("message") ?: "تعذّر الاتصال بالخادم",
                status,
            )
        } finally {
            connection.disconnect()
        }
    }

    /** بعض المسارات تعيد مصفوفة؛ تُغلَّف لتوحيد النوع. */
    private fun parse(text: String): JSONObject =
        if (text.trimStart().startsWith("[")) {
            JSONObject().put("results", JSONArray(text))
        } else {
            JSONObject(text)
        }
}
