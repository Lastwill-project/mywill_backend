import datetime
import base58
import fcntl

from django.db import models
from django.core.mail import send_mail, EmailMessage
from django.utils import timezone
from rest_framework.exceptions import ValidationError

from lastwill.contracts.submodels.common import *
from lastwill.contracts.submodels.airdrop import AirdropAddress
from lastwill.consts import NET_DECIMALS
from lastwill.settings import TRON_NODE

from tronapi import Tron, HttpProvider


def convert_address_to_hex(address):
    # short_addresss = address[1:]
    decode_address = base58.b58decode(address)[1:21]
    hex_address = binascii.hexlify(decode_address)
    hex_address = '0x' + hex_address.decode("utf-8")
    return hex_address


def replace_0x(message):
    for mes in message:
        mes['address'] = '41' + mes['address'][2:]
    return message


def generate_tron_url(network):
    tron_url = str(NETWORKS[network]['host'])
    return tron_url


def instantiate_tronapi(pk, net):
    node_url = generate_tron_url(network=net)
    tron = Tron(full_node=node_url,
                solidity_node=node_url,
                event_server=node_url,
                private_key=pk
                )
    tron.private_key = pk
    tron.default_address = tron.address.from_private_key(tron.private_key).base58
    return tron


class TRONContract(EthContract):
    pass


