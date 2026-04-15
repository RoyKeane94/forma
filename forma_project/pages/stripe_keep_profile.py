"""Stripe Checkout for keep-profile: pay first, then create the Django user."""

from __future__ import annotations

import logging

from django.conf import settings
from django.core.cache import cache

logger = logging.getLogger(__name__)

PENDING_CACHE_PREFIX = 'keep_profile_checkout:'
PENDING_TTL = 60 * 60  # 1 hour


def stripe_configured() -> bool:
    return bool(
        getattr(settings, 'STRIPE_SECRET_KEY', '').strip()
        and getattr(settings, 'STRIPE_PRODUCT_ID', '').strip()
    )


def store_pending_registration(*, pending_token: str, profile_id: int, email: str, password: str) -> None:
    cache.set(
        f'{PENDING_CACHE_PREFIX}{pending_token}',
        {'profile_id': profile_id, 'email': email, 'password': password},
        timeout=PENDING_TTL,
    )


def peek_pending_registration(pending_token: str) -> dict | None:
    return cache.get(f'{PENDING_CACHE_PREFIX}{pending_token}')


def delete_pending_registration(pending_token: str) -> None:
    cache.delete(f'{PENDING_CACHE_PREFIX}{pending_token}')


def _subscription_price_id() -> str:
    price_override = getattr(settings, 'STRIPE_PRICE_ID', '') or ''
    price_override = price_override.strip()
    if price_override:
        return price_override

    import stripe

    stripe.api_key = settings.STRIPE_SECRET_KEY
    prod = stripe.Product.retrieve(
        settings.STRIPE_PRODUCT_ID,
        expand=['default_price'],
    )
    dp = prod.default_price
    if dp is None:
        raise ValueError(
            'Stripe product has no default price. Add one in the Stripe Dashboard '
            'or set STRIPE_PRICE_ID in the environment.'
        )
    if isinstance(dp, str):
        return dp
    return dp.id


def create_subscription_checkout_session(
    *,
    success_url: str,
    cancel_url: str,
    customer_email: str,
    pending_token: str,
    profile_id: int,
) -> str:
    """
    Create a Checkout Session in subscription mode. Returns the session URL
    to redirect the browser to.
    """
    import stripe

    stripe.api_key = settings.STRIPE_SECRET_KEY
    price_id = _subscription_price_id()

    session = stripe.checkout.Session.create(
        mode='subscription',
        line_items=[{'price': price_id, 'quantity': 1}],
        success_url=success_url,
        cancel_url=cancel_url,
        customer_email=customer_email,
        metadata={
            'pending_token': pending_token,
            'profile_id': str(profile_id),
            'purpose': 'keep_profile',
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


def _stripe_object_id(value) -> str:
    if value is None:
        return ''
    if isinstance(value, str):
        return value
    return str(getattr(value, 'id', value) or '')


def save_checkout_billing_ids(user, stripe_session) -> None:
    """Store Stripe customer/subscription from a completed Checkout Session on the user’s Profile."""
    from accounts.models import Profile

    cust_id = _stripe_object_id(getattr(stripe_session, 'customer', None))
    sub_id = _stripe_object_id(getattr(stripe_session, 'subscription', None))
    if not cust_id and not sub_id:
        return
    prof, _ = Profile.objects.get_or_create(user=user)
    changed = []
    if cust_id and prof.stripe_customer_id != cust_id:
        prof.stripe_customer_id = cust_id
        changed.append('stripe_customer_id')
    if sub_id and prof.stripe_subscription_id != sub_id:
        prof.stripe_subscription_id = sub_id
        changed.append('stripe_subscription_id')
    if changed:
        prof.save(update_fields=changed)


def cancel_stripe_subscription_immediately(subscription_id: str) -> tuple[bool, str | None]:
    """
    End a subscription in Stripe right away.
    Returns (ok, error_message). If ok is False, do not delete the Django user.
    """
    sid = (subscription_id or '').strip()
    if not sid:
        return True, None
    if not stripe_configured():
        return False, 'Stripe is not configured on this server.'

    import stripe

    stripe.api_key = settings.STRIPE_SECRET_KEY
    try:
        stripe.Subscription.delete(sid)
    except stripe.error.InvalidRequestError as e:
        err = (getattr(e, 'user_message', None) or str(e) or '').lower()
        if 'no such subscription' in err or 'already been canceled' in err or 'already cancelled' in err:
            return True, None
        return False, getattr(e, 'user_message', None) or str(e)
    except stripe.error.StripeError as e:
        return False, getattr(e, 'user_message', None) or str(e)
    return True, None


def checkout_session_paid(session) -> bool:
    """True when checkout completed and subscription is usable (incl. trial start)."""
    if session.status != 'complete':
        return False
    if getattr(session, 'mode', None) != 'subscription':
        return False
    ps = getattr(session, 'payment_status', None) or ''
    return ps in ('paid', 'no_payment_required')
