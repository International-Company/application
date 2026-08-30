package com.mobde3.creator.ui

import android.content.ClipData
import android.content.ClipboardManager
import android.content.Context
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.Button
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.text.font.FontFamily
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import com.mobde3.creator.notifications.PackageVerifier
import com.mobde3.creator.notifications.ProbeLog
import com.mobde3.creator.setup.TikTokLauncher

/**
 * أدوات المطوّر — **نسخة التطوير وحدها**.
 *
 * ليست جزءًا من منتج المبدع ولا تظهر له. غرضها واحد: تمكين التجربة على جهاز
 * حقيقي قبل ربط SDK الخاص بـ TikTok، ورصد أجوبة الأسئلة المفتوحة في §16:
 * بصمة توقيع حزمة TikTok، والنص الحرفي لإشعاراتها، وهل تقبل خانات الدفع
 * التعبئة التلقائية.
 *
 * وهي الشاشة الوحيدة في التطبيق التي فيها حقول نصية، لأنها ليست للمبدع.
 */
@Composable
fun DevToolsScreen(
    onDevSignIn: (phone: String, code: String, onResult: (String) -> Unit) -> Unit,
    onBack: () -> Unit,
) {
    val context = LocalContext.current
    var phone by remember { mutableStateOf("+201000000001") }
    var otp by remember { mutableStateOf("") }
    var message by remember { mutableStateOf("") }
    var refreshToken by remember { mutableStateOf(0) }

    val installedPackage = remember(refreshToken) { TikTokLauncher.installedPackage(context) }
    val signatures = remember(refreshToken) {
        installedPackage?.let { PackageVerifier.signatureDigests(context, it) }.orEmpty()
    }
    val captures = remember(refreshToken) { ProbeLog.all(context) }

    Column(
        modifier = Modifier.fillMaxSize().padding(20.dp).verticalScroll(rememberScrollState())
    ) {
        Text("أدوات المطوّر", fontSize = 22.sp, fontWeight = FontWeight.Bold)
        Text(
            "لا تظهر هذه الشاشة في نسخة الإنتاج",
            fontSize = 13.sp,
            color = Color(0xFF888888),
        )

        Spacer(Modifier.height(20.dp))
        Section("١) حزمة TikTok")
        Text(installedPackage ?: "غير مثبَّت على هذا الجهاز", fontSize = 15.sp)

        Spacer(Modifier.height(12.dp))
        Section("٢) بصمة التوقيع (SHA-256)")
        if (signatures.isEmpty()) {
            Text("لم تُقرأ — ثبّت TikTok ثم حدّث", fontSize = 15.sp, color = Color(0xFF888888))
        } else {
            signatures.forEach {
                Text(it, fontSize = 12.sp, fontFamily = FontFamily.Monospace)
            }
            Text(
                "ضع هذه القيمة في tiktokSignatures عند البناء لتُصدَّق الإشعارات",
                fontSize = 13.sp,
                color = Color(0xFF888888),
            )
        }

        Spacer(Modifier.height(20.dp))
        Section("٣) دخول تجريبي بلا SDK")
        Text(
            "يعمل فقط مع خادم تطوير يستعمل مزوّد TikTok المزيّف",
            fontSize = 13.sp,
            color = Color(0xFF888888),
        )
        OutlinedTextField(
            value = phone,
            onValueChange = { phone = it },
            label = { Text("رقم الهاتف") },
            modifier = Modifier.fillMaxWidth(),
        )
        OutlinedTextField(
            value = otp,
            onValueChange = { otp = it },
            label = { Text("رمز التحقق (من سجل الخادم)") },
            modifier = Modifier.fillMaxWidth(),
        )
        Row {
            Button(onClick = { onDevSignIn(phone, "") { message = it } }) {
                Text("أرسل الرمز")
            }
            Spacer(Modifier.fillMaxWidth(0.05f))
            Button(onClick = { onDevSignIn(phone, otp) { message = it } }) {
                Text("تأكيد ودخول")
            }
        }
        if (message.isNotBlank()) {
            Text(message, fontSize = 14.sp, color = Color(0xFF333333))
        }

        Spacer(Modifier.height(20.dp))
        Section("٤) إشعارات TikTok المرصودة (${captures.size})")
        Text(
            "افتح TikTok واطلب سحبًا حقيقيًا، ثم عد هنا وانسخ النص",
            fontSize = 13.sp,
            color = Color(0xFF888888),
        )
        captures.forEach { capture ->
            Spacer(Modifier.height(10.dp))
            Text(
                "${capture.at} — ${capture.parsedKind} — توقيع: ${capture.signatureOk}",
                fontSize = 12.sp,
                color = Color(0xFF888888),
            )
            Text(capture.text, fontSize = 15.sp)
        }

        Spacer(Modifier.height(20.dp))
        Button(
            onClick = { copy(context, ProbeLog.asReport(context, signatures)) },
            modifier = Modifier.fillMaxWidth(),
        ) { Text("نسخ التقرير كاملًا") }

        TextButton(onClick = { refreshToken++ }, modifier = Modifier.fillMaxWidth()) {
            Text("تحديث")
        }
        TextButton(
            onClick = {
                ProbeLog.clear(context)
                refreshToken++
            },
            modifier = Modifier.fillMaxWidth(),
        ) { Text("مسح المرصود") }
        TextButton(onClick = onBack, modifier = Modifier.fillMaxWidth()) { Text("عودة") }
    }
}

@Composable
private fun Section(title: String) {
    Text(title, fontSize = 17.sp, fontWeight = FontWeight.Bold)
    Spacer(Modifier.height(4.dp))
}

private fun copy(context: Context, text: String) {
    val clipboard = context.getSystemService(Context.CLIPBOARD_SERVICE) as ClipboardManager
    clipboard.setPrimaryClip(ClipData.newPlainText("mobde3-probe", text))
}