@contract_details('Token contract')
class ContractDetailsTRONToken(CommonDetails):
    token_name = models.CharField(max_length=512)
    token_short_name = models.CharField(max_length=64)
    admin_address = models.CharField(max_length=50)
    decimals = models.IntegerField()
    token_type = models.CharField(max_length=32, default='ERC20')
    tron_contract_token = models.ForeignKey(
        TRONContract,
        null=True,
        default=None,
        related_name='token_details',
        on_delete=models.SET_NULL
    )
    future_minting = models.BooleanField(default=False)
    temp_directory = models.CharField(max_length=36)

    def predeploy_validate(self):
        now = timezone.now()
        token_holders = self.contract.tokenholder_set.all()
        for th in token_holders:
            if th.freeze_date:
                if th.freeze_date < now.timestamp() + 600:
                    raise ValidationError({'result': 1}, code=400)

    @classmethod
    def min_cost(cls):
        network = Network.objects.get(name='TRON_MAINNET')
        cost = cls.calc_cost({}, network)
        return cost

    @staticmethod
    def calc_cost(kwargs, network):
        if NETWORKS[network.name]['is_free']:
            return 0
        result = int(79 * NET_DECIMALS['USDT'])
        return result

    @classmethod
    def min_cost_tron(cls):
        network = Network.objects.get(name='TRON_MAINNET')
        cost = cls.calc_cost_tron({}, network)
        return cost

    @staticmethod
    def calc_cost_tron(kwargs, network):
        if NETWORKS[network.name]['is_free']:
            return 0
        result = int(600 * NET_DECIMALS['TRX'])
        return result

    def get_arguments(self, eth_contract_attr_name):
        return []

    def compile(self, eth_contract_attr_name='eth_contract_token'):
        print('standalone token contract compile')
        if self.temp_directory:
            print('already compiled')
            return
        dest, preproc_config = create_directory(self, sour_path='lastwill/tron-token/*')
        token_holders = self.contract.tokenholder_set.all()
        for th in token_holders:
            if th.address.startswith('41'):
                th.address = '0x' + th.address[2:]
                th.save()
            elif th.address.startswith('0x'):
                pass
            else:
                th.address = convert_address_to_hex(th.address)
                th.save()
        preproc_params = {"constants": {"D_ONLY_TOKEN": True}}
        preproc_params['constants'] = add_token_params(
            preproc_params['constants'], self, token_holders,
            False, self.future_minting
        )
        owner = '0x' + self.admin_address[2:] if self.admin_address.startswith('41') else convert_address_to_hex(
            self.admin_address)
        preproc_params['constants']['D_CONTRACTS_OWNER'] = owner
        with open(preproc_config, 'w') as f:
            f.write(json.dumps(preproc_params))
        if os.system('cd {dest} && yarn compile'.format(dest=dest)):
            raise Exception('compiler error while deploying')

        with open(path.join(dest, 'build/contracts/MainToken.json'), 'rb') as f:
            token_json = json.loads(f.read().decode('utf-8-sig'))
        with open(path.join(dest, 'build/MainToken.sol'), 'rb') as f:
            source_code = f.read().decode('utf-8-sig')
        tron_contract_token = TRONContract()
        tron_contract_token.abi = token_json['abi']
        tron_contract_token.bytecode = token_json['bytecode'][2:]
        tron_contract_token.compiler_version = token_json['compiler']['version']
        tron_contract_token.contract = self.contract
        tron_contract_token.original_contract = self.contract
        tron_contract_token.source_code = source_code
        tron_contract_token.save()
        self.tron_contract_token = tron_contract_token
        self.save()
        token_holders = self.contract.tokenholder_set.all()
        for th in token_holders:
            if th.address.startswith('0x'):
                th.address = '41' + th.address[2:]
                th.save()

    @blocking
    @postponable
    def deploy(self, eth_contract_attr_name='eth_contract_token'):
        self.compile()
        print('deploy tron token')
        abi = json.dumps(self.tron_contract_token.abi)

        tron = instantiate_tronapi(NETWORKS[self.contract.network.name]['private_key'], self.contract.network.name)


        contract = tron.trx.contract(
            abi=str(abi),
            bytecode=self.tron_contract_token.bytecode,
        )

        print('contract: ', contract, flush=True)

        res = contract.deploy(
            consume_user_resource_percent=0,
            fee_limit=1000000000,
            call_value=0,
            bandwidth_limit=1000000,
            owner_address='41' + convert_address_to_hex(NETWORKS[self.contract.network.name]['address'])[2:],
            origin_energy_limit=100000000
        )
        # fcntl.fcntl(1, fcntl.F_SETFL, 0)

        print('deployed contract: ', res, flush=True)

        self.tron_contract_token.address = res['contract_address']
        self.tron_contract_token.save()


        sign = tron.trx.sign(res)
        print('signed contract: ', sign, flush=True)

        res = tron.trx.broadcast(sign)
        print('broadcast: ', res, flush=True)

        if res['result']:
            self.tron_contract_token.tx_hash = res['transaction']['txID']
            self.tron_contract_token.save()
            self.contract.state = 'WAITING_FOR_DEPLOYMENT'
            self.contract.save()
            return

        raise ValidationError({'result': 1}, code=400)


    def msg_deployed(self, message, eth_contract_attr_name='eth_contract'):
        self.contract.state = 'ACTIVE'
        self.contract.save()
        self.tron_contract_token.address = message['address']
        self.tron_contract_token.save()
        take_off_blocking(self.contract.network.name)

    def ownershipTransferred(self, message):
        if self.tron_contract_token.original_contract.state not in (
                'UNDER_CROWDSALE', 'ENDED'
        ):
            self.tron_contract_token.original_contract.state = 'UNDER_CROWDSALE'
            self.tron_contract_token.original_contract.save()

    def finalized(self, message):
        if self.tron_contract_token.original_contract.state != 'ENDED':
            self.tron_contract_token.original_contract.state = 'ENDED'

            self.tron_contract_token.original_contract.save()
        if (self.tron_contract_token.original_contract.id !=
                self.tron_contract_token.contract.id and
                self.tron_contract_token.contract.state != 'ENDED'):
            self.tron_contract_token.contract.state = 'ENDED'
            self.tron_contract_token.contract.save()

    def check_contract(self):
        pass

    def initialized(self, message):
        pass


