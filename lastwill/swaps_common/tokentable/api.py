import json

from django.core.files.base import ContentFile
from requests import Session
from rest_framework.decorators import api_view
from rest_framework.response import Response
from rest_framework.status import HTTP_200_OK, HTTP_404_NOT_FOUND

from lastwill.swaps_common.tokentable.models import (
    CoinGeckoToken,
    Tokens,
    TokensCoinMarketCap,
)
from lastwill.contracts.models import *
from lastwill.settings import (
    DEFAULT_IMAGE_LINK,
    COINMARKETCAP_API_KEYS,
    MY_WISH_URL,
    RUBIC_EXC_URL
)


def add_eth_for_test(result):
    t = Tokens.objects.get(token_short_name='ETH')
    result.append({
        'address': t.address,
        'token_name': t.token_name,
        'token_short_name': t.token_short_name,
        'decimals': t.decimals,
        'image_link': t.image_link
    })
    return result


def get_test_tokens(token_name=None, token_short_name=None, address=None):
    token_list = ContractDetailsToken.objects.all().exclude(contract__state__in=('CREATED', 'POSTPONED'))
    result = []
    if token_short_name:
        if token_short_name == 'ETH':
            result = add_eth_for_test(result)
        else:
            token_list = token_list.filter(
                token_short_name__startswith=token_short_name.upper())

    if token_name:
        token_list = token_list.filter(token_name__istartswith=token_name)

    if address:
        if address == '0x0000000000000000000000000000000000000000':
            result = add_eth_for_test(result)
        token_list = token_list.filter(eth_contract_token__address=address.lower())

    for t in token_list:
        result.append({
            'address': t.eth_contract_token.address,
            'token_name': t.token_name,
            'token_short_name': t.token_short_name,
            'decimals': t.decimals,
            'image_link': DEFAULT_IMAGE_LINK
        })
    return result


@api_view()
def get_all_tokens(request):
    host = request.META['HTTP_HOST']
    token_short_name = request.query_params.get('token_short_name', None)
    token_name = request.query_params.get('token_name', None)
    address = request.query_params.get('address', None)

    if 'dev' in host.lower():
        result = get_test_tokens(token_name, token_short_name, address)
        return Response(result)

    token_list = Tokens.objects.all()
    if token_short_name:
        token_list = token_list.filter(
            Q(token_short_name__icontains=token_short_name.upper()) | Q(token_name__icontains=token_short_name.lower())
        )

    if address:
        token_list = token_list.filter(address=address.lower())

    result = []
    results_count = 20
    for t in token_list:
        result.append({
            'address': t.address,
            'token_name': t.token_name,
            'token_short_name': t.token_short_name,
            'decimals': t.decimals,
            'image_link': t.image_link
        })
        results_count -= 1

        if results_count == 0:
            break
    return Response(result)


@api_view()
def get_standarts_tokens(request):
    tokens_all = Tokens.objects.all()
    token_list = tokens_all.filter(token_short_name__in=[
        'BNB', 'MKR', 'CRO', 'BAT', 'USDC', 'OMG', 'TUSD', 'LINK', 'ZIL', 'HOT'
    ])

    result = []
    for t in token_list:
        result.append({
            'address': t.address,
            'token_name': t.token_name,
            'token_short_name': t.token_short_name,
            'decimals': t.decimals,
            'image_link': t.image_link
        })
    return Response(result)


@api_view()
def get_all_coinmarketcap_tokens(request):
    tokens = get_cmc_tokens(request)
    return Response(tokens)


def get_cmc_tokens(request):
    serve_url = MY_WISH_URL
    if 'HTTP_REFERER' in request.META:
        scheme_part = request.META['HTTP_REFERER'][5:]
        if scheme_part[-1] == ':':
            scheme = 'http'
        else:
            scheme = 'https'
            serve_url = RUBIC_EXC_URL
    elif request.META['HTTP_HOST'] == RUBIC_EXC_URL:
        scheme = 'https'
        serve_url = RUBIC_EXC_URL
    else:
        scheme = request.scheme


    token_list = []
    token_objects = TokensCoinMarketCap.objects.all()

    for t in token_objects:
        token_list.append({
            'cmc_id': t.token_cmc_id,
            'mywish_id': t.id,
            'token_name': t.token_name,
            'token_short_name': t.token_short_name,
            'platform': t.token_platform,
            'address':  t.token_address,
            'image_link': '{}://{}{}'.format(scheme, serve_url, t.image.url),
            'rank': t.token_rank,
            'rate': t.token_price
        })

    return token_list


