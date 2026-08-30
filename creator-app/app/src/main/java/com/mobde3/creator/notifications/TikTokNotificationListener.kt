package com.mobde3.creator.notifications

import android.service.notification.NotificationListenerService
import android.service.notification.StatusBarNotification
import com.mobde3.creator.data.ApiClient
import com.mobde3.creator.data.SessionStore
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.SupervisorJob
import kotlinx.coroutines.launch

/**
 * التقاط إشعارات TikTok المتعلقة بالسحب.
 *
 * ثلاثة حواجز قبل أن يُرسل أي شيء:
 * ١) اسم الحزمة من حزم TikTok المعروفة.
 * ٢) توقيع الحزمة مطابق لبصمة معتمدة (يفشل مغلقًا إن لم تُضبط).
 * ٣) نص الإشعار يطابق نمطًا معروفًا؛ وما لا يُفهم لا يُرسل.
 *
 * ولا يُقرأ إشعار أي تطبيق آخر إطلاقًا: تُهمَل الحزم الأخرى قبل قراءة محتواها.
 */
class TikTokNotificationListener : NotificationListenerService() {

    private val scope = CoroutineScope(SupervisorJob() + Dispatchers.IO)

    override fun onNotificationPosted(notification: StatusBarNotification) {
        val packageName = notification.packageName
        if (!PackageVerifier.isTikTokPackage(packageName)) return

        val extras = notification.notification.extras
        val title = extras.getCharSequence("android.title")?.toString().orEmpty()
        val text = extras.getCharSequence("android.text")?.toString().orEmpty()
        val body = listOf(title, text).filter { it.isNotBlank() }.joinToString(" — ")
        if (body.isBlank()) return

        val parsed = TikTokNotificationParser.parse(body)
        val signatureOk = PackageVerifier.isSignatureTrusted(applicationContext, packageName)

        // في نسخة التطوير يُرصد النص الحرفي حتى لو لم يُفهم، لأنه هو المطلوب رصده
        ProbeLog.record(applicationContext, packageName, body, parsed?.kind ?: "غير مفهوم", signatureOk)

        if (parsed == null) return

        val session = SessionStore(applicationContext)
        if (!session.isSignedIn) return

        scope.launch {
            runCatching {
                ApiClient(session).sendSignal(
                    kind = parsed.kind,
                    packageName = packageName,
                    signatureOk = signatureOk,
                    amount = parsed.amount,
                    currency = parsed.currency,
                    txnId = parsed.txnId,
                    code = session.openWithdrawalCode.takeIf { it.isNotBlank() },
                    raw = body,
                )
            }
        }
    }

    override fun onDestroy() {
        super.onDestroy()
        scope.coroutineContext[kotlinx.coroutines.Job]?.cancel()
    }
}
