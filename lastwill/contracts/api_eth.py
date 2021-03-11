from django.http import JsonResponse
from django.db.models import F
from django.shortcuts import get_object_or_404

from rest_framework.response import Response
from rest_framework.decorators import api_view
from rest_framework.exceptions import ValidationError

from lastwill.contracts.api_eos import *
import lastwill.check as check
from lastwill.contracts.models import *
from lastwill.profile.models import *
from lastwill.settings import MY_WISH_URL
from lastwill.deploy.models import *
from lastwill.consts import *


def log_userinfo(api_action, token, user=None, id=None):
    logger = ('ETH API: called {action} with token {tok} ').format(
        action=api_action, tok=token
    )
    if user is not None:
        logger += 'for user {usr} '.format(usr=user)
    if id is not None:
        logger += 'on contract {contract_id} '.format(contract_id=id)
    print(logger, flush=True)


def log_additions(api_action, add_params):
    logger = 'ETH API: {action} parameters: {params}'.format(
        action=api_action, params=add_params
    )
    print(logger, flush=True)


def validate_token_short_name(name):
    if len(name) > 64:
        raise ValidationError({'result': 'Too long token short name'},
                              code=404)
    if len(name) == 0:
        raise ValidationError({'result': 'Empty token short name'},
                              code=404)
    for symb in name:
        if not symb.isupper():
            raise ValidationError({'result': 'Wrong symbol in token short name'}, code=404)


def validate_token_name(name):
    if len(name) == 0:
        raise ValidationError({'result': 'Empty token name'},
                              code=404)
    if len(name) > 512:
        raise ValidationError({'result': 'Too long token name'},
                              code=404)


@api_view(http_method_names=['POST'])
def create_eth_token(request):
    '''
    view for create eth token
    :param request: (admin_address, token_name, decimals,
    token_short_name, token_type, network_id)
    :return: ok
    '''
    token = request.META['HTTP_TOKEN']
    if not token:
        raise ValidationError({'result': 'Token not found'}, code=404)
    user = get_user_for_token(token)
    if int(request.data['network_id']) not in [1, 2]:
        raise ValidationError({'result': 'Wrong network id'}, code=404)
    log_action_name = 'create_eth_token'
    log_userinfo(log_action_name, token, user)
    network = Network.objects.get(id=int(request.data['network_id']))
    check.is_address(request.data['admin_address'])
    if int(request.data['decimals']) < 0 or int(request.data['decimals']) > 50:
        raise ValidationError({'result': 'Wrong decimals'}, code=404)
    if request.data['token_type'] not in ['ERC20', 'ERC223']:
        raise ValidationError({'result': 'Wrong token type'}, code=404)
    validate_token_name(request.data['token_name'])
    validate_token_short_name(request.data['token_short_name'])
    if request.data['future_minting'] not in [True, False]:
        raise ValidationError({'result': 'Wrong future minting'}, code=404)
    token_params = {
        'decimals': int(request.data['decimals']),
        'token_name': request.data['token_name'],
        'token_short_name': request.data['token_short_name'],
        'admin_address': request.data['admin_address'],
        'token_type': request.data['token_type'],
        'future_minting': request.data['future_minting'],
        'token_holders': []
    }
    log_additions(log_action_name, token_params)
    Contract.get_details_model(
        5
    ).calc_cost(token_params, network)
    contract = Contract(
        state='CREATED',
        name='Contract',
        contract_type=5,
        network=network,
        cost=0,
        user=user
    )
    contract.save()

    contract_details = ContractDetailsTokenSerializer().create(contract, token_params)
    answer = {
        'state': contract.state,
        'admin_address': contract_details.admin_address,
        'token_short_name': contract_details.token_short_name,
        'token_name': contract_details.token_name,
        'contract_id': contract.id,
        'created_date': contract.created_date,
        'network': contract.network.name,
        'network_id': contract.network.id,
        'decimals': contract_details.decimals,
        'token_type': contract_details.token_type,
        'future_minting': contract_details.future_minting
    }
    return Response(answer)


