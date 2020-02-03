from .common import CommonDetails
from .lastwill import ContractDetailsLastwill
from .lostkey import ContractDetailsLostKey
from .deffered import ContractDetailsDelayedPayment
from .ico import ContractDetailsICO
from .ico import ContractDetailsToken
from .airdrop import ContractDetailsAirdrop
from .investment_pool import ContractDetailsInvestmentPool
from .lostkey import ContractDetailsLostKeyTokens


class ContractDetailsDUCATUSXLastwill(CommonDetails, ContractDetailsLastwill):
    pass

class ContractDetailsDUCATUSXLostKey(CommonDetails, ContractDetailsLostKey):
    pass

class ContractDetailsDUCATUSXDelayedPayment(CommonDetails, ContractDetailsDelayedPayment):
    pass

class ContractDetailsDUCATUSXICO(CommonDetails, ContractDetailsICO):
    pass

class ContractDetailsDUCATUSXToken(CommonDetails, ContractDetailsToken):
    pass

class ContractDetailsDUCATUSXAirdrop(CommonDetails, ContractDetailsAirdrop):
    pass

class ContractDetailsDUCATUSXInvestmentPool(CommonDetails, ContractDetailsInvestmentPool):
    pass

class ContractDetailsDUCATUSXLostKeyTokens(CommonDetails, ContractDetailsLostKeyTokens):
    pass
