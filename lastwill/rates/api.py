import time
from celery import shared_task
from lastwill.rates.models import Rate


@shared_task
def update_rates():
    rates = Rate.objects.all()
    for rate in rates:
        rate.update()
        print(f'{rate.fsym} -> {rate.tsym} rate updated: {rate.value}', flush=True)
        time.sleep(5)


def rate(fsym, tsym):
    try:
        rate_obj = Rate.objects.get(fsym=fsym, tsym=tsym)
    except Rate.DoesNotExist:
        rate_obj = Rate(fsym=fsym, tsym=tsym)
        rate_obj.update()
        rate_obj.save()

    return rate_obj.value
