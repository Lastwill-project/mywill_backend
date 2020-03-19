from django.core.mail import send_mail
from django.contrib.sites.shortcuts import get_current_site
from allauth.account.adapter import DefaultAccountAdapter
from ducx_wish.settings import DUCATUSX_URL, EMAIL_HOST_USER
from email_messages import register_subject, register_text


class SubSiteRegistrationAdapter(DefaultAccountAdapter):

    def send_confirmation_mail(self, request, emailconfirmation, signup):
        welcome_head = ''
        current_site = get_current_site(request)
        activate_url = self.get_email_confirmation_url(request, emailconfirmation)

        to_user = emailconfirmation.email_address.user
        to_email = emailconfirmation.email_address.email

        host = self.request.META['HTTP_HOST']

        from_email = EMAIL_HOST_USER
        welcome_head = 'MyWish Platform'

        send_mail(
            register_subject,
            register_text.format(
                subsite_name=welcome_head,
                user_display=to_user,
                activate_url=activate_url
            ),
            from_email,
            [to_email]
        )
