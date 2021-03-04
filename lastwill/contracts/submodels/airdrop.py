from django.db import models
import datetime
from lastwill.contracts.submodels.common import *
from lastwill.consts import NET_DECIMALS, CONTRACT_GAS_LIMIT, CONTRACT_PRICE_USDT, VERIFICATION_PRICE_USDT
from lastwill.settings import SUPPORT_EMAIL
from django.core.mail import EmailMessage


class AirdropAddress(models.Model):
    contract = models.ForeignKey(Contract, null=True)
    address = models.CharField(max_length=50, db_index=True)
    active = models.BooleanField(default=True)
    state = models.CharField(max_length=10, default='added')
    amount = models.DecimalField(
        max_digits=MAX_WEI_DIGITS, decimal_places=0, null=True,
        db_index=True
    )


class AbstractContractDetailsAirdrop(CommonDetails):
    class Meta:
        abstract = True

    contract = models.ForeignKey(Contract, null=True)
    admin_address = models.CharField(max_length=50)
    token_address = models.CharField(max_length=50)
    eth_contract = models.ForeignKey(EthContract, null=True, default=None)
    airdrop_in_progress = models.BooleanField(default=False)

    verification = models.BooleanField(default=False)
    verification_status = models.CharField(max_length=100, default='NOT_VERIFIED')
    verification_date_payment = models.DateField(null=True, default=None)

    def get_arguments(self, *args, **kwargs):
        return [
            self.admin_address,
            self.token_address
        ]

    def compile(self, _=''):
        dest = path.join(CONTRACTS_DIR, 'lastwill/airdrop-contract/')
        with open(path.join(dest, 'build/contracts/AirDrop.json'), 'rb') as f:
            airdrop_json = json.loads(f.read().decode('utf-8-sig'))
        with open(path.join(dest, 'contracts/AirDrop.sol'), 'rb') as f:
            source_code = f.read().decode('utf-8-sig')
        self.eth_contract = create_ethcontract_in_compile(
            airdrop_json['abi'], airdrop_json['bytecode'][2:],
            airdrop_json['compiler']['version'], self.contract, source_code
        )
        self.save()

    @blocking
    @postponable
    def deploy(self, attempts=1):
        return super().deploy(attempts=attempts)

    @staticmethod
    def calc_cost(kwargs, network):
        if NETWORKS[network.name]['is_free']:
            return 0
        price = CONTRACT_PRICE_USDT['ETH_AIRDROP']
        if 'verification' in kwargs and kwargs['verification']:
            price += VERIFICATION_PRICE_USDT
        return price * NET_DECIMALS['USDT']

    @classmethod
    def min_cost(cls):
        network = Network.objects.get(name='ETHEREUM_MAINNET')
        cost = cls.calc_cost({}, network)
        return cost

    def get_gaslimit(self):
        return CONTRACT_GAS_LIMIT['AIRDROP']

    def airdrop(self, message):
        new_state = {
            'COMMITTED': 'sent',
            'PENDING': 'processing',
            'REJECTED': 'added'
        }[message['status']]
        old_state = {
            'COMMITTED': 'processing',
            'PENDING': 'added',
            'REJECTED': 'processing'
        }[message['status']]

        ids = []
        for js in message['airdroppedAddresses']:
            address = js['address']
            amount = js['value']
            addr = AirdropAddress.objects.filter(
                address=address,
                amount=amount,
                contract=self.contract,
                active=True,
                state=old_state,
            ).exclude(id__in=ids).first()
            # in case 'pending' msg was lost or dropped, but 'commited' is there
            if addr is None and message['status'] == 'COMMITTED':
                old_state = 'added'
                addr = AirdropAddress.objects.filter(
                    address=address,
                    amount=amount,
                    contract=self.contract,
                    active=True,
                    state=old_state,
                ).exclude(id__in=ids).first()
            if addr is None:
                continue

            ids.append(addr.id)

        if len(message['airdroppedAddresses']) != len(ids):
            print('=' * 40, len(message['airdroppedAddresses']), len(ids),
                  flush=True)
        AirdropAddress.objects.filter(id__in=ids).update(state=new_state)
        if self.contract.airdropaddress_set.filter(state__in=('added', 'processing'),
                                                   active=True).count() == 0:
            self.airdrop_in_progress = False
            self.save()

            self.contract.airdropaddress_set.filter(active=True).update(state='completed')

        else:
            self.airdrop_in_progress = True
            self.save()

    @postponable
    @check_transaction
    def msg_deployed(self, message, eth_contract_attr_name='eth_contract'):
        super().msg_deployed(message, 'eth_contract')
        if self.verification:
            mail = EmailMessage(
                subject=verification_subject,
                body=verification_message.format(
                    network=self.contract.network.name,
                    addresses=self.eth_contract.address,
                    compiler_version=self.eth_contract.compiler_version,
                    optimization='Yes',
                    runs='200',
                ),
                from_email=DEFAULT_FROM_EMAIL,
                to=[SUPPORT_EMAIL]
            )
            mail.attach('code.sol', self.eth_contract.source_code)
            mail.send()
            self.verification_date_payment = datetime.datetime.now().date()
            self.verification_status = 'IN_PROCESS'
            self.save()


@contract_details('Airdrop')
class ContractDetailsAirdrop(AbstractContractDetailsAirdrop):
    pass
