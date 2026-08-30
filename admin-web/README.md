# لوحة الإدارة

React 18 + TypeScript + Vite + Tailwind. عربية RTL افتراضيًا مع تبديل كامل
للإنجليزية LTR، وتصميم أبيض بلا زخرفة.

## التشغيل

الخادم أولًا في طرفية:

```bash
cd ../backend
python manage.py runserver          # 127.0.0.1:8000
```

ثم اللوحة في طرفية أخرى:

```bash
npm install
npm run dev                         # http://localhost:5173
```

الجلسة كعكة `HttpOnly` على نفس الأصل، لذلك يمرّ `/api` عبر وسيط Vite إلى الخادم.
افتح **http://localhost:5173** لا `127.0.0.1` — Vite يربط على `localhost`.

## إنشاء مستخدم إدارة

```bash
cd ../backend
python manage.py shell -c "
from apps.identity.models import AdminUser, AdminRole
AdminUser.objects.create_user('admin@example.com', 'كلمة-مرور-قوية',
                              role=AdminRole.FINANCE, is_staff=True)
"
```

الأدوار: `superadmin` و`finance` يحرّكان المال، و`support` يقرأ ويلغي،
و`viewer` يقرأ فقط. الواجهة تُخفي أزرار المال عمّن لا يملكها، والخادم يرفضها
بصرف النظر عن الواجهة.

> في الإنتاج `ADMIN_REQUIRE_TOTP=1`: فعّل التحقق الثنائي عبر
> `POST /api/v1/admin/auth/totp` قبل أول دخول.

## البناء

```bash
npm run build      # dist/
npm run lint       # فحص الأنواع فقط
```

## الشاشات

| الشاشة | ما تفعله |
|---|---|
| الطلبات | جدول لحظي يتحدّث كل ١٠ ثوانٍ، بفلاتر الحالة والتاريخ، ومصدر كل تأكيد بالضغط على الرمز |
| الحالات المتعارضة | ما لم يصل وما رفضه TikTok |
| حسابات الاستلام | إضافة صاحب حساب، إضافة حساب، تخصيصه لمبدع، إيقافه (لا حذف) |
| المبدعون | بحث، حالة التجهيز، الرصيد |
| الدفع | قائمة المعتمدة، وتنفيذ الدفع بتسجيل المرجع |
| الإعدادات | جدول الرسوم وسعر الصرف |
| التقارير | الدفتر، الرسوم المحصّلة، الوارد اليومي، والقيود غير المتوازنة |
