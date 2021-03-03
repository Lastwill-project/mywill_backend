"""
    Модуль-парсер данных об актуальных токенах, полученных из GoinGecko.

    Этапы синхронизации с базой данных токенов CoinGecko.
    - В CoinGecko запрашиваются список всех актуальных токенов.
    - В CoinGecko запрашивается данные котировок по всем токенам.
    - Полученные данные форматируются в соответствии с форматом, заданным моделью CionGeckoToken.
    - Из базы данных запрашиваются все записи о токенами. Записи сравниваются с полученным списком по полям токенов title и short title.
        - Если о токене есть НЕ скрытая запись в БД и его нет в списке актуальных токенов, то запись скрывается.
        - Если о токене есть скрытая запись в БД и он есть в списке актуальных токнов, то запись НЕ скрывается.
    - Из базы данных запрашиваются только НЕ скрытые записи о токенах.
        - Если токена нет в результате запроса в БД, то создается новая запись с этим токеном.
        - Если токен есть в результате запроса в БД, то данные о токене обновляются в БД.
    - Подгружаются иконки к каждому НЕ скрытому токену. По-умолчанию в качестве иконки токену устанавливается fa-empire.png.

"""
from decimal import Decimal, ROUND_HALF_UP
import logging
from requests import get
from time import sleep

from django.core.files.base import ContentFile

from lastwill.swaps_common.tokentable.models import (
    CoinGeckoToken,
)


def push_request(url, params=None):
    """
    Отправляет запрос на API CoinGecko.com.

    ---

    Входные параметры:
    - url : str.
    - params : dict, по-умолчанию None.

    ---

    Возвращаемое значение:
    - list
    """
    response = get(url, params)

    return response.json()


def get_actual_tokens():
    """
    Возвращает список актуальных токенов из CoinGecko.com.

    ---

    Возвращаемое значение:
    - list
    """
    target_url = 'https://api.coingecko.com/api/v3/coins/list'
    params = {
        'include_platform': 'true',
    }
    return push_request(target_url, params)


def get_coingecko_token_id(tokens, exclude_token=['thorecoin', ]):
    """
    Возвращает список идентификаторов токенов из CoinGecko.com.

    ---

    Возвращаемое значение:
    - list
    """
    # {
    #     "id": "ethereum",
    #     "symbol": "eth",
    #     "name": "Ethereum",
    #     "platforms":
    #     {
    #         "binance-smart-chain": "0x2170ed0880ac9a755fd29b2688956bd959f933f8",
    #         "huobi-token": "0x64ff637fb478863b7468bc97d30a5bf3a428a1fd"
    #     }
    # }
    coingecko_id_list = [item.get('id') for item in tokens]

    if exclude_token:
        for token in exclude_token:
            if token in coingecko_id_list:
                coingecko_id_list.pop(coingecko_id_list.index(token))

    return coingecko_id_list


def get_token_market_data(
    tokens,
    start=0,
    stop_slice=300,
    timeout=5
):
    """
    Возвращает актуальные данные по токенам из CoinGecko.com.

    ---

    Принимаемые параметры:
    - tokens : dict
    - start : int, по-умолчанию 0
    - stop_slice : int, по-умолчанию 300
    - timeout : int, по-умолчанию 5

    ---

    Возвращаемое значение:
    - dict
    """
    actual_token_id = get_coingecko_token_id(tokens)
    target_url = 'https://api.coingecko.com/api/v3/coins/markets'
    params = {
        'vs_currency': 'usd',
    }
    result = []

    while 1:
        # Здесь происходит "магия", не обращайте внимания.
        #
        # Запросы отправляются несколько раз по 300 идентификаторов,
        # ответ записывается в результирующий список.
        if stop_slice < len(actual_token_id):
            params.update({
                'ids': ','.join(actual_token_id[start:stop_slice]),
            })
            response = push_request(target_url, params)

            if 'error' in response:
                raise Exception(
                    f'\nSending the request has been failed!\nError message: "{response["error"]}".'
                )

            result += response
            start = stop_slice
            stop_slice += 300

            sleep(timeout)

            continue
        else:
            params.update({
                'ids': ','.join(actual_token_id[start:]),
            })
            result += push_request(target_url, params)

        break

    return result


