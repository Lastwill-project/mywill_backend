import requests
from django.db import models

COINGECKO_API_URL = 'https://api.coingecko.com/api/v3/simple/price?ids={fsym}&vs_currencies={tsym}'

COINGECKO_SYMBOL = {
    'ETH': 'ethereum',
    'WISH': 'mywish',
    'BTC': 'bitcoin',
    'OKB': 'okb',
    'RBC': 'rubic',
    'EOS': 'eos',
    'TRX': 'tron',
    'BNB': 'binancecoin',
    'USDT': 'tether',
    'EOSISH': 'eosish',
    'NEO': 'neo',
    'SWAP': 'swaps-network',
}

TEMP_CURRENCY = {
    'TRONISH': 'TRX'
}


class RateException(Exception):
    pass


class Rate(models.Model):
    fsym = models.CharField(max_length=50)
    tsym = models.CharField(max_length=50)
    value = models.FloatField()

    class Meta:
        unique_together = (('fsym', 'tsym'),)

    @staticmethod
    def _get_coingecko_rate(fsym, tsym):
        response = requests.get(COINGECKO_API_URL.format(fsym=fsym, tsym=tsym))
        if response.status_code != 200:
            raise RateException

        return response.json()[fsym][tsym]

    def _get_rate(self, fsym, tsym):
        if fsym == tsym:
            return 1.0
        if fsym == 'USD':
            return 1 / self._get_coingecko_rate(COINGECKO_SYMBOL[tsym], 'usd')

        try:
            value = self._get_coingecko_rate(COINGECKO_SYMBOL[fsym], tsym.lower())
        except KeyError:
            fsym_usd_rate = self._get_coingecko_rate(COINGECKO_SYMBOL[fsym], 'usd')
            tsym_usd_rate = self._get_coingecko_rate(COINGECKO_SYMBOL[tsym], 'usd')
            value = fsym_usd_rate / tsym_usd_rate

        return value

    def _result_value(self, value):
        if self.fsym == 'TRONISH':
            return value * 0.02
        elif self.tsym == 'TRONISH':
            return value / 0.02
        else:
            return value

    def update(self):
        fsym = self.fsym if self.fsym not in TEMP_CURRENCY else TEMP_CURRENCY[self.fsym]
        tsym = self.tsym if self.tsym not in TEMP_CURRENCY else TEMP_CURRENCY[self.tsym]

        temp_value = self._get_rate(fsym, tsym)

        self.value = self._result_value(temp_value)
