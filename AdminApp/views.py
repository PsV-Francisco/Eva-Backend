from django.shortcuts import render


def home(request):
    return render(request, 'AdminApp/index.html', {'sgr_role': 'Admin'})
