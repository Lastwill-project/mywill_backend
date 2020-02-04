from os import path
import os
import uuid
import binascii
import pika
from copy import deepcopy
from base58 import b58decode
from ethereum import abi

from django.db import models
from django.apps import apps
from django.core.mail import send_mail
from django.contrib.auth.models import User
from django.contrib.postgres.fields import JSONField

from neo.Settings import settings
from neo.Core.Witness import Witness
from neocore.Cryptography.Crypto import Crypto
from neocore.UInt160 import UInt160


from lastwill.settings import SIGNER, CONTRACTS_DIR, CONTRACTS_TEMP_DIR
from lastwill.parint import *
from lastwill.consts import MAX_WEI_DIGITS, MAIL_NETWORK
from lastwill.deploy.models import Network
from lastwill.contracts.decorators import *
from email_messages import *


def address_to_scripthash(address):

    data = b58decode(address)
    if len(data) != 25:
        raise ValueError('Not correct Address, wrong length.')
    if data[0] != settings.ADDRESS_VERSION:
        raise ValueError('Not correct Coin Version')
    checksum = Crypto.Default().Hash256(data[:21])[:4]
    if checksum != data[21:]:
        raise Exception('Address format error')
    return UInt160(data=data[1:21]).ToBytes()


def add_token_params(params, details, token_holders, pause, cont_mint):
    params["D_ERC"] = details.token_type
    params["D_NAME"] = details.token_name
    params["D_SYMBOL"] = details.token_short_name
    params["D_DECIMALS"] = details.decimals
    params["D_CONTINUE_MINTING"] = cont_mint
    params["D_CONTRACTS_OWNER"] = "0x8ffff2c69f000c790809f6b8f9abfcbaab46b322"
    params["D_PAUSE_TOKENS"] = pause
    params["D_PREMINT_COUNT"] = len(token_holders)
    params["D_PREMINT_ADDRESSES"] = ','.join(map(
        lambda th: 'address(%s)' % th.address, token_holders
    ))
    params["D_PREMINT_AMOUNTS"] = ','.join(map(
        lambda th: 'uint(%s)' % th.amount, token_holders
    ))
    params["D_PREMINT_FREEZES"] = ','.join(map(
        lambda th: 'uint64(%s)' % (
            th.freeze_date if th.freeze_date else 0
        ), token_holders
    ))
    return params


def add_crowdsale_params(params, details, time_bonuses, amount_bonuses):
    params["D_CAN_CHANGE_START_TIME"] = "true" if details.allow_change_dates and not time_bonuses else "false"
    params["D_CAN_CHANGE_END_TIME"] = "true" if details.allow_change_dates else "false"
    params["D_START_TIME"] = details.start_date
    params["D_END_TIME"] = details.stop_date
    params["D_SOFT_CAP_WEI"] = str(details.soft_cap)
    params["D_HARD_CAP_WEI"] = str(details.hard_cap)
    params["D_RATE"] = int(details.rate)
    params["D_COLD_WALLET"] = '0x9b37d7b266a41ef130c4625850c8484cf928000d'
    params["D_CONTRACTS_OWNER"] = '0x8ffff2c69f000c790809f6b8f9abfcbaab46b322'
    params["D_AUTO_FINALISE"] = details.platform_as_admin
    params["D_BONUS_TOKENS"] = "true" if time_bonuses or amount_bonuses else "false"
    params["D_WEI_RAISED_AND_TIME_BONUS_COUNT"] = len(time_bonuses)
    params["D_WEI_RAISED_STARTS_BOUNDARIES"] = ','.join(
        map(lambda b: 'uint(%s)' % b['min_amount'], time_bonuses))
    params["D_WEI_RAISED_ENDS_BOUNDARIES"] = ','.join(
        map(lambda b: 'uint(%s)' % b['max_amount'], time_bonuses))
    params["D_TIME_STARTS_BOUNDARIES"] = ','.join(
        map(lambda b: 'uint64(%s)' % b['min_time'], time_bonuses))
    params["D_TIME_ENDS_BOUNDARIES"] = ','.join(
        map(lambda b: 'uint64(%s)' % b['max_time'], time_bonuses))
    params["D_WEI_RAISED_AND_TIME_MILLIRATES"] = ','.join(
        map(lambda b: 'uint(%s)' % (int(10 * b['bonus'])), time_bonuses))
    params["D_WEI_AMOUNT_BONUS_COUNT"] = len(amount_bonuses)
    params["D_WEI_AMOUNT_BOUNDARIES"] = ','.join(
        map(lambda b: 'uint(%s)' % b['max_amount'], reversed(amount_bonuses)))
    params["D_WEI_AMOUNT_MILLIRATES"] = ','.join(
        map(lambda b: 'uint(%s)' % (int(10 * b['bonus'])),
            reversed(amount_bonuses)))
    params["D_MYWISH_ADDRESS"] = '0xe33c67fcb6f17ecadbc6fa7e9505fc79e9c8a8fd'
    params["D_WHITELIST_ENABLED"] = details.whitelist
    return params


