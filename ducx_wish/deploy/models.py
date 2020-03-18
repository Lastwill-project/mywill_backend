from django.db import models

class Network(models.Model):
    name = models.CharField(max_length=128, db_index=True)


class DeployAddress(models.Model):
    address = models.CharField(max_length=50)
    locked_by = models.IntegerField(null=True, default=None)
    network = models.ForeignKey(Network, default=1)
