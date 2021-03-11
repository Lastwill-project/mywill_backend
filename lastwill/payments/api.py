import datetime

from django.contrib.auth.models import User
from django.db.models import F

from rest_framework.exceptions import ValidationError

from lastwill.payments.models import InternalPayment, FreezeBalance
from lastwill.profile.models import Profile, UserSiteBalance, SubSite
from lastwill.settings import MY_WISH_URL, TRON_URL, SWAPS_URL, TOKEN_PROTECTOR_URL, NETWORKS, RUBIC_EXC_URL, RUBIC_FIN_URL
from lastwill.consts import NET_DECIMALS
from lastwill.rates.api import rate


def create_payment(uid, tx, currency, amount, site_id, network=None):
    amount = float(amount)
    if amount == 0.0:
        return
    print('create payment')
    if (SubSite.objects.get(id=site_id).site_name == MY_WISH_URL
            or SubSite.objects.get(id=site_id).site_name == TRON_URL):
        if currency in ['BWISH', 'BBNB', 'BSCWISH', 'WWISH']:
            amount = amount * 10 ** 10
            if currency == 'BBNB':
                currency = 'BNB'
            else:
                amount *= 1.1

        value = amount if (currency in ['WISH', 'BWISH', 'BSCWISH', 'WWISH']) else amount * rate(currency, 'WISH')
        if currency == 'BTC':
            value = value * NET_DECIMALS['ETH'] / NET_DECIMALS['BTC']
        if currency in ['TRON', 'TRX', 'TRONISH']:
            value = value * NET_DECIMALS['ETH'] / NET_DECIMALS['TRX']
        if currency in ['EOS', 'EOSISH']:
            value = value * NET_DECIMALS['ETH'] / NET_DECIMALS['EOS']
        if currency == 'USDT':
            value = value * NET_DECIMALS['ETH'] / NET_DECIMALS['USDT']
    elif SubSite.objects.get(id=site_id).site_name in [SWAPS_URL, RUBIC_EXC_URL, RUBIC_FIN_URL]:
        value = amount if currency == 'USDT' else amount * float(rate(
            currency, 'USDT'
        )) / NET_DECIMALS[currency] * NET_DECIMALS['USDT']

    elif SubSite.objects.get(id=site_id).site_name == TOKEN_PROTECTOR_URL:
        value = amount if currency == 'USDT' else amount * float(rate(
            currency, 'USDT'
        )) / NET_DECIMALS[currency] * NET_DECIMALS['USDT']
    else:
        amount = calculate_decimals(currency, amount)
        value = amount if currency == 'EOSISH' else amount * rate(currency, 'EOSISH') * NET_DECIMALS['EOSISH']
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


def freeze_payments(amount, network):
    if network == 'EOS_MAINNET':
    #if currency in ('EOS', 'EOSISH'):
        value = amount * 0.15 * NET_DECIMALS['EOSISH'] / NET_DECIMALS['ETH']
        value *= rate('WISH', 'EOSISH')
        #value = float(':.4f'.format(value)
        FreezeBalance.objects.select_for_update().filter(id=1).update(
            eosish=F('eosish') + value
        )
        print('FREEZE', value, 'EOSISH', flush=True)
    elif network == 'TRON_MAINNET':
    #elif currency in ('TRON', 'TRONISH'):
        value = amount * 0.10 * NET_DECIMALS['TRX'] / NET_DECIMALS['ETH']
        value *= rate('WISH', 'TRONISH')
        FreezeBalance.objects.select_for_update().filter(id=1).update(
            tronish=F('tronish') + int(value)
        )
        wish_value = amount * 0.10
        FreezeBalance.objects.select_for_update().filter(id=1).update(
            wish=F('wish') + wish_value
        )
        print('FREEZE', int(value), 'TRONISH', flush=True)
        #print('FREEZE', wish_value, 'WISH', flush=True)
    #elif currency in ('BNB', 'BWISH'):
    else:
        value = amount * 0.10
        FreezeBalance.objects.select_for_update().filter(id=1).update(
            bwish=F('bwish') + value
        )
        print('FREEZE', value, 'BWISH', flush=True)
    # if network == 'ETHEREUM_MAINNET':
    #    value = amount * 0.10
    #    FreezeBalance.objects.select_for_update().filter(id=1).update(
    #        wish=F('wish') + value
    #    )
    #    print('FREEZE', value, 'WISH', flush=True)


def positive_payment(user, value, site_id, currency, amount):
    UserSiteBalance.objects.select_for_update().filter(
        user=user, subsite__id=site_id).update(
            balance=F('balance') + value)


def negative_payment(user, value, site_id, network):
    if not UserSiteBalance.objects.select_for_update().filter(
            user=user, subsite__id=site_id, balance__gte=value
    ).update(balance=F('balance') - value):
        raise ValidationError({'result': 3}, code=400)
    if not NETWORKS[network]['is_free']:
        freeze_payments(value, network)


def get_payment_statistics(start, stop=None):
    if not stop:
        stop = datetime.datetime.now().date()
    payments = InternalPayment.objects.filter(
        delta__gte=0, datetime__gte=start, datetime__lte=stop
    ).order_by('datetime')

    total_payments = {
        'ETH': 0.0,
        'WISH': 0.0,
        'BTC': 0.0,
        'BNB': 0.0,
        'EOS': 0.0,
        'EOSISH': 0.0,
        'TRX': 0.0,
        'TRONISH': 0.0,
        'BWISH': 0.0,
        'SWAP': 0.0,
        'OKB': 0.0,
        'RBC': 0.0,
        'BSCWISH': 0.0,
        'WWISH': 0.0
    }

    user_ids = []
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
        user_ids.append(pay.user.id)

    print('total_payments', total_payments, flush=True)
    return user_ids
