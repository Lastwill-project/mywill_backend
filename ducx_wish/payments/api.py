import datetime

from django.contrib.auth.models import User
from django.db.models import F

from rest_framework.exceptions import ValidationError

from ducx_wish.payments.models import InternalPayment
from ducx_wish.profile.models import Profile, UserSiteBalance, SubSite
from ducx_wish.settings import MY_WISH_URL, TRON_URL, SWAPS_URL, TOKEN_PROTECTOR_URL, NETWORKS
from ducx_wish.consts import NET_DECIMALS
from exchange_API import to_wish, convert


def create_payment(uid, tx, currency, amount, site_id, network=None):
    amount = float(amount)
    if amount == 0.0:
        return
    print('create payment')
    if (SubSite.objects.get(id=site_id).site_name == MY_WISH_URL
            or SubSite.objects.get(id=site_id).site_name == TRON_URL):
        if currency in ['BWISH', 'BBNB']:
            amount = amount * 10 ** 10
            if currency in ['BWISH']:
                amount *= 1.1
            if currency == 'BBNB':
                currency = 'BNB'
        value = amount if (currency in ['WISH', 'BWISH']) else to_wish(
            currency, amount
        )
        if currency == 'BTC':
            value = value * NET_DECIMALS['ETH'] / NET_DECIMALS['BTC']
        if currency in ['TRON', 'TRX', 'TRONISH']:
            value = value * NET_DECIMALS['ETH'] / NET_DECIMALS['TRX']
        if currency in ['EOS', 'EOSISH']:
            value = value * NET_DECIMALS['ETH'] / NET_DECIMALS['EOS']
        if currency == 'USDT':
            value = value * NET_DECIMALS['ETH'] / NET_DECIMALS['USDT']
    # elif SubSite.objects.get(id=site_id).site_name == TRON_URL:
    #     value = amount if currency in ('TRONISH', 'TRX') else amount * float(convert(
    #         currency, 'TRX'
    #     )['TRX']) / NET_DECIMALS[currency] * NET_DECIMALS['TRON']
    elif SubSite.objects.get(id=site_id).site_name == SWAPS_URL:
        value = amount if currency == 'USDT' else amount * float(convert(
            currency, 'USDT'
        )['USDT']) / NET_DECIMALS[currency] * NET_DECIMALS['USDT']

    elif SubSite.objects.get(id=site_id).site_name == TOKEN_PROTECTOR_URL:
        value = amount if currency == 'USDT' else amount * float(convert(
            currency, 'USDT'
        )['USDT']) / NET_DECIMALS[currency] * NET_DECIMALS['USDT']
    else:
        amount = calculate_decimals(currency, amount)
        value = amount if currency == 'EOSISH' else amount * convert(currency, 'EOSISH')['EOSISH'] * NET_DECIMALS['EOSISH']
        amount = add_decimals(currency, amount)
    user = User.objects.get(id=uid)
    if amount < 0.0:
        if site_id == 4 or site_id == 5:
            try:
                negative_payment(user, -value, site_id, network)
            except:
                print('-5% payment', flush=True)
                value = value * 0.95
                negative_payment(user, -value, site_id, network)
        else:
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


def negative_payment(user, value, site_id, network):
    if not UserSiteBalance.objects.select_for_update().filter(
            user=user, subsite__id=site_id, balance__gte=value
    ).update(balance=F('balance') - value):
        raise ValidationError({'result': 3}, code=400)


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
