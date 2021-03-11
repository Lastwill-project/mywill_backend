import datetime
import smtplib
import binascii
import string
import random
import uuid
from ethereum.abi import method_id as m_id
from eth_utils import int_to_big_endian

from django.db import transaction
from django.core.mail import send_mail, get_connection, EmailMessage
from django.utils import timezone
from rest_framework.exceptions import PermissionDenied
from rest_framework import serializers
from rest_framework.exceptions import ValidationError

import lastwill.check as check
from lastwill.parint import EthereumProvider
from lastwill.contracts.models import (
    Contract, Heir, EthContract, TokenHolder, WhitelistAddress,
    NeoContract, ContractDetailsNeoICO, ContractDetailsNeo,
    ContractDetailsToken, ContractDetailsICO,
    ContractDetailsAirdrop, AirdropAddress, TRONContract,
    ContractDetailsLastwill, ContractDetailsLostKey,
    ContractDetailsDelayedPayment, ContractDetailsInvestmentPool,
    InvestAddress, EOSTokenHolder, ContractDetailsEOSToken, EOSContract,
    ContractDetailsEOSAccount, ContractDetailsEOSICO, EOSAirdropAddress,
    ContractDetailsEOSAirdrop, ContractDetailsEOSTokenSA,
    ContractDetailsTRONToken, ContractDetailsGameAssets, ContractDetailsTRONAirdrop,
    ContractDetailsTRONLostkey, ContractDetailsLostKeyTokens,
    ContractDetailsWavesSTO, ContractDetailsSWAPS, InvestAddresses, ContractDetailsSWAPS2,
    ContractDetailsTokenProtector, ApprovedToken,
    ContractDetailsBinanceLostKeyTokens, ContractDetailsBinanceToken, ContractDetailsBinanceDelayedPayment,
    ContractDetailsBinanceLostKey, ContractDetailsBinanceLastwill, ContractDetailsBinanceInvestmentPool,
    ContractDetailsBinanceICO, ContractDetailsBinanceAirdrop,
    ContractDetailsMaticICO, ContractDetailsMaticToken, ContractDetailsMaticAirdrop,
)
from lastwill.contracts.models import send_in_queue
from lastwill.contracts.decorators import *
from lastwill.rates.api import rate
from lastwill.settings import EMAIL_HOST_USER_SWAPS, EMAIL_HOST_PASSWORD_SWAPS
from lastwill.consts import NET_DECIMALS
from lastwill.profile.models import *
from lastwill.payments.api import create_payment
from lastwill.consts import MAIL_NETWORK
import email_messages
from neocore.Cryptography.Crypto import Crypto
from neocore.UInt160 import UInt160


def count_sold_tokens(address):
    contract = EthContract.objects.get(address=address).contract
    eth_int = EthereumProvider().get_provider(contract.network.name)

    method_sign = '0x' + binascii.hexlify(
        int_to_big_endian(m_id('totalSupply', []))).decode()
    sold_tokens = eth_int.eth_call({'to': address,
                                    'data': method_sign,
                                    })
    sold_tokens = '0x0' if sold_tokens == '0x' else sold_tokens
    sold_tokens = int(sold_tokens, 16) / 10 ** contract.get_details().decimals
    return sold_tokens


def sendEMail(sub, text, mail):
    server = smtplib.SMTP('smtp.yandex.ru', 587)
    server.starttls()
    server.ehlo()
    server.login(EMAIL_HOST_USER_SWAPS, EMAIL_HOST_PASSWORD_SWAPS)
    message = "\r\n".join([
        "From: {address}".format(address=EMAIL_HOST_USER_SWAPS),
        "To: {to}".format(to=mail),
        "Subject: {sub}".format(sub=sub),
        "",
        str(text)
    ])
    server.sendmail(EMAIL_HOST_USER_SWAPS, mail, message)
    server.quit()


def deploy_swaps(contract_id):
    contract = Contract.objects.get(id=contract_id)
    if contract.state == 'WAITING_FOR_PAYMENT':
        contract_details = contract.get_details()
        contract_details.predeploy_validate()
        kwargs = ContractSerializer().get_details_serializer(
            contract.contract_type
        )().to_representation(contract_details)
        cost = contract_details.calc_cost_usdt(kwargs, contract.network)
        site_id = 4
        currency = 'USDT'
        user_info = UserSiteBalance.objects.get(user=contract.user, subsite__id=4)
        if user_info.balance >= cost or int(user_info.balance) >= cost * 0.95:
            create_payment(contract.user.id, '', currency, -cost, site_id, 'ETHEREUM_MAINNET')
            contract.state = 'WAITING_FOR_DEPLOYMENT'
            contract.save()
            queue = NETWORKS[contract.network.name]['queue']
            send_in_queue(contract.id, 'launch', queue)
    return True


def deploy_protector(contract_id):
    contract = Contract.objects.get(id=contract_id)
    if contract.state == 'WAITING_FOR_PAYMENT':
        contract_details = contract.get_details()
        contract_details.predeploy_validate()
        kwargs = ContractSerializer().get_details_serializer(
            contract.contract_type
        )().to_representation(contract_details)
        cost = contract_details.calc_cost(kwargs, contract.network)
        site_id = 5
        currency = 'USDT'
        user_info = UserSiteBalance.objects.get(user=contract.user, subsite__id=5)
        if user_info.balance >= cost or int(user_info.balance) >= cost * 0.95:
            create_payment(contract.user.id, '', currency, -cost, site_id, 'ETHEREUM_MAINNET')
            contract.state = 'WAITING_FOR_DEPLOYMENT'
            contract.save()
            queue = NETWORKS[contract.network.name]['queue']
            print('check1', flush=True)
            send_in_queue(contract.id, 'launch', queue)
        print('check2', flush=True)
    return True


class HeirSerializer(serializers.ModelSerializer):
    class Meta:
        model = Heir
        fields = ('address', 'email', 'percentage')


class TokenHolderSerializer(serializers.ModelSerializer):
    class Meta:
        model = TokenHolder
        fields = ('address', 'amount', 'freeze_date', 'name')


