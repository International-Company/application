# الخادم الخلفي — منصة إدارة المبدعين وسحب أرباح TikTok

## التشغيل محليًا

```bash
python -m venv .venv
.venv/Scripts/pip install -r requirements-dev.txt   # لينكس: .venv/bin/pip
cp .env.example .env
# ولّد مفتاح التشفير وضعه في FIELD_ENCRYPTION_KEY
python -c "import os,base64;print(base64.b64encode(os.urandom(32)).decode())"
python manage.py migrate
python manage.py runserver
```

## تجربة الرحلة كاملة محليًا

بيئة التطوير تعمل **بلا أي مفاتيح خارجية**: TikTok والرسائل والإشعارات وفحص الجهاز
كلها بدائل في الذاكرة، ورمز التحقق يظهر في سجل الخادم.

```bash
python manage.py migrate
python manage.py seed_demo        # حساب استلام + رسوم + سعر صرف (ما تضعه الإدارة لاحقًا)
python manage.py runserver
```

ثم من طرفية أخرى:

```bash
B=http://127.0.0.1:8000/api/v1

# 1) ضغطة «ابدأ بحساب TikTok»
curl -s -X POST $B/auth/tiktok/exchange -H 'Content-Type: application/json'      -d '{"code":"demo","device_id":"dev-1"}'
# انسخ preauth_token

# 2) إرسال رمز التحقق — يظهر الرمز في سجل الخادم لا في الاستجابة
curl -s -X POST $B/auth/phone/verify -H 'Content-Type: application/json'      -H 'Authorization: Bearer <preauth_token>' -d '{"phone":"+201000000001"}'

# 3) تأكيده وإصدار الجلسة — انسخ session.access
curl -s -X POST $B/auth/phone/verify -H 'Content-Type: application/json'      -H 'Authorization: Bearer <preauth_token>'      -d '{"phone":"+201000000001","code":"<الرمز>","device_id":"dev-1"}'

# 4) تسجيل الجهاز، ثم التجهيز، ثم السحب
A='Authorization: Bearer <access>'
curl -s -X POST $B/creators/me/devices -H 'Content-Type: application/json' -H "$A"      -d '{"device_id":"dev-1","integrity_token":"t","fcm_token":"f"}'
curl -s $B/setup/autofill-dataset -H "$A"
curl -s -X POST $B/setup/complete -H 'Content-Type: application/json' -H "$A" -d '{}'
curl -s -X POST $B/withdrawals -H 'Content-Type: application/json' -H "$A" -d '{}'

# 5) محاكاة إشعار TikTok
curl -s -X POST $B/withdrawals/signals -H 'Content-Type: application/json' -H "$A"      -d '{"source":"notification","kind":"sent","amount":"100.0000","currency":"USD",
          "txn_id":"TT-1","package_sig_ok":true,"package_name":"com.zhiliaoapp.musically"}'
```

وصول المال والاعتماد والدفع تُنفَّذ اليوم من `manage.py shell`، وستصير شاشات في
لوحة الإدارة (المرحلة 3).

## الاختبارات

```bash
python -m pytest          # يحتاج PostgreSQL يعمل محليًا
python -m ruff check .
```

## التشغيل بالحاويات

```bash
cd ../infra && docker compose up -d --build
```

## قواعد لا تُخالَف

1. الكتابة في الدفتر تمر عبر `apps.ledger.services.post_transaction` فقط.
2. تغيير حالة طلب السحب يمر عبر `apps.withdrawals.state_machine.transition` فقط.
3. `received_eg` هو الانتقال الوحيد الذي يُنشئ قيدًا دائنًا لرصيد المبدع.
4. `ledger_entries` و`audit_log` للإلحاق فقط — محروسة بمشغّلات في قاعدة البيانات.
5. لا أسرار في الكود؛ كلها في `.env` ولها نظير في `.env.example`.

القرارات المعمارية موثّقة في `../docs/adr/`.
