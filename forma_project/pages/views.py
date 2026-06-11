import logging
import os
import secrets
import json
import re
import threading
import subprocess
import tempfile
import shutil

from django.conf import settings
from django.contrib import messages
from django.contrib.auth import get_user_model, login
from django.contrib.auth.decorators import login_required, user_passes_test
from django.core.files import File
from django.core.files.base import ContentFile
from django.core.files.storage import default_storage
from django.db import OperationalError, close_old_connections
from django.db import transaction
from django.db.models import Avg, Count, Prefetch
from django.core.exceptions import ValidationError
from django.http import Http404, HttpResponse, HttpResponseBadRequest, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST

from accounts.forms import RegisterForm
from accounts.media_cleanup import delete_user_and_associated_media
from accounts.models import Profile as AccountsProfile
from accounts.stripe_register import (
    complete_pending_registration_from_stripe_session,
    register_checkout_metadata_ok,
)

from .forms import (
    OnboardingStep1Form,
    TrainerWhoIWorkWithFormSet,
    OnboardingStep2QuickForm,
    OnboardingStep4Form,
    OnboardingStep5MetaForm,
    TrainerGymFormSet,
    OnboardingStep6InstagramForm,
    OnboardingStep7ReviewsForm,
    ProofDetailsForm,
    ProofProfileSetupForm,
    ProofVideoUploadForm,
    ProfileEnquiryForm,
    StaffTrainerCreateForm,
    TrainerAdditionalQualificationFormSet,
    TrainerGalleryPhotoFormSet,
    PRICE_TIER_MAX_NUM,
    TrainerPriceTierFormSet,
    TrainerSpecialismFormSet,
    client_reviews_form_initial,
    price_tier_row_captions_for_meta_form,
)
from .forma_yaml_import import (
    apply_forma_profile_yaml,
    parse_forma_profile_yaml,
    read_profile_example_template,
)
from .models import (
    QUICK_QUALIFICATION_CHOICES,
    ProofOutcomeTag,
    ProfilePageView,
    ProfileScrollEvent,
    ProofTestimonial,
    TrainerGym,
    TrainerProfile,
    TrainerSpecialism,
    ensure_onboarding_children,
)
from .profile_analytics import (
    is_trackable_public_profile_path,
    normalize_profile_path,
    profile_path_for_object,
)
from .stripe_keep_profile import (
    checkout_session_paid,
    create_subscription_checkout_session,
    delete_pending_registration,
    peek_pending_registration,
    retrieve_checkout_session,
    save_checkout_billing_ids,
    store_pending_registration,
    stripe_configured,
)
from .onboarding_meta import ONBOARDING_STEPS, TAB_LABELS
from .profile_completion import profile_checklist_items, profile_outstanding_items, save_proof_profile_setup
from .profile_display import (
    media_storage_preconnect_origin,
    non_empty_client_reviews,
    split_featured_client_reviews,
    visible_who_i_work_with_items,
    quick_qualification_items,
    specialism_display_items,
    training_location_items,
    visible_price_tiers,
    proof_contact_email,
    proof_contact_phone,
    proof_hero_media_mode,
    proof_location_strap,
    proof_trains_in_labels,
    proof_area_labels,
    proof_primary_gym_label,
    proof_location_strapline,
    proof_location_byline_segments,
    proof_specialism_titles,
    proof_intro_video_pull_quote,
    proof_profession_label,
)
from .posters import poster_bytes_from_video_file, resolve_ffmpeg_binary

STEP_COUNT = 7

logger = logging.getLogger(__name__)

try:
    import boto3
except Exception:  # pragma: no cover - only used for direct-to-S3 uploads.
    boto3 = None

_PROOF_UPLOAD_ALLOWED_EXTENSIONS = {'.mp4', '.webm', '.mov', '.m4v'}
_PROOF_DIRECT_UPLOAD_MAX_BYTES = int(os.getenv('PROOF_DIRECT_UPLOAD_MAX_MB', '200')) * 1024 * 1024


def _proof_direct_upload_enabled() -> bool:
    return bool((getattr(settings, 'AWS_STORAGE_BUCKET_NAME', '') or '').strip())


def _safe_upload_filename(filename: str) -> str:
    raw_name = os.path.basename((filename or '').strip()) or 'upload-video'
    sanitized = re.sub(r'[^A-Za-z0-9._-]+', '-', raw_name).strip('-')
    return sanitized or 'upload-video'


def _proof_upload_extension_ok(filename: str) -> bool:
    ext = os.path.splitext((filename or '').strip())[1].lower()
    return ext in _PROOF_UPLOAD_ALLOWED_EXTENSIONS


def _proof_temp_video_key(filename: str) -> str:
    safe_name = _safe_upload_filename(filename)
    return f'proof/tmp/{secrets.token_hex(8)}_{safe_name}'


def _proof_upload_size_ok(size_bytes: int) -> bool:
    return 1 <= size_bytes <= _PROOF_DIRECT_UPLOAD_MAX_BYTES


def _storage_supports_server_side_copy() -> bool:
    return bool(
        getattr(default_storage, 'bucket_name', None)
        and getattr(getattr(default_storage, 'connection', None), 'meta', None)
    )


def _copy_storage_object(source_name: str, destination_name: str) -> bool:
    if not _storage_supports_server_side_copy():
        return False
    bucket_name = getattr(default_storage, 'bucket_name', '')
    client = getattr(getattr(default_storage, 'connection', None), 'meta', None)
    client = getattr(client, 'client', None)
    if not bucket_name or client is None:
        return False
    try:
        client.copy_object(
            Bucket=bucket_name,
            CopySource={'Bucket': bucket_name, 'Key': source_name},
            Key=destination_name,
        )
        return True
    except Exception:
        logger.warning('Could not copy storage object %s -> %s', source_name, destination_name)
        return False


def _fast_copy_temp_video_to_submission(submission: ProofTestimonial, temp_video_path: str) -> bool:
    video_basename = os.path.basename(temp_video_path)
    generated_name = submission.video.field.generate_filename(submission, video_basename)
    final_name = default_storage.get_available_name(generated_name)
    if not _copy_storage_object(temp_video_path, final_name):
        return False
    submission.video.name = final_name
    submission.save(update_fields=['video'])
    return True


def _proof_draft_session_key(profile_id: int) -> str:
    return f'proof_draft_{profile_id}'


def _extract_json_array_from_text(raw: str) -> list:
    text = (raw or '').strip()
    if not text:
        return []
    try:
        parsed = json.loads(text)
        return parsed if isinstance(parsed, list) else []
    except Exception:
        pass
    fenced = re.search(r'```(?:json)?\s*(\[[\s\S]*?\])\s*```', text, re.IGNORECASE)
    if fenced:
        try:
            parsed = json.loads(fenced.group(1))
            return parsed if isinstance(parsed, list) else []
        except Exception:
            return []
    bracketed = re.search(r'(\[[\s\S]*\])', text)
    if bracketed:
        try:
            parsed = json.loads(bracketed.group(1))
            return parsed if isinstance(parsed, list) else []
        except Exception:
            return []
    return []


def _normalize_quote_candidates(raw_candidates) -> list[str]:
    if not isinstance(raw_candidates, list):
        return []
    out: list[str] = []
    for item in raw_candidates:
        quote = (str(item or '')).strip()
        if not quote:
            continue
        if len(quote) > 40:
            continue
        if quote in out:
            continue
        out.append(quote)
        if len(out) >= 3:
            break
    return out


def _suggested_quotes_from_stored_video(video_name: str, *, log_context: str) -> tuple[list[str], str, str]:
    api_key = (getattr(settings, 'OPENAI_API_KEY', '') or '').strip()
    if not api_key:
        return [], ProofTestimonial.QUOTE_STATUS_SKIPPED, ''
    filename = (video_name or '').strip()
    if not filename:
        return [], ProofTestimonial.QUOTE_STATUS_FAILED, ''
    ext = os.path.splitext(filename)[1].lower()
    supported_exts = {'.flac', '.m4a', '.mp3', '.mp4', '.mpeg', '.mpga', '.oga', '.ogg', '.wav', '.webm'}
    upload_filename = os.path.basename(filename) or 'audio_upload'
    upload_bytes = b''
    source_bytes = b''
    try:
        with default_storage.open(filename, 'rb') as video_file:
            source_bytes = video_file.read()
    except Exception:
        logger.exception('Could not read media for quote generation (%s)', log_context)
        return [], ProofTestimonial.QUOTE_STATUS_FAILED, ''
    if ext in supported_exts:
        upload_bytes = source_bytes
    elif ext == '.mov':
        input_path = ''
        output_path = ''
        ffmpeg_bin = resolve_ffmpeg_binary()
        if not ffmpeg_bin:
            logger.warning('No ffmpeg binary available; cannot transcode .mov for %s', log_context)
            return [], ProofTestimonial.QUOTE_STATUS_FAILED, ''
        try:
            with tempfile.NamedTemporaryFile(delete=False, suffix='.mov') as in_tmp:
                in_tmp.write(source_bytes)
                input_path = in_tmp.name
            fd, output_path = tempfile.mkstemp(suffix='.m4a')
            os.close(fd)
            extract_copy_cmd = [
                ffmpeg_bin,
                '-y',
                '-i',
                input_path,
                '-vn',
                '-map',
                'a:0',
                '-c:a',
                'copy',
                output_path,
            ]
            extract_encode_cmd = [
                ffmpeg_bin,
                '-y',
                '-i',
                input_path,
                '-vn',
                '-map',
                'a:0',
                '-c:a',
                'aac',
                '-b:a',
                '128k',
                output_path,
            ]
            try:
                subprocess.run(
                    extract_copy_cmd,
                    check=True,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                )
            except subprocess.CalledProcessError:
                subprocess.run(
                    extract_encode_cmd,
                    check=True,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                )
            with open(output_path, 'rb') as out_fh:
                upload_bytes = out_fh.read()
            upload_filename = f'{os.path.splitext(upload_filename)[0]}.m4a'
        except Exception:
            logger.warning('Failed to transcode .mov for %s', log_context)
            return [], ProofTestimonial.QUOTE_STATUS_FAILED, ''
        finally:
            if input_path and os.path.exists(input_path):
                os.remove(input_path)
            if output_path and os.path.exists(output_path):
                os.remove(output_path)
    else:
        logger.info('Skipping AI quote generation for unsupported extension: %s (%s)', ext or '(none)', log_context)
        return [], ProofTestimonial.QUOTE_STATUS_SKIPPED, ''
    if not upload_bytes:
        return [], ProofTestimonial.QUOTE_STATUS_FAILED, ''
    try:
        from openai import OpenAI
    except Exception:
        logger.exception('OpenAI SDK import failed; skipping quote generation')
        return [], ProofTestimonial.QUOTE_STATUS_FAILED, ''
    try:
        client = OpenAI(api_key=api_key)
        transcript_res = client.audio.transcriptions.create(
            model='whisper-1',
            file=(upload_filename, upload_bytes),
        )
        transcript = (getattr(transcript_res, 'text', '') or '').strip()
        if not transcript:
            return [], ProofTestimonial.QUOTE_STATUS_FAILED, ''
        quote_prompt = (
            "Return the three most compelling sentences from this transcript "
            "that would make a stranger want to watch the video. "
            "Each must be under 60 characters. Return as a JSON array.\n\n"
            f"Transcript:\n{transcript}"
        )
        quote_res = client.chat.completions.create(
            model='gpt-4o',
            messages=[{'role': 'user', 'content': quote_prompt}],
            temperature=0.2,
        )
        content = ''
        if quote_res.choices:
            content = (quote_res.choices[0].message.content or '').strip()
        quotes = _normalize_quote_candidates(_extract_json_array_from_text(content))
        if quotes:
            return quotes, ProofTestimonial.QUOTE_STATUS_COMPLETE, transcript
        return [], ProofTestimonial.QUOTE_STATUS_FAILED, transcript
    except Exception:
        logger.exception('AI quote generation failed for %s', log_context)
        return [], ProofTestimonial.QUOTE_STATUS_FAILED, ''


