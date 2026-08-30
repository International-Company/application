package com.mobde3.collector

import android.service.notification.NotificationListenerService
import android.service.notification.StatusBarNotification

/**
 * احتياط لقراءة إشعار تطبيق البنك حين لا تصل رسالة SMS.
 *
 * لا يُقرأ إلا إشعار الحزم المُدرجة في القائمة المسموحة، ويُهمَل ما عداها قبل
 * قراءة محتواه.
 */
class BankNotificationListener : NotificationListenerService() {

    override fun onNotificationPosted(notification: StatusBarNotification) {
        val settings = Settings(applicationContext)
        if (!settings.isConfigured) return
        if (!settings.isSenderAllowed(notification.packageName)) return

        val extras = notification.notification.extras
        val title = extras.getCharSequence("android.title")?.toString().orEmpty()
        val text = extras.getCharSequence("android.text")?.toString().orEmpty()
        val body = listOf(title, text).filter { it.isNotBlank() }.joinToString(" — ")
        if (body.isBlank()) return

        val transfer = BankMessageParser.parse(
            text = body,
            receivedAtMillis = notification.postTime,
            accountIdentifier = settings.accountIdentifier,
            source = "notification",
        ) ?: return

        UploadWorker.enqueue(applicationContext, transfer)
    }
}
