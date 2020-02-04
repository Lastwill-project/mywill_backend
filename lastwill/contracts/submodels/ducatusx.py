from lastwill.contracts.submodels.common import *
from .lastwill import ContractDetailsLastwill
from .lostkey import ContractDetailsLostKey
from .deffered import ContractDetailsDelayedPayment
from .ico import ContractDetailsICO
from .ico import ContractDetailsToken
from .airdrop import ContractDetailsAirdrop
from .investment_pool import ContractDetailsInvestmentPool
from .lostkey import ContractDetailsLostKeyTokens


@contract_details('DUCATUSX Will contract')
class ContractDetailsDUCATUSXLastwill(ContractDetailsLastwill):
    pass

@contract_details('DUCATUSX Wallet contract (lost key)')
class ContractDetailsDUCATUSXLostKey(ContractDetailsLostKey):
    pass

@contract_details('DUCATUSX Deferred payment contract')
class ContractDetailsDUCATUSXDelayedPayment(ContractDetailsDelayedPayment):
    pass

@contract_details('DUCATUSX MyWish ICO')
class ContractDetailsDUCATUSXICO(ContractDetailsICO):
    pass

@contract_details('DUCATUSX Token contract')
class ContractDetailsDUCATUSXToken(ContractDetailsToken):
    pass

@contract_details('DUCATUSX Airdrop')
class ContractDetailsDUCATUSXAirdrop(ContractDetailsAirdrop):
    pass

@contract_details('DUCATUSX Investment Pool')
class ContractDetailsDUCATUSXInvestmentPool(ContractDetailsInvestmentPool):
    pass

@contract_details('DUCATUSX Wallet contract (lost key)')
class ContractDetailsDUCATUSXLostKeyTokens(ContractDetailsLostKeyTokens):
    pass