def _suggested_quotes_from_submission_video(submission: ProofTestimonial) -> tuple[list[str], str, str]:
    return _suggested_quotes_from_stored_video(
        submission.video.name,
        log_context=f'testimonial {submission.pk}',
    )


def _generate_and_store_suggested_quotes(submission_id: int) -> None:
    close_old_connections()
    print(f'[proof-quotes] worker started for submission={submission_id}', flush=True)
    try:
        try:
            submission = ProofTestimonial.objects.get(pk=submission_id)
        except ProofTestimonial.DoesNotExist:
            print(f'[proof-quotes] submission missing id={submission_id}', flush=True)
            return
        if submission.status != ProofTestimonial.STATUS_PENDING:
            print(
                f'[proof-quotes] submission={submission_id} skipped; status={submission.status}',
                flush=True,
            )
            return
        if submission.suggested_quotes:
            if submission.quote_generation_status != ProofTestimonial.QUOTE_STATUS_COMPLETE:
                submission.quote_generation_status = ProofTestimonial.QUOTE_STATUS_COMPLETE
                submission.quote_generation_updated_at = timezone.now()
                submission.save(update_fields=['quote_generation_status', 'quote_generation_updated_at'])
            print(
                f'[proof-quotes] submission={submission_id} already has suggested quotes',
                flush=True,
            )
            return
        submission.quote_generation_status = ProofTestimonial.QUOTE_STATUS_PROCESSING
        submission.quote_generation_updated_at = timezone.now()
        submission.save(update_fields=['quote_generation_status', 'quote_generation_updated_at'])
        print(f'[proof-quotes] submission={submission_id} status=processing', flush=True)
        suggested_quotes, quote_status, transcript = _suggested_quotes_from_submission_video(submission)
        update_fields = ['quote_generation_status', 'quote_generation_updated_at']
        if transcript:
            submission.video_transcript = transcript
            update_fields.append('video_transcript')
        if suggested_quotes:
            submission.suggested_quotes = suggested_quotes
            submission.quote_generation_status = ProofTestimonial.QUOTE_STATUS_COMPLETE
            submission.quote_generation_updated_at = timezone.now()
            update_fields.append('suggested_quotes')
            submission.save(update_fields=update_fields)
            print(
                f'[proof-quotes] submission={submission_id} status=complete quotes={len(suggested_quotes)}',
                flush=True,
            )
        else:
            submission.quote_generation_status = quote_status
            submission.quote_generation_updated_at = timezone.now()
            submission.save(update_fields=update_fields)
            print(
                f'[proof-quotes] submission={submission_id} no quotes status={quote_status}',
                flush=True,
            )
    except OperationalError:
        logger.warning('Quote generation worker could not update testimonial %s due to DB lock', submission_id)
        print(f'[proof-quotes] submission={submission_id} db lock', flush=True)
    except Exception:
        logger.exception('Quote generation worker crashed for testimonial %s', submission_id)
        print(f'[proof-quotes] submission={submission_id} crashed', flush=True)


def _enqueue_suggested_quotes_generation(submission_id: int) -> None:
    ProofTestimonial.objects.filter(pk=submission_id).update(
        quote_generation_status=ProofTestimonial.QUOTE_STATUS_PENDING,
        quote_generation_updated_at=timezone.now(),
    )
    print(f'[proof-quotes] queued submission={submission_id} status=pending', flush=True)
    worker = threading.Thread(
        target=_generate_and_store_suggested_quotes,
        args=(submission_id,),
        daemon=True,
        name=f'proof-quote-generator-{submission_id}',
    )
    worker.start()


def _generate_and_store_intro_video_quotes(profile_id: int) -> None:
    close_old_connections()
    print(f'[intro-quotes] worker started for profile={profile_id}', flush=True)
    try:
        try:
            profile = TrainerProfile.objects.get(pk=profile_id)
        except TrainerProfile.DoesNotExist:
            print(f'[intro-quotes] profile missing id={profile_id}', flush=True)
            return
        if not profile.intro_video or not profile.intro_video.name:
            print(f'[intro-quotes] profile={profile_id} has no welcome video', flush=True)
            return
        TrainerProfile.objects.filter(pk=profile_id).update(
            intro_video_quote_generation_status=ProofTestimonial.QUOTE_STATUS_PROCESSING,
            intro_video_quote_generation_updated_at=timezone.now(),
        )
        suggested_quotes, quote_status, transcript = _suggested_quotes_from_stored_video(
            profile.intro_video.name,
            log_context=f'profile intro video {profile_id}',
        )
        update_fields = ['intro_video_quote_generation_status', 'intro_video_quote_generation_updated_at']
        profile.refresh_from_db(fields=['intro_video'])
        if not profile.intro_video or not profile.intro_video.name:
            return
        if transcript:
            profile.intro_video_transcript = transcript
            update_fields.append('intro_video_transcript')
        if suggested_quotes:
            profile.intro_video_suggested_quotes = suggested_quotes
            profile.intro_video_pull_quote = suggested_quotes[0][:120]
            profile.intro_video_quote_generation_status = quote_status
            update_fields.extend(['intro_video_suggested_quotes', 'intro_video_pull_quote'])
        else:
            profile.intro_video_quote_generation_status = quote_status
        profile.intro_video_quote_generation_updated_at = timezone.now()
        profile.save(update_fields=update_fields)
        print(
            f'[intro-quotes] profile={profile_id} status={quote_status} quotes={len(suggested_quotes)}',
            flush=True,
        )
    except OperationalError:
        logger.warning('Intro quote generation worker could not update profile %s due to DB lock', profile_id)
    except Exception:
        logger.exception('Intro quote generation worker crashed for profile %s', profile_id)


def _enqueue_intro_video_quotes_generation(profile_id: int) -> None:
    TrainerProfile.objects.filter(pk=profile_id).update(
        intro_video_suggested_quotes=[],
        intro_video_pull_quote='',
        intro_video_transcript='',
        intro_video_quote_generation_status=ProofTestimonial.QUOTE_STATUS_PENDING,
        intro_video_quote_generation_updated_at=timezone.now(),
    )
    worker = threading.Thread(
        target=_generate_and_store_intro_video_quotes,
        args=(profile_id,),
        daemon=True,
        name=f'intro-quote-generator-{profile_id}',
    )
    worker.start()


def _maybe_enqueue_intro_video_quotes(profile: TrainerProfile) -> None:
    if not profile.intro_video or not profile.intro_video.name:
        return
    if profile.intro_video_suggested_quotes:
        return
    status = (profile.intro_video_quote_generation_status or ProofTestimonial.QUOTE_STATUS_PENDING).strip()
    if status != ProofTestimonial.QUOTE_STATUS_PENDING:
        return
    if profile.intro_video_quote_generation_updated_at:
        return
    _enqueue_intro_video_quotes_generation(profile.pk)


def _generate_and_store_submission_poster(submission_id: int) -> None:
    close_old_connections()
    print(f'[proof-poster] worker started for submission={submission_id}', flush=True)
    try:
        try:
            submission = ProofTestimonial.objects.get(pk=submission_id)
        except ProofTestimonial.DoesNotExist:
            print(f'[proof-poster] submission missing id={submission_id}', flush=True)
            return
        if not (submission.video and submission.video.name):
            print(f'[proof-poster] submission={submission_id} has no video', flush=True)
            return
        if submission.poster:
            print(f'[proof-poster] submission={submission_id} poster already exists', flush=True)
            return
        source_ext = os.path.splitext(submission.video.name)[1].lower() or '.mp4'
        try:
            with default_storage.open(submission.video.name, 'rb') as fh:
                source_bytes = fh.read()
        except Exception:
            logger.exception('Could not read video for poster generation on testimonial %s', submission.pk)
            print(f'[proof-poster] submission={submission_id} read failed', flush=True)
            return
        try:
            poster_bytes = poster_bytes_from_video_file(source_bytes=source_bytes, source_ext=source_ext)
        except Exception:
            logger.exception('Poster generation failed for testimonial %s', submission.pk)
            print(f'[proof-poster] submission={submission_id} generation failed', flush=True)
            return
        if not poster_bytes:
            print(f'[proof-poster] submission={submission_id} no poster bytes generated', flush=True)
            return
        poster_name = f'{os.path.splitext(os.path.basename(submission.video.name))[0]}.jpg'
        submission.poster.save(poster_name, ContentFile(poster_bytes), save=False)
        submission.save(update_fields=['poster'])
        print(f'[proof-poster] submission={submission_id} poster saved', flush=True)
    except OperationalError:
        logger.warning('Poster worker could not update testimonial %s due to DB lock', submission_id)
        print(f'[proof-poster] submission={submission_id} db lock', flush=True)
    except Exception:
        logger.exception('Poster worker crashed for testimonial %s', submission_id)
        print(f'[proof-poster] submission={submission_id} crashed', flush=True)


def _enqueue_submission_poster_generation(submission_id: int) -> None:
    worker = threading.Thread(
        target=_generate_and_store_submission_poster,
        args=(submission_id,),
        daemon=True,
        name=f'proof-poster-generator-{submission_id}',
    )
    worker.start()


def _review_carousel_pages(reviews: list, page_size: int = 2) -> list:
    """Slice reviews into page-sized groups for the public profile carousel (2 per slide by default; CSS stacks on small widths)."""
    if not reviews:
        return []
    return [reviews[i : i + page_size] for i in range(0, len(reviews), page_size)]


def _approved_proof_testimonials_for_profile(profile: TrainerProfile) -> list[ProofTestimonial]:
    """Fetch only fields needed to render Proof wall cards."""
    return list(
        ProofTestimonial.objects.filter(
            profile=profile,
            status=ProofTestimonial.STATUS_APPROVED,
        )
        .only(
            'video',
            'poster',
            'pull_quote',
            'suggested_quotes',
            'client_first_name',
            'client_last_initial',
            'client_job_title',
            'star_rating',
            'outcome_tags',
            'reviewed_at',
            'submitted_at',
            'profile_id',
        )
        .order_by('-reviewed_at', '-submitted_at')
    )

