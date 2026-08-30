package com.mobde3.creator.auth

import android.content.Context
import com.google.android.play.core.integrity.IntegrityManagerFactory
import com.google.android.play.core.integrity.IntegrityTokenRequest
import com.google.android.gms.tasks.Tasks
import java.util.concurrent.TimeUnit

/**
 * سلامة الجهاز عبر Play Integrity.
 *
 * الرمز يُطلب هنا ويُرسل إلى الخادم؛ **التحقق منه يجري على الخادم وحده**، لأن
 * أي فحص على الجهاز يستطيع مهاجمٌ تعطيله. الخادم يرفض السحب من جهاز غير موثوق.
 *
 * فشل الحصول على الرمز يعيد نصًا فارغًا، فيُعامله الخادم كجهاز غير معروف —
 * أي يفشل مغلقًا لا مفتوحًا.
 */
object DeviceIntegrity {

    /** يطلب رمز سلامة. عملية شبكية: تُستدعى خارج الخيط الرئيسي. */
    fun requestToken(context: Context, nonce: String): String = runCatching {
        val manager = IntegrityManagerFactory.create(context)
        val task = manager.requestIntegrityToken(
            IntegrityTokenRequest.builder().setNonce(nonce).build()
        )
        Tasks.await(task, 20, TimeUnit.SECONDS).token()
    }.getOrDefault("")

    /** قيمة عشوائية تربط الرمز بهذا الطلب تحديدًا. */
    fun newNonce(): String {
        val bytes = ByteArray(32)
        java.security.SecureRandom().nextBytes(bytes)
        return android.util.Base64.encodeToString(
            bytes,
            android.util.Base64.URL_SAFE or android.util.Base64.NO_WRAP or
                android.util.Base64.NO_PADDING,
        )
    }
}
