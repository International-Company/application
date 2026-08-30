package com.mobde3.creator.notifications

import android.content.Context
import com.mobde3.creator.BuildConfig
import org.json.JSONArray
import org.json.JSONObject
import java.text.SimpleDateFormat
import java.util.Date
import java.util.Locale

/**
 * سجل رصد إشعارات TikTok — **في نسخة التطوير وحدها**.
 *
 * الغرض منه واحد: التقاط **النص الحرفي** لإشعار TikTok عند طلب السحب وإتمامه
 * ورفضه، وهو ما لا يمكن معرفته إلا على جهاز حقيقي (سؤال §16 في وثيقة المشروع).
 * لا يُخمَّن نص ولا يُخترع؛ يُرصد ثم يُبنى عليه المحلّل.
 *
 * لا يعمل في نسخة الإنتاج إطلاقًا، ولا يرصد إلا حزم TikTok.
 */
object ProbeLog {

    private const val PREFS = "probe"
    private const val KEY = "captures"
    private const val LIMIT = 40

    private val stamp = SimpleDateFormat("yyyy-MM-dd HH:mm:ss", Locale.US)

    data class Capture(
        val packageName: String,
        val at: String,
        val text: String,
        val parsedKind: String,
        val signatureOk: Boolean,
    )

    fun record(context: Context, packageName: String, text: String, parsedKind: String, signatureOk: Boolean) {
        if (!BuildConfig.DEBUG) return

        val prefs = context.getSharedPreferences(PREFS, Context.MODE_PRIVATE)
        val existing = runCatching { JSONArray(prefs.getString(KEY, "[]")) }.getOrDefault(JSONArray())

        val entry = JSONObject()
            .put("package", packageName)
            .put("at", stamp.format(Date()))
            .put("text", text)
            .put("kind", parsedKind)
            .put("sig", signatureOk)

        val trimmed = JSONArray()
        trimmed.put(entry)
        for (index in 0 until minOf(existing.length(), LIMIT - 1)) {
            trimmed.put(existing.get(index))
        }
        prefs.edit().putString(KEY, trimmed.toString()).apply()
    }

    fun all(context: Context): List<Capture> {
        if (!BuildConfig.DEBUG) return emptyList()
        val prefs = context.getSharedPreferences(PREFS, Context.MODE_PRIVATE)
        val array = runCatching { JSONArray(prefs.getString(KEY, "[]")) }.getOrDefault(JSONArray())
        return buildList {
            for (index in 0 until array.length()) {
                val item = array.optJSONObject(index) ?: continue
                add(
                    Capture(
                        packageName = item.optString("package"),
                        at = item.optString("at"),
                        text = item.optString("text"),
                        parsedKind = item.optString("kind").ifBlank { "—" },
                        signatureOk = item.optBoolean("sig"),
                    )
                )
            }
        }
    }

    fun clear(context: Context) {
        context.getSharedPreferences(PREFS, Context.MODE_PRIVATE).edit().remove(KEY).apply()
    }

    /** نص جاهز للنسخ والإرسال، يجمع كل ما رُصد. */
    fun asReport(context: Context, signatures: List<String>): String = buildString {
        appendLine("== بصمات توقيع TikTok ==")
        if (signatures.isEmpty()) appendLine("لم تُرصد") else signatures.forEach { appendLine(it) }
        appendLine()
        appendLine("== إشعارات مرصودة ==")
        all(context).forEach {
            appendLine("[${it.at}] ${it.packageName} (توقيع: ${it.signatureOk})")
            appendLine("النمط المستنتج: ${it.parsedKind}")
            appendLine(it.text)
            appendLine("---")
        }
    }
}
