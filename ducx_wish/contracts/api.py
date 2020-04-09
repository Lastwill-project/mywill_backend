import datetime
from os.path import join

from django.http import Http404, JsonResponse
from django.views.generic import View
from django.core.mail import send_mail, EmailMessage

from rest_framework import status
from rest_framework import viewsets
from rest_framework.viewsets import ModelViewSet
from rest_framework.permissions import BasePermission, SAFE_METHODS
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.decorators import api_view
from rest_framework.exceptions import PermissionDenied
from collections import OrderedDict

from ducx_wish.settings import BASE_DIR, ETHERSCAN_API_KEY, COINMARKETCAP_API_KEYS, NETWORKS
from ducx_wish.settings import DUCATUSX_URL, EMAIL_HOST_USER, DUCATUSX_CONFIRM_EMAIL, DEFAULT_FROM_EMAIL
from ducx_wish.permissions import IsOwner, IsStaff
from ducx_wish.profile.models import Profile
from ducx_wish.contracts.models import Contract, WhitelistAddress, AirdropAddress, DUCXContract, send_in_queue,\
    ContractDetailsInvestmentPool, InvestAddress,  CurrencyStatisticsCache
from ducx_wish.deploy.models import Network
from ducx_wish.payments.api import create_payment
from exchange_API import to_wish, convert
from email_messages import authio_message, authio_subject, authio_google_subject, authio_google_message, \
    ducatus_admin_confirm_subject, ducatus_admin_confirm_text
from .serializers import ContractSerializer, count_sold_tokens, WhitelistAddressSerializer, AirdropAddressSerializer
from ducx_wish.consts import *
import requests
from django.db.models import Q

BROWSER_HEADERS = {'User-Agent': 'Mozilla/5.0 (X11; Linux x86_64; rv:69.0) Geko/20100101 Firefox/69.0'}


class ContractViewSet(ModelViewSet):
    queryset = Contract.objects.all()
    serializer_class = ContractSerializer
    permission_classes = (IsAuthenticated, IsStaff | IsOwner)

    def destroy(self, request, *args, **kwargs):
        instance = self.get_object()
        if instance.state in ('CREATED', 'WAITING_FOR_PAYMENT', 'WAITING_FOR_ACTIVATION'):
            try:
                self.perform_destroy(instance)
            except Http404:
                pass
            return Response(status=status.HTTP_204_NO_CONTENT)
        raise PermissionDenied()

    def get_queryset(self):
        result = self.queryset.order_by('-created_date')
        host = self.request.META['HTTP_HOST']
        print('host is', host, flush=True)
        if host == DUCATUSX_URL:
            result = result.exclude(contract_type__in=[20, 21, 22, 23])
            # result = result.exclude(contract_type__in=[20, 21, 22])
        if self.request.user.is_staff:
            return result
        return result.filter(user=self.request.user)


@api_view()
def get_code(request):
    with open(path.join(CONTRACTS_DIR, Contract.get_details_model(
            int(request.query_params['contract_type'])
    ).sol_path)) as f:
        return Response({'result': f.read()})


@api_view()
def test_comp(request):
    contract = Contract.objects.get(id=request.query_params['id'])
    contract.get_details().compile()
    contract.save()
    return Response({'result': 'ok'})


@api_view()
def get_token_contracts(request):
    if request.user.is_anonymous:
        return Response([])
    res = []
    ducx_contracts = DUCXContract.objects.filter(
             contract__contract_type__in=(4, 5),
             contract__user=request.user,
             address__isnull=False,
             contract__network=request.query_params['network'],
    )
    for ec in ducx_contracts:
        details = ec.contract.get_details()
        if details.ducx_contract_token == ec:
            if any([x.contract.contract_type == 4 and x.contract.state not in ('CREATED', 'ENDED') for x in ec.ico_details_token.all()]):
                state = 'running'
            elif any([x.contract.contract_type == 4 and not x.continue_minting and x.contract.state =='ENDED' for x in ec.ico_details_token.all()]):
                state = 'closed'
            elif any([x.contract.contract_type == 5 and x.contract.state == 'ENDED' for x in ec.token_details_token.all()]):
                state = 'closed'
            else:
                state = 'ok'
            res.append({
                    'id': ec.id,
                    'address': ec.address,
                    'token_name': details.token_name,
                    'token_short_name': details.token_short_name,
                    'decimals': details.decimals,
                    'state': state
            })
    return Response(res)


