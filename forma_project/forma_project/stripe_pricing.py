"""Shared Stripe subscription price resolution for Checkout."""

from __future__ import annotations

import logging

from django.conf import settings

logger = logging.getLogger(__name__)


def stripe_subscription_checkout_configured() -> bool:
    return bool(
        getattr(settings, 'STRIPE_SECRET_KEY', '').strip()
        and (
            getattr(settings, 'STRIPE_PRICE_ID', '').strip()
            or getattr(settings, 'STRIPE_PRODUCT_ID', '').strip()
        )
    )


def subscription_price_id() -> str:
    import stripe

    stripe.api_key = settings.STRIPE_SECRET_KEY
    price_override = (getattr(settings, 'STRIPE_PRICE_ID', '') or '').strip()
    if price_override:
        try:
            stripe.Price.retrieve(price_override)
            return price_override
        except stripe.error.InvalidRequestError:
            logger.warning(
                'STRIPE_PRICE_ID %r not found in Stripe; using product default price',
                price_override,
            )

    product_id = (getattr(settings, 'STRIPE_PRODUCT_ID', '') or '').strip()
    if not product_id:
        raise ValueError('Set STRIPE_PRODUCT_ID or a valid STRIPE_PRICE_ID')

    prod = stripe.Product.retrieve(product_id, expand=['default_price'])
    dp = prod.default_price
    if dp is None:
        raise ValueError(
            'Stripe product has no default price. Add one in the Stripe Dashboard '
            'or set STRIPE_PRICE_ID in the environment.'
        )
    if isinstance(dp, str):
        return dp
    return dp.id
