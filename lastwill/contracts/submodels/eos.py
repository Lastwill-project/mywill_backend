from threading import Timer
from subprocess import Popen, PIPE

from django.db import models
from django.utils import timezone
from django.core.mail import send_mail
from rest_framework.exceptions import ValidationError

from lastwill.consts import CONTRACT_PRICE_EOS, CONTRACT_PRICE_USDT
from lastwill.contracts.submodels.airdrop import *
from lastwill.json_templates import create_eos_json
from lastwill.rates.api import rate
from lastwill.settings import EOS_ATTEMPTS_COUNT, CLEOS_TIME_COOLDOWN, CLEOS_TIME_LIMIT


def unlock_eos_account(wallet_name, password):
    lock_command = 'cleos wallet lock -n {wallet}'.format(wallet=wallet_name)
    if os.system(
            "/bin/bash -c '{command}'".format(command=lock_command)

    ):
        raise Exception('lock command error')

    unlock_command = 'echo {password} | cleos wallet unlock -n {wallet}'.format(
        password=password, wallet=wallet_name
    )
    if os.system(
            "/bin/bash -c '{command}'".format(command=unlock_command)

    ):
        raise Exception('unlock command error')


def implement_cleos_command(command_list):
    print('command list', command_list, flush=True)
    print('raw command', ' '.join(str(x) for x in command_list), flush=True)
    stderr = None
    for attempt in range(EOS_ATTEMPTS_COUNT):
        print('attempt', attempt, flush=True)
        proc = Popen(command_list, stdin=PIPE, stdout=PIPE, stderr=PIPE)
        timer = Timer(CLEOS_TIME_LIMIT, proc.kill)
        try:
            timer.start()
            stdout, stderr = proc.communicate()
            # if attempt == EOS_ATTEMPTS_COUNT - 1:
            print('stdout', stdout.decode(), flush=True)
            print('stderr', stderr.decode(), flush=True)
        finally:
            timer.cancel()
        result = stdout.decode()
        if result:
            break
        time.sleep(CLEOS_TIME_COOLDOWN)
    else:
        print('stderr', stderr, flush=True)
        raise Exception(
            'cannot make tx with %i attempts' % EOS_ATTEMPTS_COUNT)
    if 'pack_action_data' not in command_list:
        result = json.loads(result)
    return result


class EOSContract(EthContract):
    pass