@api_view(http_method_names=['POST'])
def deploy(request):
    contract = Contract.objects.get(id=request.data.get('id'))
    contract_details = contract.get_details()
    contract_details.predeploy_validate()

    if contract.user != request.user or contract.state not in ('CREATED', 'WAITING_FOR_PAYMENT'):
        raise PermissionDenied

    if contract.network.name == 'DUCATUSX_MAINNET':
        if not contract.user.profile.is_ducx_admin:
            send_to_ducatus_admin(contract, request)
            return Response('ok')

    cost = contract.cost
    currency = 'DUC'
    site_id = 1
    network = contract.network.name
    create_payment(request.user.id, '', currency, -cost, site_id, network)
    contract.state = 'WAITING_FOR_DEPLOYMENT'
    contract.save()
    queue = NETWORKS[contract.network.name]['queue']
    send_in_queue(contract.id, 'launch', queue)
    print('send to deploy queue', flush=True)
    return Response('ok')


def send_to_ducatus_admin(contract, request):
    details = contract.get_details()

    # mint_info = ''
    # token_holders = contract.tokenholder_set.all()
    # for th in token_holders:
    #     mint_info = mint_info + '\n' + th.address + '\n'
    #     mint_info = mint_info + str(th.amount) + '\n'
    #     if th.freeze_date:
    #         mint_info = mint_info + str(
    #             datetime.datetime.utcfromtimestamp(th.freeze_date).strftime('%Y-%m-%d %H:%M:%S')) + '\n'

    http_schema = request.scheme + '://'
    host = request.META['HTTP_HOST']
    contract_url = join(http_schema, host, 'contracts', str(contract.id))
    print('contract url', contract_url, flush=True)

    EmailMessage(
        subject=ducatus_admin_confirm_subject,
        body=ducatus_admin_confirm_text.format(
            # address=details.ducx_contract_token.address,
            email=contract.feedback_email,
            token_name=details.token_name,
            token_short_name=details.token_short_name,
            token_type=details.token_type,
            decimals=details.decimals,
            # mint_info=mint_info if mint_info else 'No',
            admin_address=details.admin_address,
            confirm_url=contract_url
        ),
        from_email=EMAIL_HOST_USER,
        to=[DUCATUSX_CONFIRM_EMAIL]
    ).send()


@api_view(http_method_names=['POST'])
def cancel_ducatusx_contract(request):
    contract = Contract.objects.get(id=request.date.get('id'))

    if not request.user.profile.is_ducx_admin:
        raise PermissionDenied

    contract.state = 'CANCELLED'
    contract.save()

    return Response('ok')


@api_view(http_method_names=['POST'])
def i_am_alive(request):
    contract = Contract.objects.get(id=request.data.get('id'))
    if contract.user != request.user or contract.state != 'ACTIVE' or contract.contract_type not in (0, 1, 18):
        raise PermissionDenied
    details = contract.get_details()
    if details.last_press_imalive:
        delta = timezone.now() - details.last_press_imalive
        if delta.days < 1:
            raise PermissionDenied(3000)
    queue = NETWORKS[contract.network.name]['queue']
    send_in_queue(contract.id, 'confirm_alive', queue)
    details.last_press_imalive = timezone.now()
    details.save()
    return Response('ok')


@api_view(http_method_names=['POST'])
def cancel(request):
    contract = Contract.objects.get(id=request.data.get('id'))
    if contract.user != request.user or contract.state not in ('ACTIVE', 'EXPIRED') or contract.contract_type not in (0, 1, 18):
        raise PermissionDenied()
    queue = NETWORKS[contract.network.name]['queue']
    send_in_queue(contract.id, 'cancel', queue)
    return Response('ok')


class ICOtokensView(View):

    def get(self, request, *args, **kwargs):

        address = request.GET.get('address', None)
        if not DUCXContract.objects.filter(address=address):
            raise PermissionDenied
        sold_tokens = count_sold_tokens(address)
        return Response({'sold tokens': sold_tokens})


def get_users(names):
    users = []
    for name in names:
        first_name, last_name = name.split()
        user = User.objects.filter(
            last_name=last_name,
            first_name=first_name
        ).first()
        if user:
            users.append(user)
    return users


def get_coinmarketcap_statistics(id_list, convert_currency='USD'):
    parameters = {
        'id': id_list,
        'convert': convert_currency
    }
    headers = {
        'Accepts': 'application/json',
        'X-CMC_PRO_API_KEY': COINMARKETCAP_API_KEYS[2],
    }

    session = requests.Session()
    session.headers.update(headers)

    try:
        response = session.get(URL_STATS_CURRENCY['CoinMarketCap'], params=parameters)
        data = response.text
        # print(data)
    except (requests.exceptions.ConnectionError, requests.exceptions.Timeout, requests.exceptions.TooManyRedirects) as e:
        print(e)
        data = {'error': 'Exception in fetching coinmarketcap statistics'}
        return data

    return data


