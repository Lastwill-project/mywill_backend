import time
from lastwill.celery import app
from lastwill.rates.models import Rate


@app.task()
def update_rates():
    rates = Rate.objects.all()
    for rate in rates:
        rate.update()
        time.sleep(5)


def rate(fsym, tsym):
    try:
        rate_obj = Rate.objects.get(fsym=fsym, tsym=tsym)
    except Rate.DoesNotExist:
        rate_obj = Rate(fsym=fsym, tsym=tsym)
        rate_obj.update()
        rate_obj.save()

    return rate_obj.value
