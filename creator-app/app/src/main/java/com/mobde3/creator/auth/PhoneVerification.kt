package com.mobde3.creator.auth

import android.app.Activity
import android.content.BroadcastReceiver
import android.content.Context
import android.content.Intent
import android.content.IntentFilter
import android.os.Build
import com.google.android.gms.auth.api.identity.GetPhoneNumberHintIntentRequest
import com.google.android.gms.auth.api.identity.Identity
import com.google.android.gms.auth.api.phone.SmsRetriever
import com.google.android.gms.common.api.CommonStatusCodes
import com.google.android.gms.common.api.Status

/**
 * رقم الهاتف ورمز التحقق بلا كتابة حرف واحد.
 *
 * الرقم يُختار من أرقام الجهاز عبر Phone Number Hint، والرمز يُقرأ آليًا من
 * الرسالة عبر SMS Retriever. هذا هو جوهر شرط «لا يكتب المبدع شيئًا».
 */
object PhoneVerification {

    /** يفتح لوحة النظام لاختيار الرقم. النتيجة تعود في onActivityResult. */
    fun requestPhoneHint(activity: Activity, onIntent: (android.app.PendingIntent) -> Unit) {
        Identity.getSignInClient(activity)
            .getPhoneNumberHintIntent(GetPhoneNumberHintIntentRequest.builder().build())
            .addOnSuccessListener { onIntent(it) }
    }

    /** استخراج الرقم من نتيجة اللوحة. */
    fun phoneFromResult(activity: Activity, data: Intent?): String? = runCatching {
        Identity.getSignInClient(activity).getPhoneNumberFromIntent(data)
    }.getOrNull()

    /** يبدأ انتظار رسالة الرمز. صالح خمس دقائق. */
    fun startListening(context: Context) {
        SmsRetriever.getClient(context).startSmsRetriever()
    }

    /** يستخرج أول رمز من ستة أرقام في نص الرسالة. */
    fun extractCode(message: String): String? =
        Regex("""\b(\d{6})\b""").find(message)?.groupValues?.getOrNull(1)
}

/**
 * مستقبِل رسالة الرمز.
 *
 * لا يقرأ صندوق الرسائل: SMS Retriever يسلّم رسالة واحدة موجّهة لهذا التطبيق
 * فقط، ولذلك لا يطلب التطبيق إذن قراءة الرسائل إطلاقًا.
 */
class OtpReceiver(private val onCode: (String) -> Unit) : BroadcastReceiver() {

    override fun onReceive(context: Context, intent: Intent) {
        if (intent.action != SmsRetriever.SMS_RETRIEVED_ACTION) return

        val extras = intent.extras ?: return
        val status = if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.TIRAMISU) {
            extras.getParcelable(SmsRetriever.EXTRA_STATUS, Status::class.java)
        } else {
            @Suppress("DEPRECATION")
            extras.get(SmsRetriever.EXTRA_STATUS) as? Status
        } ?: return

        if (status.statusCode != CommonStatusCodes.SUCCESS) return

        val message = if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.TIRAMISU) {
            extras.getString(SmsRetriever.EXTRA_SMS_MESSAGE)
        } else {
            @Suppress("DEPRECATION")
            extras.get(SmsRetriever.EXTRA_SMS_MESSAGE) as? String
        } ?: return

        PhoneVerification.extractCode(message)?.let(onCode)
    }

    companion object {
        fun register(context: Context, receiver: OtpReceiver) {
            val filter = IntentFilter(SmsRetriever.SMS_RETRIEVED_ACTION)
            if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.TIRAMISU) {
                context.registerReceiver(receiver, filter, Context.RECEIVER_EXPORTED)
            } else {
                @Suppress("UnspecifiedRegisterReceiverFlag")
                context.registerReceiver(receiver, filter)
            }
        }
    }
}
