from django.shortcuts import render
from django.contrib.auth.decorators import login_required


@login_required
def home(request):
    """Clean TrustBuilding dashboard home view."""
    context = {
        'user': request.user,
        'page_title': 'TrustBuilding Dashboard',
    }
    return render(request, 'dashboard/home.html', context)


@login_required
def topbar_search(request):
    """Global topbar search placeholder."""
    query = request.GET.get('q', '').strip()
    return render(request, 'partials/topbar_search_results.html', {
        'query': query,
        'results': [],
    })