def get_currency_statistics():
    now = timezone.now()
    cached_stats = CurrencyStatisticsCache.objects.first()
    if not cached_stats or cached_stats.updated_at < now - datetime.timedelta(hours=1):
        try:
            stats = get_new_currency_statistics()
            cached_stats = CurrencyStatisticsCache(**stats)
            cached_stats.updated_at = now
            cached_stats.save()
        except Exception as e:
            print('Exception in retrieving coinmarketcap data. Error is:', flush=True)
            print(e, flush=True)
            stats = cached_stats.__dict__
    else:
        stats = cached_stats.__dict__

    if '_state' in stats.keys():
        stats.pop('id')
        stats.pop('_state')

    return stats


def get_new_currency_statistics():
    currencies_request_ids = ','.join(str(curr_id) for curr_id in URL_STATS_CURRENCY_ID.values())
    cmc_info_usd = json.loads(get_coinmarketcap_statistics(currencies_request_ids))
    cmc_info_eth = json.loads(get_coinmarketcap_statistics(currencies_request_ids, 'ETH'))

    info_error_usd = cmc_info_usd['status']['error_message']
    info_error_eth = cmc_info_eth['status']['error_message']

    if info_error_usd is not None:
        raise Exception(info_error_usd)
    if info_error_eth is not None:
        raise Exception(info_error_eth)

    data_usd = cmc_info_usd['data']
    data_eth = cmc_info_eth['data']

    eosish_info = float(requests.get(URL_STATS_CURRENCY['EOSISH']).json()['eosish']['eos'])
    usd_info = get_usd_rub_rates()

    currency_info = {}

    for curr_id, curr_data in data_usd.items():
        currency = curr_data['slug']
        info = curr_data['quote']['USD']

        price = info['price']
        price_change_24h = info['percent_change_24h']
        rank = curr_data['cmc_rank']

        if currency == 'mywish':
            price_field = 'wish_price_usd'
            price_change_field = 'wish_usd_percent_change_24h'
            rank_field = 'mywish_rank'
        elif currency == 'bitcoin':
            price_field = 'btc_price_usd'
            price_change_field = 'btc_percent_change_24h'
            rank_field = 'bitcoin_rank'
        elif currency == 'ethereum':
            price_field = 'eth_price_usd'
            price_change_field = 'eth_percent_change_24h'
            rank_field = 'eth_rank'
        elif currency == 'eos':
            price_field = 'eos_price_usd'
            price_change_field = 'eos_percent_change_24h'
            rank_field = 'eos_rank'
        else:
            raise Exception('cannot translate currency %s to field' % currency)

        currency_info[price_field] = price
        currency_info[price_change_field] = price_change_24h
        currency_info[rank_field] = rank

    wish_eth_info = data_eth[str(URL_STATS_CURRENCY_ID['MYWISH'])]['quote']['ETH']
    currency_info['wish_price_eth'] = wish_eth_info['price']
    wish_eth_change = currency_info['eth_percent_change_24h'] / wish_eth_info['percent_change_24h']
    currency_info['wish_eth_percent_change_24h'] = wish_eth_change
    currency_info['eosish_price_eos'] = eosish_info
    currency_info['eosish_price_usd'] = eosish_info * currency_info['eos_price_usd']
    currency_info['usd_price_rub'] = usd_info['price']
    currency_info['usd_percent_change_24h'] = usd_info['change_24h']

    answer = {}
    for key, value in currency_info.items():
        if 'rank' in key:
            result_value = value
        elif key == 'eosish_price_usd':
            result_value = round(value, 2)
        elif key == 'wish_price_eth':
            result_value = round(float(value), 4)
        else:
            result_value = round(float(value), 2)

        answer[key] = result_value

    return answer


