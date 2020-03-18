from django.conf.urls import url
from django.contrib import admin
from ducx_wish.contracts.submitting.views import create_contract_swaps


class LastWillAdminSite(admin.AdminSite):
    def get_urls(self):
        urls = admin.site.get_urls()

        admin_urls = [
            url(r'^create_contract_swaps/', create_contract_swaps),
        ]
        return urls + admin_urls


lastwill_admin = LastWillAdminSite(name='lastwill_admin')
