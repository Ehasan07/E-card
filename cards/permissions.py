"""Plan-tier helpers used to gate premium features.

Payment integration is deferred — for now a user is considered
"premium" if their Profile.card_limit has been bumped above the default
by an admin (equivalent to an approved UpgradeRequest) or if a
Subscription with status=active exists.

Keep this module lightweight; it's imported from a request context
processor so it runs on every request.
"""

from functools import wraps

from django.conf import settings
from django.contrib import messages
from django.shortcuts import redirect
from django.urls import reverse


# Plan-tier constants
TIER_ANON = 'anon'
TIER_FREE = 'free'
TIER_PRO = 'pro'
TIER_TEAM = 'team'
TIER_ADMIN = 'admin'

PREMIUM_TIERS = {TIER_PRO, TIER_TEAM, TIER_ADMIN}


def user_plan_tier(user) -> str:
    """Return the effective plan tier for `user`.

    Order:
      1. Anonymous → anon
      2. Superuser → admin (implicitly premium)
      3. Active Subscription → pro/team
      4. Profile.card_limit bumps → pro/team (admin-granted premium)
      5. Everyone else → free
    """
    if not getattr(user, 'is_authenticated', False):
        return TIER_ANON

    if getattr(user, 'is_superuser', False):
        return TIER_ADMIN

    # Deferred imports so context processor stays cheap at Django boot
    from .models import Subscription

    active_sub = (
        Subscription.objects
        .filter(user=user, status=Subscription.STATUS_ACTIVE)
        .select_related('plan')
        .order_by('-current_period_end')
        .first()
    )
    if active_sub:
        plan_slug = (active_sub.plan.slug if active_sub.plan_id else '') or ''
        if 'team' in plan_slug.lower():
            return TIER_TEAM
        return TIER_PRO

    profile = getattr(user, 'profile', None)
    card_limit = getattr(profile, 'card_limit', 1) if profile else 1
    if card_limit >= 25:
        return TIER_TEAM
    if card_limit and card_limit > 1:
        return TIER_PRO

    return TIER_FREE


def is_premium(user) -> bool:
    return user_plan_tier(user) in PREMIUM_TIERS


def premium_required(feature_key: str):
    """View decorator: bounce free users to the pricing page.

    `feature_key` is passed to the pricing page via `?locked=` so the
    template can highlight *which* feature the user was trying to reach.
    """
    def decorator(view_func):
        @wraps(view_func)
        def inner(request, *args, **kwargs):
            if not is_premium(request.user):
                messages.info(
                    request,
                    'That feature is available on the Pro plan. '
                    'Upgrade to unlock it — free tier is limited to the basics.',
                )
                target = reverse('pricing') + f'?locked={feature_key}'
                return redirect(target)
            return view_func(request, *args, **kwargs)
        return inner
    return decorator


def themes_for_user(all_active_themes, user):
    """Annotate each theme with a `locked` flag so the template can show
    a paywall chip on premium themes for free users. Returns the same
    queryset/list, unchanged; callers should render `theme.locked`.
    """
    premium = is_premium(user)
    result = []
    for theme in all_active_themes:
        theme.locked = bool(getattr(theme, 'is_premium', False)) and not premium
        result.append(theme)
    return result