def get_balances_statistics():
    neo_info = json.loads(requests.get(
        URL_STATS_BALANCE['NEO'] +
        '{address}'.format(address=NETWORKS['NEO_TESTNET']['address'])
    ).content.decode())
    neo_balance = 0.0
    gas_balance = 0.0
    for curr in neo_info['balance']:
        if curr['asset'] == 'GAS':
            gas_balance = curr['amount']
        if curr['asset'] == 'NEO':
            neo_balance = curr['amount']
    eth_account_balance = float(json.loads(requests.get(url=
        URL_STATS_BALANCE['ETH'] + '{address}&tag=latest&apikey={api_key}'.format(
            address=ETH_MAINNET_ADDRESS,api_key=ETHERSCAN_API_KEY),
        headers=BROWSER_HEADERS).content.decode())['result']) / NET_DECIMALS['ETH']
    eth_test_account_balance = float(json.loads(requests.get(url=
        URL_STATS_BALANCE['ETH_ROPSTEN'] + '{address}&tag=latest&apikey={api_key}'.format(
            address=ETH_TESTNET_ADDRESS, api_key=ETHERSCAN_API_KEY),
        headers=BROWSER_HEADERS).content.decode())['result']) / NET_DECIMALS['ETH']

    # eth_account_balance = float(json.loads(requests.get(
    #     'https://api.etherscan.io/api?module=account&action=balance'
    #     '&address=0x1e1fEdbeB8CE004a03569A3FF03A1317a6515Cf1'
    #     '&tag=latest'
    #     '&apikey={api_key}'.format(api_key=ETHERSCAN_API_KEY)).content.decode()
    #                                        )['result']) / 10 ** 18
    # eth_test_account_balance = float(json.loads(requests.get(
    #     'https://api-ropsten.etherscan.io/api?module=account&action=balance'
    #     '&address=0x88dbD934eF3349f803E1448579F735BE8CAB410D'
    #     '&tag=latest'
    #     '&apikey={api_key}'.format(api_key=ETHERSCAN_API_KEY)).content.decode()
    #                                             )['result']) / 10 ** 18
    # eos_url = 'https://%s:%s' % (
    #     str(NETWORKS['EOS_TESTNET']['host']),
    #     str(NETWORKS['EOS_TESTNET']['port'])
    # )
    # wallet_name = NETWORKS['EOS_TESTNET']['wallet']
    # password = NETWORKS['EOS_TESTNET']['eos_password']
    # account = NETWORKS['EOS_TESTNET']['address']
    # token = NETWORKS['EOS_TESTNET']['token_address']
    # unlock_eos_account(wallet_name, password)
    # command = [
    #     'cleos', '-u', eos_url, 'get', 'currency', 'balance', 'eosio.token',
    #     account
    # ]
    # print('command', command)
    #
    # for attempt in range(EOS_ATTEMPTS_COUNT):
    #     print('attempt', attempt, flush=True)
    #     proc = Popen(command, stdin=PIPE, stdout=PIPE, stderr=PIPE)
    #     stdout, stderr = proc.communicate()
    #     timer = Timer(CLEOS_TIME_LIMIT, proc.kill)
    #     try:
    #         timer.start()
    #         stdout, stderr = proc.communicate()
    #     finally:
    #         timer.cancel()
    #     # print(stdout, stderr, flush=True)
    #     result = stdout.decode()
    #     if result:
    #         eos_test_account_balance = float(
    #             result.split('\n')[0].split(' ')[0])
    #         break
    #     time.sleep(CLEOS_TIME_COOLDOWN)
    # else:
    #     raise Exception(
    #         'cannot make tx with %i attempts' % EOS_ATTEMPTS_COUNT)
    eos_test_account_balance = 0

    # command = [
    #     'cleos', '-u', eos_url, 'get', 'account', token, '-j'
    # ]
    # time.sleep(CLEOS_TIME_COOLDOWN)
    # builder_params = implement_cleos_command(command)
    # eos_cpu_test_builder = (
    #         builder_params['cpu_limit']['used'] * 100.0 /
    #         builder_params['cpu_limit']['max']
    # )
    # eos_net_test_builder = (
    #         builder_params['net_limit']['used'] * 100.0 /
    #         builder_params['net_limit']['max']
    # )
    # eos_ram_test_builder = (
    #                                builder_params['ram_quota'] - builder_params[
    #                            'ram_usage']
    #                        ) / 1024
    eos_cpu_test_builder = 0
    eos_net_test_builder = 0
    eos_ram_test_builder = 0

    # eos_url = 'https://%s:%s' % (
    #     str(NETWORKS['EOS_MAINNET']['host']),
    #     str(NETWORKS['EOS_MAINNET']['port'])
    # )
    # account = NETWORKS['EOS_MAINNET']['address']
    # token = NETWORKS['EOS_MAINNET']['token_address']
    # command = [
    #     'cleos', '-u', eos_url, 'get', 'account', token, '-j'
    # ]
    # wallet_name = NETWORKS['EOS_MAINNET']['wallet']
    # password = NETWORKS['EOS_MAINNET']['eos_password']
    # unlock_eos_account(wallet_name, password)
    # builder_params = implement_cleos_command(command)
    # eos_cpu_builder = (
    #         builder_params['cpu_limit']['used'] * 100.0 /
    #         builder_params['cpu_limit']['max']
    # )
    # eos_net_builder = (
    #         builder_params['net_limit']['used'] * 100.0 /
    #         builder_params['net_limit']['max']
    # )
    # eos_ram_builder = (
    #                           builder_params['ram_quota'] - builder_params[
    #                       'ram_usage']
    #                   ) / 1024
    eos_cpu_builder = 0
    eos_net_builder = 0
    eos_ram_builder = 0

    # command = [
    #     'cleos', '-u', eos_url, 'get', 'currency', 'balance', 'eosio.token',
    #     account
    # ]
    # print('command', command)
    #
    # for attempt in range(EOS_ATTEMPTS_COUNT):
    #     print('attempt', attempt, flush=True)
    #     proc = Popen(command, stdin=PIPE, stdout=PIPE, stderr=PIPE)
    #     stdout, stderr = proc.communicate()
    #     # print(stdout, stderr, flush=True)
    #     timer = Timer(CLEOS_TIME_LIMIT, proc.kill)
    #     try:
    #         timer.start()
    #         stdout, stderr = proc.communicate()
    #     finally:
    #         timer.cancel()
    #     result = stdout.decode()
    #     if result:
    #         eos_account_balance = float(
    #             result.split('\n')[0].split(' ')[0])
    #         break
    #     time.sleep(CLEOS_TIME_COOLDOWN)
    # else:
    #     raise Exception(
    #         'cannot make tx with %i attempts' % EOS_ATTEMPTS_COUNT)
    eos_account_balance = 0
    return {
    'eth_account_balance': eth_account_balance,
    'eth_test_account_balance': eth_test_account_balance,
    'eos_account_balance':  eos_account_balance,
    'eos_test_account_balance': eos_test_account_balance,
    'eos_cpu_test_builder': eos_cpu_test_builder,
    'eos_net_test_builder': eos_net_test_builder,
    'eos_ram_test_builder': eos_ram_test_builder,
    'eos_cpu_builder': eos_cpu_builder,
    'eos_net_builder': eos_net_builder,
    'eos_ram_builder': eos_ram_builder,
    'neo_test_balance': neo_balance,
    'gas_test_balance': gas_balance
    }