class ContractSerializer(serializers.ModelSerializer):
    contract_details = serializers.JSONField(write_only=True)

    class Meta:
        model = Contract
        fields = (
            'id', 'user', 'owner_address', 'state', 'created_date', 'balance',
            'cost', 'name', 'contract_type', 'contract_details', 'network',
        )
        extra_kwargs = {
            'user': {'read_only': True},
            'owner_address': {'read_only': True},
            'created_date': {'read_only': True},
            'balance': {'read_only': True},
            'cost': {'read_only': True},
            'last_check': {'read_only': True},
            'next_check': {'read_only': True},
        }

    def create(self, validated_data):
        validated_data['user'] = self.context['request'].user
        if validated_data.get('state') not in ('CREATED', 'WAITING_FOR_PAYMENT'):
            validated_data['state'] = 'CREATED'

        contract_type = validated_data['contract_type']
        details_serializer = self.get_details_serializer(
            contract_type
        )(context=self.context)
        contract_details = validated_data.pop('contract_details')
        details_serializer.validate(contract_details)
        validated_data['cost'] = Contract.get_details_model(
            contract_type
        ).calc_cost(contract_details, validated_data['network'])
        transaction.set_autocommit(False)
        try:
            contract = super().create(validated_data)
            details_serializer.create(contract, contract_details)
        except:
            transaction.rollback()
            raise
        else:
            transaction.commit()
        finally:
            transaction.set_autocommit(True)
        if validated_data['user'].email:
            network = validated_data['network']
            network_name = MAIL_NETWORK[network.name]
            if contract.contract_type not in (11, 20, 21, 23):
                send_mail(
                    email_messages.create_subject,
                    email_messages.create_message.format(
                        network_name=network_name
                    ),
                    DEFAULT_FROM_EMAIL,
                    [validated_data['user'].email]
                )
            elif contract.contract_type in (20, 21):
                sendEMail(
                    email_messages.swaps_subject,
                    email_messages.swaps_message,
                    validated_data['user'].email
                )
            elif contract.contract_type == 23:
                email = contract_details['email'] if contract_details['email'] else validated_data['user'].email
                send_mail(
                    email_messages.protector_create_subject,
                    email_messages.protector_create_text,
                    DEFAULT_FROM_EMAIL,
                    [email]
                )
            else:
                send_mail(
                    email_messages.eos_create_subject,
                    email_messages.eos_create_message.format(
                        network_name=network_name
                    ),
                    DEFAULT_FROM_EMAIL,
                    [validated_data['user'].email]
                )
        return contract

    def to_representation(self, contract):
        res = super().to_representation(contract)
        res['contract_details'] = self.get_details_serializer(
            contract.contract_type
        )(context=self.context).to_representation(contract.get_details())
        if contract.state != 'CREATED':
            usdt_cost = res['cost']
            if 'TESTNET' in contract.network.name or 'ROPSTEN' in contract.network.name:
                usdt_cost = 0
        else:
            usdt_cost = Contract.get_details_model(
                contract.contract_type
            ).calc_cost(res['contract_details'], contract.network)
        usdt_cost = int(usdt_cost)
        res['cost'] = {
            'USDT': str(usdt_cost),
            'ETH': str(int(int(usdt_cost) / 10 ** 6 * rate('USDT', 'ETH') * 10 ** 18)),
            'WISH': str(int(int(usdt_cost) / 10 ** 6 * rate('USDT', 'WISH') * 10 ** 18)),
            'BTC': str(int(round((int(usdt_cost) / 10 ** 6 * rate('USDT', 'BTC') * 10 ** 8), 0))),
            'EOS': str(int(int(usdt_cost) / 10 ** 6 * rate('USDT', 'EOS') * 10 ** 4)),
            'TRON': str(int(round((int(usdt_cost) * rate('USDT', 'TRX')), 0))),
        }
        if contract.network.name == 'EOS_MAINNET':
            res['cost']['EOS'] = str(Contract.get_details_model(
                contract.contract_type
            ).calc_cost_eos(res['contract_details'], contract.network))
            res['cost']['EOSISH'] = str(float(
                res['cost']['EOS']
            ) * rate('EOS', 'EOSISH'))
        if contract.network.name == 'EOS_TESTNET':
            res['cost']['EOS'] = 0
            res['cost']['EOSISH'] = 0
        if contract.network.name == 'TRON_MAINNET':
            res['cost']['TRX'] = str(Contract.get_details_model(
                contract.contract_type
            ).calc_cost_tron(res['contract_details'], contract.network))
            res['cost']['TRONISH'] = res['cost']['TRX']
        if contract.network.name == 'TRON_TESTNET':
            res['cost']['TRX'] = 0
            res['cost']['TRONISH'] = 0
        if contract.contract_type == 20:
            cost = Contract.get_details_model(
                contract.contract_type
            ).calc_cost_usdt(res['contract_details'], contract.network) / NET_DECIMALS['USDT']
            res['cost'] = {
                'USDT': str(int(cost * NET_DECIMALS['USDT'])),
                'ETH': str(int(cost) * rate('USDT', 'ETH') * NET_DECIMALS['ETH']),
                'WISH': str(int(cost) * rate('USDT', 'WISH') * NET_DECIMALS['WISH']),
                'BTC': str(int(cost) * rate('USDT', 'BTC') * NET_DECIMALS['BTC']),
                'BNB': str(int(cost) * rate('USDT', 'BNB') * NET_DECIMALS['BNB']),
                'SWAP': str(int(cost) * rate('USDT', 'SWAP') * NET_DECIMALS['SWAP']),
                'OKB': str(int(cost) * rate('USDT', 'OKB') * NET_DECIMALS['OKB'])
            }
        elif contract.contract_type == 23:
            cost = Contract.get_details_model(
                contract.contract_type
            ).calc_cost_usdt(res['contract_details'], contract.network) / NET_DECIMALS['USDT']
            res['cost'] = {
                'USDT': str(int(cost * NET_DECIMALS['USDT'])),
                'ETH': str(int(cost) * rate('USDT', 'ETH') * NET_DECIMALS['ETH']),
                'WISH': str(int(cost) * rate('USDT', 'WISH') * NET_DECIMALS['WISH']),
                'BTC': str(int(cost) * rate('USDT', 'BTC') * NET_DECIMALS['BTC']),
                'BNB': str(int(cost) * rate('USDT', 'BNB') * NET_DECIMALS['BNB']),
                'SWAP': str(int(cost) * rate('USDT', 'SWAP') * NET_DECIMALS['SWAP']),
                'OKB': str(int(cost) * rate('USDT', 'OKB') * NET_DECIMALS['OKB'])
            }

        return res

    def update(self, contract, validated_data):
        validated_data.pop('contract_type', None)
        if contract.state != 'CREATED':
            raise PermissionDenied()
        if 'state' in validated_data and validated_data['state'] not in ('CREATED', 'WAITING_FOR_PAYMENT'):
            del validated_data['state']

        contract_type = contract.contract_type
        contract_details = validated_data.pop('contract_details', None)
        if contract_details:
            details_serializer = self.get_details_serializer(
                contract_type
            )(context=self.context)
            details_serializer.validate(contract_details)
            validated_data['cost'] = contract.get_details_model(
                contract_type
            ).calc_cost(contract_details, validated_data['network'])
            details_serializer.update(
                contract, contract.get_details(), contract_details
            )

        return super().update(contract, validated_data)

    def get_details_serializer(self, contract_type):
        return {
            0: ContractDetailsLastwillSerializer,
            1: ContractDetailsLostKeySerializer,
            2: ContractDetailsDelayedPaymentSerializer,
            4: ContractDetailsICOSerializer,
            5: ContractDetailsTokenSerializer,
            6: ContractDetailsNeoSerializer,
            7: ContractDetailsNeoICOSerializer,
            8: ContractDetailsAirdropSerializer,
            9: ContractDetailsInvestmentPoolSerializer,
            10: ContractDetailsEOSTokenSerializer,
            11: ContractDetailsEOSAccountSerializer,
            12: ContractDetailsEOSICOSerializer,
            13: ContractDetailsEOSAirdropSerializer,
            14: ContractDetailsEOSTokenSASerializer,
            15: ContractDetailsTRONTokenSerializer,
            16: ContractDetailsGameAssetsSerializer,
            17: ContractDetailsTRONAirdropSerializer,
            18: ContractDetailsTRONLostkeySerializer,
            19: ContractDetailsLostKeyTokensSerializer,
            20: ContractDetailsSWAPSSerializer,
            22: ContractDetailsSTOSerializer,
            21: ContractDetailsSWAPS2Serializer,
            23: TokenProtectorSerializer,
            24: ContractDetailsBinanceLastwillSerializer,
            25: ContractDetailsBinanceLostKeySerializer,
            26: ContractDetailsBinanceDelayedPaymentSerializer,
            27: ContractDetailsBinanceICOSerializer,
            28: ContractDetailsBinanceTokenSerializer,
            29: ContractDetailsBinanceAirdropSerializer,
            30: ContractDetailsBinanceInvestmentPoolSerializer,
            31: ContractDetailsBinanceLostKeyTokensSerializer,
            32: ContractDetailsMaticICOSerializer,
            33: ContractDetailsMaticTokenSerializer,
            34: ContractDetailsMaticAirdropSerializer,
        }[contract_type]


class TokenProtectorSerializer(serializers.ModelSerializer):
    class Meta:
        model = ContractDetailsTokenProtector
        fields = ['owner_address', 'reserve_address', 'end_timestamp', 'email', 'with_oracle',
                  'oracle_inactive_interval']

    def to_representation(self, contract_details):
        if contract_details.end_timestamp < timezone.now().timestamp() + 30 * 60 and contract_details.contract.state in [
            'CREATED', 'WAITING_FOR_PAYMENT']:
            print('TIME_IS_UP', flush=True)
            contract_details.contract.state = 'TIME_IS_UP'
            contract_details.contract.save()
        if contract_details.approving_time:
            if contract_details.approving_time + 10 * 60 < datetime.datetime.now().timestamp():
                print('POSTPONED', flush=True)
                contract_details.approving_time = None
                contract_details.save()
                contract_details.contract.state = 'POSTPONED'
                contract_details.contract.save()
        res = super().to_representation(contract_details)
        res['eth_contract'] = EthContractSerializer().to_representation(contract_details.eth_contract)
        if contract_details.contract.network.name in ['ETHEREUM_ROPSTEN', 'RSK_TESTNET']:
            res['eth_contract']['source_code'] = ''
        if contract_details.eth_contract:
            if contract_details.eth_contract.compiler_version:
                res['eth_contract']['compiler_version'] = '.'.join(
                    res['eth_contract']['compiler_version'].split('.')[:4])

        res['approved_tokens'] = []
        for token in ApprovedToken.objects.filter(contract=contract_details):
            res['approved_tokens'].append({
                'address': token.address,
                'is_confirmed': token.is_confirmed
            })

        # print('protector representation', res, flush=True)

        return res

    def create(self, contract, contract_details):
        kwargs = contract_details.copy()
        kwargs['contract'] = contract

        eth_int = EthereumProvider().get_provider(network=contract.network.name)
        kwargs['last_account_nonce'] = int(
            eth_int.eth_getTransactionCount(contract_details['owner_address'], "pending"), 16)
        kwargs['last_active_time'] = timezone.now()
        return super().create(kwargs)

    def update(self, contract, details, contract_details):
        kwargs = contract_details.copy()
        kwargs['contract'] = contract
        return super().update(details, kwargs)

    def validate(self, contract_details):
        if 'owner_address' not in contract_details or 'reserve_address' not in contract_details or 'end_timestamp' not in contract_details:
            raise ValidationError
        check.is_address(contract_details['owner_address'])
        contract_details['owner_address'] = contract_details['owner_address'].lower()
        check.is_address(contract_details['reserve_address'])
        contract_details['reserve_address'] = contract_details['reserve_address'].lower()
        if contract_details['end_timestamp'] < timezone.now().timestamp() + 30 * 60:
            raise ValidationError

        if 'oracle_inactive_interval' not in contract_details:
            contract_details['oracle_inactive_interval'] = 24 * 3600

        return contract_details


class EthContractSerializer(serializers.ModelSerializer):
    class Meta:
        model = EthContract
        fields = (
            'id', 'address', 'source_code', 'abi',
            'bytecode', 'compiler_version', 'constructor_arguments'
        )


class EOSContractSerializer(serializers.ModelSerializer):
    class Meta:
        model = EOSContract
        fields = (
            'id', 'address', 'source_code', 'abi',
            'bytecode', 'compiler_version', 'constructor_arguments'
        )


class WhitelistAddressSerializer(serializers.ModelSerializer):
    class Meta:
        model = WhitelistAddress
        fields = ('address',)


