from lastwill.contracts.submodels.common import *
from .lastwill import ContractDetailsLastwill
from .lostkey import ContractDetailsLostKey
from .deffered import ContractDetailsDelayedPayment
from .ico import ContractDetailsICO
from .ico import ContractDetailsToken
from .airdrop import ContractDetailsAirdrop
from .investment_pool import ContractDetailsInvestmentPool
from .lostkey import ContractDetailsLostKeyTokens


class ContractDetailsDUCATUSXLastwill(ContractDetailsLastwill):
    pass

class ContractDetailsDUCATUSXLostKey(ContractDetailsLostKey):
    pass

class ContractDetailsDUCATUSXDelayedPayment(ContractDetailsDelayedPayment):
    pass

class ContractDetailsDUCATUSXICO(ContractDetailsICO):
    pass

class ContractDetailsDUCATUSXToken(ContractDetailsToken):
    pass

class ContractDetailsDUCATUSXAirdrop(ContractDetailsAirdrop):
    pass

class ContractDetailsDUCATUSXInvestmentPool(ContractDetailsInvestmentPool):
    pass

class ContractDetailsDUCATUSXLostKeyTokens(ContractDetailsLostKeyTokens):
    pass
