from __future__ import annotations

from django.core.files.storage import default_storage
from django.core.management.base import BaseCommand

from pages.models import ProofTestimonial


def _referenced_file_names() -> set[str]:
    names: set[str] = set()
    for row in ProofTestimonial.objects.values_list('video', 'poster'):
        video_name = (row[0] or '').strip()
        poster_name = (row[1] or '').strip()
        if video_name:
            names.add(video_name)
        if poster_name:
            names.add(poster_name)
    return names


def _list_all_files(prefix: str) -> set[str]:
    files: set[str] = set()
    stack = [prefix.rstrip('/')]
    while stack:
        current = stack.pop()
        try:
            directories, leaf_files = default_storage.listdir(current)
        except Exception:
            continue

        for filename in leaf_files:
            filename = (filename or '').strip()
            if not filename:
                continue
            files.add(f'{current}/{filename}')

        for directory in directories:
            directory = (directory or '').strip().strip('/')
            if not directory:
                continue
            stack.append(f'{current}/{directory}')
    return files


class Command(BaseCommand):
    help = 'Delete orphaned files from proof/videos and proof/posters not referenced by testimonials.'

    def add_arguments(self, parser):
        parser.add_argument(
            '--apply',
            action='store_true',
            help='Actually delete orphaned files. Without this flag, prints what would be deleted.',
        )

    def handle(self, *args, **options):
        apply = bool(options['apply'])
        referenced = _referenced_file_names()
        stored = _list_all_files('proof/videos') | _list_all_files('proof/posters')
        orphaned = sorted(stored - referenced)

        mode_label = 'DELETE' if apply else 'DRY-RUN'
        self.stdout.write(f'[{mode_label}] Referenced: {len(referenced)}')
        self.stdout.write(f'[{mode_label}] Stored: {len(stored)}')
        self.stdout.write(f'[{mode_label}] Orphaned: {len(orphaned)}')

        if not orphaned:
            self.stdout.write(self.style.SUCCESS('No orphaned proof media found.'))
            return

        if not apply:
            for path in orphaned[:50]:
                self.stdout.write(f'  would delete: {path}')
            if len(orphaned) > 50:
                self.stdout.write(f'  ... plus {len(orphaned) - 50} more')
            self.stdout.write(self.style.WARNING('Dry run only. Re-run with --apply to delete.'))
            return

        deleted = 0
        failed = 0
        for path in orphaned:
            try:
                default_storage.delete(path)
                deleted += 1
            except Exception as exc:
                failed += 1
                self.stdout.write(self.style.ERROR(f'Failed deleting {path}: {exc}'))

        self.stdout.write(
            self.style.SUCCESS(
                f'Deletion complete. Deleted: {deleted}, Failed: {failed}, Total orphaned: {len(orphaned)}.'
            )
        )