_QUICK_QUAL_NOTE_MAX_LEN = 600


def _finalize_keep_forma_profile(*, profile_id: int, email: str, password: str):
    """
    Attach the Forma-made profile to a new user (or return existing user if already done).
    Returns (user, error_code). error_code is None on success.
    """
    User = get_user_model()
    email = (email or '').strip().lower()
    with transaction.atomic():
        profile = (
            TrainerProfile.objects.select_for_update()
            .select_related('user')
            .get(pk=profile_id)
        )
        if not profile.forma_made:
            existing = profile.user
            if (existing.email or '').strip().lower() == email:
                return existing, None
            return None, 'already_claimed'
        if User.objects.filter(email__iexact=email).exists():
            return None, 'email_taken'
        new_user = User.objects.create_user(
            username=email,
            email=email,
            password=password,
        )
        AccountsProfile.objects.get_or_create(user=new_user)
        old_user = profile.user
        profile.user = new_user
        profile.forma_made = False
        profile.public_url_key = None
        # Claimed profiles should always be live on their new owner URL.
        profile.is_published = True
        profile.save()
        if old_user.pk != new_user.pk:
            delete_user_and_associated_media(old_user)
        return new_user, None


def _stripe_metadata_dict(meta) -> dict:
    """Copy a Stripe metadata mapping to a plain str→str dict (never use dict(meta) on StripeObject)."""
    if meta is None:
        return {}
    if isinstance(meta, dict):
        return {str(k): '' if v is None else str(v) for k, v in meta.items()}
    to_dict = getattr(meta, 'to_dict', None)
    if callable(to_dict):
        try:
            raw = to_dict()
            if isinstance(raw, dict):
                return {str(k): '' if v is None else str(v) for k, v in raw.items()}
        except Exception:
            pass
    if hasattr(meta, 'items'):
        try:
            return {str(k): '' if v is None else str(v) for k, v in meta.items()}
        except Exception:
            pass
    out = {}
    for key in getattr(meta, 'keys', lambda: [])():
        try:
            out[str(key)] = '' if meta[key] is None else str(meta[key])
        except (KeyError, TypeError):
            continue
    return out


def _checkout_session_metadata_dict(stripe_session) -> dict:
    """Checkout Session.metadata via full session serialization (most reliable with StripeObject)."""
    to_dict = getattr(stripe_session, 'to_dict', None)
    if callable(to_dict):
        try:
            whole = to_dict()
            if isinstance(whole, dict):
                md = whole.get('metadata')
                if isinstance(md, dict):
                    return {str(k): '' if v is None else str(v) for k, v in md.items()}
        except Exception:
            pass
    return _stripe_metadata_dict(getattr(stripe_session, 'metadata', None))


def _keep_profile_checkout_metadata_ok(meta: dict) -> bool:
    """Sessions we create set purpose=keep_profile; tolerate missing purpose if token+profile are set."""
    if not meta:
        return False
    if (meta.get('purpose') or '').strip() == 'keep_profile':
        return True
    return bool((meta.get('pending_token') or '').strip() and (meta.get('profile_id') or '').strip())


def _complete_keep_profile_from_stripe_session(*, profile: TrainerProfile, stripe_session) -> tuple:
    """
    After a paid Checkout Session, create the account if pending data exists.
    Returns (user | None, error_message for display).
    """
    if not checkout_session_paid(stripe_session):
        return None, 'Payment was not completed. Please try again or contact support.'

    meta = _checkout_session_metadata_dict(stripe_session)
    try:
        meta_profile_id = int(meta.get('profile_id') or 0)
    except (TypeError, ValueError):
        meta_profile_id = 0
    if meta_profile_id != profile.pk:
        return None, 'This payment does not match this profile page.'

    pending_token = (meta.get('pending_token') or '').strip()
    if not pending_token:
        if not profile.forma_made:
            return profile.user, None
        return None, 'Your registration data expired. Please start again from the form.'

    data = peek_pending_registration(pending_token)
    if not data:
        if not profile.forma_made:
            return profile.user, None
        return None, 'Your registration data expired. Please start again from the form.'

    if int(data.get('profile_id') or 0) != profile.pk:
        return None, 'Something went wrong linking your payment. Please contact support.'

    user, err = _finalize_keep_forma_profile(
        profile_id=profile.pk,
        email=data['email'],
        password=data['password'],
    )
    if err == 'email_taken':
        delete_pending_registration(pending_token)
        return None, 'That email is already registered. Sign in, or contact support if you were charged.'
    if err == 'already_claimed':
        delete_pending_registration(pending_token)
        return None, 'This profile has already been claimed.'
    if user is None:
        return None, 'We could not finish creating your account. Please contact support.'

    delete_pending_registration(pending_token)
    return user, None


def _quick_qual_notes_from_post(request) -> dict:
    out = {}
    allowed = {k for k, _ in QUICK_QUALIFICATION_CHOICES}
    for key in allowed:
        raw = (request.POST.get(f'quick_qual_note_{key}') or '').strip()
        if raw:
            out[key] = raw[:_QUICK_QUAL_NOTE_MAX_LEN]
    return out


def _get_profile(user) -> TrainerProfile:
    profile, _ = TrainerProfile.objects.get_or_create(
        user=user,
        defaults={
            'first_name': (user.first_name or '').strip(),
            'last_name': (user.last_name or '').strip(),
            'tagline': '',
            'bio': '',
        },
    )
    ensure_onboarding_children(profile)
    return profile


def _get_profile_fast(user) -> TrainerProfile:
    """
    Lightweight profile lookup for account actions that do not require onboarding child bootstrapping.
    """
    profile, _ = TrainerProfile.objects.get_or_create(
        user=user,
        defaults={
            'first_name': (user.first_name or '').strip(),
            'last_name': (user.last_name or '').strip(),
            'tagline': '',
            'bio': '',
        },
    )
    return profile


def _advance_profile(profile: TrainerProfile, step_idx: int) -> None:
    if step_idx < STEP_COUNT - 1:
        profile.onboarding_step = step_idx + 1
        profile.save(update_fields=['onboarding_step'])
    else:
        profile.onboarding_step = STEP_COUNT
        profile.completed_at = timezone.now()
        profile.save(update_fields=['onboarding_step', 'completed_at'])


@login_required
def my_account(request):
    profile = _get_profile(request.user)
    accounts_profile, _ = AccountsProfile.objects.get_or_create(user=request.user)
    if request.method == 'POST' and request.POST.get('update_visibility'):
        profile.is_published = request.POST.get('is_published') == 'on'
        profile.save(update_fields=['is_published'])
        if profile.is_published:
            messages.success(request, 'Your page is now published — your public link works for everyone.')
        else:
            messages.success(request, 'Your page is unpublished — only you can open your profile link while signed in.')
        return redirect('pages:my_account')

    if profile.forma_made and profile.public_url_key:
        proof_public_url = request.build_absolute_uri(
            reverse(
                'pages:trainer_profile_forma_proof',
                kwargs={'profile_slug': profile.slug, 'url_key': profile.public_url_key},
            )
        )
    else:
        proof_public_url = request.build_absolute_uri(
            reverse('pages:trainer_profile_proof', kwargs={'profile_slug': profile.slug})
        )
    public_profile_url = ''
    if profile.completed_at and profile.is_published:
        public_profile_url = proof_public_url
    proof_testimonial_url = request.build_absolute_uri(
        reverse('pages:trainer_proof_submit', kwargs={'profile_slug': profile.slug})
    )
    testimonial_total_count = ProofTestimonial.objects.filter(
        profile=profile,
        status=ProofTestimonial.STATUS_APPROVED,
    ).count()
    testimonial_to_review_count = ProofTestimonial.objects.filter(
        profile=profile,
        status=ProofTestimonial.STATUS_PENDING,
    ).count()
    show_legacy_profile_admin = bool(
        request.user.is_superuser and request.GET.get('legacy_profile_admin') == '1'
    )

    profile = (
        TrainerProfile.objects.filter(pk=profile.pk)
        .select_related('primary_area', 'user')
        .prefetch_related('gyms__location_area', 'specialisms__catalog')
        .first()
        or profile
    )
    profile_checklist = profile_checklist_items(profile)
    profile_outstanding_items_list = [item for item in profile_checklist if not item['complete']]

    return render(
        request,
        'pages/my_account.html',
        {
            'profile': profile,
            'accounts_profile': accounts_profile,
            'tab_labels': TAB_LABELS,
            'public_profile_url': public_profile_url,
            'proof_public_url': proof_public_url,
            'proof_testimonial_url': proof_testimonial_url,
            'testimonial_total_count': testimonial_total_count,
            'testimonial_to_review_count': testimonial_to_review_count,
            'show_legacy_profile_admin': show_legacy_profile_admin,
            'profile_checklist_items': profile_checklist,
            'profile_outstanding_items': profile_outstanding_items_list,
        },
    )


@login_required
def proof_profile_setup(request):
    profile = _get_profile_fast(request.user)
    profile = (
        TrainerProfile.objects.filter(pk=profile.pk)
        .select_related('primary_area', 'user')
        .prefetch_related('gyms__location_area', 'specialisms__catalog')
        .first()
        or profile
    )

    if request.method == 'POST':
        form = ProofProfileSetupForm(request.POST, request.FILES, profile=profile)
        if form.is_valid():
            intro_video_uploaded = save_proof_profile_setup(profile, form.cleaned_data)
            if intro_video_uploaded:
                _enqueue_intro_video_quotes_generation(profile.pk)
            messages.success(request, 'Your Proof profile has been updated.')
            return redirect('pages:my_account')
    else:
        form = ProofProfileSetupForm(profile=profile)

    return render(
        request,
        'pages/proof_profile_setup.html',
        {
            'form': form,
            'profile': profile,
            'profile_outstanding_items': profile_outstanding_items(profile),
        },
    )


@login_required
def onboarding_edit_start(request):
    profile = _get_profile(request.user)
    if not profile.completed_at:
        return redirect('pages:onboarding')
    return redirect('pages:onboarding_step_edit', step=1)


@login_required
def onboarding_redirect(request):
    profile = _get_profile(request.user)
    if profile.completed_at or profile.onboarding_step >= STEP_COUNT:
        return redirect('pages:onboarding_complete')
    return redirect('pages:onboarding_step', step=profile.onboarding_step + 1)


def _onboarding_redirect(step: int, *, onboarding_edit: bool, staff_forma: bool, profile_pk: int | None):
    if staff_forma and profile_pk is not None:
        if onboarding_edit:
            return redirect('pages:staff_forma_onboarding_step_edit', profile_pk=profile_pk, step=step)
        return redirect('pages:staff_forma_onboarding_step', profile_pk=profile_pk, step=step)
    if onboarding_edit:
        return redirect('pages:onboarding_step_edit', step=step)
    return redirect('pages:onboarding_step', step=step)


