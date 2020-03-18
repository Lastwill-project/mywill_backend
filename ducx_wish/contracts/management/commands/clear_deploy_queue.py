from django.core.management.base import BaseCommand, CommandError
from ducx_wish.deploy.models import *

class Command(BaseCommand):
    help = 'Clear queue of all Deploy addresses'

    def handle(self, *args, **options):
        addresses = DeployAddress.objects.all()
        for address in addresses:
            address.locked_by = None
            address.save()

        self.stdout.write('Successfully clear queue')