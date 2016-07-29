# -*- encoding: utf-8 -*-
"""
=================
Module de mailing
=================

Fonctionalités :
----------------
* Envoi de courriels à une liste de destinataires
* Le corps du courriel est rendu comme template django
* Les envois sont loggés, avec les éventuelles erreurs
* La répétition de l'envoi à une liste ne renvoie que les courriels de la liste
qui n'avaient pas été envoyés, pour cause d'interruption du processus, ou
d'erreur. Les destinataires dont l'adresse aurait été modifiée sont également
inclus automatiquement dans un réenvoi.

Fonctionnement :
----------------
* Définir un modèle de courriel, à l'aide du modèle `ModeleCourriel`
* Les instances du modèle `Enveloppe` représentent toutes les informations
pour envoyer un courriel : elles ont besoin d'un `ModeleCourriel`.
* Pour utiliser cette application, il faut définir son propre modèle pour pouvoir
personnaliser le paramétrage des enveloppes, c'est-à-dire leur fournir l'adresse
du destinataire et un contexte pour le rendu du corps du message. Cette classe
doit :
  - comporter deux méthodes, `get_contexte_corps()` et  `get_adresse()`
  - comporter une ForeignKey vers le modèle `Enveloppe`, avec unique=True
  - elle doit être déclarée dans les settings dans le paramètre
  `MAILING_MODELE_PARAMS_ENVELOPPE` sous le format 'nom_application.nom_modele'
* L'envoi est temporisé, d'un nombre de secondes indiqué dans le paramètre
`MAILING_TEMPORISATION`. Défaut: 2 secondes

"""
import random
import smtplib
import string
import time
from distutils import version
import django
from django.core.exceptions import ImproperlyConfigured
from django.core.mail.message import EmailMessage
from django.core.urlresolvers import reverse
from django.db import models, transaction
try:
    from django.models import get_model
except ImportError:
    from django.apps import apps
from django.db.models.fields import CharField, TextField, BooleanField, DateTimeField
from django.db.models.fields.related import ForeignKey
import datetime
from django.template.base import Template
from django.template.context import Context
from django.conf import settings

class ModeleCourriel(models.Model):
    """
    Représente un modèle de courriel. Le corps sera interprété comme un template
    django
    """
    code = CharField(max_length=8, unique=True)
    sujet = CharField(max_length=256)
    corps = TextField()
    html = BooleanField(verbose_name=u"Le corps est au format HTML")
    
    def __unicode__(self):
        return self.code + u" / " + self.sujet


TAILLE_JETON = 32

def generer_jeton(taille=TAILLE_JETON):
    return ''.join(random.choice(string.letters + string.digits)\
        for i in xrange(TAILLE_JETON))


class EnveloppeParametersNotAvailable(Exception):
    pass


class Enveloppe(models.Model):
    """
    Représente un envoi à faire, avec toutes les informations nécessaires.
    """
    modele = ForeignKey(ModeleCourriel)

    def get_params(self):
        """
        Retourne les paramètres associés à cette enveloppe.
        Le mécanisme est copié sur celui des profils utilisateurs
        (cf. `django.contrib.auth.User.get_profile`) et permet à chaque site
        de définir l'adresse d'envoi et le contexte de rendu du template
        selon ses propres besoins.

        On s'attend à ce que la classe soit indiquée au format 'application.model'
        dans le setting MODELE_PARAMS_ENVELOPPE, et que cette classe ait une
        ForeignKey vers `Enveloppe`, avec unique=True

        Voir aussi l'article de James Bennett à l'adresse :
        http://www.b-list.org/weblog/2006/jun/06/django-tips-extending-user-model/
        """
        if not hasattr(self, '_params_cache'):
            if not getattr(settings, 'MAILING_MODELE_PARAMS_ENVELOPPE', False):
                raise EnveloppeParametersNotAvailable()
            try:
                app_label, model_name = settings.MAILING_MODELE_PARAMS_ENVELOPPE.split('.')
            except ValueError:
                raise EnveloppeParametersNotAvailable()
            try:
                if hasattr(models, 'get_model'):  # django < 1.7
                    model = get_model(app_label, model_name)
                else:
                    model = apps.get_model(app_label, model_name)
                if model is None:
                    raise EnveloppeParametersNotAvailable()
                self._params_cache = model._default_manager.using(
                    self._state.db).get(enveloppe__id__exact=self.id)
                self._params_cache.user = self
            except (ImportError, ImproperlyConfigured):
                raise EnveloppeParametersNotAvailable()
        return self._params_cache

    def get_corps_context(self):
        context = self.get_params().get_corps_context()
        return context

    def get_adresse(self):
        return self.get_params().get_adresse()

