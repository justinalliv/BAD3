from django.http import JsonResponse
from django.shortcuts import redirect

from .models import Customer, OperationsManager, SalesRepresentative, Technician


ROLE_HOME = {
    'customer': 'home',
    'om': 'om_home',
    'technician': 'technician_home',
    'sales': 'sales_representative_home',
}

ROLE_SESSION_KEYS = {
    'customer': 'customer_id',
    'om': 'om_id',
    'technician': 'technician_id',
    'sales': 'sales_representative_id',
}

ROLE_MODELS = {
    'customer': Customer,
    'om': OperationsManager,
    'technician': Technician,
    'sales': SalesRepresentative,
}

ROLE_PREFIXES = (
    ('om', '/om/'),
    ('technician', '/technician/'),
    ('sales', '/sales-representative/'),
    ('sales', '/sales/'),
)

CUSTOMER_PREFIXES = (
    '/profile/',
    '/pending-payment/',
    '/payment-instructions/',
    '/submit-payment-proof/',
    '/properties/',
    '/book-inspection/',
    '/service-status/',
)

SHARED_PROTECTED_PREFIXES = (
    '/payment-proofs/',
)

PUBLIC_EXACT_PATHS = {
    '/',
    '/signup/',
    '/login/',
    '/logout/',
}

PUBLIC_PREFIXES = (
    '/admin/',
    '/static/',
    '/media/',
)


class RoleAccessMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        required_roles = self._required_roles(request.path_info)
        if required_roles:
            current_role = self._current_role(request)
            if current_role is None:
                return self._unauthenticated_response(request)
            if current_role not in required_roles:
                return self._forbidden_response(request, current_role)

        response = self.get_response(request)

        if required_roles:
            response['Cache-Control'] = 'no-store, no-cache, must-revalidate, max-age=0'
            response['Pragma'] = 'no-cache'
            response['Expires'] = '0'

        return response

    def _required_roles(self, path):
        if path in PUBLIC_EXACT_PATHS or any(path.startswith(prefix) for prefix in PUBLIC_PREFIXES):
            return None

        for role, prefix in ROLE_PREFIXES:
            if path.startswith(prefix):
                return {role}

        if any(path.startswith(prefix) for prefix in CUSTOMER_PREFIXES):
            return {'customer'}

        if any(path.startswith(prefix) for prefix in SHARED_PROTECTED_PREFIXES):
            return {'customer', 'om', 'sales'}

        return None

    def _current_role(self, request):
        valid_roles = []

        for role, session_key in ROLE_SESSION_KEYS.items():
            account_id = request.session.get(session_key)
            if not account_id:
                continue

            account = ROLE_MODELS[role].objects.filter(id=account_id).first()
            if not account or not getattr(account, 'is_active', True):
                request.session.flush()
                return None
            valid_roles.append(role)

        if len(valid_roles) != 1:
            if valid_roles:
                request.session.flush()
            return None

        return valid_roles[0]

    def _wants_json(self, request):
        accept = request.headers.get('Accept', '')
        content_type = request.headers.get('Content-Type', '')
        return (
            request.headers.get('X-Requested-With') == 'XMLHttpRequest'
            or 'application/json' in accept
            or 'application/json' in content_type
        )

    def _unauthenticated_response(self, request):
        if self._wants_json(request):
            return JsonResponse({'detail': 'Authentication required.'}, status=401)
        return redirect('login')

    def _forbidden_response(self, request, current_role):
        if self._wants_json(request):
            return JsonResponse({'detail': 'Access denied.'}, status=403)
        return redirect(ROLE_HOME[current_role])