def format_marketdata():
    """
    Фильтрует и форматирует данные для сохранения в базу данных.

    ---

    Возвращаемое значение - dict.

    Формат возвращаемого значения:
    {
        <token_ticker>:
        {
            <token_title> as string,
            <token_short_title> as string,
            <token_image_link> as string,
            <token_rank> as integer,
            <token_usd_price> as float
        },
        ...
    }
    """
    # Пример данных:
    # [
    #     {
    #         "id": "1337", -
    #         "symbol": "1337", as short name
    #         "name": "Elite", as repr name
    #         "image": "https://assets.coingecko.com/coins/images/686/large/EliteLogo256.png?1559143523", as image link
    #         "current_price": 0.00001408, as token price
    #         "market_cap": 415426, -
    #         "market_cap_rank": 1247, as token rank
    #         "fully_diluted_valuation": null, -
    #         "total_volume": 5.26, -
    #         "high_24h": 0.0000185, -
    #         "low_24h": 0.00001542, -
    #         "price_change_24h": -0.00000274, -
    #         "price_change_percentage_24h": -16.31284, -
    #         "market_cap_change_24h": -80975.61992168, -
    #         "market_cap_change_percentage_24h": -16.31252, -
    #         "circulating_supply": 29515041222.0315, -
    #         "total_supply": null, -
    #         "max_supply": null, -
    #         "ath": 0.00108002, -
    #         "ath_change_percentage": -98.69678, -
    #         "ath_date": "2018-01-09T00:00:00.000Z", -
    #         "atl": 2.2e-7, -
    #         "atl_change_percentage": 6281.09, -
    #         "atl_date": "2020-06-26T11:53:55.843Z", -
    #         "roi": null, -
    #         "last_updated": "2020-12-04T14:12:07.411Z" -
    #     },
    # ]

    # [
    #     {
    #         "id":"e1337",
    #         "symbol":"1337",
    #         "name":"1337",
    #         "platforms":{
    #             "ethereum": "0x35872fea6a4843facbcdbce99e3b69596a3680b8"
    #         }
    #     }
    # ]
    actual_tokens = get_actual_tokens()
    actual_token_market_data = get_token_market_data(actual_tokens, timeout=0)
    result = {}

    try:
        for _, token in enumerate(actual_tokens):
            for _, item in enumerate(actual_token_market_data):
                if token.get('id') == item.get('id'):
                    token_title = token.get('name')
                    token_short_title = token.get('symbol').lower()
                    platforms = list(token.get('platforms').keys())
                    coingecko_id = token.get('id').lower()
                    token_image_link = item.get('image')
                    token_rank = item.get('market_cap_rank')
                    token_usd_price = item.get('current_price')

                    token_data = {
                        'token_title': str(token_title),
                        'token_short_title': str(token_short_title),
                        'token_platform': str(platforms[0]) if platforms else '',
                        'token_address': str(token.get('platforms').get(platforms[0])) if platforms else '',
                        'token_coingecko_id': str(coingecko_id),
                        'token_image_link': str(token_image_link),
                        'token_rank': int(token_rank) if token_rank else 0,
                        'token_usd_price': Decimal(token_usd_price).quantize(
                            Decimal('1.0000000'), ROUND_HALF_UP
                        ) if token_usd_price else 0,
                    }
                    result.update(
                        {
                            token_data.get('token_short_title'): token_data
                        }
                    )

                    del item
    except Exception as exception_error:
        print(
            'Error in format_marketdata: {}'.format(exception_error)
        )
        return 0

    return result


def get_all_coingecko_tokens():
    """
    Возвращает объект QuerySet со всеми CoinGecko токенами.
    """
    return CoinGeckoToken.objects.all()


def get_current_coingecko_tokens():
    """
    Возвращает объект QuerySet со всеми актуальными CoinGecko токенами
    (is_displayed=True).
    """
    return CoinGeckoToken.objects.all().filter(is_displayed=True)


def get_actual_coingecko_token_list(actual_tokens: dict) -> list:
    """
    Возвращает список кортежей в формате
    [(<token_title>, <token_short_title>), ...].

    ---

    Принимаемые параметры:
    - Список токенов : dict

    ---

    Возвращаемое значение:
    - Список кортежей : list(tuple(), ...)
    """
    if not actual_tokens:
        return 0

    actual_token_list = []

    try:
        for _, actual_token in enumerate(actual_tokens):
            current_token = (
                actual_tokens.get(actual_token).get('token_title'),
                actual_tokens.get(actual_token).get('token_short_title'),
            )
            actual_token_list.append(current_token)
    except (KeyError, Exception) as exception_error:
        print(
            'Error in get_actual_coingecko_token_list: {}.'.format(
                exception_error
            )
        )
        return 0

    return actual_token_list