class EntreeLog(models.Model):
    enveloppe = ForeignKey(Enveloppe)
    adresse = CharField(max_length=256)
    date_heure_envoi = DateTimeField(default=datetime.datetime.now)
    erreur = TextField(null=True)


def envoyer(code_modele, adresse_expediteur, site=None, url_name=None,
            limit=None, retry_errors=True):
    u"""
    Cette fonction procède à l'envoi proprement dit, pour toutes les enveloppes
    du modele ayant pour code :code_modele. Si ``site``, ``url_name`` sont spécifiés
    et que les enveloppes passent un paramètre ``jeton`` dans leur contexte,
    une url sera générée et passée comme variable au template.
    :param code_modele: le code du modèle pour lequel faire l'envoi
    :param adresse_expediteur:
    :param site: une instance de django.contrib.sites (pour la génération de l'URL)
    :param url_name: le nom de l'URL à générer
    :param limit: indique un nombre maximal de courriels à envoyer pour cet appel
    :param retry_errors: les envois en erreur doivent-ils être retentés ou non ?

    .. warning:: L'utilisation conjointe d'une limite (paramètre ``limit``) et
     de ``retry_errors`` pourrait faire en sorte que certains courriels ne soient
     jamais envoyés (si il y a plus de courriels en erreur que ``limit``)
    """
    modele = ModeleCourriel.objects.get(code=code_modele)
    enveloppes = Enveloppe.objects.filter(modele=modele)
    temporisation = getattr(settings, 'MAILING_TEMPORISATION', 2)
    counter = 0
    for enveloppe in enveloppes:
        # on vérifie qu'on n'a pas déjà envoyé ce courriel à
        # cet établissement et à cette adresse
        adresse_envoi = enveloppe.get_adresse()
        entree_log = EntreeLog.objects.filter(enveloppe=enveloppe,
                                              adresse=adresse_envoi)
        if retry_errors:
            entree_log = entree_log.filter(erreur__isnull=True)

        if entree_log.count() > 0:
            continue

        modele_corps = Template(enveloppe.modele.corps)
        contexte_corps = enveloppe.get_corps_context()

        if site and url_name and 'jeton' in contexte_corps:
            url = 'http://%s%s' % (
                site.domain,
                reverse(url_name,
                        kwargs={'jeton': contexte_corps['jeton']}))
            contexte_corps['url'] = url

        corps = modele_corps.render(Context(contexte_corps))
        message = EmailMessage(enveloppe.modele.sujet,
                               corps,
                               adresse_expediteur,  # adresse de retour
                               [adresse_envoi],  # adresse du destinataire
                               headers={'precedence': 'bulk'}
                               # selon les conseils de google
                               )
        envoyer_message(adresse_envoi, enveloppe, message)
        counter += 1
        time.sleep(temporisation)
        if limit and counter >= limit:
            break


def get_envoyer_message():
    django_version = django.get_version()
    if version.StrictVersion(django_version) < version.StrictVersion('1.6'):

        def envoyer_msg(adresse_envoi, enveloppe, message):
            try:
                envoyer_message(adresse_envoi, enveloppe, message)
            except:
                transaction.rollback()
                raise

        envoyer_msg = transaction.commit_manually(envoyer_msg)
    else:

        def envoyer_msg(adresse_envoi, enveloppe, message):
            with transaction.atomic():
                envoyer_message(adresse_envoi, enveloppe, message)
    return envoyer_msg


def envoyer_message(adresse_envoi, enveloppe, message):
    message.content_subtype = "html" if enveloppe.modele.html else "text"
    new_entree_log = EntreeLog()
    new_entree_log.enveloppe = enveloppe
    new_entree_log.adresse = adresse_envoi
    try:
        # Attention en DEV, devrait simplement écrire le courriel
        # dans la console, cf. paramètre EMAIL_BACKEND dans conf.py
        # En PROD, supprimer EMAIL_BACKEND (ce qui fera retomber sur
        # le défaut qui est d'envoyer par SMTP). Même chose en TEST,
        # mais attention car les adresses qui sont dans la base
        # seront utilisées: modifier les données pour y mettre des
        # adresses de test plutôt que les vraies
        message.send()
    except (smtplib.socket.error, smtplib.SMTPException) as e:
        new_entree_log.erreur = e.__str__()
    new_entree_log.save()


