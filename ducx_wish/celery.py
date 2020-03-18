#from __future__ import absolute_import
import os
from celery import Celery
from celery.schedules import crontab
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'ducx_wish.settings')
import django
django.setup()

app = Celery('ducx_wish')
app.autodiscover_tasks()