class ContractDetailsEOSToken(CommonDetails):
    token_short_name = models.CharField(max_length=64)
    admin_address = models.CharField(max_length=50)
    decimals = models.IntegerField()
    eos_contract = models.ForeignKey(
        EOSContract,
        null=True,
        default=None,
        related_name='eos_token_details',
        on_delete=models.SET_NULL
    )
    temp_directory = models.CharField(max_length=36)
    maximum_supply = models.DecimalField(
        max_digits=MAX_WEI_DIGITS, decimal_places=0, null=True
    )
    easy_token = models.BooleanField(default=True)

    def predeploy_validate(self):
        now = timezone.now()
        token_holders = self.contract.eostokenholder_set.all()
        for th in token_holders:
            if th.freeze_date:
                if th.freeze_date < now.timestamp() + 600:
                    raise ValidationError({'result': 1}, code=400)

    @classmethod
    def min_cost(cls):
        network = Network.objects.get(name='EOS_MAINNET')
        cost = cls.calc_cost({}, network)
        return cost

    @classmethod
    def min_cost_eos(cls):
        network = Network.objects.get(name='EOS_MAINNET')
        cost = cls.calc_cost_eos({}, network)
        return cost

    @staticmethod
    def calc_cost(kwargs, network):
        if NETWORKS[network.name]['is_free']:
            return 0
        return int(CONTRACT_PRICE_USDT['EOS_TOKEN'] * NET_DECIMALS['USDT'])

    @staticmethod
    def calc_cost_eos(kwargs, network):
        if NETWORKS[network.name]['is_free']:
            return 0
        return int(CONTRACT_PRICE_EOS['EOS_TOKEN'] * NET_DECIMALS['EOS'])

    def get_arguments(self, eth_contract_attr_name):
        return []

    def get_stake_params(self):
        return {
            'stake_net': '10.0000 EOS',
            'stake_cpu': '10.0000 EOS',
            'buy_ram_kbytes': 128
        }

    @blocking
    @postponable
    def deploy(self):
        wallet_name = NETWORKS[self.contract.network.name]['wallet']
        password = NETWORKS[self.contract.network.name]['eos_password']
        unlock_eos_account(wallet_name, password)
        builder = NETWORKS[self.contract.network.name]['tokensfather']
        acc_name = NETWORKS[self.contract.network.name]['address']
        if self.contract.network.name == 'EOS_MAINNET':
            eos_url = 'https://%s' % (
            str(NETWORKS[self.contract.network.name]['host']))
        else:
            eos_url = 'http://%s:%s' % (str(NETWORKS[self.contract.network.name]['host']), str(NETWORKS[self.contract.network.name]['port']))
        if self.decimals != 0:
            max_supply = str(self.maximum_supply)[:-self.decimals] + '.' + str(self.maximum_supply)[-self.decimals:]
        else:
            max_supply = str(self.maximum_supply)
        command = [
            'cleos', '-u', eos_url, 'push', 'action',
            builder, 'create',
            '["{acc_name}","{max_sup} {token}"]'.format(
                acc_name=self.admin_address,
                max_sup=max_supply,
                token=self.token_short_name
            ), '-p', acc_name, '-j'
        ]
        print('command = ', command)

        tx_hash = implement_cleos_command(command)['transaction_id']
        print('tx_hash:', tx_hash, flush=True)
        eos_contract = EOSContract()
        eos_contract.tx_hash = tx_hash
        eos_contract.address = builder
        eos_contract.contract=self.contract
        eos_contract.save()
        self.eos_contract = eos_contract
        self.save()
        self.contract.state='WAITING_FOR_DEPLOYMENT'
        self.contract.save()

    def tokenCreated(self, message):
        self.msg_deployed(message, eth_contract_attr_name='eos_contract')


