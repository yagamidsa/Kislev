release: python manage.py migrate --noinput && python manage.py collectstatic --noinput
web: gunicorn kislevsmart.wsgi:application --workers 2 --threads 4 --worker-class gthread --timeout 120 --bind 0.0.0.0:$PORT
