register_subject = """Please Confirm Your E-mail Address"""

register_text = """{subsite_name} team welcomes you!

You're receiving this e-mail because user {user_display} has entered this e-mail address to connect to their account.

To confirm the registration, click on the link below:

{activate_url}

Best regards!
{subsite_name} Team."""


password_reset_subject = """Password reset on {subsite_name} """
password_reset_text = """
You're receiving this email because you requested a password reset for your user account at {subsite_name}.

Please go to the following page and choose a new password:

{password_reset_url}

Your username, in case you've forgotten: {user_display}

Thanks for using our site!

{subsite_name} Team."""

common_subject = """Your contract is ready"""
common_text = """Hello,

We are happy to inform you that your contract was successfully created and deployed to {network_name} network.
{contract_type_name}: {link}

Please contact support@mywish.io if you need if you have any questions.

Best wishes,
MyWish Team."""

ico_subject = """Your contract is ready"""
ico_text = """Hello,

We are happy to inform you that your contract was successfully created and deployed to {network_name} network.
Token contract: {link1}
Crowdsale contract: {link2}

Please contact support@mywish.io if you have any questions.

Best wishes,
MyWish Team."""

create_subject = """Your contract is ready for deployment"""
create_message = """Congratulations!

Your contract is created and ready for deployment to {network_name}.

If you have any questions or want to get free promotion of your project in MyWish social channels please contact support@mywish.io.

Thank you for using MyWish.
"""

eos_create_subject = """Your account is ready for creation"""
eos_create_message = """Congratulations!

Your EOS account is ready for creation in {network_name}.

If you have any questions please contact support@mywish.io.

Thank you for using MyWish.
"""

eos_account_subject = """Your account is ready"""
eos_account_message = """Hello,

We are happy to inform you that your account was successfully created in {network_name}.
EOS Account: {link}

Please contact support@mywish.io if you need if you have any questions.

Best wishes,
MyWish Team."""

eos_ico_subject = """Your account is ready"""
eos_ico_message = """Hello,

We are happy to inform you that your ICO was successfully created in {network_name}.

Please contact support@mywish.io if you need if you have any questions.

Best wishes,
MyWish Team."""

eos_contract_subject = """Your contract is ready"""
eos_contract_message = """Hello,

We are happy to inform you that your contract was successfully created and deployed to {network_name}.
EOS Token: {token_name}

You can MINT your token now.

Please contact support@mywish.io if you need if you have any questions.

Best wishes,
MyWish Team."""

heir_subject = """MyWish notification"""
heir_message = """Hello!

In accordance with the contract created on MyWish platform, Funds have been transfered to address "{user_address}" :  "{link_tx}"

If you have any questions, please contact support@mywish.io"""

postponed_subject = """ATTENTION! POSTPONED CONTRACT"""
postponed_message = """Contract {contract_id} change state on 'POSTPONED' """

remind_subject = """Reminder to confirm “Live” status"""
remind_message = """Hello,

We would like to remind you to confirm your “live” status for the contract.
Contract will be executed if no confirmation during the next {days} days.

You can see the contract here: https://contracts.mywish.io

If you have any questions please contact support@mywish.io

Best wishes,
MyWish Team
"""
carry_out_subject = """The Will contract is completed"""
carry_out_message = """Hello,

In accordance with Will contract funds have been transferred successfully.

If you have any questions please contact support@mywish.io

Best wishes,
MyWish Team
"""

neo_token_text = '''Hello,

We are happy to inform you that your contract was successfully created and deployed to NEO Test network.
Token contract address: {addr}

Please contact support@mywish.io if you have any questions.

Best wishes,
MyWish Team.
'''

eos_airdrop_subject = """Your contract is ready"""
eos_airdrop_message = """Hello,

We are happy to inform you that your contract was successfully created and deployed on {network_name}.
Tx hash: {hash}

Please contact support@mywish.io if you have any questions.

Best wishes,
MyWish Team.
"""

authio_subject = """MyWish - Request for brand report"""
authio_message = """Hello!

We want to inform you that the user {email} has created a request to check
the smart contract created on the MyWish platform and get a branded report.

Contract parameters (Source code):

1) Token address: {address}
2)Token name: {token_name}
3) Token symbol: {token_short_name}
4) Decimals: {decimals}
5) Type of Token: {token_type}
6) Token Owner: {admin_address}
7) Mint/Freeze tokens: {mint_info}
Please contact support@mywish.io if you have any questions.

Best wishes,
MyWish Team.
"""

authio_google_subject = """Branded Audit Report: Project details request"""
authio_google_message = """Hello!

Thank you for using our service.

Your contract is ready for the report preparation.

If you have any questions - please mail to support@mywish.io. We will contact you as soon as possible.

Thank you,
MyWish Team
"""

freeze_15_failed_subject = """ MyWish - Freezing of 15% tokens failed """
freeze_15_failed_message = """Hello!

Please check the receipt of 15% of {token_type} tokens on {address_type} for freezing.
Last payment can be failed due to an error.

Freezed balance is:
{tx_balance} {token_type}

Error, which was encountered:
{traceback}

Best wishes,
MyWish Team.
"""

tron_deploy_subject = """Your contract is ready"""
tron_deploy_text = """Hello,

We are happy to inform you that your contract was successfully created and deployed to {network_name} network.

Please contact support@mywish.io if you need if you have any questions.

Best wishes,
MyWish Team."""

swaps_subject = """Your SWAP is ready for deployment"""
swaps_message = """Hello,

Your SWAP is created and ready for deployment to Ethereum.

If you have any questions please contact support@swaps.network.

Best wishes,
SWAPS.NETWORK Team.

"""

swaps_deploed_subject = """Your contract is ready"""
swaps_deploed_message = """Congratulations!

We are happy to inform you that your contract was successfully deployed to Ethereum.
You can use your SWAP now: {swaps_link}

Please contact support@swaps.network if you have any questions.

Best wishes,
SWAPS.NETWORK Team.
"""

swaps_support_subject = """ Swaps user notification"""
swaps_support_message = """Hello,

User with email {email} want to send next message:
{msg}

to swap with id {id}
contract's link {link}

Best wishes,
Swaps Team."""


waves_sto_subject = """Your contract is ready"""
waves_sto_text = """Hello,

We are happy to inform you that your Waves STO smart account was successfully created and deployed to {network_name} network.
Asset:  {link1}
STO contract: {link2}

Please contact support@mywish.io if you have any questions.

Best wishes,
MyWish Team."""

protector_deployed_subject = """Your Protector is on"""
protector_deployed_text = """Congratulations!

Your protector contract was deployed to Ethereum successfully. 
Please make sure you select tokens for protection.

You can manage the contract in your profile on protector.mywish.io
Please contact support@mywish.io in case of any questions.

Best wishes,
MyWish Team"""

protector_create_subject = """Your contract is ready for deployment"""
protector_create_text = """Hello!

Your contract is created and ready for deployment to Ethereum.

If you have any questions please contact support@mywish.io.

Best wishes,
MyWish Team
"""

protector_execution_subject = """Your contract will be executed soon"""
protector_execution_text = """Hello,

This is Mywish platform. Your token protector contract will be executed in {days} day(s).
You can cancel it in your profile on protector.mywish.io

Best Wishes,
MyWish Team"""
