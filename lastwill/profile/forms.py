from django import forms
from django.core.mail import send_mail
from django.contrib.auth.forms import PasswordResetForm
from django.contrib.sites.shortcuts import get_current_site
from django.contrib.auth.tokens import default_token_generator
from django.utils.http import urlsafe_base64_encode
from django.utils.encoding import force_bytes
from lastwill.settings import MY_WISH_URL, SWAPS_URL, EMAIL_HOST_USER, EMAIL_HOST_USER_SWAPS
from lastwill.contracts.submodels.swaps import sendEMail
from email_messages import password_reset_subject, password_reset_text


class SubSitePasswordResetForm(PasswordResetForm):

    def save(self,
             use_https=False, token_generator=default_token_generator,
             request=None):
        """
        Generate a one-use only link for resetting password and send it to the
        user.
        """
        to_email = self.cleaned_data["email"]

        for user in self.get_users(to_email):
            protocol = 'https' if use_https else 'http'
            u_id = urlsafe_base64_encode(force_bytes(user.pk)).decode('utf-8')
            u_token = token_generator.make_token(user)
            subsite_domain = request.META['HTTP_HOST']

            token_generator_link = '{protocol}://{domain}/reset/{uid}/{token}/'.format(
                protocol=protocol,
                domain=subsite_domain,
                uid=u_id,
                token=u_token
            )

            if subsite_domain == MY_WISH_URL:
                from_email = EMAIL_HOST_USER
                subsite_name = 'MyWish Platform'

                send_mail(
                    password_reset_subject.format(subsite_name=subsite_name),
                    password_reset_text.format(
                        subsite_name=subsite_name,
                        user_display=user,
                        password_reset_url=token_generator_link
                    ),
                    from_email,
                    [user.username]
                )

            if subsite_domain == SWAPS_URL:
                # from_email = EMAIL_HOST_USER_SWAPS
                subsite_name = "SWAPS.NETWORK"

                sendEMail(
                    password_reset_subject.format(subsite_name=subsite_name),
                    password_reset_text.format(
                        subsite_name=subsite_name,
                        user_display=user,
                        password_reset_url=token_generator_link
                    ),
                    # from_email,
                    user.username
                )
