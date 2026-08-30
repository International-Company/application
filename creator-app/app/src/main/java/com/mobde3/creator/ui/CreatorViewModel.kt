package com.mobde3.creator.ui

import android.app.Application
import androidx.lifecycle.AndroidViewModel
import androidx.lifecycle.viewModelScope
import com.mobde3.creator.data.ApiClient
import com.mobde3.creator.data.SessionStore
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext
import org.json.JSONObject

/** طلب سحب كما يعرضه التطبيق. */
data class Withdrawal(
    val code: String,
    val status: String,
    val statusLabel: String,
    val amountUsd: String?,
    val amountEgp: String?,
    val netEgp: String?,
) {
    companion object {
        fun from(json: JSONObject) = Withdrawal(
            code = json.optString("code"),
            status = json.optString("status"),
            statusLabel = json.optString("status_label"),
            amountUsd = json.optString("amount_usd").takeIf { it.isNotBlank() && it != "null" },
            amountEgp = json.optString("amount_egp").takeIf { it.isNotBlank() && it != "null" },
            netEgp = json.optString("net_amount_egp").takeIf { it.isNotBlank() && it != "null" },
        )
    }
}

/** حالة الشاشة الرئيسية. */
data class HomeState(
    val loading: Boolean = true,
    val name: String = "",
    val balanceEgp: String = "0",
    val setupCompleted: Boolean = false,
    val withdrawals: List<Withdrawal> = emptyList(),
    val error: String = "",
    val busy: Boolean = false,
)

class CreatorViewModel(application: Application) : AndroidViewModel(application) {

    val session = SessionStore(application)
    private val api = ApiClient(session)

    private val _state = MutableStateFlow(HomeState())
    val state: StateFlow<HomeState> = _state.asStateFlow()

    fun refresh() {
        viewModelScope.launch {
            _state.value = _state.value.copy(loading = true, error = "")
            val result = runCatching { withContext(Dispatchers.IO) { api.me() } }
            result.onSuccess { me ->
                val list = me.optJSONArray("recent_withdrawals")
                val items = buildList {
                    for (index in 0 until (list?.length() ?: 0)) {
                        add(Withdrawal.from(list!!.getJSONObject(index)))
                    }
                }
                session.setupCompleted = me.optBoolean("setup_completed")
                _state.value = HomeState(
                    loading = false,
                    name = me.optString("display_name"),
                    balanceEgp = me.optString("balance_egp"),
                    setupCompleted = me.optBoolean("setup_completed"),
                    withdrawals = items,
                )
            }.onFailure { error ->
                _state.value = _state.value.copy(loading = false, error = messageOf(error))
            }
        }
    }

    /** ضغطة «سحب»: لا مبلغ ولا حقل. يعيد رمز الطلب عند النجاح. */
    fun requestWithdrawal(onCreated: (String) -> Unit) {
        viewModelScope.launch {
            _state.value = _state.value.copy(busy = true, error = "")
            runCatching { withContext(Dispatchers.IO) { api.createWithdrawal() } }
                .onSuccess { response ->
                    val code = response.optJSONObject("withdrawal")?.optString("code").orEmpty()
                    session.openWithdrawalCode = code
                    _state.value = _state.value.copy(busy = false)
                    onCreated(code)
                    refresh()
                }
                .onFailure { error ->
                    _state.value = _state.value.copy(busy = false, error = messageOf(error))
                }
        }
    }

    fun completeSetup(onDone: () -> Unit) {
        viewModelScope.launch {
            runCatching { withContext(Dispatchers.IO) { api.completeSetup() } }
                .onSuccess {
                    session.setupCompleted = true
                    onDone()
                    refresh()
                }
                .onFailure { error ->
                    _state.value = _state.value.copy(error = messageOf(error))
                }
        }
    }

    /**
     * دخول تجريبي بلا SDK — **نسخة التطوير وحدها**.
     *
     * يمر بنفس مسارات الخادم الحقيقية: تبادل الكود ثم تحقق الهاتف. الفرق
     * الوحيد أن خادم التطوير يستعمل مزوّد TikTok المزيّف، فيقبل أي كود.
     */
    fun devSignIn(phone: String, code: String, onResult: (String) -> Unit) {
        if (!com.mobde3.creator.BuildConfig.DEBUG) {
            onResult("غير متاح في نسخة الإنتاج")
            return
        }
        viewModelScope.launch {
            val outcome = runCatching {
                withContext(Dispatchers.IO) {
                    val exchange = api.exchangeTikTokCode("dev-code", "dev-verifier", session.deviceId)
                    val preauth = exchange.optString("preauth_token")
                    if (preauth.isBlank()) return@withContext "الحساب مربوط بالفعل — أعد التشغيل"

                    if (code.isBlank()) {
                        api.verifyPhone(preauth, phone)
                        "أُرسل الرمز؛ اقرأه من سجل الخادم"
                    } else {
                        val result = api.verifyPhone(preauth, phone, code, session.deviceId)
                        val sessionJson = result.optJSONObject("session")
                            ?: return@withContext "لم تصدر جلسة"
                        session.save(sessionJson)
                        api.registerDevice(
                            deviceId = session.deviceId,
                            integrityToken = "dev-integrity-token",
                            fcmToken = "",
                            permissions = emptyMap(),
                        )
                        "تم الدخول"
                    }
                }
            }
            onResult(outcome.getOrElse { messageOf(it) })
            refresh()
        }
    }

    fun signOut() {
        session.clear()
        _state.value = HomeState(loading = false)
    }

    private fun messageOf(error: Throwable): String =
        (error as? ApiClient.ApiException)?.message ?: "تعذّر الاتصال بالخادم"
}
