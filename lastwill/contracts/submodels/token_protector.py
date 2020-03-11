from lastwill.contracts.submodels.common import *
from django.utils import timezone
from rest_framework.exceptions import ValidationError
import datetime
from lastwill.consts import NET_DECIMALS, CONTRACT_GAS_LIMIT
from django.db import models
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

    approving_time = models.IntegerField(null=True, default=None)

    day_mail_sent = models.BooleanField(default=False)
    week_mail_sent = models.BooleanField(default=False)

    def predeploy_validate(self):
        # now = timezone.now().timestamp()
        if self.end_timestamp < timezone.now().timestamp() + 30 * 60:
            raise ValidationError({'result': 1}, code=400)

    @postponable
    @check_transaction
    def msg_deployed(self, message):
        take_off_blocking(self.contract.network.name)
        self.eth_contract.address = message['address']
        self.eth_contract.save()
        self.contract.state = 'WAITING_FOR_APPROVE'
        self.contract.save()
        email = self.email if self.email else self.contract.user.email
        print('email', email, flush=True)
        try:
            send_mail(
                protector_deployed_subject,
                protector_deployed_text,
                DEFAULT_FROM_EMAIL,
                [email]
            )
        except Exception as err:
            print('deployed mail failed', str(err), flush=True)

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
            "D_OWNER_ADDRESS": checksum_encode(self.owner_address),
            "D_RESERVE_ADDRESS": checksum_encode(self.reserve_address),
            "D_BACKEND_ADDRESS": checksum_encode(NETWORKS[self.contract.network.name]['address']),
            "D_END_TIMESTAMP": self.end_timestamp
        }}

        print('params for testing', preproc_params, flush=True)
        self.compile_and_test(preproc_config, preproc_params, dest)

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

    def compile_and_test(self, config, params, dest):
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

    def try_confirm_execute(self):
        if self.approving_time:
            front_tokens_count = len(ApprovedToken.objects.filter(contract=self, approve_from_front=True))
            approved_tokens_count = len(
                ApprovedToken.objects.filter(contract=self, approve_from_scanner=True, approve_from_front=True))
            if approved_tokens_count == front_tokens_count:
                self.approving_time = None
                self.save()
                self.confirm_tokens()


    @check_transaction
    def TokenProtectorApprove(self, message):
        token_address = message['tokenAddress'].lower()
        if int(message['tokens']) > 0:
            approved_token = ApprovedToken.objects.filter(contract=self, address=token_address).first()
            if not approved_token:
                approved_token = ApprovedToken(contract=self, address=token_address,
                                               approve_from_scanner=True)
                approved_token.save()
                print('approved from scanner', flush=True)
            else:
                approved_token.approve_from_scanner = True
                approved_token.save()
                print('already approved, scanner', flush=True)
        else:
            disapproved_token = ApprovedToken.objects.filter(contract=self, address=token_address).first()
            if disapproved_token:
                disapproved_token.delete()

        self.try_confirm_execute()


    def approve_from_front(self, tokens):
        for token in tokens:
            token = token.lower()
            approved_token = ApprovedToken.objects.filter(contract=self, address=token).first()
            if not approved_token:
                approved_token = ApprovedToken(contract=self, address=token,
                                               approve_from_front=True)
                approved_token.save()
                print('approved from front')
            else:
                approved_token.approve_from_front = True
                approved_token.save()
                print('already approved, front', flush=True)

        self.approving_time = datetime.datetime.now().timestamp()
        self.save()
        if self.contract.state == 'WAITING_FOR_APPROVE':
            self.contract.state = 'WAITING_FOR_CONFIRM'
            self.contract.save()

        self.try_confirm_execute()


    def confirm_tokens(self):
        eth_int = EthereumProvider().get_provider(network=self.contract.network.name)
        w3 = Web3(HTTPProvider(eth_int.url))
        contract = w3.eth.contract(address=checksum_encode(self.eth_contract.address), abi=self.eth_contract.abi)

        tokens_to_confirm = list(map(checksum_encode, list(
            ApprovedToken.objects.filter(contract=self, is_confirmed=False).values_list('address', flat=True))))

        print('tokens to confirm', tokens_to_confirm, flush=True)

        txn = contract.functions.addTokenType(tokens_to_confirm).buildTransaction(
            {'from': checksum_encode(NETWORKS[self.contract.network.name]['address']), 'gas': self.get_gaslimit()})

        print('txn', txn, flush=True)

        nonce = int(eth_int.eth_getTransactionCount(NETWORKS[self.contract.network.name]['address'], "pending"), 16)

        signed = sign_transaction(NETWORKS[self.contract.network.name]['address'], nonce, 3000000,
                                  self.contract.network.name, value=0,
                                  dest=self.eth_contract.address, contract_data=txn['data'][2:],
                                  gas_price=2000000000)

        print('signed', signed, flush=True)

        tx_hash = eth_int.eth_sendRawTransaction('0x' + signed)

        print('hash', tx_hash, flush=True)



    def TokenProtectorTokensToSave(self, message):
        for approved_token in ApprovedToken.objects.filter(contract=self, is_confirmed=False):
            approved_token.is_confirmed = True
            approved_token.save()

        self.contract.state = 'ACTIVE'
        self.contract.save()


    def execute_contract(self):

        eth_int = EthereumProvider().get_provider(network=self.contract.network.name)
        nonce = int(eth_int.eth_getTransactionCount(NETWORKS[self.contract.network.name]['address'], "pending"), 16)

        signed = sign_transaction(NETWORKS[self.contract.network.name]['address'], nonce, 3000000,
                                  self.contract.network.name, value=0,
                                  dest=self.eth_contract.address, contract_data=None,
                                  gas_price=2000000000)

        print('signed', signed, flush=True)

        tx_hash = eth_int.eth_sendRawTransaction('0x' + signed)
        print('hash', tx_hash, flush=True)

        # except:
        self.contract.state = 'WAITING_FOR_EXECUTION'
        self.contract.save()


    def TokenProtectorTransactionInfo(self, message):
        self.contract.state = 'DONE'
        self.contract.save()


    def SelfdestructionEvent(self, message):
        self.contract.state = 'CANCELLED'
        self.contract.save()


    def execution_before_mail(self, days):
        email = self.email if self.email else self.contract.user.email
        send_mail(
            protector_execution_subject,
            protector_execution_text.format(days=days),
            DEFAULT_FROM_EMAIL,
            [email]
        )
        if days == 1:
            self.day_mail_sent = True
        else:
            self.week_mail_sent = True
        self.save()



class ApprovedToken(models.Model):
    contract = models.ForeignKey(ContractDetailsTokenProtector, related_name='tokens', on_delete=models.CASCADE)
    address = models.CharField(max_length=50)
    is_confirmed = models.BooleanField(default=False)
    approve_from_scanner = models.BooleanField(default=False)
    approve_from_front = models.BooleanField(default=False)
