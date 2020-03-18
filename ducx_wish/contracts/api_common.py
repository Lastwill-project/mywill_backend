from rest_framework.response import Response
from rest_framework.decorators import api_view
from rest_framework.exceptions import ValidationError

from ducx_wish.contracts.api_eos import *
from ducx_wish.consts import *


@api_view(http_method_names=['GET'])
def get_available_contracts(request):
    '''
    view for get available contracts
    :param request: (network_id)
    :return: list of available contracts
    '''
    token = request.META['HTTP_TOKEN']
    if not token:
        raise ValidationError({'result': 'Token not found'}, code=404)
    get_user_for_token(token)
    if 'network_id' not in request.data:
        return Response(AVAILABLE_CONTRACT_TYPES)
    else:
        if int(request.data['network_id']) not in (1, 2, 5, 6, 10, 11, 14, 15):
            raise ValidationError({'result': 'Wrong network id'}, code=404)
        return Response(AVAILABLE_CONTRACT_TYPES[int(request.data['network_id'])])


@api_view(http_method_names=['GET'])
def get_contracts(request):
    '''
    view for get contracts with filter
    :param request: (network_id, network_type, contract_type, state)
    :return: list of available contracts
    '''
    token = request.META['HTTP_TOKEN']
    if not token:
        raise ValidationError({'result': 'Token not found'}, code=404)
    user = get_user_for_token(token)
    contracts = Contract.objects.filter(user=user, invisible=False)
    if 'network_id' in request.data:
        if int(request.data['network_id']) not in (1, 2, 5, 6, 10, 11, 14, 15):
            raise ValidationError({'result': 'Wrong network id'}, code=404)
        contracts = contracts.filter(network__id=int(request.data['network_id']))
    if 'network_type' in request.data:
        if request.data['network_type'].lower() not in ('testnet', 'mainnet'):
            raise ValidationError({'result': 'Wrong network type'}, code=404)
        contracts = contracts.filter(network__id__in=NETWORK_TYPES[request.data['network_type'].lower()])
    if 'contract_type' in request.data:
        if int(request.data['contract_type']) not in [x for x in range(18)] or int(request.data['contract_type']) == 3:
            raise ValidationError({'result': 'Wrong contract type'}, code=404)
        contracts = contracts.filter(contract_type=int(request.data['contract_type']))
    if 'state' in request.data:
        if request.data['state'] not in ALL_CONTRACT_STATES:
            raise ValidationError({'result': 'Wrong state'}, code=404)
        contracts = contracts.filter(state=request.data['state'])

    answer = []
    for c in contracts:
        answer.append({
            'id': c.id, 'name': c.name, 'network_name': c.network.name,
            'network_id': c.network.id, 'contract_type': c.contract_type,
            'state': c.state
        })
    return Response(answer)


@api_view(http_method_names=['GET'])
def get_contract_price(request):
    '''
    view for get contract price
    :param request: (contract_type)
    :return: price with decimals
    '''
    token = request.META['HTTP_TOKEN']
    if not token:
        raise ValidationError({'result': 'Token not found'}, code=404)
    get_user_for_token(token)
    if 'contract_type' not in request.data:
        return Response(API_CONTRACT_PRICES)
    else:
        if int(request.data['contract_type']) not in [x for x in range(18)]:
            raise ValidationError({'result': 'Wrong contract_type'}, code=404)
        if int(request.data['contract_type']) == 3 or int(request.data['contract_type']) == 6 or int(request.data['contract_type']) == 7:
            raise ValidationError({'result': 'Wrong contract_type'}, code=404)
        for x in API_CONTRACT_PRICES:
            if x['contract_type'] == int(request.data['contract_type']):
                return Response(x)
