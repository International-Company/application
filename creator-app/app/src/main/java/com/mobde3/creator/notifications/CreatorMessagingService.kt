package com.mobde3.creator.notifications

import android.app.NotificationChannel
import android.app.NotificationManager
import android.app.PendingIntent
import android.content.Intent
import android.os.Build
import androidx.core.app.NotificationCompat
import androidx.core.app.NotificationManagerCompat
import com.google.firebase.messaging.FirebaseMessagingService
import com.google.firebase.messaging.RemoteMessage
import com.mobde3.creator.MainActivity
import com.mobde3.creator.R
import com.mobde3.creator.data.ApiClient
import com.mobde3.creator.data.SessionStore
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.SupervisorJob
import kotlinx.coroutines.launch

/**
 * إشعارات المنصة للمبدع: حالة طلبه، وسؤال المهلة، وسؤال حسم التحويل المتعارض.
 *
 * الإجابات تعود إلى الخادم كإشارات لا كأوامر: «لم أُكمل السحب» تُلغي الطلب،
 * والمطالبة بتحويل تحسم صاحبه ولا تُنشئ مالًا بذاتها.
 */
class CreatorMessagingService : FirebaseMessagingService() {

    private val scope = CoroutineScope(SupervisorJob() + Dispatchers.IO)

    override fun onNewToken(token: String) {
        val session = SessionStore(applicationContext)
        if (!session.isSignedIn) return
        scope.launch {
            runCatching {
                ApiClient(session).registerDevice(
                    deviceId = session.deviceId,
                    integrityToken = "",
                    fcmToken = token,
                    permissions = emptyMap(),
                )
            }
        }
    }

    override fun onMessageReceived(message: RemoteMessage) {
        val data = message.data
        val title = message.notification?.title ?: data["title"].orEmpty()
        val body = message.notification?.body ?: data["body"].orEmpty()

        data["code"]?.let { code ->
            val session = SessionStore(applicationContext)
            if (data["status"] in CLOSED_STATUSES && session.openWithdrawalCode == code) {
                session.openWithdrawalCode = ""
            }
        }

        if (title.isNotBlank() || body.isNotBlank()) {
            show(title, body)
        }
    }

    private fun show(title: String, body: String) {
        val manager = NotificationManagerCompat.from(this)
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
            manager.createNotificationChannel(
                NotificationChannel(
                    CHANNEL_ID,
                    getString(R.string.app_name),
                    NotificationManager.IMPORTANCE_HIGH,
                )
            )
        }

        val intent = PendingIntent.getActivity(
            this,
            0,
            Intent(this, MainActivity::class.java),
            PendingIntent.FLAG_IMMUTABLE or PendingIntent.FLAG_UPDATE_CURRENT,
        )

        val notification = NotificationCompat.Builder(this, CHANNEL_ID)
            .setSmallIcon(android.R.drawable.ic_dialog_info)
            .setContentTitle(title)
            .setContentText(body)
            .setStyle(NotificationCompat.BigTextStyle().bigText(body))
            .setContentIntent(intent)
            .setAutoCancel(true)
            .build()

        runCatching { manager.notify(System.currentTimeMillis().toInt(), notification) }
    }

    private companion object {
        const val CHANNEL_ID = "withdrawals"
        val CLOSED_STATUSES = setOf("paid", "cancelled", "tiktok_rejected")
    }
}