def _onboarding_step_for_profile(
    request,
    profile: TrainerProfile,
    step: int,
    *,
    onboarding_edit: bool,
    staff_forma: bool,
):
    if not 1 <= step <= STEP_COUNT:
        raise Http404
    step_idx = step - 1

    if not staff_forma and onboarding_edit and not profile.completed_at:
        return redirect('pages:onboarding_step', step=profile.onboarding_step + 1)

    if staff_forma and onboarding_edit and not profile.completed_at:
        return redirect('pages:staff_forma_onboarding_step', profile_pk=profile.pk, step=profile.onboarding_step + 1)

    if profile.completed_at or profile.onboarding_step >= STEP_COUNT:
        if staff_forma and not onboarding_edit:
            messages.info(request, 'This profile is already complete.')
            return redirect('pages:staff_forma_profiles')
        if not staff_forma and not onboarding_edit:
            return redirect('pages:onboarding_complete')

    if not onboarding_edit and not staff_forma and step_idx > profile.onboarding_step:
        return redirect('pages:onboarding_step', step=profile.onboarding_step + 1)

    skip_advance = bool(onboarding_edit and profile.completed_at)
    max_reachable_step = STEP_COUNT if onboarding_edit else profile.onboarding_step + 1

    context = {
        'step': step_idx,
        'step_display': step,
        'prev_step': step - 1 if step > 1 else None,
        'profile': profile,
        'total_steps': STEP_COUNT,
        'tab_labels': TAB_LABELS,
        'step_meta': ONBOARDING_STEPS[step_idx],
        'max_reachable_step': max_reachable_step,
        'onboarding_edit': onboarding_edit,
        'staff_forma': staff_forma,
        'staff_profile_pk': profile.pk if staff_forma else None,
    }

    profile_pk = profile.pk if staff_forma else None

    if request.method == 'POST':
        advance = not request.POST.get('save_draft')
        ok, errors = _process_step_post(
            request,
            profile,
            step_idx,
            advance=advance,
            skip_profile_advance=skip_advance,
        )
        if ok:
            if not advance:
                messages.success(request, 'Draft saved.')
                return _onboarding_redirect(step, onboarding_edit=onboarding_edit, staff_forma=staff_forma, profile_pk=profile_pk)
            if step_idx == STEP_COUNT - 1:
                if onboarding_edit:
                    if staff_forma:
                        messages.success(request, 'Profile updated.')
                        return redirect('pages:staff_forma_profiles')
                    messages.success(request, 'Your page has been updated.')
                    return redirect(profile)
                if staff_forma:
                    messages.success(request, 'Forma-made profile is complete.')
                    return redirect('pages:staff_forma_profiles')
                return redirect('pages:onboarding_complete')
            return _onboarding_redirect(step + 1, onboarding_edit=onboarding_edit, staff_forma=staff_forma, profile_pk=profile_pk)
        messages.error(request, 'Please correct the errors below.')
        context.update(errors)
    else:
        _load_step_get_forms(context, profile, step_idx)

    return render(request, 'pages/onboarding.html', context)


@login_required
def onboarding_step(request, step: int, onboarding_edit: bool = False):
    profile = _get_profile(request.user)
    return _onboarding_step_for_profile(
        request,
        profile,
        step,
        onboarding_edit=onboarding_edit,
        staff_forma=False,
    )


@user_passes_test(lambda u: u.is_superuser)
def staff_forma_profile_list(request):
    profiles = (
        TrainerProfile.objects.filter(forma_made=True, created_by=request.user)
        .select_related('user')
        .order_by('-pk')
    )
    paths = []
    rows = []
    for p in profiles:
        url = request.build_absolute_uri(p.get_absolute_url()) if p.public_url_key else ''
        track_path = profile_path_for_object(p)
        paths.append(track_path)
        rows.append(
            {
                'profile': p,
                'label': f'{p.first_name} {p.last_name}'.strip(),
                'url': url,
                'track_path': track_path,
            }
        )
    view_counts = dict(
        ProfilePageView.objects.filter(page__in=paths)
        .values('page')
        .annotate(c=Count('pk'))
        .values_list('page', 'c')
    )
    scroll_avgs = dict(
        ProfileScrollEvent.objects.filter(page__in=paths)
        .values('page')
        .annotate(a=Avg('depth'))
        .values_list('page', 'a')
    )
    for row in rows:
        tp = row['track_path']
        row['page_views'] = view_counts.get(tp, 0)
        avg = scroll_avgs.get(tp)
        row['avg_scroll_pct'] = None if avg is None else round(float(avg), 1)
    return render(
        request,
        'pages/staff_forma_profile_list.html',
        {'rows': rows},
    )


@user_passes_test(lambda u: u.is_superuser)
@require_POST
def staff_forma_profile_reset_analytics(request):
    """Clear ProfilePageView / ProfileScrollEvent rows for this staff user’s Forma-made URLs only."""
    profiles = TrainerProfile.objects.filter(forma_made=True, created_by=request.user)
    paths = [profile_path_for_object(p) for p in profiles]
    if paths:
        pv_n = ProfilePageView.objects.filter(page__in=paths).delete()[0]
        sc_n = ProfileScrollEvent.objects.filter(page__in=paths).delete()[0]
        messages.success(
            request,
            f'Cleared public page stats for your Forma-made profiles '
            f'({pv_n} page views removed, {sc_n} scroll events removed).',
        )
    else:
        messages.info(request, 'No Forma-made profiles to reset.')
    return redirect('pages:staff_forma_profiles')


@user_passes_test(lambda u: u.is_superuser)
@require_POST
def staff_forma_outreach_toggle(request, profile_pk: int):
    profile = get_object_or_404(
        TrainerProfile.objects.filter(forma_made=True, created_by=request.user),
        pk=profile_pk,
    )
    raw_field = (request.POST.get('field') or '').strip()
    checked = request.POST.get('checked') == '1'
    field_map = {
        'email_1': 'forma_outreach_email_1',
        'call_1': 'forma_outreach_call_1',
        'email_2': 'forma_outreach_email_2',
    }
    attr = field_map.get(raw_field)
    if not attr:
        return HttpResponseBadRequest('invalid field')
    setattr(profile, attr, checked)
    profile.save(update_fields=[attr])
    return HttpResponse(status=204)


@user_passes_test(lambda u: u.is_superuser)
def staff_forma_profile_create(request):
    if request.method == 'POST':
        form = StaffTrainerCreateForm(request.POST)
        if form.is_valid():
            User = get_user_model()
            username_max = User._meta.get_field('username').max_length
            uname = f"forma_{secrets.token_hex(8)}"
            while User.objects.filter(username=uname).exists():
                uname = f"forma_{secrets.token_hex(8)}"
            email = f"{uname}@placeholder.forma"
            user = User(
                username=uname[:username_max],
                email=email,
                first_name=form.cleaned_data['first_name'].strip(),
                last_name=form.cleaned_data['last_name'].strip(),
                is_active=False,
            )
            user.set_unusable_password()
            user.save()
            AccountsProfile.objects.get_or_create(user=user)
            profile = TrainerProfile(
                user=user,
                first_name=form.cleaned_data['first_name'].strip(),
                last_name=form.cleaned_data['last_name'].strip(),
                tagline='',
                bio='',
                forma_made=True,
                created_by=request.user,
                is_published=True,
            )
            profile.save()
            ensure_onboarding_children(profile)
            messages.success(request, 'Profile created. Complete the onboarding steps.')
            return redirect('pages:staff_forma_onboarding', profile_pk=profile.pk)
    else:
        form = StaffTrainerCreateForm()
    return render(
        request,
        'pages/staff_forma_profile_new.html',
        {'form': form},
    )


@user_passes_test(lambda u: u.is_superuser)
def staff_forma_profile_create_yaml(request):
    try:
        example_yaml = read_profile_example_template()
    except FileNotFoundError:
        example_yaml = ''
        if request.method == 'GET':
            messages.warning(request, 'Example template file is missing from the server.')

    if request.method == 'POST':
        raw = request.POST.get('yaml_body', '')
        try:
            data = parse_forma_profile_yaml(raw)
        except ValidationError as exc:
            for msg in exc.messages:
                messages.error(request, msg)
            return render(
                request,
                'pages/staff_forma_profile_new_yaml.html',
                {'yaml_body': raw},
            )

        user_block = data.get('user') or {}
        if not isinstance(user_block, dict):
            user_block = {}
        email = (user_block.get('email') or '').strip()
        if not email:
            messages.error(request, 'user.email is required in the YAML.')
            return render(
                request,
                'pages/staff_forma_profile_new_yaml.html',
                {'yaml_body': raw},
            )

        User = get_user_model()
        email_field = User._meta.get_field('email')
        email_max = getattr(email_field, 'max_length', None) or 254
        if len(email) > email_max:
            messages.error(request, f'user.email must be at most {email_max} characters.')
            return render(
                request,
                'pages/staff_forma_profile_new_yaml.html',
                {'yaml_body': raw},
            )

        if User.objects.filter(email__iexact=email).exists():
            messages.error(request, 'A user with this email already exists.')
            return render(
                request,
                'pages/staff_forma_profile_new_yaml.html',
                {'yaml_body': raw},
            )

        prof_in = data.get('profile') or {}
        if not isinstance(prof_in, dict):
            messages.error(request, 'YAML must include a top-level "profile" mapping.')
            return render(
                request,
                'pages/staff_forma_profile_new_yaml.html',
                {'yaml_body': raw},
            )
        first = (prof_in.get('first_name') or '').strip()
        last = (prof_in.get('last_name') or '').strip()
        if not first or not last:
            messages.error(request, 'profile.first_name and profile.last_name are required.')
            return render(
                request,
                'pages/staff_forma_profile_new_yaml.html',
                {'yaml_body': raw},
            )

        try:
            with transaction.atomic():
                username_max = User._meta.get_field('username').max_length
                uname = f'forma_{secrets.token_hex(8)}'
                while User.objects.filter(username=uname).exists():
                    uname = f'forma_{secrets.token_hex(8)}'
                uname = uname[:username_max]

                user = User(
                    username=uname,
                    email=email[:email_max],
                    first_name=first[:150],
                    last_name=last[:150],
                    is_active=False,
                )
                user.set_unusable_password()
                user.save()
                AccountsProfile.objects.get_or_create(user=user)
                profile = TrainerProfile(
                    user=user,
                    first_name=first[:150],
                    last_name=last[:150],
                    tagline='',
                    bio='',
                    forma_made=True,
                    created_by=request.user,
                    is_published=True,
                )
                profile.save()
                ensure_onboarding_children(profile)
                apply_forma_profile_yaml(profile, data)
                user.first_name = profile.first_name
                user.last_name = profile.last_name
                user.save(update_fields=['first_name', 'last_name'])
        except ValidationError as exc:
            for msg in exc.messages:
                messages.error(request, msg)
            return render(
                request,
                'pages/staff_forma_profile_new_yaml.html',
                {'yaml_body': raw},
            )

        messages.success(
            request,
            'Profile created from YAML. Complete any remaining onboarding steps (e.g. photos).',
        )
        return redirect('pages:staff_forma_onboarding', profile_pk=profile.pk)

    return render(
        request,
        'pages/staff_forma_profile_new_yaml.html',
        {'yaml_body': example_yaml},
    )


