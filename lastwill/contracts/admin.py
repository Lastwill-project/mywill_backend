from django.contrib.admin import ModelAdmin, register

from lastwill.swaps_common.tokentable.models import (
    Tokens,
    TokensCoinMarketCap,
    TokensUpdateTime
)


@register(Tokens)
class TokensModelAdmin(ModelAdmin):
    """
    Настройки панели администратора модели Token.
    """
    fields = (
        'address',
        'token_name',
        'token_short_name',
        'decimals',
        'image_link',
    )
    list_display = (
        'id',
        'address',
        'token_name',
        'token_short_name',
        'decimals',
        'image_link',
    )
    search_fields = (
        'id',
        'token_short_name',
        'address',
    )
    ordering = (
        'id',
    )


@register(TokensCoinMarketCap)
class TokensCoinMarketCapModelAdmin(ModelAdmin):
    """
    Настройки панели администратора модели TokensCoinMarketCap.
    """
    fields = (
        # 'token_cmc_id',
        'token_name',
        'token_short_name',
        'token_platform',
        'token_address',
        # 'image_link',
        # 'token_rank',
        'image',
        # 'token_price',
        # 'updated_at',
    )
    list_display = (
        'id',
        'token_cmc_id',
        'token_short_name',
        'token_platform',
        'token_address',
        'token_rank',
        'token_price',
        'updated_at',
    )
    list_filter = (
        'updated_at',
    )
    search_fields = (
        'token_cmc_id',
        'token_name',
        'token_short_name',
        'token_platform',
        'token_address',
    )
    ordering = (
        'id',
    )


@register(TokensUpdateTime)
class TokensUpdateTimeModelAdmin(ModelAdmin):
    """
    Настройки панели администратора модели TokensUpdateTime.
    """
    fields = ()
    list_display = (
        'id',
        'last_time_updated',
    )
    list_filter = (
        'last_time_updated',
    )
    search_fields = (
        'id',
    )
    ordering = (
        'id',
    )
