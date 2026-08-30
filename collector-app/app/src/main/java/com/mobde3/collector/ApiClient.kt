package com.mobde3.collector

import android.util.Base64
import org.json.JSONObject
import java.io.OutputStreamWriter
import java.net.HttpURLConnection
import java.net.URL
import javax.crypto.Mac
import javax.crypto.spec.SecretKeySpec

/**
 * عميل الخادم: يوقّع كل طلب بسرّ الجهاز.
 *
 * التوقيع على «الطابع الزمني + نقطة + الجسم» بـ HMAC-SHA256، ويرفض الخادم أي
 * طلب خارج نافذة زمنية ضيقة، فلا تنفع إعادة بث طلب قديم موقّع.
 */
class ApiClient(
    private val baseUrl: String,
    private val collectorId: String,
    private val secret: String,
) {

    data class Result(val success: Boolean, val code: Int, val body: String)

    fun sendIncoming(transfer: IncomingTransfer): Result {
        val payload = JSONObject().apply {
            put("account_identifier", transfer.accountIdentifier)
            put("amount_egp", transfer.amountEgp)
            put("received_at", transfer.receivedAtIso)
            put("bank_ref", transfer.bankRef)
            put("sender_hint", transfer.senderHint)
            put("source", transfer.source)
            put("dedupe_key", transfer.dedupeKey)
            put("raw_payload", JSONObject().apply { put("text", transfer.rawText) })
        }.toString()

        val timestamp = (System.currentTimeMillis() / 1000).toString()
        val signature = sign("$timestamp.$payload")

        val connection = (URL("$baseUrl/api/v1/reconciliation/incoming").openConnection()
            as HttpURLConnection).apply {
            requestMethod = "POST"
            doOutput = true
            connectTimeout = 15_000
            readTimeout = 15_000
            setRequestProperty("Content-Type", "application/json")
            setRequestProperty("X-Collector-Id", collectorId)
            setRequestProperty("X-Timestamp", timestamp)
            setRequestProperty("X-Signature", signature)
        }

        return try {
            OutputStreamWriter(connection.outputStream, Charsets.UTF_8).use { it.write(payload) }
            val code = connection.responseCode
            val stream = if (code in 200..299) connection.inputStream else connection.errorStream
            val body = stream?.bufferedReader(Charsets.UTF_8)?.use { it.readText() } ?: ""
            Result(code in 200..299, code, body)
        } catch (error: Exception) {
            Result(false, 0, error.message ?: "network error")
        } finally {
            connection.disconnect()
        }
    }

    private fun sign(message: String): String {
        val mac = Mac.getInstance("HmacSHA256")
        mac.init(SecretKeySpec(secret.toByteArray(Charsets.UTF_8), "HmacSHA256"))
        val bytes = mac.doFinal(message.toByteArray(Charsets.UTF_8))
        return bytes.joinToString("") { "%02x".format(it) }
    }

    companion object {
        /** بصمة نص الرسالة وزمنها: مفتاح منع التكرار على الخادم. */
        fun dedupeKey(text: String, timestampMillis: Long): String {
            val digest = java.security.MessageDigest.getInstance("SHA-256")
            val raw = digest.digest("$timestampMillis:$text".toByteArray(Charsets.UTF_8))
            return Base64.encodeToString(raw, Base64.NO_WRAP or Base64.URL_SAFE).take(64)
        }
    }
}
