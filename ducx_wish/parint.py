#!/usr/bin/env python3
import json
import requests
import sys
from ducx_wish.settings import NETWORKS


class InterfaceConnectExc(Exception):
    def __init__(self, name, *args):
        if not name:
            name = 'interface'
        self.value = 'can not connect to %s' % name

    def __str__(self):
        return self.value


class InterfaceErrorExc(Exception):
    pass


class ParConnectExc(InterfaceConnectExc):
    def __init__(self, *args):
        super().__init__(name='parity')


class ParErrorExc(InterfaceErrorExc):
    pass


class ParInt:
    def __init__(self, network=None):
        if network is None:
            if len(sys.argv) > 1 and sys.argv[1] in NETWORKS:
                network = sys.argv[1]
            else:
                network = 'ETHEREUM_MAINNET'
        print('network', network, type(network))
        self.addr = NETWORKS[network]['host']
        self.port = NETWORKS[network]['port']
        print('parity interface', self.addr, self.port, flush=True)

    def __getattr__(self, method):
        def f(*args):
            arguments = {
                    'method': method,
                    'params': args,
                    'id': 1,
                    'jsonrpc': '2.0',
            }
            try:
                temp = requests.post(
                        'http://{}:{}/'.format(self.addr, self.port),
                        json=arguments,
                        headers={'Content-Type': 'application/json'}
                )
            except requests.exceptions.ConnectionError as e:
                raise ParConnectExc()
            print('raw response', temp.content, flush=True)
            result = json.loads(temp.content.decode())
            if result.get('error'):
                raise ParErrorExc(result['error']['message'])
            return result['result']
        return f


class NeoInt(ParInt):
    pass


class InfuraConnectExc(InterfaceConnectExc):
    def __init__(self, *args):
        super().__init__(name='infura')


class InfuraErrorExc(InterfaceErrorExc):
    pass


class InfuraInt:
    def __init__(self, network=None):
        if network is None:
            if len(sys.argv) > 1 and sys.argv[1] in NETWORKS:
                network = sys.argv[1]
            else:
                network = 'ETHEREUM_MAINNET'
        self.infura_subdomain = NETWORKS[network]['infura_subdomain']
        self.infura_project_id = NETWORKS[network]['infura_project_id']

        self.url = 'https://{subdomain}.infura.io/v3/{proj_id}'\
            .format(
                subdomain=self.infura_subdomain,
                proj_id=self.infura_project_id
        )

        print('infura interface', self.url, flush=True)

    def __getattr__(self, method):
        def f(*args):
            arguments = {
                    'method': method,
                    'params': args,
                    'id': 1,
                    'jsonrpc': '2.0',
            }
            try:
                temp = requests.post(
                        self.url,
                        json=arguments,
                        headers={'Content-Type': 'application/json'}
                )
            except requests.exceptions.ConnectionError as e:
                raise InfuraConnectExc()
            print('raw response', temp.content, flush=True)
            result = json.loads(temp.content.decode())
            if result.get('error'):
                raise InfuraErrorExc(result['error']['message'])
            return result['result']
        return f


class EthereumProvider:

    @staticmethod
    def get_provider(network):
        provider = NETWORKS[network]['provider']

        if provider == 'infura':
            return InfuraInt(network)
        elif provider == 'parity':
            return ParInt(network)
        else:
            raise ValueError('only infura and parity supported')