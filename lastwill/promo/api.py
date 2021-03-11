import datetime
from django.core.exceptions import ObjectDoesNotExist
from rest_framework.decorators import api_view
from rest_framework.exceptions import PermissionDenied
from rest_framework.response import Response

from lastwill.contracts.submodels.common import Contract
from lastwill.contracts.serializers import ContractSerializer
from lastwill.settings import MY_WISH_URL, EOSISH_URL, TRON_URL, WAVES_URL
from lastwill.consts import NET_DECIMALS, VERIFICATION_PRICE_USDT
from .models import *
from lastwill.rates.api import rate


def check_and_get_discount(promo_str, contract_type, user):
    promo = Promo.objects.filter(promo_str=promo_str.upper()).first()
    if promo is None:
        raise PermissionDenied(2000)
    now = datetime.datetime.now().date()
    if (promo.start and promo.start > now) or (promo.stop and promo.stop < now):
        raise PermissionDenied(2003)
    if promo.use_count_max and promo.use_count >= promo.use_count_max:
        raise PermissionDenied(2004)
    if promo.user2promo_set.filter(user=user).exists():
        raise PermissionDenied(2001)
    p2ct = promo.promo2contracttype_set.filter(contract_type=contract_type).first()
    if not p2ct:
        raise PermissionDenied(2002)
    return p2ct.discount


@api_view()
def get_discount(request):
    if request.user.is_anonymous:
        raise PermissionDenied()
    host = request.META['HTTP_HOST']
    user = request.user
    contract_type = request.query_params['contract_type']
    promo_str = request.query_params['promo']
    discount = check_and_get_discount(promo_str, contract_type, user)
    answer = {'discount': discount}
    if 'contract_id' in request.query_params:
        contract = Contract.objects.get(id=request.query_params['contract_id'])
        contract_details = contract.get_details()
        if host == EOSISH_URL:
            kwargs = ContractSerializer().get_details_serializer(
                contract.contract_type
            )().to_representation(contract_details)
            cost = contract_details.calc_cost_eos(kwargs, contract.network) * (100 - discount) / 100
            answer['discount_price'] = {
                'EOS': cost,
                'EOSISH': str(float(cost) * rate('EOS', 'EOSISH'))
            }
        elif host == MY_WISH_URL:
            options_cost = 0
            if contract.contract_type == 5:
                if contract_details.authio:
                    options_cost += 450 * NET_DECIMALS['USDT']
            if contract.contract_type in (5, 4, 8, 27, 28):
                if contract_details.verification:
                    options_cost += VERIFICATION_PRICE_USDT * NET_DECIMALS['USDT']

            cost = (contract.cost - options_cost) * (100 - discount) / 100 + options_cost
            answer['discount_price'] = {
                'USDT': str(cost),
                'ETH': str(int(int(cost) / 10 ** 6 * rate('USDT', 'ETH') * 10 ** 18)),
                'WISH': str(int(int(cost) / 10 ** 6 * rate('USDT', 'WISH') * 10 ** 18)),
                'BTC': str(int(int(cost) / 10 ** 6 * rate('USDT', 'BTC') * 10 ** 8)),
                'TRX': str(int(int(cost) * rate('ETH', 'TRX'))),
                'TRONISH': str(int(int(cost) * rate('ETH', 'TRX')))
            }
        elif host == TRON_URL:
            kwargs = ContractSerializer().get_details_serializer(
                contract.contract_type
            )().to_representation(contract_details)
            cost = contract_details.calc_cost_tron(kwargs, contract.network) * (100 - discount) / 100

            answer['discount_price'] = {
                'TRX': int(cost),
                'TRONISH': int(cost)
            }
        elif host == WAVES_URL:
            kwargs = ContractSerializer().get_details_serializer(
                contract.contract_type
            )().to_representation(contract_details)
            cost = contract_details.calc_cost(kwargs, contract.network) * (100 - discount) / 100
            answer['discount_price'] = {
                'USDT': str(cost),
                'ETH': str(int(int(cost) / 10 ** 6 * rate('USDT', 'ETH') * 10 ** 18)),
                'WISH': str(int(int(cost) / 10 ** 6 * rate('USDT', 'WISH') * 10 ** 18)),
                'BTC': str(int(int(cost) / 10 ** 6 * rate('USDT', 'BTC') * 10 ** 8)),
                'TRX': str(int(int(cost) * rate('ETH', 'TRX'))),
                'TRONISH': str(int(int(cost) * rate('ETH', 'TRX')))
            }
        else:
            kwargs = ContractSerializer().get_details_serializer(
                contract.contract_type
            )().to_representation(contract_details)
            cost = contract_details.calc_cost(kwargs, contract.network) * (100 - discount) / 100
            answer['discount_price'] = {
                'ETH': str(cost),
                'WISH': str(int(cost * rate('ETH', 'WISH'))),
                'BTC': str(int(cost * rate('ETH', 'BTC'))),
                'TRX': str(int(cost) / 10 ** 18 * rate('ETH', 'TRX') * 10 ** 6),
                'TRONISH': str(int(cost) / 10 ** 18 * rate('ETH', 'TRONISH') * 10 ** 6)
            }

    return Response(answer)


def create_promocode(
        promo_str, contract_types, discount, start=None,
        stop=None, use_count=0, use_count_max=None
):
    promo = Promo.objects.filter(promo_str=promo_str.upper()).first()
    if promo is not None:
        print('this promocode already exists')
        return
    else:
        if start is None and stop is None:
            start = datetime.datetime.now().date()
            stop = datetime.datetime(start.year + 1, start.month, start.day).date()
        promo = Promo(
            promo_str=promo_str, start=start, stop=stop,
            use_count=use_count, use_count_max=use_count_max
        )
        promo.save()
        for ct in contract_types:
            p2c = Promo2ContractType(
                promo=promo, discount=discount, contract_type=ct
            )
            p2c.save()
        return promo


def get_all_promos():
    count = 0
    for promo in Promo.objects.all():
        print(
            'promo: ' + str(promo.promo_str),
            'start_date: ' + str(promo.start),
            'stop_date: ' + str(promo.stop),
            'used_times: ' + str(promo.use_count),
            'is_limited: ' + str(promo.use_count_max),
            '---------------',
            sep='\n'
        )
        print()
        count += 1
    print('Promos total', count)


@api_view(http_method_names=['GET'])
def get_all_promos_api(request):
    count = 0

    promo_dict = {}
    for promo in Promo.objects.all():
        promo_dict[promo.promo_str] = {
            'promo': str(promo.promo_str),
            'start_date': str(promo.start),
            'stop_date': str(promo.stop),
            'used_times': str(promo.use_count),
            'is_limited': str(promo.use_count_max)
        }
        count += 1
    promo_dict['total'] = count

    return Response(promo_dict)
