from lastwill.contracts.submodels.common import *
from django.utils import timezone
from rest_framework.exceptions import ValidationError
import datetime
from lastwill.consts import NET_DECIMALS, CONTRACT_GAS_LIMIT
from django.db import models
from lastwill.settings import D_BACKEND_ADDRESS
from ethereum.utils import checksum_encode
from web3 import Web3, HTTPProvider, IPCProvider



@contract_details('Token protector contract')
class ContractDetailsTokenProtector(CommonDetails):
    owner_address = models.CharField(max_length=50)
    reserve_address = models.CharField(max_length=50)

    end_timestamp = models.IntegerField()
    email = models.CharField(max_length=200, null=True)

    eth_contract = models.ForeignKey(EthContract, null=True, default=None)

    temp_directory = models.CharField(max_length=36)

    def predeploy_validate(self):
        now = timezone.now().timestamp()
        if self.end_timestamp < now:
            raise ValidationError({'result': 1}, code=400)

    @postponable
    @check_transaction
    def msg_deployed(self, message):
        super().msg_deployed(message)
        # self.next_check = timezone.now() + datetime.timedelta(seconds=self.check_interval)
        # self.save()

    @classmethod
    def min_cost(cls):
        network = Network.objects.get(name='ETHEREUM_MAINNET')
        cost = cls.calc_cost({}, network)
        return cost

    @staticmethod
    def calc_cost_usdt(kwargs, network):
        if NETWORKS[network.name]['is_free']:
            return 0
        return int(25 * NET_DECIMALS['USDT'])

    @staticmethod
    def calc_cost(kwargs, network):
        if NETWORKS[network.name]['is_free']:
            return 0
        return int(25 * NET_DECIMALS['USDT'])


    def get_gaslimit(self):
        return CONTRACT_GAS_LIMIT['TOKEN_PROTECTOR']

    @blocking
    @postponable
    def deploy(self):
        super().deploy()

    def approve(self):
        pass

    def compile(self, eth_contract_attr_name='eth_contract_token'):
        print('token protector compiling', flush=True)
        if self.temp_directory:
            print('already compiled', flush=True)
            return
        dest, preproc_config = create_directory(
            self, sour_path='lastwill/token_saver/*',
            config_name='c-preprocessor-config.json'
        )

        preproc_params = {'constants': {
            "D_OWNER_ADDRESS": checksum_encode("0xf17f52151EbEF6C7334FAD080c5704D77216b732"),
            "D_RESERVE_ADDRESS": checksum_encode("0xf17f52151EbEF6C7334FAD080c5704D77216b732"),
            "D_BACKEND_ADDRESS": checksum_encode(NETWORKS[self.contract.network.name]['address']),
            "D_END_TIMESTAMP": self.end_timestamp
        }}

        print('params for testing', preproc_params, flush=True)
        # self.test_protector_params(preproc_config, preproc_params, dest)

        preproc_params["constants"]["D_OWNER_ADDRESS"] = checksum_encode(self.owner_address)
        preproc_params["constants"]["D_RESERVE_ADDRESS"] = checksum_encode(self.reserve_address)

        print('params', preproc_params, flush=True)

        with open(preproc_config, 'w') as f:
            f.write(json.dumps(preproc_params))
        if os.system('cd {dest} && ./compile.sh'.format(dest=dest)):
            raise Exception('compiler error while deploying')

        with open(path.join(dest, 'build/contracts/TokenSaver.json'), 'rb') as f:
            token_json = json.loads(f.read().decode('utf-8-sig'))
        with open(path.join(dest, 'contracts/TokenSaver.sol'), 'rb') as f:
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

    def test_protector_params(self, config, params, dest):
        with open(config, 'w') as f:
            f.write(json.dumps(params))
        if os.system("/bin/bash -c 'cd {dest} && ./compile.sh'".format(
                dest=dest)):
            raise Exception('compiler error while testing')
        if os.system("/bin/bash -c 'cd {dest} && ./test-compiled.sh'".format(
                dest=dest)):
            raise Exception('testing error')

    def get_arguments(self, *args, **kwargs):
        return [
        ]

    @check_transaction
    def TokenProtectorApprove(self, message):
        approved_token = ApprovedToken(contract=self, address=message['address'])
        approved_token.save()


    def confirm_tokens(self):
        w3 = Web3(HTTPProvider('http://{host}:{port}'.format(host=NETWORKS[self.contract.network.name]['host'],
                                                             port=NETWORKS[self.contract.network.name]['port'])))
        contract = w3.eth.contract(address=checksum_encode(self.eth_contract.address), abi=self.eth_contract.abi)

        tokens_to_confirm = list(ApprovedToken.objects.filter(contract=self, is_confirmed=False).values_list('address', flat=True))
        txn = contract.functions.addTokenType(
            checksum_encode(NETWORKS[self.contract.network.name]['address'])).buildTransaction(
            {'from': checksum_encode(NETWORKS[self.contract.network.name]['address']), 'gas':self.get_gaslimit()})

        eth_int = EthereumProvider().get_provider(network=self.contract.network.name)
        nonce = int(eth_int.eth_getTransactionCount(address, "pending"), 16)

        signed = sign_transaction(NETWORKS[self.contract.network.name]['address'], nonce, 3000000, self.contract.network.name, value=0,
                                       dest=self.eth_contract.address, contract_data=txn['data'][2:],
                                       gas_price=2000000000)

        hash = w3.eth.sendRawTransaction(signed)
        print('hash', hash, flush=True)

        # for approved_token in ApprovedToken.objects.filter(contract=self, is_confirmed=False):
        #     approved_token.is_confirmed = True
        #     approved_token.save()




    def finalized(self, message):
        self.contract.state = 'DONE'
        self.contract.save()

    def cancelled(self, message):
        self.contract.state = 'CANCELLED'
        self.contract.save()



class ApprovedToken(models.Model):
    contract = models.ForeignKey(ContractDetailsTokenProtector, related_name='tokens',on_delete=models.CASCADE)
    address = models.CharField(max_length=50)
    is_confirmed = models.BooleanField(default=False)