@contract_details('Game Asset contract')
class ContractDetailsGameAssets(CommonDetails):
    token_name = models.CharField(max_length=512)
    token_short_name = models.CharField(max_length=64)
    admin_address = models.CharField(max_length=50)
    temp_directory = models.CharField(max_length=36)
    uri = models.CharField(max_length=2000)
    tron_contract_token = models.ForeignKey(
        TRONContract,
        null=True,
        default=None,
        related_name='game_asset_details',
        on_delete=models.SET_NULL
    )

    def predeploy_validate(self):
        pass

    @classmethod
    def min_cost(cls):
        network = Network.objects.get(name='TRON_MAINNET')
        cost = cls.calc_cost({}, network)
        return cost

    @staticmethod
    def calc_cost(kwargs, network):
        if NETWORKS[network.name]['is_free']:
            return 0
        result = int(45 * NET_DECIMALS['USDT'])
        return result

    @classmethod
    def min_cost_tron(cls):
        network = Network.objects.get(name='TRON_MAINNET')
        cost = cls.calc_cost_tron({}, network)
        return cost

    @staticmethod
    def calc_cost_tron(kwargs, network):
        if NETWORKS[network.name]['is_free']:
            return 0
        result = int(60 * NET_DECIMALS['TRX'])
        return result

    def get_arguments(self, eth_contract_attr_name):
        return []

    def compile(self, eth_contract_attr_name='eth_contract_token'):
        print('standalone token contract compile')
        if self.temp_directory:
            print('already compiled')
            return
        dest, preproc_config = create_directory(self, sour_path='lastwill/game-assets-contract/*')
        owner = '0x' + self.admin_address[2:] if self.admin_address.startswith('41') else convert_address_to_hex(
            self.admin_address)
        preproc_params = {"constants":
            {
                "D_NAME": self.token_name,
                "D_SYMBOL": self.token_short_name,
                "D_OWNER": owner,
                "D_URI": self.uri
            }
        }
        with open(preproc_config, 'w') as f:
            f.write(json.dumps(preproc_params))
        if os.system('cd {dest} && yarn compile'.format(dest=dest)):
            raise Exception('compiler error while deploying')

        with open(path.join(dest, 'build/contracts/GameAssetsContract.json'), 'rb') as f:
            token_json = json.loads(f.read().decode('utf-8-sig'))
        with open(path.join(dest, 'build/GameAssetsContract.sol'), 'rb') as f:
            source_code = f.read().decode('utf-8-sig')
        tron_contract_token = TRONContract()
        tron_contract_token.abi = token_json['abi']
        tron_contract_token.bytecode = token_json['bytecode'][2:]
        tron_contract_token.compiler_version = token_json['compiler']['version']
        tron_contract_token.contract = self.contract
        tron_contract_token.original_contract = self.contract
        tron_contract_token.source_code = source_code
        tron_contract_token.save()
        self.tron_contract_token = tron_contract_token
        self.save()

    @blocking
    @postponable
    def deploy(self, eth_contract_attr_name='eth_contract_token'):
        self.compile()
        print('deploy tron token')
        abi = json.dumps(self.tron_contract_token.abi)

        tron = instantiate_tronapi(NETWORKS[self.contract.network.name]['private_key'], self.contract.network.name)

        contract = tron.trx.contract(
            abi=str(abi),
            bytecode=self.tron_contract_token.bytecode,
        )

        print('contract: ', contract, flush=True)

        res = contract.deploy(
            consume_user_resource_percent=0,
            fee_limit=1000000000,
            call_value=0,
            bandwidth_limit=1000000,
            owner_address='41' + convert_address_to_hex(NETWORKS[self.contract.network.name]['address'])[2:],
            origin_energy_limit=100000000
        )

        print('deployed contract: ', res, flush=True)

        self.tron_contract_token.address = res['contract_address']
        self.tron_contract_token.save()

        sign = tron.trx.sign(res)
        print('signed contract', sign, flush=True)

        res = tron.trx.broadcast(sign)
        print('broadcast: ', res, flush=True)

        if res['result']:
            self.tron_contract_token.tx_hash = res['transaction']['txID']
            self.tron_contract_token.save()
            self.contract.state = 'WAITING_FOR_DEPLOYMENT'
            self.contract.save()
            return

        raise ValidationError({'result': 1}, code=400)



    def msg_deployed(self, message, eth_contract_attr_name='eth_contract'):
        self.contract.state = 'ACTIVE'
        self.contract.save()
        self.tron_contract_token.address = message['address']
        self.tron_contract_token.save()
        take_off_blocking(self.contract.network.name)

    def ownershipTransferred(self, message):
        if self.tron_contract_token.original_contract.state not in (
                'UNDER_CROWDSALE', 'ENDED'
        ):
            self.tron_contract_token.original_contract.state = 'UNDER_CROWDSALE'
            self.tron_contract_token.original_contract.save()

    def finalized(self, message):
        if self.tron_contract_token.original_contract.state != 'ENDED':
            self.tron_contract_token.original_contract.state = 'ENDED'
            self.tron_contract_token.original_contract.save()
        if (self.tron_contract_token.original_contract.id !=
                self.tron_contract_token.contract.id and
                self.tron_contract_token.contract.state != 'ENDED'):
            self.tron_contract_token.contract.state = 'ENDED'
            self.tron_contract_token.contract.save()

    def check_contract(self):
        pass

    def initialized(self, message):
        pass


