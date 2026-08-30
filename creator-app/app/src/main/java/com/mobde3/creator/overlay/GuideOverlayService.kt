package com.mobde3.creator.overlay

import android.app.Service
import android.content.Context
import android.content.Intent
import android.graphics.PixelFormat
import android.os.Build
import android.os.IBinder
import android.view.Gravity
import android.view.LayoutInflater
import android.view.View
import android.view.WindowManager
import android.widget.Button
import android.widget.TextView
import com.mobde3.creator.R

/**
 * بطاقة إرشاد تظهر فوق TikTok.
 *
 * **إرشادية بحتة**: تعرض الخطوة التالية نصًا ولا تقرأ الشاشة ولا تلمس شيئًا
 * داخل TikTok. لا توجد في هذا التطبيق خدمة إتاحة (Accessibility) ولا حقن
 * أحداث لمس؛ المبدع هو من يضغط بإصبعه دائمًا.
 */
class GuideOverlayService : Service() {

    private var windowManager: WindowManager? = null
    private var view: View? = null

    override fun onBind(intent: Intent?): IBinder? = null

    override fun onStartCommand(intent: Intent?, flags: Int, startId: Int): Int {
        val step = intent?.getStringExtra(EXTRA_STEP) ?: STEP_WITHDRAW
        show(step)
        return START_NOT_STICKY
    }

    private fun show(step: String) {
        if (!canDraw(this)) {
            stopSelf()
            return
        }

        hide()
        val manager = getSystemService(WINDOW_SERVICE) as WindowManager
        val card = LayoutInflater.from(this).inflate(R.layout.overlay_guide, null)

        card.findViewById<TextView>(R.id.guideTitle).setText(titleFor(step))
        card.findViewById<TextView>(R.id.guideBody).setText(bodyFor(step))
        card.findViewById<Button>(R.id.guideDone).setOnClickListener { stopSelf() }

        val params = WindowManager.LayoutParams(
            WindowManager.LayoutParams.MATCH_PARENT,
            WindowManager.LayoutParams.WRAP_CONTENT,
            if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
                WindowManager.LayoutParams.TYPE_APPLICATION_OVERLAY
            } else {
                @Suppress("DEPRECATION")
                WindowManager.LayoutParams.TYPE_PHONE
            },
            // لا تلتقط اللمس: كل ضغطة تمر إلى TikTok تحتها
            WindowManager.LayoutParams.FLAG_NOT_FOCUSABLE,
            PixelFormat.TRANSLUCENT,
        ).apply {
            gravity = Gravity.TOP
            y = 80
        }

        manager.addView(card, params)
        windowManager = manager
        view = card
    }

    private fun titleFor(step: String): Int = when (step) {
        STEP_SETUP -> R.string.guide_setup_title
        else -> R.string.guide_withdraw_title
    }

    private fun bodyFor(step: String): Int = when (step) {
        STEP_SETUP -> R.string.guide_setup_body
        else -> R.string.guide_withdraw_body
    }

    private fun hide() {
        val current = view ?: return
        runCatching { windowManager?.removeView(current) }
        view = null
    }

    override fun onDestroy() {
        hide()
        super.onDestroy()
    }

    companion object {
        const val EXTRA_STEP = "step"
        const val STEP_SETUP = "setup"
        const val STEP_WITHDRAW = "withdraw"

        fun canDraw(context: Context): Boolean =
            Build.VERSION.SDK_INT < Build.VERSION_CODES.M ||
                android.provider.Settings.canDrawOverlays(context)

        fun start(context: Context, step: String) {
            if (!canDraw(context)) return
            context.startService(
                Intent(context, GuideOverlayService::class.java).putExtra(EXTRA_STEP, step)
            )
        }

        fun stop(context: Context) {
            context.stopService(Intent(context, GuideOverlayService::class.java))
        }
    }
}
