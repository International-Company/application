package com.mobde3.collector

import java.text.SimpleDateFormat
import java.util.Date
import java.util.Locale
import java.util.TimeZone

/** تحويل وارد كما استُخرج من رسالة البنك. */
data class IncomingTransfer(
    val accountIdentifier: String,
    val amountEgp: String,
    val receivedAtIso: String,
    val bankRef: String,
    val senderHint: String,
    val source: String,
    val dedupeKey: String,
    val rawText: String,
)

/**
 * محلّل رسائل البنك.
 *
 * الأنماط هنا **مبدئية**: الصيغة الحرفية لرسالة بنك الشركة عند وصول تحويل
 * إنستاباي لم تُرصد بعد على جهاز حقيقي (سؤال §16 في وثيقة المشروع). حين تصل
 * الصيغة الحقيقية تُضاف كنمط جديد دون تغيير أي شيء آخر في التطبيق.
 *
 * قاعدة السلامة: ما لا يُفهم لا يُرسل. رسالة لا تطابق أي نمط تُهمَل تمامًا
 * بدل تخمين مبلغ قد يُقيَّد في دفتر مالي.
 */
object BankMessageParser {

    private val isoFormat = SimpleDateFormat("yyyy-MM-dd'T'HH:mm:ss'Z'", Locale.US).apply {
        timeZone = TimeZone.getTimeZone("UTC")
    }

    /** أنماط تُلتقط منها: المبلغ، والحساب، والمرجع إن وُجد. */
    private val patterns = listOf(
        // نمط شائع بالعربية: «تم إيداع 4850.00 جنيه إلى حسابك ... مرجع 123»
        Regex(
            """(?:تم\s+)?(?:إيداع|ايداع|استلام)\s+([\d,]+(?:\.\d{1,2})?)\s*(?:جنيه|ج\.م|EGP)""",
            RegexOption.IGNORE_CASE,
        ),
        // نمط إنجليزي: «Credit EGP 4,850.00 to account ... Ref 123»
        Regex(
            """(?:credit(?:ed)?|received)\s+(?:EGP|LE)\s*([\d,]+(?:\.\d{1,2})?)""",
            RegexOption.IGNORE_CASE,
        ),
    )

    private val referencePattern = Regex(
        """(?:مرجع|ref(?:erence)?|txn)\W{0,3}([A-Za-z0-9\-]{4,32})""",
        RegexOption.IGNORE_CASE,
    )

    private val senderPattern = Regex(
        """(?:من|from)\s+([A-Za-z؀-ۿ0-9 @._\-]{3,40})""",
        RegexOption.IGNORE_CASE,
    )

    /**
     * يعيد التحويل إن فُهمت الرسالة، وإلا null.
     *
     * @param accountIdentifier معرّف حساب الاستلام المرتبط بهذا الجهاز.
     */
    fun parse(
        text: String,
        receivedAtMillis: Long,
        accountIdentifier: String,
        source: String,
    ): IncomingTransfer? {
        if (accountIdentifier.isBlank()) return null

        val amount = patterns.firstNotNullOfOrNull { pattern ->
            pattern.find(text)?.groupValues?.getOrNull(1)
        }?.replace(",", "") ?: return null

        if (amount.toDoubleOrNull()?.let { it <= 0.0 } != false) return null

        return IncomingTransfer(
            accountIdentifier = accountIdentifier,
            amountEgp = amount,
            receivedAtIso = isoFormat.format(Date(receivedAtMillis)),
            bankRef = referencePattern.find(text)?.groupValues?.getOrNull(1).orEmpty(),
            senderHint = senderPattern.find(text)?.groupValues?.getOrNull(1)?.trim().orEmpty(),
            source = source,
            dedupeKey = ApiClient.dedupeKey(text, receivedAtMillis),
            rawText = text,
        )
    }
}
