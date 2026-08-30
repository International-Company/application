package com.mobde3.creator.auth

import android.app.Activity
import android.util.Base64
import java.security.MessageDigest
import java.security.SecureRandom

/**
 * ربط حساب TikTok.
 *
 * ⚠️ الـ SDK غير مربوط بعد: يتطلب اعتماد التطبيق لدى TikTok وتسجيل بصمة توقيعه.
 * لذلك يبقى خلف واجهة كما تنص قواعد المشروع، ولا يُخترع له أي استدعاء.
 * حين يُعتمد التطبيق يُضاف [SdkTikTokLogin] بتنفيذ واحد لا يمس بقية التطبيق.
 *
 * الثابت الوحيد هنا هو PKCE، وهو معيار عام لا يخص TikTok:
 * يولّد التطبيق `code_verifier` سرًا، ويرسل `code_challenge` مع طلب الإذن،
 * ثم يرسل الـ verifier إلى خادمنا ليتم به تبادل الكود.
 */
interface TikTokLogin {

    /** نتيجة محاولة الربط. */
    sealed interface Result {
        data class Success(val code: String, val codeVerifier: String) : Result
        data class Failed(val reason: String) : Result
        data object Cancelled : Result
    }

    /** يفتح تطبيق TikTok لطلب الإذن. النتيجة تصل عبر [onResult]. */
    fun authorize(activity: Activity, onResult: (Result) -> Unit)

    /** هل SDK مربوط وجاهز؟ */
    val isAvailable: Boolean
}

/** توليد قيم PKCE — معيار قياسي مستقل عن أي مزوّد. */
object Pkce {

    fun newVerifier(): String {
        val bytes = ByteArray(64)
        SecureRandom().nextBytes(bytes)
        return encode(bytes)
    }

    fun challengeOf(verifier: String): String {
        val digest = MessageDigest.getInstance("SHA-256")
        return encode(digest.digest(verifier.toByteArray(Charsets.US_ASCII)))
    }

    private fun encode(bytes: ByteArray): String =
        Base64.encodeToString(bytes, Base64.URL_SAFE or Base64.NO_PADDING or Base64.NO_WRAP)
}

/**
 * تنفيذ مؤقت يعلن صراحةً أن الربط غير متاح بعد.
 *
 * يفشل فشلًا واضحًا بدل أن يُوهم بنجاح: لا يُقبل في المنصة حساب لم يُربط فعلًا.
 */
class UnavailableTikTokLogin : TikTokLogin {

    override val isAvailable: Boolean = false

    override fun authorize(activity: Activity, onResult: (TikTokLogin.Result) -> Unit) {
        onResult(
            TikTokLogin.Result.Failed(
                "ربط TikTok غير متاح بعد: يلزم اعتماد التطبيق لدى TikTok وتسجيل بصمة توقيعه"
            )
        )
    }
}

/**
 * نقطة الإدخال الوحيدة التي تُستبدل عند اعتماد التطبيق.
 */
object TikTokLoginFactory {
    @Volatile
    var provider: TikTokLogin = UnavailableTikTokLogin()

    fun current(): TikTokLogin = provider
}