class ContractDetailsLastwillSerializer(serializers.ModelSerializer):
    class Meta:
        model = ContractDetailsLastwill
        fields = (
            'user_address', 'active_to', 'check_interval',
            'last_check', 'next_check', 'email', 'platform_alive',
            'platform_cancel', 'last_reset', 'last_press_imalive'
        )
        extra_kwargs = {
            'last_check': {'read_only': True},
            'next_check': {'read_only': True},
            'last_reset': {'read_only': True},
            'last_press_imalive': {'read_only': True}
        }

    def to_representation(self, contract_details):
        res = super().to_representation(contract_details)
        heir_serializer = HeirSerializer()
        if not contract_details:
            print('*' * 50, contract_details.id, flush=True)
        res['heirs'] = [heir_serializer.to_representation(heir) for heir in contract_details.contract.heir_set.all()]
        res['eth_contract'] = EthContractSerializer().to_representation(contract_details.eth_contract)

        if contract_details.contract.network.name in ['RSK_MAINNET', 'RSK_TESTNET']:
            btc_key = contract_details.btc_key
            if btc_key:
                res['btc_address'] = contract_details.btc_key.btc_address
        if contract_details.contract.network.name in ['ETHEREUM_ROPSTEN', 'RSK_TESTNET']:
            res['eth_contract']['source_code'] = ''
        return res

    def create(self, contract, contract_details):
        heirs = contract_details.pop('heirs')
        for heir_json in heirs:
            heir_json['address'] = heir_json['address'].lower()
            kwargs = heir_json.copy()
            kwargs['contract'] = contract
            Heir(**kwargs).save()
        kwargs = contract_details.copy()
        kwargs['contract'] = contract
        return super().create(kwargs)

    def update(self, contract, details, contract_details):
        contract.heir_set.all().delete()
        heirs = contract_details.pop('heirs')
        for heir_json in heirs:
            heir_json['address'] = heir_json['address'].lower()
            kwargs = heir_json.copy()
            kwargs['contract'] = contract
            Heir(**kwargs).save()
        kwargs = contract_details.copy()
        kwargs['contract'] = contract
        return super().update(details, kwargs)

    def validate(self, details):
        if 'user_address' not in details or 'heirs' not in details:
            raise ValidationError
        if 'active_to' not in details or 'check_interval' not in details:
            raise ValidationError
        if details['check_interval'] > 315360000:
            raise ValidationError
        check.is_address(details['user_address'])
        details['user_address'] = details['user_address'].lower()
        details['active_to'] = datetime.datetime.strptime(
            details['active_to'], '%Y-%m-%d %H:%M'
        )
        for heir_json in details['heirs']:
            heir_json.get('email', None) and check.is_email(heir_json['email'])
            check.is_address(heir_json['address'])
            heir_json['address'] = heir_json['address'].lower()
            check.is_percent(heir_json['percentage'])
            heir_json['percentage'] = int(heir_json['percentage'])
        check.is_sum_eq_100([h['percentage'] for h in details['heirs']])
        return details


class ContractDetailsLostKeySerializer(ContractDetailsLastwillSerializer):
    class Meta:
        model = ContractDetailsLostKey
        fields = (
            'user_address',
            'active_to',
            'check_interval',
            'last_check',
            'next_check',
        )
        extra_kwargs = {
            'last_check': {'read_only': True},
            'next_check': {'read_only': True},
        }


class ContractDetailsDelayedPaymentSerializer(serializers.ModelSerializer):
    class Meta:
        model = ContractDetailsDelayedPayment
        fields = (
            'user_address', 'date', 'recepient_address', 'recepient_email'
        )

    def create(self, contract, contract_details):
        kwargs = contract_details.copy()
        kwargs['contract'] = contract
        return super().create(kwargs)

    def update(self, contract, details, contract_details):
        kwargs = contract_details.copy()
        kwargs['contract'] = contract
        return super().update(details, kwargs)

    def validate(self, details):
        if 'user_address' not in details or 'date' not in details or 'recepient_address' not in details:
            raise ValidationError
        check.is_address(details['user_address'])
        check.is_address(details['recepient_address'])
        details.get('recepient_email', None) and check.is_email(details['recepient_email'])
        return details

    def to_representation(self, contract_details):
        res = super().to_representation(contract_details)
        res['eth_contract'] = EthContractSerializer().to_representation(contract_details.eth_contract)
        if contract_details.contract.network.name in ['ETHEREUM_ROPSTEN', 'RSK_TESTNET']:
            res['eth_contract']['source_code'] = ''
        return res


class ContractDetailsICOSerializer(serializers.ModelSerializer):
    class Meta:
        model = ContractDetailsICO
        fields = (
            'soft_cap', 'hard_cap', 'token_name', 'token_short_name',
            'is_transferable_at_once', 'start_date', 'stop_date',
            'decimals', 'rate', 'admin_address', 'platform_as_admin',
            'time_bonuses', 'amount_bonuses', 'continue_minting',
            'cold_wallet_address', 'reused_token',
            'token_type', 'min_wei', 'max_wei', 'allow_change_dates',
            'whitelist',
            'verification', 'verification_status', 'verification_date_payment'
        )
        extra_kwargs = {
            'verification_status': {'read_only': True},
            'verification_date_payment': {'read_only': True},
        }

    def create(self, contract, contract_details):
        token_id = contract_details.pop('token_id', None)
        token_holders = contract_details.pop('token_holders')
        for th_json in token_holders:
            th_json['address'] = th_json['address'].lower()
            kwargs = th_json.copy()
            kwargs['contract'] = contract
            TokenHolder(**kwargs).save()
        kwargs = contract_details.copy()
        kwargs['contract'] = contract
        res = super().create(kwargs)
        if token_id:
            res.eth_contract_token_id = token_id
            res.save()
        return res

    def validate(self, details):
        now = timezone.now().timestamp() + 600
        if 'eth_contract_token' in details and 'id' in details['eth_contract_token'] and details['eth_contract_token'][
            'id']:
            token_model = EthContract.objects.get(id=details['eth_contract_token']['id'])
            token_details = token_model.contract.get_details()
            details.pop('eth_contract_token')
            details['token_name'] = token_details.token_name
            details['token_short_name'] = token_details.token_short_name
            details['decimals'] = token_details.decimals
            details['reused_token'] = True
            details['token_id'] = token_model.id
            details['token_type'] = token_details.token_type
        else:
            if '"' in details['token_name'] or '\n' in details['token_name']:
                raise ValidationError
            if '"' in details['token_short_name'] or '\n' in details['token_short_name']:
                raise ValidationError
            if details['decimals'] < 0 or details['decimals'] > 50:
                raise ValidationError
            details['reused_token'] = False
            if details.get('token_type', 'ERC20') not in ('ERC20, ERC223'):
                raise ValidationError
        for k in ('hard_cap', 'soft_cap'):
            details[k] = int(details[k])
        for k in ('max_wei', 'min_wei'):
            details[k] = (int(details[k]) if details.get(k, None) else None)
        if details['min_wei'] is not None and details['max_wei'] is not None and details['min_wei'] > details[
            'max_wei']:
            raise ValidationError
        if details['max_wei'] is not None and details['max_wei'] < 10 * 10 ** 18:
            raise ValidationError
        if 'admin_address' not in details or 'token_holders' not in details:
            raise ValidationError
        if len(details['token_holders']) > 5:
            raise ValidationError
        for th in details['token_holders']:
            th['amount'] = int(th['amount'])
        if not len(details['token_name']) or not len(details['token_short_name']):
            raise ValidationError
        if details['rate'] < 1 or details['rate'] > 10 ** 12:
            raise ValidationError
        check.is_address(details['admin_address'])
        if details['start_date'] < datetime.datetime.now().timestamp() + 5 * 60:
            raise ValidationError({'result': 1}, code=400)
        if details['stop_date'] < details['start_date'] + 5 * 60:
            raise ValidationError
        if details['hard_cap'] < details['soft_cap']:
            raise ValidationError
        if details['soft_cap'] < 0:
            raise ValidationError
        for th in details['token_holders']:
            check.is_address(th['address'])
            if th['amount'] < 0:
                raise ValidationError
            if th['freeze_date'] is not None and th['freeze_date'] < now:
                raise ValidationError({'result': 2}, code=400)
        amount_bonuses = details['amount_bonuses']
        min_amount = 0
        for bonus in amount_bonuses:
            if bonus.get('min_amount', None) is not None:
                if bonus.get('max_amount', None) is None:
                    raise ValidationError
                if int(bonus['min_amount']) < min_amount:
                    raise ValidationError
                min_amount = int(bonus['max_amount'])
            if int(bonus['min_amount']) >= int(bonus['max_amount']):
                raise ValidationError
            if bonus['bonus'] < 0.1:
                raise ValidationError
        time_bonuses = details['time_bonuses']
        for bonus in time_bonuses:
            if bonus.get('min_amount', None) is not None:
                if bonus.get('max_amount', None) is None:
                    raise ValidationError
                if not (0 <= int(bonus['min_amount']) < int(bonus['max_amount']) <= int(details['hard_cap'])):
                    raise ValidationError
            if bonus.get('min_time', None) is not None:
                if bonus.get('max_time', None) is None:
                    raise ValidationError
                if not (int(details['start_date']) <= int(bonus['min_time']) < int(bonus['max_time']) <= int(
                        details['stop_date'])):
                    raise ValidationError
            if bonus['bonus'] < 0.1:
                raise ValidationError

    def to_representation(self, contract_details):
        res = super().to_representation(contract_details)
        token_holder_serializer = TokenHolderSerializer()
        res['token_holders'] = [token_holder_serializer.to_representation(th) for th in
                                contract_details.contract.tokenholder_set.order_by('id').all()]
        res['eth_contract_token'] = EthContractSerializer().to_representation(contract_details.eth_contract_token)
        res['eth_contract_crowdsale'] = EthContractSerializer().to_representation(
            contract_details.eth_contract_crowdsale)
        res['rate'] = int(res['rate'])
        if contract_details.contract.network.name in ['ETHEREUM_ROPSTEN', 'RSK_TESTNET']:
            res['eth_contract_token']['source_code'] = ''
            res['eth_contract_crowdsale']['source_code'] = ''
        return res

    def update(self, contract, details, contract_details):
        token_id = contract_details.pop('token_id', None)
        contract.tokenholder_set.all().delete()
        token_holders = contract_details.pop('token_holders')
        for th_json in token_holders:
            th_json['address'] = th_json['address'].lower()
            kwargs = th_json.copy()
            kwargs['contract'] = contract
            TokenHolder(**kwargs).save()
        kwargs = contract_details.copy()
        kwargs['contract'] = contract
        kwargs.pop('eth_contract_token', None)
        kwargs.pop('eth_contract_crowdsale', None)

        if token_id:
            details.eth_contract_token_id = token_id
        return super().update(details, kwargs)


