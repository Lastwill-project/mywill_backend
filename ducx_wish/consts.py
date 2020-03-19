MAX_WEI_DIGITS = len(str(2**256))
MAIL_NETWORK = {
    'DUCATUSX_MAINNET': 'Ethereum',
    'DUCATUSX_TESTNET': 'Ropsten (Ethereum Testnet)',
    'RSK_MAINNET': 'RSK',
    'RSK_TESTNET': 'RSK Testnet',
    'NEO_TESTNET': 'NEO Test Net',
    'NEO_MAINNET': 'NEO',
    'EOS_MAINNET': 'EOS',
    'EOS_TESTNET': 'EOS Testnet',
    'TRON_MAINNET': 'TRON',
    'TRON_TESTNET': 'TRON Testnet',
    'WAVES_MAINNET': 'WAVES',
    'WAVES_TESTNET': 'WAVES Testnet'
}

API_NETWORK = {
    'DUCATUSX_MAINNET': 'DUCATUSX_MAINNET',
    'DUCATUSX_TESTNET': 'DUCATUSX_TESTNET',
    'RSK_MAINNET': 'BITCOIN_MAINNET',
    'RSK_TESTNET': 'BITCOIN_TESTNET',
    'NEO_TESTNET': 'NEO_MAINNET',
    'NEO_MAINNET': 'NEO_TESTNET',
    'EOS_MAINNET': 'EOS_MAINNET',
    'EOS_TESTNET': 'EOS TESTNET',
    'TRON_MAINNET': 'TRON_MAINNET',
    'TRON_TESTNET': 'TRON_TESTNET',
}

NETWORK_SUBSITE = {
    'DUCATUSX_MAINNET': 1,
    'DUCATUSX_TESTNET': 1,
    'RSK_MAINNET': 1,
    'RSK_TESTNET': 1,
    'NEO_TESTNET': 1,
    'NEO_MAINNET': 1,
    'EOS_MAINNET': 2,
    'EOS_TESTNET': 2,
    'TRON_MAINNET': 1,
    'TRON_TESTNET': 1,
}

CONTRACT_PRICE_DUC = {
    'AIRDROP': 0.5,
    'DEFFERED': 0.025,
    'ICO': 1,
    'TOKEN': 0.5,
    'TOKEN_AUTHIO': 3.5,
    'INVESTMENT_POOL': 0.5,
    'EOS_TOKEN': 2.99,
    'EOS_ICO': 5,
    'EOS_TOKEN_STANDALONE': 5,
}

CONTRACT_PRICE_EOS = {
    'EOS_TOKEN': 150,
    'EOS_ICO': 250,
    'EOS_TOKEN_STANDALONE': 190,
    'EOS_ACCOUNT': 2,
    'EOS_AIRDROP': 250
}

CONTRACT_PRICE_NEO = {
    'NO_STORAGE': 200,
    'WITH_STORAGE': 600,
}

CONTRACT_PRICE_TRON = {
    'TRON_TOKEN': 5,
    'TRON_GAME_ASSET': 0.5,
    'TRON_AIRDROP': 0.5,
}

BRAND_REPORT_PRICE = 450

CONTRACT_GAS_LIMIT = {
    'AIRDROP': 3000000,
    'DEFFERED': 1700000,
    'ICO': 3200000,
    'TOKEN': 3200000,
    'INVESTMENT_POOL': 3000000,
    'LASTWILL_PAYMENT': 50000,
    'LASTWILL_COMMON': 600000,
    'TOKEN_PROTECTOR': 3000000
}

NET_DECIMALS = {
    'DUC': 10 ** 8,
    'DUCX': 10 ** 18
}

TRON_REPLENISH_THRESHOLD = {
    'NET': 36000,
    'ENERGY': 5600000,
    'MIN_TRX': 1000000
}

URL_STATS_CURRENCY_BODY = 'https://pro-api.coinmarketcap.com/v1/cryptocurrency/quotes/latest'
URL_STATS_CURRENCY = {
    'CoinMarketCap': 'https://pro-api.coinmarketcap.com/v1/cryptocurrency/quotes/latest',
    'EOSISH': "https://api.coingecko.com/api/v3/simple/price?ids=eosish&vs_currencies=eos",
    'RUB': "https://api.cryptonator.com/api/ticker/usd-rub",
}

URL_STATS_CURRENCY_ID = {
    'MYWISH': 2236,
    'BTC': 1,
    'ETH': 1027,
    'EOS': 1765
}

URL_STATS_ETH_QUERY = 'api?module=account&action=balance&address='
URL_STATS_BALANCE = {
    'NEO': 'http://neoscan.mywish.io/api/test_net/v1/get_balance/',
    'ETH': 'https://api.etherscan.io/' + URL_STATS_ETH_QUERY,
    'ETH_ROPSTEN': 'https://api-ropsten.etherscan.io/' + URL_STATS_ETH_QUERY,
}