def get_ieo_statistics():
    res = requests.get('https://www.bitforex.com/server/cointrade.act?cmd=getTicker&busitype=coin-btc-swap')
    return res.json()


def get_usd_rub_rates():
    res = requests.get(url=URL_STATS_CURRENCY['RUB'], headers=BROWSER_HEADERS)
    rub_rate = {
        'price': res.json()['ticker']['price'],
        'change_24h': res.json()['ticker']['change']
    }

    return rub_rate


def get_contracts_for_network(net, all_contracts, now, day):
    contracts = all_contracts.filter(network=net)
    new_contracts = contracts.filter(created_date__lte=now,
                                     created_date__gte=day)
    created = contracts.filter(state__in=['CREATED'])
    now_created = created.filter(created_date__lte=now, created_date__gte=day)
    active = contracts.filter(
        state__in=['ACTIVE', 'WAITING', 'WAITING_ACTIVATION']
    )
    now_active = active.filter(created_date__lte=now, created_date__gte=day)
    done = contracts.filter(
        state__in=[
            'DONE', 'CANCELLED', 'ENDED', 'EXPIRED',
            'UNDER_CROWDSALE', 'TRIGGERED', 'KILLED'
        ]
    )
    now_done = done.filter(created_date__lte=now, created_date__gte=day)
    error = contracts.filter(state__in=['POSTPONED'])
    now_error = error.filter(created_date__lte=now, created_date__gte=day)
    in_progress = contracts.filter(state__in=['WAITING_FOR_DEPLOYMENT'])
    now_in_progress = in_progress.filter(
        created_date__lte=now, created_date__gte=day
    )
    answer = {
        'contracts': len(contracts),
        'new_contracts': len(new_contracts),
        'active_contracts': len(active),
        'created_contracts': len(created),
        'done': len(done),
        'error': len(error),
        'now_created': len(now_created),
        'now_active': len(now_active),
        'now_done': len(now_done),
        'now_error': len(now_error),
        'launch': len(in_progress),
        'now_launch': len(now_in_progress)
        }
    contract_details_types = Contract.get_all_details_model()
    for ctype in contract_details_types:
        answer['contract_type_'+str(ctype)] = contracts.filter(
            contract_type=ctype
        ).count()
        answer['contract_type_'+str(ctype)+'_new'] = contracts.filter(
            contract_type=ctype
        ).filter(created_date__lte=now, created_date__gte=day).count()
    return answer