@api_view(http_method_names=['GET'])
def show_eth_token(request):
    '''
    view for show eth token
    :param request: contain contract id
    :return:
    '''
    # token = request.data['token']
    token = request.META['HTTP_TOKEN']
    if not token:
        raise ValidationError({'result': 'Token not found'}, code=404)
    user = get_user_for_token(token)
    log_action_name = 'show_eth_token'
    log_userinfo(log_action_name, token, user)
    contract = get_object_or_404(Contract, id=int(request.data['contract_id']))
    if contract.invisible:
        raise ValidationError({'result': 'Contract is deleted'}, code=404)
    if contract.user != user:
        raise ValidationError({'result': 'Wrong token'}, code=404)
    contract_details = contract.get_details()
    answer = {
        'state': contract.state,
        'contract_id': contract.id,
        'created_date': contract.created_date,
        'network': contract.network.name,
        'network_id': contract.network.id,
        'token_name': contract_details.token_name,
        'token_short_name': contract_details.token_short_name,
        'admin_address': contract_details.admin_address,
        'decimals': contract_details.decimals,
        'token_type': contract_details.token_type,
        'future_minting': contract_details.future_minting
    }
    log_additions(log_action_name, {'contract_id': int(request.data['contract_id'])})
    if contract_details.eth_contract_token and contract_details.eth_contract_token.tx_hash:
        answer['tx_hash'] = contract_details.eth_contract_token.tx_hash
    if contract_details.eth_contract_token and contract_details.eth_contract_token.address:
        answer['contract_address'] = contract_details.eth_contract_token.address
    if contract_details.eth_contract_token and contract_details.eth_contract_token.compiler_version:
        answer['compiler_version'] = contract_details.eth_contract_token.compiler_version
        answer['name_contract'] = 'MainToken'
    return JsonResponse(answer)


@api_view(http_method_names=['PUT', 'PATCH'])
def edit_eth_token(request):
    '''
    view for edit params in  eth token
    :param request: contain contract id, editable field
    (admin_address, token_name, decimals, token_short_name, token_type)
    :return:
    '''
    token = request.META['HTTP_TOKEN']
    if not token:
        raise ValidationError({'result': 'Token not found'}, code=404)
    user = get_user_for_token(token)
    log_action_name = 'edit_eth_token'
    log_userinfo(log_action_name, token, user)
    contract = Contract.objects.get(id=int(request.data['contract_id']))
    if contract.invisible:
        raise ValidationError({'result': 'Contract is deleted'}, code=404)
    if contract.state != 'CREATED':
        raise ValidationError({'result': 'Wrong status in contract'}, code=403)
    if contract.user != user:
        raise ValidationError({'result': 'Wrong token'}, code=404)
    contract_details = contract.get_details()
    fields = ('decimals', 'token_type', 'token_short_name', 'admin_address', 'token_name')
    if not any([key in request.data.keys() for key in fields]):
        raise ValidationError({'result': 'Optional parameters (at least one)'}, code=403)
    if 'decimals' in request.data:
        if int(request.data['decimals']) < 0 and int(request.data['decimals']) > 50:
            raise ValidationError({'result': 'Wrong decimals'}, code=404)
        contract_details.decimals = int(request.data['decimals'])
    if 'token_type' in request.data:
        if request.data['token_type'] not in ['ERC20', 'ERC223']:
            raise ValidationError({'result': 'Wrong token type'}, code=404)
        contract_details.token_type = request.data['token_type']
    if 'token_short_name' in request.data:
        validate_token_short_name(request.data['token_short_name'])
        contract_details.token_short_name = request.data['token_short_name']
    if 'admin_address' in request.data:
        check.is_address(request.data['admin_address'])
        contract_details.admin_address = request.data['admin_address']
    if 'token_name' in request.data and request.data['token_name'] != '':
        validate_token_name(request.data['token_name'])
        contract_details.token_name = request.data['token_name']
    if 'future_minting' in request.data:
        if request.data['future_minting'] not in [True, False]:
            raise ValidationError({'result': 'Wrong future minting'}, code=404)
        contract_details.future_minting = request.data['future_minting']
    log_additions(log_action_name, request.data)
    contract_details.save()
    answer = {
        'state': contract.state,
        'contract_id': contract.id,
        'created_date': contract.created_date,
        'network': contract.network.name,
        'network_id': contract.network.id,
        'token_name': contract_details.token_name,
        'token_short_name': contract_details.token_short_name,
        'admin_address': contract_details.admin_address,
        'decimals': contract_details.decimals,
        'token_type': contract_details.token_type
    }
    return Response(answer)


