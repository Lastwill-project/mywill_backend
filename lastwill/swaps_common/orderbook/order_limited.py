import requests
import logging

from typing import Union
from django.db.models.query import QuerySet
from django.db.models import Q
from gql import Client, gql
from gql.transport.requests import RequestsHTTPTransport
from web3.contract import Contract

from .models import OrderBookSwaps
from .working_with_uniswap import (
    Web3,
    HexBytes, addr_to_str,

    approve,
    build_and_send_tx,
    get_tx_params,
    is_approved,
    eth_to_token_swap_output,
    get_eth_balance,
    get_eth_token_output_price,
    get_rbc_balance,
    get_token_eth_output_price,
    load_contract,
    token_to_eth_swap_output,

    AddressLike,
    Wei,
    w3,
    # TEST_WALLET_ADDRESS,
)


ETHERSCAN_API = "https://api.etherscan.io/api"
ETHERSCAN_API_KEY = "D8QKZPVM9BMRWS7BY41RU9EKU2VMWT8PM5"
UNISWAP_API = "https://api.thegraph.com/subgraphs/name/uniswap/uniswap-v2"
UNISWAP_RBC_ETH_CONTRACT_ADDRESS = "0x10db37f4d9b3bc32AE8303B46E6166F7e9652d28"

INFURA_URL = 'https://mainnet.infura.io/v3/519bcee159504883ad8af59830dec2bb'
WALLET_ADDRESS = '0xfCf49f25a2D1E49631d05614E2eCB45296F26258'
OLD_MAINNET_CONTRACT_ADDRESS = '0xAAaCFf66942df4f1e1cB32C21Af875AC971A8117'
NEW_KOVAN_ADDRESS = "0xB09fe422dE371a86D7148d6ED9DBD499287cc95c"
RUBIC_ADDRESS = "0xA4EED63db85311E22dF4473f87CcfC3DaDCFA3E3"
ETH_ADDRESS = "0x0000000000000000000000000000000000000000"
BLOCKCHAIN_DECIMALS = 10 ** 18
MIN_BALANCE_PARAM = 1
MAX_SLIPPAGE = 0.1
PRIVATE_KEY = "0x00"
UNISWAP_ROUTER02_ADDRESS = "0x7a250d5630B4cF539739dF2C5dAcb4c659F2488D"

BLOCKCHAIN_DECIMALS = 10 ** 18
DEFAULT_ETH_MAINNET_CONTRACT_ADDRESS = '0xf954ddfbc31b775baaf245882701fb1593a7e7bc'
DEFAULT_GAS_LIMIT = 250000
DEFAULT_NETWORK_ID = 1
ETHERSCAN_API_URL = "https://api.etherscan.io/api"
ETHERSCAN_API_KEY = "D8QKZPVM9BMRWS7BY41RU9EKU2VMWT8PM5"
ORDERBOOK_CONTRACT_ABI = 'orderbook_contract_abi.json'
# MIN_BALANCE_PARAM = 1
# MAX_SLIPPAGE = 0.1
# PRIVATE_KEY = "0x00"
LIQUIDITY_PULL_ADDRESS = 'fill_me'
GAS_FEE = 'fill_me'
PROFIT_RATIO = 0.15
# ORDER_FEE = 0.015
ORDER_FEE = 0.02
UNISWAP_API = 'https://api.thegraph.com/subgraphs/name/uniswap/uniswap-v2'
ERC20_CONTRACT_ABI = 'erc20.json'


def get_rbc_eth_ratio_uniswap():
    """
        Parse exchange rate rbc to eth from uniswap.
        Return exchange rate(float type).
    """

    # Select your transport with a defined url endpoint
    transport = RequestsHTTPTransport(url=UNISWAP_API)

    # Create a GraphQL client using the defined transport
    client = Client(transport=transport, fetch_schema_from_transport=True)

    # Provide a GraphQL query
    query = gql(
        """
        {
            token(id: "%s"){
               name
               symbol
               decimals
               derivedETH
               tradeVolumeUSD
               totalLiquidity
            }
        }
        """ % RUBIC_ADDRESS
    )

    # Execute the query on the transport
    result = client.execute(query)
    return float(result.get("token").get("derivedETH"))


