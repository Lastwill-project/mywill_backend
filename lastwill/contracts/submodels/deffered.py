from django.db import models
from django.core.mail import send_mail
from django.utils import timezone
from rest_framework.exceptions import ValidationError

from lastwill.contracts.submodels.common import *
from lastwill.consts import NET_DECIMALS, CONTRACT_GAS_LIMIT
from email_messages import *



class AbstractContractDetailsDelayedPayment(CommonDetails):
    class Meta:
        abstract = True

    sol_path = 'lastwill/delayed-payment/'
    source_filename = 'contracts/DelayedPayment.sol'
    result_filename = 'build/contracts/DelayedPayment.json'
    date = models.DateTimeField()
    user_address = models.CharField(max_length=50)
    recepient_address = models.CharField(max_length=50)
    recepient_email = models.CharField(max_length=200, null=True)
    eth_contract = models.ForeignKey(EthContract, null=True, default=None)

    def predeploy_validate(self):
        now = timezone.now()
        if self.date < now:
            raise ValidationError({'result': 1}, code=400)

    @classmethod
    def min_cost(cls):
        network = Network.objects.get(name='ETHEREUM_MAINNET')
        cost = cls.calc_cost({}, network)
        return cost

    @staticmethod
    def calc_cost(kwargs, network):
        if NETWORKS[network.name]['is_free']:
            return 0
        return 30 * NET_DECIMALS['USDT']

    def fundsAdded(self, message):
        pass

    @postponable
    @check_transaction
    def msg_deployed(self, message):
        super().msg_deployed(message)

    def checked(self, message):
        pass

    def triggered(self, message):
        link = NETWORKS[self.eth_contract.contract.network.name]['link_tx']
        if self.recepient_email:
            send_mail(
                heir_subject,
                heir_message.format(
                    user_address=self.recepient_address,
                    link_tx=link.format(tx=message['transactionHash'])
                ),
                DEFAULT_FROM_EMAIL,
                [self.recepient_email]
            )
        self.contract.state = 'TRIGGERED'
        self.contract.save()
        if self.contract.user.email:
            send_mail(
                carry_out_subject,
                carry_out_message,
                DEFAULT_FROM_EMAIL,
                [self.contract.user.email]
            )

    def get_arguments(self, *args, **kwargs):
        return [
            self.user_address,
            self.recepient_address,
            2 ** 256 - 1,
            int(self.date.timestamp()),
        ]

    def get_gaslimit(self):
        return CONTRACT_GAS_LIMIT['DEFFERED']

    @blocking
    @postponable
    def deploy(self):
        return super().deploy()



@contract_details('Deferred payment contract')
class ContractDetailsDelayedPayment(AbstractContractDetailsDelayedPayment):
    pass