def add_amount_bonuses(details):
    amount_bonuses = []
    if details.amount_bonuses:
        curr_min_amount = 0
        for bonus in details.amount_bonuses:
            amount_bonuses.append({
                'max_amount': bonus['min_amount'],
                'bonus': bonus['bonus']
            })
            if int(bonus[
                       'min_amount']) > curr_min_amount:  # fill gap with zero
                amount_bonuses.append({
                    'max_amount': bonus['max_amount'],
                    'bonus': 0
                })
            curr_min_amount = int(bonus['max_amount'])
    return amount_bonuses


def add_time_bonuses(details):
    time_bonuses = deepcopy(details.time_bonuses)
    for bonus in time_bonuses:
        if bonus.get('min_time', None) is None:
            bonus['min_time'] = details.start_date
            bonus['max_time'] = details.stop_date - 5
        else:
            if int(bonus['max_time']) > int(details.stop_date) - 5:
                bonus['max_time'] = int(details.stop_date) - 5
        if bonus.get('min_amount', None) is None:
            bonus['min_amount'] = 0
            bonus['max_amount'] = details.hard_cap
    return time_bonuses


def create_ethcontract_in_compile(abi, bytecode, cv, contract, source_code):
    eth_contract_token = EthContract()
    eth_contract_token.abi = abi
    eth_contract_token.bytecode = bytecode
    eth_contract_token.compiler_version = cv
    eth_contract_token.contract = contract
    eth_contract_token.original_contract = contract
    eth_contract_token.source_code = source_code
    eth_contract_token.save()
    return eth_contract_token


def add_real_params(params, admin_address, address, wallet_address):
    params['constants']['D_CONTRACTS_OWNER'] = admin_address
    params['constants']['D_MYWISH_ADDRESS'] = address
    params['constants']['D_COLD_WALLET'] = wallet_address
    return params


def create_directory(details, sour_path='lastwill/ico-crowdsale/*', config_name='c-preprocessor-config.json'):
    details.temp_directory = str(uuid.uuid4())
    print(details.temp_directory, flush=True)
    sour = path.join(CONTRACTS_DIR, sour_path)
    dest = path.join(CONTRACTS_TEMP_DIR, details.temp_directory)
    os.mkdir(dest)
    os.system('cp -as {sour} {dest}'.format(sour=sour, dest=dest))
    preproc_config = os.path.join(dest, config_name)
    os.unlink(preproc_config)
    return dest, preproc_config


def test_investment_pool_params(config, params, dest):
    with open(config, 'w') as f:
        f.write(json.dumps(params))
    if os.system("/bin/bash -c 'cd {dest} && yarn compile'".format(
                dest=dest)):
        raise Exception('compiler error while testing')
    if os.system("/bin/bash -c 'cd {dest} &&  yarn test'".format(
            dest=dest)):
        raise Exception('testing error')


def test_crowdsale_params(config, params, dest):
    with open(config, 'w') as f:
        f.write(json.dumps(params))
    if os.system("/bin/bash -c 'cd {dest} && yarn compile-crowdsale'".format(
                dest=dest)):
        raise Exception('compiler error while testing')
    if os.system("/bin/bash -c 'cd {dest} &&  yarn test-crowdsale'".format(
            dest=dest)):
        raise Exception('testing error')