def _get_active_orders():
    """
        Returns public active orders.
    """
    return OrderBookSwaps.public_active_orders.all()


def _get_matching_orders(
    queryset: QuerySet,
    base_token_address,
    quote_token_address,
    network,
    contract_address,
    matching_value=5,
    # кол-во рубиков в эфире.
):
    """
        Returns orders filtered by the amount.
    """
    return queryset.filter(
        Q(
            base_address=base_token_address,
            base_limit__lte=matching_value,
            network=network,
            # contract_address=contract_address,
            # base_amount_contributed=base_limin
        ) | \
        Q(
            quote_address=quote_token_address,
            quote_limit__lte=matching_value,
            network=network,
            # contract_address=contract_address,
            # base_amount_contributed=base_limin
        )
    )


def _get_profitability_order(
    base_token_address,
    quote_token_address,
    network_id,
    contract_address,
):
    """

    """
    # Проверка сделки на доходность.
    # - Получаем текущий курс RBC в ETH c UniSwap'а.
    # - Если сделка выгодна по текущему курсу обмениваемого токена, то
    # скрываем сделку и отправляем ее на исполнение.
    #   # - Проверяем доступный остаток средств для закрытия сделки.
    #   #   - Если доступного остатка на кошельке обмениваемого токена
    #   #     не достаточно для совершения сделки, то проверяем
    #   #     доступный остаток исходного токена, для обмена
    #   #   - Если средств RBC и ETH недоставточно, то записываем в
    #   #     logging.warning ссобщение о недостаточности средств (и для
    #   #     обмена между собой) и выходим из функции со статусом 0.
    # - Если сделка НЕ выгодна по текущему курсу обмениваемого токена,
    # то пропускаем (удаляем из плученного пула?).


    # TODO: переименовать под более подхдящее имя, потому что в сделках могут
    # участвовать не только эфир и рубик.
    active_eth_rbc_orders = _get_matching_orders(
        queryset=_get_active_orders(),
        base_token_address=base_token_address,
        quote_token_address=base_token_address,
        network=network_id,
        contract_address=contract_address,
        # TODO: передать предельную сумму в эфире (до 5 включительно)
        # и обмениваемого токена эквивателнтного до 5 эфира по текущему курсу.
    )
    matching_order_count = active_eth_rbc_orders.count()

    # eth_currency_quote = ''
    # rbc_currency_quote = ''

    # eth_current_balance = get_eth_balance(LIQUIDITY_PULL_ADDRESS)
    # rbc_current_balance = get_rbc_balance(LIQUIDITY_PULL_ADDRESS)

    profitable_orders = []
    result = {
        'total': matching_order_count,
        'profitable_orders': 0,
    }


    if active_eth_rbc_orders.exists():
        print(
            f'Matching orders have been found is: {matching_order_count}.'
        )
        logging.info(
            f'Matching orders have been found is: {matching_order_count}.'
        )

        rbc_eth_ratio = _get_rbc_eth_ratio()
        gas_fee = get_gas_price() * int(DEFAULT_GAS_LIMIT)

        # for counter, order in enumerate(active_eth_rbc_orders):
        for _, order in enumerate(active_eth_rbc_orders):

            if (
                order.base_address == RUBIC_ADDRESS and \
                order.quote_address == ETH_ADDRESS
            ):
                if not _check_profitability(
                    exchange_rate=rbc_eth_ratio,
                    gas_fee=gas_fee,
                    rbc_value=float(order.base_limit),
                    eth_value=float(order.quote_limit),
                    is_rbc=True
                ):
                    # print(f'{counter}. NOUP...')
                    continue

                # print(f'{counter}. YEP!')
                result['profitable_orders'] += 1
                profitable_orders.append(order.id)

                _hide_order(order)
            elif (
                order.base_address == quote_token_address and \
                order.quote_address == base_token_address
            ):
                if not _check_profitability(
                    exchange_rate=rbc_eth_ratio,
                    gas_fee=gas_fee,
                    rbc_value=float(order.base_limit),
                    eth_value=float(order.quote_limit),
                    is_rbc=False
                ):
                    # print(f'{counter}. NOUP...')
                    continue

                # print(f'{counter}. YEP!')
                result['profitable_orders'] += 1
                profitable_orders.append(order.id)
            else:
                continue

        print(result)

        # print(
        #     profitable_orders,
        #     active_eth_rbc_orders.filter(id__in=profitable_orders).count(),
        #     active_eth_rbc_orders.filter(id__in=profitable_orders),
        #     sep='\n'
        # )

        return active_eth_rbc_orders.filter(id__in=profitable_orders)

    print('No active "ETH <> RBC" or "RBC <> ETH" orders yet.')
    logging.info('No active "ETH <> RBC" or "RBC <> ETH" orders yet.')

    return 0


