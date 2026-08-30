package com.mobde3.creator

import android.content.Intent
import android.net.Uri
import android.os.Bundle
import android.provider.Settings
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.activity.viewModels
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.material3.Surface
import androidx.compose.material3.lightColorScheme
import androidx.compose.runtime.Composable
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.unit.dp
import com.mobde3.creator.overlay.GuideOverlayService
import com.mobde3.creator.setup.TikTokLauncher
import com.mobde3.creator.ui.AfterWithdrawScreen
import com.mobde3.creator.ui.DevToolsScreen
import com.mobde3.creator.ui.CreatorViewModel
import com.mobde3.creator.ui.HomeScreen
import com.mobde3.creator.ui.PermissionsScreen
import com.mobde3.creator.ui.SetupScreen
import com.mobde3.creator.ui.WelcomeScreen

/**
 * الواجهة الوحيدة للمبدع.
 *
 * كل ما في هذه الشاشات أزرار إرشادية: تفتح TikTok وتشرح الخطوة، ولا تنفّذ شيئًا
 * داخله. عدد الضغطات مقيَّد بما نصّت عليه وثيقة المشروع.
 */
class MainActivity : ComponentActivity() {

    private val viewModel: CreatorViewModel by viewModels()

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        setContent {
            MaterialTheme(
                colorScheme = lightColorScheme(
                    primary = Color(0xFF111111),
                    background = Color.White,
                    surface = Color.White,
                )
            ) {
                Surface { AppRoot() }
            }
        }
    }

    override fun onResume() {
        super.onResume()
        // العودة من TikTok تُخفي بطاقة الإرشاد
        GuideOverlayService.stop(this)
        if (viewModel.session.isSignedIn) viewModel.refresh()
    }

    @Composable
    private fun AppRoot() {
        val state by viewModel.state.collectAsState()
        var screen by remember {
            mutableStateOf(if (viewModel.session.isSignedIn) Screen.HOME else Screen.WELCOME)
        }
        var lastCode by remember { mutableStateOf("") }

        when (screen) {
            Screen.WELCOME -> Box(modifier = Modifier.fillMaxSize()) {
                WelcomeScreen(
                    busy = state.busy,
                    error = state.error,
                    onStart = { startTikTokLink() },
                )
                // مدخل أدوات المطوّر: نسخة التطوير وحدها
                if (BuildConfig.DEBUG) {
                    TextButton(
                        onClick = { screen = Screen.DEV_TOOLS },
                        modifier = Modifier
                            .align(Alignment.BottomCenter)
                            .fillMaxWidth()
                            .padding(bottom = 16.dp),
                    ) { Text("أدوات المطوّر") }
                }
            }

            Screen.DEV_TOOLS -> DevToolsScreen(
                onDevSignIn = { phone, code, onResult ->
                    viewModel.devSignIn(phone, code) { message ->
                        onResult(message)
                        if (message == "تم الدخول") screen = Screen.PERMISSIONS
                    }
                },
                onBack = { screen = Screen.WELCOME },
            )

            Screen.PERMISSIONS -> PermissionsScreen(
                notificationsGranted = hasNotificationAccess(),
                overlayGranted = GuideOverlayService.canDraw(this),
                autofillGranted = hasAutofillService(),
                onGrant = { openNextMissingPermission() },
                onSkip = { screen = Screen.SETUP },
            )

            Screen.SETUP -> SetupScreen(
                onPrepare = {
                    GuideOverlayService.start(this, GuideOverlayService.STEP_SETUP)
                    TikTokLauncher.open(this)
                },
                onDone = { viewModel.completeSetup { screen = Screen.HOME } },
            )

            Screen.HOME -> HomeScreen(
                state = state,
                onWithdraw = {
                    viewModel.requestWithdrawal { code ->
                        lastCode = code
                        GuideOverlayService.start(this, GuideOverlayService.STEP_WITHDRAW)
                        TikTokLauncher.open(this)
                        screen = Screen.AFTER_WITHDRAW
                    }
                },
                onOpenSetup = { screen = Screen.PERMISSIONS },
                onSupport = { openSupport(lastCode) },
            )

            Screen.AFTER_WITHDRAW -> AfterWithdrawScreen(
                code = lastCode,
                onBack = {
                    screen = Screen.HOME
                    viewModel.refresh()
                },
            )
        }
    }

    private enum class Screen { WELCOME, DEV_TOOLS, PERMISSIONS, SETUP, HOME, AFTER_WITHDRAW }

    /**
     * ربط TikTok.
     *
     * الـ SDK غير مربوط بعد، فالواجهة تُظهر السبب صراحةً بدل أن توهم بنجاح.
     */
    private fun startTikTokLink() {
        val provider = com.mobde3.creator.auth.TikTokLoginFactory.current()
        provider.authorize(this) { result ->
            when (result) {
                is com.mobde3.creator.auth.TikTokLogin.Result.Success -> {
                    // التبادل يتم على الخادم: التوكنات لا تصل الجهاز إطلاقًا
                    viewModel.refresh()
                }
                is com.mobde3.creator.auth.TikTokLogin.Result.Failed ->
                    android.widget.Toast
                        .makeText(this, result.reason, android.widget.Toast.LENGTH_LONG)
                        .show()
                com.mobde3.creator.auth.TikTokLogin.Result.Cancelled -> Unit
            }
        }
    }

    private fun hasNotificationAccess(): Boolean {
        val enabled = Settings.Secure.getString(contentResolver, "enabled_notification_listeners")
        return enabled?.contains(packageName) == true
    }

    private fun hasAutofillService(): Boolean {
        val current = Settings.Secure.getString(contentResolver, "autofill_service")
        return current?.contains(packageName) == true
    }

    /** يفتح إعداد واحدًا ناقصًا في كل ضغطة، بلا إغراق المبدع بنوافذ. */
    private fun openNextMissingPermission() {
        when {
            !hasNotificationAccess() ->
                startActivity(Intent(Settings.ACTION_NOTIFICATION_LISTENER_SETTINGS))

            !GuideOverlayService.canDraw(this) -> startActivity(
                Intent(
                    Settings.ACTION_MANAGE_OVERLAY_PERMISSION,
                    Uri.parse("package:$packageName"),
                )
            )

            !hasAutofillService() -> startActivity(
                Intent(Settings.ACTION_REQUEST_SET_AUTOFILL_SERVICE)
                    .setData(Uri.parse("package:$packageName"))
            )
        }
    }

    private fun openSupport(code: String) {
        val text = Uri.encode(getString(R.string.support_message, code.ifBlank { "-" }))
        val number = getString(R.string.support_whatsapp)
        runCatching {
            startActivity(Intent(Intent.ACTION_VIEW, Uri.parse("https://wa.me/$number?text=$text")))
        }
    }
}
