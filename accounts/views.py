from allauth.account.utils import send_email_confirmation
from django.contrib import messages
from django.contrib.auth import logout
from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse

from .forms import EmailChangeForm, ProfileForm
from .models import User


def profile_view(request, username=None):
    """
    Displays the profile of the user with the given username using @username syntax.
    If no username is provided, the profile of the currently logged in user is displayed.
    """
    if username:
        profile = get_object_or_404(User, username=username).profile
    else:
        try:
            profile = request.user.profile
        except:  # noqa: E722
            return redirect("account_login")
    return render(request, "account/profile.html", {"profile": profile})


@login_required
def profile_edit_view(request):
    form = ProfileForm(instance=request.user.profile)

    if request.method == "POST":
        form = ProfileForm(request.POST, request.FILES, instance=request.user.profile)
        if form.is_valid():
            form.save()
            return redirect("profile")

    onboarding = True if request.path == reverse("profile_onboarding") else False  # noqa: SIM210

    context = {"form": form, "onboarding": onboarding}
    return render(request, "account/profile_edit.html", context)


@login_required
def profile_settings_view(request):
    return render(request, "account/profile_settings.html")


@login_required
def email_change_view(request):
    if request.htmx:
        form = EmailChangeForm(instance=request.user)
        return render(request, "account/partials/email_change_form.html", {"form": form})

    if request.method == "POST":
        form = EmailChangeForm(request.POST, instance=request.user)

        if form.is_valid():
            # Check if the email already exists
            email = form.cleaned_data["email"]
            if User.objects.filter(email=email).exclude(id=request.user.id).exists():
                messages.warning(request, f"{email} is already in use.")
                return redirect("profile_settings")

            form.save()

            # Then Signal updates the email_address and sets "verified" to False

            # Then send confirmation email
            send_email_confirmation(request, request.user)

            return redirect("profile_settings")
        else:
            messages.warning(request, "Form not valid")
            return redirect("profile_settings")

    return redirect("index")


@login_required
def email_verify(request):
    """
    Send confirmation email to the user
    """
    send_email_confirmation(request, request.user)
    return redirect("profile_settings")


@login_required
def profile_delete_view(request):
    user = request.user
    if request.method == "POST":
        logout(request)
        user.delete()
        messages.success(request, "Account deleted, what a pity")
        return redirect("index")

    return render(request, "account/profile_delete.html")
