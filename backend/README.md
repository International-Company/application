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
