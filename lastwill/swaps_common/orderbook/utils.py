import random
from string import ascii_lowercase, digits


def _get_memo():
    """
        Returns a randomly generated hash string.
    """
    return '0x' + ''.join(
        random.choice('abcdef'.join(digits)) for _ in range(64)
    )


def _get_unique_link():
    """
        Returns a randomly generated string.
    """
    return ''.join(
        random.choice(ascii_lowercase.join(digits)) for _ in range(6)
    )
