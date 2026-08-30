"""فهرس رسائل الحالات: مفتاح لكل حدث، ونص افتراضي بلغتين.

القوالب تُخزَّن في قاعدة البيانات لتعدّلها الإدارة، وهذا الفهرس هو النص
الافتراضي الذي يُنشأ منه أول مرة والذي يُستعمل إن غاب القالب.
"""
from apps.withdrawals.models import WithdrawalStatus

# أزرار الرد التفاعلي على رسالة «TikTok أرسل»
ARRIVAL_BUTTONS = [
    {"id": "received", "title_ar": "وصل", "title_en": "Received"},
    {"id": "not_received", "title_ar": "لم يصل", "title_en": "Not received"},
]

OWNER_TEMPLATES: dict[str, dict] = {
    WithdrawalStatus.TIKTOK_PROCESSING: {
        "key": "owner_processing",
        "provider_template_name": "wd_owner_processing",
        "ar": "طلب سحب {code} بمبلغ {amount_usd}$ من {creator} إلى حسابك، متوقع خلال ١–٣ أيام.",
        "en": (
            "Withdrawal {code} of {amount_usd}$ from {creator} to your account, "
            "expected within 1-3 days."
        ),
        "buttons": [],
    },
    WithdrawalStatus.TIKTOK_SENT: {
        "key": "owner_sent",
        "provider_template_name": "wd_owner_sent",
        "ar": "TikTok أرسل {amount_usd}$ للطلب {code}. هل وصل إلى حسابك؟",
        "en": "TikTok sent {amount_usd}$ for request {code}. Did it arrive in your account?",
        "buttons": ARRIVAL_BUTTONS,
    },
    WithdrawalStatus.TIKTOK_REJECTED: {
        "key": "owner_rejected",
        "provider_template_name": "wd_owner_rejected",
        "ar": "الطلب {code} رُفض من TikTok، لا شيء سيصل إلى حسابك.",
        "en": "Request {code} was rejected by TikTok. Nothing will arrive.",
        "buttons": [],
    },
    WithdrawalStatus.RECEIVED_EG: {
        "key": "owner_received",
        "provider_template_name": "wd_owner_received",
        "ar": "تم تسجيل وصول {amount_egp} ج.م للطلب {code}. شكرًا لتأكيدك.",
        "en": "Arrival of {amount_egp} EGP recorded for request {code}. Thank you.",
        "buttons": [],
    },
    WithdrawalStatus.NOT_RECEIVED: {
        "key": "owner_not_received",
        "provider_template_name": "wd_owner_not_received",
        "ar": "تذكير: هل وصل الطلب {code} بمبلغ {amount_usd}$ إلى حسابك؟",
        "en": "Reminder: did request {code} for {amount_usd}$ arrive in your account?",
        "buttons": ARRIVAL_BUTTONS,
    },
}

# ما يصل الإدارة على واتساب — الحالات التي تحتاج تدخلًا بشريًا
ADMIN_TEMPLATES: dict[str, dict] = {
    WithdrawalStatus.TIKTOK_REJECTED: {
        "key": "admin_rejected",
        "provider_template_name": "wd_admin_rejected",
        "ar": "الطلب {code} للمبدع {creator} رُفض من TikTok.",
        "en": "Request {code} for creator {creator} was rejected by TikTok.",
        "buttons": [],
    },
    WithdrawalStatus.NOT_RECEIVED: {
        "key": "admin_not_received",
        "provider_template_name": "wd_admin_not_received",
        "ar": "الطلب {code} بمبلغ {amount_usd}$ لم يصل خلال المهلة. يلزم تحقيق.",
        "en": "Request {code} for {amount_usd}$ did not arrive within the deadline.",
        "buttons": [],
    },
}

# رد صاحب الحساب يُترجم إلى دلالة واحدة
BUTTON_MEANING = {
    "received": "received",
    "not_received": "not_received",
    "وصل": "received",
    "لم يصل": "not_received",
}


def all_definitions() -> list[tuple[str, dict]]:
    """كل القوالب مع من يستقبلها، لتوليدها في قاعدة البيانات."""
    items: list[tuple[str, dict]] = []
    for definition in OWNER_TEMPLATES.values():
        items.append(("owner", definition))
    for definition in ADMIN_TEMPLATES.values():
        items.append(("admin", definition))
    return items
