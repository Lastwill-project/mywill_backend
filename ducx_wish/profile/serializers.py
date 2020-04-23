import requests
import os
import hashlib
import binascii

from bip32utils import BIP32Key
from eth_keys import keys

from rest_framework.exceptions import PermissionDenied
from rest_framework import serializers
from rest_auth.registration.serializers import RegisterSerializer
from rest_auth.serializers import (
    LoginSerializer, PasswordChangeSerializer, PasswordResetConfirmSerializer, PasswordResetSerializer
)

from ducx_wish.profile.models import Profile, UserSiteBalance, SubSite
from ducx_wish.settings import ROOT_PUBLIC_KEY_DUCATUS, BITCOIN_URLS, DUCATUSX_URL, ROOT_PUBLIC_KEY_DUCATUX, \
    ROOT_PUBLIC_KEY_ETH
from ducx_wish.profile.helpers import valid_totp
from ducx_wish.profile.forms import SubSitePasswordResetForm
from ducx_wish.bip32_ducatus import DucatusWallet


def generate_memo(m):
    memo_str = os.urandom(8)
    m.update(memo_str)
    memo_str = binascii.hexlify(memo_str + m.digest()[0:2])
    return memo_str


def registration_btc_address(btc_address):
    requests.post(
        BITCOIN_URLS['main'],
        json={
            'method': 'importaddress',
            'params': [btc_address, btc_address, False],
            'id': 1, 'jsonrpc': '1.0'
        }
    )


def create_wish_balance(user, duc_address, eth_address, ducx_address, memo_str):
    ducxwish = SubSite.objects.get(site_name=DUCATUSX_URL)
    UserSiteBalance(
        user=user, subsite=ducxwish,
        duc_address=duc_address,
        eth_address=eth_address,
        ducx_address=ducx_address,
        memo=memo_str
    ).save()


def init_profile(user, is_social=False, metamask_address=None, lang='en', swaps=False):
    m = hashlib.sha256()
    memo_str = generate_memo(m)

    eth_key = BIP32Key.fromExtendedKey(ROOT_PUBLIC_KEY_ETH, public=True)
    ducx_key = BIP32Key.fromExtendedKey(ROOT_PUBLIC_KEY_DUCATUX, public=True)
    duc_root_key = DucatusWallet.deserialize(ROOT_PUBLIC_KEY_DUCATUS)

    eth_address = keys.PublicKey(eth_key.ChildKey(user.id).K.to_string()).to_checksum_address().lower()
    ducx_address = keys.PublicKey(ducx_key.ChildKey(user.id).K.to_string()).to_checksum_address().lower()
    duc_address = duc_root_key.get_child(user.id, is_prime=False).to_address()

    Profile(user=user, is_social=is_social, metamask_address=metamask_address, lang=lang, is_swaps=swaps).save()
    create_wish_balance(user, duc_address, eth_address, ducx_address, memo_str)
    # registration_btc_address()


class UserRegisterSerializer(RegisterSerializer):
    def save(self, request):
        user = super().save(request)
        init_profile(user, lang=request.COOKIES.get('lang', 'en'))
        return user


class UserLoginSerializer2FA(LoginSerializer):
    totp = serializers.CharField(required=False, allow_blank=True)

    def validate(self, attrs):
        res = super().validate(attrs)
        if attrs['user']:
            user = attrs['user']
            if user.profile.use_totp:
                totp = attrs.get('totp', None)
                if not totp:
                    raise PermissionDenied(1019)
                if not valid_totp(user, totp):
                    raise PermissionDenied(1020)
        return res


class PasswordChangeSerializer2FA(PasswordChangeSerializer):
    totp = serializers.CharField(required=False, allow_blank=True)

    def validate(self, attrs):
        res = super().validate(attrs)
        if self.user.profile.use_totp:
            totp = attrs.get('totp', None)
            if totp is None or not valid_totp(self.user, totp):
                raise PermissionDenied()
        return res


class PasswordResetConfirmSerializer2FA(PasswordResetConfirmSerializer):
    totp = serializers.CharField(required=False, allow_blank=True)

    def custom_validation(self, attrs):
        if self.user.profile.use_totp:
            totp = attrs.get('totp', None)
            if not totp:
                raise PermissionDenied(1021)
            if not valid_totp(self.user, totp):
                raise PermissionDenied(1022)


class SubSitePasswordResetSerializer(PasswordResetSerializer):
    email = serializers.EmailField()
    password_reset_form_class = SubSitePasswordResetForm

    def save(self):
        request = self.context.get('request')
        # Set some values to trigger the send_email method.
        opts = {
            'use_https': request.is_secure(),
            'request': request,
        }
        opts.update(self.get_email_options())
        self.reset_form.save(**opts)
