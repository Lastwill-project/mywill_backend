from .lastwill import AbstractContractDetailsLastwill
from .lostkey import AbstractContractDetailsLostKey
from .deffered import AbstractContractDetailsDelayedPayment
from .ico import AbstractContractDetailsICO
from .ico import AbstractContractDetailsToken
from .airdrop import AbstractContractDetailsAirdrop
from .investment_pool import AbstractContractDetailsInvestmentPool
from .lostkey import AbstractContractDetailsLostKeyTokens
from lastwill.contracts.submodels.common import *



@contract_details('DUCATUSX Will contract')
class ContractDetailsDUCATUSXLastwill(AbstractContractDetailsLastwill):
    pass

@contract_details('DUCATUSX Wallet contract (lost key)')
class ContractDetailsDUCATUSXLostKey(AbstractContractDetailsLostKey):
    pass

@contract_details('DUCATUSX Deferred payment contract')
class ContractDetailsDUCATUSXDelayedPayment(AbstractContractDetailsDelayedPayment):
    pass

@contract_details('DUCATUSX MyWish ICO')
class ContractDetailsDUCATUSXICO(AbstractContractDetailsICO):
    pass


@contract_details('DUCATUSX Token contract')
class ContractDetailsDUCATUSXToken(AbstractContractDetailsToken):
    eth_contract_token = models.ForeignKey(
        EthContract,
        null=True,
        default=None,
        related_name='ducatusx_token_details_token',
        on_delete=models.SET_NULL
    )


@contract_details('DUCATUSX Airdrop')
class ContractDetailsDUCATUSXAirdrop(AbstractContractDetailsAirdrop):
    pass


@contract_details('DUCATUSX Investment Pool')
class ContractDetailsDUCATUSXInvestmentPool(AbstractContractDetailsInvestmentPool):
    pass

@contract_details('DUCATUSX Wallet contract (lost key)')
class ContractDetailsDUCATUSXLostKeyTokens(AbstractContractDetailsLostKeyTokens):
    pass
