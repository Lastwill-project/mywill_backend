import time
from lastwill.celery import app
from lastwill.rates.models import Rate


@app.task()
def update_rates():
    rates = Rate.objects.all()
    for rate in rates:
        rate.update()
        time.sleep(5)


def convert(amount, from_cur, to_cur):
    try:
        rate = Rate.objects.get(from_cur=from_cur, to_cur=to_cur)
    except Rate.DoesNotExist:
        rate = Rate(from_cur=from_cur, to_cur=to_cur)
        rate.update()
        rate.save()

    return amount * rate.value