@api_view(http_method_names=['GET'])
def calculate_cost_eth_token_contract(request):
    eth_cost = int(CONTRACT_PRICE_ETH['TOKEN'] * NET_DECIMALS['ETH'])
    token = request.META['HTTP_TOKEN']
    if not token:
        raise ValidationError({'result': 'Token not found'}, code=404)
    get_user_for_token(token)
    log_userinfo('calculate_cost_eos_account', token)
    return Response({
        'ETH': str(int(eth_cost)),
        'WISH': str(int(eth_cost) * rate('ETH', 'WISH')),
        'BTC': str(int(eth_cost) * rate('ETH', 'BTC'))
    })


@api_view(http_method_names=['POST', 'DELETE'])
def delete_eth_token_contract(request):
    '''
    delete eth token
    :param request: contain contract_id
    :return: cost
    '''
    token = request.META['HTTP_TOKEN']
    if not token:
        raise ValidationError({'result': 'Token not found'}, code=404)
    user = get_user_for_token(token)
    contract = Contract.objects.get(id=int(request.data['contract_id']))
    log_userinfo('delete_cost_eos_account_contract', token, user, int(request.data['contract_id']))
    if contract.user != user:
        raise ValidationError({'result': 'Wrong token'}, code=404)
    if contract.contract_type != 5:
        raise ValidationError({'result': 'Wrong contract id'}, code=404)
    contract.invisible = True
    contract.save()
    return Response('Contract with id {id} deleted'.format(id=contract.id))



@api_view(http_method_names=['POST'])
def deploy_eth_token(request):
    '''
    view for deploy eth token
    :param request: contain contract id
    :return:
    '''
    token = request.META['HTTP_TOKEN']
    if not token:
        raise ValidationError({'result': 'Token not found'}, code=404)
    user = get_user_for_token(token)
    contract = Contract.objects.get(id=int(request.data.get('contract_id')))
    log_action_name = 'deploy_eth_token'
    contract_id = int(request.data.get('contract_id'))
    log_userinfo(log_action_name, token, user, contract_id)
    if contract.user != user:
        raise ValidationError({'result': 'Wrong contract_id'}, code=404)
    if contract.invisible:
        raise ValidationError({'result': 'Contract is deleted'}, code=404)
    if contract.state != 'CREATED':
        raise ValidationError({'result': 'Wrong status in contract'}, code=404)
    contract_details = contract.get_details()
    log_additions(log_action_name, request.data)
    contract_details.predeploy_validate()
    if contract.network.id == 1:
        eth_cost = int(CONTRACT_PRICE_ETH['TOKEN'] * NET_DECIMALS['ETH'])
        wish_cost = int(eth_cost) * rate('ETH', 'WISH')
        if 'promo' in request.data:
            promo = request.data['promo'].upper()
            user_balance = UserSiteBalance.objects.get(user=user, subsite__site_name=MY_WISH_URL).balance
            wish_cost = check_promocode_in_api(promo, 15, user, user_balance, contract.id, wish_cost)
        if not UserSiteBalance.objects.select_for_update().filter(
                user=user, subsite__site_name=MY_WISH_URL, balance__gte=wish_cost
        ).update(balance=F('balance') - wish_cost):
            raise ValidationError({'result': 'You have not money'}, code=400)
    contract.state = 'WAITING_FOR_DEPLOYMENT'
    contract.save()
    queue = NETWORKS[contract.network.name]['queue']
    send_in_queue(contract.id, 'launch', queue)
    return Response({'id': contract.id, 'state': contract.state})


@api_view(http_method_names=['GET'])
def get_source_code_eth_token(request):
    '''
    view for show source code of eth token
    :param request: contain contract id
    :return:
    '''
    # token = request.data['token']
    token = request.META['HTTP_TOKEN']
    if not token:
        raise ValidationError({'result': 'Token not found'}, code=404)
    user = get_user_for_token(token)
    contract = get_object_or_404(Contract, id=int(request.data['contract_id']))
    log_action_name = 'get_source_code_eth_token'
    log_userinfo(log_action_name, token, int(request.data['contract_id']))
    if contract.invisible:
        raise ValidationError({'result': 'Contract is deleted'}, code=404)
    if contract.network.name != 'ETHEREUM_MAINNET':
        raise ValidationError({'result': 'Source code not available for testnet'}, code=404)
    if contract.state not in ['ACTIVE', 'DONE', 'ENDED']:
        raise ValidationError({'result': 'Source code not available for this state of contract'}, code=404)
    if contract.user != user:
        raise ValidationError({'result': 'Wrong token'}, code=404)
    contract_details = contract.get_details()
    answer = {
        'source_code': contract_details.eth_contract_token.source_code,
    }
    return JsonResponse(answer)