class ContractDetailsTokenSerializer(serializers.ModelSerializer):
    class Meta:
        model = ContractDetailsToken
        fields = (
            'token_name', 'token_short_name', 'decimals',
            'admin_address', 'token_type', 'future_minting',
            'authio', 'authio_email', 'authio_date_payment', 'authio_date_getting',
            'verification', 'verification_status', 'verification_date_payment'
        )
        extra_kwargs = {
            'authio_date_payment': {'read_only': True},
            'authio_date_getting': {'read_only': True},
            'verification_status': {'read_only': True},
            'verification_date_payment': {'read_only': True},
        }

    def create(self, contract, contract_details):
        token_holders = contract_details.pop('token_holders')
        for th_json in token_holders:
            th_json['address'] = th_json['address'].lower()
            kwargs = th_json.copy()
            kwargs['contract'] = contract
            TokenHolder(**kwargs).save()
        kwargs = contract_details.copy()
        kwargs['contract'] = contract
        return super().create(kwargs)

    def validate(self, details):
        now = timezone.now().timestamp() + 600
        if '"' in details['token_name'] or '\n' in details['token_name']:
            raise ValidationError
        if '"' in details['token_short_name'] or '\n' in details['token_short_name']:
            raise ValidationError
        if not (0 <= details['decimals'] <= 50):
            raise ValidationError
        for th in details['token_holders']:
            th['amount'] = int(th['amount'])
        if 'admin_address' not in details or 'token_holders' not in details:
            raise ValidationError
        if details['token_name'] == '' or details['token_short_name'] == '':
            raise ValidationError
        check.is_address(details['admin_address'])
        for th in details['token_holders']:
            check.is_address(th['address'])
            if th['amount'] <= 0:
                raise ValidationError
            if th['freeze_date'] is not None and th['freeze_date'] < now:
                raise ValidationError({'result': 2}, code=400)
        if 'authio' in details:
            if details['authio']:
                if not details['authio_email']:
                    raise ValidationError

    def to_representation(self, contract_details):
        res = super().to_representation(contract_details)
        token_holder_serializer = TokenHolderSerializer()
        res['token_holders'] = [token_holder_serializer.to_representation(th) for th in
                                contract_details.contract.tokenholder_set.order_by('id').all()]
        res['eth_contract_token'] = EthContractSerializer().to_representation(contract_details.eth_contract_token)
        if contract_details.eth_contract_token and contract_details.eth_contract_token.ico_details_token.filter(
                contract__state='ACTIVE'):
            res['crowdsale'] = contract_details.eth_contract_token.ico_details_token.filter(
                contract__state__in=('ACTIVE', 'ENDED')).order_by('id')[0].contract.id
        if contract_details.contract.network.name in ['ETHEREUM_ROPSTEN', 'RSK_TESTNET']:
            res['eth_contract_token']['source_code'] = ''
        return res

    def update(self, contract, details, contract_details):
        contract.tokenholder_set.all().delete()
        token_holders = contract_details.pop('token_holders')
        for th_json in token_holders:
            th_json['address'] = th_json['address'].lower()
            kwargs = th_json.copy()
            kwargs['contract'] = contract
            TokenHolder(**kwargs).save()
        kwargs = contract_details.copy()
        kwargs['contract'] = contract
        kwargs.pop('eth_contract_token', None)
        return super().update(details, kwargs)


class NeoContractSerializer(serializers.ModelSerializer):
    class Meta:
        model = NeoContract
        fields = ('id', 'address')


class ContractDetailsNeoSerializer(serializers.ModelSerializer):
    class Meta:
        model = ContractDetailsNeo
        fields = (
            'token_name', 'decimals', 'token_short_name', 'admin_address', 'future_minting',
        )

    def to_representation(self, contract_details):
        res = super().to_representation(contract_details)
        res['neo_contract_token'] = NeoContractSerializer().to_representation(contract_details.neo_contract)
        if res['neo_contract_token']['address']:
            res['neo_contract_token']['script_hash'] = res['neo_contract_token']['address']
            print('neo contract id', contract_details.contract.id, flush=True)
            res['neo_contract_token']['address'] = Crypto.ToAddress(
                UInt160.ParseString(res['neo_contract_token']['address']))
        token_holder_serializer = TokenHolderSerializer()
        res['token_holders'] = [
            token_holder_serializer.to_representation(th)
            for th in
            contract_details.contract.tokenholder_set.order_by(
                'id').all()
        ]
        if not contract_details:
            print('*' * 50, contract_details.id, flush=True)
        # res['eth_contract'] = EthContractSerializer().to_representation(contract_details.eth_contract)
        return res

    def create(self, contract, contract_details):
        token_holders = contract_details.pop('token_holders')
        for th_json in token_holders:
            th_json['address'] = th_json['address']
            kwargs = th_json.copy()
            kwargs['contract'] = contract
            TokenHolder(**kwargs).save()
        kwargs = contract_details.copy()
        kwargs['contract'] = contract
        return super().create(kwargs)

    def update(self, contract, details, contract_details):
        contract.tokenholder_set.all().delete()
        token_holders = contract_details.pop('token_holders')
        for th_json in token_holders:
            th_json['address'] = th_json['address']
            kwargs = th_json.copy()
            kwargs['contract'] = contract
            TokenHolder(**kwargs).save()
        kwargs = contract_details.copy()
        kwargs['contract'] = contract
        return super().update(details, kwargs)

    def validate(self, details):
        if details['decimals'] < 0 or details['decimals'] > 9:
            raise ValidationError
        if len(details['token_short_name']) == 0 or len(details['token_short_name']) > 9:
            raise ValidationError


class ContractDetailsNeoICOSerializer(serializers.ModelSerializer):
    class Meta:
        model = ContractDetailsNeoICO
        fields = (
            'hard_cap', 'token_name', 'token_short_name',
            'start_date', 'stop_date', 'decimals', 'rate',
            'admin_address'
        )

    def create(self, contract, contract_details):
        token_id = contract_details.pop('token_id', None)
        token_holders = contract_details.pop('token_holders')
        for th_json in token_holders:
            th_json['address'] = th_json['address']
            kwargs = th_json.copy()
            kwargs['contract'] = contract
            TokenHolder(**kwargs).save()
        kwargs = contract_details.copy()
        kwargs['contract'] = contract
        res = super().create(kwargs)
        if token_id:
            res.neo_contract_crowdsale_id = token_id
            res.save()
        return res

    def validate(self, details):
        if '"' in details['token_name'] or '\n' in details['token_name']:
            raise ValidationError
        if '"' in details['token_short_name'] or '\n' in details['token_short_name']:
            raise ValidationError
        if details['decimals'] < 0 or details['decimals'] > 9:
            raise ValidationError
        if 'admin_address' not in details:
            raise ValidationError
        if len(details['token_name']) == '' or len(details['token_short_name']) == '':
            raise ValidationError
        if not (1 <= details['rate'] <= 10 ** 12):
            raise ValidationError
        if details['start_date'] < datetime.datetime.now().timestamp() + 5 * 60:
            raise ValidationError({'result': 1}, code=400)
        if details['stop_date'] < details['start_date'] + 5 * 60:
            raise ValidationError
        details['hard_cap'] = int(details['hard_cap'])
        if details['hard_cap'] < 10:
            raise ValidationError

    def to_representation(self, contract_details):
        res = super().to_representation(contract_details)
        token_holder_serializer = TokenHolderSerializer()
        res['token_holders'] = [
            token_holder_serializer.to_representation(th) for th in
            contract_details.contract.tokenholder_set.order_by('id').all()
        ]
        res['neo_contract_crowdsale'] = NeoContractSerializer().to_representation(
            contract_details.neo_contract_crowdsale)
        if res['neo_contract_crowdsale']['address']:
            res['neo_contract_crowdsale']['script_hash'] = res['neo_contract_crowdsale']['address']
            res['neo_contract_crowdsale']['address'] = Crypto.ToAddress(
                UInt160.ParseString(res['neo_contract_crowdsale']['address']))

        res['rate'] = int(res['rate'])
        if contract_details.contract.network.name in ['ETHEREUM_ROPSTEN', 'RSK_TESTNET']:
            res['neo_contract_crowdsale']['source_code'] = ''
        return res

    def update(self, contract, details, contract_details):
        token_id = contract_details.pop('token_id', None)
        contract.tokenholder_set.all().delete()
        token_holders = contract_details.pop('token_holders')
        for th_json in token_holders:
            th_json['address'] = th_json['address']
            kwargs = th_json.copy()
            kwargs['contract'] = contract
            TokenHolder(**kwargs).save()
        kwargs = contract_details.copy()
        kwargs['contract'] = contract
        kwargs.pop('neo_contract_crowdsale', None)

        if token_id:
            details.neo_contract_crowdsale_id = token_id
        return super().update(details, kwargs)