ETH_MAINNET_ADDRESS = '0x1e1fEdbeB8CE004a03569A3FF03A1317a6515Cf1'
ETH_TESTNET_ADDRESS = '0x88dbD934eF3349f803E1448579F735BE8CAB410D'

AVAILABLE_CONTRACT_TYPES = {
    1: [
        {'contract_type': 0, 'contract_name': 'LastWill'},
        {'contract_type': 1, 'contract_name': 'LostKey'},
        {'contract_type': 2, 'contract_name': 'DefferedPayment'},
        {'contract_type': 4, 'contract_name': 'ICO'},
        {'contract_type': 5, 'contract_name': 'Token'},
        {'contract_type': 8, 'contract_name': 'AirDrop'},
        {'contract_type': 9, 'contract_name': 'InvestmentPool'},
    ],
    2: [
        {'contract_type': 0, 'contract_name': 'LastWill'},
        {'contract_type': 1, 'contract_name': 'LostKey'},
        {'contract_type': 2, 'contract_name': 'DefferedPayment'},
        {'contract_type': 4, 'contract_name': 'ICO'},
        {'contract_type': 5, 'contract_name': 'Token'},
        {'contract_type': 8, 'contract_name': 'AirDrop'},
        {'contract_type': 9, 'contract_name': 'InvestmentPool'},
    ],
    5: [],
    6: [
        {'contract_type': 6, 'contract_name': 'Token'},
        {'contract_type': 7, 'contract_name': 'ICO'}
    ],
    10: [
        {'contract_type': 10, 'contract_name': 'Token'},
        {'contract_type': 11, 'contract_name': 'Account'},
        {'contract_type': 12, 'contract_name': 'ICO'},
        {'contract_type': 13, 'contract_name': 'AirDrop'},
        {'contract_type': 14, 'contract_name': 'TokenStandAlone'}

    ],
    11: [
        {'contract_type': 10, 'contract_name': 'Token'},
        {'contract_type': 11, 'contract_name': 'Account'},
        {'contract_type': 12, 'contract_name': 'ICO'},
        {'contract_type': 13, 'contract_name': 'AirDrop'},
        {'contract_type': 14, 'contract_name': 'TokenStandAlone'}
    ],
    14: [
        {'contract_type': 15, 'contract_name': 'Token'},
        {'contract_type': 16, 'contract_name': 'GameAsset'},
        {'contract_type': 17, 'contract_name': 'AirDrop'}

    ],
    15: [
        {'contract_type': 15, 'contract_name': 'Token'},
        {'contract_type': 16, 'contract_name': 'GameAsset'},
        {'contract_type': 17, 'contract_name': 'AirDrop'}
    ]
}

NETWORK_TYPES = {
    'testnet': [2, 4, 6, 11, 15],
    'mainnet': [1, 3, 5, 10, 14]
}

ALL_CONTRACT_STATES = [
    'ACTIVE',
    'CANCELLED',
    'CREATED',
    'DONE',
    'ENDED',
    'EXPIRED',
    'KILLED',
    'POSTPONED',
    'TRIGGERED',
    'UNDER_CROWDSALE',
    'WAITING_ACTIVATION',
    'WAITING_FOR_DEPLOYMENT',
    'WAITING_FOR_PAYMENT'
]

API_CONTRACT_PRICES = [
    {'contract_type': 0, 'contract_name': 'LastWill', 'price': 0.257 * NET_DECIMALS['DUC'], 'currency': 'DUC'},
    {'contract_type': 1, 'contract_name': 'LostKey', 'price': 0.2 * NET_DECIMALS['DUC'], 'currency': 'DUC'},
    {'contract_type': 2, 'contract_name': 'DefferedPayment', 'price': 0.025 * NET_DECIMALS['DUC'], 'currency': 'DUC'},
    {'contract_type': 4, 'contract_name': 'ICO', 'price': CONTRACT_PRICE_DUC['ICO'] * NET_DECIMALS['DUC'], 'currency': 'DUC'},
    {'contract_type': 5, 'contract_name': 'Token', 'price': CONTRACT_PRICE_DUC['TOKEN'] * NET_DECIMALS['DUC'], 'currency': 'DUC'},
    {'contract_type': 8, 'contract_name': 'AirDrop', 'price': CONTRACT_PRICE_DUC['AIRDROP'] * NET_DECIMALS['DUC'], 'currency': 'DUC'},
    {'contract_type': 9, 'contract_name': 'InvestmentPool', 'price': CONTRACT_PRICE_DUC['INVESTMENT_POOL'] * NET_DECIMALS['DUC'], 'currency': 'DUC'},
]

ETHPLORER_URL = 'http://api.ethplorer.io/getAddressInfo/{address}?apiKey={key}'
ETHPLORER_KEY = 'freekey'

ETH_ADDRESS = '0x0000000000000000000000000000000000000000'
