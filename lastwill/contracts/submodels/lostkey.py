import datetime

from django.db import models

from django.core.mail import send_mail
from django.utils import timezone
from rest_framework.exceptions import ValidationError

from lastwill.contracts.submodels.common import *
from email_messages import *
from lastwill.consts import NET_DECIMALS
from lxml.html import parse, fromstring, etree


def get_parsing_tokenholdings(address):
    pages = 16
    results = []
    for i in range(pages):
        page = get_tokenholdings_page(address, i+1)
        if len(page) != 0:
            results.extend(page)
    return results


def get_tokenholdings_page(address, page):
    TOKEN_HOLDINGS_URL_BASE = 'https://etherscan.io/tokenholdingsHandler.ashx?&a='
    URL_END = '&q=&p={page}&f=0&h=0&sort=total_price_usd&order=desc&fav='.format(page=page)
    res = requests.get(TOKEN_HOLDINGS_URL_BASE + address + URL_END)
    doc = fromstring(res.content)

    div = doc[1][5] if len(doc[1]) == 6 else doc[1]

    tr_list = []
    for el in div:
        if el.tag == 'tr':
            tr_list.append(el)

    tr_list = tr_list[:int((len(tr_list)/2))]

    if len(tr_list) >= 1:
        res = []
        tr_list = tr_list[:int((len(tr_list)/2))]
        for el in tr_list:
            value = el[3].text_content().split()
            amount = value[0].replace(',', '')
            symbol = value[1]
            if symbol == 'ETH':
                continue
            try:
                name_t = el[1][0][1][0]
                name = name_t.items()[0][1]
            except IndexError:
                name = 'Erc20 ({sym})'.format(sym=symbol)
            token_addr = el[1][1][0].text_content()
            res.append(
                {
                    'tokenInfo':
                        {
                            'address': token_addr,
                            'symbol': symbol,
                            'name': name
                        },
                    'balance': amount
                }
            )
        return res
    else:
        return []



class AbstractContractDetailsLostKey(CommonDetails):
    class Meta:
        abstract = True

    sol_path = 'lastwill/lost-key/'
    source_filename = 'contracts/LostKeyDelayedPaymentWallet.sol'
    result_filename = 'build/contracts/LostKeyDelayedPaymentWallet.json'
    user_address = models.CharField(max_length=50, null=True, default=None)
    check_interval = models.IntegerField()
    active_to = models.DateTimeField()
    last_check = models.DateTimeField(null=True, default=None)
    next_check = models.DateTimeField(null=True, default=None)
    eth_contract = models.ForeignKey(EthContract, null=True, default=None)
    transfer_threshold_wei = models.IntegerField(default=0)
    transfer_delay_seconds = models.IntegerField(default=0)

    def predeploy_validate(self):
        now = timezone.now()
        if self.active_to < now:
            raise ValidationError({'result': 1}, code=400)

    def get_arguments(self, *args, **kwargs):
        return [
            self.user_address,
            [h.address for h in self.contract.heir_set.all()],
            [h.percentage for h in self.contract.heir_set.all()],
            self.check_interval,
            2 ** 256 - 1,
            0,
        ]

    def fundsAdded(self, message):
        pass

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
        heirs_num = int(kwargs['heirs_num']) if 'heirs_num' in kwargs else len(
            kwargs['heirs'])
        active_to = kwargs['active_to']
        if isinstance(active_to, str):
            if 'T' in active_to:
                active_to = active_to[:active_to.index('T')]
            active_to = datetime.date(*map(int, active_to.split('-')))
        elif isinstance(active_to, datetime.datetime):
            active_to = active_to.date()
        check_interval = int(kwargs['check_interval'])
        Cg = 1476117
        CBg = 28031
        Tg = 22000
        Gp = 60 * NET_DECIMALS['ETH_GAS_PRICE']
        Dg = 29435
        DBg = 9646
        B = heirs_num
        Cc = 124852
        DxC = max(abs((
                              datetime.date.today() - active_to).total_seconds() / check_interval),
                  1)
        O = 25000 * NET_DECIMALS['ETH_GAS_PRICE']
        # return 2 * int(
        #     Tg * Gp + Gp * (Cg + B * CBg) + Gp * (Dg + DBg * B) + (
        #                 Gp * Cc + O) * DxC
        # ) + 80000
        return 50 * NET_DECIMALS['USDT']

    @postponable
    @check_transaction
    def msg_deployed(self, message):
        super().msg_deployed(message)
        self.next_check = timezone.now() + datetime.timedelta(
            seconds=self.check_interval)
        self.save()

    @check_transaction
    def checked(self, message):
        now = timezone.now()
        self.last_check = now
        next_check = now + datetime.timedelta(seconds=self.check_interval)
        if next_check < self.active_to:
            self.next_check = next_check
        else:
            self.contract.state = 'EXPIRED'
            self.contract.save()
            self.next_check = None
        self.save()
        take_off_blocking(self.contract.network.name, self.contract.id)

    @check_transaction
    def triggered(self, message):
        self.last_check = timezone.now()
        self.next_check = None
        self.save()
        heirs = Heir.objects.filter(contract=self.contract)
        link = NETWORKS[self.eth_contract.contract.network.name]['link_tx']
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
                carry_out_subject,
                carry_out_message,
                DEFAULT_FROM_EMAIL,
                [self.contract.user.email]
            )

    def get_gaslimit(self):
        Cg = 3200000
        CBg = 28031
        return Cg + len(self.contract.heir_set.all()) * CBg

    @blocking
    @postponable
    def deploy(self):
        return super().deploy()