@user_passes_test(lambda u: u.is_superuser)
@require_POST
def staff_forma_profile_delete(request, profile_pk: int):
    """Remove a Forma-made profile and its placeholder user (superuser-only, own creations)."""
    profile = get_object_or_404(
        TrainerProfile,
        pk=profile_pk,
        forma_made=True,
        created_by=request.user,
    )
    label = f'{profile.first_name} {profile.last_name}'.strip() or profile.user.get_username()
    user = profile.user
    with transaction.atomic():
        delete_user_and_associated_media(user)
    messages.success(request, f'Deleted profile for {label}.')
    return redirect('pages:staff_forma_profiles')


@user_passes_test(lambda u: u.is_superuser)
def staff_forma_onboarding_redirect(request, profile_pk: int):
    profile = get_object_or_404(
        TrainerProfile,
        pk=profile_pk,
        forma_made=True,
        created_by=request.user,
    )
    if profile.completed_at or profile.onboarding_step >= STEP_COUNT:
        return redirect('pages:staff_forma_profiles')
    return redirect('pages:staff_forma_onboarding_step', profile_pk=profile.pk, step=profile.onboarding_step + 1)


@user_passes_test(lambda u: u.is_superuser)
def staff_forma_onboarding_step(request, profile_pk: int, step: int):
    profile = get_object_or_404(
        TrainerProfile,
        pk=profile_pk,
        forma_made=True,
        created_by=request.user,
    )
    return _onboarding_step_for_profile(
        request,
        profile,
        step,
        onboarding_edit=False,
        staff_forma=True,
    )


@user_passes_test(lambda u: u.is_superuser)
def staff_forma_onboarding_edit_start(request, profile_pk: int):
    profile = get_object_or_404(
        TrainerProfile,
        pk=profile_pk,
        forma_made=True,
        created_by=request.user,
    )
    if not profile.completed_at:
        return redirect('pages:staff_forma_onboarding', profile_pk=profile_pk)
    return redirect('pages:staff_forma_onboarding_step_edit', profile_pk=profile_pk, step=1)


@user_passes_test(lambda u: u.is_superuser)
def staff_forma_onboarding_step_edit(request, profile_pk: int, step: int):
    profile = get_object_or_404(
        TrainerProfile,
        pk=profile_pk,
        forma_made=True,
        created_by=request.user,
    )
    return _onboarding_step_for_profile(
        request,
        profile,
        step,
        onboarding_edit=True,
        staff_forma=True,
    )


@login_required
def onboarding_complete(request):
    profile = _get_profile(request.user)
    if not profile.completed_at:
        return redirect('pages:onboarding')
    return render(request, 'pages/onboarding_complete.html', {'profile': profile})


def trainer_profile_id_redirect(request, profile_id: int):
    profile = get_object_or_404(TrainerProfile, pk=profile_id)
    return redirect(profile, permanent=True)


def trainer_proof_submit(request, profile_slug: str):
    profile = get_object_or_404(
        TrainerProfile.objects.select_related('primary_area__district'),
        slug__iexact=profile_slug,
        forma_made=False,
    )
    if not profile.is_published:
        raise Http404
    session_key = _proof_draft_session_key(profile.pk)
    draft = request.session.get(session_key) or {}
    step = (request.GET.get('step') or 'upload').strip().lower()
    if step not in {'upload', 'details', 'preview'}:
        step = 'upload'
    if step in {'details', 'preview'} and not (draft.get('video_path') or '').strip():
        return redirect(f"{reverse('pages:trainer_proof_submit', kwargs={'profile_slug': profile.slug})}?step=upload")
    if step == 'preview' and not draft.get('details'):
        return redirect(f"{reverse('pages:trainer_proof_submit', kwargs={'profile_slug': profile.slug})}?step=details")

    upload_form = ProofVideoUploadForm()
    details_form = ProofDetailsForm()

    if request.method == 'POST':
        action = (request.POST.get('proof_action') or '').strip()
        if action == 'upload_video':
            upload_form = ProofVideoUploadForm(request.POST, request.FILES)
            if upload_form.is_valid():
                uploaded = upload_form.cleaned_data['video']
                temp_name = default_storage.save(f'proof/tmp/{secrets.token_hex(8)}_{uploaded.name}', uploaded)
                old_path = (draft.get('video_path') or '').strip()
                if old_path and old_path != temp_name and default_storage.exists(old_path):
                    default_storage.delete(old_path)
                draft['video_path'] = temp_name
                request.session[session_key] = draft
                request.session.modified = True
                return redirect(f"{reverse('pages:trainer_proof_submit', kwargs={'profile_slug': profile.slug})}?step=details")
            step = 'upload'
        elif action == 'upload_video_direct':
            video_key = (request.POST.get('video_key') or '').strip()
            original_name = (request.POST.get('video_name') or '').strip()
            if not video_key.startswith('proof/tmp/'):
                messages.error(request, 'We could not verify your upload. Please try again.')
                step = 'upload'
            elif not _proof_upload_extension_ok(original_name or video_key):
                messages.error(request, 'Upload MP4, WebM, MOV, or M4V.')
                step = 'upload'
            elif not default_storage.exists(video_key):
                messages.error(request, 'Upload did not finish. Please try again.')
                step = 'upload'
            else:
                try:
                    uploaded_size = int(default_storage.size(video_key))
                except Exception:
                    uploaded_size = 0
                if not _proof_upload_size_ok(uploaded_size):
                    default_storage.delete(video_key)
                    max_mb = _PROOF_DIRECT_UPLOAD_MAX_BYTES // (1024 * 1024)
                    messages.error(request, f'Video must be between 1 byte and {max_mb}MB.')
                    step = 'upload'
                else:
                    old_path = (draft.get('video_path') or '').strip()
                    if old_path and old_path != video_key and default_storage.exists(old_path):
                        default_storage.delete(old_path)
                    draft['video_path'] = video_key
                    request.session[session_key] = draft
                    request.session.modified = True
                    return redirect(f"{reverse('pages:trainer_proof_submit', kwargs={'profile_slug': profile.slug})}?step=details")
        elif action == 'save_details':
            details_form = ProofDetailsForm(request.POST)
            if details_form.is_valid():
                draft['details'] = {
                    'client_first_name': details_form.cleaned_data['client_first_name'],
                    'client_last_initial': details_form.cleaned_data['client_last_initial'],
                    'client_job_title': details_form.cleaned_data['client_job_title'],
                    'star_rating': details_form.cleaned_data['star_rating'],
                    'outcome_tags': details_form.cleaned_data['outcome_tags'],
                }
                request.session[session_key] = draft
                request.session.modified = True
                return redirect(f"{reverse('pages:trainer_proof_submit', kwargs={'profile_slug': profile.slug})}?step=preview")
            step = 'details'
        elif action == 'submit_testimonial':
            details = draft.get('details') or {}
            video_path = (draft.get('video_path') or '').strip()
            if not video_path or not details:
                return redirect(f"{reverse('pages:trainer_proof_submit', kwargs={'profile_slug': profile.slug})}?step=upload")
            if not default_storage.exists(video_path):
                messages.error(request, 'Your uploaded video could not be found. Please upload again.')
                request.session.pop(session_key, None)
                return redirect(f"{reverse('pages:trainer_proof_submit', kwargs={'profile_slug': profile.slug})}?step=upload")
            submission = ProofTestimonial(
                profile=profile,
                client_first_name=details.get('client_first_name', ''),
                client_last_initial=details.get('client_last_initial', ''),
                client_job_title=details.get('client_job_title', ''),
                star_rating=int(details.get('star_rating') or 0),
                outcome_tags=list(details.get('outcome_tags') or []),
                prompt_start='Submitted via Proof quick capture flow.',
                prompt_change='Submitted via Proof quick capture flow.',
                prompt_recommend='Submitted via Proof quick capture flow.',
                status=ProofTestimonial.STATUS_PENDING,
            )
            source_ext = os.path.splitext(video_path)[1].lower() or '.mp4'
            submission.save()
            copied_via_storage = _fast_copy_temp_video_to_submission(submission, video_path)
            if not copied_via_storage:
                with default_storage.open(video_path, 'rb') as fh:
                    submission.video.save(os.path.basename(video_path), File(fh), save=False)
                submission.save(update_fields=['video'])
            print(
                f'[proof-submit] created submission={submission.pk} profile={profile.pk} ext={source_ext} '
                f'copy_mode={"server-copy" if copied_via_storage else "stream-upload"}',
                flush=True,
            )
            _enqueue_submission_poster_generation(submission.pk)
            _enqueue_suggested_quotes_generation(submission.pk)
            default_storage.delete(video_path)
            request.session.pop(session_key, None)
            return redirect(reverse('pages:trainer_proof_submit_success', kwargs={'profile_slug': profile.slug}))

    video_url = ''
    video_path = (draft.get('video_path') or '').strip()
    if video_path and default_storage.exists(video_path):
        try:
            video_url = default_storage.url(video_path)
        except Exception:
            video_url = ''

    preview = draft.get('details') or {}
    outcome_labels = dict(ProofOutcomeTag.objects.filter(is_active=True).values_list('key', 'label'))
    preview_outcomes = [outcome_labels.get(k, k.replace('_', ' ').title()) for k in preview.get('outcome_tags', [])]

    return render(
        request,
        'pages/proof_submit.html',
        {
            'profile': profile,
            'step': step,
            'upload_form': upload_form,
            'details_form': details_form,
            'video_url': video_url,
            'preview': preview,
            'preview_outcomes': preview_outcomes,
            'preview_stars': range(int(preview.get('star_rating') or 0)),
            'direct_upload_enabled': _proof_direct_upload_enabled(),
            'direct_upload_max_bytes': _PROOF_DIRECT_UPLOAD_MAX_BYTES,
        },
    )


