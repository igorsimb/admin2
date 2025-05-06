from django.forms import ModelForm
from django import forms
from .models import Profile, User


class ProfileForm(ModelForm):
    class Meta:
        model = Profile
        exclude = ["user"]
        widgets = {
            "image": forms.FileInput(),
            "display_name": forms.TextInput(attrs={"placeholder": "Add display name"}),
            "info": forms.Textarea(attrs={"rows:": 3, "placeholder": "Add info"}),
        }


class EmailChangeForm(ModelForm):
    email = forms.EmailField(required=True)

    class Meta:
        model = User
        fields = ["email"]
