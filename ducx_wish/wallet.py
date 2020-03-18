from neo.Wallets.Wallet import Wallet
from neo.Implementations.Wallets.peewee.UserWallet import UserWallet
from neo.SmartContract.Contract import Contract as WalletContract
from neo.Settings import settings


class MyWallet(UserWallet):

    def __init__(self, path, passwordKey, create):
        self.AddressVersion = settings.ADDRESS_VERSION

    def CreateKey(self, prikey=None):
        account = super(UserWallet, self).CreateKey(private_key=prikey)
        # self.OnCreateAccount(account)
        contract = WalletContract.CreateSignatureContract(account.PublicKey)
        self.AddContract(contract)
        return account

    def AddContract(self, contract):
        Wallet.AddContract(self, contract)
        # if not contract.PublicKeyHash.ToBytes() in self._keys.keys():
        #     raise Exception('Invalid operation - public key mismatch')
        #
        # self._contracts[contract.ScriptHash.ToBytes()] = contract
        # if contract.ScriptHash in self._watch_only:
        #     self._watch_only.remove(contract.ScriptHash)

    @property
    def IsSynced(self):
        return True

    def FindUnspentCoinsByAssetAndTotal(
            self, asset_id, amount, from_addr=None,
            use_standard=False, watch_only_val=0, reverse=False
    ):
        return []
