from binascii import hexlify, unhexlify
from eospy.utils import sha256, ripemd160, str_to_hex, hex_to_int

from django.http import JsonResponse
from django.db.models import F
from django.shortcuts import get_object_or_404

from rest_framework.response import Response
from rest_framework.decorators import api_view
from rest_framework.exceptions import ValidationError

from lastwill.contracts.serializers import *
from lastwill.contracts.models import *
from lastwill.profile.models import *
from lastwill.promo.models import *
from lastwill.settings import EOSISH_URL
from lastwill.deploy.models import *
from lastwill.consts import *
from lastwill.rates.api import rate


def check_account_name(name, network_id):
    network = Network.objects.get(id=network_id)
    if network.name == 'EOS_MAINNET':
        eos_url = 'https://%s' % (
            str(NETWORKS[network.name]['host']))
    else:
        eos_url = 'http://%s:%s' % (
        str(NETWORKS[network.name]['host']),
        str(NETWORKS[network.name]['port']))

    command_list = [
            'cleos', '-u', eos_url, 'get', 'account', name, '--json'
        ]
    proc = Popen(command_list, stdin=PIPE, stdout=PIPE, stderr=PIPE)
    stdout, stderr = proc.communicate()
    if len(stdout) > 0:
        json.loads(stdout.decode())
        raise ValidationError({
            'result': 'Account with this name has already been created'
        }, code=404)


def check_eos_key(key, key_type=None) :
    '''
    method check eos public key
    :param key: eos key
    :param key_type: type of cryptografy
    :return: key if succuss else ValueError
    '''
    if not key.startswith('EOS'):
        raise ValueError('EOS public key should start with "EOS"')
    key_string = key[3:]
    buffer = hexlify(base58.b58decode(key_string)).decode()
    chksum = buffer[-8:]
    key = buffer[:-8]
    if key_type == 'sha256x2':
            # legacy
        first_sha = sha256(unhexlify(key))
        newChk = sha256(unhexlify(first_sha))[:8]
    else:
        check = key
        if key_type:
            check += hexlify(bytearray(key_type, 'utf-8')).decode()
        newChk = ripemd160(unhexlify(check))[:8]
    print('newChk: '+newChk)
    if chksum != newChk :
        raise ValueError('Checksums do not match: {0} != {1} in your public key'.format(chksum, newChk))
    return key


def get_user_for_token(token):
    api_token = get_object_or_404(APIToken, token=token)
    if not api_token.active:
        raise ValidationError({'result': 'Your token is not active'}, code=404)
    return api_token.user


def check_promocode_in_api(promo_str, contract_type, user, balance, cid, cost):
    promo = Promo.objects.filter(promo_str=promo_str).first()
    if not promo:
        raise ValidationError({'result': 'Wrong promocode'}, code=404)
    now_date = datetime.datetime.now().date()
    if now_date >= promo.start and now_date <= promo.stop:
        p2c = Promo2ContractType.objects.filter(promo=promo, contract_type=contract_type).first()
        if not p2c:
            raise ValidationError({'result': 'Promocode is not valid for this type of contract'},
                                  code=404)
        u2p = User2Promo.objects.filter(user=user, promo=promo).first()
        if u2p:
            raise ValidationError({'result': 'Promocode already used'},
                                  code=404)
        discount = p2c.discount
        if balance >= discount:
            User2Promo(user=user, promo=promo, contract_id=cid).save()
            cost = cost * discount / 100
            return cost
    else:
        raise ValidationError({'result': 'Promocode is not valid'}, code=404)



def validate_account_name(name):
    if len(name) != 12:
        raise ValidationError({'result': 'Wrong lenght of account name'}, code=404)
    for symb in name:
        if symb.isupper():
            raise ValidationError({'result': 'Upper case in account name'},
                                  code=404)
        if symb in ['6', '7', '8', '9', '0']:
            raise ValidationError({'result': 'Wrong number in account name'},
                                  code=404)


def validate_eos_account_params(cpu, net, ram):
    if cpu > 50 or net > 50 or ram > 40 or cpu < 0 or net < 0 or ram < 0:
        raise ValidationError({'result': 'Wrong value net, cpu or ram'},
                              code=404)


