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
    contract = models.ForeignKey(Contract)

@contract_details('DUCATUSX Wallet contract (lost key)')
class ContractDetailsDUCATUSXLostKey(ContractDetailsLostKey):
    contract = models.ForeignKey(Contract)

@contract_details('DUCATUSX Deferred payment contract')
class ContractDetailsDUCATUSXDelayedPayment(ContractDetailsDelayedPayment):
    contract = models.ForeignKey(Contract)

@contract_details('DUCATUSX MyWish ICO')
class ContractDetailsDUCATUSXICO(ContractDetailsICO):
    contract = models.ForeignKey(Contract)

@contract_details('DUCATUSX Token contract')
class ContractDetailsDUCATUSXToken(ContractDetailsToken):
    contract = models.ForeignKey(Contract)

@contract_details('DUCATUSX Airdrop')
class ContractDetailsDUCATUSXAirdrop(ContractDetailsAirdrop):
    contract = models.ForeignKey(Contract)

@contract_details('DUCATUSX Investment Pool')
class ContractDetailsDUCATUSXInvestmentPool(ContractDetailsInvestmentPool):
    contract = models.ForeignKey(Contract)

@contract_details('DUCATUSX Wallet contract (lost key)')
class ContractDetailsDUCATUSXLostKeyTokens(ContractDetailsLostKeyTokens):
    contract = models.ForeignKey(Contract)
