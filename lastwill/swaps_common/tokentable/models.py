from django.db import models

from lastwill.consts import ETH_ADDRESS


class Tokens(models.Model):
    address = models.CharField(max_length=50)
    token_name = models.CharField(max_length=512)
    token_short_name = models.CharField(max_length=64)
    decimals = models.IntegerField()
    image_link = models.CharField(max_length=512)


class TokensCoinMarketCap(models.Model):
    token_cmc_id = models.IntegerField(null=True)
    token_name = models.CharField(max_length=512)
    token_short_name = models.CharField(max_length=128)
    token_platform = models.CharField(max_length=128, null=True)
    token_address = models.CharField(max_length=128)
    image_link = models.CharField(max_length=512)
    token_rank = models.IntegerField(null=True, default=None)
    image = models.ImageField(
        upload_to=f'token_images/',
        default='token_images/fa-empire.png',
        blank=True,
    )
    token_price = models.CharField(max_length=100, null=True, default=None)
    updated_at = models.DateTimeField(auto_now=True)
    is_native = models.BooleanField(default=False)
    is_displayed=models.BooleanField(default=True)

    class Meta:
        unique_together = ['token_name', 'token_short_name']


class CoinGeckoToken(models.Model):
    """
    Хранит данные токенов с сайта CoinGecko.

    ---

    Поля:
    - title : str, 255 симв;
    - short_title : str, 64 симв., необязательное;
    - address : str, 50 симв., обязательное;
    - platform : str, 255 симв, необязательное;
    - decimals : decimal, макс. 255;
    - image_file : url, 200 симв., необязательное;
    - token_rank : int;
    - token_usd_price : decimal, макс. 255, макс. чисел после запятой 15;
    - created_at : date-time, автодобавляемое;
    - updated_at : date-time, автообновляемое;
    - is_native : bool, по-умолчанию False;
    - is_displayed : bool, по-умолчанию True;
    """
    title = models.CharField(max_length=255)
    short_title = models.CharField(max_length=255)
    coingecko_id = models.CharField(max_length=255)
    platform = models.CharField(
        max_length=255,
        default='',
        blank=True,
    )
    address = models.CharField(
        max_length=150,
        default='',
        blank=True,
    )
    decimals = models.PositiveIntegerField(default=18)
    source_image_link = models.URLField(
        max_length=512,
        default='',
        blank=True
    )
    image_file = models.ImageField(
        upload_to=f'token_images/',
        default='token_images/fa-empire.png',
        blank=True,
    )
    rank = models.IntegerField(default=0, blank=True)
    usd_price = models.DecimalField(
        max_digits=255,
        decimal_places=15,
        default=0,
        blank=True
    )
    created_at=models.DateTimeField(auto_now_add=True)
    updated_at=models.DateTimeField(auto_now=True)
    is_native=models.BooleanField(default=False)
    is_displayed=models.BooleanField(default=True)

    class Meta:
        db_table = 'coingecko_tokens'
        indexes = (
            models.Index(
                fields=['id', ]
            ),
        )
        unique_together = ['title', 'short_title']

    def save(self, *args, **kwargs):
        self.short_title = self.short_title.lower()

        if self.platform and not self.address:
            self.address = ETH_ADDRESS

        if self.title == 'Rubic' and self.short_title == 'rbc':
            self.rank = -1

        return super().save(*args, **kwargs)


class TokensUpdateTime(models.Model):
    last_time_updated = models.DateTimeField(auto_now_add=True)