@contract_details('Wallet contract (lost key)')
class ContractDetailsLostKey(AbstractContractDetailsLostKey):
    pass



class AbstractContractDetailsLostKeyTokens(CommonDetails):
    class Meta:
        abstract = True

    user_address = models.CharField(max_length=50, null=True, default=None)
    check_interval = models.IntegerField()
    active_to = models.DateTimeField()
    last_check = models.DateTimeField(null=True, default=None)
    next_check = models.DateTimeField(null=True, default=None)
    temp_directory = models.CharField(max_length=36)
    eth_contract = models.ForeignKey(
        EthContract,
        null=True,
        default=None,
        related_name='eth_lostkey_details',
        on_delete=models.SET_NULL
    )
    email = models.CharField(max_length=256, null=True, default=None)
    platform_alive = models.BooleanField(default=False)
    platform_cancel = models.BooleanField(default=False)
    last_reset = models.DateTimeField(null=True, default=None)
    last_press_imalive = models.DateTimeField(null=True, default=None)

    def predeploy_validate(self):
        pass

    def get_arguments(self, *args, **kwargs):
        return [
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
        active_to = kwargs['active_to']
        if isinstance(active_to, str):
            if 'T' in active_to:
                active_to = active_to[:active_to.index('T')]
            active_to = datetime.date(*map(int, active_to.split('-')))
        elif isinstance(active_to, datetime.datetime):
            active_to = active_to.date()
        check_interval = int(kwargs['check_interval'])

        gasPrice = 40000000000

        constructGas = 1660000
        constructGasPerHeir = 40000

        checkGas = 25000

        triggerGas = 32000
        triggerGasPerHeir = 42000
        triggerGasPerToken = 18000
        heirsCount = int(kwargs['heirs_num']) if 'heirs_num' in kwargs else len(
            kwargs['heirs'])

        constructPrice = gasPrice * (
                constructGas + heirsCount * constructGasPerHeir)

        checkCount = max(abs(
            (datetime.date.today() - active_to).total_seconds() / check_interval
        ), 1)
        checkPrice = checkGas * gasPrice * checkCount

        triggerPrice = gasPrice * (
                triggerGas + triggerGasPerHeir * heirsCount + triggerGasPerToken * 400 * 2)

        # return constructPrice + checkPrice + triggerPrice
        return int(50 * NET_DECIMALS['USDT'])

    @postponable
    @check_transaction
    def msg_deployed(self, message):
        super().msg_deployed(message)
        self.next_check = timezone.now() + datetime.timedelta(
            seconds=self.check_interval)
        self.save()

    @check_transaction
    def checked(self, message):
        now = timezone.now()
        self.last_check = now
        next_check = now + datetime.timedelta(seconds=self.check_interval)
        if next_check < self.active_to:
            self.next_check = next_check
        else:
            self.contract.state = 'EXPIRED'
            self.contract.save()
            self.next_check = None
        self.save()
        take_off_blocking(self.contract.network.name, self.contract.id)

    @check_transaction
    def triggered(self, message):
        self.last_check = timezone.now()
        self.next_check = None
        self.save()
        heirs = Heir.objects.filter(contract=self.contract)
        link = NETWORKS[self.eth_contract.contract.network.name]['link_tx']
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
                carry_out_subject,
                carry_out_message,
                DEFAULT_FROM_EMAIL,
                [self.contract.user.email]
            )

    def get_gaslimit(self):
        Cg = 3200000
        CBg = 28031
        return Cg + len(self.contract.heir_set.all()) * CBg

    @blocking
    @postponable
    def deploy(self):
        return super().deploy()

    def compile(self, eth_contract_attr_name='eth_contract_token'):
        print('tron lostkey contract compile')
        if self.temp_directory:
            print('already compiled')
            return
        dest, preproc_config = create_directory(
            self, sour_path='lastwill/eth-lost-key-token/*',
            config_name='c-preprocessor-config.json'
        )
        heirs = self.contract.heir_set.all()
        heirs_list = ','.join(map(lambda h: 'address(%s)' % h.address, heirs))
        heirs_percents = ','.join(map(lambda h: 'uint(%s)' % h.percentage, heirs))
        preproc_params = {'constants': {}}
        preproc_params["constants"]["D_TARGET"] = "0xf17f52151EbEF6C7334FAD080c5704D77216b732"
        preproc_params["constants"]["D_HEIRS"] = heirs_list
        preproc_params["constants"]["D_PERCENTS"] = heirs_percents
        preproc_params["constants"]["D_PERIOD_SECONDS"] = self.check_interval
        preproc_params["constants"]["D_HEIRS_COUNT"] = len(heirs)
        print('params', preproc_params, flush=True)

        with open(preproc_config, 'w') as f:
            f.write(json.dumps(preproc_params))
        if os.system('cd {dest} && yarn compile'.format(dest=dest)):
            raise Exception('compiler for test error while deploying')
        if os.system('cd {dest} && yarn test'.format(
                dest=dest)):
            raise Exception('testing error')

        preproc_params["constants"]["D_TARGET"] = self.user_address
        with open(preproc_config, 'w') as f:
            f.write(json.dumps(preproc_params))
        if os.system('cd {dest} && yarn compile'.format(dest=dest)):
            raise Exception('compiler error while deploying')

        with open(path.join(dest, 'build/contracts/LostKeyMain.json'), 'rb') as f:
            token_json = json.loads(f.read().decode('utf-8-sig'))
        with open(path.join(dest, 'build/LostKeyMain.sol'), 'rb') as f:
            source_code = f.read().decode('utf-8-sig')
        eth_contract = EthContract()
        eth_contract.abi = token_json['abi']
        eth_contract.bytecode = token_json['bytecode'][2:]
        eth_contract.compiler_version = token_json['compiler']['version']
        eth_contract.contract = self.contract
        eth_contract.original_contract = self.contract
        eth_contract.source_code = source_code
        eth_contract.save()
        self.eth_contract = eth_contract
        self.save()


@contract_details('Wallet contract (lost key)')
class ContractDetailsLostKeyTokens(AbstractContractDetailsLostKeyTokens):
    pass
