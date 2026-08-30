package com.mobde3.creator.notifications

import android.content.Context
import android.content.pm.PackageManager
import android.os.Build
import com.mobde3.creator.BuildConfig
import java.security.MessageDigest

/**
 * التحقق من أن الإشعار جاء من TikTok الحقيقي.
 *
 * اسم الحزمة وحده لا يكفي: تطبيق مزيّف يستطيع محاكاة نص الإشعار، لكنه لا
 * يستطيع تزوير بصمة شهادة توقيع TikTok. لذلك يُقارَن التوقيع نفسه.
 *
 * **يفشل مغلقًا**: إن لم تُضبط البصمات المعتمدة، يُعتبر كل إشعار غير موثوق،
 * فيُرسل إلى الخادم موسومًا بذلك ولا يُصدَّق هناك.
 */
object PackageVerifier {

    val TIKTOK_PACKAGES = setOf(
        "com.zhiliaoapp.musically",
        "com.ss.android.ugc.trill",
    )

    /** بصمات SHA-256 المعتمدة، تُضبط وقت البناء بعد رصدها على جهاز حقيقي. */
    private val trustedSignatures: Set<String> by lazy {
        BuildConfig.TIKTOK_SIGNATURES
            .split(',')
            .map { it.trim().uppercase().replace(":", "") }
            .filter { it.isNotEmpty() }
            .toSet()
    }

    fun isTikTokPackage(packageName: String): Boolean = packageName in TIKTOK_PACKAGES

    /**
     * هل الحزمة موقّعة بشهادة معتمدة؟
     *
     * @return false عند أي شك: حزمة غير معروفة، أو بصمات غير مضبوطة، أو خطأ.
     */
    fun isSignatureTrusted(context: Context, packageName: String): Boolean {
        if (!isTikTokPackage(packageName)) return false
        if (trustedSignatures.isEmpty()) return false

        val digests = signatureDigests(context, packageName)
        return digests.any { it in trustedSignatures }
    }

    /** بصمات توقيع حزمة — تُستعمل أيضًا لرصد البصمة الحقيقية أول مرة. */
    fun signatureDigests(context: Context, packageName: String): List<String> = runCatching {
        val manager = context.packageManager
        val signatures = if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.P) {
            val info = manager.getPackageInfo(
                packageName,
                PackageManager.GET_SIGNING_CERTIFICATES,
            )
            val signing = info.signingInfo ?: return@runCatching emptyList()
            if (signing.hasMultipleSigners()) {
                signing.apkContentsSigners
            } else {
                signing.signingCertificateHistory
            }
        } else {
            @Suppress("DEPRECATION")
            manager.getPackageInfo(packageName, PackageManager.GET_SIGNATURES).signatures
        }

        signatures.orEmpty().map { signature ->
            MessageDigest.getInstance("SHA-256")
                .digest(signature.toByteArray())
                .joinToString("") { "%02X".format(it) }
        }
    }.getOrElse { emptyList() }
}
