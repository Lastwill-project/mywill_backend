import requests
from django.db import models
from lastwill.settings import COINGECKO_API_URL, COINGECKO_SYMBOLS, TEMP_SYMBOLS


class RateException(Exception):
    pass


class Rate(models.Model):
    fsym = models.CharField(max_length=50)
    tsym = models.CharField(max_length=50)
    value = models.FloatField()
    last_update_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = (('fsym', 'tsym'),)

    @staticmethod
    def _get_coingecko_rate(fsym, tsym):
        response = requests.get(COINGECKO_API_URL.format(fsym=fsym, tsym=tsym))
        if response.status_code != 200:
            raise RateException('Cannot get rate from coingecko.com')

        return response.json()[fsym][tsym]

    @staticmethod
    def _get_coingecko_sym(sym):
        try:
            return COINGECKO_SYMBOLS[sym]
        except KeyError:
            raise RateException(f'Unknown symbol: {sym}')

    @classmethod
    def _get_rate(cls, fsym, tsym):
        if fsym == tsym:
            value = 1.0
        elif fsym == 'USD':
            coingecko_tsym = cls._get_coingecko_sym(tsym)
            value = 1 / cls._get_coingecko_rate(coingecko_tsym, 'usd')
        elif tsym == 'USD':
            coingecko_fsym = cls._get_coingecko_sym(fsym)
            value = cls._get_coingecko_rate(coingecko_fsym, tsym.lower())
        else:
            coingecko_fsym = cls._get_coingecko_sym(fsym)
            coingecko_tsym = cls._get_coingecko_sym(tsym)

            try:
                value = cls._get_coingecko_rate(coingecko_fsym, tsym.lower())
            except KeyError:  # if coingecko returns {} or {tsym: {}}
                fsym_usd_rate = cls._get_coingecko_rate(coingecko_fsym, 'usd')
                tsym_usd_rate = cls._get_coingecko_rate(coingecko_tsym, 'usd')
                value = fsym_usd_rate / tsym_usd_rate

        return value

    def _get_result_value(self, value):
        if self.fsym == 'TRONISH':
            return value * 0.02
        elif self.tsym == 'TRONISH':
            return value / 0.02
        else:
            return value

    def update(self):
        # check if we need replace symbol for additional rate logic
        fsym = self.fsym if self.fsym not in TEMP_SYMBOLS else TEMP_SYMBOLS[self.fsym]
        tsym = self.tsym if self.tsym not in TEMP_SYMBOLS else TEMP_SYMBOLS[self.tsym]

        raw_value = self._get_rate(fsym, tsym)

        self.value = self._get_result_value(raw_value)  # apply additional logic if required
