from allauth.account.models import EmailAddress
from django.db.models.signals import post_save, pre_save
from django.dispatch import receiver

from .models import User, Profile


@receiver(post_save, sender=User)
def create_profile(sender, instance, created, **kwargs):
    user = instance
    if created:
        Profile.objects.create(user=user)
    else:
        # update allauth email_address if exists
        try:
            email_address = EmailAddress.objects.get_primary(user)
            if email_address.email != user.email:
                email_address.email = user.email
                email_address.verified = False
                email_address.save()
        except:
            # if allauth email_address doesn't exist, create one
            EmailAddress.objects.create(user=user, email=user.email, primary=True, verified=False)


@receiver(pre_save, sender=User)
def lower_case_username(sender, instance, **kwargs):
    """
    Convert username to lowercase.
    """
    if instance.username:
        instance.username = instance.username.lower()