@require_POST
def trainer_proof_upload_presign(request, profile_slug: str):
    profile = get_object_or_404(
        TrainerProfile.objects.select_related('primary_area__district'),
        slug__iexact=profile_slug,
        forma_made=False,
    )
    if not profile.is_published:
        raise Http404

    if not _proof_direct_upload_enabled():
        return JsonResponse({'error': 'Direct upload unavailable.'}, status=400)
    if boto3 is None:
        return JsonResponse({'error': 'Upload service unavailable.'}, status=503)

    filename = (request.POST.get('filename') or '').strip()
    content_type = (request.POST.get('content_type') or '').strip() or 'application/octet-stream'
    try:
        size_bytes = int(request.POST.get('size') or '0')
    except (TypeError, ValueError):
        size_bytes = 0

    if not _proof_upload_extension_ok(filename):
        return JsonResponse({'error': 'Upload MP4, WebM, MOV, or M4V.'}, status=400)
    if not _proof_upload_size_ok(size_bytes):
        max_mb = _PROOF_DIRECT_UPLOAD_MAX_BYTES // (1024 * 1024)
        return JsonResponse({'error': f'Video must be between 1 byte and {max_mb}MB.'}, status=400)

    key = _proof_temp_video_key(filename)
    bucket = (getattr(settings, 'AWS_STORAGE_BUCKET_NAME', '') or '').strip()
    region_name = (getattr(settings, 'AWS_S3_REGION_NAME', '') or '').strip() or None
    client_kwargs = {
        'region_name': region_name,
    }
    access_key = (getattr(settings, 'AWS_ACCESS_KEY_ID', '') or '').strip()
    secret_key = (getattr(settings, 'AWS_SECRET_ACCESS_KEY', '') or '').strip()
    if access_key and secret_key:
        client_kwargs['aws_access_key_id'] = access_key
        client_kwargs['aws_secret_access_key'] = secret_key
    try:
        s3_client = boto3.client('s3', **client_kwargs)
        upload_url = s3_client.generate_presigned_url(
            ClientMethod='put_object',
            Params={
                'Bucket': bucket,
                'Key': key,
                'ContentType': content_type,
            },
            ExpiresIn=15 * 60,
        )
    except Exception:
        logger.exception('Failed to create pre-signed upload URL for proof submit')
        return JsonResponse({'error': 'Could not start upload.'}, status=500)

    return JsonResponse(
        {
            'upload_url': upload_url,
            'video_key': key,
            'max_bytes': _PROOF_DIRECT_UPLOAD_MAX_BYTES,
        }
    )


def trainer_proof_submit_success(request, profile_slug: str):
    profile = get_object_or_404(
        TrainerProfile.objects.select_related('primary_area__district'),
        slug__iexact=profile_slug,
        forma_made=False,
    )
    if not profile.is_published:
        raise Http404
    return render(
        request,
        'pages/proof_submit_success.html',
        {
            'profile': profile,
            'proof_submit_url': reverse('pages:trainer_proof_submit', kwargs={'profile_slug': profile.slug}),
        },
    )


@login_required
def proof_notifications(request):
    profile = _get_profile_fast(request.user)

    if request.method == 'POST':
        action = (request.POST.get('action') or '').strip().lower()
        raw_id = (request.POST.get('submission_id') or '').strip()
        try:
            submission_id = int(raw_id)
        except (TypeError, ValueError):
            submission_id = 0
        submission = get_object_or_404(
            ProofTestimonial,
            pk=submission_id,
            profile=profile,
            status=ProofTestimonial.STATUS_PENDING,
        )

        if action == 'approve':
            selected_pull_quote = (request.POST.get('pull_quote') or '').strip()
            allowed_quotes = [str(q).strip() for q in (submission.suggested_quotes or []) if str(q).strip()]
            if selected_pull_quote and allowed_quotes and selected_pull_quote not in allowed_quotes:
                messages.error(request, 'Choose one of the suggested pull quotes.')
                return redirect('pages:proof_notifications')
            now = timezone.now()
            submission.status = ProofTestimonial.STATUS_APPROVED
            submission.pull_quote = selected_pull_quote[:120]
            submission.reviewed_by = request.user
            submission.reviewed_at = now
            ProofTestimonial.objects.filter(pk=submission.pk).update(
                status=ProofTestimonial.STATUS_APPROVED,
                pull_quote=selected_pull_quote[:120],
                reviewed_by=request.user,
                reviewed_at=now,
            )
            messages.success(request, 'Testimonial approved.')
            return redirect('pages:proof_notifications')
        if action == 'reject':
            video_name = (submission.video.name or '').strip()
            poster_name = (submission.poster.name or '').strip()
            submission.delete()
            if video_name:
                try:
                    default_storage.delete(video_name)
                except Exception:
                    logger.warning('Could not delete testimonial video %s after rejection', video_name)
            if poster_name:
                try:
                    default_storage.delete(poster_name)
                except Exception:
                    logger.warning('Could not delete testimonial poster %s after rejection', poster_name)
            messages.success(request, 'Testimonial rejected and deleted.')
            return redirect('pages:proof_notifications')
        messages.error(request, 'Choose approve or reject.')
        return redirect('pages:proof_notifications')

    pending_submissions = list(
        ProofTestimonial.objects.filter(
            profile=profile,
            status=ProofTestimonial.STATUS_PENDING,
        ).order_by('-submitted_at')
    )
    recently_reviewed = list(
        ProofTestimonial.objects.filter(
            profile=profile,
        )
        .exclude(status=ProofTestimonial.STATUS_PENDING)
        .order_by('-reviewed_at', '-submitted_at')[:20]
    )
    outcome_label_map = dict(ProofOutcomeTag.objects.filter(is_active=True).values_list('key', 'label'))
    for item in pending_submissions + recently_reviewed:
        item.outcome_labels = [outcome_label_map.get(k, str(k).replace('_', ' ').title()) for k in (item.outcome_tags or [])]

    return render(
        request,
        'pages/proof_notifications.html',
        {
            'profile': profile,
            'pending_submissions': pending_submissions,
            'recently_reviewed': recently_reviewed,
        },
    )


def _profile_queryset_for_proof_page():
    return TrainerProfile.objects.select_related(
        'user',
        'primary_area__district',
    ).prefetch_related(
        Prefetch(
            'specialisms',
            queryset=TrainerSpecialism.objects.select_related('catalog'),
        ),
        Prefetch(
            'gyms',
            queryset=TrainerGym.objects.select_related('location_area__district'),
        ),
    )


def _load_profile_for_proof_page(profile: TrainerProfile) -> TrainerProfile:
    return _profile_queryset_for_proof_page().get(pk=profile.pk)


def _proof_page_context(request, profile: TrainerProfile, *, approved_testimonials, approved_count: int) -> dict:
    trainer_gyms = [
        g for g in profile.gyms.all()
        if (g.name or '').strip() or g.location_area_id
    ]
    is_owner = request.user.is_authenticated and request.user.pk == profile.user_id
    average_rating = 0.0
    average_rating_rounded = 0
    if approved_count:
        total = sum(int(item.star_rating or 0) for item in approved_testimonials)
        average_rating = round(total / approved_count, 1)
        average_rating_rounded = max(1, min(5, int(round(average_rating))))

    return {
        'profile': profile,
        'approved_testimonials': approved_testimonials,
        'approved_count': approved_count,
        'average_rating': average_rating,
        'average_rating_rounded': average_rating_rounded,
        'media_preconnect_origin': media_storage_preconnect_origin(),
        'specialism_items': specialism_display_items(profile),
        'trainer_gyms': trainer_gyms,
        'proof_area_labels': proof_area_labels(profile),
        'proof_primary_gym': proof_primary_gym_label(profile),
        'proof_location_strapline': proof_location_strapline(profile),
        'proof_location_byline_segments': proof_location_byline_segments(profile),
        'proof_specialism_titles': proof_specialism_titles(profile),
        'proof_intro_video_pull_quote': proof_intro_video_pull_quote(profile),
        'proof_profession_label': proof_profession_label(profile),
        'trains_in_labels': proof_trains_in_labels(profile, trainer_gyms),
        'proof_location_strap': proof_location_strap(profile),
        'proof_hero_media_mode': proof_hero_media_mode(profile),
        'proof_contact_phone': proof_contact_phone(profile),
        'proof_contact_email': proof_contact_email(profile),
        'is_proof_owner': is_owner,
    }


@login_required
def proof_testimonials_page(request):
    profile = _load_profile_for_proof_page(_get_profile_fast(request.user))
    _maybe_enqueue_intro_video_quotes(profile)

    approved_testimonials = _approved_proof_testimonials_for_profile(profile)
    approved_count = len(approved_testimonials)
    outcome_label_map = dict(ProofOutcomeTag.objects.filter(is_active=True).values_list('key', 'label'))
    for item in approved_testimonials:
        item.outcome_labels = [outcome_label_map.get(k, str(k).replace('_', ' ').title()) for k in (item.outcome_tags or [])]

    context = _proof_page_context(
        request,
        profile,
        approved_testimonials=approved_testimonials,
        approved_count=approved_count,
    )
    return render(request, 'pages/proof_testimonials_page.html', context)


@login_required
def proof_testimonials_edit(request):
    profile = _get_profile(request.user)
    if request.method == 'POST':
        submission_id = request.POST.get('submission_id')
        action = (request.POST.get('action') or '').strip()
        submission = get_object_or_404(
            ProofTestimonial,
            pk=submission_id,
            profile=profile,
            status=ProofTestimonial.STATUS_APPROVED,
        )
        if action != 'delete':
            messages.error(request, 'Choose a valid testimonial action.')
            return redirect('pages:proof_testimonials_edit')
        video_name = (submission.video.name or '').strip()
        poster_name = (submission.poster.name or '').strip()
        submission.delete()
        if video_name and default_storage.exists(video_name):
            default_storage.delete(video_name)
        if poster_name and default_storage.exists(poster_name):
            default_storage.delete(poster_name)
        messages.success(request, 'Testimonial deleted.')
        return redirect('pages:proof_testimonials_edit')

    testimonials = list(
        ProofTestimonial.objects.filter(
            profile=profile,
            status=ProofTestimonial.STATUS_APPROVED,
        ).order_by('-reviewed_at', '-submitted_at')
    )
    return render(
        request,
        'pages/proof_testimonials_edit.html',
        {
            'profile': profile,
            'testimonials': testimonials,
        },
    )


def keep_forma_profile_register(request, profile_slug: str, url_key: str):
    """
    Forma-made public profiles: collect email/password, then Stripe Checkout.
    The account is created only after payment (success page or webhook).
    """
    if len(url_key) != 5:
        raise Http404
    profile = get_object_or_404(
        TrainerProfile.objects.select_related('user', 'primary_area'),
        slug__iexact=profile_slug,
        public_url_key__iexact=url_key,
        forma_made=True,
    )
    if not profile.is_published:
        raise Http404
    if request.user.is_authenticated:
        messages.info(
            request,
            'You’re signed in. Sign out first if you need to claim this page with a different account.',
        )
        return redirect('pages:my_account')

    if request.GET.get('checkout') == 'canceled':
        messages.info(request, 'Checkout was cancelled. Your account has not been charged.')

    if request.method == 'POST':
        form = RegisterForm(request.POST)
        if form.is_valid():
            if not stripe_configured():
                form.add_error(
                    None,
                    'Payments are not configured on this server. Add Stripe keys to the environment.',
                )
            else:
                pending_token = secrets.token_urlsafe(32)
                email = form.cleaned_data['email']
                password = form.cleaned_data['password1']
                store_pending_registration(
                    pending_token=pending_token,
                    profile_id=profile.pk,
                    email=email,
                    password=password,
                )
                success_url = request.build_absolute_uri(
                    reverse('pages:keep_forma_profile_success'),
                ) + '?session_id={CHECKOUT_SESSION_ID}'
                cancel_url = request.build_absolute_uri(
                    reverse(
                        'pages:keep_forma_profile',
                        kwargs={
                            'profile_slug': profile.slug,
                            'url_key': profile.public_url_key,
                        },
                    )
                ) + '?checkout=canceled'
                try:
                    checkout_url = create_subscription_checkout_session(
                        success_url=success_url,
                        cancel_url=cancel_url,
                        customer_email=email,
                        pending_token=pending_token,
                        profile_id=profile.pk,
                    )
                except Exception:
                    logger.exception('Stripe Checkout failed for keep-profile')
                    delete_pending_registration(pending_token)
                    form.add_error(
                        None,
                        'Could not start checkout. Check Stripe product/price configuration and try again.',
                    )
                else:
                    return redirect(checkout_url)
    else:
        form = RegisterForm()

    return render(
        request,
        'pages/keep_profile_register.html',
        {'form': form, 'profile': profile},
    )