def put_image_names():
    c = 0
    for i in TokensCoinMarketCap.objects.all():
        image_name = i.image_link.split('/')[-1]
        i.image.save(name=image_name, content=ContentFile(requests.get(i.image_link).content))
        i.save()
        c += 1
        print(c, i.image, flush=True)


def get_cmc_token_by_id(token_mywish_id):
    return TokensCoinMarketCap.objects.filter(id=token_mywish_id).first()


@api_view(http_method_names=['GET'])
def get_coins_rate(request):
    id1 = request.GET.get('id1')
    id2 = request.GET.get('id2')
    url = 'https://pro-api.coinmarketcap.com/v1/cryptocurrency/quotes/latest'
    headers = {
        'Accepts': 'application/json',
        'X-CMC_PRO_API_KEY': COINMARKETCAP_API_KEYS[1],
    }
    session = Session()
    try:
        session.headers.update(headers)
        response = session.get(url, params={'id': str(id1) + ',' + str(id2)})
    except KeyError as e:
        print('API key reached limit. Using other API key.', e, flush=True)
        session.headers.update(headers.update({'X-CMC_PRO_API_KEY': COINMARKETCAP_API_KEYS[1]}))
        response = session.get(url, params={'id': str(id1) + ',' + str(id2)})

    data = json.loads(response.text)

    return Response({'coin1': data['data'][str(id1)]['quote']['USD']['price'],
                     'coin2': data['data'][str(id2)]['quote']['USD']['price']})


@api_view()
def get_coingecko_tokens(request):
    """
    Возвращает список актуальных токенов CoinGecko.

    ---

    Принимаемые параметры:
    - request
    """
    coingecko_tokens = get_actual_coingecko_tokens(request)

    if not coingecko_tokens:
        return get_response('No coingecko tokens.', HTTP_404_NOT_FOUND)

    return get_response(
        data_to_response={
            'total': len(coingecko_tokens),
            'tokens': coingecko_tokens,
        }
    )


def get_response(data_to_response, status_to_response=HTTP_200_OK):
    """
    Возвращает объект Response.

    ---

    Принимаемые параметры:
    - data_to_response : Any
    - status_to_response : int, по-умолчанию - 200
    """
    return Response(
        data=data_to_response,
        status=status_to_response,
    )


def get_actual_coingecko_tokens(request):
    serve_url = MY_WISH_URL
    if 'HTTP_REFERER' in request.META:
        scheme_part = request.META['HTTP_REFERER'][5:]
        if scheme_part[-1] == ':':
            scheme = 'http'
        else:
            scheme = 'https'
            serve_url = RUBIC_EXC_URL
    elif request.META['HTTP_HOST'] == RUBIC_EXC_URL:
        scheme = 'https'
        serve_url = RUBIC_EXC_URL
    else:
        scheme = request.scheme

    token_list = []
    coingecko_tokens = CoinGeckoToken.objects \
                       .filter(
                           platform__in=[
                               'ethereum',
                               'binance-smart-chain',
                           ],
                           is_displayed=True,
                        ) \
                       .order_by('short_title')

    if coingecko_tokens.exists():
        for token in coingecko_tokens:
            token_list.append({
                'token_title': token.title,
                'token_short_title': token.short_title.upper(),
                'coingecko_id': token.coingecko_id,
                'platform': token.platform,
                'address':  token.address,
                'decimals': token.decimals,
                'image_link': '{}://{}{}'.format(
                    scheme,
                    serve_url,
                    token.image_file.url
                ),
                'coingecko_rank': token.rank,
                'usd_price': token.usd_price,
            })

    return token_list
