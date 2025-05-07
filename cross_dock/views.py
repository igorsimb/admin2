from django.shortcuts import render


def index(request):
    """Temporary view for testing purposes"""
    return render(request, "cross_dock/index.html")
