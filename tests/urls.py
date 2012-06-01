# -*- encoding: utf-8 -*-


from django.conf.urls import patterns, include, url


urlpatterns = patterns('tests.views',
    url(r'^acces/(?P<jeton>\w+)$', 'dummy', name='dummy'),
)