def _hide_order(order: QuerySet):
    """
        Changes order visiblity to False.
    """
    order.is_displayed=False
    order.save()

    return 1


def _set_done_status_order(order: QuerySet):
    """
        Changes order visibility to True and state to 'done'.
    """
    order.state=OrderBookSwaps.STATE_DONE
    order.is_displayed=True
    order.save()

    return 1


def _get_rbc_eth_ratio():
    """
        Parse exchange rate rbc to eth from UniSwap.
        Return exchange rate: float.
    """

    # Select your transport with a defined url endpoint
    # transport = AIOHTTPTransport(url=UNISWAP_API)
    transport = RequestsHTTPTransport(url=UNISWAP_API)

    # Create a GraphQL client using the defined transport
    client = Client(transport=transport, fetch_schema_from_transport=True)

    # Provide a GraphQL query
    query = gql(
        """
        {
            token(id: "%s"){
               name
               symbol
               decimals
               derivedETH
               tradeVolumeUSD
               totalLiquidity
            }
        }
        """ % RUBIC_ADDRESS
    )

    # Execute the query on the transport
    result = client.execute(query)

    return float(result.get("token").get("derivedETH"))


def get_gas_price() -> int:
    """
        Get gas price from etherscan api.
        Returns gas price for average speed : int.
    """

    response = requests.get(
        "{url}?module=gastracker&action=gasoracle&apikey={api_key}".format(
            url=ETHERSCAN_API_URL,
            api_key=ETHERSCAN_API_KEY,
            # api_key='123',
        )
    ) \
    .json()

    try:
        result = int(response['result']['FastGasPrice'])

        return result
    except (KeyError, Exception):
        logging.warning(
            f'Unable to get gas from Etnerscan.io.\nDescription: \n{response}.'
        )
        print(
            f'Unable to get gas from Etnerscan.io.\nDescription: \n{response}.'
        )


def _check_profitability(
    exchange_rate:float,
    gas_fee:float,
    rbc_value:float,
    eth_value:float,
    is_rbc:bool=True
):
    # profit_coeff - value in ETH showing the minimum profit for which a transaction can be carried out
    """
        Calculate profit for active orderbook. Returns True if order is
        profitable or False if it isn't.

        RinE = RBC*exch_rate = value RBC in ETH
        RinE - ETH = free profit
        RinE - ETH - gas = total profit
        Total: rbcValue*exchangeRate - ethValue - gasPrice

        Logic:
        If we have RBC we want that: user's ETH > our RBC*ExchRate
            (ETH - RBC*ER) - GP - PC > 0
        If we have ETH we want that: user's RBC*ExchRate > our ETH
            (RBC*ER - ETH) - GP - PC > 0
        value isRBC: int =1 if we have RBC, int = -1 if we have ETH

        Finally we get:
        is_rbc * ((eth_value - rbc_value * exchange_rate) * BLOCKCHAIN_DECIMALS) - gas_fee - (PROFIT_RATIO * BLOCKCHAIN_DECIMALS) + ORDER_FEE > 0 - it's profit

        Input data: rbc/eth exchange rate, gasPrice,
            orderbook's value of eth and rbc, isRBC
        Output data: True if profit, False if not.
    """
    if not is_rbc:
        is_rbc = -1
    else:
        is_rbc = int(is_rbc)

    profitability = is_rbc * ((eth_value - rbc_value * exchange_rate) \
                    * BLOCKCHAIN_DECIMALS) - gas_fee \
                    - (PROFIT_RATIO * BLOCKCHAIN_DECIMALS) + ORDER_FEE

    if profitability > 0:
        return True
    else:
        return False


