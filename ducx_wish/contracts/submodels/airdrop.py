from django.db import models

from ducx_wish.contracts.submodels.common import *
from ducx_wish.consts import NET_DECIMALS, CONTRACT_GAS_LIMIT


class AirdropAddress(models.Model):
    contract = models.ForeignKey(Contract, null=True)
    address = models.CharField(max_length=50, db_index=True)
    active = models.BooleanField(default=True)
    state = models.CharField(max_length=10, default='added')
    amount = models.DecimalField(
        max_digits=MAX_WEI_DIGITS, decimal_places=0, null=True,
        db_index=True
    )


@contract_details('Airdrop')
class ContractDetailsAirdrop(CommonDetails):

    contract = models.ForeignKey(Contract, null=True)
    admin_address = models.CharField(max_length=50)
    token_address = models.CharField(max_length=50)
    ducx_contract = models.ForeignKey(DUCXContract, null=True, default=None)

    def get_arguments(self, *args, **kwargs):
        return [
            self.admin_address,
            self.token_address
        ]

    def compile(self, _=''):
        dest = path.join(CONTRACTS_DIR, 'ducx_wish/airdrop-contract/')
        with open(path.join(dest, 'build/contracts/AirDrop.json'), 'rb') as f:
            airdrop_json = json.loads(f.read().decode('utf-8-sig'))
        with open(path.join(dest, 'contracts/AirDrop.sol'), 'rb') as f:
            source_code = f.read().decode('utf-8-sig')
        self.ducx_contract = create_ethcontract_in_compile(
            airdrop_json['abi'], airdrop_json['bytecode'][2:],
            airdrop_json['compiler']['version'], self.contract, source_code
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
        #return 0.5 * 10**18
        return 75 * NET_DECIMALS['DUC']

    @classmethod
    def min_cost(cls):
        network = Network.objects.get(name='DUCATUSX_MAINNET')
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
                    state=old_state
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
            self.contract.state = 'ENDED'
            self.contract.save()
