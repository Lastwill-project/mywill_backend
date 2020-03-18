import datetime
import bitcoin
from ethereum import abi

from django.db import models
from django.db.models import F
from django.core.mail import send_mail
from django.utils import timezone
from rest_framework.exceptions import ValidationError

from ducx_wish.contracts.submodels.common import *
from email_messages import *
from ducx_wish.settings import LASTWILL_ALIVE_TIMEOUT
from ducx_wish.consts import NET_DECIMALS, CONTRACT_GAS_LIMIT


@contract_details('Will contract')
class ContractDetailsLastwill(CommonDetails):
    sol_path = 'ducx_wish/last-will/'
    source_filename = 'contracts/LastWillNotify.sol'
    result_filename = 'build/contracts/LastWillNotify.json'
    user_address = models.CharField(max_length=50, null=True, default=None)
    check_interval = models.IntegerField()
    active_to = models.DateTimeField()
    last_check = models.DateTimeField(null=True, default=None)
    next_check = models.DateTimeField(null=True, default=None)
    ducx_contract = models.ForeignKey(DUCXContract, null=True, default=None)
    email = models.CharField(max_length=256, null=True, default=None)
    btc_key = models.ForeignKey(BtcKey4RSK, null=True, default=None)
    platform_alive = models.BooleanField(default=False)
    platform_cancel = models.BooleanField(default=False)
    last_reset = models.DateTimeField(null=True, default=None)
    last_press_imalive = models.DateTimeField(null=True, default=None)
    btc_duty = models.DecimalField(
        max_digits=MAX_WEI_DIGITS, decimal_places=0, default=0
    )

    def predeploy_validate(self):
        now = timezone.now()
        if self.active_to < now:
            raise ValidationError({'result': 1}, code=400)

    def contractPayment(self, message):
        if self.contract.network.name not in ['RSK_MAINNET', 'RSK_TESTNET']:
            return
        ContractDetailsLastwill.objects.select_for_update().filter(
            id=self.id
        ).update(btc_duty=F('btc_duty') + message['value'])
        queues = {
            'RSK_MAINNET': 'notification-rsk-fgw',
            'RSK_TESTNET': 'notification-rsk-testnet-fgw'
        }
        queue = queues[self.contract.network.name]
        send_in_queue(self.contract.id, 'make_payment', queue)

    @blocking
    def make_payment(self, message):
        contract = self.contract
        eth_int = EthereumProvider().get_provider(network=self.contract.network.name)
        wl_address = NETWORKS[self.contract.network.name]['address']
        balance = int(eth_int.eth_getBalance(wl_address), 16)
        gas_limit = CONTRACT_GAS_LIMIT['LASTWILL_PAYMENT']
        gas_price = NET_DECIMALS['ETH_GAS_PRICE']
        if balance < contract.get_details().btc_duty + gas_limit * gas_price:
            send_mail(
                'RSK',
                'No RSK funds ' + contract.network.name,
                DEFAULT_FROM_EMAIL,
                [EMAIL_FOR_POSTPONED_MESSAGE]
            )
            return
        nonce = int(eth_int.eth_getTransactionCount(wl_address, "pending"), 16)
        signed_data = sign_transaction(
            wl_address, nonce, gas_limit, self.contract.network.name,
            value=int(contract.get_details().btc_duty),
            dest=contract.get_details().ducx_contract.address,
            gas_price=gas_price
        )
        self.ducx_contract.tx_hansh = eth_int.eth_sendRawTransaction(
            '0x' + signed_data)
        self.ducx_contract.save()

    def get_arguments(self, *args, **kwargs):
        return [
            self.user_address,
            [h.address for h in self.contract.heir_set.all()],
            [h.percentage for h in self.contract.heir_set.all()],
            self.check_interval,
            False if self.contract.network.name in
                     ['ETHEREUM_MAINNET', 'ETHEREUM_ROPSTEN'] else True,
        ]

    @classmethod
    def min_cost(cls):
        network = Network.objects.get(name='ETHEREUM_MAINNET')
        now = datetime.datetime.now()
        cost = cls.calc_cost({
            'check_interval': 1,
            'heirs': [],
            'active_to': now
        }, network)
        return cost

    @staticmethod
    def calc_cost(kwargs, network):
        if NETWORKS[network.name]['is_free']:
            return 0
        heirs_num = int(kwargs['heirs_num']) if 'heirs_num' in kwargs else len(kwargs['heirs'])
        active_to = kwargs['active_to']
        if isinstance(active_to, str):
            if 'T' in active_to:
                active_to = active_to[:active_to.index('T')]
            active_to = datetime.date(*map(int, active_to.split('-')))
        elif isinstance(active_to, datetime.datetime):
            active_to = active_to.date()
        check_interval = int(kwargs['check_interval'])
        Cg = 780476
        CBg = 26561
        Tg = 22000
        Gp = 60 * NET_DECIMALS['ETH_GAS_PRICE']
        Dg = 29435
        DBg = 9646
        B = heirs_num
        Cc = 124852
        DxC = max(abs(
            (datetime.date.today() - active_to).total_seconds() / check_interval
        ), 1)
        O = 25000 * NET_DECIMALS['ETH_GAS_PRICE']
        result = 2 * int(
            Tg * Gp + Gp * (Cg + B * CBg) + Gp * (Dg + DBg * B) + (Gp * Cc + O) * DxC
        ) + 80000
        if network.name == 'RSK_MAINNET':
            result += 2 * NET_DECIMALS['ETH']
        return 30 * NET_DECIMALS['USDT']

    @postponable
    @check_transaction
    def msg_deployed(self, message):
        super().msg_deployed(message)
        self.next_check = timezone.now() + datetime.timedelta(seconds=self.check_interval)
        self.save()

    @check_transaction
    def checked(self, message):
        now = timezone.now()
        self.last_check = now
        next_check = now + datetime.timedelta(seconds=self.check_interval)
        if next_check < self.active_to:
            self.next_check = next_check
        else:
            self.next_check = None
        self.save()
        take_off_blocking(self.contract.network.name, self.contract.id)

    @check_transaction
    def triggered(self, message):
        self.last_check = timezone.now()
        self.next_check = None
        self.save()
        heirs = Heir.objects.filter(contract=self.contract)
        link = NETWORKS[self.ducx_contract.contract.network.name]['link_tx']
        for heir in heirs:
            if heir.email:
                send_mail(
                    heir_subject,
                    heir_message.format(
                            user_address=heir.address,
                            link_tx=link.format(tx=message['transactionHash'])
                    ),
                    DEFAULT_FROM_EMAIL,
                    [heir.email]
                )
        self.contract.state = 'TRIGGERED'
        self.contract.save()
        if self.contract.user.email:
            send_mail(
                carry_out_subject, carry_out_message,
                DEFAULT_FROM_EMAIL, [self.contract.user.email]
            )

    def get_gaslimit(self):
        Cg = 1270525
        CBg = 26561
        return Cg + len(self.contract.heir_set.all()) * CBg + 25000

    @blocking
    @postponable
    def deploy(self):
        if self.contract.network.name in ['RSK_MAINNET', 'RSK_TESTNET'] and self.btc_key is None:
            priv = os.urandom(32)
            if self.contract.network.name == 'RSK_MAINNET':
                address = bitcoin.privkey_to_address(priv, magicbyte=0)
            else:
                address = bitcoin.privkey_to_address(priv, magicbyte=0x6F)
            btc_key = BtcKey4RSK(
                private_key=binascii.hexlify(priv).decode(),
                btc_address=address
            )
            btc_key.save()
            self.btc_key = btc_key
            self.save()
        super().deploy()

    @blocking
    def i_am_alive(self, message):
        if self.last_press_imalive:
            delta = self.last_press_imalive - timezone.now()
            if delta.days < 1 and delta.total_seconds() < LASTWILL_ALIVE_TIMEOUT:
                take_off_blocking(
                    self.contract.network.name, address=self.contract.address
                )
        tr = abi.ContractTranslator(self.ducx_contract.abi)
        eth_int = EthereumProvider().get_provider(network=self.contract.network.name)
        address = self.contract.network.deployaddress_set.all()[0].address
        nonce = int(eth_int.eth_getTransactionCount(address, "pending"), 16)
        gas_limit = CONTRACT_GAS_LIMIT['LASTWILL_COMMON']
        signed_data = sign_transaction(
            address, nonce, gas_limit, self.contract.network.name,
            dest=self.ducx_contract.address,
            contract_data=binascii.hexlify(
                    tr.encode_function_call('imAvailable', [])
                ).decode(),
        )
        self.ducx_contract.tx_hash = eth_int.eth_sendRawTransaction(
            '0x' + signed_data
        )
        self.ducx_contract.save()
        self.last_press_imalive = timezone.now()

    @blocking
    def cancel(self, message):
        tr = abi.ContractTranslator(self.ducx_contract.abi)
        eth_int = EthereumProvider().get_provider(network=self.contract.network.name)
        address = self.contract.network.deployaddress_set.all()[0].address
        nonce = int(eth_int.eth_getTransactionCount(address, "pending"), 16)
        gas_limit = CONTRACT_GAS_LIMIT['LASTWILL_COMMON']
        signed_data = sign_transaction(
            address, nonce,  gas_limit, self.contract.network.name,
            dest=self.ducx_contract.address,
            contract_data=binascii.hexlify(
                    tr.encode_function_call('kill', [])
                ).decode(),
        )
        self.ducx_contract.tx_hash = eth_int.eth_sendRawTransaction(
            '0x' + signed_data
        )
        self.ducx_contract.save()

    def fundsAdded(self, message):
        if self.contract.network.name not in ['RSK_MAINNET', 'RSK_TESTNET']:
            return
        ContractDetailsLastwill.objects.select_for_update().filter(
            id=self.id
        ).update(btc_duty=F('btc_duty') - message['value'])
        take_off_blocking(self.contract.network.name)