class ContractDetailsAirdropSerializer(serializers.ModelSerializer):
    class Meta:
        model = ContractDetailsAirdrop
        fields = ('admin_address', 'token_address', 'verification', 'verification_status', 'verification_date_payment')
        extra_kwargs = {
            'verification_status': {'read_only': True},
            'verification_date_payment': {'read_only': True},
        }

    def to_representation(self, contract_details):
        res = super().to_representation(contract_details)
        res['eth_contract'] = EthContractSerializer().to_representation(contract_details.eth_contract)
        address_set = contract_details.contract.airdropaddress_set
        res['added_count'] = address_set.filter(state='added', active=True).count()
        res['processing_count'] = address_set.filter(state='processing', active=True).count()
        res['sent_count'] = address_set.filter(state='sent', active=True).count()
        res['total_sent_count'] = address_set.filter(state='sent', active=True).count() + \
                                  address_set.filter(state='completed', active=True).count()
        return res

    def create(self, contract, contract_details):
        kwargs = contract_details.copy()
        kwargs['contract'] = contract
        return super().create(kwargs)

    def update(self, contract, details, contract_details):
        kwargs = contract_details.copy()
        kwargs['contract'] = contract
        return super().update(details, kwargs)


class AirdropAddressSerializer(serializers.ModelSerializer):
    class Meta:
        model = AirdropAddress
        fields = ('address', 'amount', 'state')


class InvestAddressSerializer(serializers.ModelSerializer):
    class Meta:
        model = InvestAddress
        fields = ('address', 'amount')


@memoize_timeout(10 * 60)
def count_last_balance(contract):
    now_date = datetime.datetime.now()
    now_date = now_date - datetime.timedelta(days=1)
    if now_date.minute > 30:
        if now_date.hour != 23:
            date = datetime.datetime(
                now_date.year, now_date.month,
                now_date.day, now_date.hour + 1, 0, 0
            )
        else:
            date = datetime.datetime(
                now_date.year, now_date.month,
                now_date.day, 0, 0, 0
            )
    else:
        date = datetime.datetime(
            now_date.year, now_date.month,
            now_date.day, now_date.hour, 0, 0
        )
    invests = InvestAddress.objects.filter(contract=contract, created_date__lte=date)
    balance = 0
    for inv in invests:
        balance = balance + inv.amount
    balance = str(balance)
    return balance


class ContractDetailsInvestmentPoolSerializer(serializers.ModelSerializer):
    class Meta:
        model = ContractDetailsInvestmentPool
        fields = (
            'soft_cap', 'hard_cap', 'start_date', 'stop_date',
            'admin_address', 'admin_percent', 'token_address',
            'min_wei', 'max_wei', 'allow_change_dates', 'whitelist',
            'investment_address', 'send_tokens_hard_cap',
            'send_tokens_soft_cap', 'link', 'investment_tx_hash', 'balance',
            'platform_as_admin'
        )
        extra_kwargs = {
            'link': {'read_only': True},
            'investment_tx_hash': {'read_only': True},
            'balance': {'read_only': True},
        }

    def create(self, contract, contract_details):
        contract_details['link'] = str(uuid.uuid4())
        kwargs = contract_details.copy()
        kwargs['contract'] = contract
        res = super().create(kwargs)
        return res

    def validate(self, details):
        for k in ('hard_cap', 'soft_cap'):
            details[k] = int(details[k])
        for k in ('max_wei', 'min_wei'):
            details[k] = (int(details[k]) if details.get(k, None) else None)
        if details['min_wei'] is not None and details['max_wei'] is not None and details['min_wei'] > details[
            'max_wei']:
            raise ValidationError
        if details['max_wei'] is not None and details['max_wei'] < 10 * 10 ** 18:
            raise ValidationError
        if 'admin_address' not in details or 'admin_percent' not in details:
            raise ValidationError
        elif details['admin_percent'] < 0 or details['admin_percent'] >= 1000:
            raise ValidationError
        check.is_address(details['admin_address'])
        if details.get('token_address', None):
            check.is_address(details['token_address'])
        if details.get('investment_address', None):
            check.is_address(details['investment_address'])
        if details['start_date'] < datetime.datetime.now().timestamp() + 5 * 60:
            raise ValidationError({'result': 1}, code=400)
        if details['stop_date'] < details['start_date'] + 5 * 60:
            raise ValidationError
        if details['hard_cap'] < details['soft_cap']:
            raise ValidationError
        if details['soft_cap'] < 0:
            raise ValidationError

    def to_representation(self, contract_details):
        res = super().to_representation(contract_details)
        res['eth_contract'] = EthContractSerializer().to_representation(contract_details.eth_contract)
        if contract_details.contract.network.name in ['ETHEREUM_ROPSTEN', 'RSK_TESTNET']:
            res['eth_contract']['source_code'] = ''
        if contract_details.contract.state not in ('ACTIVE', 'CANCELLED', 'DONE', 'ENDED'):
            res.pop('link', '')
        res['last_balance'] = count_last_balance(contract_details.contract)
        return res

    def update(self, contract, details, contract_details):
        kwargs = contract_details.copy()
        kwargs['contract'] = contract
        return super().update(details, kwargs)


class EOSTokenHolderSerializer(serializers.ModelSerializer):
    class Meta:
        model = EOSTokenHolder
        fields = ('address', 'amount', 'freeze_date', 'name')


class ContractDetailsEOSTokenSerializer(serializers.ModelSerializer):
    class Meta:
        model = ContractDetailsEOSToken
        fields = ('token_short_name', 'admin_address', 'decimals', 'maximum_supply')

    def create(self, contract, contract_details):
        token_holders = contract_details.pop('token_holders')
        for th_json in token_holders:
            th_json['address'] = th_json['address']
            kwargs = th_json.copy()
            kwargs['contract'] = contract
            EOSTokenHolder(**kwargs).save()
        kwargs = contract_details.copy()
        kwargs['contract'] = contract
        res = super().create(kwargs)
        return res

    def validate(self, details):
        check.is_eos_address(details['admin_address'])
        if details['decimals'] < 0 or details['decimals'] > 15:
            raise ValidationError
        if len(details['token_short_name']) < 1 or len(details['token_short_name']) > 7:
            raise ValidationError
        details['maximum_supply'] = int(details['maximum_supply'])
        if any([x in string.punctuation for x in details['token_short_name']]):
            raise ValidationError

    def to_representation(self, contract_details):
        res = super().to_representation(contract_details)
        token_holder_serializer = EOSTokenHolderSerializer()
        res['token_holders'] = [
            token_holder_serializer.to_representation(th) for th in
            contract_details.contract.eostokenholder_set.order_by('id').all()
        ]
        res['eos_contract'] = EOSContractSerializer().to_representation(contract_details.eos_contract)
        if contract_details.contract.network.name in ['ETHEREUM_ROPSTEN', 'RSK_TESTNET', 'EOS_TESTNET']:
            res['eos_contract']['source_code'] = ''
        return res

    def update(self, contract, details, contract_details):
        contract.eostokenholder_set.all().delete()
        token_holders = contract_details.pop('token_holders')
        for th_json in token_holders:
            th_json['address'] = th_json['address']
            kwargs = th_json.copy()
            kwargs['contract'] = contract
            EOSTokenHolder(**kwargs).save()
        kwargs = contract_details.copy()
        kwargs['contract'] = contract
        return super().update(details, kwargs)


class ContractDetailsEOSAccountSerializer(serializers.ModelSerializer):
    class Meta:
        model = ContractDetailsEOSAccount
        fields = (
            'owner_public_key', 'active_public_key', 'account_name',
            'stake_net_value', 'stake_cpu_value', 'buy_ram_kbytes'
        )

    def create(self, contract, contract_details):
        kwargs = contract_details.copy()
        kwargs['contract'] = contract
        res = super().create(kwargs)
        return res

    def validate(self, details):
        check.is_eos_address(details['account_name'])
        check.is_eos_public(details['owner_public_key'])
        check.is_eos_public(details['active_public_key'])

    def to_representation(self, contract_details):
        res = super().to_representation(contract_details)
        return res

    def update(self, contract, details, contract_details):
        kwargs = contract_details.copy()
        kwargs['contract'] = contract
        return super().update(details, kwargs)


