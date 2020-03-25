import datetime

from django.contrib.auth.models import User
from django.db.models import F

from rest_framework.exceptions import ValidationError

from ducx_wish.payments.models import InternalPayment
from ducx_wish.profile.models import Profile, UserSiteBalance, SubSite
from ducx_wish.settings import DUCATUSX_URL
from ducx_wish.consts import NET_DECIMALS
from exchange_API import to_wish, convert


def create_payment(uid, tx, currency, amount, site_id, network=None):
    amount = float(amount)
    if amount == 0.0:
        return
    print('create payment')
    if not SubSite.objects.get(id=site_id).site_name == DUCATUSX_URL:
         raise Exception('Payment site is not ducatusx')
    else:
        value = amount
    user = User.objects.get(id=uid)
    if amount < 0.0:
        # if site_id == 4 or site_id == 5:
        #     try:
        #         negative_payment(user, -value, site_id, network)
        #     except:
        #         print('-5% payment', flush=True)
        #         value = value * 0.95
        #         negative_payment(user, -value, site_id, network)
        # else:
        #     negative_payment(user, -value, site_id, network)
        negative_payment(user, -value, site_id, network)
    else:
        positive_payment(user, value, site_id, currency, amount)
    site = SubSite.objects.get(id=site_id)
    InternalPayment(
        user_id=uid,
        delta=value,
        tx_hash=tx,
        original_currency=currency,
        original_delta=str(amount),
        site=site
    ).save()
    print('PAYMENT: Created', flush=True)
    print('PAYMENT: Received {amount} {curr} ({wish_value} WISH) from user {email}, id {user_id} with TXID: {txid} at site: {sitename}'
          .format(amount=amount, curr=currency, wish_value=value, email=user, user_id=uid, txid=tx, sitename=site_id),
          flush=True)


def calculate_decimals(currency, amount):
    # count sum payments without decimals
    if currency in ['ETH']:
        amount = amount / NET_DECIMALS['ETH']
    if currency in ['BTC']:
        amount = amount / NET_DECIMALS['BTC']
    if currency in ['EOS']:
        amount = amount / NET_DECIMALS['EOS']
    return amount


def add_decimals(currency, amount):
    # add decimals for eth, btc
    if currency in ['ETH']:
        amount = amount * NET_DECIMALS['ETH']
    if currency in ['BTC']:
        amount = amount * NET_DECIMALS['BTC']
    if currency in ['EOS']:
        amount = amount * NET_DECIMALS['EOS']
    return amount




def positive_payment(user, value, site_id, currency, amount):
    UserSiteBalance.objects.select_for_update().filter(
        user=user, subsite__id=site_id).update(
            balance=F('balance') + value)
    print('positive payment ok', flush=True)


def negative_payment(user, value, site_id, network):
    if not UserSiteBalance.objects.select_for_update().filter(
            user=user, subsite__id=site_id, balance__gte=value
    ).update(balance=F('balance') - value):
        raise ValidationError({'result': 3}, code=400)
    print('negative payment ok', flush=True)


def get_payment_statistics(start, stop=None):
    if not stop:
        stop = datetime.datetime.now().date()
    payments = InternalPayment.objects.filter(
        delta__gte=0, datetime__gte=start, datetime__lte=stop
    ).order_by('datetime')
    total_payments = {'ETH': 0.0, 'WISH': 0.0, 'BTC': 0.0, 'BNB': 0.0, 'EOS': 0.0, 'EOSISH': 0.0, 'TRX': 0.0, 'TRONISH': 0.0, 'BWISH': 0.0, 'SWAP': 0.0}
    for pay in payments:
        print(
            pay.datetime.date(),
            pay.user.id, pay.user.email,
            float(pay.original_delta)/NET_DECIMALS[pay.original_currency],
            pay.original_currency,
            'site id', pay.site.id,
            flush=True
        )
        total_payments[pay.original_currency] += float(pay.original_delta)/NET_DECIMALS[pay.original_currency]

    print('total_payments', total_payments, flush=True)
