import queue
import pika
import os
import traceback
import threading
import json
import sys
from types import FunctionType
import datetime
import fcntl

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'ducx_wish.settings')
import django
django.setup()
from django.utils import timezone
from django.core.exceptions import ObjectDoesNotExist
from django.db.models import Q
from django.db.models.signals import post_save

from ducx_wish.contracts.models import (
    Contract, DUCXContract, TxFail, NeedRequeue, AlreadyPostponed,
    WhitelistAddress, ContractDetailsSWAPS2
)
from ducx_wish.swaps_common.orderbook.models import OrderBookSwaps
from ducx_wish.contracts.serializers import ContractSerializer
from ducx_wish.contracts.api import autodeploing
from ducx_wish.settings import NETWORKS
from ducx_wish.deploy.models import DeployAddress
from ducx_wish.payments.api import create_payment
from ducx_wish.profile.models import Profile
from exchange_API import to_wish


class Receiver(threading.Thread):

    def __init__(self, network):
        super().__init__()
        self.network = network

    def run(self):
        connection = pika.BlockingConnection(pika.ConnectionParameters(
            'localhost',
            5672,
            'mywill',
            pika.PlainCredentials('java', 'java'),
            heartbeat_interval=0,
        ))

        channel = connection.channel()

        channel.queue_declare(
                queue=NETWORKS[self.network]['queue'],
                durable=True,
                auto_delete=False,
                exclusive=False
        )
        channel.basic_consume(
                self.callback,
                queue=NETWORKS[self.network]['queue']
        )

        print('receiver start ', self.network, flush=True)
        channel.start_consuming()

    def payment(self, message):
        print('payment message', flush=True)
        print('message["amount"]', message['amount'])
        print('payment ok', flush=True)
        create_payment(message['userId'], message['transactionHash'], message['currency'], message['amount'], message['siteId'])
        if message['siteId'] in [4, 5]:
            autodeploing(message['userId'], message['siteId'])


    def deployed(self, message):
        print('deployed message received', flush=True)
        contract = DUCXContract.objects.get(id=message['contractId']).contract
        if contract.state == 'ACTIVE':
            print('ignored because already active', flush=True)
            return
        contract.get_details().msg_deployed(message)
        print('deployed ok!', flush=True)

    def orderCreated(self, message):
        print('deployed message received', flush=True)
        # commenting because of upgrade to orderboook
        #
        #details = ContractDetailsSWAPS2.objects.get(memo_contract=message['id'])
        #if details.contract.state == 'ACTIVE':
        #    print('ignored because already active', flush=True)
        #    return
        #details.msg_deployed(message)
        order = OrderBookSwaps.objects.get(memo_contract=message['id'])
        if order.contract_state == 'ACTIVE':
            print('ignored because already active', flush=True)
            return
        order.msg_deployed(message)
        print('deployed ok!', flush=True)


    def killed(self, message):
        print('killed message', flush=True)
        contract = DUCXContract.objects.get(id=message['contractId']).contract
        contract.state = 'KILLED'
        contract.save()
        network = contract.network
        DeployAddress.objects.filter(network=network, locked_by=contract.id).update(locked_by=None)
        print('killed ok', flush=True)

    def checked(self, message):
        print('checked message', flush=True)
        contract = DUCXContract.objects.get(id=message['contractId']).contract
        contract.get_details().checked(message)
        print('checked ok', flush=True)

    def repeat_check(self, message):
        print('repeat check message', flush=True)
        contract = DUCXContract.objects.get(id=message['contractId']).contract
        contract.get_details().check_contract()
        print('repeat check ok', flush=True)

    def check_contract(self, message):
        print('ignored',flush=True)
        print('check contract message', flush=True)
        contract = Contract.objects.get(id=message['contractId'])
        contract.get_details().check_contract()
        print('check contract ok', flush=True)

    def triggered(self, message):
        print('triggered message', flush=True)
        contract = DUCXContract.objects.get(id=message['contractId']).contract
        contract.get_details().triggered(message)
        print('triggered ok', flush=True)

    def SelfdestructionEvent(self, message):
        print('contract destruct message', flush=True)
        contract = DUCXContract.objects.get(id=message['contractId']).contract
        contract.get_details().SelfdestructionEvent(message)
        print('destructed ok', flush=True)

    def launch(self, message):
        print('launch message', flush=True)
        try:
            contract_details = Contract.objects.get(id=message['contractId']).get_details()
            contract_details.deploy()
        except ObjectDoesNotExist:
            # only when contract removed manually
            print('no contract, ignoging')
            return
        try:
            contract_details.refresh_from_db()
        except:
            import time
            time.sleep(0.5)
        print('launch ok', flush=True)

    def ownershipTransferred(self, message):
        print('ownershipTransferred message')
        contract = DUCXContract.objects.get(id=message['crowdsaleId']).contract
        contract.get_details().ownershipTransferred(message)
        print('ownershipTransferred ok')

    def initialized(self, message):
        print('initialized message')
        contract = DUCXContract.objects.get(id=message['contractId']).contract
        contract.get_details().initialized(message)
        print('initialized ok')

    def finish(self, message):
        print('finish message')
        if 'id' in message:
            # contract = ContractDetailsSWAPS2.objects.get(memo_contract=message['id'])
            # contract.finalized(message)
            order = OrderBookSwaps.objects.get(memo_contract=message['id'])
            order.finalized(message)
        else:
            contract = DUCXContract.objects.get(id=message['contractId']).contract
            contract.get_details().finalized(message)
        print('finish ok')

    def finalized(self, message):
        print('finalized message')
        if 'id' in message:
            # contract = ContractDetailsSWAPS2.objects.get(
            #     memo_contract=message['id'])
            # contract.finalized(message)
            order = OrderBookSwaps.objects.get(
                 memo_contract=message['id'])
            order.finalized(message)
        else:
            contract = DUCXContract.objects.get(
                id=message['contractId']).contract
            contract.get_details().finalized(message)
        print('finalized ok')

    def transactionCompleted(self, message):
        print('transactionCompleted')
        if message['transactionStatus']:
            print('success, ignoring')
            return
        try:
            contract = DUCXContract.objects.get(tx_hash=message['transactionHash']).contract
            contract.get_details().tx_failed(message)
        except Exception as e:
            print(e)
            print('not found, returning')
            return
        print('transactionCompleted ok')

    def cancel(self, message):
        print('cancel message')
        contract = Contract.objects.get(id=message['contractId'])
        contract.get_details().cancel(message)
        print('cancel ok')

    def confirm_alive(self, message):
        print('confirm_alive message')
        contract = Contract.objects.get(id=message['contractId'])
        contract.get_details().i_am_alive(message)
        print('confirm_alive ok')

    def contractPayment(self, message):
        print('contract Payment message')
        contract = Contract.objects.get(id=message['contractId'])
        contract.get_details().contractPayment(message)
        print('contract Payment ok')

    def notified(self, message):
        print('notified message')
        contract = DUCXContract.objects.get(id=message['contractId']).contract
        details = contract.get_details()
        details.last_reset = timezone.now()
        details.save()
        print('notified ok')

    def fundsAdded(self, message):
        print('funds Added message')
        contract = DUCXContract.objects.get(id=message['contractId']).contract
        contract.get_details().fundsAdded(message)
        print('funds Added ok')

    def make_payment(self, message):
        print('make payment message')
        contract = Contract.objects.get(id=message['contractId'])
        contract.get_details().make_payment(message)
        print('make payment ok')

    def timesChanged(self, message):
        print('time changed message')
        contract = DUCXContract.objects.get(id=message['contractId']).contract
        contract.get_details().timesChanged(message)
        print('time changed ok')

    def airdrop(self, message):
        print(datetime.datetime.now(), flush=True)
        contract = DUCXContract.objects.get(id=message['contractId']).contract
        contract.get_details().airdrop(message)
        print(datetime.datetime.now(), flush=True)

    def callback(self, ch, method, properties, body):
        print('received', body, properties, method, flush=True)
        try:
            message = json.loads(body.decode())
            if message.get('status', '') == 'COMMITTED' or properties.type in ('airdrop', 'finalized'):
                write_flags = fcntl.fcntl(sys.stdout, fcntl.F_GETFL)
                write_blocking = write_flags & os.O_NONBLOCK
                if write_blocking != 0:
                    print('Blocking write mode detected. Resetting blocking flag, previous was:',
                          write_blocking, flush=True
                          )
                    fcntl.fcntl(1, fcntl.F_SETFL, 0)
                getattr(self, properties.type, self.unknown_handler)(message)
        except (TxFail, AlreadyPostponed):
            ch.basic_ack(delivery_tag=method.delivery_tag)
        except NeedRequeue:
            print('requeueing message', flush=True)
            ch.basic_nack(delivery_tag=method.delivery_tag, requeue=True)
        except Exception as e:
            print('\n'.join(traceback.format_exception(*sys.exc_info())),
                  flush=True)
        else:
            ch.basic_ack(delivery_tag=method.delivery_tag)

    def unknown_handler(self, message):
        print('unknown message', message, flush=True)

    def whitelistAdded(self, message):
        contract = DUCXContract.objects.get(id=message['contractId']).contract
        address = message['address']
        w, _ = WhitelistAddress.objects.get_or_create(contract=contract, address=address)
        w.active = True
        w.save()

    def whitelistRemoved(self, message):
        contract = DUCXContract.objects.get(id=message['contractId']).contract
        address = message['address']
        try:
            w = WhitelistAddress.objects.get(contract=contract, address=address)
            w.active = False
            w.save()
        except:
            pass

    def tokensAdded(self, mesage):
        pass

    def tokensSent(self, message):
        contract = DUCXContract.objects.get(id=message['contractId']).contract
        contract.get_details().tokenSent(message)

    def investmentPoolSetup(self, message):
        contract = DUCXContract.objects.get(id=message['contractId']).contract
        details = contract.get_details()
        if message['investmentAddress']:
            details.investment_address = message['investmentAddress']
        if message['tokenAddress']:
            details.token_address = message['tokenAddress']
        details.save()

    def cancelled(self, message):
        if 'id' in message:
            # contract = ContractDetailsSWAPS2.objects.get(memo_contract=message['id'])
            # contract.cancelled(message)
            order = OrderBookSwaps.objects.get(memo_contract=message['id'])
            order.cancelled(message)
        else:
            contract = DUCXContract.objects.get(id=message['contractId']).contract
            details = contract.get_details()
            details.cancelled(message)

    def refund(self, message):
        contract = DUCXContract.objects.get(id=message['contractId']).contract
        details = contract.get_details()
        details.cancelled(message)

    def created(self, message):
        contract = DUCXContract.objects.get(id=message['contractId']).contract
        details = contract.get_details()
        details.created(message)

    def newAccount(self, message):
        contract = DUCXContract.objects.get(id=message['contractId']).contract
        if contract.state == 'ACTIVE':
            print('ignored because already active', flush=True)
            return
        details = contract.get_details()
        details.newAccount(message)

    def tokenCreated(self, message):
        contract = DUCXContract.objects.get(id=message['contractId']).contract
        details = contract.get_details()
        details.tokenCreated(message)

    def setcode(self, message):
        contract = DUCXContract.objects.get(id=message['contractId']).contract
        details = contract.get_details()
        details.setcode(message)

    def refundOrder(self, message):
        order = OrderBookSwaps.objects.get(memo_contract=message['id'])
        order.refund_order(message)

    def depositOrder(self, message):
        order = OrderBookSwaps.objects.get(memo_contract=message['id'])
        order.deposit_order(message)

    def refundSwaps(self, message):
        contract = DUCXContract.objects.get(id=message['contractId']).contract
        details = contract.get_details()
        details.refund_swaps(message)

    def depositSwaps(self, message):
        contract = DUCXContract.objects.get(id=message['contractId']).contract
        details = contract.get_details()
        details.deposit_swaps(message)

