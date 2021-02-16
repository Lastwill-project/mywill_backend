from .order_limited import *


def get_eth_balance(wallet_address) -> Wei:
    """Get the balance of ETH in a wallet."""
    return w3.eth.getBalance(wallet_address)


def get_rbc_balance(wallet_address) -> Wei:
    """
    return user rbc balance on wallet on rbc
    """
    rubic_abi = get_abi_by_filename("rubic_abi.json")
    contract = w3.eth.contract(address=RUBIC_ADDRESS, abi=rubic_abi)
    return contract.functions.balanceOf(wallet_address).call()


def deadline() -> int:
    """Get a predefined deadline. 10min by default (same as the Uniswap SDK)."""
    return int(time.time()) + 10 * 60


def addr_to_str(a: AddressLike) -> str:
    if isinstance(a, bytes):
        # Address or ChecksumAddress
        addr: str = Web3.toChecksumAddress("0x" + bytes(a).hex())
        return addr
    elif isinstance(a, str):
        if a.startswith("0x"):
            addr = Web3.toChecksumAddress(a)
            return addr


def get_tx_params(value: Wei = Wei(0), gas: Wei = Wei(250000)) -> TxParams:
    """Get generic transaction parameters."""
    return {
        "from": addr_to_str(WALLET_ADDRESS),
        "value": value,
        "gas": gas,
        "nonce": w3.eth.getTransactionCount(WALLET_ADDRESS),
    }


#----------расчет кол-ва токенов на отправку-------------
def get_eth_token_output_price(
        quantity_in_wei: int,
        token_address: AddressLike,
) -> Wei:
    """Public price for ETH to token trades with an exact output."""
    abi = get_abi_by_filename("uniswap_router02_abi.json")
    contract = w3.eth.contract(address=UNISWAP_ROUTER02_ADDRESS, abi=abi)
    function_get_price = contract.get_function_by_name("getAmountsIn")

    address: ChecksumAddress = contract.functions.WETH().call()

    price = function_get_price(quantity_in_wei, [address, token_address]).call()[0]
    return price


def get_token_eth_output_price(
        token_address: AddressLike,
        quantity_in_wei: Wei
) -> int:
    """Public price for token to ETH trades with an exact output."""
    # Если зотим получить на выходе 1 эфир то нужно закинуть не менее output рубиков
    abi = get_abi_by_filename("uniswap_router02_abi.json")
    contract = w3.eth.contract(address=UNISWAP_ROUTER02_ADDRESS, abi=abi)
    function_get_price = contract.get_function_by_name("getAmountsIn")

    address: ChecksumAddress = contract.functions.WETH().call()

    price = function_get_price(quantity_in_wei, [token_address, address]).call()[0]

    return price


#----------обмен высчитанных токенов------------------
def eth_to_token_swap_output(
    output_token: AddressLike,
    qty: int,
    recipient: Optional[AddressLike]
) -> HexBytes:
    """Convert ETH to tokens given an output amount."""

    if recipient is None:
        recipient = WALLET_ADDRESS
    eth_qty = get_eth_token_output_price(token_address=output_token, quantity_in_wei=qty)

    # get swap function from contract
    router_abi = get_abi_by_filename("uniswap_router02_abi.json")
    router_contract = w3.eth.contract(address=UNISWAP_ROUTER02_ADDRESS, abi=router_abi)
    swap_func = router_contract.functions.swapETHForExactTokens

    return build_and_send_tx(
        swap_func(
            qty,
            [ETH_ADDRESS, RUBIC_ADDRESS],
            recipient,
            deadline(),
        ),
        get_tx_params(eth_qty),
    )


def token_to_eth_swap_output(
    input_token: AddressLike, qty: Wei, recipient: Optional[AddressLike]
) -> HexBytes:
    """Convert tokens to ETH given an output amount."""
    cost = get_token_eth_output_price(input_token, qty)
    max_tokens = int((1 + MAX_SLIPPAGE) * cost)

    router_abi = get_abi_by_filename("uniswap_router02_abi.json")
    router_contract = w3.eth.contract(address=UNISWAP_ROUTER02_ADDRESS, abi=router_abi)
    swap_func = router_contract.functions.swapTokensForExactETH

    return build_and_send_tx(
        swap_func(
            qty,
            max_tokens,
            [input_token, ETH_ADDRESS],
            RUBIC_ADDRESS,
            deadline(),
        ),
    )


def build_and_send_tx(
    function: ContractFunction, tx_params: Optional[TxParams] = None
    ) -> HexBytes:

    """Build and send a transaction."""
    if not tx_params:
        tx_params = get_tx_params()
    transaction = function.buildTransaction(tx_params)
    signed_txn = w3.eth.account.sign_transaction(
        transaction, private_key=PRIVATE_KEY
    )
    return w3.eth.sendRawTransaction(signed_txn.rawTransaction)


# test
# gg = int(1*BLOCKCHAIN_DECIMALS)
# print(get_eth_token_output_price(quantity_in_wei=gg, token_address=RUBIC_ADDRESS))
# print(get_token_eth_output_price(quantity_in_wei=gg, token_address=RUBIC_ADDRESS))