def calc_eos_cost(cpu, net, ram):
    eos_url = 'https://%s' % (
        str(NETWORKS['EOS_MAINNET']['host'])
    )
    command1 = [
        'cleos', '-u', eos_url, 'get', 'table', 'eosio', 'eosio', 'rammarket'
    ]
    result = implement_cleos_command(command1)
    ram_cost = result['rows'][0]
    ram_price = float(ram_cost['quote']['balance'].split()[0]) / float(
        ram_cost['base']['balance'].split()[0]) * 1024
    print('get ram price', flush=True)

    eos_cost = round(
        (float(ram) * ram_price + float(net) + float(cpu)) * 2 + 0.3, 0)
    return eos_cost


def log_userinfo(api_action, token, user=None, id=None):
    logger = ('EOS API: called {action} with token {tok} ').format(
        action=api_action, tok=token
    )
    if user is not None:
        logger += 'for user {usr} '.format(usr=user)
    if id is not None:
        logger += 'on contract {contract_id} '.format(contract_id=id)
    print(logger, flush=True)


def log_additions(api_action, add_params):
    logger = 'EOS API: {action} parameters: {params}'.format(
        action=api_action, params=add_params
    )
    print(logger, flush=True)


def check_int_number(number):
    try:
        int(number)
    except:
        raise ValidationError({'result': 'Invalid value. Integer var expected.'}, code=404)


@api_view(http_method_names=['POST'])
def create_eos_account(request):
    '''
    view for create eos account
    :param request: contain account_name, owner_public_key, active_public_key, token, network_id
    :return: ok
    '''
    token = request.META['HTTP_TOKEN']
    if not token:
        raise ValidationError({'result': 'Token not found'}, code=404)
    user = get_user_for_token(token)
    log_action_name = 'create_eos_account'
    log_userinfo(log_action_name, token, user)
    print('logging', flush=True)
    token_params = {}
    token_params['account_name'] = request.data['account_name']
    validate_account_name(request.data['account_name'])
    check_account_name(token_params['account_name'], int(request.data['network_id']))
    if int(request.data['network_id']) not in [10,11]:
        raise ValidationError({'result': 'Wrong network id'}, code=404)
    network = Network.objects.get(id=int(request.data['network_id']))
    token_params['owner_public_key'] = request.data['owner_public_key']
    check_eos_key(request.data['owner_public_key'])
    token_params['active_public_key'] = request.data['active_public_key']
    check_eos_key(request.data['active_public_key'])
    if 'stake_net_value' in request.data and len(str(request.data['stake_net_value'])) > 0:
        token_params['stake_net_value'] = str(request.data['stake_net_value'])
    else:
        token_params['stake_net_value'] = '0.01'
    if 'stake_cpu_value' in  request.data and len(str(request.data['stake_cpu_value'])) > 0:
        token_params['stake_cpu_value'] = str(request.data['stake_cpu_value'])
    else:
        token_params['stake_cpu_value'] = '0.64'
    if 'buy_ram_kbytes' in request.data and request.data['buy_ram_kbytes'] != '':
        check_int_number(request.data['buy_ram_kbytes'])
        token_params['buy_ram_kbytes'] = int(request.data['buy_ram_kbytes'])
    else:
        token_params['buy_ram_kbytes'] = 4
    log_additions(log_action_name, token_params)
    validate_eos_account_params(
        float(token_params['stake_cpu_value']),
        float(token_params['stake_net_value']),
        token_params['buy_ram_kbytes']
    )
    name_contract = request.data['name'] if 'name' in request.data else 'contract'
    contract = Contract(
        state='CREATED',
        name=name_contract,
        contract_type=11,
        network=network,
        cost=0,
        user=user
    )
    contract.save()
    eos_contract = EOSContract(
        address=None,
        source_code='',
        abi={},
        bytecode='',
        compiler_version=None,
        constructor_arguments=''
    )
    eos_contract.save()
    token_params['eos_contract'] = eos_contract
    ContractDetailsEOSAccountSerializer().create(contract, token_params)
    contract_details = contract.get_details()
    answer = {
        'state': contract.state,
        'address': contract_details.account_name,
        'contract_id': contract.id,
        'created_date': contract.created_date,
        'network': contract.network.name,
        'network_id': contract.network.id,
        'name': contract.name
    }
    answer['net'] = contract_details.stake_net_value
    answer['cpu'] = contract_details.stake_cpu_value
    answer['ram'] = contract_details.buy_ram_kbytes
    return Response(answer)