class ContractDetailsEOSICOSerializer(serializers.ModelSerializer):
    class Meta:
        model = ContractDetailsEOSICO
        fields = (
            'soft_cap', 'hard_cap', 'token_short_name', 'whitelist',
            'is_transferable_at_once', 'start_date', 'stop_date',
            'decimals', 'rate', 'crowdsale_address', 'min_wei', 'max_wei',
            'allow_change_dates', 'protected_mode', 'admin_address'
        )

    def create(self, contract, contract_details):
        token_holders = contract_details.pop('token_holders')
        for th_json in token_holders:
            th_json['address'] = th_json['address'].lower()
            kwargs = th_json.copy()
            kwargs['contract'] = contract
            EOSTokenHolder(**kwargs).save()
        kwargs = contract_details.copy()
        kwargs['contract'] = contract
        res = super().create(kwargs)
        return res

    def validate(self, details):
        if 'eos_contract_token' in details and 'id' in details['eos_contract_token'] and details['eos_contract_token'][
            'id']:
            token_model = EOSContract.objects.get(id=details['eos_contract_token']['id'])
            token_details = token_model.contract.get_details()
            details.pop('eos_contract_token')
            details['token_name'] = token_details.token_name
            details['decimals'] = token_details.decimals
            details['token_type'] = token_details.token_type
        else:
            if '"' in details['token_short_name'] or '\n' in details['token_short_name']:
                raise ValidationError
            if details['decimals'] < 0 or details['decimals'] > 50:
                raise ValidationError

        for k in ('hard_cap', 'soft_cap'):
            details[k] = int(details[k])
        if 'admin_address' not in details or 'token_holders' not in details:
            raise ValidationError
        if len(details['token_holders']) > 5:
            raise ValidationError
        for th in details['token_holders']:
            th['amount'] = int(th['amount'])
        if not len(details['token_short_name']): \
                raise ValidationError
        if details['rate'] < 1 or details['rate'] > 10 ** 12:
            raise ValidationError
        if details['start_date'] < datetime.datetime.now().timestamp() + 5 * 60:
            raise ValidationError({'result': 1}, code=400)
        if details['stop_date'] < details['start_date'] + 5 * 60:
            raise ValidationError
        if details['hard_cap'] < details['soft_cap']:
            raise ValidationError
        if details['soft_cap'] < 0:
            raise ValidationError
        for th in details['token_holders']:
            if th['amount'] < 0:
                raise ValidationError

    def to_representation(self, contract_details):
        res = super().to_representation(contract_details)
        token_holder_serializer = EOSTokenHolderSerializer()
        res['token_holders'] = [token_holder_serializer.to_representation(th) for th in
                                contract_details.contract.eostokenholder_set.order_by('id').all()]
        res['eos_contract_token'] = EOSContractSerializer().to_representation(contract_details.eos_contract_token)
        res['eos_contract_crowdsale'] = EOSContractSerializer().to_representation(
            contract_details.eos_contract_crowdsale)
        res['rate'] = int(res['rate'])
        if contract_details.contract.network.name in ['ETHEREUM_ROPSTEN', 'RSK_TESTNET']:
            res['eos_contract_token']['source_code'] = ''
            res['eos_contract_crowdsale']['source_code'] = ''
        return res

    def update(self, contract, details, contract_details):
        contract.eostokenholder_set.all().delete()
        token_holders = contract_details.pop('token_holders')
        for th_json in token_holders:
            th_json['address'] = th_json['address'].lower()
            kwargs = th_json.copy()
            kwargs['contract'] = contract
            EOSTokenHolder(**kwargs).save()
        kwargs = contract_details.copy()
        kwargs['contract'] = contract
        kwargs.pop('eos_contract_token', None)
        kwargs.pop('eos_contract_crowdsale', None)

        return super().update(details, kwargs)


class ContractDetailsEOSAirdropSerializer(serializers.ModelSerializer):
    class Meta:
        model = ContractDetailsEOSAirdrop
        fields = (
            'admin_address', 'token_address', 'token_short_name', 'address_count'
        )
        extra_kwargs = {
            'link': {'memo': True},
        }

    def to_representation(self, contract_details):
        res = super().to_representation(contract_details)
        res['eos_contract'] = EOSContractSerializer().to_representation(contract_details.eos_contract)
        res['added_count'] = contract_details.contract.eosairdropaddress_set.filter(state='added', active=True).count()
        res['processing_count'] = contract_details.contract.eosairdropaddress_set.filter(state='processing',
                                                                                         active=True).count()
        res['sent_count'] = contract_details.contract.eosairdropaddress_set.filter(state='sent', active=True).count()
        res['failed'] = contract_details.contract.eosairdropaddress_set.filter(state='failed', active=True).count()
        return res

    def create(self, contract, contract_details):
        kwargs = contract_details.copy()
        kwargs['contract'] = contract
        return super().create(kwargs)

    def update(self, contract, details, contract_details):
        kwargs = contract_details.copy()
        kwargs['contract'] = contract
        return super().update(details, kwargs)

    def validate(self, details):
        check.is_eos_address(details['admin_address'])
        check.is_eos_address(details['token_address'])


class EOSAirdropAddressSerializer(serializers.ModelSerializer):
    class Meta:
        model = EOSAirdropAddress
        fields = ('address', 'amount', 'state')


class ContractDetailsEOSTokenSASerializer(serializers.ModelSerializer):
    class Meta:
        model = ContractDetailsEOSTokenSA
        fields = ('token_short_name', 'token_account', 'admin_address', 'decimals', 'maximum_supply')

    def validate(self, details):
        check.is_eos_address(details['admin_address'])
        check.is_eos_address(details['token_account'])
        if details['decimals'] < 0 or details['decimals'] > 15:
            raise ValidationError
        details['maximum_supply'] = int(details['maximum_supply'])
        if any([x in string.punctuation for x in details['token_short_name']]):
            raise ValidationError

    def to_representation(self, contract_details):
        res = super().to_representation(contract_details)
        res['eos_contract'] = EOSContractSerializer().to_representation(contract_details.eos_contract)
        if contract_details.contract.network.name == 'EOS_TESTNET':
            res['eos_contract']['source_code'] = ''
        return res

    def create(self, contract, contract_details):
        kwargs = contract_details.copy()
        kwargs['contract'] = contract
        return super().create(kwargs)

    def update(self, contract, details, contract_details):
        kwargs = contract_details.copy()
        kwargs['contract'] = contract
        return super().update(details, kwargs)


class TRONContractSerializer(serializers.ModelSerializer):
    class Meta:
        model = TRONContract
        fields = (
            'id', 'address', 'source_code', 'abi',
            'bytecode', 'compiler_version', 'constructor_arguments'
        )


class ContractDetailsTRONTokenSerializer(serializers.ModelSerializer):
    class Meta:
        model = ContractDetailsTRONToken
        fields = (
            'token_name', 'token_short_name', 'decimals',
            'admin_address', 'token_type', 'future_minting',
        )

    def create(self, contract, contract_details):
        token_holders = contract_details.pop('token_holders')
        for th_json in token_holders:
            th_json['address'] = th_json['address']
            kwargs = th_json.copy()
            kwargs['contract'] = contract
            TokenHolder(**kwargs).save()
        kwargs = contract_details.copy()
        kwargs['contract'] = contract
        return super().create(kwargs)

    def validate(self, details):
        now = timezone.now().timestamp() + 600
        if '"' in details['token_name'] or '\n' in details['token_name']:
            raise ValidationError
        if '"' in details['token_short_name'] or '\n' in details[
            'token_short_name']:
            raise ValidationError
        if not (0 <= details['decimals'] <= 50):
            raise ValidationError
        for th in details['token_holders']:
            th['amount'] = int(th['amount'])
        if 'admin_address' not in details or 'token_holders' not in details:
            raise ValidationError
        if details['token_name'] == '' or details['token_short_name'] == '':
            raise ValidationError
        for th in details['token_holders']:
            if th['amount'] <= 0:
                raise ValidationError
            if th['freeze_date'] is not None and th['freeze_date'] < now:
                raise ValidationError({'result': 2}, code=400)

    def to_representation(self, contract_details):
        res = super().to_representation(contract_details)
        token_holder_serializer = TokenHolderSerializer()
        res['token_holders'] = [token_holder_serializer.to_representation(th)
                                for th in
                                contract_details.contract.tokenholder_set.order_by(
                                    'id').all()]
        res['tron_contract_token'] = TRONContractSerializer().to_representation(
            contract_details.tron_contract_token)
        return res

    def update(self, contract, details, contract_details):
        contract.tokenholder_set.all().delete()
        token_holders = contract_details.pop('token_holders')
        for th_json in token_holders:
            th_json['address'] = th_json['address']
            kwargs = th_json.copy()
            kwargs['contract'] = contract
            TokenHolder(**kwargs).save()
        kwargs = contract_details.copy()
        kwargs['contract'] = contract
        kwargs.pop('tron_contract_token', None)
        return super().update(details, kwargs)


class ContractDetailsGameAssetsSerializer(serializers.ModelSerializer):
    class Meta:
        model = ContractDetailsGameAssets
        fields = (
            'token_name', 'token_short_name', 'admin_address', 'uri'
        )

    def create(self, contract, contract_details):
        kwargs = contract_details.copy()
        kwargs['contract'] = contract
        return super().create(kwargs)

    def validate(self, details):
        if '"' in details['token_name'] or '\n' in details['token_name']:
            raise ValidationError
        if '"' in details['token_short_name'] or '\n' in details[
            'token_short_name']:
            raise ValidationError
        if 'admin_address' not in details:
            raise ValidationError
        if details['token_name'] == '' or details['token_short_name'] == '':
            raise ValidationError

    def to_representation(self, contract_details):
        res = super().to_representation(contract_details)
        res['tron_contract_token'] = TRONContractSerializer().to_representation(
            contract_details.tron_contract_token)
        return res

    def update(self, contract, details, contract_details):
        kwargs = contract_details.copy()
        kwargs['contract'] = contract
        kwargs.pop('tron_contract_token', None)
        return super().update(details, kwargs)


class ContractDetailsTRONAirdropSerializer(serializers.ModelSerializer):
    class Meta:
        model = ContractDetailsTRONAirdrop
        fields = ('admin_address', 'token_address')

    def to_representation(self, contract_details):
        res = super().to_representation(contract_details)
        res['tron_contract'] = TRONContractSerializer().to_representation(contract_details.tron_contract)
        res['added_count'] = contract_details.contract.airdropaddress_set.filter(state='added', active=True).count()
        res['processing_count'] = contract_details.contract.airdropaddress_set.filter(state='processing',
                                                                                      active=True).count()
        res['sent_count'] = contract_details.contract.airdropaddress_set.filter(state='sent', active=True).count()
        return res

    def create(self, contract, contract_details):
        kwargs = contract_details.copy()
        kwargs['contract'] = contract
        return super().create(kwargs)

    def update(self, contract, details, contract_details):
        kwargs = contract_details.copy()
        kwargs['contract'] = contract
        return super().update(details, kwargs)