@contract_details('Tron Airdrop contract')
class ContractDetailsTRONAirdrop(CommonDetails):
    contract = models.ForeignKey(Contract, null=True)
    admin_address = models.CharField(max_length=50)
    token_address = models.CharField(max_length=50)
    temp_directory = models.CharField(max_length=36)
    tron_contract = models.ForeignKey(
        TRONContract,
        null=True,
        default=None,
        related_name='tron_airdrop_details',
        on_delete=models.SET_NULL
    )

    def get_arguments(self, *args, **kwargs):
        return [
            self.admin_address,
            self.token_address
        ]

    def predeploy_validate(self):
        pass

    @classmethod
    def min_cost(cls):
        network = Network.objects.get(name='TRON_MAINNET')
        cost = cls.calc_cost({}, network)
        return cost

    @staticmethod
    def calc_cost(kwargs, network):
        if NETWORKS[network.name]['is_free']:
            return 0
        result = int(75 * NET_DECIMALS['USDT'])
        return result

    @classmethod
    def min_cost_tron(cls):
        network = Network.objects.get(name='TRON_MAINNET')
        cost = cls.calc_cost_tron({}, network)
        return cost

    @staticmethod
    def calc_cost_tron(kwargs, network):
        if NETWORKS[network.name]['is_free']:
            return 0
        result = int(60 * NET_DECIMALS['TRX'])
        return result

    def compile(self, eth_contract_attr_name='eth_contract_token'):
        print('standalone token contract compile')
        if self.temp_directory:
            print('already compiled')
            return
        dest, preproc_config = create_directory(self, sour_path='lastwill/tron-airdrop-contract/*')
        owner = '0x' + self.admin_address[2:] if self.admin_address.startswith('41') else convert_address_to_hex(
            self.admin_address)
        token = '0x' + self.token_address[2:] if self.token_address.startswith('41') else convert_address_to_hex(
            self.token_address)
        preproc_params = {"constants": {"D_TOKEN": token, "D_TARGET": owner}}
        with open(preproc_config, 'w') as f:
            f.write(json.dumps(preproc_params))
        if os.system('cd {dest} && yarn compile'.format(dest=dest)):
            raise Exception('compiler error while deploying')

        with open(path.join(dest, 'build/contracts/AirDrop.json'), 'rb') as f:
            token_json = json.loads(f.read().decode('utf-8-sig'))
        with open(path.join(dest, 'build/AirDrop.sol'), 'rb') as f:
            source_code = f.read().decode('utf-8-sig')
        tron_contract = TRONContract()
        tron_contract.abi = token_json['abi']
        tron_contract.bytecode = token_json['bytecode'][2:]
        tron_contract.compiler_version = token_json['compiler']['version']
        tron_contract.contract = self.contract
        tron_contract.original_contract = self.contract
        tron_contract.source_code = source_code
        tron_contract.save()
        self.tron_contract = tron_contract
        self.save()

    @blocking
    @postponable
    def deploy(self, eth_contract_attr_name='eth_contract_token'):
        self.compile()
        print('deploy tron token')
        abi = json.dumps(self.tron_contract.abi)

        tron = instantiate_tronapi(NETWORKS[self.contract.network.name]['private_key'], self.contract.network.name)

        contract = tron.trx.contract(
            abi=str(abi),
            bytecode=self.tron_contract.bytecode,
        )

        print('contract: ', contract, flush=True)

        res = contract.deploy(
            consume_user_resource_percent=0,
            fee_limit=1000000000,
            call_value=0,
            bandwidth_limit=1000000,
            owner_address='41' + convert_address_to_hex(NETWORKS[self.contract.network.name]['address'])[2:],
            origin_energy_limit=100000000
        )

        print('deployed contract: ', res, flush=True)

        self.tron_contract.address = res['contract_address']
        self.tron_contract.save()

        sign = tron.trx.sign(res)
        print('signed contract', sign, flush=True)

        res = tron.trx.broadcast(sign)
        print('broadcast: ', res, flush=True)

        if res['result']:
            self.tron_contract.tx_hash = res['transaction']['txID']
            self.tron_contract.save()
            self.contract.state = 'WAITING_FOR_DEPLOYMENT'
            self.contract.save()
            return

        raise ValidationError({'result': 1}, code=400)


    def airdrop(self, message):
        message['airdroppedAddresses'] = replace_0x(message['airdroppedAddresses'])
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

    def msg_deployed(self, message, eth_contract_attr_name='eth_contract'):
        self.contract.state = 'ACTIVE'
        self.contract.save()
        self.tron_contract.address = message['address']
        self.tron_contract.save()
        take_off_blocking(self.contract.network.name)


