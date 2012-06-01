# -*- encoding: utf-8 -*-



DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.sqlite3',
        'NAME': 'tests.sqlite'
    }
}

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
