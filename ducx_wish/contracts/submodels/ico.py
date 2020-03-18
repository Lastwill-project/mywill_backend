import datetime

from ethereum import abi

from django.db import models
from django.core.mail import send_mail, EmailMessage
from django.contrib.postgres.fields import JSONField
from django.utils import timezone
from rest_framework.exceptions import ValidationError

from ducx_wish.contracts.submodels.common import *
from ducx_wish.settings import AUTHIO_EMAIL, SUPPORT_EMAIL
from ducx_wish.consts import NET_DECIMALS, CONTRACT_GAS_LIMIT
from email_messages import *


@contract_details('MyWish ICO')
class ContractDetailsICO(CommonDetails):
    sol_path = 'ducx_wish/contracts/contracts/ICO.sol'

    soft_cap = models.DecimalField(
        max_digits=MAX_WEI_DIGITS, decimal_places=0, null=True
    )
    hard_cap = models.DecimalField(
        max_digits=MAX_WEI_DIGITS, decimal_places=0, null=True
    )
    token_name = models.CharField(max_length=512)
    token_short_name = models.CharField(max_length=64)
    admin_address = models.CharField(max_length=50)
    is_transferable_at_once = models.BooleanField(default=False)
    start_date = models.IntegerField()
    stop_date = models.IntegerField()
    rate = models.DecimalField(
        max_digits=MAX_WEI_DIGITS, decimal_places=0, null=True
    )
    decimals = models.IntegerField()
    platform_as_admin = models.BooleanField(default=False)
    temp_directory = models.CharField(max_length=36)
    time_bonuses = JSONField(null=True, default=None)
    amount_bonuses = JSONField(null=True, default=None)
    continue_minting = models.BooleanField(default=False)
    cold_wallet_address = models.CharField(max_length=50, default='')
    allow_change_dates = models.BooleanField(default=False)
    whitelist = models.BooleanField(default=False)

    ducx_contract_token = models.ForeignKey(
        DUCXContract,
        null=True,
        default=None,
        related_name='ico_details_token',
        on_delete=models.SET_NULL
    )
    ducx_contract_crowdsale = models.ForeignKey(
        DUCXContract,
        null=True,
        default=None,
        related_name='ico_details_crowdsale',
        on_delete=models.SET_NULL
    )

    reused_token = models.BooleanField(default=False)
    token_type = models.CharField(max_length=32, default='ERC20')

    min_wei = models.DecimalField(
        max_digits=MAX_WEI_DIGITS, decimal_places=0, default=None, null=True
    )
    max_wei = models.DecimalField(
        max_digits=MAX_WEI_DIGITS, decimal_places=0, default=None, null=True
    )

    def predeploy_validate(self):
        now = timezone.now()
        if self.start_date < now.timestamp():
            raise ValidationError({'result': 1}, code=400)
        token_holders = self.contract.tokenholder_set.all()
        for th in token_holders:
            if th.freeze_date:
                if th.freeze_date < now.timestamp() + 600:
                    raise ValidationError({'result': 2}, code=400)

    @classmethod
    def min_cost(cls):
        network = Network.objects.get(name='ETHEREUM_MAINNET')
        cost = cls.calc_cost({}, network)
        return cost

    @staticmethod
    def calc_cost(kwargs, network):
        if NETWORKS[network.name]['is_free']:
            return 0
        return int(125 * NET_DECIMALS['USDT'])

    def compile(self, ducx_contract_attr_name='ducx_contract_token'):
        print('ico_contract compile')
        if self.temp_directory:
            print('already compiled')
            return
        dest, preproc_config = create_directory(self)
        token_holders = self.contract.tokenholder_set.all()
        amount_bonuses = add_amount_bonuses(self)
        time_bonuses = add_time_bonuses(self)
        preproc_params = {'constants': {}}
        preproc_params['constants'] = add_token_params(
            preproc_params['constants'], self, token_holders,
            not self.is_transferable_at_once,
            self.continue_minting
        )
        preproc_params['constants'] = add_crowdsale_params(
            preproc_params['constants'], self, time_bonuses, amount_bonuses
        )
        if self.min_wei:
            preproc_params["constants"]["D_MIN_VALUE_WEI"] = str(
                int(self.min_wei))
        if self.max_wei:
            preproc_params["constants"]["D_MAX_VALUE_WEI"] = str(
                int(self.max_wei))

        test_crowdsale_params(preproc_config, preproc_params, dest)
        address = NETWORKS[self.contract.network.name]['address']
        preproc_params = add_real_params(
            preproc_params, self.admin_address,
            address, self.cold_wallet_address
        )
        with open(preproc_config, 'w') as f:
            f.write(json.dumps(preproc_params))
        if os.system(
                "/bin/bash -c 'cd {dest} && yarn compile-crowdsale'".format(
                    dest=dest)
        ):
            raise Exception('compiler error while deploying')
        with open(path.join(dest, 'build/contracts/TemplateCrowdsale.json'),
                  'rb') as f:
            crowdsale_json = json.loads(f.read().decode('utf-8-sig'))
        with open(path.join(dest, 'build/TemplateCrowdsale.sol'), 'rb') as f:
            source_code = f.read().decode('utf-8-sig')
        self.ducx_contract_crowdsale = create_ethcontract_in_compile(
            crowdsale_json['abi'], crowdsale_json['bytecode'][2:],
            crowdsale_json['compiler']['version'], self.contract, source_code
        )
        if not self.reused_token:
            with open(path.join(dest, 'build/contracts/MainToken.json'),
                      'rb') as f:
                token_json = json.loads(f.read().decode('utf-8-sig'))
            with open(path.join(dest, 'build/MainToken.sol'), 'rb') as f:
                source_code = f.read().decode('utf-8-sig')
            self.ducx_contract_token = create_ethcontract_in_compile(
                token_json['abi'], token_json['bytecode'][2:],
                token_json['compiler']['version'], self.contract, source_code
            )
        self.save()

    @blocking
    @postponable
    @check_transaction
    def msg_deployed(self, message):
        print('msg_deployed method of the ico contract')
        address = NETWORKS[self.contract.network.name]['address']
        if self.contract.state != 'WAITING_FOR_DEPLOYMENT':
            take_off_blocking(self.contract.network.name)
            return
        if self.reused_token:
            self.contract.state = 'WAITING_ACTIVATION'
            self.contract.save()
            self.ducx_contract_crowdsale.address = message['address']
            self.ducx_contract_crowdsale.save()
            take_off_blocking(self.contract.network.name)
            print('status changed to waiting activation')
            return
        if self.ducx_contract_token.id == message['contractId']:
            self.ducx_contract_token.address = message['address']
            self.ducx_contract_token.save()
            self.deploy(ducx_contract_attr_name='ducx_contract_crowdsale')
        else:
            self.ducx_contract_crowdsale.address = message['address']
            self.ducx_contract_crowdsale.save()
            tr = abi.ContractTranslator(self.ducx_contract_token.abi)
            eth_int = EthereumProvider().get_provider(network=self.contract.network.name)
            nonce = int(eth_int.eth_getTransactionCount(address, "pending"), 16)
            print('nonce', nonce)
            print('transferOwnership message signed')
            signed_data = sign_transaction(
                address, nonce, 100000, self.contract.network.name,
                dest=self.ducx_contract_token.address,
                contract_data=binascii.hexlify(tr.encode_function_call(
                    'transferOwnership', [self.ducx_contract_crowdsale.address]
                )).decode(),
            )
            self.ducx_contract_token.tx_hash = eth_int.eth_sendRawTransaction(
                '0x' + signed_data
            )
            self.ducx_contract_token.save()
            print('transferOwnership message sended')

    def get_gaslimit(self):
        return CONTRACT_GAS_LIMIT['ICO']

    @blocking
    @postponable
    def deploy(self, ducx_contract_attr_name='ducx_contract_token'):
        if self.reused_token:
            ducx_contract_attr_name = 'ducx_contract_crowdsale'
        return super().deploy(ducx_contract_attr_name)

    def get_arguments(self, ducx_contract_attr_name):
        return {
            'ducx_contract_token': [],
            'ducx_contract_crowdsale': [self.ducx_contract_token.address],
        }[ducx_contract_attr_name]

    # token
    @blocking
    @postponable
    #    @check_transaction
    def ownershipTransferred(self, message):
        address = NETWORKS[self.contract.network.name]['address']
        if message['contractId'] != self.ducx_contract_token.id:
            if self.contract.state == 'WAITING_FOR_DEPLOYMENT':
                take_off_blocking(self.contract.network.name)
            print('ignored', flush=True)
            return
        if self.contract.state in ('ACTIVE', 'ENDED'):
            take_off_blocking(self.contract.network.name)
            return
        if self.contract.state == 'WAITING_ACTIVATION':
            self.contract.state = 'WAITING_FOR_DEPLOYMENT'
            self.contract.save()
            # continue deploy: call init
        tr = abi.ContractTranslator(self.ducx_contract_crowdsale.abi)
        eth_int = EthereumProvider().get_provider(network=self.contract.network.name)
        nonce = int(eth_int.eth_getTransactionCount(address, "pending"), 16)
        gas_limit = 100000 + 80000 * self.contract.tokenholder_set.all().count()
        print('nonce', nonce)
        print('init message signed')
        signed_data = sign_transaction(
            address, nonce,
            gas_limit,
            self.contract.network.name,
            dest=self.ducx_contract_crowdsale.address,
            contract_data=binascii.hexlify(
                tr.encode_function_call('init', [])
            ).decode()
        )
        self.ducx_contract_crowdsale.tx_hash = eth_int.eth_sendRawTransaction(
            '0x' + signed_data
        )
        self.ducx_contract_crowdsale.save()
        print('init message sended')

    # crowdsale
    @postponable
    @check_transaction
    def initialized(self, message):
        if self.contract.state != 'WAITING_FOR_DEPLOYMENT':
            return
        take_off_blocking(self.contract.network.name)
        if message['contractId'] != self.ducx_contract_crowdsale.id:
            print('ignored', flush=True)
            return
        self.contract.state = 'ACTIVE'
        self.contract.save()
        if self.ducx_contract_token.original_contract.contract_type == 5:
            self.ducx_contract_token.original_contract.state = 'UNDER_CROWDSALE'
            self.ducx_contract_token.original_contract.save()
        network_link = NETWORKS[self.contract.network.name]['link_address']
        network_name = MAIL_NETWORK[self.contract.network.name]
        if self.contract.user.email:
            send_mail(
                ico_subject,
                ico_text.format(
                    link1=network_link.format(
                        address=self.ducx_contract_token.address,
                    ),
                    link2=network_link.format(
                        address=self.ducx_contract_crowdsale.address
                    ),
                    network_name=network_name
                ),
                DEFAULT_FROM_EMAIL,
                [self.contract.user.email]
            )

    def finalized(self, message):
        if not self.continue_minting and self.ducx_contract_token.original_contract.state != 'ENDED':
            self.ducx_contract_token.original_contract.state = 'ENDED'
            self.ducx_contract_token.original_contract.save()
        if self.ducx_contract_crowdsale.contract.state != 'ENDED':
            self.ducx_contract_crowdsale.contract.state = 'ENDED'
            self.ducx_contract_crowdsale.contract.save()

    def check_contract(self):
        pass

    def timesChanged(self, message):
        if 'startTime' in message and message['startTime']:
            self.start_date = message['startTime']
        if 'endTime' in message and message['endTime']:
            self.stop_date = message['endTime']
        self.save()