class ContractDetailsEOSAccount(CommonDetails):
    owner_public_key = models.CharField(max_length=128)
    active_public_key = models.CharField(max_length=128)
    account_name = models.CharField(max_length=50)
    stake_net_value = models.CharField(default='0.01', max_length=20)
    stake_cpu_value = models.CharField(default='0.64', max_length=20)
    buy_ram_kbytes = models.IntegerField(default=4)
    eos_contract = models.ForeignKey(
        EOSContract,
        null=True,
        default=None,
        related_name='eos_account_details',
        on_delete=models.SET_NULL
    )

    @staticmethod
    def calc_cost_eos(kwargs, network):
        if NETWORKS[network.name]['is_free']:
            return 0
        if network.name == 'EOS_MAINNET':
            eos_url = 'https://%s' % (
                str(NETWORKS[network.name]['host'])
            )
        else:
            eos_url = 'http://%s:%s' % (
                str(NETWORKS[network.name]['host']),
                str(NETWORKS[network.name]['port'])
            )

        command1 = [
            'cleos', '-u', eos_url, 'get', 'table', 'eosio', 'eosio', 'rammarket'
        ]
        result = implement_cleos_command(command1)
        ram = result['rows'][0]
        ram_price = float(ram['quote']['balance'].split()[0]) / float(ram['base']['balance'].split()[0]) * 1024
        print('get ram price', flush=True)
        usdt_cost = (
                float(kwargs['buy_ram_kbytes']) * ram_price
                + float(kwargs['stake_net_value'])
                 + float(kwargs['stake_cpu_value'])
        ) * 5 + 0.3
        return round(usdt_cost, 0) * NET_DECIMALS['USDT']

    @staticmethod
    def calc_cost(kwargs, network):
        if NETWORKS[network.name]['is_free']:
            return 0
        eos_cost_base = CONTRACT_PRICE_USDT['EOS_ACCOUNT'] * NET_DECIMALS['USDT']
        eos_cost = ContractDetailsEOSAccount.calc_cost_eos(kwargs, network) / NET_DECIMALS['EOS']
        cost = eos_cost * rate('EOS', 'ETH')
        print('convert eos cost', cost, flush=True)
        converted_cost = round(cost, 2) * NET_DECIMALS['USDT']
        if converted_cost < eos_cost_base:
            final_cost = eos_cost_base
        else:
            final_cost = converted_cost
        return final_cost

    def get_arguments(self, eth_contract_attr_name):
        return []

    @classmethod
    def min_cost(cls):
        network = Network.objects.get(name='EOS_MAINNET')
        cost = cls.calc_cost(
            {
            'stake_cpu_value': '0.64',
            'stake_net_value': '0.01',
            'buy_ram_kbytes': 4
        }, network
        )
        return cost

    @classmethod
    def min_cost_eos(cls):
        network = Network.objects.get(name='EOS_MAINNET')
        cost = cls.calc_cost_eos({
            'stake_cpu_value': '0.64',
            'stake_net_value': '0.01',
            'buy_ram_kbytes': 4
        }, network)
        return cost

    @blocking
    @postponable
    def deploy(self):
        wallet_name = NETWORKS[self.contract.network.name]['wallet']
        password = NETWORKS[self.contract.network.name]['eos_password']
        unlock_eos_account(wallet_name, password)
        acc_name = NETWORKS[self.contract.network.name]['address']
        if self.contract.network.name == 'EOS_MAINNET':
            eos_url = 'https://%s' % (
            str(NETWORKS[self.contract.network.name]['host']))
        else:
            eos_url = 'http://%s:%s' % (str(NETWORKS[self.contract.network.name]['host']), str(NETWORKS[self.contract.network.name]['port']))
        command = [
            'cleos', '-u', eos_url, 'system', 'newaccount',
            acc_name, self.account_name, self.owner_public_key,
            self.active_public_key, '--stake-net', str(self.stake_net_value) + ' EOS',
            '--stake-cpu', str(self.stake_cpu_value) + ' EOS',
            '--buy-ram-kbytes', str(self.buy_ram_kbytes),
            '--transfer', '-j'
        ]
        print('command:', command, flush=True)
        tx_hash = implement_cleos_command(command)['transaction_id']
        print('tx_hash:', tx_hash, flush=True)
        eos_contract = EOSContract()
        eos_contract.tx_hash = tx_hash
        eos_contract.address = self.account_name
        eos_contract.contract=self.contract
        eos_contract.save()
        self.eos_contract = eos_contract
        self.save()
        self.contract.state = 'WAITING_FOR_DEPLOYMENT'
        self.contract.save()

    def newAccount(self, message):
        self.msg_deployed(message, eth_contract_attr_name='eos_contract')


