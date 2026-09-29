from django.shortcuts import render


def home(request):
    return render(request, 'SupervisorApp/index.html', {'sgr_role': 'Supervisor'})
