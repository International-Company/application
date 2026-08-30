package com.mobde3.creator.data

import android.content.Context
import android.content.SharedPreferences
import androidx.security.crypto.EncryptedSharedPreferences
import androidx.security.crypto.MasterKey
import java.util.UUID

/**
 * تخزين جلسة المبدع.
 *
 * رمز الوصول قصير (ربع ساعة) ورمز التجديد مربوط بهذا الجهاز وحده، فسرقة نسخة
 * من التخزين لا تفتح الحساب على جهاز آخر. ويُخزَّن كلاهما مشفّرًا.
 */
class SessionStore(context: Context) {

    private val prefs: SharedPreferences = runCatching {
        EncryptedSharedPreferences.create(
            context,
            "session",
            MasterKey.Builder(context).setKeyScheme(MasterKey.KeyScheme.AES256_GCM).build(),
            EncryptedSharedPreferences.PrefKeyEncryptionScheme.AES256_SIV,
            EncryptedSharedPreferences.PrefValueEncryptionScheme.AES256_GCM,
        )
    }.getOrElse {
        // أجهزة قديمة قد يفشل فيها مخزن المفاتيح: لا يُمنع الاستعمال
        context.getSharedPreferences("session", Context.MODE_PRIVATE)
    }

    var accessToken: String
        get() = prefs.getString(KEY_ACCESS, "").orEmpty()
        set(value) = prefs.edit().putString(KEY_ACCESS, value).apply()

    var refreshToken: String
        get() = prefs.getString(KEY_REFRESH, "").orEmpty()
        set(value) = prefs.edit().putString(KEY_REFRESH, value).apply()

    /** معرّف ثابت للجهاز يُولَّد مرة واحدة محليًا. */
    val deviceId: String
        get() {
            val existing = prefs.getString(KEY_DEVICE, "").orEmpty()
            if (existing.isNotBlank()) return existing
            val generated = UUID.randomUUID().toString()
            prefs.edit().putString(KEY_DEVICE, generated).apply()
            return generated
        }

    var setupCompleted: Boolean
        get() = prefs.getBoolean(KEY_SETUP, false)
        set(value) = prefs.edit().putBoolean(KEY_SETUP, value).apply()

    /** رمز آخر طلب سحب مفتوح، ليربط الإشعارات الملتقطة به. */
    var openWithdrawalCode: String
        get() = prefs.getString(KEY_OPEN_CODE, "").orEmpty()
        set(value) = prefs.edit().putString(KEY_OPEN_CODE, value).apply()

    val isSignedIn: Boolean
        get() = accessToken.isNotBlank()

    fun authHeader(): String? = accessToken.takeIf { it.isNotBlank() }?.let { "Bearer $it" }

    fun save(session: org.json.JSONObject) {
        accessToken = session.optString("access")
        refreshToken = session.optString("refresh")
    }

    fun clear() {
        prefs.edit()
            .remove(KEY_ACCESS)
            .remove(KEY_REFRESH)
            .remove(KEY_OPEN_CODE)
            .apply()
    }

    private companion object {
        const val KEY_ACCESS = "access"
        const val KEY_REFRESH = "refresh"
        const val KEY_DEVICE = "device_id"
        const val KEY_SETUP = "setup_completed"
        const val KEY_OPEN_CODE = "open_code"
    }
}
