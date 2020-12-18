from django.db import models


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
    image = models.ImageField(upload_to='token_images/', default='token_images/')
    token_price = models.CharField(max_length=100, null=True, default=None)
    updated_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ('id', 'token_name', 'token_short_name')


class TokensUpdateTime(models.Model):
    last_time_updated = models.DateTimeField(auto_now_add=True)
