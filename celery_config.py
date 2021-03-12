import os
from celery import Celery
from celery.schedules import crontab

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'lastwill.settings')
import django
django.setup()

app = Celery('mywish', broker='amqp://java:java@localhost:5672/mywill', include=['lastwill.rates.api'])
app.conf.update(result_expires=3600, enable_utc=True, timezone='Europe/Moscow')

app.conf.beat_schedule['update_rates'] = {
    'task': 'lastwill.rates.api.update_rates',
    'schedule': crontab(minute=f'*/5'),
}