@contract_details('Tron Lost key contract')
class ContractDetailsTRONLostkey(CommonDetails):
    user_address = models.CharField(max_length=50, null=True, default=None)
    check_interval = models.IntegerField()
    active_to = models.DateTimeField()
    last_check = models.DateTimeField(null=True, default=None)
    next_check = models.DateTimeField(null=True, default=None)
    temp_directory = models.CharField(max_length=36)
    tron_contract = models.ForeignKey(
        TRONContract,
        null=True,
        default=None,
        related_name='tron_lostkey_details',
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
            self.user_address,
            [h.address for h in self.contract.heir_set.all()],
            [h.percentage for h in self.contract.heir_set.all()],
            self.check_interval,
            False if self.contract.network.name in
                     ['ETHEREUM_MAINNET', 'ETHEREUM_ROPSTEN'] else True,
        ]

    @classmethod
    def min_cost(cls):
        network = Network.objects.get(name='TRON_MAINNET')
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
        checkCount = max(abs(
            (datetime.date.today() - active_to).total_seconds() / check_interval
        ), 1)

        heirs_num = int(kwargs['heirs_num']) if 'heirs_num' in kwargs else len(kwargs['heirs'])
        constructEnergy = 1171716
        constructNet = 7819
        heirConstructAdditionEnergy = 25722
        heirConstructAdditionNet = 78
        energyPrice = 10
        netPrice = 10
        checkEnergy = 2003
        checkNet = 280
        triggerEnergy = 8500
        triggerNet = 280
        triggerEnergyPerHeir = 40000
        triggerEnergyPerToken = 40000
        tokensCount = 20
        constructPrice = (
                constructEnergy * energyPrice
                + constructNet * netPrice
                + heirs_num * (
                        heirConstructAdditionEnergy * energyPrice
                        + heirConstructAdditionNet * netPrice
                )
        )
        checkPrice = ((checkEnergy * energyPrice + checkNet * netPrice)) * checkCount
        triggerPrice = (
                triggerEnergy * energyPrice + triggerNet
                + netPrice + triggerEnergyPerHeir * energyPrice * heirs_num
                + triggerEnergyPerToken * energyPrice * tokensCount
        )
        tron_cost = (constructPrice + checkPrice + triggerPrice) * 200 / 10 ** 6
        # result = (int(tron_cost) * convert('TRX', 'ETH')['ETH'] * 10 ** 18)
        result = int(30 * NET_DECIMALS['USDT'])
        return result

    @classmethod
    def min_cost_tron(cls):
        network = Network.objects.get(name='TRON_MAINNET')
        cost = cls.calc_cost_tron({}, network)
        return cost

    @staticmethod
    def calc_cost_tron(kwargs, network):
        if NETWORKS[network.name]['is_free']:
            return 0
        result = int(80 * NET_DECIMALS['TRX'])
        return result

    @postponable
    @check_transaction
    def msg_deployed(self, message):
        self.contract.state = 'ACTIVE'
        self.contract.save()
        self.next_check = timezone.now() + datetime.timedelta(
            seconds=self.check_interval)
        self.save()
        self.tron_contract.address = message['address']
        self.tron_contract.save()
        if self.contract.user.email:
            network = self.contract.network.name
            network_name = MAIL_NETWORK[network]
            send_mail(
                tron_deploy_subject,
                tron_deploy_text.format(
                    contract_type_name=self.contract.get_all_details_model()[
                        self.contract.contract_type]['name'],
                    network_name=network_name
                ),
                DEFAULT_FROM_EMAIL,
                [self.contract.user.email]
            )
        take_off_blocking(self.contract.network.name)

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
        for heir in heirs:
            if heir.email:
                send_mail(
                    heir_subject,
                    heir_message.format(
                        user_address=heir.address,
                        link_tx=message['transactionHash']
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
        Cg = 1270525
        CBg = 26561
        return Cg + len(self.contract.heir_set.all()) * CBg + 25000

    def compile(self, eth_contract_attr_name='eth_contract_token'):
        print('tron lostkey contract compile')
        if self.temp_directory:
            print('already compiled')
            return
        dest, preproc_config = create_directory(
            self, sour_path='lastwill/tron-lost-key-token/*',
            config_name='c-preprocessor-config.json'
        )
        owner = '0x' + self.user_address[2:] if self.user_address.startswith('41') else convert_address_to_hex(
            self.user_address)
        heirs = self.contract.heir_set.all()
        heirs_list = ','.join(map(
            lambda h: 'address(%s)' % '0x' + h.address[2:] if h.address.startswith(
                '41') else 'address(%s)' % convert_address_to_hex(h.address),
            heirs
        ))
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
            raise Exception('compiler error while deploying')

        with open(path.join(dest, 'build/contracts/LostKeyMain.json'), 'rb') as f:
            token_json = json.loads(f.read().decode('utf-8-sig'))
        with open(path.join(dest, 'build/LostKeyMain.sol'), 'rb') as f:
            source_code = f.read().decode('utf-8-sig')
        tron_contract = TRONContract()
        tron_contract.abi = token_json['abi']
        tron_contract.bytecode = token_json['bytecode'][2:]
        tron_contract.compiler_version = token_json['compiler']['version']
        tron_contract.contract = self.contract
        tron_contract.original_contract = self.contract
        tron_contract.source_code = source_code
        tron_contract.save()
        self.tron_contract = tron_contract
        self.save()

    @blocking
    @postponable
    def deploy(self, eth_contract_attr_name='eth_contract_token'):
        self.compile()
        print('deploy tron lostkey token')
        abi = json.dumps(self.tron_contract.abi)

        tron = instantiate_tronapi(NETWORKS[self.contract.network.name]['private_key'], self.contract.network.name)

        contract = tron.trx.contract(
            abi=str(abi),
            bytecode=self.tron_contract.bytecode,
        )

        print('contract: ', contract, flush=True)

        res = contract.deploy(
            consume_user_resource_percent=0,
            fee_limit=1000000000,
            call_value=0,
            bandwidth_limit=1000000,
            owner_address='41' + convert_address_to_hex(NETWORKS[self.contract.network.name]['address'])[2:],
            origin_energy_limit=100000000
        )

        print('deployed contract: ', res, flush=True)

        self.tron_contract.address = res['contract_address']
        self.tron_contract.save()

        sign = tron.trx.sign(res)
        print('signed contract: ', sign, flush=True)

        res = tron.trx.broadcast(sign)
        print('broadcast: ', res, flush=True)

        if res['result']:
            self.tron_contract.tx_hash = res['transaction']['txID']
            self.tron_contract.save()
            self.contract.state = 'WAITING_FOR_DEPLOYMENT'
            self.contract.save()
            return

        raise ValidationError({'result': 1}, code=400)


    @blocking
    def check_contract(self):
        tron = instantiate_tronapi(NETWORKS[self.contract.network.name]['private_key'], self.contract.network.name)

        tx_builder = tron.transaction_builder.trigger_smart_contract(
            contract_address=self.tron_contract.address,
            function_selector='check()',
            fee_limit=1000000000,
            owner_address='41' + convert_address_to_hex(
                NETWORKS[self.contract.network.name]['check_address'])[2:]
        )

        print('building tx: ', tx_builder, flush=True)
        tx = None
        if tx_builder['result']['result'] is True:
            tx = tx_builder['transaction']
        else:
            raise Exception('tx building error in tronish check_contract')

        signed_tx = tron.trx.sign(tx)
        print('signed tx: ', signed_tx, flush=True)
        result = tron.trx.broadcast(signed_tx)
        print('result: ', result, flush=True)
        if result['result'] is True:
            print('check_contract tronish ok', flush=True)
            print('tx: ', result['transaction'], flush=True)
            return
        else:
            print('check_contract failed', flush=True)
            print('res: ', result, flush=True)
            raise ValidationError({'result': 1}, code=400)
