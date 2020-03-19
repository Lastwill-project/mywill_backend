from django.db import models

from .submodels.airdrop import *
from .submodels.lastwill import *
from .submodels.deffered import *
from .submodels.ico import *
from .submodels.common import *
from .submodels.investment_pool import *


class CurrencyStatisticsCache(models.Model):
    id = models.IntegerField(default=1, null=False, primary_key=True)
    wish_price_usd = models.FloatField(default=0, null=True)
    wish_usd_percent_change_24h = models.FloatField(default=0, null=True)
    wish_price_eth = models.FloatField(default=0, null=True)
    wish_eth_percent_change_24h = models.FloatField(default=0, null=True)
    mywish_rank = models.FloatField(default=0, null=True)
    btc_price_usd = models.FloatField(default=0, null=True)
    btc_percent_change_24h = models.FloatField(default=0, null=True)
    bitcoin_rank = models.FloatField(default=0, null=True)
    eth_price_usd = models.FloatField(default=0, null=True)
    eth_percent_change_24h = models.FloatField(default=0, null=True)
    eth_rank = models.FloatField(default=0, null=True)
    eos_price_usd = models.FloatField(default=0, null=True)
    eos_percent_change_24h = models.FloatField(default=0, null=True)
    eos_rank = models.FloatField(default=0, null=True)
    eosish_price_eos = models.FloatField(default=0, null=True)
    eosish_price_usd = models.FloatField(default=0, null=True)
    usd_price_rub = models.FloatField(default=0, null=True)
    usd_percent_change_24h = models.FloatField(default=0, null=True)
    updated_at = models.DateTimeField(auto_now_add=True)
