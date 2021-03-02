from lastwill.contracts.submodels.airdrop import AbstractContractDetailsAirdrop
from lastwill.contracts.submodels.common import *
from lastwill.consts import NET_DECIMALS, CONTRACT_PRICE_USDT
from lastwill.settings import BSC_WEB3_ATTEMPTS


@contract_details('Binance Airdrop')
class ContractDetailsBinanceAirdrop(AbstractContractDetailsAirdrop):

    @staticmethod
    def calc_cost(kwargs, network):
        if NETWORKS[network.name]['is_free']:
            return 0
        price = CONTRACT_PRICE_USDT['BINANCE_AIRDROP']
        if 'verification' in kwargs and kwargs['verification']:
            price += VERIFICATION_PRICE_USDT
        return price * NET_DECIMALS['USDT']

    @classmethod
    def min_cost(cls):
        network = Network.objects.get(name='BINANCE_SMART_MAINNET')
        cost = cls.calc_cost({}, network)
        return cost

    @blocking
    @postponable
    def deploy(self):
        return super().deploy(attempts=BSC_WEB3_ATTEMPTS)
