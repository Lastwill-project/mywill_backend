import requests
from django.db import models

COINGECKO_API_URL = 'https://api.coingecko.com/api/v3/simple/price?ids={fsym}&vs_currencies={tsym}'

COINGECKO_SYMBOL = {
    'ETH': 'ethereum',
    'WISH': 'mywish',
    'BTC': 'bitcoin',
}


class RateException(Exception):
    pass


class Rate(models.Model):
    fsym = models.CharField(max_length=50)
    tsym = models.CharField(max_length=50)
    value = models.FloatField()

    @staticmethod
    def _get_rate(fsym, tsym):
        response = requests.get(COINGECKO_API_URL.format(fsym=fsym, tsym=tsym))
        if response.status_code != 200:
            raise RateException

        return response.json()[fsym][tsym]

    def update(self):
        if self.fsym == self.tsym:
            self.value = 1.0
            self.save()
            return

        tsym = COINGECKO_SYMBOL[self.fsym]

        if self.fsym == 'USD':
            try:
                self.value = 1 / self._get_rate(self.tsym, 'usd')
                self.save()
                return
            except KeyError:
                raise RateException

        fsym = COINGECKO_SYMBOL[self.fsym]

        try:
            self.value = self._get_rate(fsym, self.tsym.lower())
            self.save()
        except KeyError:
            fsym_usd_rate = self._get_rate(fsym, 'usd')
            tsym_usd_rate = self._get_rate(tsym, 'usd')
            self.value = fsym_usd_rate / tsym_usd_rate
            self.save()
