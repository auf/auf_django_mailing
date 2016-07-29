# -*- encoding: utf-8 -*-


try:
    from django.conf.urls.defaults import patterns, include, url
except ImportError:
    from django.conf.urls import patterns, include, url


urlpatterns = patterns('tests.views',
    url(r'^acces/(?P<jeton>\w+)$', 'dummy', name='dummy'),
)

