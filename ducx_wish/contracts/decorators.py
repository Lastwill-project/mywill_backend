import sys, traceback
import time

from django.db.models import Q
from django.core.mail import send_mail

from ducx_wish.deploy.models import DeployAddress
from ducx_wish.settings import DEFAULT_FROM_EMAIL, EMAIL_FOR_POSTPONED_MESSAGE
from ducx_wish.settings import NETWORKS
from email_messages import *


# contract_details_types = []


def contract_details(name):
    def w(c):
        return c
    return w


class NeedRequeue(Exception):
    pass


class TxFail(Exception):
    pass


class AlreadyPostponed(Exception):
    pass


def check_transaction(f):
    def wrapper(*args, **kwargs):
        if not args[1].get('success', True):
            print('message rejected because transaction failed', flush=True)
            raise TxFail()
        else:
            return f(*args, **kwargs)
    return wrapper


def postponable(f):
    def wrapper(*args, **kwargs):
        contract = args[0].contract
        if contract.state == 'POSTPONED':
            print('message rejected because contract postponed', flush=True)
            send_mail(
                postponed_subject,
                postponed_message.format(
                    contract_id=contract.id
                ),
                DEFAULT_FROM_EMAIL,
                [EMAIL_FOR_POSTPONED_MESSAGE]
            )
            take_off_blocking(contract.network.name, contract_id=contract.id)
            raise AlreadyPostponed
        try:
            return f(*args, **kwargs)
        except Exception as e:
            contract.state = 'POSTPONED'
            contract.save()
            send_mail(
                postponed_subject,
                postponed_message.format(
                    contract_id=contract.id
                ),
                DEFAULT_FROM_EMAIL,
                [EMAIL_FOR_POSTPONED_MESSAGE]
            )
            print('contract postponed due to exception', flush=True)
            address = NETWORKS[contract.network.name]['address']
            take_off_blocking(
                contract.network.name, contract_id=contract.id, address=address
            )
            print('queue unlocked due to exception', flush=True)
            raise
    return wrapper


def blocking(f):
    def wrapper(*args, **kwargs):
        network_name = args[0].contract.network.name
        address = NETWORKS[args[0].contract.network.name]['address']
        if not DeployAddress.objects.select_for_update().filter(
                Q(network__name=network_name) & Q(address=address) & (Q(locked_by__isnull=True) | Q(locked_by=args[0].contract.id))
        ).update(locked_by=args[0].contract.id):
            print('address locked. sleeping 5 and requeueing the message', flush=True)
            time.sleep(5)
            raise NeedRequeue()
        return f(*args, **kwargs)
    return wrapper


def take_off_blocking(network, contract_id=None, address=None):
    if not address:
        address = NETWORKS[network]['address']
    if not contract_id:
        DeployAddress.objects.select_for_update().filter(
            network__name=network, address=address
        ).update(locked_by=None)
    else:
        DeployAddress.objects.select_for_update().filter(
            network__name=network, address=address, locked_by=contract_id
        ).update(locked_by=None)


class memoize_timeout:
    def __init__(self, timeout):
        self.timeout = timeout
        self.cache = {}

    def __call__(self, f):
        def func(*args, **kwargs):
            key = (args, tuple(sorted(kwargs.items())))
            v = self.cache.get(key, (0,0))
            print('cache')
            if time.time() - v[1] > self.timeout:
                print('updating')
                v = self.cache[key] = f(*args, **kwargs), time.time()
            return v[0]
        return func
