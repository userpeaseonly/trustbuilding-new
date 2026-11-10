class SubdomainRoutingMiddleware:
    """
    Routes requests arriving at about.trust-building.uz (or subdomains starting with 'about.')
    directly to the landing application URLconf.
    Main domain requests (trust-building.uz) continue through root URLconf as normal.
    """
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        host = request.get_host().split(':')[0].lower()
        if host.startswith('about.') or host == 'about.localhost':
            request.urlconf = 'landing.urls'
        return self.get_response(request)