def test_token_params(config, params, dest):
    with open(config, 'w') as f:
        f.write(json.dumps(params))
    if os.system("/bin/bash -c 'cd {dest} && yarn compile-token'".format(dest=dest)):
        raise Exception('compiler error while deploying')
    if os.system("/bin/bash -c 'cd {dest} && yarn test-token'".format(dest=dest)):
        raise Exception('compiler error while testing')


def test_neo_token_params(config, params, dest):
    with open(config, 'w') as f:
        f.write(json.dumps(params))
    if os.system("/bin/bash -c 'cd {dest} && ./3_test_token.sh'".format(dest=dest)):
        raise Exception('compiler error while deploying')


def test_neo_ico_params(config, params, dest):
    with open(config, 'w') as f:
        f.write(json.dumps(params))
    if os.system("/bin/bash -c 'cd {dest} && ./3_test_crowdsale.sh'".format(dest=dest)):
        raise Exception('compiler error while deploying')


def send_in_queue(contract_id, type, queue):
    connection = pika.BlockingConnection(pika.ConnectionParameters(
        'localhost',
        5672,
        'mywill',
        pika.PlainCredentials('java', 'java'),
    ))
    channel = connection.channel()
    channel.queue_declare(queue=queue, durable=True, auto_delete=False,
                          exclusive=False)
    channel.basic_publish(
        exchange='',
        routing_key=queue,
        body=json.dumps({'status': 'COMMITTED', 'contractId': contract_id}),
        properties=pika.BasicProperties(type=type),
    )
    connection.close()


def sign_transaction(address, nonce, gaslimit, network, value=None, dest=None, contract_data=None, gas_price=None):
    data = {
        'source': address,
        'nonce': nonce,
        'gaslimit': gaslimit,
        'network': network,
    }
    if value:
        data['value'] = value
    if dest:
        data['dest'] = dest
    if contract_data:
        data['data'] = contract_data
    if gas_price:
        data['gas_price'] = gas_price

    signed_data = json.loads(requests.post(
        'http://{}/sign/'.format(SIGNER), json=data
    ).content.decode())
    return signed_data['result']


def sign_neo_transaction(tx, binary_tx, address):
    scripts = requests.post(
        'http://{}/neo_sign/'.format(SIGNER),
        json={'binary_tx': binary_tx, 'address': address}
    ).json()
    tx.scripts = [Witness(
        x['invocation'].encode(),
        x['verification'].encode(),
    ) for x in scripts]
    return tx


'''
contract as user see it at site. contract as service. can contain more then one real ethereum contracts
'''


