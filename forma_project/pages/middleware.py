"""Middleware for site-wide behaviour (e.g. logging unhandled exceptions)."""

from django.core.exceptions import PermissionDenied
from django.http import Http404
from django.utils.deprecation import MiddlewareMixin


class LogUnhandledExceptionMiddleware(MiddlewareMixin):
    """
    Persist unexpected exceptions (500-class) to HttpErrorLog.
    Http404 and PermissionDenied are left to the error handlers so they are not double-logged.
    """

    def process_exception(self, request, exception):
        if isinstance(exception, (Http404, PermissionDenied)):
            return None
        from .models import record_http_error_log

        record_http_error_log(request, 500, exception=exception)
        return None
