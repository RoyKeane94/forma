import logging

from django.core.files.storage import default_storage

from pages.models import ProofTestimonial, TrainerGalleryPhoto, TrainerProfile

logger = logging.getLogger(__name__)


def _add_file_name(paths: set[str], field_file) -> None:
    name = (getattr(field_file, 'name', None) or '').strip()
    if name:
        paths.add(name)


def collect_user_media_paths(user) -> set[str]:
    paths: set[str] = set()
    profile = TrainerProfile.objects.filter(user=user).first()
    if profile is None:
        return paths

    _add_file_name(paths, profile.portrait)
    _add_file_name(paths, profile.intro_video)

    for item in TrainerGalleryPhoto.objects.filter(profile=profile).only('image'):
        _add_file_name(paths, item.image)

    for submission in ProofTestimonial.objects.filter(profile=profile).only('video', 'poster'):
        _add_file_name(paths, submission.video)
        _add_file_name(paths, submission.poster)

    return paths


def delete_user_and_associated_media(user) -> bool:
    media_paths = collect_user_media_paths(user)
    deleted, _ = user.__class__.objects.filter(pk=user.pk).delete()
    if not deleted:
        return False

    for path in sorted(media_paths):
        try:
            if default_storage.exists(path):
                default_storage.delete(path)
        except Exception:
            logger.exception('Failed to remove media file during account deletion: %s', path)
    return True