@api_view(http_method_names=['POST'])
def deploy_eos_account(request):
    '''
    view for deploy eos ac count
    :param request: contain contract id
    :return:
    '''
    token = request.META['HTTP_TOKEN']
    if not token:
        raise ValidationError({'result': 'Token not found'}, code=404)
    user = get_user_for_token(token)
    log_action_name = 'deploy_eos_account'
    contract_id = int(request.data.get('contract_id'))
    log_userinfo(log_action_name, token, user, contract_id)
    contract = Contract.objects.get(id=contract_id)
    if contract.user != user:
        raise ValidationError({'result': 'Wrong contract_id'}, code=404)
    if contract.invisible:
        raise ValidationError({'result': 'Contract is deleted'}, code=404)
    if contract.state != 'CREATED':
        raise ValidationError({'result': 'Wrong state'}, code=404)
    contract_details = contract.get_details()
    log_additions(log_action_name, request.data)
    check_account_name(contract_details.account_name, contract.network.id)
    contract_details.predeploy_validate()
    if contract.network.id == 10:
        network = Network.objects.get(name='EOS_MAINNET')
        params = {
            'stake_net_value': contract_details.stake_net_value,
            'stake_cpu_value': contract_details.stake_cpu_value,
            'buy_ram_kbytes': contract_details.buy_ram_kbytes
        }
        eosish_cost = contract_details.calc_cost_eos(params, network)
        eos_cost = (int(eosish_cost) * rate('EOS', 'EOSISH'))
        if 'promo' in request.data:
            promo = request.data['promo'].upper()
            user_balance = UserSiteBalance.objects.get(user=user, subsite__site_name=EOSISH_URL).balance
            eos_cost = check_promocode_in_api(promo, 10, user, user_balance, contract.id, eos_cost)
        if not UserSiteBalance.objects.select_for_update().filter(
                user=user, subsite__site_name=EOSISH_URL, balance__gte=eos_cost
        ).update(balance=F('balance') - eos_cost):
            raise ValidationError({'result': 'You have not money'}, code=400)
    contract.state = 'WAITING_FOR_DEPLOYMENT'
    contract.save()
    queue = NETWORKS[contract.network.name]['queue']
    send_in_queue(contract.id, 'launch', queue)
    return Response({'id': contract.id, 'state': contract.state})


@api_view(http_method_names=['GET'])
def show_eos_account(request):
    '''
    view for show eos account
    :param request: contain contract id
    :return:
    '''
    # token = request.data['token']
    token = request.META['HTTP_TOKEN']
    if not token:
        raise ValidationError({'result': 'Token not found'}, code=404)
    user = get_user_for_token(token)
    log_action_name = 'show_eos_account'
    contract_id = int(request.data['contract_id'])
    log_userinfo(log_action_name, token, user, contract_id)
    contract = get_object_or_404(Contract, id=contract_id)
    if contract.invisible:
        raise ValidationError({'result': 'Contract is deleted'}, code=404)
    if contract.user != user:
        raise ValidationError({'result': 'Wrong token'}, code=404)
    contract_details = contract.get_details()
    log_additions(log_action_name, {'contract_id': int(request.data['contract_id'])})
    answer = {
        'state': contract.state,
        'address': contract_details.account_name,
        'contract_id': contract.id,
        'created_date': contract.created_date,
        'network': contract.network.name,
        'network_id': contract.network.id,
        'name': contract.name
    }
    answer['net'] = contract_details.stake_net_value
    answer['cpu'] = contract_details.stake_cpu_value
    answer['ram'] = contract_details.buy_ram_kbytes
    if contract_details.eos_contract:
        if contract_details.eos_contract.tx_hash:
            answer['tx_hash'] = contract_details.eos_contract.tx_hash
    return JsonResponse(answer)


