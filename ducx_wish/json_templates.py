def get_freeze_wish_abi():
  return [
  {
    "constant": True,
    "inputs": [],
    "name": "name",
    "outputs": [
      {
        "name": "",
        "type": "string"
      }
    ],
    "payable": False,
    "stateMutability": "view",
    "type": "function"
  },
  {
    "constant": False,
    "inputs": [
      {
        "name": "_spender",
        "type": "address"
      },
      {
        "name": "_value",
        "type": "uint256"
      }
    ],
    "name": "approve",
    "outputs": [
      {
        "name": "",
        "type": "bool"
      }
    ],
    "payable": False,
    "stateMutability": "nonpayable",
    "type": "function"
  },
  {
    "constant": True,
    "inputs": [],
    "name": "totalSupply",
    "outputs": [
      {
        "name": "",
        "type": "uint256"
      }
    ],
    "payable": False,
    "stateMutability": "view",
    "type": "function"
  },
  {
    "constant": False,
    "inputs": [
      {
        "name": "_from",
        "type": "address"
      },
      {
        "name": "_to",
        "type": "address"
      },
      {
        "name": "_value",
        "type": "uint256"
      }
    ],
    "name": "transferFrom",
    "outputs": [
      {
        "name": "",
        "type": "bool"
      }
    ],
    "payable": False,
    "stateMutability": "nonpayable",
    "type": "function"
  },
  {
    "constant": True,
    "inputs": [],
    "name": "decimals",
    "outputs": [
      {
        "name": "",
        "type": "uint8"
      }
    ],
    "payable": False,
    "stateMutability": "view",
    "type": "function"
  },
  {
    "constant": True,
    "inputs": [
      {
        "name": "_owner",
        "type": "address"
      }
    ],
    "name": "balanceOf",
    "outputs": [
      {
        "name": "balance",
        "type": "uint256"
      }
    ],
    "payable": False,
    "stateMutability": "view",
    "type": "function"
  },
  {
    "constant": True,
    "inputs": [],
    "name": "symbol",
    "outputs": [
      {
        "name": "",
        "type": "string"
      }
    ],
    "payable": False,
    "stateMutability": "view",
    "type": "function"
  },
  {
    "constant": False,
    "inputs": [
      {
        "name": "_to",
        "type": "address"
      },
      {
        "name": "_value",
        "type": "uint256"
      }
    ],
    "name": "transfer",
    "outputs": [
      {
        "name": "",
        "type": "bool"
      }
    ],
    "payable": False,
    "stateMutability": "nonpayable",
    "type": "function"
  },
  {
    "constant": True,
    "inputs": [
      {
        "name": "_owner",
        "type": "address"
      },
      {
        "name": "_spender",
        "type": "address"
      }
    ],
    "name": "allowance",
    "outputs": [
      {
        "name": "",
        "type": "uint256"
      }
    ],
    "payable": False,
    "stateMutability": "view",
    "type": "function"
  },
  {
    "payable": True,
    "stateMutability": "payable",
    "type": "fallback"
  },
  {
    "anonymous": False,
    "inputs": [
      {
        "indexed": True,
        "name": "owner",
        "type": "address"
      },
      {
        "indexed": True,
        "name": "spender",
        "type": "address"
      },
      {
        "indexed": False,
        "name": "value",
        "type": "uint256"
      }
    ],
    "name": "Approval",
    "type": "event"
  },
  {
    "anonymous": False,
    "inputs": [
      {
        "indexed": True,
        "name": "from",
        "type": "address"
      },
      {
        "indexed": True,
        "name": "to",
        "type": "address"
      },
      {
        "indexed": False,
        "name": "value",
        "type": "uint256"
      }
    ],
    "name": "Transfer",
    "type": "event"
  }
]