class ContractDetailsTRONLostkeySerializer(serializers.ModelSerializer):
    class Meta:
        model = ContractDetailsTRONLostkey
        fields = (
            'user_address', 'active_to', 'check_interval',
            'last_check', 'next_check', 'email', 'platform_alive',
            'platform_cancel', 'last_reset', 'last_press_imalive'
        )
        extra_kwargs = {
            'last_check': {'read_only': True},
            'next_check': {'read_only': True},
            'last_reset': {'read_only': True},
            'last_press_imalive': {'read_only': True}
        }

    def to_representation(self, contract_details):
        res = super().to_representation(contract_details)
        heir_serializer = HeirSerializer()
        if not contract_details:
            print('*' * 50, contract_details.id, flush=True)
        res['heirs'] = [heir_serializer.to_representation(heir) for heir in contract_details.contract.heir_set.all()]
        res['tron_contract'] = TRONContractSerializer().to_representation(contract_details.tron_contract)
        return res

    def create(self, contract, contract_details):
        heirs = contract_details.pop('heirs')
        for heir_json in heirs:
            heir_json['address'] = heir_json['address']
            kwargs = heir_json.copy()
            kwargs['contract'] = contract
            Heir(**kwargs).save()
        kwargs = contract_details.copy()
        kwargs['contract'] = contract
        return super().create(kwargs)

    def update(self, contract, details, contract_details):
        contract.heir_set.all().delete()
        heirs = contract_details.pop('heirs')
        for heir_json in heirs:
            heir_json['address'] = heir_json['address']
            kwargs = heir_json.copy()
            kwargs['contract'] = contract
            Heir(**kwargs).save()
        kwargs = contract_details.copy()
        kwargs['contract'] = contract
        return super().update(details, kwargs)

    def validate(self, details):
        now = timezone.now()
        if 'user_address' not in details or 'heirs' not in details:
            raise ValidationError
        if 'active_to' not in details or 'check_interval' not in details:
            raise ValidationError
        if details['check_interval'] > 315360000:
            raise ValidationError
        details['user_address'] = details['user_address']
        details['active_to'] = datetime.datetime.strptime(
            details['active_to'], '%Y-%m-%d %H:%M'
        )
        for heir_json in details['heirs']:
            heir_json.get('email', None) and check.is_email(heir_json['email'])

            heir_json['address'] = heir_json['address']
            check.is_percent(heir_json['percentage'])
            heir_json['percentage'] = int(heir_json['percentage'])
        check.is_sum_eq_100([h['percentage'] for h in details['heirs']])
        return details


class ContractDetailsLostKeyTokensSerializer(serializers.ModelSerializer):
    class Meta:
        model = ContractDetailsLostKeyTokens
        fields = (
            'user_address', 'active_to', 'check_interval',
            'last_check', 'next_check', 'email', 'platform_alive',
            'platform_cancel', 'last_reset', 'last_press_imalive'
        )
        extra_kwargs = {
            'last_check': {'read_only': True},
            'next_check': {'read_only': True},
            'last_reset': {'read_only': True},
            'last_press_imalive': {'read_only': True}
        }

    def to_representation(self, contract_details):
        res = super().to_representation(contract_details)
        heir_serializer = HeirSerializer()
        if not contract_details:
            print('*' * 50, contract_details.id, flush=True)
        res['heirs'] = [heir_serializer.to_representation(heir) for heir in contract_details.contract.heir_set.all()]
        res['eth_contract'] = EthContractSerializer().to_representation(contract_details.eth_contract)

        if contract_details.contract.network.name in ['ETHEREUM_ROPSTEN', 'RSK_TESTNET']:
            res['eth_contract']['source_code'] = ''
        return res

    def create(self, contract, contract_details):
        heirs = contract_details.pop('heirs')
        for heir_json in heirs:
            heir_json['address'] = heir_json['address'].lower()
            kwargs = heir_json.copy()
            kwargs['contract'] = contract
            Heir(**kwargs).save()
        kwargs = contract_details.copy()
        kwargs['contract'] = contract
        return super().create(kwargs)

    def update(self, contract, details, contract_details):
        contract.heir_set.all().delete()
        heirs = contract_details.pop('heirs')
        for heir_json in heirs:
            heir_json['address'] = heir_json['address'].lower()
            kwargs = heir_json.copy()
            kwargs['contract'] = contract
            Heir(**kwargs).save()
        kwargs = contract_details.copy()
        kwargs['contract'] = contract
        return super().update(details, kwargs)

    def validate(self, details):
        if 'user_address' not in details or 'heirs' not in details:
            raise ValidationError
        if 'active_to' not in details or 'check_interval' not in details:
            raise ValidationError
        if details['check_interval'] > 315360000:
            raise ValidationError
        check.is_address(details['user_address'])
        details['user_address'] = details['user_address'].lower()
        details['active_to'] = datetime.datetime.strptime(
            details['active_to'], '%Y-%m-%d %H:%M'
        )
        for heir_json in details['heirs']:
            heir_json.get('email', None) and check.is_email(heir_json['email'])
            check.is_address(heir_json['address'])
            heir_json['address'] = heir_json['address'].lower()
            check.is_percent(heir_json['percentage'])
            heir_json['percentage'] = int(heir_json['percentage'])
        check.is_sum_eq_100([h['percentage'] for h in details['heirs']])
        return details


class InvestAddressesSerializer(serializers.ModelSerializer):
    class Meta:
        model = InvestAddresses
        fields = ('address', 'amount')


class ContractDetailsSWAPSSerializer(serializers.ModelSerializer):
    class Meta:
        model = ContractDetailsSWAPS
        fields = (
            'base_address', 'quote_address', 'stop_date', 'base_limit',
            'quote_limit', 'public', 'owner_address', 'unique_link'
        )
        extra_kwargs = {
            'unique_link': {'read_only': True}
        }

    def to_representation(self, contract_details):
        now = timezone.now()
        if contract_details.contract.state == 'ACTIVE' and contract_details.stop_date < now:
            contract_details.contract.state = 'EXPIRED'
            contract_details.contract.save()
        res = super().to_representation(contract_details)
        # investors_serializer = InvestAddressesSerializer()
        if not contract_details:
            print('*' * 50, contract_details.id, flush=True)
        # res['investors'] = [investors_serializer.to_representation(investor) for investor in contract_details.contract.investoraddresses_set.all()]
        res['eth_contract'] = EthContractSerializer().to_representation(contract_details.eth_contract)

        if contract_details.contract.network.name in ['ETHEREUM_ROPSTEN', 'RSK_TESTNET']:
            res['eth_contract']['source_code'] = ''
        return res

    def create(self, contract, contract_details):
        kwargs = contract_details.copy()
        kwargs['contract'] = contract
        return super().create(kwargs)

    def update(self, contract, details, contract_details):
        kwargs = contract_details.copy()
        kwargs['contract'] = contract
        return super().update(details, kwargs)

    def validate(self, details):
        if 'owner_address' not in details:
            raise ValidationError
        if 'stop_date' not in details:
            raise ValidationError
        check.is_address(details['owner_address'])
        details['owner_address'] = details['owner_address'].lower()
        details['stop_date'] = datetime.datetime.strptime(
            details['stop_date'], '%Y-%m-%d %H:%M'
        )
        details['base_limit'] = int(details['base_limit'])
        details['quote_limit'] = int(details['quote_limit'])
        if details['base_address'].lower() == details['quote_address'].lower():
            raise ValidationError({'result': 1}, code=400)
        return details


class ContractDetailsSWAPS2Serializer(serializers.ModelSerializer):
    class Meta:
        model = ContractDetailsSWAPS2
        fields = (
            'base_address', 'quote_address', 'stop_date', 'base_limit',
            'quote_limit', 'public', 'owner_address', 'unique_link', 'min_quote_wei',
            'memo_contract', 'whitelist', 'whitelist_address', 'min_base_wei',
            'broker_fee', 'broker_fee_address', 'broker_fee_base', 'broker_fee_quote'
        )
        extra_kwargs = {
            'unique_link': {'read_only': True},
            'memo_contract': {'read_only': True}
        }

    def to_representation(self, contract_details):
        now = timezone.now()
        if contract_details.contract.state == 'ACTIVE' and contract_details.stop_date < now:
            contract_details.contract.state = 'EXPIRED'
            contract_details.contract.save()
        res = super().to_representation(contract_details)
        if not contract_details:
            print('*' * 50, contract_details.id, flush=True)
        res['eth_contract'] = EthContractSerializer().to_representation(contract_details.eth_contract)

        if contract_details.contract.network.name in ['ETHEREUM_ROPSTEN', 'RSK_TESTNET']:
            res['eth_contract']['source_code'] = ''
        return res

    def create(self, contract, contract_details):
        contract_details['memo_contract'] = '0x' + ''.join(
            random.choice('abcdef' + string.digits) for _ in
            range(64)
        )
        kwargs = contract_details.copy()
        kwargs['contract'] = contract
        return super().create(kwargs)

    def update(self, contract, details, contract_details):
        kwargs = contract_details.copy()
        kwargs['contract'] = contract
        return super().update(details, kwargs)

    def validate(self, details):
        if 'owner_address' not in details:
            raise ValidationError
        if 'stop_date' not in details:
            raise ValidationError
        check.is_address(details['owner_address'])
        details['owner_address'] = details['owner_address'].lower()
        details['stop_date'] = datetime.datetime.strptime(
            details['stop_date'], '%Y-%m-%d %H:%M'
        )
        details['base_limit'] = int(details['base_limit'])
        details['quote_limit'] = int(details['quote_limit'])
        if details['base_address'].lower() == details['quote_address'].lower():
            raise ValidationError({'result': 1}, code=400)
        return details