def methods(cls):
    return [x for x, y in cls.__dict__.items() if type(y) == FunctionType and not x.startswith('_')]


class WSInterface(threading.Thread):
    def __init__(self):
        super().__init__()
        self.interthread_queue = queue.Queue()

    def send(self, user, message, data):
        self.interthread_queue.put({'user': user, 'msg': message, 'data': data})

    def run(self):
        connection = pika.BlockingConnection(pika.ConnectionParameters(
                '127.0.0.1',
                5672,
                'mywill',
                pika.PlainCredentials('java', 'java'),
                heartbeat_interval=0,
        ))
        self.channel = connection.channel()
        self.channel.queue_declare(queue='websockets', durable=True, auto_delete=False, exclusive=False)
        while 1:
            message = self.interthread_queue.get()
            user = message.pop('user')
            self.channel.basic_publish(
                    exchange='',
                    routing_key='websockets',
                    body=json.dumps(message),
                    properties=pika.BasicProperties(expiration='30000', type=str(user)),
            )



"""
rabbitmqctl add_user java java
rabbitmqctl add_vhost mywill
rabbitmqctl set_permissions -p mywill java ".*" ".*" ".*"
"""

def save_profile(sender, instance, **kwargs):
    try:
        ws_interface.send(
                instance.user.id,
                'update_user',
                {'balance': str(instance.balance)},
        )
    except Exception as e:
        print('in save profile callback:', e)


def save_contract(sender, instance, **kwargs):
    try:
        contract_data = ContractSerializer().to_representation(instance)
        ws_interface.send(
                instance.user.id,
                'update_contract',
                contract_data,
        )
    except Exception as e:
        print('in save contract callback:', e)


post_save.connect(save_contract, sender=Contract)
post_save.connect(save_profile, sender=Profile)

nets = NETWORKS.keys()

ws_interface = WSInterface()
ws_interface.start()

for net in nets:
    rec = Receiver(net)
    rec.start()



