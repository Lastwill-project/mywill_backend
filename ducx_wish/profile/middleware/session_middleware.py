import time

from django.conf import settings
from django.utils.cache import patch_vary_headers
from django.utils.http import cookie_date
from django.contrib.sessions.middleware import SessionMiddleware


class CrossDomainSessionMiddleware:

    def __init__(self, get_response):
        self.get_response = get_response
        # One-time configuration and initialization.

    def __call__(self, request):
        # Code to be executed for each request before
        # the view (and later middleware) are called.

        response = self.get_response(request)

        # Code to be executed for each request/response after
        # the view is called.
        if response.cookies:
            host = request.get_host()
            # check if it's a different domain
            if host not in settings.SESSION_COOKIE_DOMAIN:
                domain = ".{domain}".format(domain=host)
                for cookie in response.cookies:
                    if 'domain' in response.cookies[cookie]:
                        response.cookies[cookie]['domain'] = domain

        return response


class SessionHostDomainMiddleware(SessionMiddleware):
    def process_response(self, request, response):
        """
        If request.session was modified, or if the configuration is to save the
        session every time, save the changes and set a session cookie.
        """
        try:
            accessed = request.session.accessed
            modified = request.session.modified
        except AttributeError:
            pass
        else:
            if accessed:
                patch_vary_headers(response, ('Cookie',))
            if modified or settings.SESSION_SAVE_EVERY_REQUEST:
                if request.session.get_expire_at_browser_close():
                    max_age = None
                    expires = None
                else:
                    max_age = request.session.get_expiry_age()
                    expires_time = time.time() + max_age
                    expires = cookie_date(expires_time)
                # Save the session data and refresh the client cookie.
                # Skip session save for 500 responses, refs #3881.
                if response.status_code != 500:
                    request.session.save()
                    host = request.get_host().split(':')[0]
                    response.set_cookie(settings.SESSION_COOKIE_NAME,
                            request.session.session_key, max_age=max_age,
                            expires=expires, domain=host,
                            path=settings.SESSION_COOKIE_PATH,
                            secure=settings.SESSION_COOKIE_SECURE or None,
                            httponly=settings.SESSION_COOKIE_HTTPONLY or None)
        return response
