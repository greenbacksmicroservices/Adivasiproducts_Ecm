from django.urls import reverse

from .models import AdminProfile, CustomerProfile, SellerApplication

SELLER_DEMO_EMAIL = 'sel@gmail.com'
FOOTER_CATEGORY_ORDER = [
    ('Top Deals', ''),
    ('Spices', 'spices'),
    ('Silk Sarees', 'silk-sarees'),
    ('Handlooms', 'handlooms'),
    ('Hand Crafts', 'hand-crafts'),
    ('Food', 'food'),
    ('Electronic', 'electronic'),
]


def _seller_lookup_values(user):
    values = []
    if getattr(user, 'email', ''):
        values.append(user.email.strip().lower())
    if getattr(user, 'username', ''):
        values.append(user.username.strip().lower())
    return [value for value in dict.fromkeys(values) if value]


def _safe_file_url(file_field):
    try:
        if file_field and getattr(file_field, 'name', ''):
            return file_field.url
    except (OSError, ValueError):
        return ''
    return ''


def _user_initial(user):
    if not user or not user.is_authenticated:
        return 'G'
    label = user.get_full_name() or user.first_name or user.email or user.username
    return (label[:1] or 'U').upper()


def role_flags(request):
    user = getattr(request, 'user', None)
    is_seller_user = False
    seller_profile = None
    admin_profile = None
    customer_profile = None

    if user and user.is_authenticated and not user.is_staff:
        lookup_values = _seller_lookup_values(user)
        if SELLER_DEMO_EMAIL in lookup_values:
            is_seller_user = True
        elif lookup_values:
            seller_profile = SellerApplication.objects.filter(
                email__in=lookup_values,
                status=SellerApplication.Status.APPROVED,
            ).order_by('-created_at').first()
            is_seller_user = bool(seller_profile)

    avatar_url = ''
    if user and user.is_authenticated:
        if user.is_staff:
            admin_profile = AdminProfile.objects.filter(user=user).first()
            if admin_profile:
                avatar_url = _safe_file_url(admin_profile.profile_photo)
        if not avatar_url and is_seller_user and seller_profile:
            avatar_url = _safe_file_url(seller_profile.profile_photo) or _safe_file_url(seller_profile.store_logo)
        if not avatar_url:
            customer_profile = CustomerProfile.objects.filter(user=user).first()
            if customer_profile:
                avatar_url = _safe_file_url(customer_profile.photo)

    return {
        'is_seller_user': is_seller_user,
        'show_customer_account_links': bool(user and user.is_authenticated and not user.is_staff and not is_seller_user),
        'show_public_seller_link': bool((not user or not user.is_authenticated) or (user.is_authenticated and not user.is_staff and not is_seller_user)),
        'footer_quick_shop_links': _footer_quick_shop_links(),
        'current_admin_profile': admin_profile,
        'current_customer_profile': customer_profile,
        'current_seller_profile': seller_profile,
        'current_avatar_url': avatar_url,
        'current_avatar_initial': _user_initial(user),
    }


def _footer_quick_shop_links():
    links = []
    for label, slug in FOOTER_CATEGORY_ORDER:
        if not slug:
            links.append({'label': label, 'url': reverse('home')})
        else:
            links.append({'label': label, 'url': reverse('store-category', kwargs={'slug': slug})})
    return links
