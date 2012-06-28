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
from django.core.exceptions import ImproperlyConfigured
from django.core.mail.message import EmailMessage
from django.core.urlresolvers import reverse
from django.db import models, transaction
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
                model = models.get_model(app_label, model_name)
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

@transaction.commit_manually
def envoyer(code_modele, adresse_expediteur, site=None, url_name=None):
    modele = ModeleCourriel.objects.get(code=code_modele)
    enveloppes = Enveloppe.objects.filter(modele=modele)
    temporisation = getattr(settings, 'MAILING_TEMPORISATION', 2)
    try:
        for enveloppe in enveloppes:
            # on vérifie qu'on n'a pas déjà envoyé ce courriel à
            # cet établissement et à cette adresse
            adresse_envoi = enveloppe.get_adresse()
            entree_log = EntreeLog.objects.filter(enveloppe=enveloppe,
                erreur__isnull=True, adresse=adresse_envoi)
            if entree_log.count() > 0:
                continue

            modele_corps = Template(enveloppe.modele.corps)
            contexte_corps = enveloppe.get_corps_context()

            if site and url_name and 'jeton' in contexte_corps:
                url = 'http://%s%s' % (site.domain,
                                    reverse(url_name,
                                        kwargs={'jeton': contexte_corps['jeton']}))
                contexte_corps['url'] = url

            corps = modele_corps.render(Context(contexte_corps))
            message = EmailMessage(enveloppe.modele.sujet,
                corps,
                adresse_expediteur,     # adresse de retour
                [adresse_envoi],                # adresse du destinataire
                headers={'precedence' : 'bulk'} # selon les conseils de google
            )
            try:
                # Attention en DEV, devrait simplement écrire le courriel
                # dans la console, cf. paramètre EMAIL_BACKEND dans conf.py
                # En PROD, supprimer EMAIL_BACKEND (ce qui fera retomber sur le défaut
                # qui est d'envoyer par SMTP). Même chose en TEST, mais attention
                # car les adresses qui sont dans la base seront utilisées:
                # modifier les données pour y mettre des adresses de test plutôt que
                # les vraies
                message.content_subtype = "html" if enveloppe.modele.html else "text"
                entree_log = EntreeLog()
                entree_log.enveloppe = enveloppe
                entree_log.adresse = adresse_envoi
                message.send()
                time.sleep(temporisation)
            except smtplib.SMTPException as e:
                entree_log.erreur = e.__str__()
            entree_log.save()
            transaction.commit()
    except:
        transaction.rollback()
        raise

    transaction.commit() # nécessaire dans le cas où rien n'est envoyé, à cause du décorateur commit_manually