def swap_token_on_uniswap(input_token: AddressLike,
                          output_token: AddressLike,
                          qty: Union[int, Wei],
                          recipient: AddressLike = None
                          ) -> HexBytes:
    """
        Make a trade by defining the qty of the output token.
        Input is address of swapped tokens and exact amount of output token.
    """
    # TODO: now it works only for ETH->TOKEN and TOKEN->ETH swaps
    #  needed to add TOKEN->TOKEN swap ability
    if not is_approved(RUBIC_ADDRESS):
        approve(RUBIC_ADDRESS)

    if input_token == Web3.toChecksumAddress(ETH_ADDRESS):
        balance = get_eth_balance(WALLET_ADDRESS)
        need = get_eth_token_output_price(token_address=output_token, quantity_in_wei=qty)
        print("balance: ", balance, " need: ", need)
        if balance < need:

            # TODO: add logging "not enough eth token"
            pass
        else:
            return eth_to_token_swap_output(output_token, qty, recipient)

    elif output_token == Web3.toChecksumAddress(ETH_ADDRESS):

        # balance = get_rbc_balance(WALLET_ADDRESS)
        # need = get_token_eth_output_price(output_token, qty)
        # if balance < need:
        #     # TODO: add logging "not enough eth token"
        #     pass
        # else:
        qty = Wei(qty)
        return token_to_eth_swap_output(input_token, qty)


def _confirm_orders(
    orders: QuerySet,
    base_token_address,
    quote_token_address
):
    """
    make transaction great again!
    """
    eth_to_rbc_orders = orders.filter(base_address=base_token_address)
    rbc_to_eth_orders = orders.filter(base_address=quote_token_address)

    # TODO: Надо паралеллить?
    for _, order in enumerate(eth_to_rbc_orders):
        # RBC -> ETH
        rbc_eth_ratio = get_eth_token_output_price(
            RUBIC_ADDRESS,
            Wei(order.qoute_limit * BLOCKCHAIN_DECIMALS),
        )
        gas_fee = get_gas_price() * int(DEFAULT_GAS_LIMIT)

        if _check_profitability(
            rbc_eth_ratio,
            gas_fee,
            rbc_value=float(order.base_limit),
            eth_value=float(order.quote_limit),
            is_rbc=True
        ):
            swap_token_on_uniswap(
                w3.toChecksumAddress(order.base_address),
                w3.toChecksumAddress(order.qoute_address),
                qty=Wei(order.qoute_limit * BLOCKCHAIN_DECIMALS)
            )
            _complete_order(order)
        ...

    for _, order in enumerate(rbc_to_eth_orders):
        # ETH -> RBC
        # !--- TODO: needs refactor.
        eth_rbc_ratio = get_token_eth_output_price(
            ETH_ADDRESS,
            Wei(order.qoute_limit * BLOCKCHAIN_DECIMALS),
        ) # Returns RBC token, not ETH.
        eth_rbc_ratio = eth_rbc_ratio * get_rbc_eth_ratio_uniswap()
        # ---
        gas_fee = get_gas_price() * int(DEFAULT_GAS_LIMIT)

        if _check_profitability(
            eth_rbc_ratio,
            gas_fee,
            rbc_value=float(order.base_limit),
            eth_value=float(order.quote_limit),
            is_rbc=False

        ):
            swap_token_on_uniswap(
                w3.toChecksumAddress(order.base_address),
                w3.toChecksumAddress(order.qoute_address),
                qty=Wei(order.qoute_limit * BLOCKCHAIN_DECIMALS)
            )
            _complete_order(order)
        ...

    # for _, order in enumerate(rbc_to_eth_orders):
    #     confirm_orderbook(order)
    #     ...


