from .models import ProofTestimonial, TrainerProfile


def proof_notifications(request):
    user = getattr(request, 'user', None)
    if not user or not user.is_authenticated:
        return {'proof_pending_approvals_count': 0}
    profile_id = (
        TrainerProfile.objects.filter(user=user)
        .values_list('pk', flat=True)
        .first()
    )
    if not profile_id:
        return {'proof_pending_approvals_count': 0}
    count = ProofTestimonial.objects.filter(
        profile_id=profile_id,
        status=ProofTestimonial.STATUS_PENDING,
    ).count()
    return {'proof_pending_approvals_count': count}