class ContractDetailsSTOSerializer(serializers.ModelSerializer):
    class Meta:
        model = ContractDetailsWavesSTO
        fields = (
            'asset_id', 'admin_address', 'cold_wallet_address', 'start_date',
            'stop_date', 'rate', 'whitelist', 'soft_cap', 'hard_cap', 'min_wei',
            'max_wei', 'reused_token', 'token_description', 'token_short_name',
            'decimals', 'allow_change_dates', 'total_supply'
        )

    def to_representation(self, contract_details):
        res = super().to_representation(contract_details)
        if not contract_details:
            print('*' * 50, contract_details.id, flush=True)
        res['ride_contract'] = EthContractSerializer().to_representation(contract_details.ride_contract)
        return res

    def create(self, contract, contract_details):
        kwargs = contract_details.copy()
        kwargs['contract'] = contract
        return super().create(kwargs)

    def update(self, contract, details, contract_details):
        kwargs = contract_details.copy()
        kwargs['contract'] = contract
        return super().update(details, kwargs)

    def validate(self, details):
        if details['rate'] < 1 or details['rate'] > 10 ** 18:
            raise ValidationError
        if 'admin_address' not in details:
            raise ValidationError
        if int(details['hard_cap']) > 922337203685477580:
            raise ValidationError
        if 'total_supply' in details:
            if int(details['total_supply']) > 922337203685477580:
                raise ValidationError
        if 'max_wei' in details and 'min_wei' in details:
            if int(details['min_wei']) > int(details['max_wei']) or int(details['max_wei']) > 922337203685477580:
                raise ValidationError
        if 'decimals' in details:
            if details['decimals'] > 8 or details['decimals'] < 0:
                raise ValidationError
        details['start_date'] = datetime.datetime.strptime(
            details['start_date'], '%Y-%m-%d %H:%M'
        )
        details['stop_date'] = datetime.datetime.strptime(
            details['stop_date'], '%Y-%m-%d %H:%M'
        )
        if details['start_date'] < datetime.datetime.now() + datetime.timedelta(minutes=5):
            raise ValidationError({'result': 1}, code=400)
        if details['stop_date'] < details['start_date'] + datetime.timedelta(minutes=5):
            raise ValidationError
        if details['stop_date'] < details['start_date']:
            raise ValidationError
        # details['start_date'] = details['start_date'] // 1000
        # details['stop_date'] = details['stop_date'] // 1000
        if 'soft_cap' not in details:
            details['soft_cap'] = 0
        return details


class ContractDetailsBinanceAirdropSerializer(ContractDetailsAirdropSerializer):
    class Meta(ContractDetailsAirdropSerializer.Meta):
        model = ContractDetailsBinanceAirdrop

    def to_representation(self, contract_details):
        res = super().to_representation(contract_details)
        res['eth_contract'] = EthContractSerializer().to_representation(contract_details.eth_contract)
        address_set = contract_details.contract.airdropaddress_set
        res['added_count'] = address_set.filter(state='added', active=True).count()
        res['processing_count'] = address_set.filter(state='processing', active=True).count()
        res['sent_count'] = address_set.filter(state='sent', active=True).count()
        res['total_sent_count'] = address_set.filter(state='sent', active=True).count() + \
                                  address_set.filter(state='completed', active=True).count()
        return res


class ContractDetailsBinanceDelayedPaymentSerializer(ContractDetailsDelayedPaymentSerializer):
    class Meta(ContractDetailsDelayedPaymentSerializer.Meta):
        model = ContractDetailsBinanceDelayedPayment

    def to_representation(self, contract_details):
        res = super().to_representation(contract_details)
        res['eth_contract'] = EthContractSerializer().to_representation(contract_details.eth_contract)
        if contract_details.contract.network.name in ['BINANCE_SMART_TESTNET']:
            res['eth_contract']['source_code'] = ''
        return res


class ContractDetailsBinanceICOSerializer(ContractDetailsICOSerializer):
    class Meta(ContractDetailsICOSerializer.Meta):
        model = ContractDetailsBinanceICO

    def to_representation(self, contract_details):
        res = super().to_representation(contract_details)
        token_holder_serializer = TokenHolderSerializer()
        res['token_holders'] = [token_holder_serializer.to_representation(th) for th in
                                contract_details.contract.tokenholder_set.order_by('id').all()]
        res['eth_contract_token'] = EthContractSerializer().to_representation(contract_details.eth_contract_token)
        res['eth_contract_crowdsale'] = EthContractSerializer().to_representation(
            contract_details.eth_contract_crowdsale)
        res['rate'] = int(res['rate'])
        if contract_details.contract.network.name in ['BINANCE_SMART_TESTNET']:
            res['eth_contract_token']['source_code'] = ''
            res['eth_contract_crowdsale']['source_code'] = ''
        return res


class ContractDetailsBinanceInvestmentPoolSerializer(ContractDetailsInvestmentPoolSerializer):
    class Meta(ContractDetailsInvestmentPoolSerializer.Meta):
        model = ContractDetailsBinanceInvestmentPool

    def to_representation(self, contract_details):
        res = super().to_representation(contract_details)
        res['eth_contract'] = EthContractSerializer().to_representation(contract_details.eth_contract)
        if contract_details.contract.network.name in ['BINANCE_SMART_TESTNET']:
            res['eth_contract']['source_code'] = ''
        if contract_details.contract.state not in ('ACTIVE', 'CANCELLED', 'DONE', 'ENDED'):
            res.pop('link', '')
        res['last_balance'] = count_last_balance(contract_details.contract)
        return res


class ContractDetailsBinanceLastwillSerializer(ContractDetailsLastwillSerializer):
    class Meta(ContractDetailsLastwillSerializer.Meta):
        model = ContractDetailsBinanceLastwill

    def to_representation(self, contract_details):
        res = super().to_representation(contract_details)
        heir_serializer = HeirSerializer()
        if not contract_details:
            print('*' * 50, contract_details.id, flush=True)
        res['heirs'] = [heir_serializer.to_representation(heir) for heir in contract_details.contract.heir_set.all()]
        res['eth_contract'] = EthContractSerializer().to_representation(contract_details.eth_contract)

        if contract_details.contract.network.name in ['BINANCE_SMART_TESTNET']:
            res['eth_contract']['source_code'] = ''
        return res


class ContractDetailsBinanceLostKeySerializer(ContractDetailsLostKeySerializer):
    class Meta(ContractDetailsLostKeySerializer.Meta):
        model = ContractDetailsBinanceLostKey


class ContractDetailsBinanceLostKeyTokensSerializer(ContractDetailsLostKeyTokensSerializer):
    class Meta(ContractDetailsLostKeyTokensSerializer.Meta):
        model = ContractDetailsBinanceLostKeyTokens

    def to_representation(self, contract_details):
        res = super().to_representation(contract_details)
        heir_serializer = HeirSerializer()
        if not contract_details:
            print('*' * 50, contract_details.id, flush=True)
        res['heirs'] = [heir_serializer.to_representation(heir) for heir in contract_details.contract.heir_set.all()]
        res['eth_contract'] = EthContractSerializer().to_representation(contract_details.eth_contract)

        if contract_details.contract.network.name in ['BINANCE_SMART_TESTNET']:
            res['eth_contract']['source_code'] = ''
        return res


class ContractDetailsBinanceTokenSerializer(ContractDetailsTokenSerializer):
    class Meta(ContractDetailsTokenSerializer.Meta):
        model = ContractDetailsBinanceToken

    def to_representation(self, contract_details):
        res = super().to_representation(contract_details)
        token_holder_serializer = TokenHolderSerializer()
        res['token_holders'] = [token_holder_serializer.to_representation(th) for th in
                                contract_details.contract.tokenholder_set.order_by('id').all()]
        res['eth_contract_token'] = EthContractSerializer().to_representation(contract_details.eth_contract_token)
        if contract_details.eth_contract_token and contract_details.eth_contract_token.binance_ico_details_token.filter(
                contract__state='ACTIVE'):
            res['crowdsale'] = contract_details.eth_contract_token.binance_ico_details_token.filter(
                contract__state__in=('ACTIVE', 'ENDED')).order_by('id')[0].contract.id
        if contract_details.contract.network.name in ['BINANCE_SMART_TESTNET']:
            res['eth_contract_token']['source_code'] = ''
        return res


class ContractDetailsMaticAirdropSerializer(ContractDetailsAirdropSerializer):
    class Meta(ContractDetailsAirdropSerializer.Meta):
        model = ContractDetailsMaticAirdrop


class ContractDetailsMaticICOSerializer(ContractDetailsICOSerializer):
    class Meta(ContractDetailsICOSerializer.Meta):
        model = ContractDetailsMaticICO

    def to_representation(self, contract_details):
        res = super().to_representation(contract_details)
        if contract_details.contract.network.name in ['MATIC_TESTNET']:
            res['eth_contract_token']['source_code'] = ''
            res['eth_contract_crowdsale']['source_code'] = ''
        return res


class ContractDetailsMaticTokenSerializer(ContractDetailsTokenSerializer):
    class Meta(ContractDetailsTokenSerializer.Meta):
        model = ContractDetailsMaticToken

    def to_representation(self, contract_details):
        res = super().to_representation(contract_details)
        token_holder_serializer = TokenHolderSerializer()
        res['token_holders'] = [token_holder_serializer.to_representation(th) for th in
                                contract_details.contract.tokenholder_set.order_by('id').all()]
        res['eth_contract_token'] = EthContractSerializer().to_representation(contract_details.eth_contract_token)
        if contract_details.eth_contract_token and contract_details.eth_contract_token.matic_ico_details_token.filter(
                contract__state='ACTIVE'):
            res['crowdsale'] = contract_details.eth_contract_token.matic_ico_details_token.filter(
                contract__state__in=('ACTIVE', 'ENDED')).order_by('id')[0].contract.id
        if contract_details.contract.network.name in ['MATIC_TESTNET']:
            res['eth_contract_token']['source_code'] = ''
        return res
