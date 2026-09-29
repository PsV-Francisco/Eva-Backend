from django.shortcuts import render


def home(request):
    return render(request, 'DelegadoApp/index.html', {'sgr_role': 'Delegado'})
