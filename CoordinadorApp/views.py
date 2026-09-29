from django.shortcuts import render


def home(request):
    return render(request, 'CoordinadorApp/index.html', {'sgr_role': 'Coordinador'})
