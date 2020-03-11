import requests
import json
import time
from binance.client import Client
from lastwill.settings import BINANCE_PAYMENT_ADDRESS, BINANCE_PAYMENT_PASSWORD


class memoize_timeout:
    def __init__(self, timeout):
        self.timeout = timeout
        self.cache = {}

    def __call__(self, f):
        def func(*args, **kwargs):
            key = (args, tuple(sorted(kwargs.items())))
            v = self.cache.get(key, (0, 0))
            # print('cache')
            if time.time() - v[1] > self.timeout:
                # print('updating')
                v = self.cache[key] = f(*args, **kwargs), time.time()
            return v[0]

        return func


@memoize_timeout(10 * 60)
def convert(fsym, tsyms):
    eosish_factor = 1.0
    swap_factor = 1.0
    wish_factor = 1.0
    reverse_convert_eos = False
    reverse_convert_swap = False
    reverse_convert_wish = False
    allowed = {'WISH', 'USD', 'ETH', 'EUR', 'BTC', 'NEO', 'EOS', 'EOSISH', 'BNB', 'TRX', 'TRONISH', 'USDT', 'WAVES',
               'SWAP'}
    if fsym == 'EOSISH' or tsyms == 'EOSISH':
        eosish_factor = float(
            requests.get('https://api.coingecko.com/api/v3/simple/price?ids=eosish&vs_currencies=eos')
            .json()['eosish']['eos']
        )
        print('eosish factor', eosish_factor, flush=True)
        if fsym == 'EOSISH':
            fsym = 'EOS'
            if tsyms == fsym:
                return {'EOS': eosish_factor}
        else:
            tsyms = 'EOS'
            if tsyms == fsym:
                return {'EOSISH': 1 / eosish_factor}
            reverse_convert_eos = True
            eosish_factor = 1 / eosish_factor
    tronish = False
    if tsyms == 'TRONISH':
        if fsym == 'TRX':
            return {'TRONISH': 0.02}
        else:
            tsyms = 'TRX'
            tronish = True
    if fsym == 'TRONISH':
        fsym = 'TRX'
        answer = json.loads(requests.get(
            'http://127.0.0.1:5001/convert?fsym={fsym}&tsyms={tsyms}'.format(
                fsym=fsym, tsyms=tsyms)
        ).content.decode())
        answer[tsyms] = answer[tsyms] * 0.02
        return answer
    if fsym == 'SWAP' or tsyms == 'SWAP':
        swap_factor = float(
            requests.get('https://api.coingecko.com/api/v3/simple/price?ids=swaps-network&vs_currencies=eth')
            .json()['swaps-network']['eth']
            )
        print('swap factor', swap_factor, flush=True)
        if fsym == 'SWAP':
            fsym = 'ETH'
            if tsyms == fsym:
                return {'ETH': swap_factor}
        else:
            tsyms = 'ETH'
            if tsyms == fsym:
                return {'SWAP': 1 / swap_factor}
            reverse_convert_swap = True
            swap_factor = 1 / swap_factor
    if fsym == 'WISH' or tsyms == 'WISH':
        wish_factor = float(
            requests.get('https://api.coingecko.com/api/v3/simple/price?ids=mywish&vs_currencies=eth')
            .json()['mywish']['eth']
            )
        print('wish factor', wish_factor, flush=True)
        if fsym == 'WISH':
            fsym = 'ETH'
            if tsyms == fsym:
                return {'ETH': wish_factor}
        else:
            tsyms = 'ETH'
            if tsyms == fsym:
                return {'WISH': 1 / wish_factor}
            reverse_convert_wish = True
            wish_factor = 1 / wish_factor

    if fsym not in allowed or any([x not in allowed for x in tsyms.split(',')]):
        raise Exception('currency not allowed')
    # print(fsym, tsyms)
    answer = json.loads(requests.get(
        'http://127.0.0.1:5001/convert?fsym={fsym}&tsyms={tsyms}'.format(fsym=fsym, tsyms=tsyms)
    ).content.decode())
    # print('currency_proxi answer', answer, flush=True)
    if reverse_convert_eos:
        answer = {'EOSISH': answer['EOS']}
        tsyms = 'EOSISH'
    if reverse_convert_swap:
        answer = {'SWAP': answer['ETH']}
        tsyms = 'SWAP'
    if reverse_convert_wish:
        answer = {'WISH': answer['ETH']}
        tsyms = 'WISH'
    if eosish_factor != 1.0:
        answer[tsyms] = answer[tsyms] * eosish_factor
    if swap_factor != 1.0:
        answer[tsyms] = answer[tsyms] * swap_factor
    if wish_factor != 1.0:
        answer[tsyms] = answer[tsyms] * wish_factor
    if tronish:
        answer['TRONISH'] = answer['TRX'] / 0.02
    return answer


def to_wish(curr, amount=1):
    return amount * (convert(curr, 'WISH')['WISH'])


def swap_to_wish(amount=1):
    return amount * to_wish('SWAP', amount)


def bnb_to_wish():
    client = Client(BINANCE_PAYMENT_ADDRESS, BINANCE_PAYMENT_PASSWORD)
    client.API_URL = 'https://dex.binance.org/api'
    wish_price = client.get_ticker(symbol='WISH-2D5_BNB')[0]['lastPrice']
    return 1 / float(wish_price)
