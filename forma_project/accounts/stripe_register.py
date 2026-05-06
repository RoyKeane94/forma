"""Stripe Checkout for public registration: pay first, then create the user account."""

from __future__ import annotations

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.db import IntegrityError, transaction

PENDING_CACHE_PREFIX = 'register_checkout:'
PENDING_TTL = 60 * 60  # 1 hour


def stripe_register_configured() -> bool:
    return bool(
        getattr(settings, 'STRIPE_SECRET_KEY', '').strip()
        and getattr(settings, 'STRIPE_PRICE_ID', '').strip()
    )


def store_pending_registration(
    *,
    pending_token: str,
    first_name: str,
    last_name: str,
    email: str,
    password: str,
) -> None:
    cache.set(
        f'{PENDING_CACHE_PREFIX}{pending_token}',
        {
            'first_name': first_name,
            'last_name': last_name,
            'email': email,
            'password': password,
        },
        timeout=PENDING_TTL,
    )


def peek_pending_registration(pending_token: str) -> dict | None:
    return cache.get(f'{PENDING_CACHE_PREFIX}{pending_token}')


def delete_pending_registration(pending_token: str) -> None:
    cache.delete(f'{PENDING_CACHE_PREFIX}{pending_token}')


def create_register_checkout_session(
    *,
    success_url: str,
    cancel_url: str,
    customer_email: str,
    pending_token: str,
) -> str:
    import stripe

    stripe.api_key = settings.STRIPE_SECRET_KEY
    price_id = (getattr(settings, 'STRIPE_PRICE_ID', '') or '').strip()
    if not price_id:
        raise ValueError('Missing STRIPE_PRICE_ID')

    session = stripe.checkout.Session.create(
        mode='subscription',
        line_items=[{'price': price_id, 'quantity': 1}],
        success_url=success_url,
        cancel_url=cancel_url,
        customer_email=customer_email,
        metadata={
            'pending_token': pending_token,
            'email': customer_email,
            'purpose': 'register_account',
        },
        subscription_data={
            'trial_period_days': int(getattr(settings, 'STRIPE_TRIAL_DAYS', 30) or 30),
        },
    )
    if not session.url:
        raise RuntimeError('Stripe Checkout session has no URL')
    return session.url


def retrieve_checkout_session(session_id: str):
    import stripe

    stripe.api_key = settings.STRIPE_SECRET_KEY
    return stripe.checkout.Session.retrieve(
        session_id,
        expand=['subscription'],
    )


def _stripe_metadata_dict(meta) -> dict:
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


def checkout_session_metadata_dict(stripe_session) -> dict:
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


def register_checkout_metadata_ok(meta: dict) -> bool:
    if not meta:
        return False
    if (meta.get('purpose') or '').strip() == 'register_account':
        return True
    return bool((meta.get('pending_token') or '').strip())


def checkout_session_paid(session) -> bool:
    if session.status != 'complete':
        return False
    if getattr(session, 'mode', None) != 'subscription':
        return False
    ps = getattr(session, 'payment_status', None) or ''
    return ps in ('paid', 'no_payment_required')


def _session_email(stripe_session, meta: dict) -> str:
    md_email = (meta.get('email') or '').strip().lower()
    if md_email:
        return md_email
    session_email = (getattr(stripe_session, 'customer_email', None) or '').strip().lower()
    if session_email:
        return session_email
    customer_details = getattr(stripe_session, 'customer_details', None)
    if customer_details is not None:
        email = (getattr(customer_details, 'email', None) or '').strip().lower()
        if email:
            return email
    return ''


def complete_pending_registration_from_stripe_session(stripe_session) -> tuple:
    if not checkout_session_paid(stripe_session):
        return None, 'Payment was not completed. Please try again.'

    meta = checkout_session_metadata_dict(stripe_session)
    if not register_checkout_metadata_ok(meta):
        return None, 'This payment session is not valid for registration.'

    email = _session_email(stripe_session, meta)
    pending_token = (meta.get('pending_token') or '').strip()
    if not pending_token:
        if email:
            existing = get_user_model().objects.filter(email__iexact=email).first()
            if existing:
                return existing, None
        return None, 'Your registration data expired. Please start again.'

    data = peek_pending_registration(pending_token)
    if not data:
        if email:
            existing = get_user_model().objects.filter(email__iexact=email).first()
            if existing:
                return existing, None
        return None, 'Your registration data expired. Please start again.'

    pending_email = (data.get('email') or '').strip().lower()
    existing = get_user_model().objects.filter(email__iexact=pending_email).first()
    if existing:
        delete_pending_registration(pending_token)
        return existing, None

    User = get_user_model()
    try:
        with transaction.atomic():
            user = User.objects.create_user(
                username=pending_email,
                email=pending_email,
                password=data['password'],
                first_name=(data.get('first_name') or '').strip(),
                last_name=(data.get('last_name') or '').strip(),
            )
    except IntegrityError:
        delete_pending_registration(pending_token)
        existing = User.objects.filter(email__iexact=pending_email).first()
        if existing:
            return existing, None
        return None, 'That email is already registered. Sign in instead.'

    delete_pending_registration(pending_token)
    return user, None
