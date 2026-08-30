package com.mobde3.creator.setup

import android.content.Context
import android.content.Intent
import android.widget.Toast
import com.mobde3.creator.R
import com.mobde3.creator.notifications.PackageVerifier

/**
 * فتح تطبيق TikTok.
 *
 * **الزر إرشادي بحت**: يفتح التطبيق ويظهر بطاقة الخطوات، ثم يتوقف دوره. لا
 * يوجد أي نقر آلي ولا حقن أحداث ولا أتمتة داخل TikTok — المبدع هو من يضغط.
 *
 * ملاحظة: لا يوجد رابط داخلي موثّق يفتح شاشة الرصيد مباشرة (سؤال §16 في وثيقة
 * المشروع). لذلك يُفتح التطبيق على شاشته الرئيسية، والبطاقة تقود بقية الطريق.
 * حين يُرصد رابط موثّق يُضاف هنا وحده.
 */
object TikTokLauncher {

    fun isInstalled(context: Context): Boolean =
        installedPackage(context) != null

    fun installedPackage(context: Context): String? =
        PackageVerifier.TIKTOK_PACKAGES.firstOrNull { packageName ->
            runCatching {
                context.packageManager.getLaunchIntentForPackage(packageName) != null
            }.getOrDefault(false)
        }

    /** يفتح TikTok. يعيد false إن لم يكن مثبَّتًا. */
    fun open(context: Context): Boolean {
        val packageName = installedPackage(context)
        if (packageName == null) {
            Toast.makeText(context, R.string.tiktok_not_installed, Toast.LENGTH_LONG).show()
            return false
        }
        val intent = context.packageManager.getLaunchIntentForPackage(packageName) ?: return false
        intent.addFlags(Intent.FLAG_ACTIVITY_NEW_TASK)
        context.startActivity(intent)
        return true
    }
}
