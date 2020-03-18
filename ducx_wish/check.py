import re
from string import ascii_letters, digits
from rest_framework.serializers import ValidationError

def die(message):
    raise ValidationError(code=400, detail=message)


def is_address(string):
    re.match('^0[xX][a-fA-F\d]{40}$', string) or die('{} is not a valid ethereum address'.format(string))


def is_email(string):
    # django.core.validators.validate_email does not eat emails without a dot 
    # like user@localserver user@[IPv6:2001:db8::1] but angular does
    # EmailValidator has whitelist for domains, but not regex so whitelist=['.*'] does not work
    # so there custom simplified check
    re.match('.*@.*', string) or die('{} is not a valid email'.format(string))


def is_percent(number):
    try:
        number = int(number)
        if number < 1 or number > 100:
            raise ValueError
    except ValueError:
        die('{} is bad percent'.format(number))


def is_sum_eq_100(iterable):
    sum(iterable) == 100 or die('percentage sum is {} not 100'.format(sum(iterable)))


def is_eos_address(string):
    re.match('^[1-5a-z\.]{1,12}$', string) or die('{} is not a valid eos address'.format(string))

def is_eos_public(string):
    all(x in ascii_letters + digits for x in string) or die('{} is not a valid public key'.format(string))
