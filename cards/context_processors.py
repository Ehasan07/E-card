"""Template context processors for the cards app.

Exposes the current user's plan tier on every template render so views
don't have to plumb it manually.
"""

from .permissions import user_plan_tier, PREMIUM_TIERS, TIER_FREE, TIER_ANON


def user_plan(request):
    tier = user_plan_tier(getattr(request, 'user', None))
    return {
        'user_plan_tier': tier,
        'user_is_premium': tier in PREMIUM_TIERS,
        'user_is_free': tier == TIER_FREE,
        'user_is_anon': tier == TIER_ANON,
    }