class Contract(models.Model):
    user = models.ForeignKey(User)
    network = models.ForeignKey(Network, default=1)

    address = models.CharField(max_length=50, null=True, default=None)
    owner_address = models.CharField(max_length=50, null=True, default=None)
    user_address = models.CharField(max_length=50, null=True, default=None)

    balance = models.DecimalField(
        max_digits=MAX_WEI_DIGITS, decimal_places=0, null=True, default=None
    )
    cost = models.DecimalField(max_digits=MAX_WEI_DIGITS, decimal_places=0)

    name = models.CharField(max_length=200, null=True, default=None)
    state = models.CharField(max_length=63, default='CREATED')
    contract_type = models.IntegerField(default=0)

    source_code = models.TextField()
    bytecode = models.TextField()
    abi = JSONField(default={})
    compiler_version = models.CharField(
        max_length=200, null=True, default=None
    )

    created_date = models.DateTimeField(auto_now_add=True)
    check_interval = models.IntegerField(null=True, default=None)
    active_to = models.DateTimeField(null=True, default=None)
    last_check = models.DateTimeField(null=True, default=None)
    next_check = models.DateTimeField(null=True, default=None)

    invisible = models.BooleanField(default=False)

    def save(self, *args, **kwargs):
        # disable balance saving to prevent collisions with java daemon
        print(args)
        str_args = ','.join([str(x) for x in args])
        if self.id:
            kwargs['update_fields'] = list(
                    {f.name for f in Contract._meta.fields if f.name not in ('balance', 'id')}
                    &
                    set(kwargs.get('update_fields', [f.name for f in Contract._meta.fields]))
            )
        return super().save(*args, **kwargs)

    def get_details(self):
        # try:
            return getattr(self, self.get_details_model(
                self.contract_type
            ).__name__.lower()+'_set').first()
        # except:
        #     ducatusx_models = [
        #         apps.get_model('contracts', 'ContractDetailsDUCATUSXLastwill'),
        #         apps.get_model('contracts', 'ContractDetailsDUCATUSXLostKey'),
        #         apps.get_model('contracts', 'ContractDetailsDUCATUSXDelayedPayment'),
        #         apps.get_model('contracts', 'ContractDetailsDUCATUSXICO'),
        #         apps.get_model('contracts', 'ContractDetailsDUCATUSXToken'),
        #         apps.get_model('contracts', 'ContractDetailsDUCATUSXAirdrop'),
        #         apps.get_model('contracts', 'ContractDetailsDUCATUSXInvestmentPool'),
        #         apps.get_model('contracts', 'ContractDetailsDUCATUSXLostKeyTokens')
        #     ]
        #     for model in ducatusx_models:
        #         if model.objects.filter(contract=self).first:
        #             return model


    @classmethod
    def get_all_details_model(cls):
        contract_details_types = {}

        lastwill = apps.get_model('contracts', 'ContractDetailsLastwill')
        lostkey = apps.get_model('contracts', 'ContractDetailsLostKey')
        deffered = apps.get_model('contracts', 'ContractDetailsDelayedPayment')
        ico = apps.get_model('contracts', 'ContractDetailsICO')
        token = apps.get_model('contracts', 'ContractDetailsToken')
        neo = apps.get_model('contracts', 'ContractDetailsNeo')
        neo_ico = apps.get_model('contracts', 'ContractDetailsNeoICO')
        airdrop = apps.get_model('contracts', 'ContractDetailsAirdrop')
        investment = apps.get_model('contracts', 'ContractDetailsInvestmentPool')
        eos_token = apps.get_model('contracts', 'ContractDetailsEOSToken')
        eos_account = apps.get_model('contracts', 'ContractDetailsEOSAccount')
        eos_ico = apps.get_model('contracts', 'ContractDetailsEOSICO')
        eos_airdrop = apps.get_model('contracts', 'ContractDetailsEOSAirdrop')
        eos_token_standalone = apps.get_model('contracts', 'ContractDetailsEOSTokenSA')
        tron_token = apps.get_model('contracts', 'ContractDetailsTRONToken')
        game_asset = apps.get_model('contracts', 'ContractDetailsGameAssets')
        tron_airdrop = apps.get_model('contracts', 'ContractDetailsTRONAirdrop')
        tron_lostkey = apps.get_model('contracts', 'ContractDetailsTRONLostkey')
        eth_lostkey_tokens = apps.get_model('contracts', 'ContractDetailsLostKeyTokens')
        swap = apps.get_model('contracts', 'ContractDetailsSWAPS')
        waves = apps.get_model('contracts', 'ContractDetailsWavesSTO')
        swap2 = apps.get_model('contracts', 'ContractDetailsSWAPS2')
        token_protector = apps.get_model('contracts', 'ContractDetailsTokenProtector')

        # duc_lastwill = apps.get_model('contracts', 'ContractDetailsDUCATUSXLastwill')
        # duc_lostkey = apps.get_model('contracts', 'ContractDetailsDUCATUSXLostKey')
        # duc_deffered = apps.get_model('contracts', 'ContractDetailsDUCATUSXDelayedPayment')
        # duc_ico = apps.get_model('contracts', 'ContractDetailsDUCATUSXICO')
        duc_token = apps.get_model('contracts', 'ContractDetailsDUCATUSXToken')
        # duc_airdrop = apps.get_model('contracts', 'ContractDetailsDUCATUSXAirdrop')
        # duc_investment = apps.get_model('contracts', 'ContractDetailsDUCATUSXInvestmentPool')
        # duc_lostkey_tokens = apps.get_model('contracts', 'ContractDetailsDUCATUSXLostKeyTokens')


        contract_details_types[0] = {'name': 'Will contract', 'model': lastwill}
        contract_details_types[1] = {'name': 'Wallet contract (lost key)',
                                     'model': lostkey}
        contract_details_types[2] = {'name': 'Deferred payment contract',
                                     'model': deffered}
        contract_details_types[4] = {'name': 'MyWish ICO', 'model': ico}
        contract_details_types[5] = {'name': 'Token contract', 'model': token}
        contract_details_types[6] = {'name': 'NEO contract', 'model': neo}
        contract_details_types[7] = {'name': 'MyWish NEO ICO', 'model': neo_ico}
        contract_details_types[8] = {'name': 'Airdrop', 'model': airdrop}
        contract_details_types[9] = {'name': 'InvestmentPool', 'model': investment}
        contract_details_types[10] = {'name': 'EOS Token', 'model': eos_token}
        contract_details_types[11] = {'name': 'EOS Account', 'model': eos_account}
        contract_details_types[12] = {'name': 'EOS ICO', 'model': eos_ico}
        contract_details_types[13] = {'name': 'EOS Airdrop', 'model': eos_airdrop}
        contract_details_types[14] = {'name': 'EOS Token standalone', 'model': eos_token_standalone}
        contract_details_types[15] = {'name': 'TRON Token', 'model': tron_token}
        contract_details_types[16] = {'name': 'Game Assets', 'model': game_asset}
        contract_details_types[17] = {'name': 'TRON Airdrop', 'model': tron_airdrop}
        contract_details_types[18] = {'name': 'TRON LostKey', 'model': tron_lostkey}
        contract_details_types[19] = {'name': 'ETH LostKey with tokens', 'model': eth_lostkey_tokens}
        contract_details_types[20] = {'name': 'SWAPS Contract', 'model': swap}
        contract_details_types[22] = {'name': 'WAVES Contract STO', 'model': waves}
        contract_details_types[21] = {'name': 'SWAPS Contract', 'model': swap2}
        contract_details_types[23] = {'name': 'Token protector contract', 'model': token_protector}
        # contract_details_types[24] = {'name': 'DUCATUSX Will contract', 'model': duc_lastwill}
        # contract_details_types[25] = {'name': 'DUCATUSX Wallet contract (lost key)',
        #                              'model': duc_lostkey}
        # contract_details_types[26] = {'name': 'DUCATUSX Deferred payment contract',
        #                              'model': duc_deffered}
        # contract_details_types[27] = {'name': 'DUCATUSX MyWish ICO', 'model': duc_ico}
        contract_details_types[28] = {'name': 'DUCATUSX Token contract', 'model': duc_token}
        # contract_details_types[29] = {'name': 'DUCATUSX Airdrop', 'model': duc_airdrop}
        # contract_details_types[30] = {'name': 'DUCATUSX InvestmentPool', 'model': duc_investment}
        # contract_details_types[31] = {'name': 'DUCATUSX LostKey with tokens', 'model': duc_lostkey_tokens}

        return contract_details_types

    @classmethod
    def get_details_model(cls, contract_type):
        contract_details_types = cls.get_all_details_model()
        return contract_details_types[contract_type]['model']


