"""عرض المستندات القانونية بالعربية والإنجليزية."""
from django.http import Http404, JsonResponse
from django.shortcuts import render

from . import documents


def legal_document(request, document: str):
    """صفحة مستند. ?lang=en للإنجليزية، و?format=json للبصمة والنسخة."""
    if document not in documents.VERSIONS:
        raise Http404("مستند غير معروف")

    language = request.GET.get("lang", "ar")
    if language not in documents.LANGUAGES:
        language = "ar"

    if request.GET.get("format") == "json":
        return JsonResponse(documents.descriptor(document, language))

    other = "en" if language == "ar" else "ar"
    return render(
        request,
        "legal/base.html",
        {
            "document": document,
            "language": language,
            "direction": "rtl" if language == "ar" else "ltr",
            "title": documents.TITLES[(document, language)],
            "version": documents.version(document),
            "content_template": f"legal/{document}_{language}.html",
            "other_language": other,
            "other_language_label": "English" if other == "en" else "العربية",
            "terms_url": "/terms" + ("" if language == "ar" else "?lang=en"),
            "privacy_url": "/privacy" + ("" if language == "ar" else "?lang=en"),
            "labels": {
                "version": "النسخة" if language == "ar" else "Version",
                "terms": "شروط الاستخدام" if language == "ar" else "Terms of Service",
                "privacy": "سياسة الخصوصية" if language == "ar" else "Privacy Policy",
            },
        },
    )
