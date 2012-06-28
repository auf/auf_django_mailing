# -*- encoding: utf-8 -*-
from django.contrib.sites.models import Site
from django.core import mail
from django.db import models
from django.db.models.fields import CharField
from django.db.models.fields.related import ForeignKey

from django.test import TestCase

from auf.django.mailing.models import EntreeLog, Enveloppe, envoyer,\
    ModeleCourriel, generer_jeton, TAILLE_JETON

class TestDestinataire(models.Model):
    adresse_courriel = CharField(max_length=128)
    nom = CharField(max_length=64)


class TestEnveloppeParams(models.Model):
    destinataire = ForeignKey(TestDestinataire)
    enveloppe = ForeignKey(Enveloppe, unique=True)
    jeton = CharField(max_length=TAILLE_JETON)

    def save(self, *args, **kwargs):
        if not self.jeton:
            self.jeton = generer_jeton(TAILLE_JETON)
        super(TestEnveloppeParams, self).save(*args, **kwargs)

    def get_adresse(self):
        return self.destinataire.adresse_courriel

    def get_corps_context(self):
        context = {
            'nom_destinataire' : self.destinataire.nom,
            'jeton': self.jeton,
        }
        return context


class MailTest(TestCase):

    def setUp(self):
        self.dest1 = TestDestinataire(adresse_courriel='dest1@test.org',
            nom='nom dest1')
        self.dest1.save()
        self.dest2 = TestDestinataire(adresse_courriel='dest2@test.org',
            nom='nom dest2')
        self.dest2.save()
        self.modele_courriel = ModeleCourriel(code='mod_test',
            sujet='sujet_modele',  corps='{{ nom_destinataire }}{{ url }}',
            html=False)
        self.modele_courriel.save()

    def get_site(self):
        return Site.objects.all()[0]

    def create_enveloppe_params(self):
        enveloppe = Enveloppe(modele=self.modele_courriel)
        enveloppe.save()
        enveloppe_params = TestEnveloppeParams(enveloppe=enveloppe, destinataire=self.dest1)
        enveloppe_params.save()
        return enveloppe, enveloppe_params


    def test_envoi_simple(self):
        enveloppe, enveloppe_params = self.create_enveloppe_params()

        envoyer(self.modele_courriel.code, 'expediteur@test.org', self.get_site(), 'dummy')

        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(mail.outbox[0].body, self.dest1.nom +
            'http://example.com/acces/' + enveloppe_params.jeton)
        self.assertEqual(mail.outbox[0].to, [self.dest1.adresse_courriel])

        entrees_log = EntreeLog.objects.all()
        self.assertEqual(len(entrees_log), 1)
        self.assertEqual(entrees_log[0].enveloppe, enveloppe)
        self.assertEqual(entrees_log[0].adresse, self.dest1.adresse_courriel)

        # normalement un deuxième envoi ne devrait rien envoyer de ce qui a
        # déjà été logué
        envoyer(self.modele_courriel.code, 'expediteur@test.org', self.get_site(), 'dummy')
        self.assertEqual(len(mail.outbox), 1)
        entrees_log = EntreeLog.objects.all()
        self.assertEqual(len(entrees_log), 1)

        # par contre si une erreur s'est produite l'envoi devrait être retenté
        entrees_log[0].erreur = u'libellé erreur'
        entrees_log[0].save()
        envoyer(self.modele_courriel.code, 'expediteur@test.org', self.get_site(), 'dummy')
        self.assertEqual(len(mail.outbox), 2)
        entrees_log = EntreeLog.objects.all()
        self.assertEqual(len(entrees_log), 2)

        entrees_log[0].delete()

        # le courriel devrait également être renvoyé si l'adresse du destinataire
        # a changé
        self.dest1.adresse_courriel = 'autre_adresse@test.org'
        self.dest1.save()
        envoyer(self.modele_courriel.code, 'expediteur@test.org', self.get_site(), 'dummy')
        self.assertEqual(len(mail.outbox), 3)
        entrees_log = EntreeLog.objects.all()
        self.assertEqual(len(entrees_log), 2)








