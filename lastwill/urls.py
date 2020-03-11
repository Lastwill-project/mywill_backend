"""lastwill URL Configuration

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/1.11/topics/http/urls/
Examples:
Function views
    1. Add an import:  from my_app import views
    2. Add a URL to urlpatterns:  url(r'^$', views.home, name='home')
Class-based views
    1. Add an import:  from other_app.views import Home
    2. Add a URL to urlpatterns:  url(r'^$', Home.as_view(), name='home')
Including another URLconf
    1. Import the include() function: from django.conf.urls import url, include
    2. Add a URL to urlpatterns:  url(r'^blog/', include('blog.urls'))
"""
from django.conf.urls import url, include
from django.conf import settings
from django.conf.urls.static import static
# from allauth.account.views import confirm_email as allauthemailconfirmation
from rest_framework.routers import DefaultRouter

from lastwill.main.views import index, balance, login, eth2rub, exc_rate, redirect_contribute
from lastwill.profile.views import confirm_email as allauthemailconfirmation
from lastwill.profile.views import profile_view, generate_key, enable_2fa, disable_2fa, resend_email, set_lang
from lastwill.profile.views import create_api_token, get_api_tokens, delete_api_token, delete_api_tokens
from lastwill.profile.helpers import generate_metamask_message
from lastwill.contracts.api import (ContractViewSet, get_code, test_comp,
                                    deploy, get_token_contracts,
                                    ICOtokensView, get_statistics, i_am_alive,
                                    cancel, get_statistics_landing,
                                    get_cost_all_contracts, neo_crowdsale_finalize,
                                    WhitelistAddressViewSet, AirdropAddressViewSet,
                                    load_airdrop, get_contract_for_link,
                                    get_invest_balance_day, check_status,
                                    get_eos_cost, EOSAirdropAddressViewSet, get_eos_airdrop_cost,
                                    check_eos_accounts_exists, buy_brand_report, get_authio_cost,
                                    get_testnet_tron_tokens, get_tokens_for_eth_address,
                                    get_tronish_balance, confirm_swaps_info, confirm_protector_info,
                                    get_contract_for_unique_link, get_public_contracts,
                                    change_contract_state, send_message_author_swap, confirm_protector_tokens,
                                    get_test_tokens, skip_protector_approve)
from lastwill.contracts.api_eos import (create_eos_account, deploy_eos_account,
                                        show_eos_account, edit_eos_account,
                                        calculate_cost_eos_account, calculate_cost_eos_account_contract,
                                        delete_eos_account_contract, get_all_blockchains,
                                        get_profile_info, get_balance_info, get_eos_contracts)
from lastwill.contracts.api_eth import (create_eth_token, show_eth_token,
                                        edit_eth_token, delete_eth_token_contract,
                                        deploy_eth_token, calculate_cost_eth_token_contract,
                                        get_source_code_eth_token)
from lastwill.contracts.api_common import get_contract_price, get_contracts, get_available_contracts
from lastwill.other.api import SentenceViewSet, send_unblocking_info
from lastwill.social.views import FacebookLogin, GoogleLogin, MetamaskLogin, FacebookAuth
from lastwill.promo.api import get_discount, get_all_promos_api
from lastwill.snapshot.api import snapshot_get_value
from lastwill.swaps_common.tokentable.api import get_all_tokens, get_standarts_tokens, get_all_coinmarketcap_tokens, get_coins_rate
from lastwill.swaps_common.mailing.api import save_swaps_mail
from lastwill.swaps_common.orderbook.api import create_contract_swaps_backend, show_contract_swaps_backend, \
    edit_contract_swaps_backend, get_swap_v3_for_unique_link, show_user_contract_swaps_backend, \
    get_swap_v3_public, set_swaps_expired, delete_swaps_v3, cancel_swaps_v3, admin_delete_swaps_v3, get_non_active_orders
from lastwill.swaps_common.orderbook.api_exchange import create_swaps_order_api, create_token_for_session, \
    get_cmc_tokens_for_api, get_user_orders_for_api, delete_order_for_user, create_token_for_session_mywish
from lastwill.swaps_common.tokentable.api import get_all_tokens, get_standarts_tokens, get_all_coinmarketcap_tokens, get_coins_rate
from lastwill.admin import lastwill_admin

