from django.urls import reverse

from .models import ProofTestimonial, TrainerProfile


def _user_initials(user, profile=None) -> str:
    first = (getattr(user, 'first_name', '') or '').strip()
    last = (getattr(user, 'last_name', '') or '').strip()
    if not first and profile is not None:
        first = (profile.first_name or '').strip()
    if not last and profile is not None:
        last = (profile.last_name or '').strip()
    if first and last:
        return (first[0] + last[0]).upper()
    if first:
        return first[:2].upper()
    email = (getattr(user, 'email', '') or '').strip()
    if email:
        return email[0].upper()
    return '?'


def proof_notifications(request):
    user = getattr(request, 'user', None)
    if not user or not user.is_authenticated:
        return {
            'proof_pending_approvals_count': 0,
            'nav_trainer_profile': None,
            'nav_user_initials': '',
            'nav_proof_submit_url': '',
        }

    profile = TrainerProfile.objects.filter(user=user).first()
    initials = _user_initials(user, profile)
    if not profile:
        return {
            'proof_pending_approvals_count': 0,
            'nav_trainer_profile': None,
            'nav_user_initials': initials,
            'nav_proof_submit_url': '',
        }

    count = ProofTestimonial.objects.filter(
        profile_id=profile.pk,
        status=ProofTestimonial.STATUS_PENDING,
    ).count()
    submit_path = reverse(
        'pages:trainer_proof_submit',
        kwargs={'profile_slug': profile.slug},
    )
    submit_url = request.build_absolute_uri(submit_path)

    return {
        'proof_pending_approvals_count': count,
        'nav_trainer_profile': profile,
        'nav_user_initials': initials,
        'nav_proof_submit_url': submit_url,
    }