def main(
    base_token_address=ETH_ADDRESS,
    quote_token_address=RUBIC_ADDRESS,
    network_id=DEFAULT_NETWORK_ID,
    contract_address=DEFAULT_ETH_MAINNET_CONTRACT_ADDRESS,
):
    """
        Fill me.
    """
    # Получили все подходящие сделки.
    # Разбили на два набора: из 1 во 2, и из 2 во 1.
    # Отправили два набора сделок на выполнение (надо распаралеллить?).

    orders = _get_profitability_order(
        base_token_address=base_token_address,
        quote_token_address=quote_token_address,
        network_id=network_id,
        contract_address=contract_address,
    )

    if not orders:
        return 0

    # TODO: добавить проверку зааппрувлен ли кошелек.
    # approve(
    #     token=Web3.toChecksumAddress(
    #         RUBIC_ADDRESS
    #     ),
    #     max_approval=int(f'0x{64 * "f"}', 16),
    #     contract_address=Web3.toChecksumAddress(
    #         DEFAULT_ETH_MAINNET_CONTRACT_ADDRESS
    #     ),
    # )

    _confirm_orders(
        orders,
        base_token_address,
        quote_token_address
    )

    return 1


def _complete_order(order:QuerySet=None):
    """
        Переводит токены на адрес контракта.
    """
    # print(transaction)
    # approve tokens (build tx, sign tx, send tx)
    # timeout
    # func call
    # build tx
    # sign tx
    # send tx
    TEST_HASH = '0x79bd92a8d9b27eac4dc52d7b5aef67e97534868f7b9797018f9805d8ab863a44'
    TEST_AMOUNT = float('1422.32415256')

    orderbook_contract = load_contract(
        ORDERBOOK_CONTRACT_ABI,
        Web3.toChecksumAddress('0xf954DdFbC31b775BaaF245882701FB1593A7e7BC'),
    )

    # `deposit`: ['deposit(bytes32,address,uint256)']
    transaction = orderbook_contract.functions.deposit(
        TEST_HASH,
        w3.toChecksumAddress(RUBIC_ADDRESS),
        w3.toWei(TEST_AMOUNT, unit='ether'),
    )

    # TODO: подключить кошелек?
    # ValueError: {'code': 3, 'data': '0x08c379a00000000000000000000000000000000000000000000000000000000000000020000000000000000000000000000000000000000000000000000000000000002f53776170733a20416c6c6f77616e63652073686f756c64206265206e6f74206c65737320746 8616e20616d6f756e740000000000000000000000000000000000', 'message': 'execution reverted: Swaps: Allowance should be not less  than amount'}

    print(
        TEST_HASH,
        w3.toChecksumAddress(RUBIC_ADDRESS),
        w3.toWei(TEST_AMOUNT, unit='ether'),
        sep='\n~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~\n'
    )

    # tx_params = {
    #     "from": w3.toChecksumAddress(TEST_WALLET_ADDRESS),
    #     'to': w3.toChecksumAddress(DEFAULT_ETH_MAINNET_CONTRACT_ADDRESS),
    #     "value": w3.toWei(TEST_AMOUNT, unit='ether'),
    # }

    # gas = w3.eth.estimateGas(tx_params)

    # tx_config = {
    #     "from": w3.toChecksumAddress(TEST_WALLET_ADDRESS),
    #     'to': w3.toChecksumAddress(DEFAULT_ETH_MAINNET_CONTRACT_ADDRESS),
    #     "value": w3.toWei(TEST_AMOUNT, unit='ether'),
    #     # "gas": gas,
    #     "gas": 250000,
    #     'gasPrice': w3.eth.gasPrice,
    #     "nonce": w3.eth.getTransactionCount(TEST_WALLET_ADDRESS),
    # }

    tx_config = get_tx_params(w3.toWei(TEST_AMOUNT, unit='ether'))

    print(tx_config)

    build_and_send_tx(
        transaction,
        tx_params=tx_config
    )
