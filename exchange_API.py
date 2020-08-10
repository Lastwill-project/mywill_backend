import requests
import json
import time

from binance.client import Client

from ducx_wish.settings import RATES_API_URL


def convert(fsym, tsyms):
    allowed = {'USD', 'DUC', 'DUCX', 'USDC'}

    if fsym not in allowed or any([x not in allowed for x in tsyms.split(',')]):
        raise Exception('currency not allowed')

    duc_usd_price = json.loads(requests.get(RATES_API_URL.format(fsym='DUC', tsyms='USD')).content).get('USD')
    ducx_usd_price = json.loads(requests.get(RATES_API_URL.format(fsym='DUCX', tsyms='USD')).content).get('USD')

    if fsym == 'USD' and tsyms == 'DUC':
        amount = 1 / duc_usd_price
    elif fsym == 'USD' and tsyms == 'DUCX':
        amount = 1 / ducx_usd_price
    elif fsym == 'USDC' and tsyms == 'DUCX':
        amount = 1 / ducx_usd_price
    elif fsym == 'DUC' and tsyms == 'USD':
        amount = duc_usd_price
    elif fsym == 'DUCX' and tsyms == 'USD':
        amount = ducx_usd_price
    elif fsym == 'DUCX' and tsyms == 'USDC':
        amount = ducx_usd_price
    elif fsym == 'DUC' and tsyms == 'DUCX':
        amount = duc_usd_price / ducx_usd_price
    elif fsym == 'DUCX' and tsyms == 'DUC':
        amount = ducx_usd_price / duc_usd_price
    else:
        amount = 1

    answer = {tsyms: amount}

    return answer


def to_wish(curr, amount=1):
    return amount * (convert(curr, 'WISH')['WISH'])


def swap_to_wish(amount=1):
    return amount * to_wish('SWAP', amount)

