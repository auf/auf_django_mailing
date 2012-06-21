# -*- encoding: utf-8 -*-



DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.sqlite3',
        'NAME': 'tests.sqlite'
    }
}

#DATABASES = {
#    'default': {
#        'ENGINE': 'django.db.backends.mysql',
#        'NAME': 'tests_mailing',
#        'USER': 'ag',
#        'PASSWORD': '2S6m9ziup2Xy',
#        'HOST' : 'new-dev.auf',
#        'HOST' : '/var/run/mysqld/mysqld-ram.sock',
#        'USER': 'root',
#        'HOST' : '127.0.0.1',
#        'PORT' : '65432'
#    }
#}

INSTALLED_APPS = (
    'django.contrib.sites',
    'django.contrib.contenttypes',
    'auf.django.mailing',
    'tests'
    )

EMAIL_BACKEND = 'django.core.mail.backends.locmem.EmailBackend'

MAILING_MODELE_PARAMS_ENVELOPPE = 'tests.TestEnveloppeParams'
MAILING_TEMPORISATION = 0

SECRET_KEY = 'not-secret'

ROOT_URLCONF = 'tests.urls'
