"""List every routed view and the permission-matrix key(s) protecting it.

    python manage.py audit_permissions            # all views
    python manage.py audit_permissions --missing  # only views WITHOUT @perm_required (to review new code)
"""
from django.core.management.base import BaseCommand
from django.urls import URLPattern, URLResolver, get_resolver


def _walk(patterns, base=''):
    for p in patterns:
        route = base + str(p.pattern)
        if isinstance(p, URLResolver):
            yield from _walk(p.url_patterns, route)
        elif isinstance(p, URLPattern):
            yield route, p


class Command(BaseCommand):
    help = 'Show which URL views are protected by @perm_required (and with which keys).'

    def add_arguments(self, parser):
        parser.add_argument('--missing', action='store_true', help='only views without @perm_required')

    def handle(self, *args, **opts):
        covered = missing = 0
        for route, pattern in _walk(get_resolver().url_patterns):
            cb = pattern.callback
            keys = getattr(cb, 'required_permissions', None)
            post = getattr(cb, 'required_post_permissions', ())
            if keys:
                covered += 1
                if opts['missing']:
                    continue
                extra = '  (POST also needs: %s)' % ', '.join(post) if post else ''
                self.stdout.write('%-55s %-35s %s%s' % (route, pattern.name or '-', ', '.join(keys), extra))
            else:
                missing += 1
                self.stdout.write(self.style.WARNING('%-55s %-35s -- no @perm_required' % (route, pattern.name or '-')))
        self.stdout.write(self.style.SUCCESS('\n%d views protected, %d without @perm_required' % (covered, missing)))
