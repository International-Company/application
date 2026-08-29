# نقطة البناء لمنصات الاستضافة التي تبني من جذر المستودع (Railway وما شابهها).
# التطبيق نفسه في backend/ وله Dockerfile مطابق يُستخدم حين يكون جذر البناء backend/.
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PORT=8000 \
    DJANGO_SETTINGS_MODULE=config.settings.prod

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential libpq-dev \
    && rm -rf /var/lib/apt/lists/*

COPY backend/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY backend/ .

# الهجرات تُنشئ مشغّلات حماية الدفتر، فتسبق إقلاع الخادم دائمًا
CMD ["sh", "-c", "python manage.py migrate --noinput && python manage.py collectstatic --noinput && gunicorn config.wsgi:application --bind 0.0.0.0:$PORT --workers 3 --timeout 60"]
