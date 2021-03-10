import time
from lastwill.celery import app
from lastwill.rates.models import Rate


@app.task()
def update_rates():
    rates = Rate.objects.all()
    for rate in rates:
        rate.update()
        time.sleep(5)


def convert(amount, fsym, tsym):
    try:
        rate = Rate.objects.get(fsym=fsym, tsym=tsym)
    except Rate.DoesNotExist:
        rate = Rate(fsym=fsym, tsym=tsym)
        rate.update()
        rate.save()

    return amount * rate.value
