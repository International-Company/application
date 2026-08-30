package com.mobde3.creator.ui

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.material3.Button
import androidx.compose.material3.Card
import androidx.compose.material3.CardDefaults
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import com.mobde3.creator.R

/**
 * شاشات المبدع.
 *
 * مبادئ ثابتة: زر واحد كبير في كل شاشة، ولا حقل نصي واحد في التطبيق كله،
 * وخط كبير وتباين عالٍ على خلفية بيضاء.
 */

@Composable
fun PrimaryButton(text: String, enabled: Boolean = true, onClick: () -> Unit) {
    Button(
        onClick = onClick,
        enabled = enabled,
        modifier = Modifier.fillMaxWidth().height(64.dp),
    ) {
        Text(text, fontSize = 20.sp, fontWeight = FontWeight.Bold)
    }
}

/** ١) الترحيب: زر واحد. */
@Composable
fun WelcomeScreen(busy: Boolean, error: String, onStart: () -> Unit) {
    Column(
        modifier = Modifier.fillMaxSize().padding(24.dp),
        verticalArrangement = Arrangement.Center,
        horizontalAlignment = Alignment.CenterHorizontally,
    ) {
        Text(
            stringResource(R.string.welcome_title),
            fontSize = 28.sp,
            fontWeight = FontWeight.Bold,
        )
        Spacer(Modifier.height(12.dp))
        Text(
            stringResource(R.string.welcome_body),
            fontSize = 17.sp,
            color = Color(0xFF555555),
        )
        Spacer(Modifier.height(40.dp))
        if (error.isNotBlank()) {
            Text(error, color = Color(0xFFB00020), fontSize = 15.sp)
            Spacer(Modifier.height(16.dp))
        }
        PrimaryButton(stringResource(R.string.start_with_tiktok), enabled = !busy, onClick = onStart)
    }
}

/** ٢) الأذونات: شاشة واحدة، زر واحد، وسطر شرح لكل إذن. */
@Composable
fun PermissionsScreen(
    notificationsGranted: Boolean,
    overlayGranted: Boolean,
    autofillGranted: Boolean,
    onGrant: () -> Unit,
    onSkip: () -> Unit,
) {
    Column(modifier = Modifier.fillMaxSize().padding(24.dp)) {
        Text(
            stringResource(R.string.permissions_title),
            fontSize = 24.sp,
            fontWeight = FontWeight.Bold,
        )
        Spacer(Modifier.height(20.dp))

        PermissionRow(
            stringResource(R.string.perm_notifications),
            stringResource(R.string.perm_notifications_why),
            notificationsGranted,
        )
        PermissionRow(
            stringResource(R.string.perm_overlay),
            stringResource(R.string.perm_overlay_why),
            overlayGranted,
        )
        PermissionRow(
            stringResource(R.string.perm_autofill),
            stringResource(R.string.perm_autofill_why),
            autofillGranted,
        )

        Spacer(Modifier.height(28.dp))
        PrimaryButton(stringResource(R.string.enable_assistant), onClick = onGrant)
        Spacer(Modifier.height(8.dp))
        TextButton(onClick = onSkip, modifier = Modifier.fillMaxWidth()) {
            Text(stringResource(R.string.later), fontSize = 16.sp)
        }
    }
}

@Composable
private fun PermissionRow(title: String, why: String, granted: Boolean) {
    Row(modifier = Modifier.fillMaxWidth().padding(vertical = 10.dp)) {
        Text(if (granted) "✓" else "•", fontSize = 20.sp, modifier = Modifier.padding(end = 12.dp))
        Column {
            Text(title, fontSize = 18.sp, fontWeight = FontWeight.Bold)
            Text(why, fontSize = 15.sp, color = Color(0xFF555555))
        }
    }
}

