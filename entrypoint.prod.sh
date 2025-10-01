#!/bin/sh


python manage.py collectstatic --noinput
python manage.py migrate --noinput
python -m gunicorn --bind 0.0.0.0:8000 --workers 2 --worker-class gthread --threads 4 --timeout 0 config.wsgi:application