class ContractDetailsEOSICO(CommonDetails):
    soft_cap = models.DecimalField(
        max_digits=MAX_WEI_DIGITS, decimal_places=0, null=True
    )
    hard_cap = models.DecimalField(
        max_digits=MAX_WEI_DIGITS, decimal_places=0, null=True
    )
    token_short_name = models.CharField(max_length=64)
    crowdsale_address = models.CharField(max_length=50)
    admin_address = models.CharField(max_length=50)
    is_transferable_at_once = models.BooleanField(default=False)
    start_date = models.IntegerField()
    stop_date = models.IntegerField()
    rate = models.DecimalField(
        max_digits=MAX_WEI_DIGITS, decimal_places=0, null=True
    )
    decimals = models.IntegerField()
    temp_directory = models.CharField(max_length=36)
    allow_change_dates = models.BooleanField(default=False)
    whitelist = models.BooleanField(default=False)
    protected_mode = models.BooleanField(default=False)
    min_wei = models.DecimalField(
        max_digits=MAX_WEI_DIGITS, decimal_places=0, default=None, null=True
    )
    max_wei = models.DecimalField(
        max_digits=MAX_WEI_DIGITS, decimal_places=0, default=None, null=True
    )

    eos_contract_token = models.ForeignKey(
        EOSContract,
        null=True,
        default=None,
        related_name='eos_ico_details_token',
        on_delete=models.SET_NULL
    )
    eos_contract_crowdsale = models.ForeignKey(
        EOSContract,
        null=True,
        default=None,
        related_name='eos_ico_details_crowdsale',
        on_delete=models.SET_NULL
    )

    @classmethod
    def min_cost(cls):
        network = Network.objects.get(name='EOS_MAINNET')
        cost = cls.calc_cost({}, network)
        return cost

    @classmethod
    def min_cost_eos(cls):
        network = Network.objects.get(name='EOS_MAINNET')
        cost = cls.calc_cost_eos({}, network)
        return cost

    @staticmethod
    def calc_cost(kwargs, network):
        if NETWORKS[network.name]['is_free']:
            return 0
        cost = CONTRACT_PRICE_USDT['EOS_ICO'] * NET_DECIMALS['USDT']
        return cost

    @staticmethod
    def calc_cost_eos(kwargs, network):
        if NETWORKS[network.name]['is_free']:
            return 0
        return int(CONTRACT_PRICE_EOS['EOS_ICO'] * NET_DECIMALS['EOS'])

    def get_arguments(self, eth_contract_attr_name):
        return []

    def predeploy_validate(self):
        now = timezone.now()
        if self.start_date < now.timestamp() + 600:
            raise ValidationError({'result': 1}, code=400)

    def compile(self):
        if self.temp_directory:
            print('already compiled')
            return
        token_holders = self.contract.eostokenholder_set.all()
        mint = ''
        for th in token_holders:
            mint = mint + ' --mint ' + '"{address} {amount}"'.format(
                address=th.address, amount=th.amount
            )
        print('mint', mint, flush=True)
        token_address = NETWORKS[self.contract.network.name]['token_address']
        dest, preproc_config = create_directory(
            self,
            sour_path='lastwill/eosio-crowdsale/*',
            config_name='config.h'
        )
        command = (
            "/bin/bash -c 'cd {dest} && ./configure.sh "
            "--issuer {issuer} --symbol {symbol} --decimals {decimals} "
            "--softcap {soft_cap} --hardcap {hard_cap} "
            "--whitelist {whitelist} --contract {acc_name} "
            "--transferable {transferable} --rate {rate} --ratedenom 1 "
            "--mincontrib {min_wei} --maxcontrib {max_wei} "
            " {mint} > {dest}/config.h' ").format(
                acc_name=token_address,
                dest=dest,
                # address=self.crowdsale_address,
                symbol=self.token_short_name,
                decimals=self.decimals,
                whitelist="true" if self.whitelist else "false",
                transferable="true" if self.is_transferable_at_once else "false",
                rate=self.rate,
                min_wei=self.min_wei if self.min_wei else 0,
                max_wei=self.max_wei if self.max_wei else 0,
                soft_cap=self.soft_cap,
                hard_cap=self.hard_cap,
                issuer=self.admin_address,
                mint=mint
                )
        print('command = ', command, flush=True)
        if os.system(command):
            raise Exception('error generate config')
        if os.system(
                "/bin/bash -c 'cd {dest} && make build'".format(
                    dest=dest)
        ):
            raise Exception('compiler error while deploying')

        with open(path.join(dest, 'crowdsale/crowdsale.abi'), 'rb') as f:
            abi = binascii.hexlify(f.read()).decode('utf-8')
        with open(path.join(dest, 'crowdsale/crowdsale.wasm'), 'rb') as f:
            bytecode = binascii.hexlify(f.read()).decode("utf-8")
        with open(path.join(dest, 'crowdsale.cpp'), 'rb') as f:
            source_code = f.read().decode('utf-8-sig')
        print('types', type(bytecode), type(abi))
        eos_contract_crowdsale = EOSContract()
        eos_contract_crowdsale.contract = self.contract
        eos_contract_crowdsale.original_contract = self.contract
        eos_contract_crowdsale.address = self.crowdsale_address
        eos_contract_crowdsale.abi = abi
        eos_contract_crowdsale.bytecode = bytecode
        eos_contract_crowdsale.source_code = source_code
        eos_contract_crowdsale.save()
        self.eos_contract_crowdsale = eos_contract_crowdsale
        self.save()

    @blocking
    @postponable
    def deploy(self):
        self.compile()
        wallet_name = NETWORKS[self.contract.network.name]['wallet']
        password = NETWORKS[self.contract.network.name]['eos_password']
        unlock_eos_account(wallet_name, password)
        acc_name = NETWORKS[self.contract.network.name]['address']
        our_public_key = NETWORKS[self.contract.network.name]['pub']
        if self.contract.network.name == 'EOS_MAINNET':
            eos_url = 'https://%s' % (
                str(NETWORKS[self.contract.network.name]['host']))
        else:
            eos_url = 'http://%s:%s' % (
            str(NETWORKS[self.contract.network.name]['host']),
            str(NETWORKS[self.contract.network.name]['port']))
        net = NETWORKS[self.contract.network.name]['stake_net']
        cpu = NETWORKS[self.contract.network.name]['stake_cpu']
        ram = NETWORKS[self.contract.network.name]['ram']
        command = [
            'cleos', '-u', eos_url, 'system', 'newaccount',
            acc_name, self.crowdsale_address, our_public_key, our_public_key,
            '--stake-net', net,
            '--stake-cpu', cpu,
            '--buy-ram-kbytes', ram, '--transfer', '-j'
        ]
        print('command:', command, flush=True)
        tx_hash = implement_cleos_command(command)['transaction_id']
        print('tx_hash:', tx_hash, flush=True)
        print('account for eos ico created', flush=True)
        self.eos_contract_crowdsale.tx_hash = tx_hash
        self.eos_contract_crowdsale.save()

    @blocking
    @postponable
    def newAccount(self, message):
        if self.contract.network.name == 'EOS_MAINNET':
            eos_url = 'https://%s' % (
                str(NETWORKS[self.contract.network.name]['host']))
        else:
            eos_url = 'http://%s:%s' % (
            str(NETWORKS[self.contract.network.name]['host']),
            str(NETWORKS[self.contract.network.name]['port']))
        acc_name = NETWORKS[self.contract.network.name]['address']
        our_public_key = NETWORKS[self.contract.network.name]['pub']
        token_address = NETWORKS[self.contract.network.name]['token_address']
        dest = path.join(CONTRACTS_TEMP_DIR, self.temp_directory)
        token_holders = self.contract.eostokenholder_set.all()
        total_supply = self.hard_cap
        for th in token_holders:
            total_supply = total_supply + th.amount
        if self.decimals != 0:
            if len(str(total_supply)) == self.decimals:
                max_supply = '0.' + str(total_supply)
            else:
                max_supply = str(total_supply)[:-self.decimals] + '.' + str(total_supply)[-self.decimals:]
        else:
            max_supply = str(total_supply)
        wallet_name = NETWORKS[self.contract.network.name]['wallet']
        password = NETWORKS[self.contract.network.name]['eos_password']
        unlock_eos_account(wallet_name, password)
        command = [
            'cleos', '-u', eos_url, 'set', 'abi', self.crowdsale_address,
            path.join(dest, 'crowdsale/crowdsale.abi'), '-jd', '-s'
        ]
        print('command:', command, flush=True)
        abi = implement_cleos_command(command)['actions'][0]['data'][20:]
        unlock_eos_account(wallet_name, password)
        dates = json.dumps({'start': self.start_date, 'finish': self.stop_date})
        print(dates, flush=True)
        if self.contract.network.name == 'EOS_MAINNET':
            contract_addr = 'dubravaleriy'
        else:
            contract_addr = 'mywishtest15'
            # acc_name = token_address
        command = [
            'cleos', '-u', eos_url, 'convert', 'pack_action_data',
            contract_addr, 'init', str(dates)
        ]
        print('command:', command, flush=True)
        init_data = implement_cleos_command(command)


        actions = create_eos_json(
            self.crowdsale_address, our_public_key,
            self.eos_contract_crowdsale.bytecode,
            abi, token_address, acc_name, max_supply, self.token_short_name,
            self.is_transferable_at_once, init_data
        )

        with open(path.join(dest, 'deploy_params.json'), 'w') as f:
            f.write(json.dumps(actions))
        command = [
            'cleos', '-u', eos_url, 'push', 'transaction',
            path.join(dest, 'deploy_params.json'), '-j',
            '-p', acc_name, '-p', self.crowdsale_address # do we need -p token_addres if address diff from token_address?
        ]
        print('command:', command, flush=True)
        print('lenght of command', len(str(command)))

        result = implement_cleos_command(command)['transaction_id']
        print('SUCCESS')
        self.contract.state = 'WAITING_FOR_DEPLOYMENT'
        self.contract.save()
        self.eos_contract_crowdsale.tx_hash = result
        self.eos_contract_crowdsale.save()

    def initialized(self, message):
        print("eos crowdsale initialized msg", flush=True)
        eos_contract_token = EOSContract()
        token_address = NETWORKS[self.contract.network.name]['token_address']
        eos_contract_token.address = token_address
        eos_contract_token.contract = self.contract
        eos_contract_token.save()
        self.eos_contract_token = eos_contract_token
        self.save()
        self.contract.state = 'ACTIVE'
        self.contract.save()
        if self.contract.user.email:
            network_name = MAIL_NETWORK[self.contract.network.name]
            send_mail(
                eos_ico_subject,
                eos_ico_message.format(
                    network_name=network_name
                ),
                DEFAULT_FROM_EMAIL,
                [self.contract.user.email]
            )
        take_off_blocking(self.contract.network.name, self.contract.id)

    def setcode(self, message):
        return

    def msg_deployed(self, message):
        pass

    def tokenCreated(self, message):
        pass

    def timesChanged(self, message):
        if 'startTime' in message and message['startTime']:
            self.start_date = message['startTime']
        if 'endTime' in message and message['endTime']:
            self.stop_date = message['endTime']
        self.save()

    def finalized(self, message):
        self.contract.state = 'DONE'
        self.contract.save()