@contract_details('Token contract')
class ContractDetailsToken(CommonDetails):
    token_name = models.CharField(max_length=512)
    token_short_name = models.CharField(max_length=64)
    admin_address = models.CharField(max_length=50)
    decimals = models.IntegerField()
    token_type = models.CharField(max_length=32, default='ERC20')
    ducx_contract_token = models.ForeignKey(
        DUCXContract,
        null=True,
        default=None,
        related_name='token_details_token',
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

    def get_arguments(self, ducx_contract_attr_name):
        return []

    def compile(self, ducx_contract_attr_name='ducx_contract_token'):
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
        self.ducx_contract_token = create_ethcontract_in_compile(
            token_json['abi'], token_json['bytecode'][2:],
            token_json['compiler']['version'], self.contract, source_code
        )
        self.save()

    @blocking
    @postponable
    def deploy(self, ducx_contract_attr_name='ducx_contract_token'):
        return super().deploy(ducx_contract_attr_name)

    def get_gaslimit(self):
        return CONTRACT_GAS_LIMIT['TOKEN']

    @postponable
    @check_transaction
    def msg_deployed(self, message):
        res = super().msg_deployed(message, 'ducx_contract_token')
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
                    address=self.ducx_contract_token.address,
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
        if self.ducx_contract_token.original_contract.state not in (
                'UNDER_CROWDSALE', 'ENDED'
        ):
            self.ducx_contract_token.original_contract.state = 'UNDER_CROWDSALE'
            self.ducx_contract_token.original_contract.save()

    def finalized(self, message):
        if self.ducx_contract_token.original_contract.state != 'ENDED':
            self.ducx_contract_token.original_contract.state = 'ENDED'
            self.ducx_contract_token.original_contract.save()
        if (self.ducx_contract_token.original_contract.id !=
                self.ducx_contract_token.contract.id and
                self.ducx_contract_token.contract.state != 'ENDED'):
            self.ducx_contract_token.contract.state = 'ENDED'
            self.ducx_contract_token.contract.save()

    def check_contract(self):
        pass

    def initialized(self, message):
        pass
