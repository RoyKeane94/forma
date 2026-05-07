from __future__ import annotations

import os

from django.core.files.base import ContentFile
from django.core.management.base import BaseCommand

from pages.models import ProofTestimonial
from pages.posters import poster_bytes_from_video_file


class Command(BaseCommand):
    help = 'Generate and save poster images for existing testimonial videos.'

    def add_arguments(self, parser):
        parser.add_argument(
            '--force',
            action='store_true',
            help='Regenerate posters even when a poster already exists.',
        )
        parser.add_argument(
            '--limit',
            type=int,
            default=0,
            help='Maximum number of testimonials to process (0 = no limit).',
        )

    def handle(self, *args, **options):
        force = bool(options['force'])
        limit = int(options['limit'] or 0)

        qs = ProofTestimonial.objects.exclude(video='').order_by('pk')
        if not force:
            qs = qs.filter(poster='')
        if limit > 0:
            qs = qs[:limit]

        processed = 0
        created = 0
        skipped = 0
        failed = 0

        for submission in qs:
            processed += 1
            if not submission.video:
                skipped += 1
                continue
            try:
                with submission.video.open('rb') as fh:
                    source_bytes = fh.read()
            except Exception as exc:
                failed += 1
                self.stdout.write(
                    self.style.ERROR(f'[{submission.pk}] Failed reading video: {exc}')
                )
                continue

            source_ext = os.path.splitext(submission.video.name or '')[1].lower() or '.mp4'
            poster_bytes = poster_bytes_from_video_file(
                source_bytes=source_bytes,
                source_ext=source_ext,
            )
            if not poster_bytes:
                failed += 1
                self.stdout.write(
                    self.style.WARNING(f'[{submission.pk}] Could not generate poster bytes')
                )
                continue

            try:
                poster_name = f'{os.path.splitext(os.path.basename(submission.video.name))[0]}.jpg'
                submission.poster.save(poster_name, ContentFile(poster_bytes), save=False)
                submission.save(update_fields=['poster'])
                created += 1
                self.stdout.write(self.style.SUCCESS(f'[{submission.pk}] Poster saved'))
            except Exception as exc:
                failed += 1
                self.stdout.write(
                    self.style.ERROR(f'[{submission.pk}] Failed saving poster: {exc}')
                )

        self.stdout.write(
            self.style.NOTICE(
                f'Processed {processed} testimonials. Saved: {created}, Skipped: {skipped}, Failed: {failed}.'
            )
        )