def keep_forma_profile_checkout_success(request):
    """
    Stripe redirects here with ?session_id=… — profile is identified from Checkout metadata
    (the vanity URL key is cleared after claim, so we cannot use /slug/key/ for this step).
    """
    if request.user.is_authenticated:
        return redirect('pages:my_account')

    session_id = (request.GET.get('session_id') or '').strip()
    if not session_id or not stripe_configured():
        messages.error(request, 'Missing payment session. Please open your profile link and try again.')
        return redirect('pages:my_account')

    try:
        stripe_session = retrieve_checkout_session(session_id)
    except Exception:
        logger.exception('Could not retrieve Stripe session')
        messages.error(request, 'Could not verify payment. Please contact support.')
        return redirect('pages:my_account')

    meta = _checkout_session_metadata_dict(stripe_session)
    if not _keep_profile_checkout_metadata_ok(meta):
        messages.error(request, 'This payment session is not valid for profile signup.')
        return redirect('pages:my_account')

    try:
        profile_id = int(meta.get('profile_id') or 0)
    except (TypeError, ValueError):
        profile_id = 0
    profile = get_object_or_404(
        TrainerProfile.objects.select_related('user', 'primary_area'),
        pk=profile_id,
    )
    if not profile.is_published:
        raise Http404

    user, err_msg = _complete_keep_profile_from_stripe_session(
        profile=profile,
        stripe_session=stripe_session,
    )
    if err_msg:
        messages.error(request, err_msg)
        return redirect('pages:my_account')

    if user is not None:
        save_checkout_billing_ids(user, stripe_session)

    login(request, user, backend='django.contrib.auth.backends.ModelBackend')
    messages.success(
        request,
        'Your account is ready — this profile is now yours. Your public link has been updated.',
    )
    return redirect('pages:my_account')


@csrf_exempt
@require_POST
def stripe_webhook(request):
    """Optional: completes keep-profile signup if the customer closes the tab before the success URL."""
    secret = getattr(settings, 'STRIPE_WEBHOOK_SECRET', '') or ''
    if not secret.strip():
        return HttpResponse(status=404)

    import stripe

    stripe.api_key = settings.STRIPE_SECRET_KEY
    payload = request.body
    sig_header = request.META.get('HTTP_STRIPE_SIGNATURE', '')

    try:
        event = stripe.Webhook.construct_event(payload, sig_header, secret)
    except ValueError:
        return HttpResponseBadRequest('invalid payload')
    except stripe.error.SignatureVerificationError:
        return HttpResponseBadRequest('invalid signature')

    if event['type'] != 'checkout.session.completed':
        return HttpResponse(status=200)

    session = event['data']['object']
    meta = session.get('metadata') or {}
    if not isinstance(meta, dict):
        meta = _stripe_metadata_dict(meta)
    if register_checkout_metadata_ok(meta):
        try:
            stripe_session = retrieve_checkout_session(session['id'])
        except Exception:
            logger.exception('Webhook could not reload checkout session for register flow')
            return HttpResponse(status=500)

        user, err_msg = complete_pending_registration_from_stripe_session(stripe_session)
        if user is not None:
            AccountsProfile.objects.get_or_create(user=user)
            save_checkout_billing_ids(user, stripe_session)
            from accounts.views import _enqueue_post_registration_tasks

            _enqueue_post_registration_tasks(
                user.pk,
                request.build_absolute_uri('/').rstrip('/'),
            )
        if err_msg and user is None:
            logger.warning('Stripe webhook register-flow incomplete: %s', err_msg)
        return HttpResponse(status=200)

    if not _keep_profile_checkout_metadata_ok(meta):
        return HttpResponse(status=200)

    try:
        profile_id = int(meta.get('profile_id') or 0)
    except (TypeError, ValueError):
        return HttpResponse(status=200)

    profile = TrainerProfile.objects.filter(pk=profile_id, forma_made=True).select_related('user').first()
    if profile is None:
        profile = TrainerProfile.objects.filter(pk=profile_id).first()
        if profile is None:
            return HttpResponse(status=200)
        if not profile.forma_made:
            return HttpResponse(status=200)

    try:
        stripe_session = retrieve_checkout_session(session['id'])
    except Exception:
        logger.exception('Webhook could not reload checkout session')
        return HttpResponse(status=500)

    user, err_msg = _complete_keep_profile_from_stripe_session(
        profile=profile,
        stripe_session=stripe_session,
    )
    if user is not None:
        save_checkout_billing_ids(user, stripe_session)
    if err_msg and user is None:
        logger.warning('Stripe webhook keep-profile incomplete: %s', err_msg)
    return HttpResponse(status=200)


def trainer_public_profile(request, profile_slug: str, url_key: str | None = None):
    if url_key is not None and len(url_key) != 5:
        raise Http404
    qs = TrainerProfile.objects.select_related(
        'user',
        'primary_area__district',
    ).prefetch_related(
        'additional_qualifications',
        Prefetch(
            'specialisms',
            queryset=TrainerSpecialism.objects.select_related('catalog'),
        ),
        'price_tiers',
        'gallery_photos',
        'who_i_work_with_items',
        Prefetch('gyms', queryset=TrainerGym.objects.select_related('location_area__district')),
    )
    if url_key is not None:
        profile = get_object_or_404(
            qs,
            slug__iexact=profile_slug,
            public_url_key__iexact=url_key,
            forma_made=True,
        )
    else:
        profile = get_object_or_404(
            qs,
            slug__iexact=profile_slug,
            forma_made=False,
        )
    is_owner = request.user.is_authenticated and request.user.pk == profile.user_id
    is_forma_creator = (
        request.user.is_authenticated
        and request.user.is_superuser
        and profile.forma_made
        and profile.created_by_id == request.user.pk
    )
    # Owner or creating superuser: may preview drafts (unpublished or onboarding incomplete).
    # Everyone else: self-serve profiles need completed onboarding + published.
    # Forma-made keyed URLs are intentionally publicly viewable even when unpublished.
    if not is_owner and not is_forma_creator:
        if not profile.forma_made and not profile.is_published:
            raise Http404
        if not profile.forma_made and not profile.completed_at:
            raise Http404

    ig_handle = (profile.instagram_handle or '').strip().lstrip('@')
    instagram_url = f'https://www.instagram.com/{ig_handle}/' if ig_handle else ''

    review_rows = non_empty_client_reviews(profile)
    featured_review, other_reviews = split_featured_client_reviews(profile, review_rows)
    review_stats = None
    if review_rows:
        n = len(review_rows)
        total = sum(int(r['rating']) for r in review_rows)
        review_stats = {
            'count': n,
            'average': round(total / n, 1),
        }

    price_tiers = visible_price_tiers(profile)
    pricing_has_featured_tier = any(getattr(t, 'is_most_popular', False) for t in price_tiers)
    trainer_gyms = [
        g
        for g in profile.gyms.all()
        if (g.name or '').strip() or g.location_area_id
    ]

    context = {
        'profile': profile,
        'quick_qual_items': quick_qualification_items(profile),
        'training_location_items': training_location_items(profile.training_locations),
        'trainer_gyms': trainer_gyms,
        'featured_review': featured_review,
        'other_reviews': other_reviews,
        'review_carousel_pages': _review_carousel_pages(other_reviews),
        'specialism_items': specialism_display_items(profile),
        'price_tiers': price_tiers,
        'pricing_has_featured_tier': pricing_has_featured_tier,
        'review_stats': review_stats,
        'instagram_url': instagram_url,
        'who_i_work_with_items': visible_who_i_work_with_items(profile),
        'media_preconnect_origin': media_storage_preconnect_origin(),
    }
    return render(request, 'pages/trainer_profile.html', context)


def trainer_public_proof_page(request, profile_slug: str, url_key: str | None = None):
    if url_key is not None and len(url_key) != 5:
        raise Http404

    qs = _profile_queryset_for_proof_page()
    if url_key is not None:
        profile = get_object_or_404(
            qs,
            slug__iexact=profile_slug,
            public_url_key__iexact=url_key,
            forma_made=True,
        )
    else:
        profile = get_object_or_404(
            qs,
            slug__iexact=profile_slug,
            forma_made=False,
        )

    _maybe_enqueue_intro_video_quotes(profile)

    approved_testimonials = _approved_proof_testimonials_for_profile(profile)
    approved_count = len(approved_testimonials)
    outcome_label_map = dict(ProofOutcomeTag.objects.filter(is_active=True).values_list('key', 'label'))
    for item in approved_testimonials:
        item.outcome_labels = [
            outcome_label_map.get(k, str(k).replace('_', ' ').title()) for k in (item.outcome_tags or [])
        ]

    context = _proof_page_context(
        request,
        profile,
        approved_testimonials=approved_testimonials,
        approved_count=approved_count,
    )
    return render(request, 'pages/proof_testimonials_page.html', context)


def _pricing_row_has_content(cleaned: dict | None) -> bool:
    if not cleaned:
        return False
    label = (cleaned.get('label') or '').strip()
    has_price = cleaned.get('price') is not None
    return bool(label or has_price)


def _pricing_most_popular_row_ok(meta, pfs) -> bool:
    """Requires meta and formset to have already passed is_valid()."""
    cd = meta.cleaned_data
    if not cd.get('show_most_popular_tier'):
        return True
    raw = (cd.get('most_popular_row') or '').strip()
    if not raw.isdigit():
        return True
    idx = int(raw)
    if idx < 0 or idx >= len(pfs.forms):
        meta.add_error('most_popular_row', 'Choose a valid price row.')
        return False
    form = pfs.forms[idx]
    fcd = getattr(form, 'cleaned_data', None) or {}
    if not _pricing_row_has_content(fcd):
        meta.add_error(
            'most_popular_row',
            'Pick a row that already has a label or a price filled in.',
        )
        return False
    return True


def _pricing_step_show_add_button(formset) -> bool:
    return len(formset.forms) < PRICE_TIER_MAX_NUM


GYM_FORM_MAX = 5


