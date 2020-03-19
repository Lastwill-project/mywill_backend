import datetime

from django.db import models
from django.utils import timezone
from rest_framework.exceptions import ValidationError

from ducx_wish.contracts.submodels.common import *
from ducx_wish.settings import NETWORKS
from ducx_wish.consts import NET_DECIMALS, CONTRACT_GAS_LIMIT

class InvestAddress(models.Model):
    contract = models.ForeignKey(Contract, null=True)
    address = models.CharField(max_length=50, db_index=True)
    take_away = models.BooleanField(default=False)
    created_date = models.DateTimeField(auto_now_add=True)
    amount = models.DecimalField(
        max_digits=MAX_WEI_DIGITS, decimal_places=0, null=True,
        db_index=True
    )


@contract_details('Investment Pool')
class ContractDetailsInvestmentPool(CommonDetails):

    contract = models.ForeignKey(Contract, null=True)
    admin_address = models.CharField(max_length=50)
    admin_percent = models.FloatField()
    temp_directory = models.CharField(max_length=36)
    ducx_contract = models.ForeignKey(DUCXContract, null=True, default=None)
    start_date = models.IntegerField()
    stop_date = models.IntegerField()
    whitelist = models.BooleanField(default=False)
    investment_address = models.CharField(max_length=50, default=None, null=True)
    token_address = models.CharField(max_length=50, default=None, null=True)
    allow_change_dates = models.BooleanField(default=False)
    send_tokens_hard_cap = models.BooleanField(default=False)
    send_tokens_soft_cap = models.BooleanField(default=False)
    link = models.CharField(max_length=50, unique=True)
    investment_tx_hash = models.CharField(max_length=70, default='')
    platform_as_admin = models.BooleanField(default=True)

    balance = models.DecimalField(
        max_digits=MAX_WEI_DIGITS, decimal_places=0, default=None, null=True
    )

    soft_cap = models.DecimalField(
        max_digits=MAX_WEI_DIGITS, decimal_places=0, null=True
    )
    hard_cap = models.DecimalField(
        max_digits=MAX_WEI_DIGITS, decimal_places=0, null=True
    )
    min_wei = models.DecimalField(
        max_digits=MAX_WEI_DIGITS, decimal_places=0, default=None, null=True
    )
    max_wei = models.DecimalField(
        max_digits=MAX_WEI_DIGITS, decimal_places=0, default=None, null=True
    )

    def get_arguments(self, *args, **kwargs):
        return [
                self.admin_address,
                self.investment_address if self.investment_address else '0x'+'0'*40,
                self.token_address if self.token_address else '0x'+'0'*40,
                NETWORKS[self.contract.network.name]['address'] if self.platform_as_admin else '0x'+'0'*40,
        ]

    def compile(self, _=''):
        print('investment pool contract compile')
        if self.temp_directory:
            print('already compiled')
            return
        dest, preproc_config = create_directory(
            self, sour_path='ducx_wish/investment-pool/*',
            config_name='investment-pool-config.json'
        )
        preproc_params = {'constants': {}}

        preproc_params["constants"]["D_SOFT_CAP_WEI"] = str(self.soft_cap)
        preproc_params["constants"]["D_HARD_CAP_WEI"] = str(self.hard_cap)
        preproc_params["constants"]["D_START_TIME"] = self.start_date
        preproc_params["constants"]["D_END_TIME"] = self.stop_date
        preproc_params["constants"]["D_WHITELIST"] = "true" if self.whitelist else "false"
        preproc_params["constants"]["D_CAN_CHANGE_TIMES"] = "true" if self.allow_change_dates else "false"
        preproc_params["constants"]["D_CAN_FINALIZE_AFTER_HARD_CAP_ONLY_OWNER"] = "false" if self.send_tokens_hard_cap else "true"
        preproc_params["constants"]["D_CAN_FINALIZE_AFTER_SOFT_CAP_ONLY_OWNER"] = "false" if self.send_tokens_soft_cap else "true"
        preproc_params["constants"]["D_REWARD_PERMILLE"] = int(self.admin_percent * 10)

        if self.min_wei:
            preproc_params["constants"]["D_MIN_VALUE_WEI"] = str(
                int(self.min_wei))
        if self.max_wei:
            preproc_params["constants"]["D_MAX_VALUE_WEI"] = str(
                int(self.max_wei))
        print('params', preproc_params, flush=True)
        test_investment_pool_params(preproc_config, preproc_params, dest)
        with open(preproc_config, 'w') as f:
            f.write(json.dumps(preproc_params))
        with open(path.join(dest, 'build/contracts/InvestmentPool.json'),
                  'rb') as f:
            investment_json = json.loads(f.read().decode('utf-8-sig'))
        with open(path.join(dest, 'build/InvestmentPool.sol'), 'rb') as f:
            source_code = f.read().decode('utf-8-sig')
        self.ducx_contract = create_ethcontract_in_compile(
            investment_json['abi'], investment_json['bytecode'][2:],
            investment_json['compiler']['version'], self.contract, source_code
        )
        self.save()

    @blocking
    @postponable
    def deploy(self):
        return super().deploy()

    @staticmethod
    def calc_cost(kwargs, network):
        if NETWORKS[network.name]['is_free']:
            return 0
        return 50 * NET_DECIMALS['DUC']

    @classmethod
    def min_cost(cls):
        network = Network.objects.get(name='ETHEREUM_MAINNET')
        cost = cls.calc_cost({}, network)
        return cost

    def get_gaslimit(self):
        return CONTRACT_GAS_LIMIT['INVESTMENT_POOL']

    def fundsAdded(self, message):
        invest = InvestAddress(
            contract=self.contract,
            address=message['investorAddress'],
            amount=message['value']
        )
        invest.save()
        self.balance = message['balance']
        self.save()

    def tokenSent(self, message):
        invest = InvestAddress.objects.filter(
            address=message['investorAddress'],
            amount=message['amount']
        ).first()
        if invest:
            invest.take_away = True
            invest.save()

    def timesChanged(self, message):
        if 'startTime' in message:
            self.start_date = message['startTime']
        if 'endTime' in message:
            self.stop_date = message['endTime']
        self.save()

    def finalized(self, message):
        contract = self.contract
        if message['status'] == 'COMMITTED':
            contract.state='DONE'
            contract.save()
            details = contract.get_details()
            details.investment_tx_hash = message['transactionHash']
            details.save()
        elif message['status'] == 'REJECTED' and datetime.datetime.now().timestamp() > self.stop_date:
            contract.state = 'CANCELLED'
            contract.save()

    def predeploy_validate(self):
        now = timezone.now()
        if self.start_date < now.timestamp() + 7 * 60:
            raise ValidationError({'result': 1}, code=400)

    def cancelled(self, message):
        contract = self.contract
        contract.state = 'CANCELLED'
        contract.save()
