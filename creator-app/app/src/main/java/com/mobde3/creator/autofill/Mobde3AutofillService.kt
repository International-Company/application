package com.mobde3.creator.autofill

import android.app.assist.AssistStructure
import android.os.Build
import android.os.CancellationSignal
import android.service.autofill.AutofillService
import android.service.autofill.Dataset
import android.service.autofill.FillCallback
import android.service.autofill.FillRequest
import android.service.autofill.FillResponse
import android.service.autofill.SaveCallback
import android.service.autofill.SaveRequest
import android.view.autofill.AutofillId
import android.view.autofill.AutofillValue
import android.widget.RemoteViews
import androidx.annotation.RequiresApi
import com.mobde3.creator.R
import com.mobde3.creator.data.ApiClient
import com.mobde3.creator.data.SessionStore
import com.mobde3.creator.notifications.PackageVerifier

/**
 * خدمة التعبئة التلقائية.
 *
 * تعبّئ بيانات حساب الاستلام داخل TikTok بضغطة واحدة، فلا يكتب المبدع شيئًا
 * ولا يرى الحساب أصلًا.
 *
 * **حدّ صارم**: لا تستجيب هذه الخدمة إلا داخل حزم TikTok. أي تطبيق آخر —
 * بنك أو بريد أو غيره — تُعاد له استجابة فارغة قبل أن تُقرأ حقوله. هذا وعد
 * مكتوب في سياسة الخصوصية، ومنفَّذ هنا سطرًا واحدًا قبل أي شيء آخر.
 *
 * والبيانات تُطلب من الخادم لحظة التعبئة ولا تُخزَّن على الجهاز إطلاقًا.
 */
@RequiresApi(Build.VERSION_CODES.O)
class Mobde3AutofillService : AutofillService() {

    override fun onFillRequest(
        request: FillRequest,
        cancellationSignal: CancellationSignal,
        callback: FillCallback,
    ) {
        val structure = request.fillContexts.lastOrNull()?.structure
        val packageName = structure?.activityComponent?.packageName.orEmpty()

        // الحاجز الأول والأهم: خارج TikTok لا نفعل شيئًا
        if (!PackageVerifier.isTikTokPackage(packageName)) {
            callback.onSuccess(null)
            return
        }

        val session = SessionStore(applicationContext)
        if (!session.isSignedIn) {
            callback.onSuccess(null)
            return
        }

        val fields = collectFields(structure)
        if (fields.isEmpty()) {
            callback.onSuccess(null)
            return
        }

        val dataset = runCatching { ApiClient(session).autofillDataset() }.getOrNull()
        if (dataset == null) {
            callback.onSuccess(null)
            return
        }

        val identifier = dataset.optString("identifier")
        val beneficiary = dataset.optString("beneficiary_name")
        val bank = dataset.optString("bank_name")

        val presentation = RemoteViews(packageName, android.R.layout.simple_list_item_1).apply {
            setTextViewText(android.R.id.text1, getString(R.string.autofill_dataset_label))
        }

        val builder = Dataset.Builder(presentation)
        var filled = 0
        for ((autofillId, hint) in fields) {
            val value = when (hint) {
                FieldHint.ACCOUNT -> identifier
                FieldHint.NAME -> beneficiary
                FieldHint.BANK -> bank
            }
            if (value.isNotBlank()) {
                builder.setValue(autofillId, AutofillValue.forText(value))
                filled++
            }
        }

        if (filled == 0) {
            callback.onSuccess(null)
            return
        }

        callback.onSuccess(FillResponse.Builder().addDataset(builder.build()).build())
    }

    /** لا نحفظ شيئًا مما يكتبه المستخدم في أي تطبيق. */
    override fun onSaveRequest(request: SaveRequest, callback: SaveCallback) {
        callback.onSuccess()
    }

    private enum class FieldHint { ACCOUNT, NAME, BANK }

    private fun collectFields(structure: AssistStructure): List<Pair<AutofillId, FieldHint>> {
        val found = mutableListOf<Pair<AutofillId, FieldHint>>()
        for (index in 0 until structure.windowNodeCount) {
            walk(structure.getWindowNodeAt(index).rootViewNode, found)
        }
        return found
    }

    private fun walk(node: AssistStructure.ViewNode, found: MutableList<Pair<AutofillId, FieldHint>>) {
        val id = node.autofillId
        if (id != null && node.autofillType == android.view.View.AUTOFILL_TYPE_TEXT) {
            hintOf(node)?.let { found.add(id to it) }
        }
        for (index in 0 until node.childCount) {
            walk(node.getChildAt(index), found)
        }
    }

    /** استنتاج معنى الحقل من تلميحاته ونصوصه. */
    private fun hintOf(node: AssistStructure.ViewNode): FieldHint? {
        val clues = buildList {
            node.autofillHints?.forEach { add(it) }
            node.hint?.let { add(it) }
            node.idEntry?.let { add(it) }
            node.text?.let { add(it.toString()) }
        }.joinToString(" ").lowercase()

        return when {
            clues.isBlank() -> null
            listOf("bank", "بنك").any { clues.contains(it) } -> FieldHint.BANK
            listOf("name", "holder", "beneficiary", "اسم", "المستفيد").any { clues.contains(it) } ->
                FieldHint.NAME
            listOf("account", "iban", "ipa", "instapay", "address", "حساب", "عنوان")
                .any { clues.contains(it) } -> FieldHint.ACCOUNT
            else -> null
        }
    }
}