class BtcKey4RSK(models.Model):
    btc_address = models.CharField(max_length=100, null=True, default=None)
    private_key = models.CharField(max_length=100, null=True, default=None)

'''
real contract to deploy to ethereum
'''


class EthContract(models.Model):
    contract = models.ForeignKey(Contract, null=True, default=None)
    original_contract = models.ForeignKey(
        Contract, null=True, default=None, related_name='orig_ethcontract'
    )
    address = models.CharField(max_length=50, null=True, default=None)
    tx_hash = models.CharField(max_length=70, null=True, default=None)

    source_code = models.TextField()
    bytecode = models.TextField()
    abi = JSONField(default={})
    compiler_version = models.CharField(
        max_length=200, null=True, default=None
    )
    constructor_arguments = models.TextField()


class CommonDetails(models.Model):
    class Meta:
        abstract = True
    contract = models.ForeignKey(Contract)

    def compile(self, eth_contract_attr_name='eth_contract'):
        print('compiling', flush=True)
        sol_path = self.sol_path
        if getattr(self, eth_contract_attr_name):
            getattr(self, eth_contract_attr_name).delete()
        sol_path = path.join(CONTRACTS_DIR, sol_path)
        with open(path.join(sol_path, self.source_filename), 'rb') as f:
            source = f.read().decode('utf-8-sig')
        result_name = path.join(sol_path, self.result_filename)
        with open(result_name, 'rb') as f:
            result =json.loads(f.read().decode('utf-8-sig'))
        eth_contract = EthContract()
        eth_contract.source_code = source
        eth_contract.compiler_version = result['compiler']['version']
        eth_contract.abi = result['abi']
        eth_contract.bytecode = result['bytecode'][2:]
        eth_contract.contract = self.contract
        eth_contract.original_contract = self.contract
        eth_contract.save()
        setattr(self, eth_contract_attr_name, eth_contract)
        self.save()

    def deploy(self, eth_contract_attr_name='eth_contract'):
        if self.contract.state not in ('CREATED', 'WAITING_FOR_DEPLOYMENT'):
            print('launch message ignored because already deployed', flush=True)
            take_off_blocking(self.contract.network.name)
            return
        self.compile(eth_contract_attr_name)
        eth_contract = getattr(self, eth_contract_attr_name)
        tr = abi.ContractTranslator(eth_contract.abi)
        arguments = self.get_arguments(eth_contract_attr_name)
        print('arguments', arguments, flush=True)
        eth_contract.constructor_arguments = binascii.hexlify(
            tr.encode_constructor_arguments(arguments)
        ).decode() if arguments else ''
        eth_int = EthereumProvider().get_provider(network=self.contract.network.name)
        address = NETWORKS[self.contract.network.name]['address']
        nonce = int(eth_int.eth_getTransactionCount(address, "pending"), 16)
        print('nonce', nonce, flush=True)
        # print('BYTECODE', eth_contract.bytecode, flush=True)
        # print('CONTRACT CODE', eth_contract.bytecode + binascii.hexlify(tr.encode_constructor_arguments(arguments)).decode() if arguments else '', flush=True)
        data = eth_contract.bytecode + (binascii.hexlify(
            tr.encode_constructor_arguments(arguments)
        ).decode() if arguments else '')
        print('data =', data)
        # if arguments:
        #     data = eth_contract.bytecode + (binascii.hexlify(
        #         tr.encode_constructor_arguments(arguments)
        #     ).decode())
        # else:
        #     data = eth_contract.bytecode

        print('DATA', data, flush=True)

        gas_price = 41 * 10 ** 9
        signed_data = sign_transaction(
            address, nonce, self.get_gaslimit(),
            self.contract.network.name, value=self.get_value(),
            contract_data=data, gas_price=gas_price
        )
        print('fields of transaction', flush=True)
        print('source', address, flush=True)
        print('gas limit', self.get_gaslimit(), flush=True)
        print('value', self.get_value(), flush=True)
        print('network', self.contract.network.name, flush=True)
        print('signed_data', signed_data, flush=True)
        eth_contract.tx_hash = eth_int.eth_sendRawTransaction(
            '0x' + signed_data
        )
        eth_contract.save()
        print('transaction sent', flush=True)
        self.contract.state = 'WAITING_FOR_DEPLOYMENT'
        self.contract.save()

    def msg_deployed(self, message, eth_contract_attr_name='eth_contract'):
        network_link = NETWORKS[self.contract.network.name]['link_address']
        network = self.contract.network.name
        network_name = MAIL_NETWORK[network]
        take_off_blocking(self.contract.network.name)
        eth_contract = getattr(self, eth_contract_attr_name)
        eth_contract.address = message['address']
        eth_contract.save()
        self.contract.state = 'ACTIVE'
        self.contract.save()
        if self.contract.user.email:
            if self.contract.contract_type ==11:
                send_mail(
                    eos_account_subject,
                    eos_account_message.format(
                        link=network_link.format(address=self.account_name),
                        network_name=network_name
                    ),
                    DEFAULT_FROM_EMAIL,
                    [self.contract.user.email]
                )
            elif self.contract.contract_type ==10:
                send_mail(
                    eos_contract_subject,
                    eos_contract_message.format(
                        token_name=self.token_short_name,
                        network_name=network_name
                    ),
                    DEFAULT_FROM_EMAIL,
                    [self.contract.user.email]
                )
            elif self.contract.contract_type == 20:
                pass
            else:
                send_mail(
                        common_subject,
                        common_text.format(
                            contract_type_name=self.contract.get_all_details_model()[self.contract.contract_type]['name'],
                            link=network_link.format(address=eth_contract.address),
                            network_name=network_name
                        ),
                        DEFAULT_FROM_EMAIL,
                        [self.contract.user.email]
                )

    def get_value(self):
        return 0

    def tx_failed(self, message):
        self.contract.state = 'POSTPONED'
        self.contract.save()
        send_mail(
            postponed_subject,
            postponed_message.format(
                contract_id=self.contract.id
            ),
            DEFAULT_FROM_EMAIL,
            [EMAIL_FOR_POSTPONED_MESSAGE]
        )
        print('contract postponed due to transaction fail', flush=True)
        take_off_blocking(self.contract.network.name, self.contract.id)
        print('queue unlocked due to transaction fail', flush=True)

    def predeploy_validate(self):
        pass

    @blocking
    def check_contract(self):
        print('checking', self.contract.name)
        tr = abi.ContractTranslator(self.eth_contract.abi)
        eth_int = EthereumProvider().get_provider(network=self.contract.network.name)
        address = self.contract.network.deployaddress_set.all()[0].address
        nonce = int(eth_int.eth_getTransactionCount(address, "pending"), 16)
        print('nonce', nonce)
        signed_data = sign_transaction(
            address, nonce, 600000, self.contract.network.name,
            dest=self.eth_contract.address,
            contract_data=binascii.hexlify(
                tr.encode_function_call('check', [])
            ).decode(),
        )
        print('signed_data', signed_data)
        eth_int.eth_sendRawTransaction('0x' + signed_data)
        print('check ok!')