class EOSAirdropAddress(models.Model):
    contract = models.ForeignKey(Contract, null=True)
    address = models.CharField(max_length=50, default=None)
    active = models.BooleanField(default=True)
    state = models.CharField(max_length=10, default='added')
    amount = models.DecimalField(
        max_digits=MAX_WEI_DIGITS, decimal_places=0, null=True,
        db_index=True
    )


class ContractDetailsEOSAirdrop(CommonDetails):

    contract = models.ForeignKey(Contract, null=True)
    admin_address = models.CharField(max_length=50)
    token_address = models.CharField(max_length=50)
    eos_contract = models.ForeignKey(EOSContract, null=True, default=None)
    token_short_name = models.CharField(max_length=64)
    address_count = models.IntegerField()
    memo = models.CharField(max_length=50, default='')

    @staticmethod
    def calc_cost(kwargs, network):
        if NETWORKS[network.name]['is_free']:
            return 0
        eos_cost = ContractDetailsEOSAirdrop.calc_cost_eos(kwargs, network) / NET_DECIMALS['EOS']
        usdt_cost = eos_cost * 5
        return round(usdt_cost, 2) * NET_DECIMALS['USDT']

    @staticmethod
    def calc_cost_eos(kwargs, network):
        if NETWORKS[network.name]['is_free']:
            return 0
        if network.name == 'EOS_MAINNET':
            eos_url = 'https://%s' % (
                str(NETWORKS[network.name]['host'])
            )
        else:
            eos_url = 'http://%s:%s' % (
                str(NETWORKS[network.name]['host']),
                str(NETWORKS[network.name]['port'])
            )
        command1 = [
            'cleos', '-u', eos_url, 'get', 'table', 'eosio', 'eosio',
            'rammarket'
        ]
        result = implement_cleos_command(command1)
        ram = result['rows'][0]
        ram_price = float(ram['quote']['balance'].split()[0]) / float(ram['base']['balance'].split()[0])
        return round(250 + ram_price * 240 * float(kwargs['address_count']) * 1.2, 4) * NET_DECIMALS['EOS']

    @classmethod
    def min_cost(cls):
        network = Network.objects.get(name='EOS_MAINNET')
        cost = cls.calc_cost({'address_count': 1}, network)
        return cost

    @classmethod
    def min_cost_eos(cls):
        network = Network.objects.get(name='EOS_MAINNET')
        cost = cls.calc_cost_eos({'address_count': 1}, network)
        return cost

    @blocking
    @postponable
    def deploy(self):
        if self.contract.network.name == 'EOS_MAINNET':
            eos_url = 'https://%s' % (
                str(NETWORKS[self.contract.network.name]['host']))
        else:
            eos_url = 'http://%s:%s' % (
                str(NETWORKS[self.contract.network.name]['host']),
                str(NETWORKS[self.contract.network.name]['port']))
        wallet_name = NETWORKS[self.contract.network.name]['wallet']
        password = NETWORKS[self.contract.network.name]['eos_password']
        airdrop_address = NETWORKS[self.contract.network.name]['airdrop_address']
        unlock_eos_account(wallet_name, password)
        command = [
            'cleos', '-u', eos_url, 'get', 'table', self.token_address,
            self.token_short_name, 'stat'
        ]
        print('command', command)
        result = implement_cleos_command(command)['rows'][0]['supply']
        print('result', result)
        decimals = len(result.split(' ')[0].split('.')[1])
        print('decimals', decimals)
        command = ['cleos', '-u', eos_url, 'push',  'action', airdrop_address, 'create',
                   '["{pk}", "{admin}", "{token}", "{decimals},{token_short_name}", "{addr_count}"]'.format(
                       pk=self.contract.id,
                       admin=self.admin_address,
                       token=self.token_address,
                       decimals=decimals,
                       token_short_name=self.token_short_name,
                       addr_count=self.address_count,
                   ), '-p', airdrop_address, '-j']
        print('command', command)
        result = implement_cleos_command(command)['transaction_id']
        print('result', result)
        print('SUCCESS')

        eos_contract = EOSContract()
        eos_contract.contract = self.contract
        eos_contract.original_contract = self.contract
        eos_contract.tx_hash = result
        eos_contract.address = airdrop_address
        eos_contract.save()
        self.eos_contract = eos_contract
        self.save()
        self.contract.state = 'WAITING_FOR_DEPLOYMENT'
        self.contract.save()

    def airdrop(self, message):
        new_state = {
            'COMMITTED': 'sent',
            'PENDING': 'processing',
            'REJECTED': 'added'
        }[message['status']]

        old_state = {
            'COMMITTED': 'processing',
            'PENDING': 'added',
            'REJECTED': 'processing'
        }[message['status']]

        ids = []
        for js in message['airdroppedAddresses']:
            address = js['address']
            amount = js['value']
            addr = EOSAirdropAddress.objects.filter(
                address=address,
                amount=amount,
                contract=self.contract,
                active=True,
                state=old_state,
            ).exclude(id__in=ids).first()
            if addr is None and message['status'] == 'COMMITTED':
                old_state = 'added'
                addr = EOSAirdropAddress.objects.filter(
                    address=address,
                    amount=amount,
                    contract=self.contract,
                    active=True,
                    state=old_state
                ).exclude(id__in=ids).first()
            if addr is None:
                continue

            ids.append(addr.id)
        if len(message['airdroppedAddresses']) != len(ids):
            print('=' * 40, len(message['airdroppedAddresses']), len(ids), flush=True)

        EOSAirdropAddress.objects.filter(id__in=ids).update(state=new_state)

        if message.get('errorAddresses'):
            self.contract.state = 'POSTPONED'
            self.contract.save()
            ids = []
            for js in message['errorAddresses']:
                addr = EOSAirdropAddress.objects.filter(
                     address=js['address'],
                     amount=js['value'],
                     contract=self.contract,
                     active=True,
                ).exclude(id__in=ids).first()
                ids.append(addr.id)
            EOSAirdropAddress.objects.filter(id__in=ids).update(state='failed')
        elif self.contract.airdropaddress_set.filter(
                state__in=('added', 'processing'),
                active=True
        ).count() == 0:
            self.contract.state = 'ENDED'
            self.contract.save()

    @blocking
    @postponable
    @check_transaction
    def msg_deployed(self, message):
        take_off_blocking(self.contract.network.name)
        network = self.contract.network.name
        network_name = MAIL_NETWORK[network]
        self.contract.state = 'ACTIVE'
        self.contract.save()
        if self.contract.user.email:
            send_mail(
                eos_airdrop_subject,
                eos_airdrop_message.format(
                    network_name=network_name,
                    hash=self.eos_contract.tx_hash
                ),
                DEFAULT_FROM_EMAIL,
                [self.contract.user.email]
            )
        self.save()
