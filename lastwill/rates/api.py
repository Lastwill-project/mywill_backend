import time
import traceback
import sys
from celery import shared_task
from lastwill.rates.models import Rate


@shared_task
def update_rates():
    rates = Rate.objects.all()
    for rate in rates:
        old_value = rate.value
        try:
            rate.update()
            rate.save()
            print(f'{rate.fsym} -> {rate.tsym} rate updated: {rate.value} (bias={abs(rate.value - old_value)})',
                  flush=True)
        except Exception:
            print('\n'.join(traceback.format_exception(*sys.exc_info())), flush=True)

        time.sleep(5)


def rate(fsym, tsym):
    try:
        rate_obj = Rate.objects.get(fsym=fsym, tsym=tsym)
    except Rate.DoesNotExist:
        rate_obj = Rate(fsym=fsym, tsym=tsym)
        rate_obj.update()
        try:
            rate_obj.save()
        except Exception:  # if object was generated by another thread yet
            rate_obj = Rate.objects.get(fsym=fsym, tsym=tsym)

    return rate_obj.value
