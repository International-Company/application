package com.mobde3.collector

import android.content.Context
import android.content.SharedPreferences

/**
 * إعدادات الجهاز.
 *
 * السر لا يُكتب في الكود ولا يُرفع في المستودع: يُدخَل مرة واحدة على الجهاز نفسه.
 */
class Settings(context: Context) {

    private val prefs: SharedPreferences =
        context.getSharedPreferences("collector", Context.MODE_PRIVATE)

    var baseUrl: String
        get() = prefs.getString(KEY_BASE_URL, "").orEmpty()
        set(value) = prefs.edit().putString(KEY_BASE_URL, value.trimEnd('/')).apply()

    var collectorId: String
        get() = prefs.getString(KEY_COLLECTOR_ID, "").orEmpty()
        set(value) = prefs.edit().putString(KEY_COLLECTOR_ID, value.trim()).apply()

    var secret: String
        get() = prefs.getString(KEY_SECRET, "").orEmpty()
        set(value) = prefs.edit().putString(KEY_SECRET, value.trim()).apply()

    /** معرّف حساب الاستلام الذي يخص هذا الهاتف. */
    var accountIdentifier: String
        get() = prefs.getString(KEY_ACCOUNT, "").orEmpty()
        set(value) = prefs.edit().putString(KEY_ACCOUNT, value.trim()).apply()

    /** أسماء مرسِلي رسائل البنك أو حزمه المقبولة، مفصولة بفاصلة. */
    var allowedSenders: String
        get() = prefs.getString(KEY_SENDERS, "").orEmpty()
        set(value) = prefs.edit().putString(KEY_SENDERS, value.trim()).apply()

    val isConfigured: Boolean
        get() = baseUrl.isNotBlank() &&
            collectorId.isNotBlank() &&
            secret.isNotBlank() &&
            accountIdentifier.isNotBlank()

    fun isSenderAllowed(sender: String): Boolean {
        val allowed = allowedSenders.split(',').map { it.trim() }.filter { it.isNotEmpty() }
        if (allowed.isEmpty()) return false
        return allowed.any { sender.equals(it, ignoreCase = true) }
    }

    fun client(): ApiClient = ApiClient(baseUrl, collectorId, secret)

    private companion object {
        const val KEY_BASE_URL = "base_url"
        const val KEY_COLLECTOR_ID = "collector_id"
        const val KEY_SECRET = "secret"
        const val KEY_ACCOUNT = "account_identifier"
        const val KEY_SENDERS = "allowed_senders"
    }
}
