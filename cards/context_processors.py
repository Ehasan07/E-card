"""Template context processors for the cards app.

Exposes the current user's plan tier + shared sidebar context on every
template render so authenticated views don't have to plumb it manually.
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


def sidebar(request):
    """Populate the shared app-sidebar with per-user data.

    Skipped entirely for anonymous requests so public pages don't run
    unnecessary DB queries.
    """
    user = getattr(request, 'user', None)
    if not user or not user.is_authenticated:
        return {
            'sidebar_first_card_slug': '',
            'sidebar_new_leads': 0,
        }

    # Local imports keep Django startup cheap.
    from .models import Card, LeadCapture, UpgradeRequest

    first_slug = (
        Card.objects
        .filter(user=user)
        .order_by('-updated_at', '-created_at')
        .values_list('slug', flat=True)
        .first()
        or ''
    )
    new_leads = LeadCapture.objects.filter(
        card__user=user,
        status=LeadCapture.STATUS_NEW,
    ).count()

    from .models import UserNotification
    unread_notifications = UserNotification.objects.filter(
        user=user, is_read=False,
    ).count()

    pending = 0
    if user.is_superuser:
        pending = UpgradeRequest.objects.filter(
            status=UpgradeRequest.STATUS_PENDING,
        ).count()

    return {
        'sidebar_first_card_slug': first_slug,
        'sidebar_new_leads': new_leads,
        'sidebar_unread_notifications': unread_notifications,
        'pending_request_count': pending,
    }
