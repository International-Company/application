package com.mobde3.collector

import android.content.BroadcastReceiver
import android.content.Context
import android.content.Intent
import android.provider.Telephony

/**
 * قراءة رسائل البنك فقط.
 *
 * الرسالة من مرسِل غير مُدرج في القائمة المسموحة تُهمَل قبل أن تُقرأ، ولا يُرسل
 * إلى الخادم إلا ما فهمه المحلّل فهمًا كاملًا.
 */
class SmsReceiver : BroadcastReceiver() {

    override fun onReceive(context: Context, intent: Intent) {
        if (intent.action != Telephony.Sms.Intents.SMS_RECEIVED_ACTION) return

        val settings = Settings(context)
        if (!settings.isConfigured) return

        val messages = Telephony.Sms.Intents.getMessagesFromIntent(intent) ?: return
        val bySender = messages.groupBy { it.originatingAddress.orEmpty() }

        for ((sender, parts) in bySender) {
            if (!settings.isSenderAllowed(sender)) continue

            // رسالة البنك قد تصل مقسّمة على عدة أجزاء
            val body = parts.joinToString("") { it.messageBody.orEmpty() }
            val timestamp = parts.firstOrNull()?.timestampMillis ?: System.currentTimeMillis()

            val transfer = BankMessageParser.parse(
                text = body,
                receivedAtMillis = timestamp,
                accountIdentifier = settings.accountIdentifier,
                source = "sms",
            ) ?: continue

            UploadWorker.enqueue(context, transfer)
        }
    }
}