/** ٣) التجهيز: زر واحد يفتح TikTok مع بطاقة الإرشاد. */
@Composable
fun SetupScreen(onPrepare: () -> Unit, onDone: () -> Unit) {
    Column(modifier = Modifier.fillMaxSize().padding(24.dp)) {
        Text(stringResource(R.string.setup_title), fontSize = 24.sp, fontWeight = FontWeight.Bold)
        Spacer(Modifier.height(12.dp))
        Text(stringResource(R.string.setup_body), fontSize = 17.sp, color = Color(0xFF555555))
        Spacer(Modifier.height(32.dp))
        PrimaryButton(stringResource(R.string.prepare_tiktok), onClick = onPrepare)
        Spacer(Modifier.height(8.dp))
        TextButton(onClick = onDone, modifier = Modifier.fillMaxWidth()) {
            Text(stringResource(R.string.setup_done), fontSize = 16.sp)
        }
    }
}

/** ٤) الرئيسية: الرصيد، زر سحب كبير، وآخر خمسة طلبات. */
@Composable
fun HomeScreen(
    state: HomeState,
    onWithdraw: () -> Unit,
    onOpenSetup: () -> Unit,
    onSupport: () -> Unit,
) {
    if (state.loading) {
        Column(
            modifier = Modifier.fillMaxSize(),
            verticalArrangement = Arrangement.Center,
            horizontalAlignment = Alignment.CenterHorizontally,
        ) { CircularProgressIndicator() }
        return
    }

    Column(modifier = Modifier.fillMaxSize().padding(24.dp)) {
        Text(state.name, fontSize = 18.sp, color = Color(0xFF555555))
        Spacer(Modifier.height(6.dp))
        Text(stringResource(R.string.balance), fontSize = 15.sp, color = Color(0xFF777777))
        Text(
            "${state.balanceEgp} ${stringResource(R.string.egp)}",
            fontSize = 34.sp,
            fontWeight = FontWeight.Bold,
        )

        Spacer(Modifier.height(28.dp))
        if (state.error.isNotBlank()) {
            Text(state.error, color = Color(0xFFB00020), fontSize = 15.sp)
            Spacer(Modifier.height(12.dp))
        }

        if (state.setupCompleted) {
            PrimaryButton(
                stringResource(R.string.withdraw),
                enabled = !state.busy,
                onClick = onWithdraw,
            )
        } else {
            PrimaryButton(stringResource(R.string.prepare_tiktok), onClick = onOpenSetup)
        }

        Spacer(Modifier.height(28.dp))
        Text(
            stringResource(R.string.recent_requests),
            fontSize = 17.sp,
            fontWeight = FontWeight.Bold,
        )
        Spacer(Modifier.height(8.dp))

        LazyColumn(modifier = Modifier.fillMaxWidth().weight(1f)) {
            items(state.withdrawals) { item ->
                Card(
                    modifier = Modifier.fillMaxWidth().padding(vertical = 6.dp),
                    colors = CardDefaults.cardColors(containerColor = Color.White),
                ) {
                    Column(Modifier.padding(14.dp)) {
                        Text(item.code, fontSize = 17.sp, fontWeight = FontWeight.Bold)
                        Text(item.statusLabel, fontSize = 15.sp, color = Color(0xFF555555))
                        item.amountEgp?.let {
                            Text("$it ${stringResource(R.string.egp)}", fontSize = 15.sp)
                        }
                    }
                }
            }
        }

        TextButton(onClick = onSupport, modifier = Modifier.fillMaxWidth()) {
            Text(stringResource(R.string.support), fontSize = 16.sp)
        }
    }
}

/** ٥) بعد الضغط: بطاقة تشرح ما يجب فعله داخل TikTok. */
@Composable
fun AfterWithdrawScreen(code: String, onBack: () -> Unit) {
    Column(
        modifier = Modifier.fillMaxSize().padding(24.dp),
        verticalArrangement = Arrangement.Center,
    ) {
        Text(
            stringResource(R.string.withdraw_started),
            fontSize = 24.sp,
            fontWeight = FontWeight.Bold,
        )
        Spacer(Modifier.height(10.dp))
        Text(code, fontSize = 20.sp, fontWeight = FontWeight.Bold)
        Spacer(Modifier.height(16.dp))
        Text(
            stringResource(R.string.withdraw_instructions),
            fontSize = 17.sp,
            color = Color(0xFF555555),
        )
        Spacer(Modifier.height(32.dp))
        PrimaryButton(stringResource(R.string.back_home), onClick = onBack)
    }
}
