import logging
import threading

from django.conf import settings
from django.core.mail import send_mail
from django.db import close_old_connections, transaction
from django.urls import reverse

from .models import TrainerProfile

logger = logging.getLogger(__name__)


def _dashboard_review_url(site_base_url: str) -> str:
    path = reverse('pages:proof_notifications')
    return f'{site_base_url.rstrip("/")}{path}'


def send_new_testimonial_review_email(profile: TrainerProfile, *, site_base_url: str) -> None:
    user = profile.user
    email = (user.email or '').strip()
    if not email:
        return

    first_name = (profile.first_name or user.first_name or '').strip() or 'there'
    review_link = _dashboard_review_url(site_base_url)
    message = f"""Hi {first_name},

A client just submitted a testimonial for your Forma profile. Head to your dashboard to approve it and get one step closer to going live.

{review_link}

Tom

Forma"""
    try:
        send_mail(
            subject='New testimonial to review',
            message=message,
            from_email=getattr(settings, 'DEFAULT_FROM_EMAIL', ''),
            recipient_list=[email],
            fail_silently=False,
        )
    except Exception:
        logger.exception('Failed to send testimonial review email for profile_id=%s', profile.pk)


def _send_new_testimonial_review_email_background(profile_id: int, site_base_url: str) -> None:
    close_old_connections()
    try:
        profile = TrainerProfile.objects.select_related('user').get(pk=profile_id)
    except TrainerProfile.DoesNotExist:
        logger.warning('Testimonial review email worker: profile_id=%s not found', profile_id)
        return
    send_new_testimonial_review_email(profile, site_base_url=site_base_url)


def enqueue_new_testimonial_review_email(profile_id: int, site_base_url: str) -> None:
    if getattr(settings, 'SYNC_PROOF_REVIEW_EMAIL', False):
        _send_new_testimonial_review_email_background(profile_id, site_base_url)
        return

    def start_worker() -> None:
        worker = threading.Thread(
            target=_send_new_testimonial_review_email_background,
            args=(profile_id, site_base_url),
            daemon=True,
            name=f'proof-review-email-{profile_id}',
        )
        worker.start()

    transaction.on_commit(start_worker)
