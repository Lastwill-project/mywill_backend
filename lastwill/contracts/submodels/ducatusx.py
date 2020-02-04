from .lastwill import ContractDetailsLastwill
from .lostkey import ContractDetailsLostKey
from .deffered import ContractDetailsDelayedPayment
from .ico import ContractDetailsICO
from .ico import ContractDetailsToken
from .airdrop import ContractDetailsAirdrop
from .investment_pool import ContractDetailsInvestmentPool
from .lostkey import ContractDetailsLostKeyTokens
import datetime

from django.core.mail import send_mail, EmailMessage
from django.utils import timezone
from rest_framework.exceptions import ValidationError

from lastwill.contracts.submodels.common import *
from lastwill.settings import AUTHIO_EMAIL, SUPPORT_EMAIL
from lastwill.consts import NET_DECIMALS, CONTRACT_GAS_LIMIT
from email_messages import *
#
#
# @contract_details('DUCATUSX Will contract')
# class ContractDetailsDUCATUSXLastwill(ContractDetailsLastwill):
#     pass
#
# @contract_details('DUCATUSX Wallet contract (lost key)')
# class ContractDetailsDUCATUSXLostKey(ContractDetailsLostKey):
#     pass

@contract_details('DUCATUSX Deferred payment contract')
class ContractDetailsDUCATUSXDelayedPayment(CommonDetails):
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

    # @blocking
    @postponable
    def deploy(self):
        return super().deploy()
#
# @contract_details('DUCATUSX MyWish ICO')
# class ContractDetailsDUCATUSXICO(ContractDetailsICO):
#     pass
#
@contract_details('DUCATUSX Token contract')
class ContractDetailsDUCATUSXToken(CommonDetails):
    token_name = models.CharField(max_length=512)
    token_short_name = models.CharField(max_length=64)
    admin_address = models.CharField(max_length=50)
    decimals = models.IntegerField()
    token_type = models.CharField(max_length=32, default='ERC20')
    eth_contract_token = models.ForeignKey(
        EthContract,
        null=True,
        default=None,
        related_name='ducatusx_token_details_token',
        on_delete=models.SET_NULL
    )
    future_minting = models.BooleanField(default=False)
    temp_directory = models.CharField(max_length=36)

    authio = models.BooleanField(default=False)
    authio_email = models.CharField(max_length=200, null=True)
    authio_date_payment = models.DateField(null=True, default=None)
    authio_date_getting = models.DateField(null=True, default=None)

    def predeploy_validate(self):
        now = timezone.now()
        token_holders = self.contract.tokenholder_set.all()
        for th in token_holders:
            if th.freeze_date:
                if th.freeze_date < now.timestamp() + 600:
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
        result = int(79 * NET_DECIMALS['USDT'])
        if 'authio' in kwargs and kwargs['authio']:
            result = int(79 + 450 * NET_DECIMALS['USDT'])
        return result

    def get_arguments(self, eth_contract_attr_name):
        return []

    def compile(self, eth_contract_attr_name='eth_contract_token'):
        print('standalone token contract compile')
        if self.temp_directory:
            print('already compiled')
            return
        dest, preproc_config = create_directory(self)
        token_holders = self.contract.tokenholder_set.all()
        preproc_params = {"constants": {"D_ONLY_TOKEN": True}}
        preproc_params['constants'] = add_token_params(
            preproc_params['constants'], self, token_holders,
            False, self.future_minting
        )
        test_token_params(preproc_config, preproc_params, dest)
        preproc_params['constants']['D_CONTRACTS_OWNER'] = self.admin_address
        with open(preproc_config, 'w') as f:
            f.write(json.dumps(preproc_params))
        if os.system('cd {dest} && yarn compile-token'.format(dest=dest)):
            raise Exception('compiler error while deploying')

        with open(path.join(dest, 'build/contracts/MainToken.json'), 'rb') as f:
            token_json = json.loads(f.read().decode('utf-8-sig'))
        with open(path.join(dest, 'build/MainToken.sol'), 'rb') as f:
            source_code = f.read().decode('utf-8-sig')
        self.eth_contract_token = create_ethcontract_in_compile(
            token_json['abi'], token_json['bytecode'][2:],
            token_json['compiler']['version'], self.contract, source_code
        )
        self.save()

    # @blocking
    @postponable
    def deploy(self, eth_contract_attr_name='eth_contract_token'):
        return super().deploy(eth_contract_attr_name)

    def get_gaslimit(self):
        return CONTRACT_GAS_LIMIT['TOKEN']

    @postponable
    @check_transaction
    def msg_deployed(self, message):
        res = super().msg_deployed(message, 'eth_contract_token')
        if not self.future_minting:
            self.contract.state = 'ENDED'
            self.contract.save()
        if self.authio and self.authio_email:
            self.authio_date_payment = datetime.datetime.now().date()
            self.authio_date_getting = self.authio_date_payment + datetime.timedelta(days=3)
            self.save()
            mint_info = ''
            token_holders = self.contract.tokenholder_set.all()
            for th in token_holders:
                mint_info = mint_info + '\n' + th.address + '\n'
                mint_info = mint_info + str(th.amount) + '\n'
                if th.freeze_date:
                    mint_info = mint_info + str(datetime.datetime.utcfromtimestamp(th.freeze_date).strftime('%Y-%m-%d %H:%M:%S')) + '\n'
            mail = EmailMessage(
                subject=authio_subject,
                body=authio_message.format(
                    address=self.eth_contract_token.address,
                    email=self.authio_email,
                    token_name=self.token_name,
                    token_short_name=self.token_short_name,
                    token_type=self.token_type,
                    decimals=self.decimals,
                    mint_info=mint_info if mint_info else 'No',
                    admin_address=self.admin_address
                ),
                from_email=DEFAULT_FROM_EMAIL,
                to=[AUTHIO_EMAIL, SUPPORT_EMAIL]
            )
            mail.send()
            send_mail(
                authio_google_subject,
                authio_google_message,
                DEFAULT_FROM_EMAIL,
                [self.authio_email]
            )
        return res

    def ownershipTransferred(self, message):
        if self.eth_contract_token.original_contract.state not in (
                'UNDER_CROWDSALE', 'ENDED'
        ):
            self.eth_contract_token.original_contract.state = 'UNDER_CROWDSALE'
            self.eth_contract_token.original_contract.save()

    def finalized(self, message):
        if self.eth_contract_token.original_contract.state != 'ENDED':
            self.eth_contract_token.original_contract.state = 'ENDED'
            self.eth_contract_token.original_contract.save()
        if (self.eth_contract_token.original_contract.id !=
                self.eth_contract_token.contract.id and
                self.eth_contract_token.contract.state != 'ENDED'):
            self.eth_contract_token.contract.state = 'ENDED'
            self.eth_contract_token.contract.save()

    def check_contract(self):
        pass

    def initialized(self, message):
        pass


class AbstractContractDetailsAirdrop(ContractDetailsAirdrop):
    class Meta:
        abstract = True

@contract_details('DUCATUSX Airdrop')
class ContractDetailsDUCATUSXAirdrop(AbstractContractDetailsAirdrop):
    pass

# @contract_details('DUCATUSX Investment Pool')
# class ContractDetailsDUCATUSXInvestmentPool(ContractDetailsInvestmentPool):
#     pass
#
# @contract_details('DUCATUSX Wallet contract (lost key)')
# class ContractDetailsDUCATUSXLostKeyTokens(ContractDetailsLostKeyTokens):
#     pass
