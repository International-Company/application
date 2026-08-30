package com.mobde3.collector

import android.content.Context
import androidx.work.BackoffPolicy
import androidx.work.Constraints
import androidx.work.Data
import androidx.work.ExistingWorkPolicy
import androidx.work.NetworkType
import androidx.work.OneTimeWorkRequestBuilder
import androidx.work.WorkManager
import androidx.work.Worker
import androidx.work.WorkerParameters
import java.util.concurrent.TimeUnit

/**
 * إرسال تحويل واحد إلى الخادم.
 *
 * الإرسال في عامل خلفي لا في مستقبِل الرسالة: انقطاع الشبكة يؤجّل الإرسال ولا
 * يُضيّع الرسالة، وWorkManager يعيد المحاولة بتباعد متزايد.
 */
class UploadWorker(context: Context, params: WorkerParameters) : Worker(context, params) {

    override fun doWork(): Result {
        val settings = Settings(applicationContext)
        if (!settings.isConfigured) return Result.failure()

        val transfer = IncomingTransfer(
            accountIdentifier = settings.accountIdentifier,
            amountEgp = inputData.getString(KEY_AMOUNT) ?: return Result.failure(),
            receivedAtIso = inputData.getString(KEY_RECEIVED_AT) ?: return Result.failure(),
            bankRef = inputData.getString(KEY_REF).orEmpty(),
            senderHint = inputData.getString(KEY_SENDER).orEmpty(),
            source = inputData.getString(KEY_SOURCE) ?: "sms",
            dedupeKey = inputData.getString(KEY_DEDUPE) ?: return Result.failure(),
            rawText = inputData.getString(KEY_RAW).orEmpty(),
        )

        val result = settings.client().sendIncoming(transfer)
        return when {
            result.success -> Result.success()
            // خطأ في البيانات نفسها: إعادة المحاولة لن تُصلحه
            result.code in 400..499 && result.code != 429 -> Result.failure()
            else -> Result.retry()
        }
    }

    companion object {
        private const val KEY_AMOUNT = "amount"
        private const val KEY_RECEIVED_AT = "received_at"
        private const val KEY_REF = "ref"
        private const val KEY_SENDER = "sender"
        private const val KEY_SOURCE = "source"
        private const val KEY_DEDUPE = "dedupe"
        private const val KEY_RAW = "raw"

        fun enqueue(context: Context, transfer: IncomingTransfer) {
            val data = Data.Builder()
                .putString(KEY_AMOUNT, transfer.amountEgp)
                .putString(KEY_RECEIVED_AT, transfer.receivedAtIso)
                .putString(KEY_REF, transfer.bankRef)
                .putString(KEY_SENDER, transfer.senderHint)
                .putString(KEY_SOURCE, transfer.source)
                .putString(KEY_DEDUPE, transfer.dedupeKey)
                .putString(KEY_RAW, transfer.rawText)
                .build()

            val request = OneTimeWorkRequestBuilder<UploadWorker>()
                .setInputData(data)
                .setConstraints(
                    Constraints.Builder()
                        .setRequiredNetworkType(NetworkType.CONNECTED)
                        .build()
                )
                .setBackoffCriteria(BackoffPolicy.EXPONENTIAL, 30, TimeUnit.SECONDS)
                .build()

            // مفتاح منع التكرار اسمٌ فريد للعمل: الرسالة الواحدة تُرسل مرة واحدة
            WorkManager.getInstance(context).enqueueUniqueWork(
                "upload-${transfer.dedupeKey}",
                ExistingWorkPolicy.KEEP,
                request,
            )
        }
    }
}
