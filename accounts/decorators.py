"""Portal access guards for tenant membership and owner role."""

from __future__ import annotations

import functools

from django.contrib import messages
from django.shortcuts import redirect

from .services import get_primary_tenant, user_is_tenant_owner


def primary_tenant_required(view_func):
    """Redirect users without a primary tenant instead of raising 500s."""

    @functools.wraps(view_func)
    def _wrapped(request, *args, **kwargs):
        tenant = get_primary_tenant(request.user)
        if tenant is None:
            messages.error(request, 'Your account is not linked to an organization.')
            return redirect('home')
        return view_func(request, *args, **kwargs)

    return _wrapped


def tenant_owner_required(view_func):
    """Restrict destructive portal POST actions to organization owners."""

    @functools.wraps(view_func)
    def _wrapped(request, *args, **kwargs):
        if request.method == 'POST' and not user_is_tenant_owner(request.user):
            messages.error(request, 'Only organization owners can perform this action.')
            return redirect('dashboard')
        return view_func(request, *args, **kwargs)

    return _wrapped
