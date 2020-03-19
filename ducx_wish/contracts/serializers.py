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

import ducx_wish.check as check
from ducx_wish.parint import EthereumProvider
from ducx_wish.contracts.models import (
    Contract, Heir, DUCXContract, TokenHolder, WhitelistAddress,
    ContractDetailsToken, ContractDetailsICO,
    ContractDetailsAirdrop, AirdropAddress,
    ContractDetailsLastwill,
    ContractDetailsDelayedPayment, ContractDetailsInvestmentPool,
    InvestAddress
)
from ducx_wish.contracts.models import send_in_queue
from ducx_wish.contracts.decorators import *
from ducx_wish.consts import NET_DECIMALS
from ducx_wish.profile.models import *
from ducx_wish.payments.api import create_payment
from exchange_API import convert, bnb_to_wish
from ducx_wish.consts import MAIL_NETWORK
import email_messages


def count_sold_tokens(address):
    contract = DUCXContract.objects.get(address=address).contract
    eth_int = EthereumProvider().get_provider(contract.network.name)

    method_sign = '0x' + binascii.hexlify(
        int_to_big_endian(m_id('totalSupply', []))).decode()
    sold_tokens = eth_int.eth_call({'to': address,
                                    'data': method_sign,
                                    })
    sold_tokens = '0x0' if sold_tokens == '0x' else sold_tokens
    sold_tokens = int(sold_tokens, 16) / 10 ** contract.get_details().decimals
    return sold_tokens


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
        return contract

    def to_representation(self, contract):
        res = super().to_representation(contract)
        res['contract_details'] = self.get_details_serializer(
            contract.contract_type
        )(context=self.context).to_representation(contract.get_details())
        if contract.state != 'CREATED':
            duc_cost = res['cost']
            if 'TESTNET' in contract.network.name or 'ROPSTEN' in contract.network.name:
                duc_cost = 0
        else:
            duc_cost = Contract.get_details_model(
                contract.contract_type
            ).calc_cost(res['contract_details'], contract.network)
        duc_cost = int(duc_cost)
        res['cost'] = {
            'DUC': str(duc_cost),
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
            2: ContractDetailsDelayedPaymentSerializer,
            4: ContractDetailsICOSerializer,
            5: ContractDetailsTokenSerializer,
            8: ContractDetailsAirdropSerializer,
            9: ContractDetailsInvestmentPoolSerializer,
        }[contract_type]


class DUCXContractSerializer(serializers.ModelSerializer):
    class Meta:
        model = DUCXContract
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
        res['ducx_contract'] = DUCXContractSerializer().to_representation(contract_details.ducx_contract)

        if contract_details.contract.network.name in ['RSK_MAINNET', 'RSK_TESTNET']:
            btc_key = contract_details.btc_key
            if btc_key:
                res['btc_address'] = contract_details.btc_key.btc_address
        if contract_details.contract.network.name in ['DUCATUSX_TESTNET', 'RSK_TESTNET']:
            res['ducx_contract']['source_code'] = ''
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
        res['ducx_contract'] = DUCXContractSerializer().to_representation(contract_details.ducx_contract)
        if contract_details.contract.network.name in ['DUCATUSX_TESTNET', 'RSK_TESTNET']:
            res['ducx_contract']['source_code'] = ''
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
            'whitelist'
        )

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
            res.ducx_contract_token_id = token_id
            res.save()
        return res

    def validate(self, details):
        now = timezone.now().timestamp() + 600
        if 'ducx_contract_token' in details and 'id' in details['ducx_contract_token'] and details['ducx_contract_token'][
            'id']:
            token_model = DUCXContract.objects.get(id=details['ducx_contract_token']['id'])
            token_details = token_model.contract.get_details()
            details.pop('ducx_contract_token')
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
        res['ducx_contract_token'] = DUCXContractSerializer().to_representation(contract_details.ducx_contract_token)
        res['ducx_contract_crowdsale'] = DUCXContractSerializer().to_representation(
            contract_details.ducx_contract_crowdsale)
        res['rate'] = int(res['rate'])
        if contract_details.contract.network.name in ['DUCATUSX_TESTNET', 'RSK_TESTNET']:
            res['ducx_contract_token']['source_code'] = ''
            res['ducx_contract_crowdsale']['source_code'] = ''
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
        kwargs.pop('ducx_contract_token', None)
        kwargs.pop('ducx_contract_crowdsale', None)

        if token_id:
            details.ducx_contract_token_id = token_id
        return super().update(details, kwargs)


class ContractDetailsTokenSerializer(serializers.ModelSerializer):
    class Meta:
        model = ContractDetailsToken
        fields = (
            'token_name', 'token_short_name', 'decimals',
            'admin_address', 'token_type', 'future_minting',
            'authio', 'authio_email', 'authio_date_payment',
            'authio_date_getting'
        )
        extra_kwargs = {
            'authio_date_payment': {'read_only': True},
            'authio_date_getting': {'read_only': True},
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
        res['ducx_contract_token'] = DUCXContractSerializer().to_representation(contract_details.ducx_contract_token)
        if contract_details.ducx_contract_token and contract_details.ducx_contract_token.ico_details_token.filter(
                contract__state='ACTIVE'):
            res['crowdsale'] = contract_details.ducx_contract_token.ico_details_token.filter(
                contract__state__in=('ACTIVE', 'ENDED')).order_by('id')[0].contract.id
        if contract_details.contract.network.name in ['DUCATUSX_TESTNET', 'RSK_TESTNET']:
            res['ducx_contract_token']['source_code'] = ''
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
        kwargs.pop('ducx_contract_token', None)
        return super().update(details, kwargs)


class ContractDetailsAirdropSerializer(serializers.ModelSerializer):
    class Meta:
        model = ContractDetailsAirdrop
        fields = ('admin_address', 'token_address')

    def to_representation(self, contract_details):
        res = super().to_representation(contract_details)
        res['ducx_contract'] = DUCXContractSerializer().to_representation(contract_details.ducx_contract)
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
        res['ducx_contract'] = DUCXContractSerializer().to_representation(contract_details.ducx_contract)
        if contract_details.contract.network.name in ['DUCATUSX_TESTNET', 'RSK_TESTNET']:
            res['ducx_contract']['source_code'] = ''
        if contract_details.contract.state not in ('ACTIVE', 'CANCELLED', 'DONE', 'ENDED'):
            res.pop('link', '')
        res['last_balance'] = count_last_balance(contract_details.contract)
        return res

    def update(self, contract, details, contract_details):
        kwargs = contract_details.copy()
        kwargs['contract'] = contract
        return super().update(details, kwargs)