@api_view(http_method_names=['GET'])
# @permission_classes((permissions.IsAdminUser,))
def get_statistics(request):

    now = datetime.datetime.now()
    day = datetime.datetime.combine(
        datetime.datetime.now().today(),
        datetime.time(0, 0)
    )

    users = User.objects.all().exclude(
        email='', password='', last_name='', first_name=''
    ).exclude(email__startswith='testermc')
    anonymous = User.objects.filter(
        email='', password='', last_name='', first_name=''
    )
    new_users = users.filter(date_joined__lte=now, date_joined__gte=day)

    try:
        test_info = json.load(open(
            path.join(BASE_DIR, 'ducx_wish/contracts/test_addresses.json')
        ))
        test_addresses = test_info['addresses']
        persons = test_info['persons']
        fb_test_users = get_users(persons)
    except(FileNotFoundError, IOError):
        test_addresses = []
        fb_test_users = []

    answer = {
        'user_statistics': {'users': len(users), 'new_users': len(new_users)},
        'currency_statistics': get_currency_statistics(),
        'balances_statistics': get_balances_statistics(),
        'ieo': get_ieo_statistics()
    }
    networks = Network.objects.all()
    contracts = Contract.objects.all().exclude(
        user__in=anonymous
    ).exclude(
        user__in=fb_test_users
    ).exclude(
        user__email__in=test_addresses
    ).exclude(
        user__email__startswith='testermc'
    )
    for network in networks:
        answer[network.name] = get_contracts_for_network(
            network, contracts, now, day
        )

    return JsonResponse(answer)


@api_view(http_method_names=['GET'])
def get_statistics_landing(request):
    now = datetime.datetime.now()
    day = datetime.datetime.combine(
        datetime.datetime.now().today(),
        datetime.time(0, 0)
    )
    users = User.objects.all().exclude(
        email='', password='', last_name='', first_name=''
    ).exclude(email__startswith='testermc')
    anonymous = User.objects.filter(
        email='', password='', last_name='', first_name=''
    )
    new_users = users.filter(date_joined__lte=now, date_joined__gte=day)

    try:
        test_info = json.load(open(
            path.join(BASE_DIR, 'ducx_wish/contracts/test_addresses.json')
        ))
        test_addresses = test_info['addresses']
        persons = test_info['persons']
        fb_test_users = get_users(persons)
    except(FileNotFoundError, IOError):
        test_addresses = []
        fb_test_users = []

    contracts = Contract.objects.all().exclude(user__in=anonymous).exclude(
        user__in=fb_test_users
    ).exclude(
        user__email__in=test_addresses
    ).exclude(
        user__email__startswith='testermc'
    )
    new_contracts = contracts.filter(
        created_date__lte=now, created_date__gte=day
    )
    answer = {
        'contracts': len(contracts),
        'new_contracts': len(new_contracts),
        'users': len(users),
        'new_users': len(new_users)
    }
    return JsonResponse(answer)


@api_view(http_method_names=['GET'])
def get_cost_all_contracts(request):
    answer = {}
    contract_details_types = Contract.get_all_details_model()
    for i in contract_details_types:
        answer[i] ={
            'DUC': str(contract_details_types[i]['model'].min_cost() / NET_DECIMALS['DUC']),
        }
    return JsonResponse(answer)


@api_view(http_method_names=['POST'])
def neo_crowdsale_finalize(request):
    contract = Contract.objects.get(id=request.data.get('id'))
    if contract.user != request.user or contract.contract_type != 7 or contract.state != 'ACTIVE':
        raise PermissionDenied
    neo_details = contract.get_details()
    now = datetime.datetime.now().timestamp()
    if neo_details.stop_date <= now:
        contract.state = 'ENDED'
        contract.save()
        return JsonResponse({'result': 2})
    raise ValidationError({'result': 2}, code=403)


class ReadOnly(BasePermission):

    def has_permission(self, request, view):
        return request.method in SAFE_METHODS