router = DefaultRouter(trailing_slash=True)
router.register(r'contracts', ContractViewSet)
router.register(r'sentences', SentenceViewSet)
router.register(r'whitelist_addresses', WhitelistAddressViewSet)
router.register(r'airdrop_addresses', AirdropAddressViewSet)
router.register(r'eos_airdrop_addresses', EOSAirdropAddressViewSet)


urlpatterns = [
    url(r'^reset', index),
    url(r'^', include('django.contrib.auth.urls')),
    # url(r'^jopa/', admin.site.urls),
    url(r'^jopa/', lastwill_admin.urls),
    url(r'^api/', include(router.urls)),
    url(
            r'^api/rest-auth/registration/account-confirm-email/(?P<key>[-:\w]+)/$',
            allauthemailconfirmation, name="account_confirm_email"
    ),
    url(r'^api/rest-auth/', include('rest_auth.urls')),
    url(r'^api/rest-auth/registration/', include('rest_auth.registration.urls')),
    url(r'^/email-verification-sent/$', index, name='account_email_verification_sent'),
    url(r'^api/profile/', profile_view),
    url(r'^api/balance/', balance),
    url(r'^auth/', login),
    url(r'^api/get_code/', get_code),
    url(r'^api/test_comp/', test_comp),
    url(r'^api/eth2rub/', eth2rub),
    url(r'^api/exc_rate/', exc_rate),
    url(r'^api/deploy/', deploy),
    url(r'^api/get_token_contracts/', get_token_contracts),
    url(r'^api/generate_key/', generate_key),
    url(r'^api/enable_2fa/', enable_2fa),
    url(r'^api/disable_2fa/', disable_2fa),
    url(r'^api/get_metamask_message/', generate_metamask_message),
    url(r'^api/rest-auth/facebook/$', FacebookAuth, name='fb_login'),
    url(r'^api/rest-auth/google/$', GoogleLogin.as_view(), name='google_login'),
    url(r'^api/rest-auth/metamask/$', MetamaskLogin.as_view(), name='metamask_login'),
    url(r'^api/resend_email/', resend_email),
    url(r'^api/get_discount/', get_discount),
    url(r'^/$', index, name='socialaccount_signup'),
    url(r'^api/count_sold_tokens_in_ICO/$', ICOtokensView.as_view(),
        name='count_ICOtokens'),
    url(r'^api/get_statistics/$', get_statistics, name='get statistics'),
    url(r'^api/get_statistics_landing/$', get_statistics_landing),
    url(r'^api/i_am_alive/', i_am_alive),
    url(r'^api/cancel/', cancel),
    url(r'^api/get_all_costs/$', get_cost_all_contracts),
    url(r'^api/set_lang/$', set_lang),
    url(r'^api/neo_ico_finalize/$', neo_crowdsale_finalize),
    url(r'^api/load_airdrop/$', load_airdrop),
    url(r'^api/get_contract_for_link/$', get_contract_for_link),
    url(r'^api/get_invest_balance_day/$', get_invest_balance_day),
    url(r'^api/check_status/$', check_status),
    url(r'^api/get_eos_cost/$', get_eos_cost),
    url(r'^api/get_eos_airdrop_cost/$', get_eos_airdrop_cost),
    url(r'^api/check_eos_accounts_exists/$', check_eos_accounts_exists),
    url(r'^api/snapshot_get_value/$', snapshot_get_value),
    url(r'^api/create_eos_account/$', create_eos_account),
    url(r'^api/deploy_eos_account/$', deploy_eos_account),
    url(r'^api/show_eos_account/$', show_eos_account),
    url(r'^api/edit_eos_account/$', edit_eos_account),
    url(r'^api/buy_brand_report/$', buy_brand_report),
    url(r'^api/get_authio_cost/$', get_authio_cost),
    url(r'^api/send_unblocking_feedback/$', send_unblocking_info),
    url(r'^api/calculate_cost_eos_account/$', calculate_cost_eos_account),
    url(r'^api/calculate_cost_eos_account_contract/$', calculate_cost_eos_account_contract),
    url(r'^api/delete_eos_account_contract/$', delete_eos_account_contract),
    url(r'^api/get_all_blockchains/$', get_all_blockchains),
    url(r'^api/get_profile_info/$', get_profile_info),
    url(r'^api/get_balance_info/$', get_balance_info),
    url(r'^api/get_eos_contracts/$', get_eos_contracts),
    url(r'^api/create_api_token/$', create_api_token),
    url(r'^api/get_api_tokens/$', get_api_tokens),
    url(r'^api/delete_api_token/$', delete_api_token),
    url(r'^api/create_eth_token/$', create_eth_token),
    url(r'^api/show_eth_token/$', show_eth_token),
    url(r'^api/edit_eth_token/$', edit_eth_token),
    url(r'^api/deploy_eth_token/$', deploy_eth_token),
    url(r'^api/calculate_cost_eth_token/$', calculate_cost_eth_token_contract),
    url(r'^api/delete_eth_token/$', delete_eth_token_contract),
    url(r'^api/delete_all_api_tokens/$', delete_api_tokens),
    url(r'^api/get_source_code_eth_token/$', get_source_code_eth_token),
    url(r'^api/get_contract_price/$', get_contract_price),
    url(r'^api/get_contracts/$', get_contracts),
    url(r'^api/get_available_contracts/$', get_available_contracts),
    url(r'^api/get_testnet_tron_tokens/$', get_testnet_tron_tokens),
    url(r'^api/get_tokens_for_eth_address/$', get_tokens_for_eth_address),
    url(r'^api/get_tronish_balance/$', get_tronish_balance),
    url(r'^api/get_all_tokens/$', get_all_tokens),
    url(r'^api/get_standarts_tokens/$', get_standarts_tokens),
    url(r'^api/get_coinmarketcap_tokens/$', get_all_coinmarketcap_tokens),
    url(r'^api/confirm_swaps_info/$', confirm_swaps_info),
    url(r'^api/confirm_protector_info/$', confirm_protector_info),
    url(r'^api/confirm_protector_tokens/$', confirm_protector_tokens),
    url(r'^api/skip_protector_approve/$', skip_protector_approve),
    url(r'^api/get_test_tokens/$', get_test_tokens),
    url(r'^api/get_contract_for_unique_link/$', get_contract_for_unique_link),
    url(r'^api/get_public_contracts/$', get_public_contracts),
    url(r'^api/change_contract_state/$', change_contract_state),
    url(r'^api/send_message_author_swap/$', send_message_author_swap),
    url(r'^api/save_swaps_mail/$', save_swaps_mail),
    url(r'^api/create_swap3/$', create_contract_swaps_backend),
    url(r'^api/get_swap3/$', show_contract_swaps_backend),
    url(r'^api/get_swap3_for_unique_link/$', get_swap_v3_for_unique_link),
    url(r'^api/edit_swap3/(?P<swap_id>\d+)/$', edit_contract_swaps_backend),
    url(r'^api/get_user_swap3/$', show_user_contract_swaps_backend),
    url(r'^api/get_public_swap3/$', get_swap_v3_public),
    url(r'^api/set_swap3_expired/$', set_swaps_expired),
    url(r'^api/delete_swap3/$', delete_swaps_v3),
    url(r'^api/cancel_swap3/$', cancel_swaps_v3),
    url(r'^api/admin_delete_swap3/$', admin_delete_swaps_v3),
    url(r'^api/create_swap_order/$', create_swaps_order_api),
    url(r'^api/get_swap_order_token/$', create_token_for_session),
    url(r'^api/get_swap_tokens_api/$', get_cmc_tokens_for_api),
    url(r'^api/get_swap3_orders/$', get_user_orders_for_api),
    url(r'^api/delete_order_for_user/$', delete_order_for_user),
    url(r'^api/generate_mywish_swap_token/$', create_token_for_session_mywish),
    url(r'^contribute', redirect_contribute),
    url(r'^api/get_non_active_swap3', get_non_active_orders),
    url(r'^api/admin_delete_swap3/$', admin_delete_swaps_v3),
    url(r'^api/get_cmc_token_rate', get_coins_rate),
    url(r'^api/get_all_promos/$', get_all_promos_api)
]

urlpatterns += url(r'^/*', index, name='all'),

urlpatterns += static(settings.STATIC_URL, document_root=settings.STATIC_ROOT)
urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