def _gym_forms_visible_count(forms, post_data) -> int:
    """How many gym form rows to show (1–GYM_FORM_MAX). GET: from saved instance only. POST: data + errors."""
    n = 1
    for i, f in enumerate(forms):
        if post_data is not None:
            if f.errors:
                n = max(n, i + 1)
            pfx = f.add_prefix('name')
            if (post_data.get(pfx) or '').strip():
                n = max(n, i + 1)
            pfx = f.add_prefix('location_area')
            if post_data.get(pfx):
                n = max(n, i + 1)
            for suffix in ('location_add_name', 'location_add_outward'):
                pfx = f.add_prefix(suffix)
                if (post_data.get(pfx) or '').strip():
                    n = max(n, i + 1)
        else:
            inst = getattr(f, 'instance', None)
            if inst and getattr(inst, 'pk', None):
                if (getattr(inst, 'name', None) or '').strip() or getattr(inst, 'location_area_id', None):
                    n = max(n, i + 1)
    return max(1, min(GYM_FORM_MAX, n))


def _apply_pricing_most_popular(profile: TrainerProfile, meta_cleaned: dict) -> None:
    profile.price_tiers.filter(order__lte=10).update(is_most_popular=False)
    if not meta_cleaned.get('show_most_popular_tier'):
        return
    raw = (meta_cleaned.get('most_popular_row') or '').strip()
    if not raw.isdigit():
        return
    idx = int(raw)
    tiers = list(profile.price_tiers.filter(order__lte=10).order_by('order'))
    if not (0 <= idx < len(tiers)):
        return
    t = tiers[idx]
    if _pricing_row_has_content({'label': t.label, 'price': t.price}):
        t.is_most_popular = True
        t.save(update_fields=['is_most_popular'])


def _process_step_post(
    request,
    profile: TrainerProfile,
    step_idx: int,
    *,
    advance: bool = True,
    skip_profile_advance: bool = False,
) -> tuple[bool, dict]:
    def _advance_if_needed() -> None:
        if advance and not skip_profile_advance:
            _advance_profile(profile, step_idx)

    if step_idx == 0:
        ensure_onboarding_children(profile)
        form = OnboardingStep1Form(request.POST, request.FILES, instance=profile)
        wfs = TrainerWhoIWorkWithFormSet(request.POST, instance=profile)
        form_ok = form.is_valid()
        wfs_ok = wfs.is_valid()
        if form_ok and wfs_ok:
            form.save()
            wfs.save()
            _advance_if_needed()
            return True, {}
        return False, {'form': form, 'who_formset': wfs}

    if step_idx == 1:
        quick = OnboardingStep2QuickForm(request.POST)
        fs = TrainerAdditionalQualificationFormSet(request.POST, instance=profile)
        if quick.is_valid() and fs.is_valid():
            selected = list(quick.cleaned_data.get('quick_qualifications') or [])
            profile.quick_qualifications = selected
            notes = _quick_qual_notes_from_post(request)
            profile.quick_qualification_notes = {k: notes[k] for k in selected if k in notes}
            profile.save(update_fields=['quick_qualifications', 'quick_qualification_notes'])
            fs.save()
            _advance_if_needed()
            return True, {}
        post_notes = _quick_qual_notes_from_post(request)
        return False, {
            'quick_form': quick,
            'formset': fs,
            'quick_qual_selected': list(request.POST.getlist('quick_qualifications')),
            'quick_qual_note_rows': [
                {'key': k, 'label': lab, 'text': post_notes.get(k, '')}
                for k, lab in QUICK_QUALIFICATION_CHOICES
            ],
        }

    if step_idx == 2:
        fs = TrainerSpecialismFormSet(request.POST, instance=profile)
        if fs.is_valid():
            fs.save()
            _advance_if_needed()
            return True, {}
        return False, {'formset': fs}

    if step_idx == 3:
        form = OnboardingStep4Form(request.POST, instance=profile)
        ensure_onboarding_children(profile)
        gym_formset = TrainerGymFormSet(
            request.POST,
            instance=profile,
            prefix='gyms',
        )
        if not form.is_valid():
            return False, {
                'form': form,
                'gym_formset': gym_formset,
                'gym_visible_forms': _gym_forms_visible_count(gym_formset.forms, request.POST),
                'gym_max_forms': GYM_FORM_MAX,
            }
        gym_locs = list(form.cleaned_data.get('training_locations') or [])
        gym_in = 'gym' in gym_locs
        if gym_in:
            if not gym_formset.is_valid():
                return False, {
                    'form': form,
                    'gym_formset': gym_formset,
                    'gym_visible_forms': _gym_forms_visible_count(gym_formset.forms, request.POST),
                    'gym_max_forms': GYM_FORM_MAX,
                }
            with transaction.atomic():
                form.save()
                gym_formset.save()
            _advance_if_needed()
            return True, {}
        with transaction.atomic():
            form.save()
            TrainerGym.objects.filter(profile=profile).update(name='', location_area_id=None)
        _advance_if_needed()
        return True, {}

    if step_idx == 4:
        pfs = TrainerPriceTierFormSet(request.POST, instance=profile)
        meta = OnboardingStep5MetaForm(
            request.POST,
            instance=profile,
            tier_row_captions=price_tier_row_captions_for_meta_form(pfs),
        )
        ok_pfs = pfs.is_valid()
        ok_meta = meta.is_valid()
        if ok_pfs and ok_meta and not _pricing_most_popular_row_ok(meta, pfs):
            ok_meta = False
        if ok_pfs and ok_meta:
            meta.save()
            pfs.save()
            _apply_pricing_most_popular(profile, meta.cleaned_data)
            _advance_if_needed()
            return True, {}
        return False, {
            'meta_form': meta,
            'formset': pfs,
            'price_tier_show_add_button': _pricing_step_show_add_button(pfs),
        }

    if step_idx == 5:
        ig = OnboardingStep6InstagramForm(request.POST, instance=profile)
        gfs = TrainerGalleryPhotoFormSet(request.POST, request.FILES, instance=profile)
        if ig.is_valid() and gfs.is_valid():
            ig.save()
            gfs.save()
            _advance_if_needed()
            return True, {}
        return False, {'instagram_form': ig, 'formset': gfs}

    if step_idx == 6:
        rf = OnboardingStep7ReviewsForm(request.POST, profile=profile)
        if rf.is_valid():
            rf.save_to_profile(profile)
            _advance_if_needed()
            return True, {}
        return False, {'reviews_form': rf}

    return False, {}


def _load_step_get_forms(context: dict, profile: TrainerProfile, step_idx: int) -> None:
    if step_idx == 0:
        ensure_onboarding_children(profile)
        context['form'] = OnboardingStep1Form(instance=profile)
        context['who_formset'] = TrainerWhoIWorkWithFormSet(instance=profile)
    elif step_idx == 1:
        context['quick_form'] = OnboardingStep2QuickForm(
            initial={'quick_qualifications': profile.quick_qualifications or []}
        )
        context['formset'] = TrainerAdditionalQualificationFormSet(instance=profile)
        notes = dict(profile.quick_qualification_notes or {})
        context['quick_qual_selected'] = list(profile.quick_qualifications or [])
        context['quick_qual_note_rows'] = [
            {'key': k, 'label': lab, 'text': (notes.get(k) or '')}
            for k, lab in QUICK_QUALIFICATION_CHOICES
        ]
    elif step_idx == 2:
        context['formset'] = TrainerSpecialismFormSet(instance=profile)
    elif step_idx == 3:
        ensure_onboarding_children(profile)
        context['form'] = OnboardingStep4Form(instance=profile)
        gfs = TrainerGymFormSet(
            instance=profile,
            prefix='gyms',
        )
        context['gym_formset'] = gfs
        context['gym_visible_forms'] = _gym_forms_visible_count(gfs.forms, None)
        context['gym_max_forms'] = GYM_FORM_MAX
    elif step_idx == 4:
        fs = TrainerPriceTierFormSet(instance=profile)
        context['formset'] = fs
        context['meta_form'] = OnboardingStep5MetaForm(
            instance=profile,
            tier_row_captions=price_tier_row_captions_for_meta_form(fs),
        )
        context['price_tier_show_add_button'] = _pricing_step_show_add_button(fs)
    elif step_idx == 5:
        context['instagram_form'] = OnboardingStep6InstagramForm(instance=profile)
        context['formset'] = TrainerGalleryPhotoFormSet(instance=profile)
    elif step_idx == 6:
        context['reviews_form'] = OnboardingStep7ReviewsForm(
            initial=client_reviews_form_initial(profile),
            profile=profile,
        )


# ── Public marketing ───────────────────────────────────────────────────────


def profile_enquiry(request):
    if request.method == 'POST':
        form = ProfileEnquiryForm(request.POST)
        if form.is_valid():
            form.save()
            messages.success(
                request,
                'Thanks — we’ve received your message and will be in touch soon.',
            )
            return redirect('pages:profile_enquiry')
    else:
        form = ProfileEnquiryForm()
    return render(
        request,
        'pages/profile_enquiry.html',
        {'form': form},
    )


# ── Public profile analytics (sendBeacon; CSRF-exempt POST) ───────────────────

# 0 = left without reaching the 25% milestone (still counts toward average scroll vs pageviews).
_SCROLL_DEPTH_ALLOWED = frozenset({0, 25, 50, 75, 100})


@csrf_exempt
@require_POST
def track_profile_pageview(request):
    page = (request.POST.get('page') or '').strip()
    if not page or not is_trackable_public_profile_path(page):
        return HttpResponse(status=204)
    ProfilePageView.objects.create(page=normalize_profile_path(page))
    return HttpResponse(status=204)


@csrf_exempt
@require_POST
def track_profile_scroll(request):
    page = (request.POST.get('page') or '').strip()
    raw_depth = (request.POST.get('depth') or '').strip()
    if not page or not is_trackable_public_profile_path(page):
        return HttpResponse(status=204)
    try:
        depth = int(raw_depth)
    except (TypeError, ValueError):
        return HttpResponse(status=204)
    if depth not in _SCROLL_DEPTH_ALLOWED:
        return HttpResponse(status=204)
    ProfileScrollEvent.objects.create(page=normalize_profile_path(page), depth=depth)
    return HttpResponse(status=204)


# ── HTTP error handlers (ROOT_URLCONF handler400 / 403 / 404 / 500) ─────────


def bad_request(request, exception=None):
    from .models import record_http_error_log

    record_http_error_log(request, 400, exception=exception)
    return render(request, 'pages/errors/400.html', status=400)


def permission_denied(request, exception=None):
    from .models import record_http_error_log

    record_http_error_log(request, 403, exception=exception)
    return render(request, 'pages/errors/403.html', status=403)


def page_not_found(request, exception=None):
    from .models import record_http_error_log

    record_http_error_log(request, 404, exception=exception)
    return render(request, 'pages/errors/404.html', status=404)


def server_error(request):
    """Logged in middleware when an exception caused the 500; this view only renders."""
    return render(request, 'pages/errors/500.html', status=500)