@api_view(http_method_names=['PUT', 'PATCH'])
def edit_eos_account(request):
    '''
    view for edit params in  eos account
    :param request: contain contract id, editable field
    (account_name, public_key, cpu, net, ram)
    :return:
    '''
    token = request.META['HTTP_TOKEN']
    if not token:
        raise ValidationError({'result': 'Token not found'}, code=404)
    user = get_user_for_token(token)
    log_action_name = 'edit_eos_account'
    log_userinfo(log_action_name, token, user)
    # params = json.loads(request.body)
    contract = Contract.objects.get(id=int(request.data['contract_id']))
    if contract.invisible:
        raise ValidationError({'result': 'Contract is deleted'}, code=404)
    if contract.state != 'CREATED':
        raise ValidationError({'result': 'Wrong status in contract'}, code=403)
    if contract.user != user:
        raise ValidationError({'result': 'Wrong token'}, code=404)
    contract_details = contract.get_details()
    if 'stake_net_value' in request.data and len(str(request.data['stake_net_value'])) > 0:
        if float(request.data['stake_net_value']) < 0 or float(request.data['stake_net_value']) > 50:
            raise ValidationError({'result': 'Wrong value of net'}, code=404)
        else:
            contract_details.stake_net_value = str(request.data['stake_net_value'])
    if 'stake_cpu_value' in request.data and len(str(request.data['stake_cpu_value'])) > 0:
        if float(request.data['stake_cpu_value']) < 0 or float(request.data['stake_cpu_value']) > 50:
            raise ValidationError({'result': 'Wrong value of cpu'}, code=404)
        else:
            contract_details.stake_cpu_value = str(request.data['stake_cpu_value'])
    if 'buy_ram_kbytes' in request.data and request.data['buy_ram_kbytes'] != '':
        check_int_number(request.data['buy_ram_kbytes'])
        if int(request.data['buy_ram_kbytes']) > 40 or int(request.data['buy_ram_kbytes']) < 0:
            raise ValidationError({'result': 'Wrong value of ram'}, code=404)
        else:
            contract_details.buy_ram_kbytes = int(request.data['buy_ram_kbytes'])
    if 'account_name' in request.data:
        validate_account_name(request.data['account_name'])
        check_account_name(request.data['account_name'], contract.network.id)
        contract_details.account_name = request.data['account_name']
    if 'owner_public_key' in request.data:
        check_eos_key(request.data['owner_public_key'])
        contract_details.owner_public_key = request.data['owner_public_key']
    if 'active_public_key' in request.data:
        check_eos_key(request.data['active_public_key'])
        contract_details.active_public_key = request.data['active_public_key']
    log_additions(log_action_name, request.data)
    contract_details.save()
    if 'name' in request.data and len(request.data['name']) > 0:
        contract.name = request.data['name']
        contract.save()
    answer = {
        'state': contract.state,
        'address': contract_details.account_name,
        'contract_id': contract.id,
        'created_date': contract.created_date,
        'network': contract.network.name,
        'network_id': contract.network.id,
        'name': contract.name
    }
    answer['net'] = contract_details.stake_net_value
    answer['cpu'] = contract_details.stake_cpu_value
    answer['ram'] = contract_details.buy_ram_kbytes
    return Response(answer)


@api_view(http_method_names=['GET'])
def calculate_cost_eos_account(request):
    '''
    calculate cost eos account with getting params
    cpu, net, ram
    :param request: contain cpu, net, ram
    :return: cost
    '''
    token = request.META['HTTP_TOKEN']
    if not token:
        raise ValidationError({'result': 'Token not found'}, code=404)
    get_user_for_token(token)
    log_userinfo('calculate_cost_eos_account', token)
    print('data in request', request.data, flush=True)
    ram = request.data['buy_ram_kbytes']
    net = request.data['stake_net_value']
    cpu = request.data['stake_cpu_value']
    eos_cost = calc_eos_cost(cpu, net, ram)
    print('eos cost', eos_cost, flush=True)

    return JsonResponse({
        'EOS': str(eos_cost),
        'EOSISH': str(eos_cost * rate('EOS', 'EOSISH')),
        'ETH': str(eos_cost * rate('EOS', 'ETH')),
        'WISH': str(eos_cost * rate('EOS', 'WISH')),
        'BTC': str(eos_cost * rate('EOS', 'BTC')),
    })


@api_view(http_method_names=['GET'])
def calculate_cost_eos_account_contract(request):
    '''
    calculate cost eos account
    :param request: contain contract_id
    :return: cost
    '''
    token = request.META['HTTP_TOKEN']
    if not token:
        raise ValidationError({'result': 'Token not found'}, code=404)
    user = get_user_for_token(token)
    contract_id = int(request.data['contract_id'])
    log_action_name = 'calculate_cost_eos_account_contract'
    log_userinfo(log_action_name, token, user, contract_id)
    contract = Contract.objects.get(id=contract_id)
    if contract.state != 'CREATED':
        raise ValidationError({'result': 'Wrong status in contract'}, code=404)
    if contract.contract_type != 11:
        raise ValidationError({'result': 'Wrong contract_type'}, code=404)
    if contract.user != user:
        raise ValidationError({'result': 'Wrong token'}, code=404)
    if contract.invisible:
        raise ValidationError({'result': 'Contract is deleted'}, code=404)
    details = contract.get_details()
    log_additions(log_action_name, details)
    network = Network.objects.get(name='EOS_MAINNET')
    params = {
        'stake_net_value': details.stake_net_value,
        'stake_cpu_value': details.stake_cpu_value,
        'buy_ram_kbytes': details.buy_ram_kbytes
    }
    eos_cost = ContractDetailsEOSAccount.calc_cost_eos(params, network) /10 ** 4
    print('eos cost', eos_cost, flush=True)

    return JsonResponse({
        'EOS': str(eos_cost),
        'EOSISH': str(eos_cost * rate('EOS', 'EOSISH')),
        'ETH': str(eos_cost * rate('EOS', 'ETH')),
        'WISH': str(eos_cost * rate('EOS', 'WISH')),
        'BTC': str(eos_cost * rate('EOS', 'BTC')),
    })