def refresh_token_visibility(actual_coingecko_token_list: list):
    """
    Обновляет видимость CoinGecko токенов в базе данных.

    ---

    Принимаемые параметры:
    - Список токенов coingecko_short_titles : list

    ---

    Возвращаемое значение:
    - ...

    """
    if not actual_coingecko_token_list:
        return 0

    current_tokens = get_all_coingecko_tokens().exclude(is_native=True)
    current_tokens.update(is_displayed=True)

    # TODO: Подумать над реализацией. Не рационально отправлять 6К+ запросов
    # в БД. Нужно собрать записи, которые не попали по фильру и одним запросом
    # обновить им поле is_displayed на False.
    for _, token in enumerate(current_tokens):
        if (
            token.title,
            token.short_title
        ) not in actual_coingecko_token_list:
            current_tokens.filter(
                title=token.title,
                short_title=token.short_title
            ).update(is_displayed=False)

    return 1


def sync_data():
    """
    Записывает и сохраняет полученые данные в базу данных.
    """
    data_for_sync = format_marketdata()

    actual_tokens = get_actual_coingecko_token_list(data_for_sync)

    if not refresh_token_visibility(actual_tokens):
        return 0

    actual_cg_tokens = get_current_coingecko_tokens()

    logging.info(
        f'Total coingecko tokens has been founded: {len(data_for_sync)}.'
    )

    counter = 0
    # TODO: Продумать вариант с сохранением объектов порционно, а не всем
    # перечнем (6К+ записей на 4.12.2020).
    try:
        for _, actual_token in enumerate(actual_tokens):
            token_title = actual_token[0]
            token_short_title = actual_token[1]
            token = data_for_sync.get(token_short_title)

            try:
                cg_token = actual_cg_tokens.get(
                    title=token_title,
                    short_title=token_short_title
                )

                if not cg_token.is_upgradable:
                    continue

                # cg_token.platform = token.get('token_platform')
                # cg_token.address = token.get('token_address')
                cg_token.coingecko_id = token.get('token_coingecko_id')
                cg_token.source_image_link = token.get('token_image_link')
                cg_token.token_rank = token.get('token_rank')
                cg_token.token_usd_price = token.get('token_usd_price')

                cg_token.save()

                counter += 1

                logging.info(
                    '{}. Token "{} ({})" has been updated successfully.'.format(
                        counter,
                        token.get('token_title'),
                        token.get('token_short_title'),
                    )
                )
            except CoinGeckoToken.DoesNotExist:
                CoinGeckoToken.objects.create(
                    title=token.get('token_title'),
                    short_title=token.get('token_short_title'),
                    platform=token.get('token_platform'),
                    address=token.get('token_address'),
                    coingecko_id=token.get('token_coingecko_id'),
                    source_image_link=token.get('token_image_link'),
                    coingecko_rank=token.get('token_rank'),
                    usd_price=token.get('token_usd_price'),
                )

                counter += 1

                logging.info(
                    '{}. Token "{} ({})" has been added successfully.'.format(
                        counter,
                        token.get('token_title'),
                        token.get('token_short_title'),
                    )
                )
    except (TypeError, Exception) as exception_error:
        print(
            'Error in sync_data_with_db: {}'.format(exception_error)
        )
        return 0

    logging.info(
        'Total tokens has been refreshed: {}.\nToken market data has been synced at {}.'.format(
            counter,
            get_current_coingecko_tokens().last().updated_at
        )
    )

    return 1


def add_icon_to_token(
    token_queryset=get_current_coingecko_tokens(),
    timeout=0
):
    """
        Скачивает и добавляет иконку токену.
    """
    counter = 0
    for token in token_queryset:
        counter += 1
        icon_url = token.source_image_link
        icon_name = icon_url.split('/')[-1] \
                            .split('?')[0]

        if token.image_file.url.split('/')[-1] == 'fa-empire.png' and not icon_url == 'missing_large.png':
            token.image_file.save(
                name='cg_logo_{0}_{1}'.format(
                    token.short_title,
                    icon_name
                ),
                content=ContentFile(get(icon_url).content)
            )

        logging.info(
            f'{counter}. Token "{token.short_title}" icon has been added successfully.'
        )

        if timeout:
            sleep(timeout)

    return 1
