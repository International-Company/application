package com.mobde3.creator.notifications

/**
 * محلّل نص إشعار TikTok.
 *
 * ⚠️ الأنماط هنا **مبدئية**: النص الحرفي لإشعار TikTok عند طلب السحب وإتمامه
 * ورفضه لم يُرصد بعد على جهاز حقيقي (سؤال §16 في وثيقة المشروع). لم يُخترع أي
 * نص؛ الأنماط الحالية عامة، وحين تصل النصوص الحقيقية تُضاف كأنماط جديدة.
 *
 * قاعدة السلامة: **ما لا يُفهم لا يُرسل.** إشعار لا يطابق نمطًا يُهمَل تمامًا،
 * فلا يُخمَّن مبلغ ولا حالة في نظام مالي.
 */
object TikTokNotificationParser {

    data class Parsed(
        val kind: String,
        val amount: String? = null,
        val currency: String? = null,
        val txnId: String? = null,
    )

    private val amountPattern = Regex("""\$\s?([\d,]+(?:\.\d{1,2})?)|([\d,]+(?:\.\d{1,2})?)\s?USD""")
    private val txnPattern = Regex("""(?:ID|رقم العملية|transaction)\W{0,3}([A-Za-z0-9\-]{6,40})""", RegexOption.IGNORE_CASE)

    /** كلمات تدل على كل حالة، بالعربية والإنجليزية. */
    private val kinds: List<Pair<String, List<String>>> = listOf(
        "rejected" to listOf("rejected", "failed", "declined", "unsuccessful", "فشل", "رُفض", "مرفوض"),
        "sent" to listOf("sent", "completed", "transferred", "successfully", "تم التحويل", "تم الإرسال", "اكتمل"),
        "processing" to listOf("processing", "pending", "in progress", "received your", "قيد المعالجة", "قيد التنفيذ", "استلمنا"),
    )

    /** كلمات تدل على أن الإشعار يخص السحب أصلًا؛ بدونها لا يُقرأ. */
    private val withdrawalHints =
        listOf("withdraw", "payout", "balance", "سحب", "رصيد", "تحويل")

    fun parse(text: String): Parsed? {
        val lower = text.lowercase()
        if (withdrawalHints.none { lower.contains(it.lowercase()) }) return null

        val kind = kinds.firstOrNull { (_, words) ->
            words.any { lower.contains(it.lowercase()) }
        }?.first ?: return null

        val amountMatch = amountPattern.find(text)
        val amount = (amountMatch?.groupValues?.getOrNull(1)?.takeIf { it.isNotBlank() }
            ?: amountMatch?.groupValues?.getOrNull(2))
            ?.replace(",", "")

        return Parsed(
            kind = kind,
            amount = amount,
            currency = amount?.let { "USD" },
            txnId = txnPattern.find(text)?.groupValues?.getOrNull(1),
        )
    }
}