@api_view(http_method_names=['POST', 'DELETE'])
def delete_eos_account_contract(request):
    '''
    delete cost eos account
    :param request: contain contract_id
    :return: cost
    '''
    token = request.META['HTTP_TOKEN']
    if not token:
        raise ValidationError({'result': 'Token not found'}, code=404)
    user = get_user_for_token(token)
    contract_id = int(request.data['contract_id'])
    log_userinfo('delete_cost_eos_account_contract', token, user, contract_id)
    contract = Contract.objects.get(id=contract_id)
    if contract.user != user:
        raise ValidationError({'result': 'Wrong token'}, code=404)
    contract.invisible = True
    contract.save()
    return Response('Contract with id {id} deleted'.format(id=contract.id))


@api_view(http_method_names=['GET'])
def get_all_blockchains(request):
    '''
    get list of blockchains
    :param request: token only
    :return: json with blockchain id and name
    '''
    token = request.META['HTTP_TOKEN']
    log_userinfo('get_all_blockchain', token)
    if not token:
        raise ValidationError({'result': 'Token not found'}, code=404)
    get_user_for_token(token)
    nets = Network.objects.all()
    answer = []
    for net in nets:
        answer.append({'id': net.id, 'blockchain_name': API_NETWORK[net.name]})
    return JsonResponse({'networks': answer})


@api_view(http_method_names=['GET'])
def get_profile_info(request):
    '''
    get info abount user
    :param request: token only
    :return: json with info about user - username, contracts_count, id, lang
    '''
    token = request.META['HTTP_TOKEN']
    if not token:
        raise ValidationError({'result': 'Token not found'}, code=404)
    user = get_user_for_token(token)
    log_userinfo('get_profile_info', token, user)
    answer = {
        'username': user.email if user.email else '{} {}'.format(
            user.first_name, user.last_name),
        'contracts': Contract.objects.filter(user=user, invisible=False).count(),
        'id': user.id,
        'lang': user.profile.lang,
    }
    log_userinfo('get_profile_info', token, user)
    return Response(answer)


@api_view(http_method_names=['GET'])
def get_balance_info(request):
    '''
    get info abount user's balance in getting blockchain
    :param request: token, network_id
    :return: balance
    '''
    token = request.META['HTTP_TOKEN']
    if not token:
        raise ValidationError({'result': 'Token not found'}, code=404)
    user = get_user_for_token(token)
    log_action_name = 'get_profile_info'
    log_userinfo(log_action_name, token, user)
    network_id = request.data['network_id']
    net = Network.objects.get(id=network_id)
    log_additions(log_action_name, network_id)
    balance = UserSiteBalance.objects.get(user=user, subsite__id = NETWORK_SUBSITE[net.name]).balance
    return JsonResponse({'balance': balance})


@api_view(http_method_names=['GET'])
def get_eos_contracts(request):
    '''
    get info abount user's balance in getting blockchain
    :param request: token, network_id
    :return: balance
    '''
    token = request.META['HTTP_TOKEN']
    log_action_name = 'get_eos_contracts'
    log_userinfo(log_action_name, token)
    if not token:
        raise ValidationError({'result': 'Token not found'}, code=404)
    user = get_user_for_token(token)
    if 'limit' in request.data:
        limit = int(request.data['limit'])
    else:
        limit = 8
    log_additions(log_action_name, limit)
    contracts = Contract.objects.filter(contract_type=11, user=user, network__name__in=['EOS_MAINNET', 'EOS_TESTNET'], invisible=False)
    contracts = contracts.order_by('-created_date')[0:limit]
    answer = {'contracts': []}
    for c in contracts:
        contract_info = {
            'contract_id': c.id,
            'state': c.state,
            'created_date': c.created_date,
            'network': c.network.name,
            'network_id': c.network.id,
            'name': c.name,
            'details': ContractDetailsEOSAccountSerializer(c.get_details()).data
        }
        answer['contracts'].append(contract_info)
    log_userinfo('get_eos_contracts', token, user)
    return JsonResponse(answer)