class WhitelistAddressViewSet(viewsets.ModelViewSet):
    queryset = WhitelistAddress.objects.all()
    serializer_class = WhitelistAddressSerializer
    permission_classes = (ReadOnly,)

    def get_queryset(self):
        result = self.queryset
        contract_id = self.request.query_params.get('contract', None)
        if not contract_id:
            raise ValidationError()
        contract = Contract.objects.get(id=contract_id)
        if contract.user != self.request.user:
            raise ValidationError({'result': 2}, code=403)
        result = result.filter(contract=contract, active=True)
        return result


class AirdropAddressViewSet(viewsets.ModelViewSet):
    queryset = AirdropAddress.objects.all()
    serializer_class = AirdropAddressSerializer
    permission_classes = (ReadOnly,)

    def get_queryset(self):
        result = self.queryset
        contract_id = self.request.query_params.get('contract', None)
        if not contract_id:
            raise ValidationError()
        contract = Contract.objects.get(id=contract_id)
        if contract.user != self.request.user:
            raise ValidationError({'result': 2}, code=403)
        result = result.filter(contract=contract, active=True)
        state = self.request.query_params.get('state', None)
        if state:
            result = result.filter(state=state)
        result = result.order_by('id')
        return result


def convert_airdrop_address_to_hex(address):
    # short_addresss = address[1:]
    decode_address = base58.b58decode(address)[1:21]
    hex_address = binascii.hexlify(decode_address)
    hex_address = '41' + hex_address.decode("utf-8")
    return hex_address


@api_view(http_method_names=['POST'])
def load_airdrop(request):
    contract = Contract.objects.get(id=request.data.get('id'))
    if contract.user != request.user or contract.contract_type not in [8, 13, 17] or contract.state != 'ACTIVE':
        raise PermissionDenied
    if contract.network.name not in ['EOS_MAINNET', 'EOS_TESTNET']:
        if contract.airdropaddress_set.filter(state__in=('processing', 'sent')).count():
            raise PermissionDenied
        contract.airdropaddress_set.all().delete()
        addresses = request.data.get('addresses')
        if contract.network.name in ['TRON_MAINNET', 'TRON_TESTNET']:
            for x in addresses:
                if x['address'].startswith('0x'):
                    x['address'] = '41' + x['address'][2:]
                else:
                    if not x['address'].startswith('41'):
                        x['address'] = convert_airdrop_address_to_hex(x['address'])
        AirdropAddress.objects.bulk_create([AirdropAddress(
                contract=contract,
                address=x['address'] if contract.network.name in ['TRON_MAINNET', 'TRON_TESTNET'] else x['address'].lower() ,
                amount=x['amount']
        ) for x in addresses])
    else:
        if contract.eosairdropaddress_set.filter(state__in=('processing', 'sent')).count():
            raise PermissionDenied
        contract.eosairdropaddress_set.all().delete()
        addresses = request.data.get('addresses')
        EOSAirdropAddress.objects.bulk_create([EOSAirdropAddress(
                contract=contract,
                address=x['address'].lower(),
                amount=x['amount']
        ) for x in addresses])
    return JsonResponse({'result': 'ok'})


@api_view(http_method_names=['GET'])
def get_contract_for_link(request):
    details = ContractDetailsInvestmentPool.objects.get(
        link=request.query_params['link'],
        contract__state__in=('ACTIVE', 'CANCELLED', 'DONE', 'ENDED')
    )
    contract = details.contract
    return JsonResponse(ContractSerializer().to_representation(contract))


@api_view(http_method_names=['GET'])
def get_invest_balance_day(request):
    contract = Contract.objects.get(id=request.query_params['id'])
    now_date = datetime.datetime.now()
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
    if balance == 0:
        balance = str(balance)
    return JsonResponse({'last_balance': balance})


@api_view(http_method_names=['POST'])
def check_status(request):
    contract = Contract.objects.get(id=request.data.get('id'))
    if contract.user != request.user or contract.state != 'ACTIVE':
        raise PermissionDenied
    if contract.contract_type != 12:
        raise PermissionDenied
    details = contract.get_details()
    now = datetime.datetime.now().timestamp()
    addr = details.crowdsale_address
    host = NETWORKS[contract.network.name]['host']
    port = NETWORKS[contract.network.name]['port']
    if contract.network.name == 'EOS_MAINNET':
        command = ['cleos', '-u', 'https://%s:%s' % (host, port), 'get', 'table',
                   addr, addr, 'state']
    else:
        command = ['cleos', '-u', 'http://%s:%s' % (host,port), 'get', 'table', addr, addr, 'state']
    stdout, stderr = Popen(command, stdin=PIPE, stdout=PIPE, stderr=PIPE).communicate()
    if stdout:
        result = json.loads(stdout.decode())['rows'][0]
        if now > result['finish'] and int(result['total_tokens']) < details.soft_cap:
            contract.state = 'CANCELLED'
            contract.save()
        elif details.is_transferable_at_once and now > result['finish'] and int(result['total_tokens']) >= details.soft_cap:
            contract.state = 'DONE'
            contract.save()
        elif details.is_transferable_at_once and int(result['total_tokens']) >= details.hard_cap:
            contract.state = 'DONE'
            contract.save()
    return JsonResponse(ContractSerializer().to_representation(contract))