def create_eos_json(
        crowdsale_address, public_key, bytecode, abi, token_address, deployer_address,
        max_supply, token_short_name, is_transferable_at_once, init_data
):
    return {"actions": [
                        {
                        "account": "eosio",
                        "name": "updateauth",
                        "authorization": [{
                            "actor": crowdsale_address,
                            "permission": "active"
                        }],
                         "data": {
                             "account": crowdsale_address,
                             "permission": "active",
                             "parent": "owner",
                             "auth": {
                                 "threshold": 1, "keys":
                                      [{
                                        "key": public_key,
                                        "weight": 1}],
                                        "accounts": [
                                                {"permission": {
                                                    "actor": crowdsale_address,
                                                    "permission": "eosio.code"
                                                },
                                                "weight": 1
                                                },
                                                {"permission": {
                                                    "actor":      token_address,
                                                    "permission": "eosio.code"
                                                },
                                                    "weight":  1
                                                }
                                        ],
                                    "waits": []
                             }
                         }
                        },
                        {
                        "account": "eosio",
                        "name": "setcode",
                        "authorization": [{
                            "actor": crowdsale_address,
                            "permission": "active"
                        }],
                        "data": {
                            "account": crowdsale_address,
                            "vmtype": 0,
                            "vmversion": 0,
                            "code": bytecode
                        }
                    }, {
                        "account": "eosio",
                        "name": "setabi",
                        "authorization": [{
                            "actor": crowdsale_address,
                            "permission": "active"
                        }],
                        "data": {
                            "account": crowdsale_address,
                            "abi": abi
                        }
                    }, {
                        "account": token_address,
                        "name": "create" if is_transferable_at_once else "createlocked",
                        "authorization": [{
                            "actor": deployer_address,
                            "permission": "active"
                        }],
                        "data": {
                            "issuer": crowdsale_address,
                            "maximum_supply": max_supply + " " + token_short_name,
                            "lock": not is_transferable_at_once
                        }
                    },
                    {
                        "account": crowdsale_address,
                        "name": "init",
                        "authorization": [{
                            "actor": crowdsale_address,
                            "permission": "active"
                        }],
                        "data": init_data
                    },
                    {
                        "account": "eosio",
                        "name": "updateauth",
                        "authorization": [{
                            "actor": crowdsale_address,
                            "permission": "owner"
                        }],
                        "data": {
                            "account": crowdsale_address,
                            "permission": "owner",
                            "parent": "",
                            "auth": {
                                "threshold": 1,
                                "keys": [],
                                "accounts": [{
                                    "permission": {
                                        "actor": crowdsale_address,
                                        "permission": "owner"
                                    },
                                    "weight": 1
                                }],
                                "waits": []
                            }
                        }
                    }, {
                        "account": "eosio",
                        "name": "updateauth",
                        "authorization": [{
                            "actor": crowdsale_address,
                            "permission": "active"
                        }],
                        "data": {
                            "account": crowdsale_address,
                            "permission": "active",
                            "parent": "owner",
                            "auth": {
                                "threshold": 1,
                                "keys": [],
                                "accounts": [
                                    {
                                    "permission": {
                                        "actor": crowdsale_address,
                                        "permission": "eosio.code"
                                        },
                                        "weight": 1
                                    },
                                    {
                                        "permission": {
                                            "actor":      token_address,
                                            "permission": "eosio.code"
                                        },
                                        "weight":     1
                                    }
                                ],
                                "waits": []
                            }
                        }
                    }]
                }

def create_eos_token_sa_json(token_address, bytecode, abi, admin_address, data):
    return {
        "actions": [
            {
                "account": "eosio",
                "name": "setabi",
                "authorization": [
                    {
                        "actor": token_address,
                        "permission": "active"
                    }
                ],
                "data": {
                    "account": token_address,
                    "abi": abi
                }
            },
            {
                "account": "eosio",
                "name": "setcode",
                "authorization": [
                    {
                        "actor": token_address,
                        "permission": "active"
                    }
                ],
                "data": {
                    "account": token_address,
                    "vmtype": 0,
                    "vmversion": 0,
                    "code": bytecode
                }
            },
            {
                "account": token_address,
                "name": "create",
                "authorization": [
                    {
                        "actor": token_address,
                        "permission": "active"
                    }
                ],
                "data": data
            },
            {
                "account": "eosio",
                "name": "updateauth",
                "authorization": [
                    {
                        "actor": token_address,
                        "permission": "owner"
                    }
                ],
                "data": {
                    "account": token_address,
                    "permission": "owner",
                    "parent": "",
                    "auth": {
                        "threshold": 1,
                        "keys": [],
                        "accounts": [
                            {
                                "permission": {
                                    "actor": admin_address,
                                    "permission": "owner"
                                },
                                "weight": 1
                            }
                        ],
                        "waits": []
                    }
                }
            },
            {
                "account": "eosio",
                "name": "updateauth",
                "authorization": [
                    {
                        "actor": token_address,
                        "permission": "active"
                    }
                ],
                "data": {
                    "account": token_address,
                    "permission": "active",
                    "parent": "owner",
                    "auth": {
                        "threshold": 1,
                        "keys": [],
                        "accounts": [
                            {
                                "permission": {
                                    "actor": admin_address,
                                    "permission": "eosio.code"
                                },
                                "weight": 1
                            }
                        ],
                        "waits": []
                    }
                }
            }
        ]
    }