@contract_details('Pizza')
class ContractDetailsPizza(CommonDetails):
    sol_path = 'lastwill/contracts/contracts/Pizza.sol'
    user_address = models.CharField(max_length=50)
    pizzeria_address = models.CharField(
        max_length=50, default='0x1eee4c7d88aadec2ab82dd191491d1a9edf21e9a'
    )
    timeout = models.IntegerField(default=60*60)
    code = models.IntegerField()
    salt = models.CharField(max_length=len(str(2**256)))
    pizza_cost = models.DecimalField(max_digits=MAX_WEI_DIGITS, decimal_places=0) # weis
    order_id = models.DecimalField(max_digits=50, decimal_places=0, unique=True)
    eth_contract = models.ForeignKey(EthContract, null=True, default=None)

    @classmethod
    def min_cost(cls):
        return 0


class Heir(models.Model):
    contract = models.ForeignKey(Contract)
    address = models.CharField(max_length=50)
    percentage = models.IntegerField()
    email = models.CharField(max_length=200, null=True)


class TokenHolder(models.Model):
    contract = models.ForeignKey(Contract)
    name = models.CharField(max_length=512, null=True)
    address = models.CharField(max_length=50)
    amount = models.DecimalField(
        max_digits=MAX_WEI_DIGITS, decimal_places=0, null=True
    )
    freeze_date = models.IntegerField(null=True)


class WhitelistAddress(models.Model):
    contract = models.ForeignKey(Contract, null=True)
    address = models.CharField(max_length=50)
    active = models.BooleanField(default=True)


class EOSTokenHolder(models.Model):
    contract = models.ForeignKey(Contract)
    name = models.CharField(max_length=512, null=True)
    address = models.CharField(max_length=50)
    amount = models.DecimalField(
        max_digits=MAX_WEI_DIGITS, decimal_places=0, null=True
    )
    freeze_date = models.IntegerField(null=True)