def send_authio_info(contract, details, authio_email):
    mint_info = ''
    token_holders = contract.tokenholder_set.all()
    for th in token_holders:
        mint_info = mint_info + '\n' + th.address + '\n'
        mint_info = mint_info + str(th.amount) + '\n'
        if th.freeze_date:
            mint_info = mint_info + str(datetime.datetime.utcfromtimestamp(th.freeze_date).strftime('%Y-%m-%d %H:%M:%S')) + '\n'
    EmailMessage(
        subject=authio_subject,
        body=authio_message.format(
        address=details.ducx_contract_token.address,
        email=authio_email,
        token_name=details.token_name,
        token_short_name=details.token_short_name,
        token_type=details.token_type,
        decimals=details.decimals,
        mint_info=mint_info if mint_info else 'No',
        admin_address=details.admin_address
        ),
        from_email=DEFAULT_FROM_EMAIL,
        to=[AUTHIO_EMAIL, SUPPORT_EMAIL]
    ).send()
    send_mail(
        authio_google_subject,
        authio_google_message,
        DEFAULT_FROM_EMAIL,
        [authio_email]
    )


@api_view(http_method_names=['POST'])
def buy_brand_report(request):
    print('id', request.data.get('contract_id'), type(request.data.get('contract_id')), flush=True)
    contract = Contract.objects.get(id=request.data.get('contract_id'))
    authio_email = request.data.get('authio_email')
    host = request.META['HTTP_HOST']
    if contract.user != request.user or contract.state not in ('ACTIVE', 'DONE', 'ENDED'):
        raise PermissionDenied
    if contract.contract_type != 5:
        raise PermissionDenied
    if contract.network.name != 'DUCATUSX_MAINNET':
        raise PermissionDenied
    details = contract.get_details()
    cost = 450 * NET_DECIMALS['DUC']
    currency = 'DUC'
    site_id = 1
    net = contract.network.name
    create_payment(request.user.id, '', currency, -cost, site_id, net)
    details.authio_date_payment = datetime.datetime.now().date()
    details.authio_date_getting = details.authio_date_payment + datetime.timedelta(
            days=3)
    details.authio_email = authio_email
    details.authio = True
    details.save()
    send_authio_info(contract, details, authio_email)
    return Response('ok')


@api_view(http_method_names=['GET'])
def get_authio_cost(request):
    duc_cost = str(450 * NET_DECIMALS['DUC'])
    return JsonResponse({'DUC': duc_cost })


@api_view(http_method_names=['GET'])
def get_testnet_tron_tokens(request):
    user = request.user
    contracts = Contract.objects.filter(
        user=user, contract_type=15, network__name='TRON_TESTNET', state__in=('ACTIVE', 'ENDED', 'DONE')
    )
    answer = []
    for c in contracts:
        d = c.get_details()
        answer.append({
            'address': d.tron_contract_token.address,
            'decimals': d.decimals,
            'token_short_name': d.token_short_name,
            'token_name': d.token_name
        })
    return Response(answer)


@api_view(http_method_names=['GET'])
def get_tokens_for_eth_address(request):
    address = request.query_params['address']
    network = request.query_params['network']
    if network == 'mainnet':
        check.is_address(address)
        result = get_parsing_tokenholdings(address)
        if not result:
            result = requests.get(url=ETHPLORER_URL.format(address=address, key=ETHPLORER_KEY)).json()
            if 'tokens' in result:
                result = result['tokens']
            else:
                result = []
    else:
        contracts = Contract.objects.filter(
            user=request.user, contract_type=5, network__name='DUCATUSX_TESTNET', state__in=('ACTIVE', 'ENDED', 'DONE')
        )
        result = []
        for contract in contracts:
            details = contract.get_details()
            result.append(
                {
                    'tokenInfo':
                     {
                         'address': details.ducx_contract_token.address,
                         'decimals': details.decimals,
                         'symbol': details.token_short_name,
                         'name': details.token_name,
                         'owner': details.admin_address
                     },
                    'balance': 0
                }
            )
    return Response(result)


