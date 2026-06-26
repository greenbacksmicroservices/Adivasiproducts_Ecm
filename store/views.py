from datetime import timedelta
from decimal import Decimal
from hashlib import sha1
import base64
import csv
import hmac
import json
import os
import uuid
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from django.contrib import messages
from django.contrib.auth import login, logout, update_session_auth_hash
from django.contrib.auth.decorators import login_required, user_passes_test
from django.contrib.auth.hashers import make_password
from django.contrib.auth.models import User
from django.conf import settings
from django.core.files.storage import default_storage
from django.db import transaction
from django.db.models import Avg, Count, F, Max, Q, Sum
from django.forms import modelform_factory
from django.http import FileResponse, Http404, HttpResponse, JsonResponse
from django.core.paginator import Paginator
from django.urls import reverse
from django.utils import timezone
from django.shortcuts import get_object_or_404, redirect, render
from django.template.loader import render_to_string
from django.utils.dateparse import parse_date
from django.utils.text import get_valid_filename
from django.utils.text import slugify
from django.views.decorators.http import require_http_methods

from .forms import (
    AdminImportantDocumentForm,
    AdminCustomerForm,
    AdminCustomerEditForm,
    AdminMediaForm,
    AdminOrderForm,
    AdminPasswordChangeForm,
    AdminProfileForm,
    AdminSellerApplicationForm,
    AdminSellerApplicationEditForm,
    BannerForm,
    CategoryForm,
    CouponForm,
    CourierPartnerForm,
    CustomerAddressForm,
    CustomerProfileForm,
    DeliveryAreaForm,
    EmailOTPRequestForm,
    ForgotPasswordSetForm,
    HomePageSettingForm,
    LoginForm,
    NotificationTemplateForm,
    OfferForm,
    OTPVerifyForm,
    ProductReviewForm,
    PushNotificationForm,
    RegisterForm,
    ReturnRequestForm,
    ReviewReportForm,
    SellerApplicationForm,
    SellerBankDetailsForm,
    SellerDocumentsForm,
    SellerPayoutForm,
    SellerProductForm,
    SellerReviewForm,
    SellerStoreProfileForm,
    ShipmentTrackingForm,
    ShippingChargeForm,
    SpiceItemForm,
    SubCategoryForm,
)
from .models import (
    AdminImportantDocument,
    AdminProfile,
    Banner,
    Cart,
    CartItem,
    Category,
    Coupon,
    CouponRedemption,
    CourierPartner,
    CustomerAddress,
    CustomerProfile,
    DeliveryArea,
    EmailOTP,
    HomePageSetting,
    NotificationTemplate,
    Order,
    OrderItem,
    OrderNotification,
    OrderStatusHistory,
    Offer,
    Payment,
    PaymentTransaction,
    ProductQuantityOption,
    ProductReview,
    PushNotification,
    ReturnRequest,
    ReviewReport,
    SavedProduct,
    SearchHistory,
    SellerApplication,
    SellerApplicationExtraDocument,
    SellerPayout,
    SellerReview,
    ShipmentTracking,
    ShippingCharge,
    SpiceItem,
    SpiceItemPhoto,
    StaticContent,
    SubCategory,
    SupportTicket,
    WebsiteSetting,
)
from .services.otp_service import (
    create_email_otp,
    mark_otp_used,
    normalize_email,
    send_account_email,
    verify_otp,
)

SPICE_CATEGORY_SLUG = 'spices'
SELLER_DEMO_EMAIL = 'sel@gmail.com'
SELLER_PROFILE_PHOTO_MAX_BYTES = 2 * 1024 * 1024
SELLER_PROFILE_PHOTO_ALLOWED_EXTENSIONS = {'jpg', 'jpeg', 'png', 'webp'}
SELLER_PROFILE_PHOTO_ALLOWED_TYPES = {'image/jpeg', 'image/png', 'image/webp'}
DELIVERY_FREE_THRESHOLD = Decimal('499.90')
DELIVERY_CHARGE = Decimal('80.00')
RECENT_SEARCH_LIMIT = 8

CATEGORY_PRIORITY = {
    'spices': 1,
    'silk-sarees': 2,
    'handlooms': 3,
    'hand-crafts': 4,
    'food': 5,
    'electronic': 6,
}

SPICE_SPOTLIGHT = [
    {'key': 'turmeric-powder', 'label': 'Turmeric Powder', 'icon': 'TP', 'terms': ['turmeric powder', 'haldi']},
    {'key': 'mustard-seeds', 'label': 'Mustard Seeds', 'icon': 'MS', 'terms': ['mustard seeds', 'rai']},
    {'key': 'chili-powder', 'label': 'Chili Powder', 'icon': 'CP', 'terms': ['chili powder', 'chilli powder']},
    {'key': 'cumin-seeds', 'label': 'Cumin Seeds', 'icon': 'CS', 'terms': ['cumin seeds', 'jeera seeds']},
    {'key': 'pepper', 'label': 'Pepper', 'icon': 'PP', 'terms': ['pepper', 'black pepper']},
    {'key': 'turmeric', 'label': 'Turmeric', 'icon': 'TR', 'terms': ['turmeric']},
    {'key': 'cardamom', 'label': 'Cardamom', 'icon': 'CD', 'terms': ['cardamom', 'elaichi']},
    {'key': 'cumin', 'label': 'Cumin', 'icon': 'CM', 'terms': ['cumin', 'jeera']},
]

SELLER_NAV = [
    {
        'label': 'Dashboard',
        'icon': 'fas fa-gauge-high',
        'key': 'dashboard',
    },
    {
        'label': 'Products',
        'icon': 'fas fa-boxes-stacked',
        'key': 'products',
        'children': [
            'Add Product',
            'All Products',
            'Live Products',
            'Out of Stock',
            'Product Reviews',
        ],
    },
    {
        'label': 'Orders',
        'icon': 'fas fa-bag-shopping',
        'key': 'orders',
        'children': [
            'All Orders',
            'Pending Orders',
            'Confirmed Orders',
            'Packed Orders',
            'Shipped Orders',
            'Delivered Orders',
            'Cancelled Orders',
            'Returned Orders',
        ],
    },
    {'label': 'Inventory', 'icon': 'fas fa-warehouse', 'key': 'inventory'},
    {
        'label': 'Sales & Earnings',
        'icon': 'fas fa-chart-line',
        'key': 'earnings',
        'children': ['Sales Report', 'Earnings', 'Commission', 'Payout History'],
    },
    {'label': 'Withdraw / Payout Request', 'icon': 'fas fa-money-bill-transfer', 'key': 'payout'},
    {'label': 'Returns & Refunds', 'icon': 'fas fa-arrow-rotate-left', 'key': 'returns'},
    {'label': 'Coupons / Offers', 'icon': 'fas fa-tags', 'key': 'coupons'},
    {'label': 'Messages', 'icon': 'fas fa-comments', 'key': 'messages'},
    {'label': 'Reviews & Ratings', 'icon': 'fas fa-star-half-stroke', 'key': 'ratings'},
    {'label': 'Shipping Management', 'icon': 'fas fa-truck-fast', 'key': 'shipping'},
    {
        'label': 'Settings',
        'icon': 'fas fa-gear',
        'key': 'store-settings',
        'children': ['Store Profile', 'Bank Details', 'Documents'],
    },
    {'label': 'Reports / Analytics', 'icon': 'fas fa-chart-pie', 'key': 'analytics'},
    {'label': 'Support Tickets', 'icon': 'fas fa-headset', 'key': 'support'},
]

CUSTOMER_NAV = [
    {'key': 'profile', 'label': 'Profile', 'icon': 'fa-solid fa-user'},
    {'key': 'orders', 'label': 'Orders', 'icon': 'fa-solid fa-bag-shopping'},
    {'key': 'coupons', 'label': 'Coupons', 'icon': 'fa-solid fa-ticket'},
    {'key': 'saved', 'label': 'Saved', 'icon': 'fa-solid fa-heart'},
    {'key': 'address', 'label': 'Saved Address', 'icon': 'fa-solid fa-location-dot'},
    {'key': 'help', 'label': 'Help', 'icon': 'fa-solid fa-headset'},
]


def _staff_required(user):
    return user.is_authenticated and user.is_staff


def _client_ip(request):
    forwarded = request.META.get('HTTP_X_FORWARDED_FOR', '')
    if forwarded:
        return forwarded.split(',')[0].strip()
    return request.META.get('REMOTE_ADDR') or None


def _get_admin_profile(user):
    profile, _ = AdminProfile.objects.get_or_create(user=user)
    return profile


def _touch_admin_security_profile(request):
    if not request.user.is_authenticated or not request.user.is_staff:
        return None
    profile = _get_admin_profile(request.user)
    profile.last_ip_address = _client_ip(request)
    profile.last_user_agent = request.META.get('HTTP_USER_AGENT', '')[:1000]
    profile.last_seen_at = timezone.now()
    profile.save(update_fields=['last_ip_address', 'last_user_agent', 'last_seen_at', 'updated_at'])
    return profile


def _get_customer_profile(user):
    if not user.is_authenticated:
        return None
    profile, _ = CustomerProfile.objects.get_or_create(user=user)
    return profile


def _saved_product_ids(user):
    if not user.is_authenticated:
        return set()
    return set(SavedProduct.objects.filter(user=user).values_list('product_id', flat=True))


def _delivery_charge_for_subtotal(subtotal):
    subtotal = subtotal or Decimal('0.00')
    if subtotal <= 0:
        return Decimal('0.00')
    return _shipping_charge_for_subtotal(subtotal)


def _shipping_charge_for_subtotal(subtotal):
    subtotal = subtotal or Decimal('0.00')
    if subtotal <= 0:
        return Decimal('0.00')

    active_rules = ShippingCharge.objects.filter(is_active=True).order_by('-min_order_value', 'charge')
    for rule in active_rules:
        if rule.applies_to(subtotal):
            return rule.charge_for(subtotal).quantize(Decimal('0.01'))

    return DELIVERY_CHARGE if subtotal < DELIVERY_FREE_THRESHOLD else Decimal('0.00')


def _delivery_area_for_pincode(pincode):
    pincode = ''.join(ch for ch in str(pincode or '') if ch.isdigit())
    if not pincode:
        return None
    return DeliveryArea.objects.filter(pincode=pincode).order_by('-is_active', '-is_serviceable', 'city').first()


def _validate_serviceable_pincode(pincode):
    if not DeliveryArea.objects.exists():
        return True, ''
    area = _delivery_area_for_pincode(pincode)
    if area and area.is_active and area.is_serviceable:
        return True, ''
    return False, 'Delivery is not available for this PIN code right now.'


def _coupon_lookup(code):
    code = (code or '').strip().upper()
    if not code:
        return None
    return Coupon.objects.select_related('seller').filter(code__iexact=code).first()


def _coupon_discount_for_subtotal(subtotal, coupon_code):
    coupon = _coupon_lookup(coupon_code)
    if not coupon:
        return None, Decimal('0.00'), 'Coupon code was not found.' if coupon_code else ''
    allowed, message = coupon.can_apply(subtotal)
    if not allowed:
        return coupon, Decimal('0.00'), message
    return coupon, coupon.calculate_discount(subtotal), ''


def _cart_coupon_code(request):
    return (request.session.get('checkout_coupon_code') or '').strip().upper()


def _set_cart_coupon(request, code):
    code = (code or '').strip().upper()
    if code:
        request.session['checkout_coupon_code'] = code
    else:
        request.session.pop('checkout_coupon_code', None)
    request.session.modified = True


def _normalize_search_term(term):
    return ' '.join((term or '').strip().split())[:120]


def _record_recent_search(request, term):
    term = _normalize_search_term(term)
    if not term:
        return

    normalized_term = term.lower()
    if request.user.is_authenticated:
        SearchHistory.objects.update_or_create(
            user=request.user,
            normalized_term=normalized_term,
            defaults={'term': term},
        )
        old_ids = list(SearchHistory.objects.filter(user=request.user).values_list('pk', flat=True)[RECENT_SEARCH_LIMIT:])
        if old_ids:
            SearchHistory.objects.filter(user=request.user, pk__in=old_ids).delete()
        return

    history = request.session.get('recent_search_history') or []
    filtered = [
        item
        for item in history
        if (item.get('normalized_term') if isinstance(item, dict) else str(item).lower()) != normalized_term
    ]
    filtered.insert(0, {'term': term, 'normalized_term': normalized_term})
    request.session['recent_search_history'] = filtered[:RECENT_SEARCH_LIMIT]
    request.session.modified = True


def _recent_search_terms(request):
    if request.user.is_authenticated:
        return list(SearchHistory.objects.filter(user=request.user).values_list('term', flat=True)[:RECENT_SEARCH_LIMIT])

    terms = []
    seen = set()
    for item in request.session.get('recent_search_history') or []:
        term = item.get('term') if isinstance(item, dict) else str(item)
        normalized = _normalize_search_term(term).lower()
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        terms.append(_normalize_search_term(term))
        if len(terms) >= RECENT_SEARCH_LIMIT:
            break
    return terms


def _recent_search_section(request):
    terms = _recent_search_terms(request)
    if not terms:
        return None

    cards = []
    for term in terms:
        category = Category.objects.filter(is_active=True).filter(
            Q(name__icontains=term) | Q(slug__icontains=slugify(term))
        ).first()
        matches = (
            SpiceItem.objects.filter(
                is_active=True,
                approval_status=SpiceItem.ApprovalStatus.APPROVED,
            )
            .filter(
                Q(name__icontains=term)
                | Q(short_description__icontains=term)
                | Q(description__icontains=term)
                | Q(sub_category__icontains=term)
                | Q(category__name__icontains=term)
            )
            .select_related('category', 'seller')
            .prefetch_related('gallery_images', 'quantity_options')
            .order_by('-is_featured', 'display_order', 'name')
        )
        products = list(matches[:2])
        first_product = products[0] if products else None
        cards.append(
            {
                'term': term,
                'url': f"{reverse('home')}?{urlencode({'q': term})}",
                'category': category,
                'category_url': reverse('store-category', kwargs={'slug': category.slug}) if category else '',
                'products': products,
                'image': _product_image_source(first_product) if first_product else (category.image_source if category else ''),
                'match_count': matches.count(),
            }
        )

    if not cards:
        return None

    user_label = ''
    if request.user.is_authenticated:
        user_label = request.user.get_full_name() or request.user.first_name or request.user.username

    return {
        'user_label': user_label,
        'cards': cards,
    }


def _ensure_seller_user(application):
    if application.status != SellerApplication.Status.APPROVED:
        return None

    email = application.email.strip().lower()
    user = User.objects.filter(email__iexact=email).first() or User.objects.filter(username__iexact=email).first()
    created = False
    if not user:
        user = User(username=email, email=email)
        created = True

    user.first_name = application.name
    user.email = email
    user.username = email
    user.is_staff = False
    if application.password_hash:
        user.password = application.password_hash
    user.save()
    return user, created


def _seller_status_tone(status):
    if status == SellerApplication.Status.APPROVED:
        return 'success'
    if status in {SellerApplication.Status.REJECTED, SellerApplication.Status.BLOCKED}:
        return 'danger'
    if status == SellerApplication.Status.MORE_INFO:
        return 'info'
    return 'warning'


CUSTOMER_REGISTER_SESSION_KEY = 'customer_register_pending'
SELLER_REGISTER_SESSION_KEY = 'seller_register_pending'
SELLER_REGISTER_OTP_EMAIL_SESSION_KEY = 'seller_register_otp_email'
SELLER_REGISTER_VERIFIED_SESSION_KEY = 'seller_register_email_verified'
LOGIN_OTP_SESSION_KEY = 'login_otp_email'
FORGOT_PASSWORD_EMAIL_SESSION_KEY = 'forgot_password_email'
FORGOT_PASSWORD_VERIFIED_SESSION_KEY = 'forgot_password_verified'

SELLER_APPLICATION_FILE_FIELDS = {
    'profile_photo',
    'store_logo',
    'store_banner',
    'aadhaar_front',
    'aadhaar_back',
    'pan_card',
    'gst_document',
    'business_registration_certificate',
    'cancelled_cheque',
    'shop_photo',
    'owner_photo',
    'business_proof',
    'address_proof',
    'signature_upload',
}

SELLER_ADMIN_DOCUMENT_FIELDS = [
    ('profile_photo', 'Profile Photo', ('profile_photo',), False),
    ('store_logo', 'Store Logo', ('store_logo',), False),
    ('store_banner', 'Store Banner', ('store_banner',), False),
    ('aadhaar_front', 'Aadhaar Front', ('aadhaar_front', 'aadhaar_document'), True),
    ('aadhaar_back', 'Aadhaar Back', ('aadhaar_back',), False),
    ('pan_card', 'PAN Card', ('pan_card', 'pan_document'), True),
    ('gst_document', 'GST Certificate', ('gst_document',), False),
    ('business_registration_certificate', 'Business Registration Certificate', ('business_registration_certificate', 'company_document'), False),
    ('cancelled_cheque', 'Cancelled Cheque / Passbook', ('cancelled_cheque', 'bank_document'), True),
    ('shop_photo', 'Shop Photo', ('shop_photo',), False),
    ('owner_photo', 'Owner Photo', ('owner_photo',), False),
    ('business_proof', 'Business Proof', ('business_proof', 'trade_license_document'), False),
    ('address_proof', 'Address Proof', ('address_proof',), False),
    ('signature_upload', 'Signature Upload', ('signature_upload',), False),
]
SELLER_ADMIN_DOCUMENT_FIELD_MAP = {
    key: field_names for key, _label, field_names, _required in SELLER_ADMIN_DOCUMENT_FIELDS
}


def _find_user_by_email(email):
    email = normalize_email(email)
    return User.objects.filter(Q(email__iexact=email) | Q(username__iexact=email)).first()


def _seller_pending_message(application):
    if not application or application.status == SellerApplication.Status.APPROVED:
        return ''
    if application.status == SellerApplication.Status.MORE_INFO:
        return 'Your seller account request needs more information from admin review.'
    if application.status == SellerApplication.Status.REJECTED:
        return 'Your seller account request was rejected. Please contact support for details.'
    if application.status == SellerApplication.Status.BLOCKED:
        return 'Your seller account is blocked. Please contact support.'
    return 'Your seller account request is pending admin approval.'


def _latest_seller_application(email):
    return SellerApplication.objects.filter(email__iexact=normalize_email(email)).order_by('-created_at').first()


def _otp_cooldown_remaining(email, purpose):
    latest = (
        EmailOTP.objects.filter(email__iexact=normalize_email(email), purpose=purpose, is_used=False)
        .order_by('-created_at')
        .first()
    )
    if not latest:
        return 0
    cooldown = int(getattr(settings, 'EMAIL_OTP_RESEND_COOLDOWN_SECONDS', 60))
    elapsed = int((timezone.now() - latest.created_at).total_seconds())
    return max(0, cooldown - elapsed)


def _seller_registration_verified_email(request):
    state = request.session.get(SELLER_REGISTER_VERIFIED_SESSION_KEY) or {}
    if not state.get('verified'):
        return ''
    return normalize_email(state.get('email'))


def _seller_registration_email_is_verified(request, email):
    verified_email = _seller_registration_verified_email(request)
    return bool(verified_email and verified_email == normalize_email(email))


def _clear_seller_registration_otp_state(request):
    request.session.pop(SELLER_REGISTER_OTP_EMAIL_SESSION_KEY, None)
    request.session.pop(SELLER_REGISTER_VERIFIED_SESSION_KEY, None)


def _save_pending_upload(uploaded_file, flow):
    if not uploaded_file:
        return ''
    filename = get_valid_filename(os.path.basename(uploaded_file.name)) or 'upload'
    return default_storage.save(f'otp_drafts/{flow}/{uuid.uuid4().hex}_{filename}', uploaded_file)


def _stash_customer_registration(form):
    cleaned = form.cleaned_data
    photo_path = _save_pending_upload(cleaned.get('photo'), 'customer_register')
    return {
        'first_name': cleaned['first_name'],
        'email': normalize_email(cleaned['email']),
        'phone': cleaned['phone'],
        'photo_path': photo_path,
        'password_hash': make_password(cleaned['password1']),
    }


def _create_customer_from_pending(data):
    email = normalize_email(data.get('email'))
    if _find_user_by_email(email):
        return None, 'This email already has an account.'
    user = User(username=email, email=email, first_name=data.get('first_name', ''))
    user.password = data.get('password_hash', '')
    user.save()
    CustomerProfile.objects.create(
        user=user,
        phone=data.get('phone', ''),
        photo=data.get('photo_path') or None,
        email_verified=True,
    )
    return user, ''


def _serialize_seller_value(value):
    if hasattr(value, 'isoformat'):
        return value.isoformat()
    return value


def _stash_seller_registration(form):
    cleaned = form.cleaned_data
    data = {
        'password_hash': make_password(cleaned['password']),
        'fields': {},
        'files': {},
        'extra_documents': [],
    }
    skip_fields = {'password', 'confirm_password', 'confirm_bank_account_number', 'extra_documents'}
    for field_name in SellerApplicationForm.Meta.fields:
        if field_name in skip_fields:
            continue
        if field_name in SELLER_APPLICATION_FILE_FIELDS:
            data['files'][field_name] = _save_pending_upload(cleaned.get(field_name), 'seller_register')
        else:
            data['fields'][field_name] = _serialize_seller_value(cleaned.get(field_name))

    for uploaded_file in cleaned.get('extra_documents') or []:
        data['extra_documents'].append({
            'path': _save_pending_upload(uploaded_file, 'seller_register_extra'),
            'original_name': getattr(uploaded_file, 'name', ''),
        })
    return data


def _create_seller_from_pending(data):
    fields = data.get('fields') or {}
    email = normalize_email(fields.get('email'))
    if SellerApplication.objects.filter(email__iexact=email).exists():
        return None, 'A seller application with this email already exists.'
    if _find_user_by_email(email):
        return None, 'This email already has an account. Please use another email or contact admin.'

    application = SellerApplication()
    for field_name, value in fields.items():
        if field_name == 'owner_dob' and value:
            value = parse_date(value)
        setattr(application, field_name, value)
    for field_name, path in (data.get('files') or {}).items():
        if path:
            setattr(application, field_name, path)

    application.email = email
    application.password_hash = data.get('password_hash', '')
    application.email_verified = True
    application.status = SellerApplication.Status.PENDING
    application.store_display_name = application.store_display_name or application.store_name
    application.business_address = application.owner_address
    application.pickup_address = application.pickup_full_address
    application.admin_note = ''
    application.admin_remark = ''
    application.reviewed_by = None
    application.reviewed_at = None
    application.save()

    for document in data.get('extra_documents') or []:
        if document.get('path'):
            SellerApplicationExtraDocument.objects.create(
                application=application,
                document_name=document.get('document_name') or document.get('original_name', ''),
                file=document['path'],
                original_name=document.get('original_name', ''),
            )
    return application, ''


def _request_flow_otp(request, email, purpose):
    try:
        return create_email_otp(email, purpose, request=request)
    except Exception:
        messages.error(request, 'We could not send OTP right now. Please check email settings or try again.')
        return None


def _render_otp_verify(
    request,
    *,
    email,
    purpose,
    verify_route,
    resend_route,
    title,
    subtitle,
    submit_label='Verify OTP',
    back_url=None,
    info_message='OTP sent to your email.',
    error_message='',
    form=None,
    icon_class='fa-solid fa-shield-halved',
):
    return render(
        request,
        'auth/otp_verify.html',
        {
            'form': form or OTPVerifyForm(),
            'email': normalize_email(email),
            'verify_url': reverse(verify_route),
            'resend_url': reverse(resend_route),
            'back_url': back_url,
            'title': title,
            'subtitle': subtitle,
            'submit_label': submit_label,
            'info_message': info_message,
            'error_message': error_message,
            'cooldown_seconds': _otp_cooldown_remaining(email, purpose),
            'icon_class': icon_class,
        },
    )


def _admin_snapshot():
    stock_summary = SpiceItem.objects.aggregate(total_stock=Sum('stock'))
    open_order_count = Order.objects.exclude(
        status__in=[Order.Status.DELIVERED, Order.Status.CANCELLED, Order.Status.RETURNED],
    ).count()
    return {
        'item_count': SpiceItem.objects.count(),
        'active_item_count': SpiceItem.objects.filter(is_active=True).count(),
        'inactive_item_count': SpiceItem.objects.filter(is_active=False).count(),
        'featured_item_count': SpiceItem.objects.filter(is_featured=True, is_active=True).count(),
        'category_count': Category.objects.count(),
        'active_category_count': Category.objects.filter(is_active=True).count(),
        'banner_count': Banner.objects.count(),
        'active_banner_count': Banner.objects.filter(is_active=True).count(),
        'large_banner_count': Banner.objects.filter(is_active=True, placement=Banner.BannerPlacement.LARGE).count(),
        'compact_banner_count': Banner.objects.filter(is_active=True, placement=Banner.BannerPlacement.COMPACT).count(),
        'total_stock': stock_summary.get('total_stock') or 0,
        'low_stock_count': SpiceItem.objects.filter(is_active=True, stock__gt=0, stock__lte=10).count(),
        'out_stock_count': SpiceItem.objects.filter(is_active=True, stock=0).count(),
        'sub_category_count': SubCategory.objects.count(),
        'order_count': Order.objects.count(),
        'open_order_count': open_order_count,
        'pending_order_count': Order.objects.filter(status=Order.Status.PENDING).count(),
        'packed_order_count': Order.objects.filter(status=Order.Status.PACKED).count(),
        'shipped_order_count': Order.objects.filter(status__in=[Order.Status.SHIPPED, Order.Status.OUT_FOR_DELIVERY]).count(),
        'delivered_order_count': Order.objects.filter(status=Order.Status.DELIVERED).count(),
        'cancelled_order_count': Order.objects.filter(status=Order.Status.CANCELLED).count(),
        'today_order_count': Order.objects.filter(created_at__date=timezone.localdate()).count(),
        'unseen_order_count': Order.objects.filter(is_seen_by_admin=False).count(),
        'total_order_revenue': Order.objects.filter(status=Order.Status.DELIVERED).aggregate(total=Sum('total_amount')).get('total') or Decimal('0'),
    }


def _build_signature():
    category_meta = Category.objects.aggregate(last=Max('updated_at'), total=Count('id'))
    banner_meta = Banner.objects.aggregate(last=Max('updated_at'), total=Count('id'))
    item_meta = SpiceItem.objects.aggregate(last=Max('updated_at'), total=Count('id'))
    item_photo_meta = SpiceItemPhoto.objects.aggregate(last=Max('updated_at'), total=Count('id'))
    quantity_option_meta = ProductQuantityOption.objects.aggregate(last=Max('updated_at'), total=Count('id'))
    sub_category_meta = SubCategory.objects.aggregate(last=Max('updated_at'), total=Count('id'))
    homepage_meta = HomePageSetting.objects.aggregate(last=Max('updated_at'), total=Count('id'))
    seller_meta = SellerApplication.objects.aggregate(last=Max('updated_at'), total=Count('id'))
    order_meta = Order.objects.aggregate(last=Max('updated_at'), total=Count('id'))
    payment_meta = PaymentTransaction.objects.aggregate(last=Max('updated_at'), total=Count('id'))
    return_meta = ReturnRequest.objects.aggregate(last=Max('updated_at'), total=Count('id'))
    coupon_meta = Coupon.objects.aggregate(last=Max('updated_at'), total=Count('id'))
    offer_meta = Offer.objects.aggregate(last=Max('updated_at'), total=Count('id'))
    shipping_charge_meta = ShippingCharge.objects.aggregate(last=Max('updated_at'), total=Count('id'))
    courier_meta = CourierPartner.objects.aggregate(last=Max('updated_at'), total=Count('id'))
    delivery_meta = DeliveryArea.objects.aggregate(last=Max('updated_at'), total=Count('id'))
    tracking_meta = ShipmentTracking.objects.aggregate(last=Max('updated_at'), total=Count('id'))
    review_meta = ProductReview.objects.aggregate(last=Max('updated_at'), total=Count('id'))
    seller_review_meta = SellerReview.objects.aggregate(last=Max('updated_at'), total=Count('id'))
    review_report_meta = ReviewReport.objects.aggregate(last=Max('updated_at'), total=Count('id'))
    ticket_meta = SupportTicket.objects.aggregate(last=Max('updated_at'), total=Count('id'))
    content_meta = StaticContent.objects.aggregate(last=Max('updated_at'), total=Count('id'))
    notification_meta = NotificationTemplate.objects.aggregate(last=Max('updated_at'), total=Count('id'))
    push_meta = PushNotification.objects.aggregate(last=Max('updated_at'), total=Count('id'))
    payout_meta = SellerPayout.objects.aggregate(last=Max('updated_at'), total=Count('id'))
    coupon_redemption_meta = CouponRedemption.objects.aggregate(last=Max('updated_at'), total=Count('id'))
    website_setting_meta = WebsiteSetting.objects.aggregate(last=Max('updated_at'), total=Count('id'))

    signature_bits = [
        str(category_meta.get('last') or '0'),
        str(category_meta.get('total') or 0),
        str(banner_meta.get('last') or '0'),
        str(banner_meta.get('total') or 0),
        str(item_meta.get('last') or '0'),
        str(item_meta.get('total') or 0),
        str(item_photo_meta.get('last') or '0'),
        str(item_photo_meta.get('total') or 0),
        str(quantity_option_meta.get('last') or '0'),
        str(quantity_option_meta.get('total') or 0),
        str(sub_category_meta.get('last') or '0'),
        str(sub_category_meta.get('total') or 0),
        str(homepage_meta.get('last') or '0'),
        str(homepage_meta.get('total') or 0),
        str(seller_meta.get('last') or '0'),
        str(seller_meta.get('total') or 0),
        str(order_meta.get('last') or '0'),
        str(order_meta.get('total') or 0),
        str(payment_meta.get('last') or '0'),
        str(payment_meta.get('total') or 0),
        str(return_meta.get('last') or '0'),
        str(return_meta.get('total') or 0),
        str(coupon_meta.get('last') or '0'),
        str(coupon_meta.get('total') or 0),
        str(offer_meta.get('last') or '0'),
        str(offer_meta.get('total') or 0),
        str(shipping_charge_meta.get('last') or '0'),
        str(shipping_charge_meta.get('total') or 0),
        str(courier_meta.get('last') or '0'),
        str(courier_meta.get('total') or 0),
        str(delivery_meta.get('last') or '0'),
        str(delivery_meta.get('total') or 0),
        str(tracking_meta.get('last') or '0'),
        str(tracking_meta.get('total') or 0),
        str(review_meta.get('last') or '0'),
        str(review_meta.get('total') or 0),
        str(seller_review_meta.get('last') or '0'),
        str(seller_review_meta.get('total') or 0),
        str(review_report_meta.get('last') or '0'),
        str(review_report_meta.get('total') or 0),
        str(ticket_meta.get('last') or '0'),
        str(ticket_meta.get('total') or 0),
        str(content_meta.get('last') or '0'),
        str(content_meta.get('total') or 0),
        str(notification_meta.get('last') or '0'),
        str(notification_meta.get('total') or 0),
        str(push_meta.get('last') or '0'),
        str(push_meta.get('total') or 0),
        str(payout_meta.get('last') or '0'),
        str(payout_meta.get('total') or 0),
        str(coupon_redemption_meta.get('last') or '0'),
        str(coupon_redemption_meta.get('total') or 0),
        str(website_setting_meta.get('last') or '0'),
        str(website_setting_meta.get('total') or 0),
    ]
    return sha1('|'.join(signature_bits).encode('utf-8')).hexdigest()


def _subcategory_options_for_category(category_slug):
    if not category_slug:
        return []

    sub_categories = list(
        SubCategory.objects.filter(category__slug=category_slug, is_active=True)
        .select_related('category')
        .order_by('display_order', 'name')
    )
    if sub_categories:
        return [
            {
                'key': sub_category.slug,
                'label': sub_category.name,
                'icon': sub_category.icon_label,
                'image': sub_category.image_source,
                'terms': [sub_category.name, sub_category.slug.replace('-', ' ')],
            }
            for sub_category in sub_categories
        ]

    if category_slug == SPICE_CATEGORY_SLUG:
        return SPICE_SPOTLIGHT

    product_sub_categories = (
        SpiceItem.objects.filter(category__slug=category_slug)
        .exclude(sub_category__exact='')
        .values_list('sub_category', flat=True)
        .distinct()
        .order_by('sub_category')
    )
    return [
        {
            'key': slugify(name) or name.lower(),
            'label': name,
            'icon': ''.join(word[:1] for word in name.split()[:2]).upper() or name[:2].upper(),
            'image': '',
            'terms': [name],
        }
        for name in product_sub_categories
    ]


def _subcategory_terms(category_slug, selected_spice):
    for option in _subcategory_options_for_category(category_slug):
        if option['key'] == selected_spice:
            return option.get('terms') or [option['label']]
    return []


def _store_queryset(search_text='', category_slug='', selected_spice=''):
    categories = Category.objects.filter(is_active=True).annotate(
        active_item_count=Count(
            'items',
            filter=Q(
                items__is_active=True,
                items__approval_status=SpiceItem.ApprovalStatus.APPROVED,
            ),
            distinct=True,
        )
    )
    large_banners = Banner.objects.filter(
        is_active=True,
        placement=Banner.BannerPlacement.LARGE,
    ).order_by('display_order', '-updated_at')[:8]
    compact_banners = Banner.objects.filter(
        is_active=True,
        placement=Banner.BannerPlacement.COMPACT,
    ).order_by('display_order', '-updated_at')[:12]

    products = SpiceItem.objects.filter(
        is_active=True,
        approval_status=SpiceItem.ApprovalStatus.APPROVED,
    ).select_related('category', 'seller').prefetch_related('gallery_images', 'quantity_options').order_by(
        '-is_featured',
        'display_order',
        'name',
    )

    if search_text:
        products = products.filter(
            Q(name__icontains=search_text)
            | Q(short_description__icontains=search_text)
            | Q(description__icontains=search_text)
            | Q(category__name__icontains=search_text)
        )

    if category_slug:
        products = products.filter(category__slug=category_slug)

    spice_terms = _subcategory_terms(category_slug, selected_spice)
    if category_slug and spice_terms:
        spice_query = Q()
        for term in spice_terms:
            spice_query |= Q(sub_category__iexact=term)
            spice_query |= Q(name__icontains=term)
            spice_query |= Q(short_description__icontains=term)
            spice_query |= Q(description__icontains=term)
        products = products.filter(category__slug=category_slug).filter(spice_query)

    return categories, large_banners, compact_banners, products


def _sorted_categories(categories):
    return sorted(
        categories,
        key=lambda category: (
            CATEGORY_PRIORITY.get(category.slug, 100 + category.display_order),
            category.display_order,
            category.name.lower(),
        ),
    )


def _build_tabs(categories, selected_category):
    tabs = []

    tabs.append(
        {
            'slug': '',
            'label': 'Top Deals',
            'icon': 'TD',
            'active': selected_category == '',
            'count': SpiceItem.objects.filter(
                is_active=True,
                approval_status=SpiceItem.ApprovalStatus.APPROVED,
            ).count(),
        }
    )

    for category in _sorted_categories(categories):
        tabs.append(
            {
                'slug': category.slug,
                'label': category.name,
                'icon': category.icon_emoji or category.name[:2].upper(),
                'active': selected_category == category.slug,
                'count': category.active_item_count,
                'color': category.highlight_color,
                'image': category.image_source,
            }
        )

    return tabs


def _build_spice_filters(selected_spice, selected_category=''):
    return [
        {
            'key': option['key'],
            'label': option['label'],
            'icon': option['icon'],
            'image': option.get('image', ''),
            'active': option['key'] == selected_spice,
        }
        for option in _subcategory_options_for_category(selected_category)
    ]


def _build_home_sections(categories, products):
    sections = []

    for category in _sorted_categories(categories):
        section_products = list(products.filter(category=category)[:5])
        if not section_products:
            continue
        sections.append(
            {
                'category': category,
                'products': section_products,
                'total': category.active_item_count,
            }
        )

    return sections


def _build_store_context(search_text, selected_category, selected_spice):
    categories, large_banners, compact_banners, products = _store_queryset(search_text, selected_category, selected_spice)
    homepage_settings = HomePageSetting.load()
    is_top_deals = selected_category == ''
    spice_filters = _build_spice_filters(selected_spice, selected_category)
    show_spice_filters = bool(selected_category and spice_filters)
    show_hero = is_top_deals and homepage_settings.hero_enabled
    show_compact_hero = is_top_deals and homepage_settings.compact_hero_enabled

    if not show_spice_filters:
        selected_spice = ''

    current_category_label = 'Top Deals'
    if selected_category:
        current_category = next(
            (category for category in categories if category.slug == selected_category),
            None,
        )
        current_category_label = current_category.name if current_category else 'Products'

    return {
        'category_tabs': _build_tabs(categories, selected_category),
        'spice_filters': spice_filters,
        'show_spice_filters': show_spice_filters,
        'show_hero': show_hero,
        'show_compact_hero': show_compact_hero,
        'is_top_deals': is_top_deals,
        'home_sections': _build_home_sections(categories, products) if is_top_deals else [],
        'current_category_label': current_category_label,
        'empty_products_message': 'No products available in this category yet.' if selected_category and not search_text else 'No products found',
        'homepage_settings': homepage_settings,
        'banners': large_banners if show_hero else [],
        'compact_banners': compact_banners if show_compact_hero else [],
        'products': products,
        'search_text': search_text,
        'selected_category': selected_category,
        'selected_spice': selected_spice,
    }


def _render_storefront(request, category_slug=''):
    search_text = request.GET.get('q', '').strip()
    selected_category = request.GET.get('category', '').strip() or category_slug.strip()
    selected_spice = request.GET.get('spice', '').strip()

    if not selected_category:
        selected_spice = ''
    if search_text:
        _record_recent_search(request, search_text)

    context = _build_store_context(search_text, selected_category, selected_spice)
    context['signature'] = _build_signature()
    context['view_key'] = f'{search_text}|{selected_category}|{selected_spice}'
    context['saved_product_ids'] = _saved_product_ids(request.user)
    context['recent_search_section'] = _recent_search_section(request)
    return render(request, 'website/home.html', context)


def home(request):
    return _render_storefront(request)


def category_page(request, slug):
    return _render_storefront(request, category_slug=slug)


def _static_content_context(page, fallback_title, fallback_body):
    content = StaticContent.objects.filter(page=page, is_active=True).first()
    return {
        'content_title': content.title if content else fallback_title,
        'content_body': content.body if content and content.body else fallback_body,
        'search_text': '',
        'selected_category': '',
        'selected_spice': '',
    }


FOOTER_INFO_PAGES = {
    'help-center': {
        'title': 'Help Center',
        'intro': 'Find quick guidance for creating an account, placing orders, making payments, tracking delivery, requesting returns or refunds, and contacting Lexvers support.',
        'sections': [
            {'heading': 'How to Create Account', 'items': ['Open Create Account from the header or login menu.', 'Enter accurate name, email, phone, and password details.', 'Complete OTP verification where required, then manage profile and addresses from the customer panel.']},
            {'heading': 'How to Place Order', 'items': ['Browse Top Deals or category pages and open a product.', 'Add the product to cart, review quantity and price, then continue to checkout.', 'Choose or add a delivery address before confirming the order.']},
            {'heading': 'How to Make Payment', 'items': ['Select the available payment method on the checkout payment page.', 'Review subtotal, delivery charge, discount, and final total before placing the order.', 'If a payment stays pending or fails, wait for confirmation before placing a duplicate order.']},
            {'heading': 'How to Track Order', 'items': ['Login with the same account used for checkout.', 'Open My Orders to view order number, items, payment status, delivery address, and order status.', 'Shipment details appear when courier tracking is added by the seller or admin team.']},
            {'heading': 'How to Request Return or Refund', 'items': ['Check whether the product and order status are eligible for return or refund.', 'Contact support with order number, registered phone or email, reason, and photos if relevant.', 'Refund approval depends on order status, product eligibility, and verification.']},
            {'heading': 'Customer Support Contact', 'items': ['Phone: +91 9938797981.', 'Email: greenbacks@gmail.com.', 'Location: Bhubaneswar, Odisha, India.']},
        ],
    },
    'faqs': {
        'title': 'FAQs',
        'intro': 'Answers to common questions about shopping, shipping, returns, refunds, sellers, payments, and accounts.',
        'sections': [
            {'heading': 'Account Related Questions', 'items': ['Create an account from the registration page and verify OTP where required.', 'Keep your email, phone, password, profile details, and saved addresses updated.', 'Use forgot password if you cannot access your account, and never share OTP or login credentials.']},
            {'heading': 'Order Related Questions', 'items': ['Add products to cart, choose address, and place the order from checkout.', 'Your order history shows order number, products, quantity, status, and total amount.', 'Order status can move through placed, packed, shipped, out for delivery, delivered, cancelled, or returned.']},
            {'heading': 'Payment Related Questions', 'items': ['Payment method and payment status are saved with each order.', 'Check the final payable amount before confirming checkout.', 'Payment and refund records are linked to order records for support and reconciliation.']},
            {'heading': 'Shipping Related Questions', 'items': ['Delivery availability depends on configured serviceable areas and pincode support.', 'Shipping charges and free delivery rules may change based on cart subtotal and active shipping settings.', 'Tracking details appear when shipment tracking is updated.']},
            {'heading': 'Return and Refund Questions', 'items': ['Returns depend on product eligibility and order status.', 'Refund processing starts after return approval and verification.', 'Non-returnable products, used items, or incomplete packages may be rejected.']},
            {'heading': 'Seller Registration Questions', 'items': ['Seller registration requires business, bank, pickup, product category, and KYC documents.', 'Seller dashboard access is enabled only after admin approval.', 'Admin may request more information or reject incomplete applications.']},
        ],
    },
    'track-order': {
        'title': 'Track Order',
        'intro': 'Track your Lexvers orders from the customer order history page or use your order number when contacting support.',
        'sections': [
            {'heading': 'For Logged In Customers', 'items': ['Open My Orders to see every order placed from your account.', 'Use the order detail page to check products, delivery address, amount, and status.', 'Shipment tracking appears when courier information is added.']},
            {'heading': 'If You Are Not Logged In', 'items': ['Login with the same account used during checkout.', 'After login, open My Orders or Customer Panel > Orders.', 'Keep your order number ready if you contact support.']},
            {'heading': 'How Tracking Works', 'items': ['Order placed means your order has been received by Lexvers.', 'Packed means the seller or fulfillment team is preparing the parcel.', 'Shipped means the parcel has been handed to a courier or delivery partner.', 'Out for delivery means the parcel is near the saved delivery address.', 'Delivered means the order reached the saved delivery address.']},
        ],
        'auth_cta': ('Open My Orders', 'my-orders'),
        'guest_cta': ('Login to Track Order', 'login'),
    },
    'return-refund-policy': {
        'title': 'Return & Refund Policy',
        'intro': 'This policy explains return eligibility, refund eligibility, processing steps, and support guidance.',
        'sections': [
            {'heading': 'Return Eligibility', 'items': ['Products must be unused, complete, and in original condition unless damaged on delivery.', 'Return eligibility may vary by category, product condition, seller rules, and order status.', 'Requests should include order details and a clear reason.']},
            {'heading': 'Refund Eligibility', 'items': ['Refunds are considered after return approval and item verification.', 'Cancelled or returned orders may be refunded according to payment method and order state.', 'Shipping or handling charges may be non-refundable where applicable.']},
            {'heading': 'Refund Process & Time', 'items': ['Submit a return/support request with order number and issue details.', 'Admin or seller review confirms eligibility.', 'Approved refunds are processed after verification; bank/payment timelines may vary.']},
            {'heading': 'Non-Returnable Items', 'items': ['Used, damaged after delivery, incomplete, customized, perishable, or hygiene-sensitive products may not be returnable.', 'Items without packaging, invoice details, or clear proof may be rejected.', 'Fraudulent or repeated misuse can restrict return access.']},
            {'heading': 'Contact Support', 'items': ['Use +91 9938797981 or greenbacks@gmail.com for assistance.', 'Share order number, registered phone/email, and photos if relevant.']},
        ],
    },
    'shipping-policy': {
        'title': 'Shipping Policy',
        'intro': 'Shipping on Lexvers depends on delivery area coverage, courier availability, and active store settings.',
        'sections': [
            {'heading': 'Delivery Areas', 'items': ['Serviceability may be checked by pincode where delivery areas are configured.', 'Some locations may not support delivery or cash on delivery.', 'Coverage may expand as more courier partners are added.']},
            {'heading': 'Delivery Timeline', 'items': ['Most orders are processed after confirmation and packing.', 'Delivery timeline can vary by product category, seller pickup location, courier load, and destination.', 'Estimated timelines are informational and may change during peak periods.']},
            {'heading': 'Shipping Charges and Free Delivery', 'items': ['Shipping fees are calculated from active shipping charge rules where configured.', 'Free delivery may apply above the configured cart threshold when an active rule supports it.', 'Final charges are shown before order placement.']},
            {'heading': 'Delivery Partners and Courier Details', 'items': ['Courier partner details are managed from the admin shipping area when available.', 'The assigned courier name and tracking number appear after shipment tracking is updated.', 'Delivery partner availability can vary by destination and serviceability.']},
            {'heading': 'Tracking Details', 'items': ['Tracking details appear when courier and tracking number are added.', 'Order status updates may include packed, shipped, out for delivery, delivered, cancelled, or returned.', 'Contact support with your order number if tracking is delayed.']},
        ],
    },
    'cancellation-policy': {
        'title': 'Cancellation Policy',
        'intro': 'Cancellation availability depends on order status, packing, shipment, and product handling stage.',
        'sections': [
            {'heading': 'When You Can Cancel', 'items': ['Orders can generally be cancelled before packing or shipment starts.', 'Cancellation may be easiest while the order is still placed or pending confirmation.', 'Contact support quickly with your order number.']},
            {'heading': 'When Cancellation Is Not Allowed', 'items': ['Cancellation may not be allowed after dispatch, out-for-delivery, or delivery.', 'Customized, perishable, or seller-processed items may have stricter rules.', 'Orders already handed to courier may need a return workflow instead.']},
            {'heading': 'Cancellation Refund Process', 'items': ['Eligible prepaid cancellations are refunded after cancellation approval.', 'Refund timing depends on payment provider and bank processing.', 'Cash on delivery orders do not require payment refund unless already collected.']},
            {'heading': 'COD and Online Payment Guidance', 'items': ['For cash on delivery, contact support before dispatch to stop fulfillment when possible.', 'For online payments, keep payment reference and order number ready for refund support.', 'If the order is already shipped, the return workflow may apply instead of cancellation.']},
            {'heading': 'Contact Support', 'items': ['Call +91 9938797981 or email greenbacks@gmail.com.', 'Share the order number, registered email/phone, and cancellation reason.']},
        ],
    },
    'seller-guidelines': {
        'title': 'Seller Guidelines',
        'intro': 'Guidelines for becoming and operating as a Lexvers seller.',
        'sections': [
            {'heading': 'Seller Registration Process', 'items': ['Submit seller registration with personal, store, bank, pickup, category, and document details.', 'Verify required information and wait for admin review.', 'Seller dashboard access starts only after approval.']},
            {'heading': 'Admin Approval Process', 'items': ['Lexvers admin reviews each submitted seller application.', 'Admin may approve, reject, block, or request more information based on documents and marketplace standards.', 'Approved sellers can access the seller dashboard and start managing products, orders, payouts, and support.']},
            {'heading': 'Document Requirements', 'items': ['Aadhaar front, PAN card, and cancelled cheque/passbook are key documents.', 'GST certificate, business proof, address proof, shop photo, owner photo, and signature may be required depending on business type.', 'Documents must be clear, valid, and owned by the applicant/business.']},
            {'heading': 'Product Listing Rules', 'items': ['Use accurate names, descriptions, category, price, images, stock, and specifications.', 'Do not list prohibited, fake, misleading, or unsafe items.', 'Seller products may require admin approval before customer visibility.']},
            {'heading': 'Order Handling Rules', 'items': ['Keep stock updated and process confirmed orders promptly.', 'Update order status as fulfillment moves forward.', 'Respond to support requests, returns, and customer issues responsibly.']},
            {'heading': 'Packaging and Shipping Responsibility', 'items': ['Pack products safely and accurately according to item type.', 'Share courier and tracking details when available.', 'Coordinate pickup, dispatch, and delivery support according to marketplace processes.']},
            {'heading': 'Marketplace Standards', 'items': ['Maintain truthful product information and fair pricing.', 'Follow pickup, shipping, return, and refund processes.', 'Admin can request more information, block, reject, or review sellers for policy issues.']},
        ],
        'cta': ('Become a Seller', 'become-seller'),
    },
    'privacy-policy': {
        'title': 'Privacy Policy',
        'intro': 'How Lexvers handles account, order, payment, session, and support information.',
        'sections': [
            {'heading': 'Information Collected', 'items': ['Name, email, phone, address, profile details, and account activity.', 'Order, cart, saved product, payment status, delivery, return, and support details.', 'Seller registration, business, bank, pickup, and document information where applicable.']},
            {'heading': 'Account / Order / Payment Data', 'items': ['Account information is used for login, order history, checkout, support, and notifications.', 'Order and payment data is used for fulfillment, invoices, refunds, and reconciliation.', 'Seller data is used for approval, dashboard access, listings, payouts, and compliance.']},
            {'heading': 'Cookies & Sessions', 'items': ['Cookies and sessions help login, cart, checkout, CSRF protection, saved products, and preferences work correctly.', 'Browser preferences may remember theme or interface choices.']},
            {'heading': 'Data Usage', 'items': ['We use data to operate the marketplace, process orders, improve service, prevent fraud, and communicate updates.', 'We do not intentionally publish private customer or seller account data.']},
            {'heading': 'Data Security & Contact', 'items': ['Reasonable safeguards are used for account and operational data.', 'For privacy questions, contact greenbacks@gmail.com or +91 9938797981.']},
        ],
    },
    'terms-and-conditions': {
        'title': 'Terms & Conditions',
        'intro': 'Rules for using Lexvers as a customer, seller, or website visitor.',
        'sections': [
            {'heading': 'Website Usage', 'items': ['Use the website only for lawful shopping, seller, account, and marketplace activities.', 'Do not misuse forms, checkout, OTP, support, seller registration, or admin-protected workflows.', 'Content, prices, offers, and availability may be updated from time to time.']},
            {'heading': 'Customer Account Rules', 'items': ['Customers must provide accurate account, address, and contact details.', 'Customers are responsible for keeping login credentials secure.', 'Orders must comply with payment, delivery, cancellation, return, and refund policies.']},
            {'heading': 'Seller Account Rules', 'items': ['Sellers must submit accurate registration, document, product, bank, and pickup details.', 'Seller access is subject to admin approval and continued compliance.', 'Seller listings must be truthful, safe, and within marketplace standards.']},
            {'heading': 'Orders, Payments, Returns & Refunds', 'items': ['Orders depend on product availability, serviceability, payment status, and fulfillment feasibility.', 'Returns, refunds, and cancellations are handled according to the relevant policies.', 'Payment records and order history may be used for support and reconciliation.']},
            {'heading': 'Liability & Marketplace Rules', 'items': ['Lexvers may review, modify, reject, block, or remove content and accounts that violate marketplace standards.', 'Sellers remain responsible for their product accuracy and fulfillment obligations.', 'Use of the marketplace means accepting these terms and related policies.']},
        ],
    },
    'cookie-policy': {
        'title': 'Cookie Policy',
        'intro': 'This policy explains how Lexvers may use cookies and similar browser storage.',
        'sections': [
            {'heading': 'What Cookies Are', 'items': ['Cookies are small browser files used to remember session, preference, and activity information.', 'They help keep checkout, login, cart, and account features working.']},
            {'heading': 'Why Cookies Are Used', 'items': ['Maintain login sessions and secure forms.', 'Remember cart, saved products, theme preference, and browsing state.', 'Improve store performance and customer experience.']},
            {'heading': 'Login / Session Cookies', 'items': ['Session cookies help keep authenticated pages secure.', 'CSRF cookies protect forms from unauthorized requests.', 'Logging out clears active account access from the browser session.']},
            {'heading': 'Analytics / Preferences', 'items': ['Preference storage may remember theme or interface choices.', 'If analytics are added later, they should be used to understand website performance and improve service.']},
            {'heading': 'Managing Cookies', 'items': ['You can clear or block cookies from your browser settings.', 'Blocking required cookies may affect login, cart, checkout, and account pages.']},
        ],
    },
    'disclaimer': {
        'title': 'Disclaimer',
        'intro': 'Important information about marketplace content, product details, pricing, availability, and responsibility.',
        'sections': [
            {'heading': 'Product Information', 'items': ['Product names, images, descriptions, specifications, and availability may be updated over time.', 'Images can be representative and may vary by batch, seller, or packaging.', 'Customers should review product details before ordering.']},
            {'heading': 'Seller Responsibility', 'items': ['Seller-listed products are provided by individual approved sellers.', 'Sellers are responsible for truthful listings, documents, stock, fulfillment, and product quality.', 'Lexvers may review or restrict seller content where required.']},
            {'heading': 'Pricing & Availability', 'items': ['Prices, offers, stock, discounts, and shipping rules may change without prior notice.', 'Orders depend on successful checkout, stock availability, and serviceability.', 'Errors may be corrected when identified.']},
            {'heading': 'External Links', 'items': ['Some links may open third-party services or partner websites.', 'Lexvers is not responsible for external website content, availability, or policy changes.']},
            {'heading': 'General Limitation', 'items': ['The website is provided for marketplace shopping and related services.', 'Use of the platform is subject to applicable policies, terms, and operational constraints.']},
        ],
    },
}


def _footer_page_context(request, page_key):
    page = FOOTER_INFO_PAGES[page_key].copy()
    cta = page.get('cta')
    if page_key == 'track-order':
        cta = page.get('auth_cta') if request.user.is_authenticated else page.get('guest_cta')
    context = {
        'content_title': page['title'],
        'content_intro': page.get('intro', ''),
        'content_sections': page.get('sections', []),
        'content_body': page.get('body', ''),
        'content_cta': {'label': cta[0], 'url': reverse(cta[1])} if cta else None,
        'search_text': '',
        'selected_category': '',
        'selected_spice': '',
    }
    return context


def footer_info_page(request, page_key):
    if page_key not in FOOTER_INFO_PAGES:
        raise Http404('Page not found.')
    return render(request, 'website/legal_page.html', _footer_page_context(request, page_key))


def privacy_policy(request):
    content = StaticContent.objects.filter(page=StaticContent.Page.PRIVACY, is_active=True).first()
    if content and content.body:
        return render(request, 'website/legal_page.html', _static_content_context(StaticContent.Page.PRIVACY, content.title, content.body))
    return render(
        request,
        'website/legal_page.html',
        _footer_page_context(request, 'privacy-policy'),
    )


def terms_of_condition(request):
    content = StaticContent.objects.filter(page=StaticContent.Page.TERMS, is_active=True).first()
    if content and content.body:
        return render(request, 'website/legal_page.html', _static_content_context(StaticContent.Page.TERMS, content.title, content.body))
    return render(
        request,
        'website/legal_page.html',
        _footer_page_context(request, 'terms-and-conditions'),
    )


ORDER_STATUS_FLOW = [
    Order.Status.PENDING,
    Order.Status.CONFIRMED,
    Order.Status.PACKED,
    Order.Status.SHIPPED,
    Order.Status.OUT_FOR_DELIVERY,
    Order.Status.DELIVERED,
]


def _order_timeline(order):
    current_index = ORDER_STATUS_FLOW.index(order.status) if order.status in ORDER_STATUS_FLOW else -1
    labels = dict(Order.Status.choices)
    return [
        {
            'status': status,
            'label': labels.get(status, status),
            'active': index <= current_index,
            'current': status == order.status,
        }
        for index, status in enumerate(ORDER_STATUS_FLOW)
    ]


def _product_image_source(product):
    try:
        return product.image_source or ''
    except Exception:
        return ''


def _cart_item_image_source(item):
    try:
        return item.display_image or ''
    except Exception:
        return _product_image_source(item.product)


def _cart_item_payload(item):
    product = item.product
    item_image = _cart_item_image_source(item)
    variant_image = item.selected_variant_image if item.quantity_option_id else ''
    return {
        'id': item.pk,
        'product_id': product.pk,
        'quantity_option_id': item.quantity_option_id,
        'name': product.name,
        'seller': product.owner_label,
        'brand': product.brand_name or 'Lexvers',
        'pack': item.display_pack,
        'image': item_image,
        'product_image': _product_image_source(product),
        'variant_image': variant_image,
        'selectedVariantImage': variant_image,
        'price': float(item.unit_price),
        'quantity': item.quantity,
        'stock': item.stock_available,
        'line_total': float(item.line_total),
    }


def _get_cart(user):
    cart, _ = Cart.objects.get_or_create(user=user)
    return (
        Cart.objects.filter(pk=cart.pk)
        .prefetch_related('items__product__seller', 'items__product__category', 'items__quantity_option')
        .first()
    )


def _cart_totals(cart, coupon_code=''):
    items = list(cart.items.all()) if cart else []
    subtotal = sum(item.line_total for item in items)
    delivery_charge = _delivery_charge_for_subtotal(subtotal)
    coupon, discount, coupon_message = _coupon_discount_for_subtotal(subtotal, coupon_code)
    total = subtotal + delivery_charge - discount
    return {
        'subtotal': subtotal,
        'delivery_charge': delivery_charge,
        'discount': discount,
        'total': total,
        'item_count': sum(item.quantity for item in items),
        'coupon': coupon,
        'coupon_code': coupon.code if coupon and discount else coupon_code,
        'coupon_message': coupon_message,
    }


def _normalize_cart_items(raw_items):
    if isinstance(raw_items, dict):
        raw_items = list(raw_items.values())
    quantities = {}
    for raw_item in raw_items or []:
        try:
            raw_id = str(raw_item.get('id') or '').strip()
            option_id = raw_item.get('quantityOptionId') or raw_item.get('optionId') or raw_item.get('quantity_option_id')
            product_id = raw_item.get('productId') or raw_item.get('product_id')
            if not product_id and ':' in raw_id:
                product_id, parsed_option_id = raw_id.split(':', 1)
                option_id = option_id or parsed_option_id
            if not product_id:
                product_id = raw_id
            product_id = int(product_id)
            option_id = int(option_id) if option_id not in (None, '', 'null') else None
            quantity = int(raw_item.get('qty') or raw_item.get('quantity') or 0)
        except (AttributeError, TypeError, ValueError):
            continue
        if quantity > 0:
            key = (product_id, option_id)
            quantities[key] = quantities.get(key, 0) + quantity
    return quantities


def _sync_cart_from_payload(user, raw_items):
    quantities = _normalize_cart_items(raw_items)
    if not quantities:
        raise ValueError('Cart empty hai. Pehle products add karein.')

    with transaction.atomic():
        cart, _ = Cart.objects.select_for_update().get_or_create(user=user)
        product_ids = {product_id for product_id, _option_id in quantities.keys()}
        option_ids = {option_id for _product_id, option_id in quantities.keys() if option_id}
        products = (
            SpiceItem.objects.filter(
                pk__in=product_ids,
                is_active=True,
                approval_status=SpiceItem.ApprovalStatus.APPROVED,
            )
            .select_related('category', 'seller')
            .prefetch_related('quantity_options')
        )
        product_map = {product.pk: product for product in products}
        if len(product_map) != len(product_ids):
            raise ValueError('Cart mein unavailable product hai. Refresh karke try karein.')

        option_map = {}
        if option_ids:
            options = ProductQuantityOption.objects.filter(
                pk__in=option_ids,
                is_active=True,
                product_id__in=product_ids,
            )
            option_map = {option.pk: option for option in options}

        cart.items.all().delete()
        cart.status = Cart.Status.ACTIVE
        cart.save(update_fields=['status', 'updated_at'])

        for (product_id, option_id), quantity in quantities.items():
            product = product_map[product_id]
            option = option_map.get(option_id) if option_id else None
            if option_id and (not option or option.product_id != product.pk):
                raise ValueError(f'{product.name} ka selected quantity unavailable hai.')
            available_stock = option.stock if option else product.stock
            if available_stock < quantity:
                pack_label = f' ({option.label})' if option else ''
                raise ValueError(f'{product.name}{pack_label} ke liye sirf {available_stock} stock available hai.')
            CartItem.objects.create(
                cart=cart,
                product=product,
                quantity_option=option,
                quantity=quantity,
                unit_price=option.effective_price if option else product.effective_price,
            )
    return _get_cart(user)


def my_cart(request):
    return render(
        request,
        'cart/cart.html',
        {
            'search_text': '',
            'selected_category': '',
            'selected_spice': '',
        },
    )


@login_required
@require_http_methods(['POST'])
def cart_sync(request):
    try:
        payload = json.loads(request.body.decode('utf-8') or '{}')
        cart = _sync_cart_from_payload(request.user, payload.get('items') or [])
    except json.JSONDecodeError:
        return JsonResponse({'ok': False, 'message': 'Invalid cart data.'}, status=400)
    except ValueError as error:
        return JsonResponse({'ok': False, 'message': str(error)}, status=400)

    return JsonResponse(
        {
            'ok': True,
            'checkout_url': reverse('checkout-address'),
            'count': cart.item_count,
        }
    )


@login_required
@require_http_methods(['POST'])
def cart_add(request, product_id):
    product = get_object_or_404(
        SpiceItem.objects.filter(is_active=True, approval_status=SpiceItem.ApprovalStatus.APPROVED),
        pk=product_id,
    )
    option_id = request.POST.get('quantity_option_id') or request.POST.get('option_id')
    option = None
    if option_id:
        option = get_object_or_404(ProductQuantityOption, pk=option_id, product=product, is_active=True)
    try:
        quantity = max(1, int(request.POST.get('quantity', 1)))
    except (TypeError, ValueError):
        quantity = 1
    available_stock = option.stock if option else product.stock
    if quantity > available_stock:
        return JsonResponse({'ok': False, 'message': f'Only {available_stock} units available.'}, status=400)

    cart, _ = Cart.objects.get_or_create(user=request.user)
    item, created = CartItem.objects.get_or_create(
        cart=cart,
        product=product,
        quantity_option=option,
        defaults={'quantity': quantity, 'unit_price': option.effective_price if option else product.effective_price},
    )
    if not created:
        item.quantity = min(item.quantity + quantity, available_stock)
        item.unit_price = option.effective_price if option else product.effective_price
        item.save(update_fields=['quantity', 'unit_price', 'updated_at'])
    cart = _get_cart(request.user)
    return JsonResponse({'ok': True, 'count': cart.item_count, 'item': _cart_item_payload(item)})


@login_required
@require_http_methods(['POST'])
def cart_update(request, item_id):
    item = get_object_or_404(CartItem.objects.select_related('cart', 'product', 'quantity_option'), pk=item_id, cart__user=request.user)
    try:
        quantity = int(request.POST.get('quantity', item.quantity))
    except (TypeError, ValueError):
        return JsonResponse({'ok': False, 'message': 'Invalid quantity.'}, status=400)
    if quantity < 1:
        item.delete()
        cart = _get_cart(request.user)
        return JsonResponse({'ok': True, 'removed': True, 'count': cart.item_count})
    if quantity > item.stock_available:
        return JsonResponse({'ok': False, 'message': f'Only {item.stock_available} units available.'}, status=400)
    item.quantity = quantity
    item.save(update_fields=['quantity', 'updated_at'])
    return JsonResponse({'ok': True, 'item': _cart_item_payload(item), 'count': _get_cart(request.user).item_count})


@login_required
@require_http_methods(['POST'])
def cart_remove(request, item_id):
    item = get_object_or_404(CartItem, pk=item_id, cart__user=request.user)
    item.delete()
    cart = _get_cart(request.user)
    return JsonResponse({'ok': True, 'count': cart.item_count})


def _default_shipping_address(user):
    address = CustomerAddress.objects.filter(user=user).first()
    if not address:
        return ''
    return f'{address.full_name}, {address.phone}, {address.full_address}'


def _address_snapshot(address):
    return {
        'id': address.pk if getattr(address, 'pk', None) else '',
        'address_type': address.address_type,
        'label': address.label,
        'full_name': address.full_name,
        'phone': address.phone,
        'alternate_phone': address.alternate_phone,
        'email': address.email,
        'house': address.house,
        'area': address.area,
        'landmark': address.landmark,
        'city': address.city,
        'district': address.district,
        'state': address.state,
        'pincode': address.pincode,
        'country': address.country or 'India',
        'shipping_address': address.full_address,
        'is_default': address.is_default,
    }


def _address_snapshot_list(addresses):
    return [_address_snapshot(address) for address in addresses]


def _save_customer_address_form(user, address_form, address=None):
    customer_address = address_form.save(commit=False)
    customer_address.user = user
    if address is None and not CustomerAddress.objects.filter(user=user).exists():
        customer_address.is_default = True
    customer_address.save()
    if customer_address.is_default:
        CustomerAddress.objects.filter(user=user).exclude(pk=customer_address.pk).update(is_default=False)
    return customer_address


def _address_snapshot_from_cleaned(cleaned_data):
    parts = [
        cleaned_data.get('house', ''),
        cleaned_data.get('area', ''),
        cleaned_data.get('landmark', ''),
        cleaned_data.get('city', ''),
        cleaned_data.get('district', ''),
        cleaned_data.get('state', ''),
        cleaned_data.get('pincode', ''),
        cleaned_data.get('country', 'India'),
    ]
    return {
        'id': '',
        'address_type': cleaned_data.get('address_type') or CustomerAddress.AddressType.HOME,
        'label': cleaned_data.get('label') or 'Checkout address',
        'full_name': cleaned_data.get('full_name') or '',
        'phone': cleaned_data.get('phone') or '',
        'alternate_phone': cleaned_data.get('alternate_phone') or '',
        'email': cleaned_data.get('email') or '',
        'house': cleaned_data.get('house') or '',
        'area': cleaned_data.get('area') or '',
        'landmark': cleaned_data.get('landmark') or '',
        'city': cleaned_data.get('city') or '',
        'district': cleaned_data.get('district') or '',
        'state': cleaned_data.get('state') or '',
        'pincode': cleaned_data.get('pincode') or '',
        'country': cleaned_data.get('country') or 'India',
        'shipping_address': ', '.join(str(part).strip() for part in parts if str(part or '').strip()),
        'is_default': bool(cleaned_data.get('is_default')),
    }


def _checkout_address_snapshot(request):
    snapshot = request.session.get('checkout_address_snapshot')
    if snapshot:
        return snapshot
    address_id = request.session.get('checkout_address_id')
    if address_id:
        address = CustomerAddress.objects.filter(user=request.user, pk=address_id).first()
        if address:
            return _address_snapshot(address)
    return None


def _get_or_save_checkout_address(user, address_snapshot):
    if not address_snapshot:
        return None

    address_id = address_snapshot.get('id')
    if address_id:
        address = CustomerAddress.objects.filter(user=user, pk=address_id).first()
        if address:
            return address

    existing = CustomerAddress.objects.filter(
        user=user,
        full_name=address_snapshot.get('full_name', ''),
        phone=address_snapshot.get('phone', ''),
        house=address_snapshot.get('house', ''),
        area=address_snapshot.get('area', ''),
        pincode=address_snapshot.get('pincode', ''),
    ).first()
    if existing:
        return existing

    should_default = bool(address_snapshot.get('is_default')) or not CustomerAddress.objects.filter(user=user).exists()
    address = CustomerAddress(
        user=user,
        label=address_snapshot.get('label') or dict(CustomerAddress.AddressType.choices).get(address_snapshot.get('address_type'), 'Home'),
        full_name=address_snapshot.get('full_name', ''),
        phone=address_snapshot.get('phone', ''),
        alternate_phone=address_snapshot.get('alternate_phone', ''),
        email=address_snapshot.get('email', ''),
        house=address_snapshot.get('house', ''),
        area=address_snapshot.get('area', ''),
        landmark=address_snapshot.get('landmark', ''),
        address_line=(address_snapshot.get('area') or address_snapshot.get('shipping_address') or '')[:240],
        city=address_snapshot.get('city', ''),
        district=address_snapshot.get('district', ''),
        state=address_snapshot.get('state', ''),
        pincode=address_snapshot.get('pincode', ''),
        country=address_snapshot.get('country') or 'India',
        address_type=address_snapshot.get('address_type') or CustomerAddress.AddressType.HOME,
        is_default=should_default,
    )
    address.save()
    if address.is_default:
        CustomerAddress.objects.filter(user=user).exclude(pk=address.pk).update(is_default=False)
    return address


def _require_non_empty_cart(request):
    cart = _get_cart(request.user)
    if not cart or not cart.items.exists():
        messages.error(request, 'Cart empty hai. Pehle products add karein.')
        return None
    return cart


@login_required
@require_http_methods(['GET', 'POST'])
def checkout_address(request):
    cart = _require_non_empty_cart(request)
    if not cart:
        return redirect('my-cart')
    addresses = CustomerAddress.objects.filter(user=request.user)
    address_form = CustomerAddressForm()
    editing_address_id = ''

    if request.method == 'POST':
        form_action = request.POST.get('form_action', '')
        selected_address_id = request.POST.get('selected_address', '').strip()
        if selected_address_id and form_action != 'address_form':
            address = get_object_or_404(CustomerAddress, pk=selected_address_id, user=request.user)
            serviceable, service_message = _validate_serviceable_pincode(address.pincode)
            if not serviceable:
                messages.error(request, service_message)
                return redirect('checkout-address')
            request.session['checkout_address_id'] = address.pk
            request.session.pop('checkout_address_snapshot', None)
            return redirect('checkout-payment')

        address_id = request.POST.get('address_id', '').strip()
        address_instance = None
        if address_id:
            address_instance = get_object_or_404(CustomerAddress, pk=address_id, user=request.user)
            editing_address_id = str(address_instance.pk)
        address_form = CustomerAddressForm(request.POST, instance=address_instance)
        if address_form.is_valid():
            address = _save_customer_address_form(request.user, address_form, address_instance)
            request.session['checkout_address_id'] = address.pk
            request.session.pop('checkout_address_snapshot', None)
            messages.success(request, 'Address updated successfully.' if address_instance else 'Address saved successfully.')
            return redirect('checkout-payment')
        messages.error(request, 'Please check the highlighted address fields.')

    return render(
        request,
        'checkout/address.html',
        {
            'checkout_step': 'address',
            'cart': cart,
            'cart_totals': _cart_totals(cart),
            'addresses': addresses,
            'addresses_json': _address_snapshot_list(addresses),
            'address_form': address_form,
            'editing_address_id': editing_address_id,
            'selected_address_id': request.session.get('checkout_address_id'),
            'saved_address_ready': bool(request.session.get('checkout_address_id') or addresses.filter(is_default=True).exists()),
            'search_text': '',
            'selected_category': '',
            'selected_spice': '',
        },
    )


def _payment_method_label(method):
    return {
        Payment.Method.ONLINE: 'Online Payment',
        Payment.Method.COD: 'Cash on Delivery',
        Payment.Method.DEMO: 'Demo Payment',
    }.get(method, 'Cash on Delivery')


def _razorpay_credentials():
    return os.environ.get('RAZORPAY_KEY_ID', '').strip(), os.environ.get('RAZORPAY_KEY_SECRET', '').strip()


def _create_razorpay_order(amount, receipt):
    key_id, key_secret = _razorpay_credentials()
    if not key_id or not key_secret:
        return {}
    payload = json.dumps(
        {
            'amount': int(amount * 100),
            'currency': 'INR',
            'receipt': receipt[:40],
            'payment_capture': 1,
        }
    ).encode('utf-8')
    auth_token = base64.b64encode(f'{key_id}:{key_secret}'.encode('utf-8')).decode('ascii')
    request = Request(
        'https://api.razorpay.com/v1/orders',
        data=payload,
        headers={
            'Authorization': f'Basic {auth_token}',
            'Content-Type': 'application/json',
        },
        method='POST',
    )
    try:
        with urlopen(request, timeout=8) as response:
            return json.loads(response.read().decode('utf-8'))
    except Exception:
        return {}


def _verify_razorpay_signature(razorpay_order_id, razorpay_payment_id, razorpay_signature):
    _key_id, key_secret = _razorpay_credentials()
    if not key_secret or not razorpay_order_id or not razorpay_payment_id or not razorpay_signature:
        return False
    payload = f'{razorpay_order_id}|{razorpay_payment_id}'.encode('utf-8')
    digest = hmac.new(key_secret.encode('utf-8'), payload, 'sha256').hexdigest()
    return hmac.compare_digest(digest, razorpay_signature)


@login_required
def checkout_payment(request):
    cart = _require_non_empty_cart(request)
    if not cart:
        return redirect('my-cart')
    address_snapshot = _checkout_address_snapshot(request)
    if not address_snapshot:
        messages.error(request, 'Checkout ke liye delivery address select karein.')
        return redirect('checkout-address')
    serviceable, service_message = _validate_serviceable_pincode(address_snapshot.get('pincode'))
    if not serviceable:
        messages.error(request, service_message)
        return redirect('checkout-address')

    if request.method == 'POST':
        coupon_action = request.POST.get('coupon_action', '')
        if coupon_action == 'apply':
            coupon_code = request.POST.get('coupon_code', '')
            totals = _cart_totals(cart, coupon_code)
            if totals.get('coupon') and totals.get('discount'):
                _set_cart_coupon(request, totals['coupon'].code)
                messages.success(request, f'Coupon {totals["coupon"].code} applied.')
            else:
                _set_cart_coupon(request, '')
                messages.error(request, totals.get('coupon_message') or 'Coupon could not be applied.')
            return redirect('checkout-payment')
        if coupon_action == 'remove':
            _set_cart_coupon(request, '')
            messages.success(request, 'Coupon removed.')
            return redirect('checkout-payment')

    razorpay_key_id, razorpay_key_secret = _razorpay_credentials()
    cart_totals = _cart_totals(cart, _cart_coupon_code(request))
    if cart_totals.get('coupon_message') and cart_totals.get('coupon_code'):
        _set_cart_coupon(request, '')
        messages.error(request, cart_totals['coupon_message'])
        return redirect('checkout-payment')
    razorpay_order = _create_razorpay_order(cart_totals['total'], f'checkout-{request.user.pk}-{int(timezone.now().timestamp())}') if razorpay_key_id and razorpay_key_secret else {}
    return render(
        request,
        'checkout/payment.html',
        {
            'checkout_step': 'payment',
            'cart': cart,
            'cart_totals': cart_totals,
            'address': address_snapshot,
            'razorpay_key_id': razorpay_key_id,
            'razorpay_ready': bool(razorpay_key_id and razorpay_key_secret),
            'razorpay_order': razorpay_order,
            'search_text': '',
            'selected_category': '',
            'selected_spice': '',
        },
    )


def _create_order_notifications(order, order_items):
    OrderNotification.objects.create(
        audience=OrderNotification.Audience.ADMIN,
        notification_type=OrderNotification.Type.NEW_ORDER,
        order=order,
        title=f'New order {order.order_number}',
        message=f'{order.customer_name} placed an order of {_format_currency(order.total_amount)}.',
    )
    OrderNotification.objects.create(
        audience=OrderNotification.Audience.CUSTOMER,
        notification_type=OrderNotification.Type.NEW_ORDER,
        user=order.customer,
        order=order,
        title=f'Order placed {order.order_number}',
        message='Your order has been placed successfully.',
    )
    seen_sellers = set()
    for item in order_items:
        if not item.seller_id or item.seller_id in seen_sellers:
            continue
        seen_sellers.add(item.seller_id)
        OrderNotification.objects.create(
            audience=OrderNotification.Audience.SELLER,
            notification_type=OrderNotification.Type.NEW_ORDER,
            seller=item.seller,
            order=order,
            order_item=item,
            title=f'New order item {order.order_number}',
            message=f'{item.product_name} x {item.quantity} needs fulfillment.',
        )


def _restore_stock_for_items(order_items):
    touched_products = set()
    for item in order_items:
        if item.quantity_option_id:
            option = ProductQuantityOption.objects.select_for_update().filter(pk=item.quantity_option_id).first()
            if option:
                option.stock += item.quantity
                option.save(update_fields=['stock', 'updated_at'])
                touched_products.add(option.product_id)
        elif item.product_id:
            product = SpiceItem.objects.select_for_update().filter(pk=item.product_id).first()
            if product:
                product.stock += item.quantity
                product.save(update_fields=['stock', 'updated_at'])
    for product_id in touched_products:
        product = SpiceItem.objects.select_for_update().filter(pk=product_id).first()
        if product:
            product.stock = sum(option.stock for option in product.quantity_options.filter(is_active=True))
            product.save(update_fields=['stock', 'updated_at'])


def _record_order_status(order, status, user=None, note='', order_item=None):
    OrderStatusHistory.objects.create(order=order, order_item=order_item, changed_by=user, status=status, note=note[:240])
    OrderNotification.objects.create(
        audience=OrderNotification.Audience.CUSTOMER,
        notification_type=OrderNotification.Type.STATUS_UPDATED,
        user=order.customer,
        order=order,
        order_item=order_item,
        title=f'Order status updated',
        message=f'{order.order_number} is now {dict(Order.Status.choices).get(status, status)}.',
    )


def _set_order_status(order, status, user=None, note=''):
    old_status = order.status
    with transaction.atomic():
        locked_order = Order.objects.select_for_update().prefetch_related('items').get(pk=order.pk)
        old_status = locked_order.status
        if status == Order.Status.CANCELLED and old_status not in {Order.Status.CANCELLED, Order.Status.RETURNED, Order.Status.SHIPPED, Order.Status.OUT_FOR_DELIVERY, Order.Status.DELIVERED}:
            _restore_stock_for_items(list(locked_order.items.select_related('product', 'quantity_option')))
        locked_order.status = status
        locked_order.items.update(item_status=status)
        locked_order.save(update_fields=['status', 'updated_at'])
        _record_order_status(locked_order, status, user, note)
    return old_status


def _order_lookup_filter(order_id):
    return Q(order_number=order_id) | Q(order_id=order_id)


def _filtered_admin_orders(request):
    orders = Order.objects.select_related('customer').prefetch_related('items__seller', 'items__product', 'items__quantity_option').order_by('-created_at')
    query = request.GET.get('q', '').strip()
    status = request.GET.get('status', '').strip()
    payment_status = request.GET.get('payment_status', '').strip()
    seller_id = request.GET.get('seller', '').strip()
    date_from = parse_date(request.GET.get('date_from', '').strip())
    date_to = parse_date(request.GET.get('date_to', '').strip())

    if query:
        orders = orders.filter(
            Q(order_number__icontains=query)
            | Q(order_id__icontains=query)
            | Q(customer_name__icontains=query)
            | Q(customer_phone__icontains=query)
            | Q(items__product_name__icontains=query)
            | Q(items__seller_name__icontains=query)
        )
    if status:
        orders = orders.filter(status=status)
    if payment_status:
        orders = orders.filter(payment_status=payment_status)
    if seller_id:
        orders = orders.filter(items__seller_id=seller_id)
    if date_from:
        orders = orders.filter(created_at__date__gte=date_from)
    if date_to:
        orders = orders.filter(created_at__date__lte=date_to)
    return orders.distinct()


def _order_summary_counts(orders=None):
    source = orders if orders is not None else Order.objects.all()
    today = timezone.localdate()
    return {
        'new': source.filter(status=Order.Status.PENDING).count(),
        'pending': source.filter(status=Order.Status.PENDING).count(),
        'packed': source.filter(status=Order.Status.PACKED).count(),
        'shipped': source.filter(status__in=[Order.Status.SHIPPED, Order.Status.OUT_FOR_DELIVERY]).count(),
        'delivered': source.filter(status=Order.Status.DELIVERED).count(),
        'cancelled': source.filter(status=Order.Status.CANCELLED).count(),
        'today': source.filter(created_at__date=today).count(),
        'unseen': source.filter(is_seen_by_admin=False).count() if hasattr(source, 'filter') else 0,
        'revenue': source.filter(status=Order.Status.DELIVERED).aggregate(total=Sum('total_amount')).get('total') or Decimal('0'),
    }


def _seller_order_items_for_user(user):
    seller_profile = _get_seller_profile(user)
    items = OrderItem.objects.select_related('order', 'order__customer', 'seller', 'product', 'quantity_option').order_by('-order__created_at')
    if user.is_staff:
        return items, seller_profile
    if seller_profile:
        return items.filter(seller=seller_profile), seller_profile
    return items.none(), None


@login_required
@require_http_methods(['POST'])
def place_order_checkout(request):
    cart = _require_non_empty_cart(request)
    if not cart:
        return redirect('my-cart')
    address_snapshot = _checkout_address_snapshot(request)
    if not address_snapshot:
        messages.error(request, 'Checkout ke liye delivery address select karein.')
        return redirect('checkout-address')

    payment_method = request.POST.get('payment_method') or Payment.Method.COD
    if payment_method not in {Payment.Method.ONLINE, Payment.Method.COD, Payment.Method.DEMO}:
        payment_method = Payment.Method.COD

    razorpay_key_id, razorpay_key_secret = _razorpay_credentials()
    razorpay_ready = bool(razorpay_key_id and razorpay_key_secret)
    is_demo_payment = payment_method == Payment.Method.DEMO or (payment_method == Payment.Method.ONLINE and not razorpay_ready)
    razorpay_payment_id = request.POST.get('razorpay_payment_id', '').strip()
    razorpay_order_id = request.POST.get('razorpay_order_id', '').strip()
    razorpay_signature = request.POST.get('razorpay_signature', '').strip()
    if payment_method == Payment.Method.ONLINE and razorpay_ready:
        if not _verify_razorpay_signature(razorpay_order_id, razorpay_payment_id, razorpay_signature):
            messages.error(request, 'Online payment verification failed. Please try again or choose COD.')
            return redirect('checkout-payment')
    payment_paid = payment_method in {Payment.Method.ONLINE, Payment.Method.DEMO} and (is_demo_payment or bool(razorpay_payment_id))

    try:
        with transaction.atomic():
            cart = Cart.objects.select_for_update().get(user=request.user)
            cart_items = list(
                CartItem.objects.filter(cart=cart)
                .select_related('product', 'product__category', 'product__seller', 'quantity_option')
                .order_by('pk')
            )
            if not cart_items:
                messages.error(request, 'Cart empty hai. Pehle products add karein.')
                return redirect('my-cart')

            product_ids = {item.product_id for item in cart_items}
            option_ids = {item.quantity_option_id for item in cart_items if item.quantity_option_id}
            product_map = {
                product.pk: product
                for product in SpiceItem.objects.select_for_update().filter(pk__in=product_ids).select_related('category', 'seller').prefetch_related('quantity_options')
            }
            option_map = {
                option.pk: option
                for option in ProductQuantityOption.objects.select_for_update().filter(pk__in=option_ids)
            }

            for item in cart_items:
                product = product_map.get(item.product_id)
                option = option_map.get(item.quantity_option_id) if item.quantity_option_id else None
                if not product or not product.is_active or product.approval_status != SpiceItem.ApprovalStatus.APPROVED:
                    raise ValueError(f'{item.product.name} unavailable hai.')
                available_stock = option.stock if option else product.stock
                if available_stock < item.quantity:
                    raise ValueError(f'{product.name} ke liye sirf {available_stock} stock available hai.')

            totals = _cart_totals(_get_cart(request.user), _cart_coupon_code(request))
            if _cart_coupon_code(request) and totals.get('coupon_message'):
                raise ValueError(totals['coupon_message'])
            selected_address = _get_or_save_checkout_address(request.user, address_snapshot)
            if selected_address:
                address_snapshot = _address_snapshot(selected_address)
            serviceable, service_message = _validate_serviceable_pincode(address_snapshot.get('pincode'))
            if not serviceable:
                raise ValueError(service_message)
            order = Order.objects.create(
                customer=request.user,
                address=selected_address,
                customer_name=address_snapshot['full_name'],
                customer_email=address_snapshot.get('email') or request.user.email,
                customer_phone=address_snapshot['phone'],
                alternate_phone=address_snapshot.get('alternate_phone', ''),
                shipping_address=address_snapshot['shipping_address'],
                address_type=address_snapshot.get('address_type') or CustomerAddress.AddressType.HOME,
                house=address_snapshot.get('house', ''),
                area=address_snapshot.get('area', ''),
                landmark=address_snapshot.get('landmark', ''),
                city=address_snapshot.get('city', ''),
                district=address_snapshot.get('district', ''),
                state=address_snapshot.get('state', ''),
                pincode=address_snapshot.get('pincode', ''),
                country=address_snapshot.get('country', 'India'),
                subtotal=totals['subtotal'],
                shipping_fee=totals['delivery_charge'],
                discount_amount=totals['discount'],
                coupon_code=totals.get('coupon_code') if totals.get('discount') else '',
                total_amount=totals['total'],
                payment_method=_payment_method_label(payment_method),
                payment_status=Order.PaymentStatus.PAID if payment_paid else Order.PaymentStatus.PENDING,
                status=Order.Status.PENDING,
            )
            payment = Payment.objects.create(
                order=order,
                customer=request.user,
                amount=order.total_amount,
                method=payment_method,
                status=Payment.Status.PAID if payment_paid else Payment.Status.PENDING,
                razorpay_payment_id=razorpay_payment_id,
                razorpay_order_id=razorpay_order_id,
                razorpay_signature=razorpay_signature,
                is_demo=is_demo_payment,
            )
            PaymentTransaction.objects.create(
                order=order,
                customer=request.user,
                amount=order.total_amount,
                method=order.payment_method,
                status=PaymentTransaction.Status.SUCCESS if payment.status == Payment.Status.PAID else PaymentTransaction.Status.PENDING,
                gateway_reference=payment.razorpay_payment_id or payment.payment_id,
            )

            order_items = []
            touched_variant_products = set()
            for item in cart_items:
                product = product_map[item.product_id]
                option = option_map.get(item.quantity_option_id) if item.quantity_option_id else None
                order_item = OrderItem.objects.create(
                    order=order,
                    product=product,
                    quantity_option=option,
                    seller=product.seller if product.owner_type == SpiceItem.OwnerType.SELLER else None,
                    product_name=product.name,
                    product_image=(option.variant_image_source if option else '') or _product_image_source(product),
                    category_name=product.category.name if product.category else 'General',
                    brand_name=product.brand_name,
                    pack_size=option.label if option else product.pack_display,
                    seller_name=product.owner_label,
                    unit_price=option.effective_price if option else product.effective_price,
                    quantity=item.quantity,
                    item_status=Order.Status.PENDING,
                )
                order_items.append(order_item)
                if option:
                    option.stock -= item.quantity
                    option.save(update_fields=['stock', 'updated_at'])
                    touched_variant_products.add(product.pk)
                else:
                    product.stock -= item.quantity
                    product.save(update_fields=['stock', 'updated_at'])

            for product_id in touched_variant_products:
                product = product_map[product_id]
                product.stock = sum(option.stock for option in product.quantity_options.filter(is_active=True))
                product.save(update_fields=['stock', 'updated_at'])

            OrderStatusHistory.objects.create(order=order, changed_by=request.user, status=Order.Status.PENDING, note='Order placed')
            if totals.get('coupon') and totals.get('discount'):
                CouponRedemption.objects.create(
                    coupon=totals['coupon'],
                    user=request.user,
                    order=order,
                    discount_amount=totals['discount'],
                )
                Coupon.objects.filter(pk=totals['coupon'].pk).update(used_count=F('used_count') + 1)
            _create_order_notifications(order, order_items)
            cart.items.all().delete()
            cart.status = Cart.Status.ACTIVE
            cart.save(update_fields=['status', 'updated_at'])
    except ValueError as error:
        messages.error(request, str(error))
        return redirect('checkout-payment')

    request.session.pop('checkout_address_id', None)
    request.session.pop('checkout_address_snapshot', None)
    request.session.pop('checkout_coupon_code', None)
    return redirect('order-success', order_id=order.order_number)


@require_http_methods(['POST'])
def place_order(request):
    if not request.user.is_authenticated:
        return JsonResponse({'ok': False, 'login_url': reverse('login')}, status=401)
    try:
        payload = json.loads(request.body.decode('utf-8') or '{}')
        cart = _sync_cart_from_payload(request.user, payload.get('items') or [])
    except json.JSONDecodeError:
        return JsonResponse({'ok': False, 'message': 'Invalid cart data.'}, status=400)
    except ValueError as error:
        return JsonResponse({'ok': False, 'message': str(error)}, status=400)
    return JsonResponse({'ok': True, 'message': 'Cart ready for checkout.', 'checkout_url': reverse('checkout-address'), 'count': cart.item_count})


@login_required
def order_success(request, order_id):
    order = get_object_or_404(
        Order.objects.filter(customer=request.user).prefetch_related('items__product', 'items__quantity_option', 'payment', 'status_history'),
        Q(order_number=order_id) | Q(order_id=order_id),
    )
    return render(
        request,
        'orders/success.html',
        {
            'checkout_step': 'success',
            'order': order,
            'order_items': order.items.all(),
            'timeline_steps': _order_timeline(order),
            'search_text': '',
            'selected_category': '',
            'selected_spice': '',
        },
    )


@login_required
def my_orders(request):
    orders = (
        Order.objects.filter(customer=request.user)
        .prefetch_related('items__product', 'items__quantity_option')
        .order_by('-created_at')
    )
    return render(
        request,
        'customer_panel/orders/my_orders.html',
        {
            'orders': orders,
            'search_text': '',
            'selected_category': '',
            'selected_spice': '',
        },
    )


@login_required
def my_order_detail(request, order_id):
    order = get_object_or_404(
        Order.objects.filter(customer=request.user).prefetch_related('items__product', 'items__quantity_option', 'items__seller', 'status_history', 'payment', 'shipments__courier', 'return_requests'),
        Q(order_number=order_id) | Q(order_id=order_id),
    )
    if request.method == 'POST' and request.POST.get('form_action') == 'return_request':
        if order.status != Order.Status.DELIVERED:
            messages.error(request, 'Return request can be raised only after delivery.')
            return redirect('my-order-detail', order_id=order.order_number)
        if order.return_requests.filter(status=ReturnRequest.Status.PENDING).exists():
            messages.error(request, 'A return request is already pending for this order.')
            return redirect('my-order-detail', order_id=order.order_number)
        reason = request.POST.get('reason', '').strip()
        details = request.POST.get('details', '').strip()
        if not reason:
            messages.error(request, 'Please add a return reason.')
            return redirect('my-order-detail', order_id=order.order_number)
        ReturnRequest.objects.create(
            order=order,
            customer=request.user,
            reason=reason[:240],
            details=details,
            proof_file=request.FILES.get('proof_file'),
            refund_amount=order.total_amount,
            status=ReturnRequest.Status.PENDING,
            refund_status=ReturnRequest.RefundStatus.REQUESTED,
        )
        messages.success(request, 'Return request submitted for admin review.')
        return redirect('my-order-detail', order_id=order.order_number)

    return render(
        request,
        'customer_panel/orders/order_detail.html',
        {
            'order': order,
            'order_items': order.items.all(),
            'shipments': order.shipments.all(),
            'return_requests': order.return_requests.all(),
            'timeline_steps': _order_timeline(order),
            'search_text': '',
            'selected_category': '',
            'selected_spice': '',
        },
    )


@login_required
def customer_order_notifications(request):
    notifications = OrderNotification.objects.filter(audience=OrderNotification.Audience.CUSTOMER, user=request.user)
    return JsonResponse(
        {
            'unread_count': notifications.filter(is_read=False).count(),
            'notifications': [
                _order_notification_payload(notification, OrderNotification.Audience.CUSTOMER)
                for notification in notifications.select_related('order')[:10]
            ],
        }
    )


def welcome(request):
    return render(request, 'admin_panel/welcome.html')


def product_detail(request, slug):
    product = get_object_or_404(
        SpiceItem.objects.filter(
            is_active=True,
            approval_status=SpiceItem.ApprovalStatus.APPROVED,
        ).select_related('category', 'seller').prefetch_related('gallery_images', 'quantity_options'),
        slug=slug,
    )
    if request.method == 'POST':
        customer_name = request.POST.get('customer_name', '').strip()
        comment = request.POST.get('comment', '').strip()
        try:
            rating = int(request.POST.get('rating', '5'))
        except ValueError:
            rating = 5
        rating = min(max(rating, 1), 5)

        if comment:
            ProductReview.objects.create(
                product=product,
                customer=request.user if request.user.is_authenticated else None,
                customer_name=customer_name[:120],
                rating=rating,
                comment=comment,
                status=ProductReview.Status.PENDING,
            )
            messages.success(request, 'Review submitted. It will appear after admin approval.')
        else:
            messages.error(request, 'Please write a review before submitting.')
        return redirect('product-detail', slug=product.slug)

    related_products = SpiceItem.objects.filter(
        is_active=True,
        approval_status=SpiceItem.ApprovalStatus.APPROVED,
        category=product.category,
    ).exclude(pk=product.pk).select_related('category', 'seller').prefetch_related('gallery_images', 'quantity_options').order_by(
        '-is_featured',
        'display_order',
        'name',
    )[:4]

    fallback_image = 'https://images.unsplash.com/photo-1599909538557-c3f9de9b756d?auto=format&fit=crop&w=900&q=80'
    base_gallery_images = []
    primary_product_image = product.image_file.url if product.image_file else product.image_url
    if primary_product_image:
        base_gallery_images.append({'src': primary_product_image, 'alt': product.name, 'image_key': f'product-{product.pk}-{int(product.updated_at.timestamp())}'})

    for photo in product.gallery_images.all():
        if photo.is_active and photo.image_source:
            base_gallery_images.append({'src': photo.image_source, 'alt': photo.alt_text or product.name, 'image_key': f'gallery-{photo.pk}-{int(photo.updated_at.timestamp())}'})

    if not base_gallery_images:
        base_gallery_images.append({'src': fallback_image, 'alt': product.name, 'image_key': ''})

    product_fallback_image = base_gallery_images[0]['src']
    quantity_options = []
    quantity_gallery_images = {'default': base_gallery_images}
    for option in product.quantity_options.all():
        if not option.is_active:
            continue
        variant_image = option.variant_image_source
        option_image_key = f'{option.pk}-{int(option.updated_at.timestamp())}'
        option_gallery = (
            [
                {
                    'src': variant_image,
                    'alt': f'{product.name} {option.label}',
                    'image_key': option_image_key,
                }
            ]
            if variant_image
            else base_gallery_images
        )
        quantity_gallery_images[str(option.pk)] = option_gallery
        quantity_options.append(
            {
                'id': option.pk,
                'label': option.label,
                'price': str(option.effective_price),
                'original_price': str(option.effective_original_price) if option.effective_original_price else '',
                'stock': option.stock,
                'sku': option.sku_code,
                'image': variant_image or product_fallback_image,
                'variant_image': variant_image,
                'image_key': option_image_key,
                'discount_percent': option.effective_discount_percent,
            }
        )
    selected_quantity_option = quantity_options[0] if quantity_options else None
    gallery_images = quantity_gallery_images.get(str(selected_quantity_option['id']), base_gallery_images) if selected_quantity_option else base_gallery_images

    approved_reviews = product.reviews.filter(status=ProductReview.Status.APPROVED).select_related('customer')
    review_stats = approved_reviews.aggregate(avg=Avg('rating'), total=Count('id'))

    return render(
        request,
        'products/product_detail.html',
        {
            'product': product,
            'related_products': related_products,
            'gallery_images': gallery_images,
            'primary_image': gallery_images[0]['src'],
            'quantity_options': quantity_options,
            'quantity_gallery_images': quantity_gallery_images,
            'selected_quantity_option': selected_quantity_option,
            'approved_reviews': approved_reviews,
            'review_average': review_stats['avg'] or 0,
            'review_count': review_stats['total'] or 0,
            'saved_product_ids': _saved_product_ids(request.user),
            'search_text': '',
            'selected_category': product.category.slug if product.category else '',
            'selected_spice': '',
        },
    )


def live_store_data(request):
    search_text = request.GET.get('q', '').strip()
    selected_category = request.GET.get('category', '').strip()
    selected_spice = request.GET.get('spice', '').strip()
    known_signature = request.GET.get('signature', '').strip()
    known_view_key = request.GET.get('view_key', '').strip()

    if not selected_category:
        selected_spice = ''

    fresh_signature = _build_signature()
    fresh_view_key = f'{search_text}|{selected_category}|{selected_spice}'

    if known_signature and known_signature == fresh_signature and known_view_key == fresh_view_key:
        return JsonResponse({'changed': False, 'signature': fresh_signature, 'view_key': fresh_view_key})

    context = _build_store_context(search_text, selected_category, selected_spice)
    context['saved_product_ids'] = _saved_product_ids(request.user)
    context['recent_search_section'] = _recent_search_section(request)

    payload = {
        'changed': True,
        'signature': fresh_signature,
        'view_key': fresh_view_key,
        'categories_html': render_to_string(
            'website/partials/category_strip.html',
            {
                'category_tabs': context['category_tabs'],
                'search_text': search_text,
                'selected_category': context['selected_category'],
                'selected_spice': context['selected_spice'],
            },
            request=request,
        ),
        'spice_filters_html': render_to_string(
            'website/partials/spice_icons_strip.html',
            {
                'spice_filters': context['spice_filters'],
                'show_spice_filters': context['show_spice_filters'],
                'selected_category': context['selected_category'],
                'current_category_label': context['current_category_label'],
                'search_text': search_text,
                'selected_spice': context['selected_spice'],
            },
            request=request,
        ),
        'banners_html': render_to_string(
            'website/partials/banner_grid.html',
            {
                'banners': context['banners'],
                'homepage_settings': context['homepage_settings'],
            },
            request=request,
        ),
        'compact_banners_html': render_to_string(
            'website/partials/compact_banner_strip.html',
            {
                'compact_banners': context['compact_banners'],
                'homepage_settings': context['homepage_settings'],
            },
            request=request,
        ),
        'store_content_html': render_to_string(
            'website/partials/store_content.html',
            context,
            request=request,
        ),
        'product_count': context['products'].count(),
    }
    return JsonResponse(payload)


def sub_category_options(request):
    category_id = request.GET.get('category_id', '').strip()
    category_slug = request.GET.get('category_slug', '').strip()
    sub_categories = SubCategory.objects.filter(is_active=True).select_related('category')
    if category_id:
        sub_categories = sub_categories.filter(category_id=category_id)
    elif category_slug:
        sub_categories = sub_categories.filter(category__slug=category_slug)
    else:
        sub_categories = sub_categories.none()

    return JsonResponse(
        {
            'options': [
                {
                    'id': sub_category.pk,
                    'name': sub_category.name,
                    'category_id': sub_category.category_id,
                    'category_slug': sub_category.category.slug,
                }
                for sub_category in sub_categories.order_by('display_order', 'name')
            ]
        }
    )


@user_passes_test(_staff_required, login_url='login')
def admin_live_signature(request):
    return JsonResponse({'signature': _build_signature()})


def _seller_lookup_values(user):
    values = []
    if getattr(user, 'email', ''):
        values.append(user.email.strip().lower())
    if getattr(user, 'username', ''):
        values.append(user.username.strip().lower())
    return [value for value in dict.fromkeys(values) if value]


def _get_seller_profile(user):
    if not user.is_authenticated:
        return None

    lookup_values = _seller_lookup_values(user)
    if not lookup_values:
        return None

    return SellerApplication.objects.filter(
        email__in=lookup_values,
        status=SellerApplication.Status.APPROVED,
    ).first()


def _get_seller_application_for_user(user):
    if not user.is_authenticated:
        return None
    lookup_values = _seller_lookup_values(user)
    if not lookup_values:
        return None
    return SellerApplication.objects.filter(email__in=lookup_values).order_by('-created_at').first()


def _seller_settings_forms(seller_profile):
    return {
        'seller_store_form': SellerStoreProfileForm(instance=seller_profile),
        'seller_bank_form': SellerBankDetailsForm(instance=seller_profile),
        'seller_documents_form': SellerDocumentsForm(instance=seller_profile),
    }


def _get_existing_customer_profile(user):
    if not user.is_authenticated:
        return None
    try:
        return user.customer_profile
    except CustomerProfile.DoesNotExist:
        return None


def _seller_avatar_context(user, seller_profile=None):
    customer_profile = _get_existing_customer_profile(user)
    display_name = ''
    store_label = ''
    avatar_url = ''
    if seller_profile:
        display_name = seller_profile.name
        store_label = seller_profile.store_name
        avatar_url = _seller_photo_url(seller_profile)
    elif user.is_authenticated:
        display_name = user.get_full_name() or user.first_name or user.username
        store_label = 'Admin seller view' if user.is_staff else 'Seller workspace'

    display_name = display_name or 'Seller'
    avatar_initial = (display_name[:1] or 'S').upper()
    if not avatar_url and customer_profile:
        avatar_url = customer_profile.photo_source
    return {
        'seller_display_name': display_name,
        'seller_store_label': store_label or 'Lexvers seller',
        'seller_avatar_initial': avatar_initial,
        'seller_avatar_url': avatar_url,
    }


def _seller_order_notification_queryset(user):
    seller_profile = _get_seller_profile(user)
    notifications = OrderNotification.objects.filter(audience=OrderNotification.Audience.SELLER).select_related('order', 'order_item')
    if user.is_staff:
        return notifications
    if seller_profile:
        return notifications.filter(seller=seller_profile)
    return notifications.none()


def _order_notification_url(notification, audience):
    if audience == OrderNotification.Audience.ADMIN:
        return reverse('admin-order-detail', kwargs={'pk': notification.order.pk})
    if audience == OrderNotification.Audience.SELLER:
        return reverse('seller-order-detail', kwargs={'order_id': notification.order.order_number})
    return reverse('my-order-detail', kwargs={'order_id': notification.order.order_number})


def _order_notification_payload(notification, audience):
    return {
        'id': notification.pk,
        'title': notification.title,
        'message': notification.message,
        'created_at': notification.created_at.strftime('%d %b, %I:%M %p'),
        'order_id': notification.order.order_number,
        'section': 'orders',
        'url': _order_notification_url(notification, audience),
    }


def _seller_header_notifications(user):
    notifications = _seller_order_notification_queryset(user)
    return {
        'seller_header_notifications': list(notifications.filter(is_read=False)[:5]),
        'seller_unread_notifications_count': notifications.filter(is_read=False).count(),
    }


def _seller_layout_context(user, page_title='Dashboard', active_section='dashboard', live_enabled=False):
    seller_profile = _get_seller_profile(user)
    return {
        'seller_nav': SELLER_NAV,
        'seller_profile': seller_profile,
        'seller_page_title': page_title,
        'seller_active_section': active_section,
        'seller_live_enabled': live_enabled,
        **_seller_avatar_context(user, seller_profile),
        **_seller_header_notifications(user),
    }


def _validate_seller_profile_photo(uploaded_file):
    extension = uploaded_file.name.rsplit('.', 1)[-1].lower() if '.' in uploaded_file.name else ''
    content_type = getattr(uploaded_file, 'content_type', '')
    if extension not in SELLER_PROFILE_PHOTO_ALLOWED_EXTENSIONS or content_type not in SELLER_PROFILE_PHOTO_ALLOWED_TYPES:
        return 'Only jpg, jpeg, png, or webp profile photos are allowed.'
    if uploaded_file.size > SELLER_PROFILE_PHOTO_MAX_BYTES:
        return 'Profile photo maximum size 2 MB hai.'
    return ''


def _is_seller_user(user):
    if not user.is_authenticated:
        return False
    if user.is_staff:
        return True
    lookup_values = _seller_lookup_values(user)
    return SELLER_DEMO_EMAIL in lookup_values or _get_seller_profile(user) is not None


def _seller_product_queryset(seller_profile=None, include_all_for_admin=False):
    products = SpiceItem.objects.select_related('category', 'seller').prefetch_related('gallery_images', 'quantity_options')
    if include_all_for_admin:
        return products.order_by('-updated_at', 'name')
    if seller_profile:
        return products.filter(owner_type=SpiceItem.OwnerType.SELLER, seller=seller_profile).order_by('-updated_at', 'name')
    return products.none()


def _seller_order_items_queryset(seller_profile=None, include_all_for_admin=False):
    order_items = OrderItem.objects.select_related('order', 'order__customer', 'seller', 'product', 'quantity_option').order_by('-order__created_at')
    if include_all_for_admin:
        return order_items
    if seller_profile:
        return order_items.filter(seller=seller_profile)
    return order_items.none()


def _seller_order_rows(order_items):
    return [
        {
            'pk': order_item.order.pk,
            'id': order_item.order.order_number,
            'customer': order_item.order.customer_name,
            'product': order_item.product_name,
            'quantity': order_item.quantity,
            'price': _format_currency(order_item.line_total),
            'payment_status': order_item.order.get_payment_status_display(),
            'payment_tone': order_item.order.payment_tone,
            'status': order_item.get_item_status_display(),
            'status_value': order_item.item_status,
            'status_tone': order_item.status_tone,
            'address': order_item.order.shipping_address or 'Address not added',
            'date': order_item.order.created_at.strftime('%d %b %Y'),
        }
        for order_item in order_items
    ]


def _seller_accessible_order_queryset(user):
    orders = Order.objects.select_related('customer').prefetch_related('items', 'items__seller', 'items__product')
    if user.is_staff:
        return orders.order_by('-updated_at')

    seller_profile = _get_seller_profile(user)
    if seller_profile:
        return orders.filter(items__seller=seller_profile).distinct().order_by('-updated_at')
    return orders.none()


def _seller_cell(value, tone=''):
    return {'value': value, 'tone': tone}


def _seller_row(cells, actions=None):
    return {'cells': cells, 'actions': actions or []}


def _seller_action(label, href='', style='view', method='get', **extra):
    action = {'label': label, 'href': href, 'style': style, 'method': method}
    action.update(extra)
    return action


def _seller_table(title, headers, rows, empty, badge='', subtitle=''):
    has_actions = any(row.get('actions') for row in rows)
    return {
        'title': title,
        'subtitle': subtitle,
        'badge': badge,
        'headers': headers,
        'rows': rows,
        'empty': empty,
        'has_actions': has_actions,
        'colspan': len(headers) + (1 if has_actions else 0),
    }


def _seller_discount_label(coupon):
    if coupon.discount_type == Coupon.DiscountType.PERCENT:
        return f'{coupon.discount_value}%'
    return _format_currency(coupon.discount_value)


def _seller_ticket_user_label(ticket):
    if ticket.seller:
        return ticket.seller.store_name
    if ticket.customer:
        return ticket.customer.first_name or ticket.customer.username
    return 'Guest'


def _shift_month_start(value, offset):
    month_index = value.month - 1 + offset
    year = value.year + month_index // 12
    month = month_index % 12 + 1
    return value.replace(year=year, month=month, day=1, hour=0, minute=0, second=0, microsecond=0)


def _percent(value, total):
    if not total:
        return 0
    return int(round((value / total) * 100))


def _product_sold_units(product):
    return max((product.initial_stock or 0) - (product.stock or 0), 0)


def _product_stock_value(product):
    return Decimal(product.stock or 0) * (product.price or Decimal('0'))


def _product_sold_value(product):
    return Decimal(_product_sold_units(product)) * (product.price or Decimal('0'))


def _line_chart_paths(points):
    values = [float(point['raw_value']) for point in points]
    max_value = max(values) if values else 0
    if max_value <= 0:
        max_value = 1

    x_step = 720 / max(len(values) - 1, 1)
    coords = []
    for index, value in enumerate(values):
        x = round(index * x_step, 2)
        y = round(220 - ((value / max_value) * 172), 2)
        y = max(46, min(220, y))
        coords.append((x, y))

    if not coords:
        coords = [(0, 220), (720, 220)]

    line_path = 'M ' + ' L '.join(f'{x} {y}' for x, y in coords)
    area_path = f'{line_path} L 720 260 L 0 260 Z'
    focus_index = max(range(len(values)), key=lambda item: values[item]) if values else len(coords) - 1
    if all(value == 0 for value in values):
        focus_index = len(coords) - 1

    return {
        'line_path': line_path,
        'area_path': area_path,
        'focus_x': coords[focus_index][0],
        'focus_y': coords[focus_index][1],
        'focus_label': points[focus_index]['label'] if points else 'Now',
        'focus_value': points[focus_index]['value'] if points else _format_currency(0),
    }


def _build_seller_dashboard_data(user):
    seller_profile = _get_seller_profile(user)
    products = _seller_product_queryset(seller_profile, include_all_for_admin=user.is_staff)
    product_items = list(products)
    seller_order_items_qs = _seller_order_items_queryset(seller_profile, include_all_for_admin=user.is_staff)
    seller_order_items = list(seller_order_items_qs[:50])

    total_products = len(product_items)
    active_products = sum(
        1
        for item in product_items
        if item.is_active and item.approval_status == SpiceItem.ApprovalStatus.APPROVED
    )
    pending_products = sum(1 for item in product_items if item.approval_status == SpiceItem.ApprovalStatus.PENDING)
    rejected_products = sum(1 for item in product_items if item.approval_status == SpiceItem.ApprovalStatus.REJECTED)
    out_of_stock_products = sum(1 for item in product_items if item.stock == 0)
    low_stock_products = sum(1 for item in product_items if 0 < item.stock <= 5)
    total_stock = sum(item.stock or 0 for item in product_items)
    initial_stock_total = sum(max(item.initial_stock or 0, item.stock or 0) for item in product_items)
    sold_units = sum(_product_sold_units(item) for item in product_items)
    stock_value = sum((_product_stock_value(item) for item in product_items), Decimal('0'))
    sold_value = sum((_product_sold_value(item) for item in product_items), Decimal('0'))
    order_sales_value = seller_order_items_qs.exclude(
        order__status__in=[Order.Status.CANCELLED, Order.Status.RETURNED],
    ).aggregate(total=Sum('line_total')).get('total') or Decimal('0')
    order_units = seller_order_items_qs.exclude(
        order__status__in=[Order.Status.CANCELLED, Order.Status.RETURNED],
    ).aggregate(total=Sum('quantity')).get('total') or 0
    if order_sales_value:
        sold_value = order_sales_value
        sold_units = order_units
    average_sale = sold_value / sold_units if sold_units else Decimal('0')
    average_price = (sum((item.price for item in product_items), Decimal('0')) / total_products) if total_products else Decimal('0')
    stock_alerts = low_stock_products + out_of_stock_products
    stock_health_percent = _percent(total_stock, initial_stock_total)
    active_percent = _percent(active_products, total_products)
    sale_percent = _percent(sold_units, total_stock + sold_units)

    pending_application_count = SellerApplication.objects.filter(status=SellerApplication.Status.PENDING).count()
    pending_orders = seller_order_items_qs.filter(item_status=Order.Status.PENDING).values('order_id').distinct().count()
    completed_orders = seller_order_items_qs.filter(item_status=Order.Status.DELIVERED).values('order_id').distinct().count()
    cancelled_orders = seller_order_items_qs.filter(
        order__status__in=[Order.Status.CANCELLED, Order.Status.RETURNED],
    ).values('order_id').distinct().count()
    pending_payout = sold_value * Decimal('0.90')
    admin_commission = sold_value * Decimal('0.10')

    now = timezone.localtime()
    current_month = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    month_starts = [_shift_month_start(current_month, offset) for offset in range(-5, 1)]
    monthly_points = []
    for month_start in month_starts:
        month_end = _shift_month_start(month_start, 1)
        month_products = [
            item
            for item in product_items
            if month_start <= timezone.localtime(item.updated_at) < month_end
        ]
        revenue_value = sum((_product_sold_value(item) for item in month_products), Decimal('0'))
        activity_value = revenue_value or sum((_product_stock_value(item) for item in month_products), Decimal('0'))
        monthly_points.append(
            {
                'label': month_start.strftime('%b'),
                'raw_value': activity_value,
                'value': _format_currency(activity_value),
            }
        )

    max_month_value = max((point['raw_value'] for point in monthly_points), default=Decimal('0'))
    monthly_sales_points = [
        {
            'label': point['label'],
            'height': max(8, _percent(point['raw_value'], max_month_value)) if max_month_value else 8,
            'value': point['value'],
        }
        for point in monthly_points
    ]
    seller_line_chart = _line_chart_paths(monthly_points)

    category_totals = {}
    for item in product_items:
        label = item.category.name if item.category else 'General'
        category_totals[label] = category_totals.get(label, 0) + (item.stock or 0)
    top_categories = sorted(category_totals.items(), key=lambda pair: pair[1], reverse=True)[:4]
    max_category_total = max((value for _, value in top_categories), default=0)
    seller_category_bars = [
        {
            'label': label[:10],
            'height': max(12, _percent(value, max_category_total)) if max_category_total else 12,
            'value': value,
        }
        for label, value in top_categories
    ] or [{'label': 'No stock', 'height': 12, 'value': 0}]

    progress_sources = [
        ('Active', active_products, total_products),
        ('Pending', pending_products, total_products),
        ('Rejected', rejected_products, total_products),
        ('Low', low_stock_products, total_products),
        ('Out', out_of_stock_products, total_products),
        ('Sold', sold_units, total_stock + sold_units),
    ]
    seller_progress_bars = [
        {
            'label': label,
            'height': max(8, _percent(value, total)) if total else 8,
            'value': value,
        }
        for label, value, total in progress_sources
    ]

    seller_status_lines = [
        {'label': 'Active catalog', 'percent': active_percent, 'value': f'{active_products}/{total_products}'},
        {'label': 'Stock health', 'percent': stock_health_percent, 'value': f'{total_stock} units'},
        {'label': 'Revenue progress', 'percent': sale_percent, 'value': _format_currency(sold_value)},
    ]

    seller_snapshot = {
        'total_products': total_products,
        'active_products': active_products,
        'pending_products': pending_products,
        'rejected_products': rejected_products,
        'pending_orders': pending_orders,
        'completed_orders': completed_orders,
        'cancelled_orders': cancelled_orders,
        'total_sales': _format_currency(sold_value),
        'average_sales': _format_currency(average_sale),
        'average_price': _format_currency(average_price),
        'admin_commission': _format_currency(admin_commission),
        'total_earnings': _format_currency(pending_payout),
        'pending_payout': _format_currency(pending_payout),
        'stock_alerts': stock_alerts,
        'low_stock_products': low_stock_products,
        'out_of_stock_products': out_of_stock_products,
        'total_stock': total_stock,
        'stock_value': _format_currency(stock_value),
        'product_revenue': _format_currency(sold_value),
        'sold_units': sold_units,
        'stock_health_percent': stock_health_percent,
        'active_percent': active_percent,
        'sale_percent': sale_percent,
        'pending_applications': pending_application_count,
    }

    seller_dashboard_cards = [
        {
            'key': 'product_revenue',
            'label': 'Product Revenue',
            'value': seller_snapshot['product_revenue'],
            'icon': 'fas fa-chart-line',
            'tone': 'blue',
            'target': 'earnings',
            'title': 'Sales & Earnings',
            'note': f'{sold_units} units moved',
        },
        {
            'key': 'average_sales',
            'label': 'Average Sales',
            'value': seller_snapshot['average_sales'],
            'icon': 'fas fa-percent',
            'tone': 'coral',
            'target': 'analytics',
            'title': 'Reports / Analytics',
            'note': f'Avg price {seller_snapshot["average_price"]}',
        },
        {
            'key': 'pending_orders',
            'label': 'Pending Orders',
            'value': seller_snapshot['pending_orders'],
            'icon': 'fas fa-bag-shopping',
            'tone': 'green',
            'target': 'orders-2',
            'title': 'Pending Orders',
            'note': f'{completed_orders} delivered',
        },
        {
            'key': 'total_products',
            'label': 'Total Products',
            'value': seller_snapshot['total_products'],
            'icon': 'fas fa-box-open',
            'tone': 'gold',
            'target': 'products-2',
            'title': 'All Products',
            'note': f'{active_products} active',
        },
    ]

    low_stock_list = sorted(
        [item for item in product_items if item.stock <= 5],
        key=lambda item: (item.stock or 0, item.name),
    )[:8]
    live_product_list = sorted(
        [
            item
            for item in product_items
            if item.is_active and item.approval_status == SpiceItem.ApprovalStatus.APPROVED
        ],
        key=lambda item: item.updated_at,
        reverse=True,
    )[:8]
    out_of_stock_list = sorted(
        [item for item in product_items if item.stock == 0],
        key=lambda item: item.updated_at,
        reverse=True,
    )[:8]

    product_ids = [item.pk for item in product_items]
    order_ids = list(seller_order_items_qs.values_list('order_id', flat=True).distinct())

    reviews = ProductReview.objects.select_related('product', 'customer').order_by('-created_at')
    if not user.is_staff:
        reviews = reviews.filter(product_id__in=product_ids)
    review_rows = [
        _seller_row(
            [
                _seller_cell(review.product.name),
                _seller_cell(review.reviewer_label),
                _seller_cell(review.rating),
                _seller_cell(review.comment[:90] if review.comment else review.title or 'No comment'),
                _seller_cell(review.get_status_display(), review.status_tone),
                _seller_cell(review.created_at.strftime('%d %b %Y')),
            ],
            [
                _seller_action(
                    'View',
                    reverse('seller-product-preview', kwargs={'pk': review.product.pk}),
                ),
                _seller_action('Edit', reverse('seller-product-edit', kwargs={'pk': review.product.pk}), 'edit'),
                _seller_action('Delete', reverse('seller-review-delete', kwargs={'pk': review.pk}), 'delete', 'post'),
            ],
        )
        for review in reviews[:30]
    ]

    returns = ReturnRequest.objects.select_related('order', 'customer').order_by('-updated_at')
    if not user.is_staff:
        returns = returns.filter(order_id__in=order_ids)
    return_rows = [
        _seller_row(
            [
                _seller_cell(return_request.order.order_number),
                _seller_cell(return_request.customer.first_name or return_request.customer.username if return_request.customer else return_request.order.customer_name),
                _seller_cell(return_request.reason),
                _seller_cell(_format_currency(return_request.refund_amount)),
                _seller_cell(return_request.get_status_display(), return_request.status_tone),
                _seller_cell(return_request.updated_at.strftime('%d %b %Y')),
            ],
            [
                _seller_action('View', reverse('seller-order-invoice', kwargs={'pk': return_request.order.pk})),
                _seller_action('Edit', '', 'edit', 'client', section='orders', title='Orders'),
                _seller_action('Delete', reverse('seller-return-delete', kwargs={'pk': return_request.pk}), 'delete', 'post'),
            ],
        )
        for return_request in returns[:30]
    ]

    coupons = Coupon.objects.order_by('-updated_at')
    if seller_profile and not user.is_staff:
        coupons = coupons.filter(title__icontains=seller_profile.store_name)
    coupon_rows = [
        _seller_row(
            [
                _seller_cell(coupon.code),
                _seller_cell(coupon.title),
                _seller_cell(_seller_discount_label(coupon)),
                _seller_cell(coupon.starts_at.strftime('%d %b %Y') if coupon.starts_at else 'Any time'),
                _seller_cell(coupon.ends_at.strftime('%d %b %Y') if coupon.ends_at else 'No end'),
                _seller_cell('Active' if coupon.is_active else 'Pending approval', 'success' if coupon.is_active else 'warning'),
            ],
            [
                _seller_action('View', '', 'view', 'client', modal=True),
                _seller_action('Edit', '', 'edit', 'client', section='coupons', title='Coupons / Offers'),
                _seller_action('Delete', reverse('seller-coupon-delete', kwargs={'pk': coupon.pk}), 'delete', 'post'),
            ],
        )
        for coupon in coupons[:30]
    ]

    shipments = ShipmentTracking.objects.select_related('order', 'courier').order_by('-updated_at')
    if not user.is_staff:
        shipments = shipments.filter(order_id__in=order_ids)
    shipping_rows = [
        _seller_row(
            [
                _seller_cell(shipment.order.order_number),
                _seller_cell(shipment.courier.name if shipment.courier else 'Not assigned'),
                _seller_cell(shipment.tracking_number or 'Not set'),
                _seller_cell(shipment.status),
                _seller_cell(shipment.last_location or 'Not set'),
                _seller_cell(shipment.updated_at.strftime('%d %b %Y')),
            ],
            [
                _seller_action('View', reverse('seller-order-invoice', kwargs={'pk': shipment.order.pk})),
                _seller_action('Edit', '', 'edit', 'client', section='shipping', title='Shipping Management'),
                _seller_action('Delete', reverse('seller-shipment-delete', kwargs={'pk': shipment.pk}), 'delete', 'post'),
            ],
        )
        for shipment in shipments[:30]
    ]

    seller_tickets = SupportTicket.objects.select_related('seller', 'customer').order_by('-updated_at')
    if user.is_staff:
        seller_tickets = seller_tickets.filter(ticket_type=SupportTicket.TicketType.SELLER)
    elif seller_profile:
        seller_tickets = seller_tickets.filter(seller=seller_profile)
    else:
        seller_tickets = seller_tickets.none()

    payout_tickets = seller_tickets.filter(subject__istartswith='Payout request')
    message_tickets = seller_tickets.exclude(subject__istartswith='Payout request')
    ticket_rows = [
        _seller_row(
            [
                _seller_cell(f'#{ticket.pk}'),
                _seller_cell(ticket.subject),
                _seller_cell(_seller_ticket_user_label(ticket)),
                _seller_cell(ticket.get_status_display(), ticket.status_tone),
                _seller_cell(ticket.admin_reply[:90] if ticket.admin_reply else 'Awaiting admin reply'),
                _seller_cell(ticket.updated_at.strftime('%d %b %Y')),
            ],
            [
                _seller_action('View', '', 'view', 'client', modal=True),
                _seller_action('Edit', '', 'edit', 'client', section='support', title='Support / Help Center'),
                _seller_action('Delete', reverse('seller-ticket-delete', kwargs={'pk': ticket.pk}), 'delete', 'post'),
            ],
        )
        for ticket in message_tickets[:30]
    ]
    payout_rows = [
        _seller_row(
            [
                _seller_cell(f'#{ticket.pk}'),
                _seller_cell(ticket.subject.replace('Payout request: ', '')),
                _seller_cell(ticket.get_status_display(), ticket.status_tone),
                _seller_cell(ticket.admin_reply[:90] if ticket.admin_reply else 'Pending admin review'),
                _seller_cell(ticket.updated_at.strftime('%d %b %Y')),
            ],
            [
                _seller_action('View', '', 'view', 'client', modal=True),
                _seller_action('Edit', '', 'edit', 'client', section='payout', title='Payout / Withdraw Request'),
                _seller_action('Delete', reverse('seller-ticket-delete', kwargs={'pk': ticket.pk}), 'delete', 'post'),
            ],
        )
        for ticket in payout_tickets[:20]
    ]

    notifications = NotificationTemplate.objects.order_by('template_type', 'name')
    notification_rows = [
        _seller_row(
            [
                _seller_cell(notification.get_template_type_display()),
                _seller_cell(notification.name),
                _seller_cell(notification.subject or notification.body[:90]),
                _seller_cell('Active' if notification.is_active else 'Inactive', 'success' if notification.is_active else 'danger'),
                _seller_cell(notification.updated_at.strftime('%d %b %Y')),
            ],
            [
                _seller_action('View', '', 'view', 'client', modal=True),
                _seller_action('Edit', '', 'edit', 'client', section='notifications', title='Notifications'),
            ],
        )
        for notification in notifications[:30]
    ]

    seller_tracking_orders = list(
        Order.objects.filter(pk__in=order_ids)
        .exclude(status__in=[Order.Status.CANCELLED, Order.Status.RETURNED])
        .order_by('-updated_at')[:50]
    )

    return {
        'seller_profile': seller_profile,
        'seller_snapshot': seller_snapshot,
        'seller_dashboard_cards': seller_dashboard_cards,
        'seller_products': product_items,
        'live_products': live_product_list,
        'out_of_stock_products': out_of_stock_list,
        'low_stock_products': low_stock_list,
        'monthly_sales_points': monthly_sales_points,
        'seller_line_chart': seller_line_chart,
        'seller_progress_bars': seller_progress_bars,
        'seller_category_bars': seller_category_bars,
        'seller_status_lines': seller_status_lines,
        'seller_order_rows': _seller_order_rows(seller_order_items),
        'seller_pending_order_rows': _seller_order_rows([item for item in seller_order_items if item.item_status == Order.Status.PENDING]),
        'seller_confirmed_order_rows': _seller_order_rows([item for item in seller_order_items if item.item_status == Order.Status.CONFIRMED]),
        'seller_packed_order_rows': _seller_order_rows([item for item in seller_order_items if item.item_status == Order.Status.PACKED]),
        'seller_shipped_order_rows': _seller_order_rows([item for item in seller_order_items if item.item_status == Order.Status.SHIPPED]),
        'seller_delivered_order_rows': _seller_order_rows([item for item in seller_order_items if item.item_status == Order.Status.DELIVERED]),
        'seller_cancelled_order_rows': _seller_order_rows([item for item in seller_order_items if item.item_status == Order.Status.CANCELLED]),
        'seller_returned_order_rows': _seller_order_rows([item for item in seller_order_items if item.item_status == Order.Status.RETURNED]),
        'seller_order_status_choices': Order.Status.choices,
        'seller_tracking_orders': seller_tracking_orders,
        'seller_courier_partners': CourierPartner.objects.filter(is_active=True).order_by('name'),
        'seller_shipment_status_choices': ShipmentTracking.Status.choices,
        'seller_returns_table': _seller_table('Returns & Refunds', ['Order ID', 'Customer', 'Reason', 'Refund', 'Status', 'Updated'], return_rows, 'No return requests yet.', f'{len(return_rows)} live'),
        'seller_coupons_table': _seller_table('Live Coupons / Offers', ['Code', 'Title', 'Discount', 'Start', 'End', 'Status'], coupon_rows, 'No coupons found yet.', f'{len(coupon_rows)} records'),
        'seller_messages_table': _seller_table('Messages / Customer Queries', ['Ticket', 'Subject', 'User', 'Status', 'Admin Reply', 'Updated'], ticket_rows, 'No messages or seller queries yet.', f'{len(ticket_rows)} tickets'),
        'seller_reviews_table': _seller_table('Product Reviews', ['Product', 'Customer', 'Rating', 'Review', 'Status', 'Date'], review_rows, 'No product reviews yet.', f'{len(review_rows)} reviews'),
        'seller_ratings_table': _seller_table('Reviews & Ratings', ['Product', 'Customer', 'Rating', 'Review', 'Status', 'Date'], review_rows, 'No reviews yet.', f'{len(review_rows)} reviews'),
        'seller_shipping_table': _seller_table('Shipment Tracking', ['Order', 'Courier', 'Tracking Number', 'Status', 'Last Location', 'Updated'], shipping_rows, 'No shipment tracking records yet.', f'{len(shipping_rows)} records'),
        'seller_notifications_table': _seller_table('Notifications', ['Type', 'Name', 'Message', 'Status', 'Updated'], notification_rows, 'No notification templates yet.', f'{len(notification_rows)} templates'),
        'seller_support_table': _seller_table('Support / Help Center', ['Ticket', 'Subject', 'User', 'Status', 'Admin Reply', 'Updated'], ticket_rows, 'No support tickets yet.', f'{len(ticket_rows)} tickets'),
        'seller_payout_table': _seller_table('Payout Requests', ['Request', 'Amount', 'Status', 'Admin Reply', 'Updated'], payout_rows, 'No payout requests yet.', f'{len(payout_rows)} requests'),
    }


def login_view(request):
    if request.user.is_authenticated:
        return redirect('role-redirect')

    form = LoginForm(request, data=request.POST or None)
    if request.method == 'POST' and form.is_valid():
        user = form.get_user()
        seller_application = _get_seller_application_for_user(user)
        if seller_application and seller_application.status != SellerApplication.Status.APPROVED and not user.is_staff:
            messages.warning(request, _seller_pending_message(seller_application))
            return redirect('login')
        login(request, user)
        messages.success(request, 'Login successful.')
        return redirect('panel-welcome')
    if request.method == 'POST' and not form.is_valid():
        lookup_email = (request.POST.get('username') or '').strip().lower()
        seller_application = _latest_seller_application(lookup_email)
        pending_message = _seller_pending_message(seller_application)
        if pending_message:
            messages.warning(request, pending_message)

    return render(request, 'auth/login.html', {'form': form})


@login_required
def panel_welcome(request):
    user = request.user
    display_name = (user.get_full_name() or user.username or user.email or 'User').strip()
    return render(
        request,
        'pannel_welcome_msg.html',
        {
            'display_name': display_name,
            'redirect_url': reverse('role-redirect'),
        },
    )


@require_http_methods(['POST'])
def login_otp_request(request):
    if request.user.is_authenticated:
        return JsonResponse({'success': True, 'redirect_url': reverse('role-redirect')})

    form = EmailOTPRequestForm(request.POST)
    if not form.is_valid():
        return JsonResponse({'success': False, 'message': 'Enter a valid email address.'}, status=400)

    email = form.cleaned_data['email']
    user = _find_user_by_email(email)
    seller_application = _latest_seller_application(email)
    pending_message = _seller_pending_message(seller_application)
    if pending_message and not (user and user.is_staff):
        return JsonResponse({'success': False, 'message': pending_message}, status=403)

    request.session[LOGIN_OTP_SESSION_KEY] = email
    cooldown_seconds = int(getattr(settings, 'EMAIL_OTP_RESEND_COOLDOWN_SECONDS', 60))
    message = 'If this email can login, an OTP has been sent.'
    if user:
        try:
            result = create_email_otp(email, EmailOTP.Purpose.LOGIN, request=request)
        except Exception:
            return JsonResponse({'success': False, 'message': 'We could not send OTP right now. Please try again.'}, status=500)
        cooldown_seconds = result.cooldown_seconds
        message = 'OTP sent to your email.' if result.sent else result.message

    return JsonResponse(
        {
            'success': True,
            'message': message,
            'cooldown_seconds': cooldown_seconds,
            'email': email,
        }
    )


@require_http_methods(['POST'])
def login_otp_verify(request):
    email = request.session.get(LOGIN_OTP_SESSION_KEY)
    if not email:
        return JsonResponse({'success': False, 'message': 'Please request a login OTP first.'}, status=400)

    form = OTPVerifyForm(request.POST)
    if form.is_valid():
        result = verify_otp(email, EmailOTP.Purpose.LOGIN, form.cleaned_data['otp'])
        if result.valid:
            user = _find_user_by_email(email)
            if not user:
                mark_otp_used(result.otp_record)
                return JsonResponse({'success': False, 'message': 'Unable to login with this email.'}, status=400)
            seller_application = _get_seller_application_for_user(user)
            if seller_application and seller_application.status != SellerApplication.Status.APPROVED and not user.is_staff:
                mark_otp_used(result.otp_record)
                return JsonResponse({'success': False, 'message': _seller_pending_message(seller_application)}, status=403)
            mark_otp_used(result.otp_record)
            request.session.pop(LOGIN_OTP_SESSION_KEY, None)
            login(request, user)
            return JsonResponse(
                {
                    'success': True,
                    'message': 'Login successful.',
                    'redirect_url': reverse('panel-welcome'),
                }
            )
        error_message = result.message
    else:
        error_message = 'Enter the 6 digit OTP.'

    return JsonResponse({'success': False, 'message': error_message}, status=400)


def register_view(request):
    if request.user.is_authenticated:
        return redirect('home')

    form = RegisterForm(request.POST or None, request.FILES or None)
    if request.method == 'POST' and form.is_valid():
        pending = _stash_customer_registration(form)
        request.session[CUSTOMER_REGISTER_SESSION_KEY] = pending
        result = _request_flow_otp(request, pending['email'], EmailOTP.Purpose.CUSTOMER_REGISTER)
        if not result:
            return render(request, 'auth/register.html', {'form': form})
        if result.sent:
            messages.success(request, 'OTP sent to your email.')
        else:
            messages.info(request, result.message)
        return _render_otp_verify(
            request,
            email=pending['email'],
            purpose=EmailOTP.Purpose.CUSTOMER_REGISTER,
            verify_route='register-verify-otp',
            resend_route='register-resend-otp',
            title='Verify Your Email',
            subtitle='Enter the 6 digit OTP to create your customer account.',
            submit_label='Continue',
            back_url=reverse('register'),
            icon_class='fa-solid fa-user-check',
        )

    return render(request, 'auth/register.html', {'form': form})


@require_http_methods(['POST'])
def register_verify_otp(request):
    pending = request.session.get(CUSTOMER_REGISTER_SESSION_KEY)
    if not pending:
        messages.error(request, 'Please submit the registration form first.')
        return redirect('register')

    email = pending.get('email')
    form = OTPVerifyForm(request.POST)
    if form.is_valid():
        result = verify_otp(email, EmailOTP.Purpose.CUSTOMER_REGISTER, form.cleaned_data['otp'])
        if result.valid:
            with transaction.atomic():
                user, error = _create_customer_from_pending(pending)
                if error:
                    mark_otp_used(result.otp_record)
                    request.session.pop(CUSTOMER_REGISTER_SESSION_KEY, None)
                    messages.error(request, error)
                    return redirect('register')
                mark_otp_used(result.otp_record)
            request.session.pop(CUSTOMER_REGISTER_SESSION_KEY, None)
            send_account_email(
                user.email,
                'emails/customer_registration_success.html',
                'Welcome to Lexvers',
                {'name': user.first_name},
            )
            login(request, user)
            messages.success(request, 'Email verified successfully. Welcome to Lexvers.')
            return redirect('home')
        error_message = result.message
    else:
        error_message = 'Enter the 6 digit OTP.'

    return _render_otp_verify(
        request,
        email=email,
        purpose=EmailOTP.Purpose.CUSTOMER_REGISTER,
        verify_route='register-verify-otp',
        resend_route='register-resend-otp',
        title='Verify Your Email',
        subtitle='Enter the 6 digit OTP to create your customer account.',
        submit_label='Continue',
        back_url=reverse('register'),
        error_message=error_message,
        info_message='',
        form=form,
        icon_class='fa-solid fa-user-check',
    )


@require_http_methods(['POST'])
def register_resend_otp(request):
    pending = request.session.get(CUSTOMER_REGISTER_SESSION_KEY)
    if not pending:
        messages.error(request, 'Please submit the registration form first.')
        return redirect('register')
    email = pending.get('email')
    result = _request_flow_otp(request, email, EmailOTP.Purpose.CUSTOMER_REGISTER)
    if result and result.sent:
        messages.success(request, 'OTP sent to your email.')
    elif result:
        messages.info(request, result.message)
    return _render_otp_verify(
        request,
        email=email,
        purpose=EmailOTP.Purpose.CUSTOMER_REGISTER,
        verify_route='register-verify-otp',
        resend_route='register-resend-otp',
        title='Verify Your Email',
        subtitle='Enter the 6 digit OTP to create your customer account.',
        submit_label='Continue',
        back_url=reverse('register'),
        info_message='OTP sent to your email.',
        icon_class='fa-solid fa-user-check',
    )


def forgot_password_request(request):
    if request.user.is_authenticated:
        return redirect('role-redirect')

    form = EmailOTPRequestForm(request.POST or None)
    if request.method == 'POST' and form.is_valid():
        email = form.cleaned_data['email']
        request.session[FORGOT_PASSWORD_EMAIL_SESSION_KEY] = email
        request.session[FORGOT_PASSWORD_VERIFIED_SESSION_KEY] = False
        user = _find_user_by_email(email)
        if user:
            _request_flow_otp(request, email, EmailOTP.Purpose.FORGOT_PASSWORD)
        messages.info(request, 'If this email exists, an OTP has been sent.')
        return _render_otp_verify(
            request,
            email=email,
            purpose=EmailOTP.Purpose.FORGOT_PASSWORD,
            verify_route='forgot-password-verify',
            resend_route='forgot-password-resend',
            title='Verify Password Reset',
            subtitle='Enter the OTP sent to your email to continue.',
            submit_label='Verify OTP',
            back_url=reverse('login'),
            info_message='If this email exists, an OTP has been sent.',
            icon_class='fa-solid fa-key',
        )

    return render(
        request,
        'auth/request_otp.html',
        {
            'form': form,
            'title': 'Forgot Password',
            'subtitle': 'Enter your email. If the account exists, we will send a password reset OTP.',
            'button_label': 'Send OTP',
            'secondary_url': reverse('login'),
            'secondary_label': 'Back to login',
            'icon_class': 'fa-solid fa-key',
        },
    )


@require_http_methods(['POST'])
def forgot_password_verify(request):
    email = request.session.get(FORGOT_PASSWORD_EMAIL_SESSION_KEY)
    if not email:
        messages.error(request, 'Please request a password reset OTP first.')
        return redirect('forgot-password')

    form = OTPVerifyForm(request.POST)
    if form.is_valid():
        result = verify_otp(email, EmailOTP.Purpose.FORGOT_PASSWORD, form.cleaned_data['otp'])
        if result.valid and _find_user_by_email(email):
            mark_otp_used(result.otp_record)
            request.session[FORGOT_PASSWORD_VERIFIED_SESSION_KEY] = True
            messages.success(request, 'Email verified successfully.')
            return redirect('forgot-password-set-new')
        error_message = result.message if not result.valid else 'Unable to verify this request.'
    else:
        error_message = 'Enter the 6 digit OTP.'

    return _render_otp_verify(
        request,
        email=email,
        purpose=EmailOTP.Purpose.FORGOT_PASSWORD,
        verify_route='forgot-password-verify',
        resend_route='forgot-password-resend',
        title='Verify Password Reset',
        subtitle='Enter the OTP sent to your email to continue.',
        submit_label='Verify OTP',
        back_url=reverse('login'),
        error_message=error_message,
        info_message='',
        form=form,
        icon_class='fa-solid fa-key',
    )


@require_http_methods(['POST'])
def forgot_password_resend(request):
    email = request.session.get(FORGOT_PASSWORD_EMAIL_SESSION_KEY)
    if not email:
        messages.error(request, 'Please request a password reset OTP first.')
        return redirect('forgot-password')
    if _find_user_by_email(email):
        result = _request_flow_otp(request, email, EmailOTP.Purpose.FORGOT_PASSWORD)
        if result and result.sent:
            messages.success(request, 'OTP sent to your email.')
        elif result:
            messages.info(request, result.message)
    messages.info(request, 'If this email exists, an OTP has been sent.')
    return _render_otp_verify(
        request,
        email=email,
        purpose=EmailOTP.Purpose.FORGOT_PASSWORD,
        verify_route='forgot-password-verify',
        resend_route='forgot-password-resend',
        title='Verify Password Reset',
        subtitle='Enter the OTP sent to your email to continue.',
        submit_label='Verify OTP',
        back_url=reverse('login'),
        info_message='If this email exists, an OTP has been sent.',
        icon_class='fa-solid fa-key',
    )


def forgot_password_set_new(request):
    email = request.session.get(FORGOT_PASSWORD_EMAIL_SESSION_KEY)
    verified = request.session.get(FORGOT_PASSWORD_VERIFIED_SESSION_KEY)
    user = _find_user_by_email(email)
    if not email or not verified or not user:
        messages.error(request, 'Please verify your OTP before setting a new password.')
        return redirect('forgot-password')

    form = ForgotPasswordSetForm(request.POST or None, user=user)
    if request.method == 'POST' and form.is_valid():
        user.set_password(form.cleaned_data['password1'])
        user.save(update_fields=['password'])
        send_account_email(
            user.email,
            'emails/password_reset_success.html',
            'Your Lexvers password was updated',
            {'name': user.first_name or user.username},
        )
        request.session.pop(FORGOT_PASSWORD_EMAIL_SESSION_KEY, None)
        request.session.pop(FORGOT_PASSWORD_VERIFIED_SESSION_KEY, None)
        messages.success(request, 'Password updated successfully. Please login with your new password.')
        return redirect('login')

    return render(
        request,
        'auth/set_new_password.html',
        {
            'form': form,
            'email': email,
        },
    )


@login_required
def logout_view(request):
    logout(request)
    messages.info(request, 'You have been logged out.')
    return redirect('home')


@login_required
def role_redirect(request):
    if request.user.is_staff:
        return redirect('admin-dashboard')
    if _is_seller_user(request.user):
        return redirect('seller-dashboard')
    return redirect('home')


def _customer_panel_counts(user):
    return {
        'saved': SavedProduct.objects.filter(user=user).count(),
        'addresses': CustomerAddress.objects.filter(user=user).count(),
        'orders': Order.objects.filter(customer=user).count(),
        'coupons': Coupon.objects.filter(is_active=True).count(),
    }


def _customer_coupon_rows():
    return [
        {
            'code': coupon.code,
            'title': coupon.title,
            'detail': f'{coupon.get_discount_type_display()} discount: {coupon.discount_value}',
            'status': 'Active' if coupon.is_active else 'Inactive',
        }
        for coupon in Coupon.objects.filter(is_active=True).order_by('-updated_at')
    ]


@login_required
def customer_panel(request, section='profile'):
    allowed_sections = {item['key'] for item in CUSTOMER_NAV}
    if section not in allowed_sections:
        section = 'profile'

    profile = _get_customer_profile(request.user)
    profile_form = CustomerProfileForm(instance=profile, user=request.user)
    address_form = CustomerAddressForm()
    editing_address_id = ''

    if request.method == 'POST':
        form_action = request.POST.get('form_action', '')
        if form_action == 'profile':
            profile_form = CustomerProfileForm(request.POST, request.FILES, instance=profile, user=request.user)
            if profile_form.is_valid():
                profile_form.save()
                messages.success(request, 'Profile updated successfully.')
                return redirect('customer-panel', section='profile')
        elif form_action == 'address':
            address_id = request.POST.get('address_id', '').strip()
            address_instance = None
            if address_id:
                address_instance = get_object_or_404(CustomerAddress, pk=address_id, user=request.user)
                editing_address_id = str(address_instance.pk)
            address_form = CustomerAddressForm(request.POST, instance=address_instance)
            if address_form.is_valid():
                _save_customer_address_form(request.user, address_form, address_instance)
                messages.success(request, 'Address updated successfully.' if address_instance else 'Address saved successfully.')
                return redirect('customer-panel', section='address')
            messages.error(request, 'Please check the highlighted address fields.')

    saved_products = (
        SavedProduct.objects.filter(user=request.user)
        .select_related('product', 'product__category', 'product__seller')
        .prefetch_related('product__gallery_images')
    )
    addresses = CustomerAddress.objects.filter(user=request.user)
    orders = Order.objects.filter(customer=request.user).prefetch_related('items').order_by('-created_at')

    return render(
        request,
        'customer_panel/dashboard.html',
        {
            'customer_nav': CUSTOMER_NAV,
            'customer_section': section,
            'customer_counts': _customer_panel_counts(request.user),
            'profile': profile,
            'profile_form': profile_form,
            'address_form': address_form,
            'editing_address_id': editing_address_id,
            'addresses': addresses,
            'addresses_json': _address_snapshot_list(addresses),
            'orders': orders,
            'saved_products': saved_products,
            'saved_product_ids': _saved_product_ids(request.user),
            'coupon_rows': _customer_coupon_rows(),
            'search_text': '',
            'selected_category': '',
            'selected_spice': '',
        },
    )


@login_required
@require_http_methods(['POST'])
def toggle_saved_product(request, pk):
    product = get_object_or_404(
        SpiceItem.objects.filter(is_active=True, approval_status=SpiceItem.ApprovalStatus.APPROVED),
        pk=pk,
    )
    saved_item, created = SavedProduct.objects.get_or_create(user=request.user, product=product)
    if not created:
        saved_item.delete()

    return JsonResponse(
        {
            'saved': created,
            'count': SavedProduct.objects.filter(user=request.user).count(),
            'product_id': product.pk,
        }
    )


@login_required
def customer_saved_live(request):
    saved_products = (
        SavedProduct.objects.filter(user=request.user)
        .select_related('product', 'product__category', 'product__seller')
        .prefetch_related('product__gallery_images')
    )
    return JsonResponse(
        {
            'count': saved_products.count(),
            'html': render_to_string(
                'customer_panel/partials/saved_products.html',
                {
                    'saved_products': saved_products,
                    'saved_product_ids': _saved_product_ids(request.user),
                },
                request=request,
            ),
        }
    )


def become_seller(request):
    return render(
        request,
        'website/become_seller.html',
        {
            'search_text': '',
            'selected_category': '',
            'selected_spice': '',
        },
    )


def _seller_register_context(request, form):
    verified_email = _seller_registration_verified_email(request)
    return {
        'form': form,
        'seller_verified_email': verified_email,
        'search_text': '',
        'selected_category': '',
        'selected_spice': '',
    }


def seller_register(request):
    form = SellerApplicationForm(request.POST or None, request.FILES or None)
    if request.method == 'POST':
        is_valid = form.is_valid()
        email = normalize_email(form.cleaned_data.get('email') if is_valid else request.POST.get('email'))
        if is_valid and not _seller_registration_email_is_verified(request, email):
            form.add_error('email', 'Verify this email with OTP before submitting your seller request.')
            is_valid = False
        if is_valid:
            with transaction.atomic():
                application = form.save()
            _clear_seller_registration_otp_state(request)
            send_account_email(
                application.email,
                'emails/seller_registration_pending.html',
                'Seller registration pending approval',
                {'seller': application},
            )
            messages.success(request, 'Your seller account request has been submitted successfully. Please wait for admin approval.')
            return redirect('seller-application-submitted', pk=application.pk)
        messages.error(request, 'Please fix the highlighted seller registration errors. Re-upload document files if the form was returned after submit.')

    return render(
        request,
        'seller_panel/register.html',
        _seller_register_context(request, form),
    )


@require_http_methods(['POST'])
def seller_register_send_otp(request):
    form = EmailOTPRequestForm(request.POST)
    if not form.is_valid():
        return JsonResponse({'success': False, 'message': 'Enter a valid email address.'}, status=400)

    email = normalize_email(form.cleaned_data['email'])
    if SellerApplication.objects.filter(email__iexact=email).exists():
        return JsonResponse({'success': False, 'message': 'A seller application with this email already exists.'}, status=400)
    if _find_user_by_email(email):
        return JsonResponse({'success': False, 'message': 'This email already has an account. Please use another email or contact admin.'}, status=400)

    request.session[SELLER_REGISTER_OTP_EMAIL_SESSION_KEY] = email
    request.session.pop(SELLER_REGISTER_VERIFIED_SESSION_KEY, None)
    try:
        result = create_email_otp(email, EmailOTP.Purpose.SELLER_REGISTER, request=request)
    except Exception:
        return JsonResponse({'success': False, 'message': 'We could not send OTP right now. Please try again.'}, status=500)

    return JsonResponse(
        {
            'success': True,
            'message': 'OTP sent to your email.' if result.sent else result.message,
            'cooldown_seconds': result.cooldown_seconds,
            'email': email,
        }
    )


@require_http_methods(['POST'])
def seller_register_verify_email_otp(request):
    email = normalize_email(request.POST.get('email') or request.session.get(SELLER_REGISTER_OTP_EMAIL_SESSION_KEY))
    pending_email = normalize_email(request.session.get(SELLER_REGISTER_OTP_EMAIL_SESSION_KEY))
    if not email or not pending_email or email != pending_email:
        return JsonResponse({'success': False, 'message': 'Please request an OTP for this email first.'}, status=400)

    form = OTPVerifyForm(request.POST)
    if not form.is_valid():
        return JsonResponse({'success': False, 'message': 'Enter the 6 digit OTP.'}, status=400)

    result = verify_otp(email, EmailOTP.Purpose.SELLER_REGISTER, form.cleaned_data['otp'])
    if not result.valid:
        return JsonResponse({'success': False, 'message': result.message}, status=400)

    mark_otp_used(result.otp_record)
    request.session[SELLER_REGISTER_VERIFIED_SESSION_KEY] = {
        'email': email,
        'verified': True,
        'verified_at': timezone.now().isoformat(),
    }
    request.session.pop(SELLER_REGISTER_OTP_EMAIL_SESSION_KEY, None)
    return JsonResponse({'success': True, 'message': 'Email verified successfully.', 'email': email})


@require_http_methods(['POST'])
def seller_register_verify_otp(request):
    pending = request.session.get(SELLER_REGISTER_SESSION_KEY)
    if not pending:
        messages.error(request, 'Please submit the seller registration form first.')
        return redirect('seller-register')

    email = pending.get('fields', {}).get('email')
    form = OTPVerifyForm(request.POST)
    if form.is_valid():
        result = verify_otp(email, EmailOTP.Purpose.SELLER_REGISTER, form.cleaned_data['otp'])
        if result.valid:
            with transaction.atomic():
                application, error = _create_seller_from_pending(pending)
                if error:
                    mark_otp_used(result.otp_record)
                    request.session.pop(SELLER_REGISTER_SESSION_KEY, None)
                    messages.error(request, error)
                    return redirect('seller-register')
                mark_otp_used(result.otp_record)
            request.session.pop(SELLER_REGISTER_SESSION_KEY, None)
            send_account_email(
                application.email,
                'emails/seller_registration_pending.html',
                'Seller registration pending approval',
                {'seller': application},
            )
            messages.success(request, 'Seller account submitted for admin approval.')
            return redirect('seller-application-submitted', pk=application.pk)
        error_message = result.message
    else:
        error_message = 'Enter the 6 digit OTP.'

    return _render_otp_verify(
        request,
        email=email,
        purpose=EmailOTP.Purpose.SELLER_REGISTER,
        verify_route='seller-register-verify-otp',
        resend_route='seller-register-resend-otp',
        title='Verify Seller Email',
        subtitle='Enter the 6 digit OTP to submit your seller request for admin approval.',
        submit_label='Continue',
        back_url=reverse('seller-register'),
        error_message=error_message,
        info_message='',
        form=form,
        icon_class='fa-solid fa-store',
    )


@require_http_methods(['POST'])
def seller_register_resend_otp(request):
    pending = request.session.get(SELLER_REGISTER_SESSION_KEY)
    if not pending:
        messages.error(request, 'Please submit the seller registration form first.')
        return redirect('seller-register')
    email = pending.get('fields', {}).get('email')
    result = _request_flow_otp(request, email, EmailOTP.Purpose.SELLER_REGISTER)
    if result and result.sent:
        messages.success(request, 'OTP sent to your email.')
    elif result:
        messages.info(request, result.message)
    return _render_otp_verify(
        request,
        email=email,
        purpose=EmailOTP.Purpose.SELLER_REGISTER,
        verify_route='seller-register-verify-otp',
        resend_route='seller-register-resend-otp',
        title='Verify Seller Email',
        subtitle='Enter the 6 digit OTP to submit your seller request for admin approval.',
        submit_label='Continue',
        back_url=reverse('seller-register'),
        info_message='OTP sent to your email.',
        icon_class='fa-solid fa-store',
    )


def seller_application_submitted(request, pk):
    application = get_object_or_404(SellerApplication, pk=pk)
    return render(
        request,
        'seller_panel/submitted.html',
        {
            'application': application,
            'search_text': '',
            'selected_category': '',
            'selected_spice': '',
        },
    )


@login_required
def seller_dashboard(request):
    if not request.user.is_staff and not _is_seller_user(request.user):
        seller_application = _get_seller_application_for_user(request.user)
        if seller_application and seller_application.status == SellerApplication.Status.PENDING:
            messages.warning(request, 'Your seller account request is pending admin approval.')
        elif seller_application and seller_application.status == SellerApplication.Status.MORE_INFO:
            messages.warning(request, 'Admin requested more information before approving your seller dashboard access.')
        elif seller_application and seller_application.status == SellerApplication.Status.REJECTED:
            messages.error(request, 'Your seller account request was rejected. Please contact support for details.')
        else:
            messages.error(request, 'Seller panel access requires an approved seller account.')
        return redirect('become-seller')

    dashboard_data = _build_seller_dashboard_data(request.user)
    settings_forms = _seller_settings_forms(dashboard_data['seller_profile'])

    return render(
        request,
        'seller_panel/dashboard.html',
        {
            **_seller_layout_context(request.user, 'Dashboard', 'dashboard', live_enabled=True),
            'seller_product_form': SellerProductForm(),
            'seller_coupon_discount_types': Coupon.DiscountType.choices,
            'recent_applications': SellerApplication.objects.order_by('-created_at')[:5],
            **settings_forms,
            **dashboard_data,
        },
    )


def _seller_live_fragments(request, dashboard_data):
    settings_forms = _seller_settings_forms(dashboard_data['seller_profile'])
    settings_context = {
        **_seller_layout_context(request.user, 'Dashboard', 'dashboard', live_enabled=True),
        **dashboard_data,
        **settings_forms,
    }
    return {
        'products_overview': render_to_string(
            'seller_panel/partials/products_table.html',
            {'products': dashboard_data['seller_products'], 'show_stock_form': True},
            request=request,
        ),
        'products_all': render_to_string(
            'seller_panel/partials/products_table.html',
            {'products': dashboard_data['seller_products'], 'show_stock_form': True},
            request=request,
        ),
        'products_pending': render_to_string(
            'seller_panel/partials/products_table.html',
            {'products': dashboard_data['live_products'], 'show_stock_form': True, 'table_title': 'Live Products'},
            request=request,
        ),
        'products_out': render_to_string(
            'seller_panel/partials/products_table.html',
            {'products': dashboard_data['out_of_stock_products'], 'show_stock_form': True},
            request=request,
        ),
        'product_reviews': render_to_string(
            'seller_panel/partials/data_table.html',
            {'table': dashboard_data['seller_reviews_table']},
            request=request,
        ),
        'orders_all': render_to_string(
            'seller_panel/partials/order_board.html',
            {'title': 'All Orders', 'seller_order_rows': dashboard_data['seller_order_rows'], 'seller_order_status_choices': dashboard_data['seller_order_status_choices']},
            request=request,
        ),
        'orders_pending': render_to_string(
            'seller_panel/partials/order_board.html',
            {'title': 'Pending Orders', 'seller_order_rows': dashboard_data['seller_pending_order_rows'], 'seller_order_status_choices': dashboard_data['seller_order_status_choices']},
            request=request,
        ),
        'orders_confirmed': render_to_string(
            'seller_panel/partials/order_board.html',
            {'title': 'Confirmed Orders', 'seller_order_rows': dashboard_data['seller_confirmed_order_rows'], 'seller_order_status_choices': dashboard_data['seller_order_status_choices']},
            request=request,
        ),
        'orders_packed': render_to_string(
            'seller_panel/partials/order_board.html',
            {'title': 'Packed Orders', 'seller_order_rows': dashboard_data['seller_packed_order_rows'], 'seller_order_status_choices': dashboard_data['seller_order_status_choices']},
            request=request,
        ),
        'orders_shipped': render_to_string(
            'seller_panel/partials/order_board.html',
            {'title': 'Shipped Orders', 'seller_order_rows': dashboard_data['seller_shipped_order_rows'], 'seller_order_status_choices': dashboard_data['seller_order_status_choices']},
            request=request,
        ),
        'orders_delivered': render_to_string(
            'seller_panel/partials/order_board.html',
            {'title': 'Delivered Orders', 'seller_order_rows': dashboard_data['seller_delivered_order_rows'], 'seller_order_status_choices': dashboard_data['seller_order_status_choices']},
            request=request,
        ),
        'orders_cancelled': render_to_string(
            'seller_panel/partials/order_board.html',
            {'title': 'Cancelled Orders', 'seller_order_rows': dashboard_data['seller_cancelled_order_rows'], 'seller_order_status_choices': dashboard_data['seller_order_status_choices']},
            request=request,
        ),
        'orders_returned': render_to_string(
            'seller_panel/partials/order_board.html',
            {'title': 'Returned Orders', 'seller_order_rows': dashboard_data['seller_returned_order_rows'], 'seller_order_status_choices': dashboard_data['seller_order_status_choices']},
            request=request,
        ),
        'inventory': render_to_string(
            'seller_panel/partials/products_table.html',
            {'products': dashboard_data['seller_products'], 'show_stock_form': True},
            request=request,
        ),
        'payout': render_to_string('seller_panel/partials/data_table.html', {'table': dashboard_data['seller_payout_table']}, request=request),
        'returns': render_to_string('seller_panel/partials/data_table.html', {'table': dashboard_data['seller_returns_table']}, request=request),
        'coupons': render_to_string('seller_panel/partials/data_table.html', {'table': dashboard_data['seller_coupons_table']}, request=request),
        'messages': render_to_string('seller_panel/partials/data_table.html', {'table': dashboard_data['seller_messages_table']}, request=request),
        'ratings': render_to_string('seller_panel/partials/data_table.html', {'table': dashboard_data['seller_ratings_table']}, request=request),
        'shipping': render_to_string('seller_panel/partials/data_table.html', {'table': dashboard_data['seller_shipping_table']}, request=request),
        'notifications': render_to_string('seller_panel/partials/data_table.html', {'table': dashboard_data['seller_notifications_table']}, request=request),
        'support': render_to_string('seller_panel/partials/data_table.html', {'table': dashboard_data['seller_support_table']}, request=request),
        'store_settings': render_to_string('seller_panel/partials/store_settings.html', settings_context, request=request),
        'bank_details': render_to_string('seller_panel/partials/bank_details.html', settings_context, request=request),
        'kyc_documents': render_to_string('seller_panel/partials/kyc_documents.html', settings_context, request=request),
    }


@login_required
def seller_live_dashboard(request):
    if not request.user.is_staff and not _is_seller_user(request.user):
        return JsonResponse({'error': 'Seller access required.'}, status=403)

    dashboard_data = _build_seller_dashboard_data(request.user)
    cards = {
        card['key']: card['value']
        for card in dashboard_data['seller_dashboard_cards']
    }
    return JsonResponse(
        {
            'cards': cards,
            'snapshot': dashboard_data['seller_snapshot'],
            'line_chart': dashboard_data['seller_line_chart'],
            'progress_bars': dashboard_data['seller_progress_bars'],
            'category_bars': dashboard_data['seller_category_bars'],
            'status_lines': dashboard_data['seller_status_lines'],
            'monthly_sales_points': dashboard_data['monthly_sales_points'],
            'fragments': _seller_live_fragments(request, dashboard_data),
            'updated_at': timezone.localtime().strftime('%I:%M %p'),
        }
    )


@login_required
@require_http_methods(['GET', 'POST'])
def seller_product_create(request):
    seller_profile = _get_seller_profile(request.user)
    if not seller_profile and not request.user.is_staff:
        messages.error(request, 'Seller approval is required before adding products.')
        return redirect('become-seller')

    form = SellerProductForm(request.POST or None, request.FILES or None)
    if request.method == 'POST' and form.is_valid():
        product = form.save(commit=False)
        product.owner_type = SpiceItem.OwnerType.SELLER
        product.seller = seller_profile
        product.approval_status = SpiceItem.ApprovalStatus.APPROVED
        product.initial_stock = product.stock
        product.is_active = True
        product.is_featured = False
        product.save()
        form.save_quantity_options(product)
        form.save_gallery_images(product)
        messages.success(request, 'Product added. Product ab store par automatic live hai.')
        return redirect('seller-dashboard')

    if request.method == 'POST':
        messages.error(request, 'Product details check karo. Required fields missing hain.')

    return render(
        request,
        'seller_panel/products/product_form.html',
        {
            **_seller_layout_context(request.user, 'Add Product', 'products'),
            'form': form,
            'product': None,
            'title': 'Add Product',
            'submit_label': 'Post Live Product',
            'back_url': reverse('seller-dashboard'),
        },
    )


@login_required
@require_http_methods(['POST'])
def seller_stock_update(request, pk):
    seller_profile = _get_seller_profile(request.user)
    product = get_object_or_404(
        _seller_product_queryset(seller_profile, include_all_for_admin=request.user.is_staff),
        pk=pk,
    )

    try:
        product.stock = max(0, int(request.POST.get('stock', product.stock)))
    except (TypeError, ValueError):
        messages.error(request, 'Stock quantity valid number hona chahiye.')
        return redirect('seller-dashboard')

    product.save(update_fields=['stock', 'updated_at'])
    messages.success(request, f'{product.name} stock updated to {product.stock}.')
    return redirect('seller-dashboard')


@login_required
def seller_product_preview(request, pk):
    seller_profile = _get_seller_profile(request.user)
    product = get_object_or_404(
        _seller_product_queryset(seller_profile, include_all_for_admin=request.user.is_staff),
        pk=pk,
    )
    return render(
        request,
        'seller_panel/products/product_preview.html',
        {
            **_seller_layout_context(request.user, product.name, 'products'),
            'product': product,
            'gallery_images': product.gallery_images.filter(is_active=True),
            'quantity_options': product.quantity_options.filter(is_active=True),
        },
    )


@login_required
@require_http_methods(['GET', 'POST'])
def seller_product_edit(request, pk):
    seller_profile = _get_seller_profile(request.user)
    product = get_object_or_404(
        _seller_product_queryset(seller_profile, include_all_for_admin=request.user.is_staff),
        pk=pk,
    )
    form = SellerProductForm(request.POST or None, request.FILES or None, instance=product)

    if request.method == 'POST' and form.is_valid():
        updated_product = form.save(commit=False)
        if request.user.is_staff:
            updated_product.owner_type = product.owner_type
            updated_product.seller = product.seller
        else:
            updated_product.owner_type = SpiceItem.OwnerType.SELLER
            updated_product.seller = seller_profile
        if not updated_product.approval_status:
            updated_product.approval_status = SpiceItem.ApprovalStatus.APPROVED
        updated_product.is_active = True
        if updated_product.initial_stock < updated_product.stock:
            updated_product.initial_stock = updated_product.stock
        updated_product.save()
        form.save_quantity_options(updated_product)
        form.save_gallery_images(updated_product)
        messages.success(request, f'{updated_product.name} updated successfully.')
        return redirect('seller-dashboard')

    if request.method == 'POST':
        messages.error(request, 'Product update failed. Required fields check karein.')

    return render(
        request,
        'seller_panel/products/product_form.html',
        {
            **_seller_layout_context(request.user, f'Edit Product: {product.name}', 'products'),
            'form': form,
            'product': product,
            'title': f'Edit Product: {product.name}',
            'submit_label': 'Save Product',
            'back_url': reverse('seller-dashboard'),
        },
    )


@login_required
@require_http_methods(['POST'])
def seller_product_delete(request, pk):
    seller_profile = _get_seller_profile(request.user)
    product = get_object_or_404(
        _seller_product_queryset(seller_profile, include_all_for_admin=request.user.is_staff),
        pk=pk,
    )
    product_name = product.name
    product.delete()
    messages.success(request, f'{product_name} deleted from seller catalog.')
    return redirect('seller-dashboard')


@login_required
@require_http_methods(['POST'])
def seller_settings_update(request, section):
    seller_profile = _get_seller_profile(request.user)
    if not seller_profile:
        messages.error(request, 'Approved seller account required for settings update.')
        return redirect('seller-dashboard')

    forms = {
        'store': SellerStoreProfileForm,
        'bank': SellerBankDetailsForm,
        'documents': SellerDocumentsForm,
    }
    form_class = forms.get(section)
    if not form_class:
        messages.error(request, 'Invalid settings section.')
        return redirect('seller-dashboard')

    form = form_class(request.POST, request.FILES, instance=seller_profile)
    if form.is_valid():
        application = form.save()
        _ensure_seller_user(application)
        labels = {
            'store': 'Store settings',
            'bank': 'Bank details',
            'documents': 'Documents',
        }
        messages.success(request, f'{labels[section]} updated. Admin panel me data sync ho gaya.')
    else:
        messages.error(request, 'Settings update failed. Fields check karein.')
    return redirect('seller-dashboard')


@login_required
@require_http_methods(['POST'])
def seller_profile_photo_update(request):
    if not request.user.is_staff and not _is_seller_user(request.user):
        messages.error(request, 'Seller panel access required.')
        return redirect('become-seller')

    uploaded_photo = request.FILES.get('profile_photo')
    if not uploaded_photo:
        messages.error(request, 'Profile photo select karein.')
        return redirect('seller-dashboard')

    validation_error = _validate_seller_profile_photo(uploaded_photo)
    if validation_error:
        messages.error(request, validation_error)
        return redirect('seller-dashboard')

    seller_profile = _get_seller_profile(request.user)
    if seller_profile:
        seller_profile.profile_photo = uploaded_photo
        seller_profile.save(update_fields=['profile_photo', 'updated_at'])
    else:
        profile, _ = CustomerProfile.objects.get_or_create(user=request.user)
        profile.photo = uploaded_photo
        profile.save(update_fields=['photo', 'updated_at'])
    messages.success(request, 'Profile photo updated.')
    return redirect('seller-dashboard')


@login_required
@require_http_methods(['POST'])
def seller_review_delete(request, pk):
    seller_profile = _get_seller_profile(request.user)
    if not request.user.is_staff and not seller_profile:
        messages.error(request, 'Seller panel access required.')
        return redirect('become-seller')
    reviews = ProductReview.objects.select_related('product', 'product__seller')
    if not request.user.is_staff:
        reviews = reviews.filter(product__seller=seller_profile)
    review = get_object_or_404(reviews, pk=pk)
    review.delete()
    messages.success(request, 'Review deleted from seller table.')
    return redirect('seller-dashboard')


@login_required
@require_http_methods(['POST'])
def seller_return_delete(request, pk):
    accessible_orders = _seller_accessible_order_queryset(request.user)
    return_request = get_object_or_404(ReturnRequest.objects.select_related('order'), pk=pk, order__in=accessible_orders)
    return_request.delete()
    messages.success(request, 'Return request removed from seller table.')
    return redirect('seller-dashboard')


@login_required
@require_http_methods(['POST'])
def seller_coupon_delete(request, pk):
    seller_profile = _get_seller_profile(request.user)
    if not request.user.is_staff and not seller_profile:
        messages.error(request, 'Seller panel access required.')
        return redirect('become-seller')
    coupons = Coupon.objects.all()
    if not request.user.is_staff:
        coupons = coupons.filter(title__icontains=seller_profile.store_name)
    coupon = get_object_or_404(coupons, pk=pk)
    coupon.delete()
    messages.success(request, 'Coupon request deleted.')
    return redirect('seller-dashboard')


@login_required
@require_http_methods(['POST'])
def seller_shipment_delete(request, pk):
    accessible_orders = _seller_accessible_order_queryset(request.user)
    shipment = get_object_or_404(ShipmentTracking.objects.select_related('order'), pk=pk, order__in=accessible_orders)
    shipment.delete()
    messages.success(request, 'Shipment tracking row deleted.')
    return redirect('seller-dashboard')


@login_required
@require_http_methods(['POST'])
def seller_ticket_delete(request, pk):
    seller_profile = _get_seller_profile(request.user)
    if not request.user.is_staff and not seller_profile:
        messages.error(request, 'Seller panel access required.')
        return redirect('become-seller')
    tickets = SupportTicket.objects.filter(ticket_type=SupportTicket.TicketType.SELLER)
    if not request.user.is_staff:
        tickets = tickets.filter(seller=seller_profile)
    ticket = get_object_or_404(tickets, pk=pk)
    ticket.delete()
    messages.success(request, 'Seller ticket deleted.')
    return redirect('seller-dashboard')


@login_required
def seller_order_invoice(request, pk):
    if not request.user.is_staff and not _is_seller_user(request.user):
        messages.error(request, 'Seller panel access required.')
        return redirect('become-seller')
    order = get_object_or_404(
        _seller_accessible_order_queryset(request.user).prefetch_related('items'),
        pk=pk,
    )
    return render(
        request,
        'seller_panel/orders/order_invoice.html',
        {
            **_seller_layout_context(request.user, f'Invoice {order.order_number}', 'orders'),
            'order': order,
        },
    )


def _sync_order_status_from_items(order):
    items = list(order.items.all())
    statuses = [item.item_status for item in items]
    if not statuses:
        return
    active_statuses = [status for status in statuses if status not in {Order.Status.CANCELLED, Order.Status.RETURNED}]
    if not active_statuses:
        order.status = Order.Status.CANCELLED
    elif all(status == Order.Status.DELIVERED for status in active_statuses):
        order.status = Order.Status.DELIVERED
    else:
        flow_indexes = [ORDER_STATUS_FLOW.index(status) for status in active_statuses if status in ORDER_STATUS_FLOW]
        if flow_indexes:
            order.status = ORDER_STATUS_FLOW[min(flow_indexes)]
    order.save(update_fields=['status', 'updated_at'])


def _seller_filtered_order_items(request):
    items, seller_profile = _seller_order_items_for_user(request.user)
    query = request.GET.get('q', '').strip()
    status = request.GET.get('status', '').strip()
    if query:
        items = items.filter(
            Q(order__order_number__icontains=query)
            | Q(order__order_id__icontains=query)
            | Q(order__customer_name__icontains=query)
            | Q(order__customer_phone__icontains=query)
            | Q(product_name__icontains=query)
        )
    if status:
        items = items.filter(item_status=status)
    return items, seller_profile


@login_required
def seller_orders(request):
    if not request.user.is_staff and not _is_seller_user(request.user):
        messages.error(request, 'Seller panel access required.')
        return redirect('become-seller')
    items, seller_profile = _seller_filtered_order_items(request)
    order_ids = items.values_list('order_id', flat=True).distinct()
    today = timezone.localdate()
    delivered_revenue = items.filter(item_status=Order.Status.DELIVERED).aggregate(total=Sum('line_total')).get('total') or Decimal('0')
    summary = {
        'new': items.filter(item_status=Order.Status.PENDING).count(),
        'pending': items.filter(item_status=Order.Status.PENDING).count(),
        'packed': items.filter(item_status=Order.Status.PACKED).count(),
        'shipped': items.filter(item_status__in=[Order.Status.SHIPPED, Order.Status.OUT_FOR_DELIVERY]).count(),
        'delivered': items.filter(item_status=Order.Status.DELIVERED).count(),
        'cancelled': items.filter(item_status=Order.Status.CANCELLED).count(),
        'today': items.filter(order__created_at__date=today).count(),
        'revenue': delivered_revenue,
        'unseen': items.filter(is_seen_by_seller=False).count(),
        'orders': order_ids.count(),
    }
    paginator = Paginator(items, 30)
    page_obj = paginator.get_page(request.GET.get('page'))
    return render(
        request,
        'seller_panel/orders/seller_orders.html',
        {
            **_seller_layout_context(request.user, 'Orders', 'orders'),
            'seller_profile': seller_profile,
            'order_items': page_obj.object_list,
            'page_obj': page_obj,
            'summary': summary,
            'status_choices': Order.Status.choices,
            'filters': request.GET,
        },
    )


@login_required
def seller_order_detail(request, order_id):
    if not request.user.is_staff and not _is_seller_user(request.user):
        messages.error(request, 'Seller panel access required.')
        return redirect('become-seller')
    order = get_object_or_404(_seller_accessible_order_queryset(request.user), _order_lookup_filter(order_id))
    seller_profile = _get_seller_profile(request.user)
    items = order.items.all() if request.user.is_staff else order.items.filter(seller=seller_profile)
    items.update(is_seen_by_seller=True)
    if not order.is_seen_by_seller:
        order.is_seen_by_seller = True
        order.save(update_fields=['is_seen_by_seller', 'updated_at'])
    return render(
        request,
        'seller_panel/orders/seller_order_detail.html',
        {
            **_seller_layout_context(request.user, f'Order {order.order_number}', 'orders'),
            'order': order,
            'order_items': items.select_related('seller', 'product', 'quantity_option'),
            'shipments': order.shipments.select_related('courier').all(),
            'timeline_steps': _order_timeline(order),
            'status_choices': Order.Status.choices,
            'customer_whatsapp': ''.join(ch for ch in order.customer_phone if ch.isdigit()),
        },
    )


@login_required
@require_http_methods(['POST'])
def seller_order_status_update_by_order_id(request, order_id):
    if not request.user.is_staff and not _is_seller_user(request.user):
        messages.error(request, 'Seller panel access required.')
        return redirect('become-seller')
    order = get_object_or_404(_seller_accessible_order_queryset(request.user), _order_lookup_filter(order_id))
    seller_profile = _get_seller_profile(request.user)
    status = request.POST.get('status', '').strip()
    note = request.POST.get('note', '').strip()
    valid_statuses = {Order.Status.CONFIRMED, Order.Status.PACKED, Order.Status.SHIPPED, Order.Status.CANCELLED}
    if request.user.is_staff:
        valid_statuses = {choice[0] for choice in Order.Status.choices}
    if status not in valid_statuses:
        messages.error(request, 'Invalid seller order status.')
        return redirect('seller-order-detail', order_id=order.order_number)

    with transaction.atomic():
        locked_order = Order.objects.select_for_update().prefetch_related('items').get(pk=order.pk)
        items = locked_order.items.select_related('product', 'quantity_option')
        if not request.user.is_staff:
            items = items.filter(seller=seller_profile)
        item_list = list(items)
        if status == Order.Status.CANCELLED:
            cancellable = [item for item in item_list if item.item_status not in {Order.Status.CANCELLED, Order.Status.SHIPPED, Order.Status.OUT_FOR_DELIVERY, Order.Status.DELIVERED}]
            _restore_stock_for_items(cancellable)
            for item in cancellable:
                item.item_status = status
                item.seller_note = note[:240]
                item.save(update_fields=['item_status', 'seller_note', 'updated_at'])
                _record_order_status(locked_order, status, request.user, note or 'Seller cancelled item', item)
        else:
            for item in item_list:
                item.item_status = status
                item.seller_note = note[:240]
                item.save(update_fields=['item_status', 'seller_note', 'updated_at'])
                _record_order_status(locked_order, status, request.user, note or 'Seller status update', item)
        _sync_order_status_from_items(locked_order)
        OrderNotification.objects.create(
            audience=OrderNotification.Audience.ADMIN,
            notification_type=OrderNotification.Type.STATUS_UPDATED,
            order=locked_order,
            title=f'Seller updated {locked_order.order_number}',
            message=f'Seller marked item(s) as {dict(Order.Status.choices).get(status)}.',
        )
    messages.success(request, f'Order {order.order_number} updated.')
    return redirect(request.POST.get('next') or reverse('seller-order-detail', kwargs={'order_id': order.order_number}))


@login_required
def seller_order_notifications(request):
    notifications = _seller_order_notification_queryset(request.user)
    seller_profile = _get_seller_profile(request.user)
    read_id = request.GET.get('read_id') or request.GET.get('notification_id')
    if read_id and str(read_id).isdigit():
        selected = notifications.filter(pk=read_id).select_related('order', 'order_item').first()
        if selected:
            selected.is_read = True
            selected.save(update_fields=['is_read', 'updated_at'])
            if selected.order_item_id:
                OrderItem.objects.filter(pk=selected.order_item_id).update(is_seen_by_seller=True)
            elif seller_profile:
                selected.order.items.filter(seller=seller_profile).update(is_seen_by_seller=True)
    if request.GET.get('mark_read') == '1':
        notifications.filter(is_read=False).update(is_read=True)
        if seller_profile:
            OrderItem.objects.filter(seller=seller_profile, is_seen_by_seller=False).update(is_seen_by_seller=True)
    unread_notifications = notifications.filter(is_read=False).select_related('order', 'order_item')
    return JsonResponse(
        {
            'unread_count': notifications.filter(is_read=False).count(),
            'notifications': [
                _order_notification_payload(notification, OrderNotification.Audience.SELLER)
                for notification in unread_notifications[:12]
            ],
        }
    )


@login_required
@require_http_methods(['POST'])
def seller_order_status_update(request, pk):
    if not request.user.is_staff and not _is_seller_user(request.user):
        messages.error(request, 'Seller panel access required.')
        return redirect('become-seller')

    order = get_object_or_404(_seller_accessible_order_queryset(request.user), pk=pk)
    status = request.POST.get('status', '').strip()
    valid_statuses = {choice[0] for choice in Order.Status.choices}
    if status not in valid_statuses:
        messages.error(request, 'Invalid order status.')
        return redirect(request.POST.get('next') or 'seller-dashboard')

    _set_order_status(order, status, request.user, 'Seller dashboard status update')
    messages.success(request, f'Order {order.order_number} updated to {order.get_status_display()}.')
    return redirect(request.POST.get('next') or 'seller-dashboard')


@login_required
@require_http_methods(['POST'])
def seller_payout_request(request):
    seller_profile = _get_seller_profile(request.user)
    if not seller_profile:
        messages.error(request, 'Approved seller account required for payout request.')
        return redirect('seller-dashboard')

    try:
        amount = Decimal(request.POST.get('amount', '0'))
    except Exception:
        amount = Decimal('0')
    if amount < Decimal('500'):
        messages.error(request, 'Minimum payout request Rs. 500 hai.')
        return redirect('seller-dashboard')

    bank_account = request.POST.get('bank_account', '').strip() or seller_profile.bank_account_number or 'Primary bank account'
    upi_id = request.POST.get('upi_id', '').strip()
    remarks = request.POST.get('remarks', '').strip()
    SellerPayout.objects.create(
        seller=seller_profile,
        requested_by=request.user,
        amount=amount,
        bank_account=bank_account,
        upi_id=upi_id,
        remarks=remarks,
        status=SellerPayout.Status.PENDING,
    )
    SupportTicket.objects.create(
        ticket_type=SupportTicket.TicketType.SELLER,
        seller=seller_profile,
        subject=f'Payout request: {_format_currency(amount)}',
        message=f'Bank account: {bank_account}\nUPI ID: {upi_id or "Not provided"}\nRemarks: {remarks or "No remarks"}',
    )
    messages.success(request, 'Payout request admin panel me submit ho gaya.')
    return redirect('seller-dashboard')


@login_required
@require_http_methods(['POST'])
def seller_coupon_create(request):
    seller_profile = _get_seller_profile(request.user)
    if not seller_profile and not request.user.is_staff:
        messages.error(request, 'Approved seller account required for coupon request.')
        return redirect('seller-dashboard')

    code = request.POST.get('code', '').strip().upper()
    discount_type = request.POST.get('discount_type', Coupon.DiscountType.PERCENT)
    try:
        discount_value = Decimal(request.POST.get('discount_value', '0'))
    except Exception:
        discount_value = Decimal('0')

    if not code or discount_type not in {choice[0] for choice in Coupon.DiscountType.choices} or discount_value <= 0:
        messages.error(request, 'Coupon code, type, aur discount value valid hona chahiye.')
        return redirect('seller-dashboard')
    if Coupon.objects.filter(code__iexact=code).exists():
        messages.error(request, 'Ye coupon code already exist karta hai.')
        return redirect('seller-dashboard')

    def to_datetime(field_name):
        raw_value = request.POST.get(field_name, '').strip()
        parsed = parse_date(raw_value)
        if not parsed:
            return None
        return timezone.make_aware(timezone.datetime.combine(parsed, timezone.datetime.min.time()))

    store_name = seller_profile.store_name if seller_profile else 'Staff seller preview'
    Coupon.objects.create(
        code=code,
        title=f'{store_name} seller offer',
        discount_type=discount_type,
        discount_value=discount_value,
        owner_type=Coupon.OwnerType.SELLER,
        seller=seller_profile,
        approval_status=Coupon.ApprovalStatus.PENDING,
        starts_at=to_datetime('starts_at'),
        ends_at=to_datetime('ends_at'),
        is_active=False,
    )
    messages.success(request, 'Coupon admin approval ke liye submit ho gaya.')
    return redirect('seller-dashboard')


@login_required
@require_http_methods(['POST'])
def seller_shipping_update(request):
    if not request.user.is_staff and not _is_seller_user(request.user):
        messages.error(request, 'Seller panel access required.')
        return redirect('become-seller')

    order = get_object_or_404(_seller_accessible_order_queryset(request.user), pk=request.POST.get('order_id'))
    courier_name = request.POST.get('courier_name', '').strip()
    courier = None
    if courier_name:
        courier, _ = CourierPartner.objects.get_or_create(name=courier_name, defaults={'is_active': True})

    tracking, _ = ShipmentTracking.objects.get_or_create(order=order)
    status = request.POST.get('status', '').strip() or ShipmentTracking.Status.SHIPPED
    if status not in {choice[0] for choice in ShipmentTracking.Status.choices}:
        messages.error(request, 'Invalid shipment status.')
        return redirect('seller-dashboard')
    tracking.courier = courier
    tracking.tracking_number = request.POST.get('tracking_number', '').strip()
    tracking.status = status
    tracking.last_location = request.POST.get('last_location', '').strip()
    tracking.save()
    _sync_tracking_order_status(tracking, request.user)

    messages.success(request, f'Shipping tracking {order.order_number} ke liye save ho gaya.')
    return redirect('seller-dashboard')


@login_required
@require_http_methods(['POST'])
def seller_support_create(request):
    seller_profile = _get_seller_profile(request.user)
    if not seller_profile:
        messages.error(request, 'Approved seller account required for support ticket.')
        return redirect('seller-dashboard')

    subject = request.POST.get('subject', '').strip()
    message = request.POST.get('message', '').strip()
    if not subject or not message:
        messages.error(request, 'Support ticket ke liye subject aur message required hai.')
        return redirect('seller-dashboard')

    SupportTicket.objects.create(
        ticket_type=SupportTicket.TicketType.SELLER,
        seller=seller_profile,
        subject=subject,
        message=message,
    )
    messages.success(request, 'Support ticket admin panel me create ho gaya.')
    return redirect('seller-dashboard')


def _format_currency(value):
    amount = value or 0
    formatted = f'{amount:,.2f}'
    if formatted.endswith('.00'):
        formatted = formatted[:-3]
    return f'Rs. {formatted}'


def _card(theme, icon, label, value):
    return {
        'theme': theme,
        'icon': icon,
        'label': label,
        'value': value,
    }


def _cell(value, tone=''):
    return {
        'value': value,
        'tone': tone,
    }


def _safe_file_url(file_field):
    try:
        if file_field and getattr(file_field, 'name', ''):
            return file_field.url
    except (OSError, ValueError):
        return ''
    return ''


def _initial_from(*values, fallback='U'):
    for value in values:
        text = str(value or '').strip()
        if text:
            return text[:1].upper()
    return fallback


def _avatar_cell(image_url, initial, label=''):
    return {
        'kind': 'avatar',
        'avatar_url': image_url or '',
        'initial': initial or 'U',
        'value': label or initial or 'U',
    }


def _customer_photo_url(user):
    try:
        profile = user.customer_profile
    except CustomerProfile.DoesNotExist:
        return ''
    return _safe_file_url(profile.photo)


def _customer_phone(user):
    try:
        profile = user.customer_profile
    except CustomerProfile.DoesNotExist:
        return ''
    return profile.phone or ''


def _seller_photo_url(seller):
    return _safe_file_url(seller.profile_photo) or _safe_file_url(seller.store_logo)


def _insight(title, text, meta=''):
    return {
        'title': title,
        'text': text,
        'meta': meta,
    }


def _action(label, href, style='ghost', method='get', modal=None):
    href_text = str(href)
    use_modal = modal
    if use_modal is None and method == 'get':
        use_modal = style == 'edit' or (
            style == 'primary' and ('/new/' in href_text or href_text.rstrip('/').endswith('/new'))
        )
    return {
        'label': label,
        'href': href,
        'style': style,
        'method': method,
        'modal': bool(use_modal),
    }


def _render_admin_form_page(request, nav_group, section, **extra):
    context = _admin_context(nav_group, section, **extra)
    is_ajax = request.headers.get('X-Requested-With') == 'XMLHttpRequest'
    is_partial = request.GET.get('partial') == 'form' or (is_ajax and request.method == 'POST')
    template = (
        'admin_panel/partials/form_modal_body.html'
        if is_partial
        else 'admin_panel/form_page.html'
    )
    return render(request, template, context)


def _admin_nav(snapshot):
    customer_count = User.objects.filter(is_staff=False).count()
    seller_count = SellerApplication.objects.count()
    alert_count = snapshot['low_stock_count'] + snapshot['out_stock_count']

    return {
        'products': snapshot['item_count'],
        'categories': snapshot['category_count'],
        'collections': snapshot['active_category_count'],
        'banners': snapshot['active_banner_count'],
        'orders': snapshot['order_count'],
        'returns': Order.objects.filter(status=Order.Status.RETURNED).count(),
        'shipping': Order.objects.filter(status__in=[Order.Status.PACKED, Order.Status.SHIPPED]).count() or alert_count,
        'customers': customer_count,
        'sellers': seller_count,
        'inventory': alert_count,
        'website': snapshot['active_banner_count'],
    }


def _section_url(module, section):
    return reverse('admin-section', kwargs={'module': module, 'section': section})


GENERIC_ADMIN_MODELS = {
    'coupon': {'model': Coupon, 'form': CouponForm, 'nav_group': 'coupon-offer-management', 'section': 'admin-coupons', 'label': 'Coupon'},
    'offer': {'model': Offer, 'form': OfferForm, 'nav_group': 'coupon-offer-management', 'section': 'flash-sales', 'label': 'Flash Sale'},
    'shipping-charge': {'model': ShippingCharge, 'form': ShippingChargeForm, 'nav_group': 'shipping-management', 'section': 'shipping-charges', 'label': 'Shipping Charge'},
    'courier-partner': {'model': CourierPartner, 'form': CourierPartnerForm, 'nav_group': 'shipping-management', 'section': 'courier-partners', 'label': 'Courier Partner'},
    'delivery-area': {'model': DeliveryArea, 'form': DeliveryAreaForm, 'nav_group': 'shipping-management', 'section': 'delivery-areas', 'label': 'Delivery Area'},
    'shipment-tracking': {'model': ShipmentTracking, 'form': ShipmentTrackingForm, 'nav_group': 'shipping-management', 'section': 'tracking-management', 'label': 'Tracking'},
    'review': {'model': ProductReview, 'form': ProductReviewForm, 'nav_group': 'reviews-ratings', 'section': 'product-reviews', 'label': 'Product Review'},
    'seller-review': {'model': SellerReview, 'form': SellerReviewForm, 'nav_group': 'reviews-ratings', 'section': 'seller-reviews', 'label': 'Seller Review'},
    'review-report': {'model': ReviewReport, 'form': ReviewReportForm, 'nav_group': 'reviews-ratings', 'section': 'reported-reviews', 'label': 'Review Report'},
    'ticket': {'model': SupportTicket, 'nav_group': 'support-tickets', 'section': 'customer-tickets', 'label': 'Ticket'},
    'content': {'model': StaticContent, 'nav_group': 'content-management', 'section': 'about-us', 'label': 'Content'},
    'notification': {'model': NotificationTemplate, 'form': NotificationTemplateForm, 'nav_group': 'notification-management', 'section': 'email-templates', 'label': 'Notification Template'},
    'push-notification': {'model': PushNotification, 'form': PushNotificationForm, 'nav_group': 'notification-management', 'section': 'push-notifications', 'label': 'Push Notification'},
    'website-setting': {'model': WebsiteSetting, 'nav_group': 'website-settings', 'section': 'general-settings', 'label': 'Website Setting'},
    'return-request': {'model': ReturnRequest, 'form': ReturnRequestForm, 'nav_group': 'return-refund-management', 'section': 'return-requests', 'label': 'Return Request'},
    'payment-transaction': {'model': PaymentTransaction, 'nav_group': 'payment-management', 'section': 'all-payments', 'label': 'Payment Transaction'},
    'seller-payout': {'model': SellerPayout, 'form': SellerPayoutForm, 'nav_group': 'payout-management', 'section': 'payout-requests', 'label': 'Seller Payout'},
}


def _generic_config(model_key):
    try:
        return GENERIC_ADMIN_MODELS[model_key]
    except KeyError:
        raise Http404('Admin model not found.')


def _generic_back_href(config):
    return _section_url(config['nav_group'], config['section'])


def _generic_form_class(model_class):
    exclude = ['created_at', 'updated_at']
    return modelform_factory(model_class, exclude=exclude)


def _generic_form_for_config(config):
    return config.get('form') or _generic_form_class(config['model'])


def _sidebar_child(label, module, section, icon='fas fa-circle', badge=None, href=None):
    return {
        'label': label,
        'module': module,
        'section': section,
        'icon': icon,
        'badge': badge,
        'href': href or _section_url(module, section),
    }


def _sidebar_group(label, key, icon, subtitle, children=None, href=None, badge=None):
    return {
        'label': label,
        'key': key,
        'icon': icon,
        'subtitle': subtitle,
        'children': children or [],
        'href': href,
        'badge': badge,
    }


def _build_admin_sidebar(snapshot):
    pending_sellers = SellerApplication.objects.filter(status=SellerApplication.Status.PENDING).count()
    approved_sellers = SellerApplication.objects.filter(status=SellerApplication.Status.APPROVED).count()
    rejected_sellers = SellerApplication.objects.filter(status=SellerApplication.Status.REJECTED).count()
    blocked_sellers = SellerApplication.objects.filter(status=SellerApplication.Status.BLOCKED).count()
    customer_count = User.objects.filter(is_staff=False).count()
    stock_alerts = snapshot['low_stock_count'] + snapshot['out_stock_count']
    pending_orders = Order.objects.filter(status=Order.Status.PENDING).count()
    confirmed_orders = Order.objects.filter(status=Order.Status.CONFIRMED).count()
    packed_orders = Order.objects.filter(status=Order.Status.PACKED).count()
    shipped_orders = Order.objects.filter(status=Order.Status.SHIPPED).count()
    delivered_orders = Order.objects.filter(status=Order.Status.DELIVERED).count()
    cancelled_orders = Order.objects.filter(status=Order.Status.CANCELLED).count()
    returned_orders = Order.objects.filter(status=Order.Status.RETURNED).count()
    pending_returns = ReturnRequest.objects.filter(status=ReturnRequest.Status.PENDING).count()
    refund_requests = ReturnRequest.objects.filter(refund_status__in=[ReturnRequest.RefundStatus.REQUESTED, ReturnRequest.RefundStatus.PROCESSING]).count()
    shipping_rules = ShippingCharge.objects.filter(is_active=True).count()
    courier_partners = CourierPartner.objects.filter(is_active=True).count()
    serviceable_areas = DeliveryArea.objects.filter(is_active=True, is_serviceable=True).count()
    tracking_records = ShipmentTracking.objects.count()
    product_review_pending = ProductReview.objects.filter(status=ProductReview.Status.PENDING).count()
    seller_review_pending = SellerReview.objects.filter(status=SellerReview.Status.PENDING).count()
    reported_review_pending = ReviewReport.objects.filter(status=ReviewReport.Status.PENDING).count()
    active_coupons = Coupon.objects.filter(is_active=True, approval_status=Coupon.ApprovalStatus.APPROVED).count()
    pending_seller_coupons = Coupon.objects.filter(owner_type=Coupon.OwnerType.SELLER, approval_status=Coupon.ApprovalStatus.PENDING).count()
    flash_sales = Offer.objects.filter(is_active=True).count()
    push_notifications = PushNotification.objects.filter(status=PushNotification.Status.SENT).count()
    email_templates = NotificationTemplate.objects.filter(template_type=NotificationTemplate.TemplateType.EMAIL, is_active=True).count()
    sms_templates = NotificationTemplate.objects.filter(template_type=NotificationTemplate.TemplateType.SMS, is_active=True).count()

    return [
        _sidebar_group('Dashboard', 'dashboard', 'fas fa-gauge-high', 'Complete overview', href=reverse('admin-dashboard')),
        _sidebar_group(
            'User Management',
            'user-management',
            'fas fa-users-gear',
            'Customers and sellers',
            [
                _sidebar_child('Customers', 'user-management', 'customers', 'fas fa-user-group', customer_count, reverse('admin-customers')),
                _sidebar_child('Sellers', 'user-management', 'sellers', 'fas fa-store', approved_sellers, reverse('admin-sellers')),
            ],
        ),
        _sidebar_group(
            'Seller Management',
            'seller-management',
            'fas fa-shop-lock',
            'Requests, KYC, blocked status',
            [
                _sidebar_child('Seller Requests', 'seller-management', 'seller-requests', 'fas fa-hourglass-half', pending_sellers),
                _sidebar_child('Rejected Sellers', 'seller-management', 'rejected-sellers', 'fas fa-circle-xmark', rejected_sellers),
                _sidebar_child('Blocked Sellers', 'seller-management', 'blocked-sellers', 'fas fa-ban', blocked_sellers),
            ],
        ),
        _sidebar_group(
            'Category Management',
            'category-management',
            'fas fa-tags',
            'Categories and structure',
            [
                _sidebar_child('Categories', 'category-management', 'categories', 'fas fa-tags', snapshot['category_count'], reverse('admin-categories')),
                _sidebar_child('Sub Categories', 'category-management', 'sub-categories', 'fas fa-sitemap', snapshot['sub_category_count'], reverse('admin-subcategories')),
            ],
        ),
        _sidebar_group(
            'Product Management',
            'product-management',
            'fas fa-boxes-stacked',
            'Approvals and reviews',
            [
                _sidebar_child('All Products', 'product-management', 'all-products', 'fas fa-box-open', snapshot['item_count'], reverse('admin-items')),
                _sidebar_child('Featured Products', 'product-management', 'featured-products', 'fas fa-star', snapshot['featured_item_count']),
                _sidebar_child('Out of Stock Products', 'product-management', 'out-of-stock-products', 'fas fa-boxes-packing', snapshot['out_stock_count']),
                _sidebar_child('Product Reviews', 'product-management', 'product-reviews', 'fas fa-star-half-stroke'),
            ],
        ),
        _sidebar_group(
            'Order Management',
            'order-management',
            'fas fa-bag-shopping',
            'Order status flow',
            [
                _sidebar_child('All Orders', 'order-management', 'all-orders', 'fas fa-receipt', snapshot['order_count'], reverse('admin-orders')),
                _sidebar_child('Pending Orders', 'order-management', 'pending-orders', 'fas fa-hourglass-start', pending_orders),
                _sidebar_child('Confirmed Orders', 'order-management', 'confirmed-orders', 'fas fa-clipboard-check', confirmed_orders),
                _sidebar_child('Packed Orders', 'order-management', 'packed-orders', 'fas fa-box', packed_orders),
                _sidebar_child('Shipped Orders', 'order-management', 'shipped-orders', 'fas fa-truck-fast', shipped_orders),
                _sidebar_child('Delivered Orders', 'order-management', 'delivered-orders', 'fas fa-house-circle-check', delivered_orders),
                _sidebar_child('Cancelled Orders', 'order-management', 'cancelled-orders', 'fas fa-ban', cancelled_orders),
                _sidebar_child('Returned Orders', 'order-management', 'returned-orders', 'fas fa-arrow-rotate-left', returned_orders),
            ],
        ),
        _sidebar_group(
            'Payment Management',
            'payment-management',
            'fas fa-credit-card',
            'Payments and refunds',
            [
                _sidebar_child('All Payments', 'payment-management', 'all-payments', 'fas fa-wallet'),
                _sidebar_child('Successful Payments', 'payment-management', 'successful-payments', 'fas fa-circle-check'),
                _sidebar_child('Failed Payments', 'payment-management', 'failed-payments', 'fas fa-triangle-exclamation'),
                _sidebar_child('Refund Payments', 'payment-management', 'refund-payments', 'fas fa-money-bill-transfer'),
            ],
        ),
        _sidebar_group(
            'Payout Management',
            'payout-management',
            'fas fa-sack-dollar',
            'Seller earnings',
            [
                _sidebar_child('Seller Earnings', 'payout-management', 'seller-earnings', 'fas fa-chart-line'),
                _sidebar_child('Payout Requests', 'payout-management', 'payout-requests', 'fas fa-hand-holding-dollar'),
                _sidebar_child('Approved Payouts', 'payout-management', 'approved-payouts', 'fas fa-circle-check'),
                _sidebar_child('Paid Payouts', 'payout-management', 'paid-payouts', 'fas fa-money-check-dollar'),
                _sidebar_child('Rejected Payouts', 'payout-management', 'rejected-payouts', 'fas fa-circle-xmark'),
            ],
        ),
        _sidebar_group(
            'Return & Refund',
            'return-refund-management',
            'fas fa-rotate-left',
            'Returns and refund control',
            [
                _sidebar_child('Return Requests', 'return-refund-management', 'return-requests', 'fas fa-box-open', pending_returns, reverse('admin-returns')),
                _sidebar_child('Refund Requests', 'return-refund-management', 'refund-requests', 'fas fa-money-bill-wave', refund_requests),
                _sidebar_child('Approved Returns', 'return-refund-management', 'approved-returns', 'fas fa-circle-check', ReturnRequest.objects.filter(status=ReturnRequest.Status.APPROVED).count()),
                _sidebar_child('Rejected Returns', 'return-refund-management', 'rejected-returns', 'fas fa-circle-xmark', ReturnRequest.objects.filter(status=ReturnRequest.Status.REJECTED).count()),
            ],
        ),
        _sidebar_group(
            'Coupon / Offer',
            'coupon-offer-management',
            'fas fa-tags',
            'Coupons and banners',
            [
                _sidebar_child('Admin Coupons', 'coupon-offer-management', 'admin-coupons', 'fas fa-ticket', active_coupons),
                _sidebar_child('Seller Coupons', 'coupon-offer-management', 'seller-coupons', 'fas fa-store', pending_seller_coupons),
                _sidebar_child('Flash Sales', 'coupon-offer-management', 'flash-sales', 'fas fa-bolt', flash_sales),
                _sidebar_child('Banners', 'coupon-offer-management', 'banners', 'fas fa-images', snapshot['banner_count'], reverse('admin-banners')),
            ],
        ),
        _sidebar_group(
            'Shipping Management',
            'shipping-management',
            'fas fa-truck-fast',
            'Courier and delivery',
            [
                _sidebar_child('Shipping Charges', 'shipping-management', 'shipping-charges', 'fas fa-indian-rupee-sign', shipping_rules),
                _sidebar_child('Courier Partners', 'shipping-management', 'courier-partners', 'fas fa-truck', courier_partners),
                _sidebar_child('Delivery Areas', 'shipping-management', 'delivery-areas', 'fas fa-map-location-dot', serviceable_areas),
                _sidebar_child('Tracking Management', 'shipping-management', 'tracking-management', 'fas fa-route', tracking_records),
            ],
        ),
        _sidebar_group(
            'Inventory Management',
            'inventory-management',
            'fas fa-warehouse',
            'Stock reports',
            [
                _sidebar_child('Stock Report', 'inventory-management', 'stock-report', 'fas fa-chart-simple', snapshot['total_stock'], reverse('admin-report-inventory')),
                _sidebar_child('Low Stock Products', 'inventory-management', 'low-stock-products', 'fas fa-triangle-exclamation', snapshot['low_stock_count']),
                _sidebar_child('Out of Stock Products', 'inventory-management', 'out-of-stock-products', 'fas fa-boxes-packing', snapshot['out_stock_count']),
            ],
        ),
        _sidebar_group(
            'Reviews & Ratings',
            'reviews-ratings',
            'fas fa-star-half-stroke',
            'Moderation',
            [
                _sidebar_child('Product Reviews', 'reviews-ratings', 'product-reviews', 'fas fa-star', product_review_pending),
                _sidebar_child('Seller Reviews', 'reviews-ratings', 'seller-reviews', 'fas fa-store', seller_review_pending),
                _sidebar_child('Reported Reviews', 'reviews-ratings', 'reported-reviews', 'fas fa-flag', reported_review_pending),
            ],
        ),
        _sidebar_group(
            'Support / Tickets',
            'support-tickets',
            'fas fa-headset',
            'Help desk',
            [
                _sidebar_child('Customer Tickets', 'support-tickets', 'customer-tickets', 'fas fa-user-headset'),
                _sidebar_child('Seller Tickets', 'support-tickets', 'seller-tickets', 'fas fa-store'),
                _sidebar_child('Complaints', 'support-tickets', 'complaints', 'fas fa-triangle-exclamation'),
            ],
        ),
        _sidebar_group(
            'Content Management',
            'content-management',
            'fas fa-file-pen',
            'Static website content',
            [
                _sidebar_child('Home Banners', 'content-management', 'home-banners', 'fas fa-images', snapshot['banner_count'], reverse('admin-website-edit')),
                _sidebar_child('About Us', 'content-management', 'about-us', 'fas fa-circle-info'),
                _sidebar_child('Terms & Conditions', 'content-management', 'terms-conditions', 'fas fa-file-contract'),
                _sidebar_child('Privacy Policy', 'content-management', 'privacy-policy', 'fas fa-user-shield'),
                _sidebar_child('Return Policy', 'content-management', 'return-policy', 'fas fa-arrow-rotate-left'),
                _sidebar_child('FAQ', 'content-management', 'faq', 'fas fa-circle-question'),
            ],
        ),
        _sidebar_group(
            'Reports & Analytics',
            'reports-analytics',
            'fas fa-chart-pie',
            'Business reports',
            [
                _sidebar_child('Revenue Reports', 'reports-analytics', 'revenue-reports', 'fas fa-chart-line'),
                _sidebar_child('Order Reports', 'reports-analytics', 'order-reports', 'fas fa-receipt'),
                _sidebar_child('Seller Reports', 'reports-analytics', 'seller-reports', 'fas fa-store'),
                _sidebar_child('Customer Reports', 'reports-analytics', 'customer-reports', 'fas fa-users'),
                _sidebar_child('Product Reports', 'reports-analytics', 'product-reports', 'fas fa-box-open'),
                _sidebar_child('Commission Report', 'reports-analytics', 'commission-report', 'fas fa-percent'),
                _sidebar_child('Payout Report', 'reports-analytics', 'payout-report', 'fas fa-sack-dollar'),
                _sidebar_child('Refund Report', 'reports-analytics', 'refund-report', 'fas fa-money-bill-transfer'),
            ],
        ),
        _sidebar_group(
            'Notification Management',
            'notification-management',
            'fas fa-bell',
            'Messages and templates',
            [
                _sidebar_child('Push Notifications', 'notification-management', 'push-notifications', 'fas fa-paper-plane', push_notifications),
                _sidebar_child('Email Templates', 'notification-management', 'email-templates', 'fas fa-envelope', email_templates),
                _sidebar_child('SMS Templates', 'notification-management', 'sms-templates', 'fas fa-message', sms_templates),
            ],
        ),
        _sidebar_group('Account Settings', 'account-settings', 'fas fa-user-gear', 'Admin profile', href=reverse('admin-settings')),
    ]


def _admin_context(nav_group, section, snapshot=None, **extra):
    snapshot = snapshot or _admin_snapshot()
    context = {
        'nav_group': nav_group,
        'section': section,
        'admin_nav': _admin_nav(snapshot),
        'admin_sidebar': _build_admin_sidebar(snapshot),
        'admin_profile': extra.get('admin_profile'),
        **snapshot,
    }
    context.update(extra)
    return context


def _category_breakdown_queryset():
    return Category.objects.annotate(
        total_products=Count('items', distinct=True),
        active_products=Count('items', filter=Q(items__is_active=True), distinct=True),
        seller_products=Count('items', filter=Q(items__owner_type=SpiceItem.OwnerType.SELLER), distinct=True),
        seller_total=Count('items__seller', filter=Q(items__seller__isnull=False), distinct=True),
        admin_products=Count('items', filter=Q(items__owner_type=SpiceItem.OwnerType.ADMIN), distinct=True),
        total_orders=Count('items__order_items__order', distinct=True),
        sub_category_total=Count('sub_categories', distinct=True),
        brand_total=Count('items__brand_name', filter=~Q(items__brand_name=''), distinct=True),
        total_stock=Sum('items__stock'),
        initial_stock=Sum('items__initial_stock'),
    ).order_by('display_order', 'name')


def _cell_value(cell):
    return str(cell.get('value', '') if isinstance(cell, dict) else cell)


def _query_url(request, **updates):
    params = request.GET.copy()
    for key, value in updates.items():
        if value is None:
            params.pop(key, None)
        else:
            params[key] = value
    encoded = params.urlencode()
    return f'{request.path}?{encoded}' if encoded else request.path


def _table_export_response(filename, headers, rows, export_format):
    response = HttpResponse(content_type='text/csv; charset=utf-8')
    extension = 'csv'
    delimiter = ','
    if export_format == 'excel':
        response = HttpResponse(content_type='application/vnd.ms-excel; charset=utf-8')
        extension = 'xls'
        delimiter = '\t'
    response['Content-Disposition'] = f'attachment; filename="{filename}.{extension}"'
    writer = csv.writer(response, delimiter=delimiter)
    writer.writerow(headers + ['Action'])
    for row in rows:
        writer.writerow([_cell_value(cell) for cell in row['cells']] + [' | '.join(action['label'] for action in row['actions'])])
    return response


def _prepare_table_context(request, headers, rows, actions, export_name):
    normalized_rows = [
        {
            'cells': row,
            'actions': actions[index] if index < len(actions) else [],
        }
        for index, row in enumerate(rows)
    ]

    search_text = request.GET.get('q', '').strip()
    if search_text:
        query = search_text.lower()
        normalized_rows = [
            row for row in normalized_rows
            if query in ' '.join(_cell_value(cell).lower() for cell in row['cells'])
        ]

    status_options = []
    seen_statuses = set()
    for row in normalized_rows:
        for cell in row['cells']:
            if isinstance(cell, dict) and cell.get('tone'):
                value = _cell_value(cell)
                if value and value not in seen_statuses:
                    seen_statuses.add(value)
                    status_options.append(value)

    selected_filter = request.GET.get('filter', '').strip()
    if selected_filter:
        normalized_rows = [
            row for row in normalized_rows
            if any(_cell_value(cell) == selected_filter for cell in row['cells'])
        ]

    try:
        sort_index = int(request.GET.get('sort', ''))
    except ValueError:
        sort_index = -1
    sort_direction = request.GET.get('dir', 'asc')
    if 0 <= sort_index < len(headers):
        normalized_rows.sort(
            key=lambda row: _cell_value(row['cells'][sort_index]).lower(),
            reverse=sort_direction == 'desc',
        )

    export_format = request.GET.get('export')
    if export_format in {'csv', 'excel'}:
        return _table_export_response(export_name, headers, normalized_rows, export_format)

    try:
        per_page = int(request.GET.get('per_page', 25))
    except ValueError:
        per_page = 25
    per_page = per_page if per_page in {10, 25, 50, 100} else 25
    paginator = Paginator(normalized_rows, per_page)
    page_obj = paginator.get_page(request.GET.get('page'))
    page_links = [
        {
            'number': number,
            'url': _query_url(request, page=number, export=None, partial=None) if isinstance(number, int) else '',
            'current': number == page_obj.number,
            'ellipsis': not isinstance(number, int),
        }
        for number in paginator.get_elided_page_range(page_obj.number)
    ]

    table_headers = []
    for index, label in enumerate(headers):
        next_direction = 'desc' if sort_index == index and sort_direction == 'asc' else 'asc'
        table_headers.append(
            {
                'label': label,
                'sort_url': _query_url(request, sort=index, dir=next_direction, page=None, export=None, partial=None),
                'active': sort_index == index,
                'direction': sort_direction if sort_index == index else '',
            }
        )

    return {
        'table_headers': table_headers,
        'table_rows': list(page_obj.object_list),
        'page_obj': page_obj,
        'paginator': paginator,
        'page_links': page_links,
        'previous_page_url': _query_url(request, page=page_obj.previous_page_number(), export=None, partial=None) if page_obj.has_previous() else '',
        'next_page_url': _query_url(request, page=page_obj.next_page_number(), export=None, partial=None) if page_obj.has_next() else '',
        'search_text': search_text,
        'selected_filter': selected_filter,
        'status_options': status_options,
        'per_page': per_page,
        'per_page_options': [10, 25, 50, 100],
        'clear_table_url': request.path,
        'export_csv_url': _query_url(request, export='csv', partial=None),
        'export_excel_url': _query_url(request, export='excel', partial=None),
    }


def _select_options(queryset, label_func, value_func=lambda obj: obj.pk):
    return [{'value': value_func(obj), 'label': label_func(obj)} for obj in queryset]


def _report_filter_controls(request, include=()):
    include = set(include)
    controls = []
    if 'date' in include:
        controls.extend(
            [
                {'type': 'date', 'name': 'date_from', 'value': request.GET.get('date_from', ''), 'placeholder': 'From date'},
                {'type': 'date', 'name': 'date_to', 'value': request.GET.get('date_to', ''), 'placeholder': 'To date'},
            ]
        )
    if 'seller' in include:
        controls.append(
            {
                'type': 'select',
                'name': 'seller',
                'value': request.GET.get('seller', ''),
                'placeholder': 'All sellers',
                'options': _select_options(SellerApplication.objects.order_by('store_name'), lambda seller: seller.store_name or seller.name),
            }
        )
    if 'customer' in include:
        controls.append(
            {
                'type': 'select',
                'name': 'customer',
                'value': request.GET.get('customer', ''),
                'placeholder': 'All customers',
                'options': _select_options(User.objects.filter(is_staff=False).order_by('first_name', 'email')[:200], lambda user: user.get_full_name() or user.email or user.username),
            }
        )
    if 'order_status' in include:
        controls.append(
            {
                'type': 'select',
                'name': 'order_status',
                'value': request.GET.get('order_status', ''),
                'placeholder': 'All order statuses',
                'options': [{'value': value, 'label': label} for value, label in Order.Status.choices],
            }
        )
    if 'payment_status' in include:
        controls.append(
            {
                'type': 'select',
                'name': 'payment_status',
                'value': request.GET.get('payment_status', ''),
                'placeholder': 'All payment statuses',
                'options': [{'value': value, 'label': label} for value, label in Order.PaymentStatus.choices],
            }
        )
    if 'category' in include:
        controls.append(
            {
                'type': 'select',
                'name': 'category',
                'value': request.GET.get('category', ''),
                'placeholder': 'All categories',
                'options': _select_options(Category.objects.order_by('display_order', 'name'), lambda category: category.name),
            }
        )
    if 'product' in include:
        controls.append(
            {
                'type': 'select',
                'name': 'product',
                'value': request.GET.get('product', ''),
                'placeholder': 'All products',
                'options': _select_options(SpiceItem.objects.order_by('name')[:300], lambda product: product.name),
            }
        )
    return controls


def _apply_order_filters_from_request(request, orders):
    date_from = parse_date(request.GET.get('date_from', '').strip())
    date_to = parse_date(request.GET.get('date_to', '').strip())
    seller_id = request.GET.get('seller', '').strip()
    customer_id = request.GET.get('customer', '').strip()
    order_status = request.GET.get('order_status', '').strip()
    payment_status = request.GET.get('payment_status', '').strip()

    if date_from:
        orders = orders.filter(created_at__date__gte=date_from)
    if date_to:
        orders = orders.filter(created_at__date__lte=date_to)
    if seller_id:
        orders = orders.filter(items__seller_id=seller_id)
    if customer_id:
        orders = orders.filter(customer_id=customer_id)
    if order_status:
        orders = orders.filter(status=order_status)
    if payment_status:
        orders = orders.filter(payment_status=payment_status)
    return orders.distinct()


def _apply_product_filters_from_request(request, products):
    seller_id = request.GET.get('seller', '').strip()
    category_id = request.GET.get('category', '').strip()
    product_id = request.GET.get('product', '').strip()
    if seller_id:
        products = products.filter(seller_id=seller_id)
    if category_id:
        products = products.filter(category_id=category_id)
    if product_id:
        products = products.filter(pk=product_id)
    return products


def _render_admin_overview(
    request,
    *,
    nav_group,
    section,
    title,
    subtitle,
    summary_cards,
    insights=None,
    quick_actions=None,
    table_title='',
    table_subtitle='',
    table_headers=None,
    table_rows=None,
    table_actions=None,
    empty_message='No data available yet.',
    primary_action=None,
    extra_filters=None,
):
    table_rows = table_rows or []
    table_actions = table_actions or []
    table_context = _prepare_table_context(
        request,
        table_headers or [],
        table_rows,
        table_actions,
        f'{nav_group}-{section}',
    )
    if isinstance(table_context, HttpResponse):
        return table_context

    context = _admin_context(
        nav_group,
        section,
        title=title,
        subtitle=subtitle,
        summary_cards=summary_cards,
        insights=insights or [],
        quick_actions=quick_actions or [],
        table_title=table_title,
        table_subtitle=table_subtitle,
        empty_message=empty_message,
        primary_action=primary_action,
        extra_filters=extra_filters or [],
        **table_context,
    )

    if request.GET.get('partial') == 'table':
        return render(request, 'admin_panel/partials/live_table.html', context)

    return render(
        request,
        'admin_panel/overview_page.html',
        context,
    )


def _humanize_slug(value):
    return value.replace('-', ' ').replace('&', 'and').title()


def _lookup_sidebar_title(module, section, snapshot):
    for group in _build_admin_sidebar(snapshot):
        if group['key'] == module:
            for child in group.get('children', []):
                if child.get('section') == section:
                    return child['label'], group['label']
            return group['label'], group['label']
    return _humanize_slug(section), _humanize_slug(module)


def _push_recipient_count(notification):
    if notification.audience == PushNotification.Audience.CUSTOMERS:
        return User.objects.filter(is_staff=False, is_active=True).count()
    if notification.audience == PushNotification.Audience.SELLERS:
        return SellerApplication.objects.filter(status=SellerApplication.Status.APPROVED).count()
    if notification.audience == PushNotification.Audience.SELECTED_CUSTOMERS:
        return notification.customers.count()
    if notification.audience == PushNotification.Audience.SELECTED_SELLERS:
        return notification.sellers.count()
    customer_count = User.objects.filter(is_staff=False, is_active=True).count()
    seller_count = SellerApplication.objects.filter(status=SellerApplication.Status.APPROVED).count()
    return customer_count + seller_count


def _mark_push_sent(notification, user=None):
    notification.status = PushNotification.Status.SENT
    notification.sent_by = user
    notification.sent_at = timezone.now()
    notification.recipient_count = _push_recipient_count(notification)
    notification.save(update_fields=['status', 'sent_by', 'sent_at', 'recipient_count', 'updated_at'])


def _sync_tracking_order_status(tracking, user=None):
    status_map = {
        ShipmentTracking.Status.PENDING: Order.Status.PENDING,
        ShipmentTracking.Status.PACKED: Order.Status.PACKED,
        ShipmentTracking.Status.SHIPPED: Order.Status.SHIPPED,
        ShipmentTracking.Status.OUT_FOR_DELIVERY: Order.Status.OUT_FOR_DELIVERY,
        ShipmentTracking.Status.DELIVERED: Order.Status.DELIVERED,
        ShipmentTracking.Status.CANCELLED: Order.Status.CANCELLED,
    }
    order_status = status_map.get(tracking.status)
    if not order_status or tracking.order.status == order_status:
        return
    _set_order_status(tracking.order, order_status, user, f'Shipment updated: {tracking.get_status_display()}')


def _process_return_side_effects(return_request, user=None):
    order = return_request.order
    update_fields = []
    if return_request.status == ReturnRequest.Status.APPROVED and order.status != Order.Status.RETURNED:
        order.status = Order.Status.RETURNED
        update_fields.append('status')
        order.items.update(item_status=Order.Status.RETURNED)
        _record_order_status(order, Order.Status.RETURNED, user, return_request.admin_note or 'Return approved')
    if return_request.refund_status == ReturnRequest.RefundStatus.COMPLETED and order.payment_status != Order.PaymentStatus.REFUNDED:
        order.payment_status = Order.PaymentStatus.REFUNDED
        update_fields.append('payment_status')
        Payment.objects.filter(order=order).update(status=Payment.Status.REFUNDED, updated_at=timezone.now())
        PaymentTransaction.objects.filter(order=order).update(status=PaymentTransaction.Status.REFUNDED, updated_at=timezone.now())
    if update_fields:
        update_fields.append('updated_at')
        order.save(update_fields=update_fields)


def _after_generic_save(config, obj, request, created=False):
    if isinstance(obj, PushNotification) and obj.status == PushNotification.Status.SENT and not obj.sent_at:
        _mark_push_sent(obj, request.user)
    if isinstance(obj, ShipmentTracking):
        now = timezone.now()
        update_fields = []
        if obj.status == ShipmentTracking.Status.SHIPPED and not obj.shipped_at:
            obj.shipped_at = now
            update_fields.append('shipped_at')
        if obj.status == ShipmentTracking.Status.DELIVERED and not obj.delivered_at:
            obj.delivered_at = now
            update_fields.append('delivered_at')
        if update_fields:
            update_fields.append('updated_at')
            obj.save(update_fields=update_fields)
        _sync_tracking_order_status(obj, request.user)
    if isinstance(obj, ReturnRequest):
        _process_return_side_effects(obj, request.user)
    if isinstance(obj, SellerPayout) and obj.status in {SellerPayout.Status.PAID, SellerPayout.Status.FAILED, SellerPayout.Status.REJECTED} and not obj.processed_at:
        obj.processed_at = timezone.now()
        obj.save(update_fields=['processed_at', 'updated_at'])


@user_passes_test(_staff_required, login_url='login')
def admin_generic_create(request, model_key):
    config = _generic_config(model_key)
    form_class = _generic_form_for_config(config)
    form = form_class(request.POST or None, request.FILES or None)
    if request.method == 'POST' and form.is_valid():
        obj = form.save()
        _after_generic_save(config, obj, request, created=True)
        messages.success(request, f'{config["label"]} saved successfully.')
        return redirect(_generic_back_href(config))

    return _render_admin_form_page(
        request,
        config['nav_group'],
        config['section'],
        title=f'Add {config["label"]}',
        subtitle=f'Create a database-backed {config["label"].lower()} record.',
        form=form,
        back_url='admin-dashboard',
        back_href=_generic_back_href(config),
    )


@user_passes_test(_staff_required, login_url='login')
def admin_generic_edit(request, model_key, pk):
    config = _generic_config(model_key)
    obj = get_object_or_404(config['model'], pk=pk)
    form_class = _generic_form_for_config(config)
    form = form_class(request.POST or None, request.FILES or None, instance=obj)
    if request.method == 'POST' and form.is_valid():
        obj = form.save()
        _after_generic_save(config, obj, request)
        messages.success(request, f'{config["label"]} updated successfully.')
        return redirect(_generic_back_href(config))

    return _render_admin_form_page(
        request,
        config['nav_group'],
        config['section'],
        title=f'Edit {config["label"]}',
        subtitle=f'Update this database-backed {config["label"].lower()} record.',
        form=form,
        back_url='admin-dashboard',
        back_href=_generic_back_href(config),
    )


@user_passes_test(_staff_required, login_url='login')
@require_http_methods(['GET', 'POST'])
def admin_generic_delete(request, model_key, pk):
    config = _generic_config(model_key)
    obj = get_object_or_404(config['model'], pk=pk)
    if request.method == 'POST':
        obj.delete()
        messages.success(request, f'{config["label"]} deleted successfully.')
        return redirect(_generic_back_href(config))

    return render(
        request,
        'admin_panel/confirm_delete.html',
        _admin_context(
            config['nav_group'],
            config['section'],
            title=f'Delete {config["label"]}',
            object_label=str(obj),
            back_url='admin-dashboard',
            back_href=_generic_back_href(config),
        ),
    )


@user_passes_test(_staff_required, login_url='login')
@require_http_methods(['POST'])
def admin_generic_action(request, model_key, pk, action):
    config = _generic_config(model_key)
    obj = get_object_or_404(config['model'], pk=pk)
    next_url = request.POST.get('next') or _generic_back_href(config)

    if action == 'activate' and hasattr(obj, 'is_active'):
        obj.is_active = True
        obj.save(update_fields=['is_active', 'updated_at'])
        messages.success(request, f'{config["label"]} activated.')
        return redirect(next_url)
    if action == 'deactivate' and hasattr(obj, 'is_active'):
        obj.is_active = False
        obj.save(update_fields=['is_active', 'updated_at'])
        messages.success(request, f'{config["label"]} deactivated.')
        return redirect(next_url)
    if isinstance(obj, Coupon) and action in {'approve', 'reject'}:
        obj.approval_status = Coupon.ApprovalStatus.APPROVED if action == 'approve' else Coupon.ApprovalStatus.REJECTED
        obj.is_active = action == 'approve'
        obj.save(update_fields=['approval_status', 'is_active', 'updated_at'])
        messages.success(request, 'Coupon approval status updated.')
        return redirect(next_url)
    if isinstance(obj, ProductReview) and action in {'approve', 'reject', 'hide', 'unhide'}:
        status_map = {
            'approve': ProductReview.Status.APPROVED,
            'reject': ProductReview.Status.REJECTED,
            'hide': ProductReview.Status.HIDDEN,
            'unhide': ProductReview.Status.APPROVED,
        }
        obj.status = status_map[action]
        obj.save(update_fields=['status', 'updated_at'])
        messages.success(request, 'Review status updated.')
        return redirect(next_url)
    if isinstance(obj, SellerReview) and action in {'approve', 'reject', 'hide', 'unhide'}:
        status_map = {
            'approve': SellerReview.Status.APPROVED,
            'reject': SellerReview.Status.REJECTED,
            'hide': SellerReview.Status.HIDDEN,
            'unhide': SellerReview.Status.APPROVED,
        }
        obj.status = status_map[action]
        obj.save(update_fields=['status', 'updated_at'])
        messages.success(request, 'Seller review status updated.')
        return redirect(next_url)
    if isinstance(obj, ReviewReport) and action in {'approve', 'reject', 'remove'}:
        if action == 'approve':
            obj.status = ReviewReport.Status.APPROVED
            if obj.product_review:
                obj.product_review.status = ProductReview.Status.HIDDEN
                obj.product_review.save(update_fields=['status', 'updated_at'])
            if obj.seller_review:
                obj.seller_review.status = SellerReview.Status.HIDDEN
                obj.seller_review.save(update_fields=['status', 'updated_at'])
        elif action == 'remove':
            obj.status = ReviewReport.Status.REMOVED
            if obj.product_review:
                obj.product_review.delete()
            if obj.seller_review:
                obj.seller_review.delete()
        else:
            obj.status = ReviewReport.Status.REJECTED
        obj.save(update_fields=['status', 'updated_at'])
        messages.success(request, 'Reported review action completed.')
        return redirect(next_url)
    if isinstance(obj, SupportTicket) and action in {'reply', 'close'}:
        obj.status = SupportTicket.Status.REPLIED if action == 'reply' else SupportTicket.Status.CLOSED
        obj.save(update_fields=['status', 'updated_at'])
        messages.success(request, 'Ticket status updated.')
        return redirect(next_url)
    if isinstance(obj, NotificationTemplate) and action == 'send':
        messages.success(request, 'Template is active for future notification flows. Provider delivery remains connected through existing email/OTP settings.')
        return redirect(next_url)
    if isinstance(obj, PushNotification) and action == 'send':
        _mark_push_sent(obj, request.user)
        messages.success(request, f'Push notification stored as sent for {obj.recipient_count} recipient(s).')
        return redirect(next_url)
    if isinstance(obj, ReturnRequest) and action in {'approve', 'reject', 'process-refund', 'complete-refund'}:
        if action == 'approve':
            obj.status = ReturnRequest.Status.APPROVED
            obj.refund_status = ReturnRequest.RefundStatus.APPROVED
        elif action == 'reject':
            obj.status = ReturnRequest.Status.REJECTED
            obj.refund_status = ReturnRequest.RefundStatus.REJECTED
        elif action == 'process-refund':
            obj.refund_status = ReturnRequest.RefundStatus.PROCESSING
        elif action == 'complete-refund':
            obj.refund_status = ReturnRequest.RefundStatus.COMPLETED
        obj.processed_by = request.user
        obj.processed_at = timezone.now()
        obj.save(update_fields=['status', 'refund_status', 'processed_by', 'processed_at', 'updated_at'])
        _process_return_side_effects(obj, request.user)
        messages.success(request, 'Return/refund status updated.')
        return redirect(next_url)
    if isinstance(obj, SellerPayout) and action in {'approve', 'paid', 'fail', 'reject'}:
        status_map = {
            'approve': SellerPayout.Status.APPROVED,
            'paid': SellerPayout.Status.PAID,
            'fail': SellerPayout.Status.FAILED,
            'reject': SellerPayout.Status.REJECTED,
        }
        obj.status = status_map[action]
        if obj.status in {SellerPayout.Status.PAID, SellerPayout.Status.FAILED, SellerPayout.Status.REJECTED}:
            obj.processed_at = timezone.now()
        obj.save(update_fields=['status', 'processed_at', 'updated_at'])
        messages.success(request, 'Payout status updated.')
        return redirect(next_url)

    messages.error(request, 'Invalid action.')
    return redirect(next_url)


def _products_for_admin_section(section):
    products = SpiceItem.objects.select_related('category', 'seller').prefetch_related('gallery_images').order_by('-updated_at', 'name')
    if section in {'pending-products'}:
        return products.filter(approval_status=SpiceItem.ApprovalStatus.PENDING)
    if section in {'approved-products'}:
        return products.filter(approval_status=SpiceItem.ApprovalStatus.APPROVED)
    if section in {'rejected-products'}:
        return products.filter(approval_status=SpiceItem.ApprovalStatus.REJECTED)
    if section in {'featured-products'}:
        return products.filter(is_featured=True)
    if section in {'out-of-stock-products'}:
        return products.filter(stock=0)
    if section in {'low-stock-products'}:
        return products.filter(stock__gt=0, stock__lte=10)
    return products


def _seller_apps_for_admin_section(section):
    applications = SellerApplication.objects.order_by('-created_at')
    if section in {'seller-requests', 'seller-kyc'}:
        return applications.filter(status__in=[SellerApplication.Status.PENDING, SellerApplication.Status.MORE_INFO])
    if section == 'approved-sellers':
        return applications.filter(status=SellerApplication.Status.APPROVED)
    if section == 'rejected-sellers':
        return applications.filter(status=SellerApplication.Status.REJECTED)
    if section == 'blocked-sellers':
        return applications.filter(status=SellerApplication.Status.BLOCKED)
    return applications


def _seller_admin_actions(seller, include_status=True):
    detail_url = reverse('admin-seller-detail', kwargs={'pk': seller.pk})
    actions = [
        _action('View', detail_url, 'view'),
    ]
    if include_status and seller.status != SellerApplication.Status.APPROVED:
        actions.append(
            _action(
                'Approve',
                reverse('admin-seller-status', kwargs={'pk': seller.pk, 'status': SellerApplication.Status.APPROVED}),
                'approve',
                'post',
            )
        )
    if include_status and seller.status != SellerApplication.Status.REJECTED:
        actions.append(_action('Reject', f'{detail_url}?action=reject#admin-review', 'delete'))
    if include_status and seller.status != SellerApplication.Status.MORE_INFO:
        actions.append(_action('Request More Info', f'{detail_url}?action=more_info#admin-review', 'edit'))
    return actions


def _seller_actions_for_section(seller, section):
    detail_url = reverse('admin-seller-detail', kwargs={'pk': seller.pk})
    details = _action('View', detail_url, 'view')
    edit = _action('Edit', reverse('admin-seller-edit', kwargs={'pk': seller.pk}), 'edit')
    delete = _action('Delete', reverse('admin-seller-delete', kwargs={'pk': seller.pk}), 'delete')
    approve = _action(
        'Approve',
        reverse('admin-seller-status', kwargs={'pk': seller.pk, 'status': SellerApplication.Status.APPROVED}),
        'approve',
        'post',
    )
    reject = _action('Reject', f'{detail_url}?action=reject#admin-review', 'delete')
    more_info = _action('Request More Info', f'{detail_url}?action=more_info#admin-review', 'edit')
    block = _action(
        'Block',
        reverse('admin-seller-status', kwargs={'pk': seller.pk, 'status': SellerApplication.Status.BLOCKED}),
        'delete',
        'post',
    )
    unblock = _action(
        'Unblock',
        reverse('admin-seller-status', kwargs={'pk': seller.pk, 'status': SellerApplication.Status.APPROVED}),
        'approve',
        'post',
    )
    reapprove = _action(
        'Reapprove',
        reverse('admin-seller-status', kwargs={'pk': seller.pk, 'status': SellerApplication.Status.APPROVED}),
        'approve',
        'post',
    )

    if section == 'seller-requests':
        return [details, approve, reject, more_info]
    if section == 'approved-sellers':
        return [details, edit, block, delete]
    if section == 'rejected-sellers':
        return [details, reapprove, delete]
    if section == 'blocked-sellers':
        return [details, unblock, delete]
    if section == 'seller-commission':
        return [details]
    return [details, approve, reject, more_info]


def _orders_for_admin_section(section):
    orders = Order.objects.select_related('customer').prefetch_related('items').order_by('-created_at')
    status_map = {
        'pending-orders': Order.Status.PENDING,
        'confirmed-orders': Order.Status.CONFIRMED,
        'packed-orders': Order.Status.PACKED,
        'shipped-orders': Order.Status.SHIPPED,
        'delivered-orders': Order.Status.DELIVERED,
        'cancelled-orders': Order.Status.CANCELLED,
        'returned-orders': Order.Status.RETURNED,
    }
    if section in status_map:
        return orders.filter(status=status_map[section])
    return orders


def _order_table_data(orders):
    table_rows = []
    table_actions = []
    for order in orders:
        order_items = list(order.items.all())
        seller_names = sorted({item.seller_name for item in order_items if item.seller_name})
        seller_label = ', '.join(seller_names) if seller_names else 'Admin catalog'
        table_rows.append(
            [
                _cell(order.order_number),
                _cell(order.customer_name),
                _cell(seller_label),
                _cell(order.item_count),
                _cell(_format_currency(order.total_amount)),
                _cell(order.get_payment_status_display(), order.payment_tone),
                _cell(order.get_status_display(), order.status_tone),
                _cell(order.created_at.strftime('%d %b %Y')),
            ]
        )
        table_actions.append(
            [
                _action('View', reverse('admin-order-detail', kwargs={'pk': order.pk}), 'view'),
                _action('Update Status', reverse('admin-order-edit', kwargs={'pk': order.pk}), 'edit'),
                _action('Invoice', reverse('admin-order-invoice', kwargs={'pk': order.pk}), 'view'),
            ]
        )
    return table_rows, table_actions


def _order_actions(order):
    return [
        _action('View', reverse('admin-order-detail', kwargs={'pk': order.pk}), 'view'),
        _action('Update Status', reverse('admin-order-edit', kwargs={'pk': order.pk}), 'edit'),
        _action('Invoice', reverse('admin-order-invoice', kwargs={'pk': order.pk}), 'view'),
    ]


def _product_admin_actions(product, include_stock=False):
    actions = [
        _action('View', reverse('admin-item-detail', kwargs={'pk': product.pk}), 'view'),
        _action('Edit', reverse('admin-item-edit', kwargs={'pk': product.pk}), 'edit'),
        _action('Delete', reverse('admin-item-delete', kwargs={'pk': product.pk}), 'delete'),
    ]
    if include_stock:
        stock_action = _action('Add Stock', reverse('admin-item-stock-update', kwargs={'pk': product.pk}), 'stock')
        stock_action['current_stock'] = product.stock
        stock_action['stock_mode'] = 'add'
        actions.append(stock_action)
    return actions


def _product_table_data(products, include_stock=False):
    rows = []
    actions = []
    for product in products:
        rows.append(
            [
                _cell(product.product_id),
                _cell(product.name),
                _cell(product.category.name if product.category else 'General'),
                _cell(product.sub_category or '--'),
                _cell(product.owner_label),
                _cell(product.brand_name or 'Lexvers'),
                _cell(_format_currency(product.price)),
                _cell(product.stock, 'danger' if product.stock == 0 else 'warning' if product.stock <= 10 else 'success'),
                _cell('Active' if product.is_active else 'Hidden', 'success' if product.is_active else 'danger'),
            ]
        )
        actions.append(_product_admin_actions(product, include_stock=include_stock))
    return rows, actions


def _payment_transactions_for_admin_section(section):
    transactions = PaymentTransaction.objects.select_related('order', 'customer').order_by('-created_at')
    if section in {'successful-payments'}:
        return transactions.filter(status=PaymentTransaction.Status.SUCCESS)
    if section in {'failed-payments'}:
        return transactions.filter(status=PaymentTransaction.Status.FAILED)
    if section in {'refund-payments'}:
        return transactions.filter(status=PaymentTransaction.Status.REFUNDED)
    return transactions


def _payment_table_data(transactions):
    rows = []
    actions = []
    for transaction_record in transactions:
        customer_name = transaction_record.customer.first_name or transaction_record.customer.username if transaction_record.customer else (
            transaction_record.order.customer_name if transaction_record.order else 'Unknown'
        )
        rows.append(
            [
                _cell(transaction_record.transaction_id),
                _cell(customer_name),
                _cell(_format_currency(transaction_record.amount)),
                _cell(transaction_record.method),
                _cell(transaction_record.get_status_display(), transaction_record.status_tone),
                _cell(transaction_record.created_at.strftime('%d %b %Y')),
            ]
        )
        refund_action = _action(
            'Refund',
            reverse('admin-payment-status', kwargs={'pk': transaction_record.pk, 'status': PaymentTransaction.Status.REFUNDED}),
            'delete',
            'post',
        )
        actions.append([_action('View', reverse('admin-payment-detail', kwargs={'pk': transaction_record.pk}), 'view'), refund_action])
    return rows, actions


def _seller_finance_table_data(sellers):
    rows = []
    actions = []
    for seller in sellers:
        seller_items = OrderItem.objects.filter(seller=seller).exclude(
            order__status__in=[Order.Status.CANCELLED, Order.Status.RETURNED],
        )
        totals = seller_items.aggregate(order_value=Sum('line_total'), units=Sum('quantity'), orders=Count('order', distinct=True))
        order_value = totals.get('order_value') or Decimal('0')
        commission = order_value * Decimal('0.10')
        rows.append(
            [
                _cell(seller.name),
                _cell(totals.get('orders') or 0),
                _cell(_format_currency(order_value)),
                _cell(_format_currency(commission), 'info'),
                _cell(_format_currency(order_value - commission), 'success'),
                _cell('Payable' if order_value else 'No earnings', 'success' if order_value else 'warning'),
            ]
        )
        actions.append([_action('Details', reverse('admin-seller-detail', kwargs={'pk': seller.pk}), 'view')])
    return rows, actions


def _seller_payout_table_data(section=''):
    payouts = SellerPayout.objects.select_related('seller', 'requested_by').order_by('-created_at')
    if section == 'approved-payouts':
        payouts = payouts.filter(status=SellerPayout.Status.APPROVED)
    elif section == 'paid-payouts':
        payouts = payouts.filter(status=SellerPayout.Status.PAID)
    elif section == 'rejected-payouts':
        payouts = payouts.filter(status=SellerPayout.Status.REJECTED)
    elif section == 'payout-requests':
        payouts = payouts.filter(status=SellerPayout.Status.PENDING)
    rows = []
    actions = []
    for payout in payouts[:100]:
        rows.append(
            [
                _cell(payout.payout_id),
                _cell(payout.seller.store_name),
                _cell(_format_currency(payout.amount)),
                _cell(payout.bank_account or payout.upi_id or 'Not set'),
                _cell(payout.get_status_display(), payout.status_tone),
                _cell(payout.created_at.strftime('%d %b %Y')),
            ]
        )
        payout_actions = _generic_edit_delete_actions('seller-payout', payout)
        if payout.status == SellerPayout.Status.PENDING:
            payout_actions += [
                _action('Approve', reverse('admin-generic-action', kwargs={'model_key': 'seller-payout', 'pk': payout.pk, 'action': 'approve'}), 'approve', 'post'),
                _action('Reject', reverse('admin-generic-action', kwargs={'model_key': 'seller-payout', 'pk': payout.pk, 'action': 'reject'}), 'delete', 'post'),
            ]
        if payout.status == SellerPayout.Status.APPROVED:
            payout_actions += [
                _action('Mark Paid', reverse('admin-generic-action', kwargs={'model_key': 'seller-payout', 'pk': payout.pk, 'action': 'paid'}), 'approve', 'post'),
                _action('Mark Failed', reverse('admin-generic-action', kwargs={'model_key': 'seller-payout', 'pk': payout.pk, 'action': 'fail'}), 'delete', 'post'),
            ]
        actions.append(payout_actions)
    return rows, actions


def _return_requests_for_admin_section(section):
    returns = ReturnRequest.objects.select_related('order', 'customer').order_by('-updated_at')
    if section == 'refund-requests':
        return returns.filter(refund_status__in=[ReturnRequest.RefundStatus.REQUESTED, ReturnRequest.RefundStatus.PROCESSING, ReturnRequest.RefundStatus.APPROVED])
    if section == 'return-requests':
        return returns.filter(status=ReturnRequest.Status.PENDING)
    if section == 'approved-returns':
        return returns.filter(status=ReturnRequest.Status.APPROVED)
    if section == 'rejected-returns':
        return returns.filter(status=ReturnRequest.Status.REJECTED)
    return returns


def _return_table_data(return_requests):
    rows = []
    actions = []
    for request_row in return_requests:
        customer_name = request_row.customer.first_name or request_row.customer.username if request_row.customer else request_row.order.customer_name
        rows.append(
            [
                _cell(request_row.order.order_number),
                _cell(customer_name),
                _cell(request_row.reason),
                _cell(_format_currency(request_row.refund_amount)),
                _cell(request_row.get_status_display(), request_row.status_tone),
                _cell(request_row.get_refund_status_display(), request_row.refund_tone),
                _cell(request_row.pickup_status),
                _cell(request_row.updated_at.strftime('%d %b %Y')),
            ]
        )
        row_actions = [
            _action('View', reverse('admin-return-detail', kwargs={'pk': request_row.pk}), 'view'),
            _action('Edit', reverse('admin-generic-edit', kwargs={'model_key': 'return-request', 'pk': request_row.pk}), 'edit'),
        ]
        if request_row.status == ReturnRequest.Status.PENDING:
            row_actions += [
                _action('Approve', reverse('admin-generic-action', kwargs={'model_key': 'return-request', 'pk': request_row.pk, 'action': 'approve'}), 'approve', 'post'),
                _action('Reject', reverse('admin-generic-action', kwargs={'model_key': 'return-request', 'pk': request_row.pk, 'action': 'reject'}), 'delete', 'post'),
            ]
        if request_row.refund_status in {ReturnRequest.RefundStatus.APPROVED, ReturnRequest.RefundStatus.REQUESTED}:
            row_actions.append(_action('Process Refund', reverse('admin-generic-action', kwargs={'model_key': 'return-request', 'pk': request_row.pk, 'action': 'process-refund'}), 'edit', 'post'))
        if request_row.refund_status == ReturnRequest.RefundStatus.PROCESSING:
            row_actions.append(_action('Complete Refund', reverse('admin-generic-action', kwargs={'model_key': 'return-request', 'pk': request_row.pk, 'action': 'complete-refund'}), 'approve', 'post'))
        actions.append(row_actions)
    return rows, actions


def _shipping_table_data(section):
    orders = Order.objects.select_related('customer').prefetch_related('items').order_by('-updated_at')
    if section == 'tracking-management':
        orders = orders.filter(status__in=[Order.Status.PACKED, Order.Status.SHIPPED, Order.Status.DELIVERED])
        rows = [
            [
                _cell(order.order_number),
                _cell(order.customer_name),
                _cell(order.shipping_address or 'Address not added'),
                _cell(_format_currency(order.shipping_fee)),
                _cell(order.get_status_display(), order.status_tone),
                _cell(order.updated_at.strftime('%d %b %Y')),
            ]
            for order in orders[:50]
        ]
        return rows, [_order_actions(order) for order in orders[:50]], ['Order', 'Customer', 'Address', 'Shipping Fee', 'Status', 'Updated']

    if section == 'shipping-charges':
        charge_orders = orders.filter(shipping_fee__gt=0)[:50]
        rows = [
            [
                _cell(order.order_number),
                _cell(order.customer_name),
                _cell(_format_currency(order.shipping_fee)),
                _cell(_format_currency(order.total_amount)),
                _cell(order.get_status_display(), order.status_tone),
                _cell(order.created_at.strftime('%d %b %Y')),
            ]
            for order in charge_orders
        ]
        return rows, [_order_actions(order) for order in charge_orders], ['Order', 'Customer', 'Shipping Fee', 'Order Total', 'Status', 'Date']

    return [], [], ['Name', 'Status', 'Updated']


def _inventory_category_table_data():
    categories = list(
        Category.objects.annotate(
            active_items=Count('items', filter=Q(items__is_active=True), distinct=True),
            stock_units=Sum('items__stock', filter=Q(items__is_active=True)),
            low_items=Count('items', filter=Q(items__is_active=True, items__stock__gt=0, items__stock__lte=10), distinct=True),
            out_items=Count('items', filter=Q(items__is_active=True, items__stock=0), distinct=True),
        ).order_by('-stock_units', 'name')
    )
    rows = [
        [
            _cell(category.name),
            _cell(category.active_items),
            _cell(category.stock_units or 0),
            _cell(category.low_items or 0, 'warning' if category.low_items else ''),
            _cell(category.out_items or 0, 'danger' if category.out_items else ''),
        ]
        for category in categories
    ]
    actions = [
        [
            _action('View', reverse('admin-category-products', kwargs={'pk': category.pk}), 'view'),
            _action('Edit', reverse('admin-category-edit', kwargs={'pk': category.pk}), 'edit'),
            _action('Delete', reverse('admin-category-delete', kwargs={'pk': category.pk}), 'delete'),
        ]
        for category in categories
    ]
    return rows, actions


def _banner_table_data(banners):
    rows = []
    actions = []
    for banner in banners:
        rows.append(
            [
                _cell(banner.title),
                _cell(banner.get_placement_display()),
                _cell(banner.cta_text),
                _cell('Active' if banner.is_active else 'Hidden', 'success' if banner.is_active else 'danger'),
                _cell(banner.updated_at.strftime('%d %b %Y')),
            ]
        )
        actions.append(
            [
                _action('Edit', reverse('admin-banner-edit', kwargs={'pk': banner.pk}), 'edit'),
                _action('Delete', reverse('admin-banner-delete', kwargs={'pk': banner.pk}), 'delete'),
            ]
        )
    return rows, actions


def _generic_edit_delete_actions(model_key, obj):
    return [
        _action('Edit', reverse('admin-generic-edit', kwargs={'model_key': model_key, 'pk': obj.pk}), 'edit'),
        _action('Delete', reverse('admin-generic-delete', kwargs={'model_key': model_key, 'pk': obj.pk}), 'delete'),
    ]


def _active_toggle_action(model_key, obj):
    if not hasattr(obj, 'is_active'):
        return []
    if obj.is_active:
        return [_action('Deactivate', reverse('admin-generic-action', kwargs={'model_key': model_key, 'pk': obj.pk, 'action': 'deactivate'}), 'delete', 'post')]
    return [_action('Activate', reverse('admin-generic-action', kwargs={'model_key': model_key, 'pk': obj.pk, 'action': 'activate'}), 'approve', 'post')]


def _coupon_table_data(coupons):
    rows = []
    actions = []
    for coupon in coupons:
        discount = f'{coupon.discount_value}% ' if coupon.discount_type == Coupon.DiscountType.PERCENT else _format_currency(coupon.discount_value)
        rows.append(
            [
                _cell(coupon.code),
                _cell(coupon.title),
                _cell(coupon.owner_label),
                _cell(discount),
                _cell(_format_currency(coupon.min_order_amount)),
                _cell(_format_currency(coupon.max_discount) if coupon.max_discount is not None else 'No cap'),
                _cell(coupon.starts_at.strftime('%d %b %Y') if coupon.starts_at else 'Any time'),
                _cell(coupon.ends_at.strftime('%d %b %Y') if coupon.ends_at else 'No end'),
                _cell('Unlimited' if coupon.usage_limit is None else f'{coupon.used_count}/{coupon.usage_limit}'),
                _cell(coupon.get_approval_status_display(), coupon.status_tone),
            ]
        )
        row_actions = _generic_edit_delete_actions('coupon', coupon) + _active_toggle_action('coupon', coupon)
        if coupon.approval_status == Coupon.ApprovalStatus.PENDING:
            row_actions += [
                _action('Approve', reverse('admin-generic-action', kwargs={'model_key': 'coupon', 'pk': coupon.pk, 'action': 'approve'}), 'approve', 'post'),
                _action('Reject', reverse('admin-generic-action', kwargs={'model_key': 'coupon', 'pk': coupon.pk, 'action': 'reject'}), 'delete', 'post'),
            ]
        actions.append(row_actions)
    return rows, actions


def _offer_table_data(offers):
    rows = []
    actions = []
    for offer in offers:
        rows.append(
            [
                _cell(offer.title),
                _cell(f'{offer.discount_value}% ' if offer.discount_type == Offer.DiscountType.PERCENT else _format_currency(offer.discount_value)),
                _cell(offer.products.count()),
                _cell(offer.starts_at.strftime('%d %b %Y') if offer.starts_at else 'Any time'),
                _cell(offer.ends_at.strftime('%d %b %Y') if offer.ends_at else 'No end'),
                _cell('Live' if offer.is_live else 'Scheduled/Inactive', offer.status_tone),
                _cell(offer.updated_at.strftime('%d %b %Y')),
            ]
        )
        actions.append(_generic_edit_delete_actions('offer', offer) + _active_toggle_action('offer', offer))
    return rows, actions


def _shipping_model_table_data(section):
    if section == 'shipping-charges':
        records = list(ShippingCharge.objects.order_by('name'))
        rows = [
            [
                _cell(record.name),
                _cell(_format_currency(record.min_order_value)),
                _cell(_format_currency(record.max_order_value) if record.max_order_value is not None else 'No max'),
                _cell(_format_currency(record.charge)),
                _cell(_format_currency(record.free_delivery_threshold) if record.free_delivery_threshold is not None else 'Not set'),
                _cell('Active' if record.is_active else 'Inactive', 'success' if record.is_active else 'danger'),
            ]
            for record in records
        ]
        actions = [_generic_edit_delete_actions('shipping-charge', record) + _active_toggle_action('shipping-charge', record) for record in records]
        return ['Name', 'Min Order', 'Max Order', 'Charge', 'Free Above', 'Status'], rows, actions, 'shipping-charge'
    if section == 'courier-partners':
        records = list(CourierPartner.objects.order_by('name'))
        rows = [
            [
                _cell(record.name),
                _cell(record.contact_phone or 'Not set'),
                _cell(record.contact_email or 'Not set'),
                _cell(record.website_url or record.tracking_url or 'Not set'),
                _cell('Active' if record.is_active else 'Inactive', 'success' if record.is_active else 'danger'),
            ]
            for record in records
        ]
        actions = [_generic_edit_delete_actions('courier-partner', record) + _active_toggle_action('courier-partner', record) for record in records]
        return ['Courier', 'Phone', 'Email', 'Website / Tracking', 'Status'], rows, actions, 'courier-partner'
    if section == 'delivery-areas':
        records = list(DeliveryArea.objects.order_by('state', 'city', 'pincode'))
        rows = [
            [
                _cell(record.pincode),
                _cell(record.city),
                _cell(record.state),
                _cell('Yes' if record.is_serviceable else 'No', record.status_tone),
                _cell('Yes' if record.cod_available else 'No', 'success' if record.cod_available else 'warning'),
                _cell(f'{record.estimated_days} days'),
            ]
            for record in records
        ]
        actions = [_generic_edit_delete_actions('delivery-area', record) + _active_toggle_action('delivery-area', record) for record in records]
        return ['Pincode', 'City', 'State', 'Serviceable', 'COD', 'ETA'], rows, actions, 'delivery-area'
    records = list(ShipmentTracking.objects.select_related('order', 'courier').order_by('-updated_at'))
    rows = [
        [
            _cell(record.order.order_number),
            _cell(record.courier.name if record.courier else 'Not assigned'),
            _cell(record.tracking_number or 'Not set'),
            _cell(record.get_status_display(), record.status_tone),
            _cell(record.last_location or 'Not set'),
            _cell(record.tracking_link or 'Not set'),
            _cell(record.updated_at.strftime('%d %b %Y')),
        ]
        for record in records
    ]
    actions = [_generic_edit_delete_actions('shipment-tracking', record) for record in records]
    return ['Order', 'Courier', 'Tracking ID', 'Status', 'Last Location', 'Tracking URL', 'Updated'], rows, actions, 'shipment-tracking'


def _review_table_data(section):
    if section == 'seller-reviews':
        reviews = SellerReview.objects.select_related('seller', 'customer').order_by('-created_at')
        rows = []
        actions = []
        for review in reviews:
            rows.append(
                [
                    _cell(review.seller.store_name),
                    _cell(review.reviewer_label),
                    _cell(review.rating),
                    _cell(review.comment[:80] if review.comment else 'No comment'),
                    _cell(review.get_status_display(), review.status_tone),
                    _cell(review.created_at.strftime('%d %b %Y')),
                ]
            )
            actions.append(
                [
                    _action('View', reverse('admin-generic-edit', kwargs={'model_key': 'seller-review', 'pk': review.pk}), 'view'),
                    _action('Approve', reverse('admin-generic-action', kwargs={'model_key': 'seller-review', 'pk': review.pk, 'action': 'approve'}), 'approve', 'post'),
                    _action('Reject', reverse('admin-generic-action', kwargs={'model_key': 'seller-review', 'pk': review.pk, 'action': 'reject'}), 'delete', 'post'),
                    _action('Hide', reverse('admin-generic-action', kwargs={'model_key': 'seller-review', 'pk': review.pk, 'action': 'hide'}), 'delete', 'post'),
                    _action('Delete', reverse('admin-generic-delete', kwargs={'model_key': 'seller-review', 'pk': review.pk}), 'delete'),
                ]
            )
        return ['Seller', 'Customer', 'Rating', 'Review', 'Status', 'Date'], rows, actions, 'seller-review'

    if section == 'reported-reviews':
        reports = ReviewReport.objects.select_related('product_review__product', 'seller_review__seller', 'reporter').order_by('-created_at')
        rows = []
        actions = []
        for report in reports:
            rows.append(
                [
                    _cell(report.review_label),
                    _cell(report.reporter_label),
                    _cell(report.reason),
                    _cell(report.details[:80] if report.details else 'No details'),
                    _cell(report.get_status_display(), report.status_tone),
                    _cell(report.created_at.strftime('%d %b %Y')),
                ]
            )
            actions.append(
                [
                    _action('View', reverse('admin-generic-edit', kwargs={'model_key': 'review-report', 'pk': report.pk}), 'view'),
                    _action('Approve Report', reverse('admin-generic-action', kwargs={'model_key': 'review-report', 'pk': report.pk, 'action': 'approve'}), 'approve', 'post'),
                    _action('Reject Report', reverse('admin-generic-action', kwargs={'model_key': 'review-report', 'pk': report.pk, 'action': 'reject'}), 'edit', 'post'),
                    _action('Remove Review', reverse('admin-generic-action', kwargs={'model_key': 'review-report', 'pk': report.pk, 'action': 'remove'}), 'delete', 'post'),
                ]
            )
        return ['Review', 'Reporter', 'Reason', 'Details', 'Status', 'Date'], rows, actions, 'review-report'

    reviews = ProductReview.objects.select_related('product', 'customer').order_by('-created_at')
    rows = []
    actions = []
    for review in reviews:
        rows.append(
            [
                _cell(review.product.name),
                _cell(review.reviewer_label),
                _cell(review.rating),
                _cell(review.comment[:80] if review.comment else review.title or 'No comment'),
                _cell(review.get_status_display(), review.status_tone),
                _cell(review.created_at.strftime('%d %b %Y')),
            ]
        )
        actions.append(
            [
                _action('View', reverse('admin-generic-edit', kwargs={'model_key': 'review', 'pk': review.pk}), 'view'),
                _action('Approve', reverse('admin-generic-action', kwargs={'model_key': 'review', 'pk': review.pk, 'action': 'approve'}), 'approve', 'post'),
                _action('Reject', reverse('admin-generic-action', kwargs={'model_key': 'review', 'pk': review.pk, 'action': 'reject'}), 'delete', 'post'),
                _action('Hide', reverse('admin-generic-action', kwargs={'model_key': 'review', 'pk': review.pk, 'action': 'hide'}), 'delete', 'post'),
                _action('Delete', reverse('admin-generic-delete', kwargs={'model_key': 'review', 'pk': review.pk}), 'delete'),
            ]
        )
    return ['Product', 'Customer', 'Rating', 'Review', 'Status', 'Date'], rows, actions, 'review'


def _ticket_table_data(section):
    ticket_type = {
        'customer-tickets': SupportTicket.TicketType.CUSTOMER,
        'seller-tickets': SupportTicket.TicketType.SELLER,
        'complaints': SupportTicket.TicketType.COMPLAINT,
    }.get(section)
    tickets = SupportTicket.objects.select_related('customer', 'seller').order_by('-updated_at')
    if ticket_type:
        tickets = tickets.filter(ticket_type=ticket_type)
    rows = []
    actions = []
    for ticket in tickets:
        user_label = ticket.seller.store_name if ticket.seller else (ticket.customer.first_name or ticket.customer.username if ticket.customer else 'Guest')
        rows.append(
            [
                _cell(ticket.pk),
                _cell(ticket.get_ticket_type_display()),
                _cell(ticket.subject),
                _cell(user_label),
                _cell(ticket.get_status_display(), ticket.status_tone),
                _cell(ticket.updated_at.strftime('%d %b %Y')),
            ]
        )
        actions.append(
            [
                _action('View', reverse('admin-generic-edit', kwargs={'model_key': 'ticket', 'pk': ticket.pk}), 'view'),
                _action('Reply', reverse('admin-generic-action', kwargs={'model_key': 'ticket', 'pk': ticket.pk, 'action': 'reply'}), 'edit', 'post'),
                _action('Close', reverse('admin-generic-action', kwargs={'model_key': 'ticket', 'pk': ticket.pk, 'action': 'close'}), 'delete', 'post'),
            ]
        )
    return rows, actions


def _content_table_data(section):
    page_map = {
        'about-us': StaticContent.Page.ABOUT,
        'terms-conditions': StaticContent.Page.TERMS,
        'privacy-policy': StaticContent.Page.PRIVACY,
        'return-policy': StaticContent.Page.RETURN,
        'faq': StaticContent.Page.FAQ,
    }
    records = StaticContent.objects.order_by('page')
    if section in page_map:
        records = records.filter(page=page_map[section])
    rows = [
        [
            _cell(record.get_page_display()),
            _cell(record.title),
            _cell('Active' if record.is_active else 'Inactive', 'success' if record.is_active else 'danger'),
            _cell(record.updated_at.strftime('%d %b %Y')),
        ]
        for record in records
    ]
    actions = [_generic_edit_delete_actions('content', record) + _active_toggle_action('content', record) for record in records]
    return rows, actions


def _notification_table_data(section):
    if section == 'push-notifications':
        records = PushNotification.objects.select_related('sent_by').prefetch_related('customers', 'sellers').order_by('-created_at')
        rows = [
            [
                _cell(record.title),
                _cell(record.get_audience_display()),
                _cell(record.recipient_count),
                _cell(record.get_status_display(), record.status_tone),
                _cell(record.sent_at.strftime('%d %b %Y %I:%M %p') if record.sent_at else 'Not sent'),
            ]
            for record in records
        ]
        actions = [
            _generic_edit_delete_actions('push-notification', record)
            + ([_action('Send', reverse('admin-generic-action', kwargs={'model_key': 'push-notification', 'pk': record.pk, 'action': 'send'}), 'approve', 'post')] if record.status != PushNotification.Status.SENT else [])
            for record in records
        ]
        return ['Title', 'Audience', 'Recipients', 'Status', 'Sent At'], rows, actions, 'push-notification'

    template_type = {
        'email-templates': NotificationTemplate.TemplateType.EMAIL,
        'sms-templates': NotificationTemplate.TemplateType.SMS,
    }.get(section)
    records = NotificationTemplate.objects.order_by('template_type', 'name')
    if template_type:
        records = records.filter(template_type=template_type)
    rows = [
        [
            _cell(record.name),
            _cell(record.get_template_type_display()),
            _cell(record.subject or 'No subject'),
            _cell(record.purpose or 'General'),
            _cell('Active' if record.is_active else 'Inactive', 'success' if record.is_active else 'danger'),
            _cell(record.updated_at.strftime('%d %b %Y')),
        ]
        for record in records
    ]
    actions = [
        _generic_edit_delete_actions('notification', record)
        + _active_toggle_action('notification', record)
        + [_action('Send', reverse('admin-generic-action', kwargs={'model_key': 'notification', 'pk': record.pk, 'action': 'send'}), 'approve', 'post')]
        for record in records
    ]
    return ['Name', 'Type', 'Subject', 'Purpose', 'Status', 'Updated'], rows, actions, 'notification'


def _website_setting_table_data(section):
    group_map = {
        'general-settings': 'Store Configuration',
        'payment-settings': 'Payment Settings',
        'payment-gateway': 'Payment Settings',
        'email-settings': 'Email Settings',
        'sms-settings': 'SMS Settings',
        'seo-settings': 'SEO Settings',
        'logo-branding': 'Logo & Branding',
    }
    records = WebsiteSetting.objects.order_by('group', 'label')
    if section in group_map:
        records = records.filter(group=group_map[section])
    rows = [
        [_cell(record.group), _cell(record.label), _cell(record.value[:100] if record.value else 'Not set'), _cell('Active' if record.is_active else 'Inactive', 'success' if record.is_active else 'danger')]
        for record in records
    ]
    actions = [_generic_edit_delete_actions('website-setting', record) + _active_toggle_action('website-setting', record) for record in records]
    return rows, actions


def _category_table_data(categories):
    rows = []
    actions = []
    for category in categories:
        rows.append(
            [
                _cell(category.name),
                _cell(category.total_products or 0),
                _cell(category.sub_category_total or 0),
                _cell(category.admin_products or 0),
                _cell(category.seller_products or 0),
                _cell(category.total_stock or 0, 'success' if (category.total_stock or 0) > 0 else 'warning'),
                _cell('Active' if category.is_active else 'Hidden', 'success' if category.is_active else 'danger'),
            ]
        )
        actions.append(
            [
                _action('View', reverse('admin-category-products', kwargs={'pk': category.pk}), 'view'),
                _action('Edit', reverse('admin-category-edit', kwargs={'pk': category.pk}), 'edit'),
                _action('Delete', reverse('admin-category-delete', kwargs={'pk': category.pk}), 'delete'),
            ]
        )
    return rows, actions


@user_passes_test(_staff_required, login_url='login')
def admin_panel_section(request, module, section):
    snapshot = _admin_snapshot()
    title, group_title = _lookup_sidebar_title(module, section, snapshot)
    subtitle = f'{group_title} workspace with live catalog and account data where available.'
    quick_actions = [
        _action('Dashboard', reverse('admin-dashboard'), 'primary'),
        _action('Products', reverse('admin-items')),
        _action('Sellers', reverse('admin-sellers')),
        _action('Settings', reverse('admin-settings')),
    ]

    table_headers = ['Record', 'Status', 'Updated']
    table_rows = []
    table_actions = []
    empty_message = 'No live records found for this section yet.'

    if module in {'order-management'}:
        orders = list(_orders_for_admin_section(section)[:50])
        table_rows, table_actions = _order_table_data(orders)
        total_value = sum((order.total_amount for order in orders), Decimal('0'))
        summary_cards = [
            _card('c-blue', 'fas fa-bag-shopping', 'Orders in View', len(orders)),
            _card('c-orange', 'fas fa-hourglass-start', 'Pending Orders', Order.objects.filter(status=Order.Status.PENDING).count()),
            _card('c-green', 'fas fa-indian-rupee-sign', 'Shown Value', _format_currency(total_value)),
            _card('c-purple', 'fas fa-truck-fast', 'Shipping Queue', Order.objects.filter(status__in=[Order.Status.PACKED, Order.Status.SHIPPED]).count()),
        ]
        return _render_admin_overview(
            request,
            nav_group=module,
            section=section,
            title=title,
            subtitle='Live order rows created from customer cart checkout.',
            summary_cards=summary_cards,
            insights=[
                _insight('Order source', 'Customer cart se place order karne par yahan record create hota hai.', 'Stock same transaction me reduce hota hai.'),
                _insight('Seller connection', 'Seller products wale order items seller panel me bhi dikhte hain.', 'Admin status update order detail edit se kar sakta hai.'),
                _insight('Fulfillment rhythm', 'Pending se Confirmed, Packed, Shipped, Delivered tak status maintain karein.', 'Cancelled/Returned records reports ke liye visible rahenge.'),
            ],
            quick_actions=quick_actions,
            table_title=title,
            table_subtitle='Customer, product, quantity, payment, status, and action controls.',
            table_headers=['Order ID', 'Customer', 'Seller', 'Product Count', 'Amount', 'Payment Status', 'Order Status', 'Date'],
            table_rows=table_rows,
            table_actions=table_actions,
            empty_message='No orders found for this section.',
            primary_action=_action('Open All Orders', reverse('admin-orders'), 'primary'),
        )

    if module in {'product-management', 'inventory-management'} or section in {'all-products', 'pending-products', 'approved-products', 'rejected-products', 'featured-products', 'out-of-stock-products', 'low-stock-products'}:
        if section == 'stock-report':
            inventory_products = list(
                SpiceItem.objects.select_related('category', 'seller')
                .annotate(
                    sold_stock=Sum('order_items__quantity'),
                    reserved_stock=Sum(
                        'order_items__quantity',
                        filter=Q(order_items__order__status__in=[Order.Status.PENDING, Order.Status.CONFIRMED, Order.Status.PACKED]),
                    ),
                )
                .order_by('name')[:50]
            )
            inventory_rows = [
                [
                    _cell(product.name),
                    _cell(product.stock, 'danger' if product.stock <= 0 else 'success'),
                    _cell(product.reserved_stock or 0, 'warning' if product.reserved_stock else ''),
                    _cell(product.sold_stock or 0),
                ]
                for product in inventory_products
            ]
            inventory_actions = [_product_admin_actions(product, include_stock=True) for product in inventory_products]
            return _render_admin_overview(
                request,
                nav_group=module,
                section=section,
                title=title,
                subtitle='Realtime product inventory from current orders and stock.',
                summary_cards=[],
                quick_actions=quick_actions,
                table_title=title,
                table_subtitle='Available, reserved, and sold stock by product.',
                table_headers=['Product', 'Available Stock', 'Reserved Stock', 'Sold Stock'],
                table_rows=inventory_rows,
                table_actions=inventory_actions,
                empty_message='No inventory records found yet.',
                primary_action=_action('Open Products', reverse('admin-items'), 'primary'),
            )

        products = list(_products_for_admin_section(section)[:50])
        stock_total = sum(product.stock for product in products)
        pending_count = SpiceItem.objects.filter(approval_status=SpiceItem.ApprovalStatus.PENDING).count()
        include_stock = module == 'product-management' or section in {'out-of-stock-products', 'low-stock-products'}
        if section == 'out-of-stock-products':
            table_headers = ['Product ID', 'Product', 'Category', 'Sub Category', 'Seller', 'Company', 'Last Stock Date', 'Status']
            table_rows = [
                [
                    _cell(product.product_id),
                    _cell(product.name),
                    _cell(product.category.name if product.category else 'General'),
                    _cell(product.sub_category or '--'),
                    _cell(product.owner_label),
                    _cell(product.brand_name or 'Lexvers'),
                    _cell(product.updated_at.strftime('%d %b %Y')),
                    _cell('Out of Stock', 'danger'),
                ]
                for product in products
            ]
            table_actions = [_product_admin_actions(product, include_stock=True) for product in products]
        else:
            table_headers = ['Product ID', 'Product', 'Category', 'Sub Category', 'Seller', 'Company', 'Price', 'Stock', 'Status']
            table_rows, table_actions = _product_table_data(products, include_stock=include_stock)
        summary_cards = [
            _card('c-blue', 'fas fa-boxes-stacked', 'Products in View', len(products)),
            _card('c-orange', 'fas fa-clock', 'Pending Products', pending_count),
            _card('c-green', 'fas fa-cubes', 'Shown Stock Units', stock_total),
            _card('c-red', 'fas fa-triangle-exclamation', 'Stock Alerts', snapshot['low_stock_count'] + snapshot['out_stock_count']),
        ]
        return _render_admin_overview(
            request,
            nav_group=module,
            section=section,
            title=title,
            subtitle=subtitle,
            summary_cards=summary_cards,
            insights=[
                _insight('Approval control', 'Seller products should stay pending until title, photo, price, category, and policy checks pass.', 'Approve only clean listings.'),
                _insight('Inventory control', 'Low and zero stock products need quick seller follow-up before orders are enabled.', 'Stock reality protects customer trust.'),
                _insight('Featured products', 'Feature only products with clear photos, healthy stock, and useful pricing.', 'This keeps homepage merchandising strong.'),
            ],
            quick_actions=quick_actions,
            table_title=title,
            table_subtitle='Live product rows from the current catalog.',
            table_headers=table_headers,
            table_rows=table_rows,
            table_actions=table_actions,
            empty_message='No products found for this section.',
            primary_action=_action('Open Product List', reverse('admin-items'), 'primary'),
        )

    if module in {'seller-management'}:
        sellers = list(_seller_apps_for_admin_section(section)[:50])
        table_headers = ['Request ID', 'Seller Name', 'Email', 'Phone', 'Shop Name', 'Business Type', 'Primary Category', 'Status', 'Submitted Date']
        table_rows = []
        table_actions = []
        if section in {'approved-sellers', 'seller-commission'}:
            sellers = list(SellerApplication.objects.filter(status=SellerApplication.Status.APPROVED).order_by('-updated_at')[:50])
            table_headers = ['Seller Name', 'Company Name', 'Products', 'Orders', 'Revenue', 'Status']
            for seller in sellers:
                seller_items = OrderItem.objects.filter(seller=seller).exclude(
                    order__status__in=[Order.Status.CANCELLED, Order.Status.RETURNED],
                )
                totals = seller_items.aggregate(revenue=Sum('line_total'), orders=Count('order', distinct=True))
                table_rows.append(
                    [
                        _cell(seller.name),
                        _cell(seller.store_name),
                        _cell(seller.products.count()),
                        _cell(totals.get('orders') or 0),
                        _cell(_format_currency(totals.get('revenue') or Decimal('0'))),
                        _cell(seller.get_status_display(), _seller_status_tone(seller.status)),
                    ]
                )
                table_actions.append(_seller_actions_for_section(seller, section))
        else:
            for seller in sellers:
                table_rows.append(
                    [
                        _cell(seller.request_code),
                        _cell(seller.name),
                        _cell(seller.email),
                        _cell(seller.phone),
                        _cell(seller.store_name),
                        _cell(seller.get_business_type_display()),
                        _cell(seller.primary_category or 'Not set'),
                        _cell(seller.get_status_display(), _seller_status_tone(seller.status)),
                        _cell(seller.created_at.strftime('%d %b %Y')),
                    ]
                )
                table_actions.append(_seller_actions_for_section(seller, section))
        summary_cards = [
            _card('c-orange', 'fas fa-hourglass-half', 'Seller Requests', SellerApplication.objects.filter(status__in=[SellerApplication.Status.PENDING, SellerApplication.Status.MORE_INFO]).count()),
            _card('c-green', 'fas fa-circle-check', 'Approved Sellers', SellerApplication.objects.filter(status=SellerApplication.Status.APPROVED).count()),
            _card('c-red', 'fas fa-circle-xmark', 'Rejected Sellers', SellerApplication.objects.filter(status=SellerApplication.Status.REJECTED).count()),
            _card('c-purple', 'fas fa-file-shield', 'More Info', SellerApplication.objects.filter(status=SellerApplication.Status.MORE_INFO).count()),
        ]
        return _render_admin_overview(
            request,
            nav_group=module,
            section=section,
            title=title,
            subtitle=subtitle,
            summary_cards=summary_cards,
            insights=[
                _insight('Seller approval flow', 'Seller register karega, KYC upload karega, phir admin approve/reject karega.', 'Approval ke baad product add flow open hota hai.'),
                _insight('KYC priority', 'PAN, GST, bank proof, and address proof ko verify karna seller trust ka core hai.', 'Incomplete KYC ko resubmission me bhejo.'),
                _insight('Commission setup', 'Global, seller-wise, category-wise, ya product-wise commission future payout calculation ka base banega.', 'Default 10% simple first version ke liye enough hai.'),
            ],
            quick_actions=quick_actions,
            table_title=title,
            table_subtitle='Seller applications from current database.',
            table_headers=table_headers,
            table_rows=table_rows,
            table_actions=table_actions,
            empty_message='No sellers found for this section.',
            primary_action=_action('Open Sellers', reverse('admin-sellers'), 'primary'),
        )

    if module in {'category-management'}:
        categories = list(_category_breakdown_queryset()[:50])
        table_headers = ['Category', 'Products', 'Sub Categories', 'Admin Products', 'Seller Products', 'Current Stock', 'Status']
        table_rows, table_actions = _category_table_data(categories)
        return _render_admin_overview(
            request,
            nav_group=module,
            section=section,
            title=title,
            subtitle=subtitle,
            summary_cards=[
                _card('c-blue', 'fas fa-tags', 'Categories', snapshot['category_count']),
                _card('c-purple', 'fas fa-sitemap', 'Sub Categories', snapshot['sub_category_count']),
                _card('c-green', 'fas fa-box-open', 'Active Products', snapshot['active_item_count']),
                _card('c-orange', 'fas fa-layer-group', 'Collections', snapshot['active_category_count']),
            ],
            insights=[
                _insight('Category structure', 'Categories decide storefront navigation and seller product placement.', 'Keep photos, order, and names clean.'),
                _insight('Sub-categories', 'Sub-categories decide category-level filtering and product grouping.', 'Keep names and photos clean for customer navigation.'),
            ],
            quick_actions=quick_actions,
            table_title=title,
            table_subtitle='Current category and sub-category structure.',
            table_headers=table_headers,
            table_rows=table_rows,
            table_actions=table_actions,
            empty_message='No data found.',
            primary_action=_action('Manage Categories', reverse('admin-categories'), 'primary'),
        )

    if module in {'payment-management'}:
        transactions = list(_payment_transactions_for_admin_section(section)[:50])
        table_rows, table_actions = _payment_table_data(transactions)
        return _render_admin_overview(
            request,
            nav_group=module,
            section=section,
            title=title,
            subtitle='Live payment status from orders created through checkout.',
            summary_cards=[],
            quick_actions=quick_actions,
            table_title=title,
            table_subtitle='Order payment status, method, amount, and admin actions.',
            table_headers=['Transaction ID', 'Customer', 'Amount', 'Method', 'Status', 'Date'],
            table_rows=table_rows,
            table_actions=table_actions,
            empty_message='No payment records found for this section.',
            primary_action=_action('Open Orders', reverse('admin-orders'), 'primary'),
        )

    if module in {'payout-management'}:
        if section == 'seller-earnings':
            sellers = list(SellerApplication.objects.filter(status=SellerApplication.Status.APPROVED).order_by('-updated_at')[:50])
            table_rows, table_actions = _seller_finance_table_data(sellers)
            table_headers = ['Seller', 'Orders', 'Revenue', 'Commission', 'Net Payable', 'Status']
            table_subtitle = '10% commission and seller earnings calculated from non-cancelled seller sales.'
            primary_action = _action('Open Sellers', reverse('admin-sellers'), 'primary')
        else:
            table_rows, table_actions = _seller_payout_table_data(section)
            table_headers = ['Payout ID', 'Seller', 'Amount', 'Destination', 'Status', 'Requested']
            table_subtitle = 'Seller payout requests and payout history from the database.'
            primary_action = _action('Create Payout', reverse('admin-generic-create', kwargs={'model_key': 'seller-payout'}), 'primary')
        return _render_admin_overview(
            request,
            nav_group=module,
            section=section,
            title=title,
            subtitle='Seller earning and payout workflow.',
            summary_cards=[],
            quick_actions=quick_actions,
            table_title=title,
            table_subtitle=table_subtitle,
            table_headers=table_headers,
            table_rows=table_rows,
            table_actions=table_actions,
            empty_message='No payout records found yet.',
            primary_action=primary_action,
        )

    if module in {'return-refund-management'}:
        return_requests = list(_return_requests_for_admin_section(section)[:50])
        table_rows, table_actions = _return_table_data(return_requests)
        return _render_admin_overview(
            request,
            nav_group=module,
            section=section,
            title=title,
            subtitle='Return and refund rows from order status and payment status.',
            summary_cards=[],
            quick_actions=quick_actions,
            table_title=title,
            table_subtitle='Orders marked returned or refunded appear here automatically.',
            table_headers=['Order ID', 'Customer', 'Reason', 'Refund Amount', 'Return Status', 'Refund Status', 'Pickup', 'Date'],
            table_rows=table_rows,
            table_actions=table_actions,
            empty_message='No return or refund records found for this section.',
            primary_action=_action('Create Return', reverse('admin-generic-create', kwargs={'model_key': 'return-request'}), 'primary'),
        )

    if module in {'coupon-offer-management'}:
        if section == 'banners':
            banners = list(Banner.objects.order_by('display_order', '-updated_at')[:50])
            table_rows, table_actions = _banner_table_data(banners)
            table_headers = ['Title', 'Placement', 'CTA', 'Status', 'Updated']
            empty_message = 'No banners found yet.'
            primary_action = _action('Manage Banners', reverse('admin-banners'), 'primary')
        elif section in {'flash-sales'}:
            table_rows, table_actions = _offer_table_data(Offer.objects.order_by('-updated_at'))
            table_headers = ['Offer', 'Discount', 'Products', 'Start', 'End', 'Status', 'Updated']
            empty_message = 'No offers found yet.'
            primary_action = _action('Add Flash Sale', reverse('admin-generic-create', kwargs={'model_key': 'offer'}), 'primary')
        elif section == 'seller-coupons':
            table_rows, table_actions = _coupon_table_data(Coupon.objects.filter(owner_type=Coupon.OwnerType.SELLER).order_by('-updated_at'))
            table_headers = ['Code', 'Title', 'Owner', 'Discount', 'Min Order', 'Max Discount', 'Start', 'End', 'Usage', 'Status']
            empty_message = 'No seller coupons found yet.'
            primary_action = _action('Add Seller Coupon', reverse('admin-generic-create', kwargs={'model_key': 'coupon'}), 'primary')
        else:
            table_rows, table_actions = _coupon_table_data(Coupon.objects.filter(owner_type=Coupon.OwnerType.ADMIN).order_by('-updated_at'))
            table_headers = ['Code', 'Title', 'Owner', 'Discount', 'Min Order', 'Max Discount', 'Start', 'End', 'Usage', 'Status']
            empty_message = 'No coupons found yet.'
            primary_action = _action('Add Coupon', reverse('admin-generic-create', kwargs={'model_key': 'coupon'}), 'primary')
        return _render_admin_overview(
            request,
            nav_group=module,
            section=section,
            title=title,
            subtitle='Live coupons, offers, and banners from the database.',
            summary_cards=[],
            quick_actions=quick_actions,
            table_title=title,
            table_subtitle='Saved database records with Add, Edit, Delete, Activate and Deactivate actions.',
            table_headers=table_headers,
            table_rows=table_rows,
            table_actions=table_actions,
            empty_message=empty_message,
            primary_action=primary_action,
        )

    if module in {'shipping-management'}:
        table_headers, table_rows, table_actions, model_key = _shipping_model_table_data(section)
        return _render_admin_overview(
            request,
            nav_group=module,
            section=section,
            title=title,
            subtitle='Shipping configuration and tracking records from the database.',
            summary_cards=[],
            quick_actions=quick_actions,
            table_title=title,
            table_subtitle='Saved shipping records only.',
            table_headers=table_headers,
            table_rows=table_rows,
            table_actions=table_actions,
            empty_message='No shipping records found for this section.',
            primary_action=_action(f'Add {GENERIC_ADMIN_MODELS[model_key]["label"]}', reverse('admin-generic-create', kwargs={'model_key': model_key}), 'primary'),
        )

    if module in {'reports-analytics'}:
        extra_filters = []
        summary_cards = []
        if section in {'revenue-reports', 'sales-report'}:
            orders_qs = _apply_order_filters_from_request(request, _orders_for_admin_section('all-orders'))
            orders = list(orders_qs[:100])
            table_rows, table_actions = _order_table_data(orders)
            revenue_qs = orders_qs.exclude(status__in=[Order.Status.CANCELLED, Order.Status.RETURNED])
            summary_cards = [
                _card('c-green', 'fas fa-indian-rupee-sign', 'Total Revenue', _format_currency(revenue_qs.aggregate(total=Sum('total_amount')).get('total') or 0)),
                _card('c-blue', 'fas fa-credit-card', 'Paid Orders', orders_qs.filter(payment_status=Order.PaymentStatus.PAID).count()),
                _card('c-orange', 'fas fa-money-bill-wave', 'COD Orders', orders_qs.filter(payment_method__icontains='Cash').count()),
                _card('c-purple', 'fas fa-globe', 'Online Orders', orders_qs.filter(payment_method__icontains='Online').count()),
            ]
            table_headers = ['Order ID', 'Customer', 'Seller', 'Product Count', 'Amount', 'Payment Status', 'Order Status', 'Date']
            table_title = 'Revenue Reports'
            table_subtitle = 'Order revenue rows generated from saved order records.'
            primary_action = _action('Open Orders', reverse('admin-orders'), 'primary')
            extra_filters = _report_filter_controls(request, {'date', 'seller', 'customer', 'order_status', 'payment_status'})
        elif section in {'order-reports', 'order-report'}:
            orders_qs = _apply_order_filters_from_request(request, _orders_for_admin_section('all-orders'))
            orders = list(orders_qs[:100])
            table_rows, table_actions = _order_table_data(orders)
            summary_cards = [
                _card('c-blue', 'fas fa-receipt', 'Total Orders', orders_qs.count()),
                _card('c-orange', 'fas fa-hourglass-half', 'Pending', orders_qs.filter(status=Order.Status.PENDING).count()),
                _card('c-purple', 'fas fa-truck-fast', 'Shipped', orders_qs.filter(status__in=[Order.Status.SHIPPED, Order.Status.OUT_FOR_DELIVERY]).count()),
                _card('c-green', 'fas fa-circle-check', 'Delivered', orders_qs.filter(status=Order.Status.DELIVERED).count()),
            ]
            table_headers = ['Order ID', 'Customer', 'Seller', 'Product Count', 'Amount', 'Payment Status', 'Order Status', 'Date']
            table_title = 'Order Reports'
            table_subtitle = 'Order status, payment, seller, and amount records from the database.'
            primary_action = _action('Open Orders', reverse('admin-orders'), 'primary')
            extra_filters = _report_filter_controls(request, {'date', 'seller', 'customer', 'order_status', 'payment_status'})
        elif section in {'seller-reports', 'seller-report'}:
            sellers = SellerApplication.objects.filter(status=SellerApplication.Status.APPROVED).order_by('-updated_at')
            seller_id = request.GET.get('seller', '').strip()
            if seller_id:
                sellers = sellers.filter(pk=seller_id)
            sellers = list(sellers[:100])
            table_headers = ['Seller', 'Orders', 'Revenue', 'Commission', 'Net Payable', 'Status']
            table_rows, table_actions = _seller_finance_table_data(sellers)
            summary_cards = [
                _card('c-blue', 'fas fa-store', 'Approved Sellers', SellerApplication.objects.filter(status=SellerApplication.Status.APPROVED).count()),
                _card('c-green', 'fas fa-indian-rupee-sign', 'Seller Sales', _format_currency(OrderItem.objects.filter(seller__in=sellers).aggregate(total=Sum('line_total')).get('total') or 0)),
                _card('c-purple', 'fas fa-percent', 'Commission Rate', '10%'),
                _card('c-orange', 'fas fa-sack-dollar', 'Payout Pending', SellerPayout.objects.filter(status=SellerPayout.Status.PENDING).count()),
            ]
            table_title = 'Seller Reports'
            table_subtitle = 'Seller wise sales, order count, commission and payable records.'
            primary_action = _action('Open Sellers', reverse('admin-sellers'), 'primary')
            extra_filters = _report_filter_controls(request, {'seller'})
        elif section in {'customer-reports', 'customer-report'}:
            customers_qs = (
                User.objects.filter(is_staff=False)
                .annotate(order_total=Count('orders', distinct=True), spend_total=Sum('orders__total_amount'), last_order=Max('orders__created_at'))
                .order_by('-date_joined')
            )
            customer_id = request.GET.get('customer', '').strip()
            date_from = parse_date(request.GET.get('date_from', '').strip())
            date_to = parse_date(request.GET.get('date_to', '').strip())
            if customer_id:
                customers_qs = customers_qs.filter(pk=customer_id)
            if date_from:
                customers_qs = customers_qs.filter(date_joined__date__gte=date_from)
            if date_to:
                customers_qs = customers_qs.filter(date_joined__date__lte=date_to)
            customers = list(customers_qs[:100])
            repeat_count = customers_qs.filter(order_total__gt=1).count()
            summary_cards = [
                _card('c-blue', 'fas fa-users', 'Customers', customers_qs.count()),
                _card('c-green', 'fas fa-user-check', 'Active Customers', customers_qs.filter(is_active=True).count()),
                _card('c-purple', 'fas fa-rotate', 'Repeat Customers', repeat_count),
                _card('c-orange', 'fas fa-bag-shopping', 'Orders', Order.objects.filter(customer__in=customers_qs).count()),
            ]
            table_headers = ['Customer', 'Email', 'Orders', 'Spend', 'Joined', 'Status']
            table_rows = [
                [
                    _cell(customer.get_full_name() or customer.username),
                    _cell(customer.email or 'No email'),
                    _cell(customer.order_total or 0),
                    _cell(_format_currency(customer.spend_total or 0), 'success' if customer.spend_total else ''),
                    _cell(customer.date_joined.strftime('%d %b %Y')),
                    _cell('Active' if customer.is_active else 'Inactive', 'success' if customer.is_active else 'danger'),
                ]
                for customer in customers
            ]
            table_actions = [
                [
                    _action('Details', reverse('admin-customer-detail', kwargs={'pk': customer.pk}), 'view'),
                    _action('Edit', reverse('admin-customer-edit', kwargs={'pk': customer.pk}), 'edit'),
                    _action('Delete', reverse('admin-customer-delete', kwargs={'pk': customer.pk}), 'delete'),
                ]
                for customer in customers
            ]
            table_title = 'Customer Reports'
            table_subtitle = 'Customer account, order count, and spend records.'
            primary_action = _action('Open Customers', reverse('admin-customers'), 'primary')
            extra_filters = _report_filter_controls(request, {'date', 'customer'})
        elif section in {'product-reports', 'product-report'}:
            products_qs = _apply_product_filters_from_request(
                request,
                SpiceItem.objects.select_related('category', 'seller').annotate(
                    sold_units=Sum('order_items__quantity'),
                    sales_value=Sum('order_items__line_total'),
                ).order_by('-sold_units', 'stock', 'name'),
            )
            products = list(products_qs[:100])
            table_headers = ['Product', 'Seller', 'Category', 'Sold Units', 'Sales', 'Stock', 'Status']
            table_rows = [
                [
                    _cell(product.name),
                    _cell(product.owner_label),
                    _cell(product.category.name if product.category else 'General'),
                    _cell(product.sold_units or 0),
                    _cell(_format_currency(product.sales_value or 0)),
                    _cell(product.stock, 'danger' if product.stock <= 0 else 'warning' if product.stock <= 10 else 'success'),
                    _cell('Active' if product.is_active else 'Hidden', 'success' if product.is_active else 'danger'),
                ]
                for product in products
            ]
            table_actions = [_product_admin_actions(product, include_stock=True) for product in products]
            summary_cards = [
                _card('c-blue', 'fas fa-box-open', 'Products', products_qs.count()),
                _card('c-green', 'fas fa-chart-line', 'Units Sold', products_qs.aggregate(total=Sum('sold_units')).get('total') or 0),
                _card('c-orange', 'fas fa-triangle-exclamation', 'Low Stock', products_qs.filter(stock__gt=0, stock__lte=10).count()),
                _card('c-red', 'fas fa-boxes-packing', 'Out of Stock', products_qs.filter(stock=0).count()),
            ]
            table_title = 'Product Reports'
            table_subtitle = 'Best selling, low stock, and product wise sales records.'
            primary_action = _action('Open Products', reverse('admin-items'), 'primary')
            extra_filters = _report_filter_controls(request, {'seller', 'category', 'product'})
        elif section in {'commission-report'}:
            sellers = list(SellerApplication.objects.filter(status=SellerApplication.Status.APPROVED).order_by('-updated_at')[:50])
            table_headers = ['Seller', 'Orders', 'Revenue', 'Commission', 'Net Payable', 'Status']
            table_rows, table_actions = _seller_finance_table_data(sellers)
            table_title = title
            table_subtitle = 'Seller earning, commission, and payable records from completed order lines.'
            primary_action = _action('Open Sellers', reverse('admin-sellers'), 'primary')
            extra_filters = _report_filter_controls(request, {'seller'})
            summary_cards = [
                _card('c-purple', 'fas fa-percent', 'Commission Rate', '10%'),
                _card('c-green', 'fas fa-indian-rupee-sign', 'Admin Commission', _format_currency(sum((item.commission_amount for item in OrderItem.objects.select_related('order').exclude(order__status__in=[Order.Status.CANCELLED, Order.Status.RETURNED])), Decimal('0')))),
                _card('c-blue', 'fas fa-store', 'Seller Commission', _format_currency(sum((item.seller_earning for item in OrderItem.objects.select_related('order').exclude(order__status__in=[Order.Status.CANCELLED, Order.Status.RETURNED])), Decimal('0')))),
                _card('c-orange', 'fas fa-receipt', 'Order Lines', OrderItem.objects.count()),
            ]
        elif section in {'payout-report'}:
            table_headers = ['Payout ID', 'Seller', 'Amount', 'Destination', 'Status', 'Requested']
            table_rows, table_actions = _seller_payout_table_data()
            table_title = 'Payout Report'
            table_subtitle = 'Seller payout pending, paid, failed, and payout history.'
            primary_action = _action('Create Payout', reverse('admin-generic-create', kwargs={'model_key': 'seller-payout'}), 'primary')
            summary_cards = [
                _card('c-orange', 'fas fa-clock', 'Pending', SellerPayout.objects.filter(status=SellerPayout.Status.PENDING).count()),
                _card('c-green', 'fas fa-circle-check', 'Paid', SellerPayout.objects.filter(status=SellerPayout.Status.PAID).count()),
                _card('c-red', 'fas fa-triangle-exclamation', 'Failed', SellerPayout.objects.filter(status=SellerPayout.Status.FAILED).count()),
                _card('c-blue', 'fas fa-indian-rupee-sign', 'Paid Amount', _format_currency(SellerPayout.objects.filter(status=SellerPayout.Status.PAID).aggregate(total=Sum('amount')).get('total') or 0)),
            ]
            extra_filters = _report_filter_controls(request, {'seller'})
        elif section in {'refund-report'}:
            returns_qs = _return_requests_for_admin_section(section)
            date_from = parse_date(request.GET.get('date_from', '').strip())
            date_to = parse_date(request.GET.get('date_to', '').strip())
            seller_id = request.GET.get('seller', '').strip()
            if date_from:
                returns_qs = returns_qs.filter(created_at__date__gte=date_from)
            if date_to:
                returns_qs = returns_qs.filter(created_at__date__lte=date_to)
            if seller_id:
                returns_qs = returns_qs.filter(order__items__seller_id=seller_id).distinct()
            returns = list(returns_qs[:100])
            table_headers = ['Order ID', 'Customer', 'Reason', 'Refund Amount', 'Return Status', 'Refund Status', 'Pickup', 'Date']
            table_rows, table_actions = _return_table_data(returns)
            table_title = 'Refund Report'
            table_subtitle = 'Return and refund request records from the database.'
            primary_action = _action('Open Orders', reverse('admin-orders'), 'primary')
            summary_cards = [
                _card('c-orange', 'fas fa-clock', 'Requested', returns_qs.filter(refund_status=ReturnRequest.RefundStatus.REQUESTED).count()),
                _card('c-green', 'fas fa-circle-check', 'Completed', returns_qs.filter(refund_status=ReturnRequest.RefundStatus.COMPLETED).count()),
                _card('c-red', 'fas fa-ban', 'Rejected/Failed', returns_qs.filter(refund_status__in=[ReturnRequest.RefundStatus.REJECTED, ReturnRequest.RefundStatus.FAILED]).count()),
                _card('c-blue', 'fas fa-indian-rupee-sign', 'Refund Amount', _format_currency(returns_qs.aggregate(total=Sum('refund_amount')).get('total') or 0)),
            ]
            extra_filters = _report_filter_controls(request, {'date', 'seller'})
        else:
            table_headers = ['Record', 'Status', 'Updated']
            table_rows = []
            table_actions = []
            table_title = title
            table_subtitle = 'Live report rows from saved database records.'
            primary_action = _action('Open Dashboard', reverse('admin-dashboard'), 'primary')
        return _render_admin_overview(
            request,
            nav_group=module,
            section=section,
            title=title,
            subtitle='Report tables generated from current database records.',
            summary_cards=summary_cards,
            quick_actions=quick_actions,
            table_title=table_title,
            table_subtitle=table_subtitle,
            table_headers=table_headers,
            table_rows=table_rows,
            table_actions=table_actions,
            empty_message='No report records found for this section.',
            primary_action=primary_action,
            extra_filters=extra_filters,
        )

    if module == 'content-management':
        if section == 'home-banners':
            banners = list(Banner.objects.order_by('display_order', '-updated_at')[:50])
            table_rows, table_actions = _banner_table_data(banners)
            table_headers = ['Title', 'Placement', 'CTA', 'Status', 'Updated']
            primary_action = _action('Manage Banners', reverse('admin-website-edit'), 'primary')
            empty_message = 'No banners found yet.'
        else:
            table_rows, table_actions = _content_table_data(section)
            table_headers = ['Page', 'Title', 'Status', 'Updated']
            primary_action = _action('Add Content', reverse('admin-generic-create', kwargs={'model_key': 'content'}), 'primary')
            empty_message = 'No content records found for this section.'
        return _render_admin_overview(
            request,
            nav_group=module,
            section=section,
            title=title,
            subtitle='Editable content records from the database.',
            summary_cards=[],
            quick_actions=quick_actions,
            table_title=title,
            table_subtitle='Static content pages are editable from admin.',
            table_headers=table_headers,
            table_rows=table_rows,
            table_actions=table_actions,
            empty_message=empty_message,
            primary_action=primary_action,
        )

    if module == 'reviews-ratings':
        table_headers, table_rows, table_actions, model_key = _review_table_data(section)
        return _render_admin_overview(
            request,
            nav_group=module,
            section=section,
            title=title,
            subtitle='Customer review moderation from database records.',
            summary_cards=[],
            quick_actions=quick_actions,
            table_title=title,
            table_subtitle='View, approve, hide, and delete reviews.',
            table_headers=table_headers,
            table_rows=table_rows,
            table_actions=table_actions,
            empty_message='No reviews found for this section.',
            primary_action=_action(f'Add {GENERIC_ADMIN_MODELS[model_key]["label"]}', reverse('admin-generic-create', kwargs={'model_key': model_key}), 'primary'),
        )

    if module == 'support-tickets':
        table_rows, table_actions = _ticket_table_data(section)
        return _render_admin_overview(
            request,
            nav_group=module,
            section=section,
            title=title,
            subtitle='Support tickets and complaints from database records.',
            summary_cards=[],
            quick_actions=quick_actions,
            table_title=title,
            table_subtitle='View, reply, and close tickets.',
            table_headers=['Ticket ID', 'Type', 'Subject', 'User', 'Status', 'Updated'],
            table_rows=table_rows,
            table_actions=table_actions,
            empty_message='No tickets found for this section.',
            primary_action=_action('Add Ticket', reverse('admin-generic-create', kwargs={'model_key': 'ticket'}), 'primary'),
        )

    if module == 'notification-management':
        table_headers, table_rows, table_actions, model_key = _notification_table_data(section)
        return _render_admin_overview(
            request,
            nav_group=module,
            section=section,
            title=title,
            subtitle='Push notification history plus email and SMS templates.',
            summary_cards=[],
            quick_actions=quick_actions,
            table_title=title,
            table_subtitle='Create, edit, delete, activate, deactivate, and send notification records.',
            table_headers=table_headers,
            table_rows=table_rows,
            table_actions=table_actions,
            empty_message='No notification templates found for this section.',
            primary_action=_action(f'Create {GENERIC_ADMIN_MODELS[model_key]["label"]}', reverse('admin-generic-create', kwargs={'model_key': model_key}), 'primary'),
        )

    if module == 'website-settings':
        table_rows, table_actions = _website_setting_table_data(section)
        return _render_admin_overview(
            request,
            nav_group=module,
            section=section,
            title=title,
            subtitle='Store configuration, payment, email, SMS, SEO, logo and branding settings.',
            summary_cards=[],
            quick_actions=quick_actions,
            table_title=title,
            table_subtitle='Settings are database-backed key/value records.',
            table_headers=['Group', 'Label', 'Value', 'Status'],
            table_rows=table_rows,
            table_actions=table_actions,
            empty_message='No website settings found for this section.',
            primary_action=_action('Add Setting', reverse('admin-generic-create', kwargs={'model_key': 'website-setting'}), 'primary'),
        )

    if module in {'reviews-ratings', 'support-tickets', 'notification-management', 'website-settings'}:
        return _render_admin_overview(
            request,
            nav_group=module,
            section=section,
            title=title,
            subtitle='This section is ready for live records once its database model is added.',
            summary_cards=[],
            quick_actions=quick_actions,
            table_title=title,
            table_subtitle='Fake data has been removed from this section.',
            table_headers=table_headers,
            table_rows=[],
            table_actions=[],
            empty_message='No live records are stored for this section yet.',
            primary_action=_action('Back to Dashboard', reverse('admin-dashboard'), 'primary'),
        )

    customers_count = User.objects.filter(is_staff=False).count()
    sellers_count = SellerApplication.objects.count()
    admin_count = User.objects.filter(is_staff=True).count()
    summary_cards = [
        _card('c-blue', 'fas fa-users', 'Customers', customers_count),
        _card('c-green', 'fas fa-store', 'Sellers', sellers_count),
        _card('c-orange', 'fas fa-boxes-stacked', 'Products', snapshot['item_count']),
        _card('c-red', 'fas fa-triangle-exclamation', 'Open Alerts', snapshot['low_stock_count'] + snapshot['out_stock_count']),
    ]

    if module == 'user-management':
        users = User.objects.filter(is_staff=(section == 'admin-users')).order_by('-date_joined')[:12]
        if section != 'admin-users':
            users = User.objects.filter(is_staff=False).order_by('-date_joined')[:12]
        table_headers = ['Name', 'Username', 'Email', 'Role', 'Joined']
        table_rows = [
            [
                _cell(user.first_name or user.username),
                _cell(user.username),
                _cell(user.email or 'Not provided'),
                _cell('Admin' if user.is_staff else 'Customer', 'success' if user.is_staff else 'info'),
                _cell(user.date_joined.strftime('%d %b %Y')),
            ]
            for user in users
        ]
        summary_cards = [
            _card('c-blue', 'fas fa-user-group', 'Customers', customers_count),
            _card('c-green', 'fas fa-store', 'Sellers', sellers_count),
            _card('c-purple', 'fas fa-user-shield', 'Admin Users', admin_count),
            _card('c-orange', 'fas fa-user-plus', 'Pending Sellers', SellerApplication.objects.filter(status=SellerApplication.Status.PENDING).count()),
        ]

    return _render_admin_overview(
        request,
        nav_group=module,
        section=section,
        title=title,
        subtitle=subtitle,
        summary_cards=summary_cards,
        insights=[
            _insight('Live data only', 'This workspace shows saved database records where a model exists.', 'Empty sections stay empty until records are created.'),
        ],
        quick_actions=quick_actions,
        table_title=title,
        table_subtitle='Live records for this module.',
        table_headers=table_headers,
        table_rows=table_rows,
        table_actions=table_actions,
        empty_message=empty_message,
        primary_action=_action('Back to Dashboard', reverse('admin-dashboard'), 'primary'),
    )


@user_passes_test(_staff_required, login_url='login')
def admin_dashboard(request):
    now = timezone.now()
    day_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    customer_count = User.objects.filter(is_staff=False).count()
    seller_count = SellerApplication.objects.count()
    pending_seller_count = SellerApplication.objects.filter(status=SellerApplication.Status.PENDING).count()
    pending_product_count = SpiceItem.objects.filter(approval_status=SpiceItem.ApprovalStatus.PENDING).count()
    order_total = Order.objects.count()
    revenue_total = Order.objects.exclude(
        status__in=[Order.Status.CANCELLED, Order.Status.RETURNED],
    ).aggregate(total=Sum('total_amount')).get('total') or Decimal('0')
    dashboard_cards = [
        {'theme': 'c-blue', 'icon': 'fas fa-user-group', 'label': 'Total Customers', 'value': customer_count, 'href': reverse('admin-customers')},
        {'theme': 'c-green', 'icon': 'fas fa-store', 'label': 'Total Sellers', 'value': seller_count, 'href': reverse('admin-sellers')},
        {'theme': 'c-orange', 'icon': 'fas fa-hourglass-half', 'label': 'Seller Requests', 'value': pending_seller_count, 'href': _section_url('seller-management', 'seller-requests')},
        {'theme': 'c-purple', 'icon': 'fas fa-boxes-stacked', 'label': 'Total Products', 'value': SpiceItem.objects.count(), 'href': reverse('admin-items')},
        {'theme': 'c-red', 'icon': 'fas fa-clock', 'label': 'Pending Products', 'value': pending_product_count, 'href': _section_url('product-management', 'pending-products')},
        {'theme': 'c-darkblue', 'icon': 'fas fa-bag-shopping', 'label': 'Total Orders', 'value': order_total, 'href': reverse('admin-orders')},
        {'theme': 'c-green', 'icon': 'fas fa-indian-rupee-sign', 'label': 'Revenue', 'value': _format_currency(revenue_total), 'href': _section_url('reports-analytics', 'sales-report')},
        {'theme': 'c-red', 'icon': 'fas fa-triangle-exclamation', 'label': 'Low Stock', 'value': SpiceItem.objects.filter(is_active=True, stock__gt=0, stock__lte=10).count(), 'href': _section_url('inventory-management', 'low-stock-products')},
    ]
    dashboard_charts = [
        {
            'title': 'Today Updates',
            'icon': 'fas fa-calendar-day',
            'bars': [
                {'label': 'Products', 'value': SpiceItem.objects.filter(updated_at__gte=day_start).count()},
                {'label': 'Sellers', 'value': SellerApplication.objects.filter(updated_at__gte=day_start).count()},
                {'label': 'Customers', 'value': User.objects.filter(date_joined__gte=day_start).count()},
                {'label': 'Banners', 'value': Banner.objects.filter(updated_at__gte=day_start).count()},
            ],
        },
        {
            'title': 'Product Updates',
            'icon': 'fas fa-box-open',
            'kind': 'donut',
            'bars': [
                {'label': 'Active', 'value': SpiceItem.objects.filter(is_active=True).count()},
                {'label': 'Pending', 'value': pending_product_count},
                {'label': 'Featured', 'value': SpiceItem.objects.filter(is_featured=True).count()},
                {'label': 'Hidden', 'value': SpiceItem.objects.filter(is_active=False).count()},
            ],
        },
        {
            'title': 'Seller Updates',
            'icon': 'fas fa-store',
            'bars': [
                {'label': 'Pending', 'value': pending_seller_count},
                {'label': 'Approved', 'value': SellerApplication.objects.filter(status=SellerApplication.Status.APPROVED).count()},
                {'label': 'Rejected', 'value': SellerApplication.objects.filter(status=SellerApplication.Status.REJECTED).count()},
                {'label': 'Month', 'value': SellerApplication.objects.filter(created_at__gte=month_start).count()},
            ],
        },
        {
            'title': 'Inventory Health',
            'icon': 'fas fa-warehouse',
            'kind': 'line',
            'bars': [
                {'label': 'High', 'value': SpiceItem.objects.filter(stock__gt=35).count()},
                {'label': 'Medium', 'value': SpiceItem.objects.filter(stock__gt=10, stock__lte=35).count()},
                {'label': 'Low', 'value': SpiceItem.objects.filter(stock__gt=0, stock__lte=10).count()},
                {'label': 'Out', 'value': SpiceItem.objects.filter(stock=0).count()},
            ],
        },
    ]
    for chart in dashboard_charts:
        max_value = max([bar['value'] for bar in chart['bars']] or [1]) or 1
        for bar in chart['bars']:
            bar['height'] = 18 + int((bar['value'] / max_value) * 118)
        if chart.get('kind') == 'donut':
            colors = ['#2563eb', '#f59e0b', '#16a66a', '#e54848']
            total = sum(bar['value'] for bar in chart['bars']) or 1
            cursor = 0
            segments = []
            for index, bar in enumerate(chart['bars']):
                next_cursor = cursor + (bar['value'] / total * 100)
                bar['color'] = colors[index % len(colors)]
                segments.append(f'{bar["color"]} {cursor:.2f}% {next_cursor:.2f}%')
                cursor = next_cursor
            chart['total'] = total if total != 1 or any(bar['value'] for bar in chart['bars']) else 0
            chart['gradient'] = f'conic-gradient({", ".join(segments)})'
        if chart.get('kind') == 'line':
            width = 220
            height = 122
            step = width / max(len(chart['bars']) - 1, 1)
            line_points = []
            for index, bar in enumerate(chart['bars']):
                x = int(index * step)
                y = int(height - ((bar['value'] / max_value) * 92) - 15)
                line_points.append({'x': x, 'y': y, **bar})
            chart['line_points'] = line_points
            chart['points'] = ' '.join(f'{point["x"]},{point["y"]}' for point in line_points)

    return render(
        request,
        'admin_panel/dashboard.html',
        _admin_context(
            'dashboard',
            'dashboard',
            latest_items=SpiceItem.objects.select_related('category', 'seller').order_by('-updated_at')[:5],
            dashboard_cards=dashboard_cards,
            dashboard_charts=dashboard_charts,
        ),
    )


@user_passes_test(_staff_required, login_url='login')
def admin_collections(request):
    snapshot = _admin_snapshot()
    collections = list(
        Category.objects.annotate(
            active_total=Count('items', filter=Q(items__is_active=True), distinct=True),
            featured_total=Count('items', filter=Q(items__is_featured=True, items__is_active=True), distinct=True),
        ).order_by('display_order', 'name')
    )
    featured_collections = sum(1 for collection in collections if collection.featured_total)
    top_collection = max(collections, key=lambda collection: collection.active_total or 0, default=None)
    recently_updated = max(collections, key=lambda collection: collection.updated_at, default=None)

    insights = [
        _insight(
            'Largest collection',
            (
                f'{top_collection.name} currently holds {top_collection.active_total} active products.'
                if top_collection
                else 'Create your first category to start curating collections.'
            ),
            'Use featured items to shape homepage highlights.',
        ),
        _insight(
            'Merchandising tip',
            f'{featured_collections} collections already contain featured products for spotlight placement.',
            'Mix banners + collections for stronger category storytelling.',
        ),
        _insight(
            'Latest refresh',
            (
                f'{recently_updated.name} was updated most recently on {recently_updated.updated_at:%d %b %Y}.'
                if recently_updated
                else 'No collection edits yet.'
            ),
            'Recent edits usually deserve a quick storefront check.',
        ),
    ]

    table_rows = [
        [
            _cell(collection.name),
            _cell(collection.active_total),
            _cell(collection.featured_total),
            _cell('Active' if collection.is_active else 'Hidden', 'success' if collection.is_active else 'danger'),
            _cell(collection.updated_at.strftime('%d %b %Y')),
        ]
        for collection in collections
    ]

    return _render_admin_overview(
        request,
        nav_group='category-management',
        section='categories',
        title='Collections',
        subtitle='Category-led merchandising blocks that shape how the storefront feels and sells.',
        summary_cards=[
            _card('c-blue', 'fas fa-layer-group', 'Live Collections', len(collections)),
            _card('c-red', 'fas fa-star', 'Featured Collections', featured_collections),
            _card('c-purple', 'fas fa-box-open', 'Featured Products', snapshot['featured_item_count']),
            _card('c-orange', 'fas fa-images', 'Banners Supporting Collections', snapshot['active_banner_count']),
        ],
        insights=insights,
        quick_actions=[
            _action('Manage Categories', reverse('admin-categories'), 'primary'),
            _action('Add Product', reverse('admin-item-create')),
            _action('Update Banners', reverse('admin-banners')),
            _action('Open Store', reverse('home')),
        ],
        table_title='Collection breakdown',
        table_subtitle='Review active product counts and featured merchandising per collection.',
        table_headers=['Collection', 'Active Items', 'Featured Items', 'Status', 'Updated'],
        table_rows=table_rows,
        empty_message='No collections available yet. Add categories to start building curated sections.',
        primary_action=_action('Go to Categories', reverse('admin-categories'), 'primary'),
    )


@user_passes_test(_staff_required, login_url='login')
def admin_orders(request):
    orders = _filtered_admin_orders(request)
    paginator = Paginator(orders, 30)
    page_obj = paginator.get_page(request.GET.get('page'))
    return render(
        request,
        'admin_panel/admin_orders.html',
        _admin_context(
            'order-management',
            'all-orders',
            orders=page_obj.object_list,
            page_obj=page_obj,
            summary=_order_summary_counts(Order.objects.all()),
            status_choices=Order.Status.choices,
            payment_status_choices=Order.PaymentStatus.choices,
            sellers=SellerApplication.objects.filter(status=SellerApplication.Status.APPROVED).order_by('store_name'),
            filters=request.GET,
        ),
    )


@user_passes_test(_staff_required, login_url='login')
def admin_order_detail(request, pk):
    order = get_object_or_404(
        Order.objects.select_related('customer').prefetch_related('items__seller', 'items__product', 'items__quantity_option'),
        pk=pk,
    )
    if not order.is_seen_by_admin:
        order.is_seen_by_admin = True
        order.save(update_fields=['is_seen_by_admin', 'updated_at'])
    return render(
        request,
        'admin_panel/admin_order_detail.html',
        _admin_context(
            'order-management',
            'all-orders',
            order=order,
            order_items=order.items.all(),
            timeline_steps=_order_timeline(order),
            status_choices=Order.Status.choices,
        ),
    )


@user_passes_test(_staff_required, login_url='login')
def admin_order_detail_by_order_id(request, order_id):
    order = get_object_or_404(
        Order.objects.select_related('customer').prefetch_related('items__seller', 'items__product', 'items__quantity_option', 'status_history', 'payment'),
        _order_lookup_filter(order_id),
    )
    return admin_order_detail(request, order.pk)


@user_passes_test(_staff_required, login_url='login')
@require_http_methods(['POST'])
def admin_order_status_update_by_order_id(request, order_id):
    order = get_object_or_404(Order, _order_lookup_filter(order_id))
    status = request.POST.get('status', '').strip()
    note = request.POST.get('note', '').strip()
    if status not in {choice[0] for choice in Order.Status.choices}:
        messages.error(request, 'Invalid order status.')
        return redirect('admin-order-detail', pk=order.pk)
    _set_order_status(order, status, request.user, note or 'Admin status update')
    messages.success(request, f'{order.order_number} updated to {dict(Order.Status.choices).get(status)}.')
    return redirect('admin-order-detail', pk=order.pk)


@user_passes_test(_staff_required, login_url='login')
def admin_order_notifications(request):
    notifications = OrderNotification.objects.filter(audience=OrderNotification.Audience.ADMIN).select_related('order')
    read_id = request.GET.get('read_id') or request.GET.get('notification_id')
    if read_id and str(read_id).isdigit():
        selected = notifications.filter(pk=read_id).first()
        if selected:
            selected.is_read = True
            selected.save(update_fields=['is_read', 'updated_at'])
            if selected.order_id:
                Order.objects.filter(pk=selected.order_id).update(is_seen_by_admin=True)
    mark_read = request.GET.get('mark_read') == '1'
    if mark_read:
        notifications.filter(is_read=False).update(is_read=True)
        Order.objects.filter(is_seen_by_admin=False).update(is_seen_by_admin=True)
    unread_notifications = notifications.filter(is_read=False)
    return JsonResponse(
        {
            'unread_count': notifications.filter(is_read=False).count(),
            'notifications': [
                _order_notification_payload(notification, OrderNotification.Audience.ADMIN)
                for notification in unread_notifications[:12]
            ],
        }
    )


@user_passes_test(_staff_required, login_url='login')
def admin_order_edit(request, pk):
    order = get_object_or_404(Order, pk=pk)
    old_status = order.status
    form = AdminOrderForm(request.POST or None, instance=order)
    if request.method == 'POST' and form.is_valid():
        updated_order = form.save(commit=False)
        new_status = updated_order.status
        updated_order.status = old_status
        updated_order.save()
        if old_status != new_status:
            _set_order_status(updated_order, new_status, request.user, updated_order.admin_note or 'Admin edit form update')
        messages.success(request, f'Order {order.order_number} updated successfully.')
        return redirect('admin-order-detail', pk=order.pk)

    return _render_admin_form_page(
        request,
        'order-management',
        'all-orders',
        title=f'Edit Order: {order.order_number}',
        subtitle='Update order status, payment state, shipping address, and admin note.',
        form=form,
        back_url='admin-orders',
    )


@user_passes_test(_staff_required, login_url='login')
@require_http_methods(['GET', 'POST'])
def admin_order_delete(request, pk):
    order = get_object_or_404(Order, pk=pk)
    if request.method == 'POST':
        order.delete()
        messages.success(request, 'Order deleted successfully.')
        return redirect('admin-orders')

    return render(
        request,
        'admin_panel/confirm_delete.html',
        _admin_context(
            'order-management',
            'all-orders',
            title='Delete Order',
            object_label=order.order_number,
            back_url='admin-orders',
        ),
    )


@user_passes_test(_staff_required, login_url='login')
def admin_returns(request):
    return_requests = list(_return_requests_for_admin_section('return-requests')[:50])
    table_rows, table_actions = _return_table_data(return_requests)

    return _render_admin_overview(
        request,
        nav_group='return-refund-management',
        section='return-requests',
        title='Returns',
        subtitle='Returned and refunded order rows from the current database.',
        summary_cards=[],
        insights=[],
        quick_actions=[
            _action('Open Customers', reverse('admin-customers'), 'primary'),
            _action('Inventory Report', reverse('admin-report-inventory')),
            _action('Website Edit', reverse('admin-website-edit')),
        ],
        table_title='Return records',
        table_subtitle='Orders marked Returned or Refunded appear here automatically.',
        table_headers=['Order ID', 'Customer', 'Reason', 'Refund Amount', 'Return Status', 'Refund Status', 'Pickup', 'Date'],
        table_rows=table_rows,
        table_actions=table_actions,
        empty_message='No return records found yet.',
        primary_action=_action('Create Return', reverse('admin-generic-create', kwargs={'model_key': 'return-request'}), 'primary'),
    )


def _order_invoice_response(order):
    lines = [
        '<!doctype html><html><head><title>Invoice</title></head><body>',
        f'<h1>Invoice {order.order_number}</h1>',
        f'<p>Customer: {order.customer_name}</p>',
        f'<p>Date: {order.created_at:%d %b %Y}</p>',
        '<table border="1" cellpadding="8" cellspacing="0"><thead><tr><th>Product</th><th>Qty</th><th>Unit</th><th>Total</th></tr></thead><tbody>',
    ]
    for item in order.items.all():
        lines.append(f'<tr><td>{item.product_name}</td><td>{item.quantity}</td><td>{item.unit_price}</td><td>{item.line_total}</td></tr>')
    lines.extend([
        '</tbody></table>',
        f'<h2>Total: {_format_currency(order.total_amount)}</h2>',
        '</body></html>',
    ])
    return HttpResponse(''.join(lines))


@user_passes_test(_staff_required, login_url='login')
def admin_order_invoice(request, pk):
    order = get_object_or_404(Order.objects.prefetch_related('items'), pk=pk)
    return _order_invoice_response(order)


@user_passes_test(_staff_required, login_url='login')
def admin_payment_detail(request, pk):
    payment = get_object_or_404(PaymentTransaction.objects.select_related('order', 'customer'), pk=pk)
    customer_name = payment.customer.first_name or payment.customer.username if payment.customer else 'Unknown'
    return _render_admin_overview(
        request,
        nav_group='payment-management',
        section='all-payments',
        title=payment.transaction_id,
        subtitle='Payment transaction detail.',
        summary_cards=[],
        table_title='Transaction detail',
        table_subtitle='Saved payment record.',
        table_headers=['Field', 'Value'],
        table_rows=[
            [_cell('Transaction ID'), _cell(payment.transaction_id)],
            [_cell('Customer'), _cell(customer_name)],
            [_cell('Order'), _cell(payment.order.order_number if payment.order else 'Not linked')],
            [_cell('Amount'), _cell(_format_currency(payment.amount))],
            [_cell('Method'), _cell(payment.method)],
            [_cell('Status'), _cell(payment.get_status_display(), payment.status_tone)],
            [_cell('Gateway Reference'), _cell(payment.gateway_reference or 'Not set')],
        ],
        table_actions=[],
        primary_action=_action('Back to Payments', _section_url('payment-management', 'all-payments'), 'primary'),
    )


@user_passes_test(_staff_required, login_url='login')
@require_http_methods(['POST'])
def admin_payment_status(request, pk, status):
    payment = get_object_or_404(PaymentTransaction.objects.select_related('order'), pk=pk)
    valid_statuses = {choice[0] for choice in PaymentTransaction.Status.choices}
    if status not in valid_statuses:
        messages.error(request, 'Invalid payment status.')
        return redirect(request.POST.get('next') or _section_url('payment-management', 'all-payments'))
    payment.status = status
    payment.save(update_fields=['status', 'updated_at'])
    if payment.order and status == PaymentTransaction.Status.REFUNDED:
        payment.order.payment_status = Order.PaymentStatus.REFUNDED
        payment.order.save(update_fields=['payment_status', 'updated_at'])
        Payment.objects.filter(order=payment.order).update(status=Payment.Status.REFUNDED, updated_at=timezone.now())
    messages.success(request, 'Payment status updated.')
    return redirect(request.POST.get('next') or _section_url('payment-management', 'all-payments'))


@user_passes_test(_staff_required, login_url='login')
def admin_return_detail(request, pk):
    return_request = get_object_or_404(ReturnRequest.objects.select_related('order', 'customer'), pk=pk)
    customer_name = return_request.customer.first_name or return_request.customer.username if return_request.customer else return_request.order.customer_name
    return _render_admin_overview(
        request,
        nav_group='return-refund-management',
        section='return-requests',
        title=f'Return {return_request.order.order_number}',
        subtitle='Return request detail.',
        summary_cards=[],
        table_title='Return detail',
        table_subtitle='Saved return request record.',
        table_headers=['Field', 'Value'],
        table_rows=[
            [_cell('Order'), _cell(return_request.order.order_number)],
            [_cell('Customer'), _cell(customer_name)],
            [_cell('Reason'), _cell(return_request.reason)],
            [_cell('Details'), _cell(return_request.details or 'Not set')],
            [_cell('Proof'), _cell(return_request.proof_source or 'Not uploaded')],
            [_cell('Refund Amount'), _cell(_format_currency(return_request.refund_amount))],
            [_cell('Return Status'), _cell(return_request.get_status_display(), return_request.status_tone)],
            [_cell('Refund Status'), _cell(return_request.get_refund_status_display(), return_request.refund_tone)],
            [_cell('Pickup'), _cell(return_request.pickup_status)],
            [_cell('Admin Note'), _cell(return_request.admin_note or 'No note')],
        ],
        table_actions=[],
        primary_action=_action('Back to Returns', _section_url('return-refund-management', 'return-requests'), 'primary'),
    )


@user_passes_test(_staff_required, login_url='login')
@require_http_methods(['POST'])
def admin_return_status(request, pk, status):
    return_request = get_object_or_404(ReturnRequest.objects.select_related('order'), pk=pk)
    valid_statuses = {choice[0] for choice in ReturnRequest.Status.choices}
    if status not in valid_statuses:
        messages.error(request, 'Invalid return status.')
        return redirect(request.POST.get('next') or _section_url('return-refund-management', 'return-requests'))
    return_request.status = status
    if status == ReturnRequest.Status.APPROVED:
        return_request.refund_status = ReturnRequest.RefundStatus.APPROVED
    if status == ReturnRequest.Status.REJECTED:
        return_request.refund_status = ReturnRequest.RefundStatus.REJECTED
    return_request.processed_by = request.user
    return_request.processed_at = timezone.now()
    return_request.save(update_fields=['status', 'refund_status', 'processed_by', 'processed_at', 'updated_at'])
    _process_return_side_effects(return_request, request.user)
    messages.success(request, 'Return request status updated.')
    return redirect(request.POST.get('next') or _section_url('return-refund-management', 'return-requests'))


@user_passes_test(_staff_required, login_url='login')
def admin_shipping(request):
    snapshot = _admin_snapshot()
    pending_shipments = Order.objects.filter(status__in=[Order.Status.PACKED, Order.Status.SHIPPED, Order.Status.OUT_FOR_DELIVERY]).count()
    serviceable_count = DeliveryArea.objects.filter(is_active=True, is_serviceable=True).count()
    courier_count = CourierPartner.objects.filter(is_active=True).count()
    tracking_count = ShipmentTracking.objects.count()
    table_headers, table_rows, table_actions, model_key = _shipping_model_table_data('tracking-management')

    return _render_admin_overview(
        request,
        nav_group='shipping-management',
        section='tracking-management',
        title='Tracking Management',
        subtitle='Courier assignments and shipment status for real orders.',
        summary_cards=[
            _card('c-blue', 'fas fa-truck-fast', 'Shipping Queue', pending_shipments),
            _card('c-red', 'fas fa-route', 'Tracking Records', tracking_count),
            _card('c-purple', 'fas fa-map-location-dot', 'Serviceable Areas', serviceable_count),
            _card('c-green', 'fas fa-route', 'Courier Partners', courier_count),
        ],
        insights=[
            _insight('Tracking records', f'{tracking_count} shipment tracking records are stored right now.', 'Courier partner and tracking tables stay database-driven.'),
            _insight('Delivery coverage', f'{serviceable_count} active serviceable delivery areas are configured.', 'Checkout validates pincodes once areas exist.'),
            _insight('Status flow', 'Pending, Packed, Shipped, Out for Delivery, Delivered, Cancelled are used for shipment updates.', 'Tracking updates also sync order status.'),
        ],
        quick_actions=[
            _action('Add Tracking', reverse('admin-generic-create', kwargs={'model_key': model_key}), 'primary'),
            _action('Courier Partners', _section_url('shipping-management', 'courier-partners')),
            _action('Delivery Areas', _section_url('shipping-management', 'delivery-areas')),
        ],
        table_title='Shipment tracking',
        table_subtitle='Courier, tracking ID, tracking URL, and current shipment status.',
        table_headers=table_headers,
        table_rows=table_rows,
        table_actions=table_actions,
        empty_message='No shipment tracking records found yet.',
        primary_action=_action('Add Tracking', reverse('admin-generic-create', kwargs={'model_key': model_key}), 'primary'),
    )


@user_passes_test(_staff_required, login_url='login')
def admin_customers(request):
    now = timezone.now()
    month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    customers = User.objects.filter(is_staff=False).select_related('customer_profile').order_by('-date_joined')
    latest_customers = list(customers[:50])
    customer_count = customers.count()
    new_this_month = customers.filter(date_joined__gte=month_start).count()
    new_this_week = customers.filter(date_joined__gte=now - timedelta(days=7)).count()
    with_email = customers.exclude(email='').count()

    table_rows = [
        [
            _avatar_cell(
                _customer_photo_url(customer),
                _initial_from(customer.first_name, customer.email, customer.username),
                customer.first_name or customer.email or customer.username,
            ),
            _cell(customer.first_name or customer.username),
            _cell(customer.username),
            _cell(customer.email or 'Not provided'),
            _cell(_customer_phone(customer) or 'Not provided'),
            _cell('Active' if customer.is_active else 'Inactive', 'success' if customer.is_active else 'danger'),
            _cell(customer.date_joined.strftime('%d %b %Y')),
        ]
        for customer in latest_customers
    ]
    table_actions = [
        [
            _action('View', reverse('admin-customer-detail', kwargs={'pk': customer.pk}), 'view'),
            _action('Edit', reverse('admin-customer-edit', kwargs={'pk': customer.pk}), 'edit'),
            _action('Delete', reverse('admin-customer-delete', kwargs={'pk': customer.pk}), 'delete'),
        ]
        for customer in latest_customers
    ]

    latest_name = latest_customers[0].first_name or latest_customers[0].username if latest_customers else 'No customer'

    return _render_admin_overview(
        request,
        nav_group='user-management',
        section='customers',
        title='Customers',
        subtitle='Account directory for the people who have signed up on Lexvers.',
        summary_cards=[
            _card('c-blue', 'fas fa-users', 'Registered Customers', customer_count),
            _card('c-red', 'fas fa-user-plus', 'Joined This Month', new_this_month),
            _card('c-purple', 'fas fa-bolt', 'Joined Last 7 Days', new_this_week),
            _card('c-green', 'fas fa-envelope', 'Profiles With Email', with_email),
        ],
        insights=[
            _insight('Latest signup', f'{latest_name} is the newest customer currently on file.' if latest_customers else 'No customer accounts created yet.', 'Use this list to verify onboarding quality.'),
            _insight('Profile completeness', f'{with_email} customer profiles already include an email address.', 'Useful for campaigns and support updates.'),
            _insight('Next evolution', 'When orders go live, this page can become the base for lifecycle and support workflows.', 'It already gives you the raw customer list.'),
        ],
        quick_actions=[
            _action('Add New Customer', reverse('admin-customer-add'), 'primary'),
            _action('Customer Report', reverse('admin-report-customers')),
            _action('Website Edit', reverse('admin-website-edit')),
            _action('Open Store', reverse('home')),
        ],
        table_title='Customer accounts',
        table_subtitle='Registered customers from your current user base with View, Edit, and Delete actions.',
        table_headers=['Photo', 'Name', 'Username', 'Email', 'Phone', 'Status', 'Joined'],
        table_rows=table_rows,
        table_actions=table_actions,
        empty_message='No customer accounts have been created yet.',
        primary_action=_action('Add New Customer', reverse('admin-customer-add'), 'primary'),
    )


@user_passes_test(_staff_required, login_url='login')
def admin_customer_create(request):
    form = AdminCustomerForm(request.POST or None, request.FILES or None)
    if request.method == 'POST' and form.is_valid():
        form.save()
        success_message = 'Customer account added successfully.'
        if form.generated_password:
            success_message = f'Customer account added successfully. Temporary password: {form.generated_password}'
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return JsonResponse(
                {
                    'success': True,
                    'message': success_message,
                    'redirect_url': reverse('admin-customers'),
                }
            )
        messages.success(request, success_message)
        return redirect('admin-customers')

    return _render_admin_form_page(
        request,
        'user-management',
        'customers',
        title='Add Customer',
        subtitle='Create a customer login manually with name, phone, mail ID, and photo.',
        form=form,
        back_url='admin-customers',
    )


@user_passes_test(_staff_required, login_url='login')
def admin_customer_detail(request, pk):
    customer = get_object_or_404(User.objects.filter(is_staff=False), pk=pk)
    profile = _get_customer_profile(customer)
    addresses = CustomerAddress.objects.filter(user=customer)
    saved_products = (
        SavedProduct.objects.filter(user=customer)
        .select_related('product', 'product__category', 'product__seller')
        .prefetch_related('product__gallery_images')
    )
    orders = Order.objects.filter(customer=customer).prefetch_related('items').order_by('-created_at')
    return render(
        request,
        'admin_panel/customer_detail.html',
        _admin_context(
            'user-management',
            'customers',
            customer=customer,
            profile=profile,
            addresses=addresses,
            saved_products=saved_products,
            orders=orders,
        ),
    )


@user_passes_test(_staff_required, login_url='login')
def admin_customer_edit(request, pk):
    customer = get_object_or_404(User.objects.filter(is_staff=False), pk=pk)
    profile = _get_customer_profile(customer)
    form = AdminCustomerEditForm(request.POST or None, request.FILES or None, instance=profile, user=customer)
    if request.method == 'POST' and form.is_valid():
        form.save()
        if form.generated_password:
            messages.success(request, f'Customer updated. New password: {form.generated_password}')
        else:
            messages.success(request, 'Customer updated successfully.')
        return redirect('admin-customer-detail', pk=customer.pk)

    return _render_admin_form_page(
        request,
        'user-management',
        'customers',
        title=f'Edit Customer: {customer.first_name or customer.username}',
        subtitle='Update registration details, phone, photo, language, and optional password.',
        form=form,
        back_url='admin-customers',
    )


@user_passes_test(_staff_required, login_url='login')
@require_http_methods(['GET', 'POST'])
def admin_customer_delete(request, pk):
    customer = get_object_or_404(User.objects.filter(is_staff=False), pk=pk)
    if request.method == 'POST':
        if customer.pk == request.user.pk:
            messages.error(request, 'You cannot delete your own active admin session account.')
            return redirect('admin-customers')
        customer.delete()
        messages.success(request, 'Customer deleted successfully.')
        return redirect('admin-customers')

    return render(
        request,
        'admin_panel/confirm_delete.html',
        _admin_context(
            'user-management',
            'customers',
            title='Delete Customer',
            object_label=customer.first_name or customer.email or customer.username,
            back_url='admin-customers',
        ),
    )


@user_passes_test(_staff_required, login_url='login')
def admin_sellers(request):
    sellers = list(SellerApplication.objects.order_by('-created_at')[:12])
    pending_count = SellerApplication.objects.filter(status__in=[SellerApplication.Status.PENDING, SellerApplication.Status.MORE_INFO]).count()
    approved_count = SellerApplication.objects.filter(status=SellerApplication.Status.APPROVED).count()
    rejected_count = SellerApplication.objects.filter(status=SellerApplication.Status.REJECTED).count()
    approved_products = SpiceItem.objects.filter(owner_type=SpiceItem.OwnerType.SELLER, approval_status=SpiceItem.ApprovalStatus.APPROVED).count()

    table_rows = [
        [
            _avatar_cell(
                _seller_photo_url(seller),
                _initial_from(seller.name, seller.store_name, seller.email, fallback='S'),
                seller.name or seller.store_name,
            ),
            _cell(seller.request_code),
            _cell(seller.name),
            _cell(seller.email),
            _cell('Verified' if seller.email_verified else 'Not verified', 'success' if seller.email_verified else 'warning'),
            _cell(seller.phone),
            _cell(seller.store_name),
            _cell(seller.get_business_type_display()),
            _cell(seller.primary_category or 'Not set'),
            _cell(seller.get_status_display(), _seller_status_tone(seller.status)),
            _cell(seller.created_at.strftime('%d %b %Y')),
        ]
        for seller in sellers
    ]
    table_actions = []
    for seller in sellers:
        table_actions.append(_seller_admin_actions(seller))

    return _render_admin_overview(
        request,
        nav_group='user-management',
        section='sellers',
        title='Sellers',
        subtitle='Seller registration requests, approvals, and manual seller accounts.',
        summary_cards=[
            _card('c-orange', 'fas fa-hourglass-half', 'Pending / More Info', pending_count),
            _card('c-green', 'fas fa-circle-check', 'Approved Sellers', approved_count),
            _card('c-red', 'fas fa-circle-xmark', 'Rejected Sellers', rejected_count),
            _card('c-purple', 'fas fa-boxes-stacked', 'Approved Seller Products', approved_products),
        ],
        insights=[
            _insight('Approval rule', 'Seller registration ke baad login access tabhi active hota hai jab admin approve kare.', 'Approval seller login user bhi create karta hai.'),
            _insight('Manual add', 'Admin manually seller add karke status Approved rakh sakta hai.', 'Us email aur password se seller dashboard login ho jayega.'),
            _insight('Product control', 'Seller products default pending rahenge, admin product list se approve/active kar sakta hai.', 'Customer side par sirf approved active products dikhte hain.'),
        ],
        quick_actions=[
            _action('Add New Seller', reverse('admin-seller-add'), 'primary'),
            _action('Seller Requests', _section_url('seller-management', 'seller-requests')),
            _action('Manage Products', reverse('admin-items')),
            _action('Open Seller Panel', reverse('seller-dashboard')),
        ],
        table_title='Seller registration requests',
        table_subtitle='Latest seller applications from the database.',
        table_headers=['Photo', 'Request ID', 'Seller Name', 'Email', 'Email Verified', 'Phone', 'Shop Name', 'Business Type', 'Primary Category', 'Status', 'Submitted Date'],
        table_rows=table_rows,
        table_actions=table_actions,
        empty_message='No seller applications yet.',
        primary_action=_action('Add New Seller', reverse('admin-seller-add'), 'primary'),
    )


@user_passes_test(_staff_required, login_url='login')
def admin_seller_create(request):
    form = AdminSellerApplicationForm(request.POST or None, request.FILES or None)
    if request.method == 'POST' and form.is_valid():
        application = form.save()
        _ensure_seller_user(application)
        if application.status == SellerApplication.Status.APPROVED:
            success_message = 'Seller account added successfully.'
        else:
            success_message = 'Seller request added successfully.'
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return JsonResponse(
                {
                    'success': True,
                    'message': success_message,
                    'redirect_url': reverse('admin-sellers'),
                }
            )
        messages.success(request, success_message)
        return redirect('admin-sellers')

    return _render_admin_form_page(
        request,
        'user-management',
        'sellers',
        title='Add Seller',
        subtitle='Create a seller account manually. Approved sellers can login to seller panel.',
        form=form,
        back_url='admin-sellers',
    )


def _seller_document_file(seller, document_key):
    field_names = SELLER_ADMIN_DOCUMENT_FIELD_MAP.get(document_key)
    if not field_names:
        return None
    for field_name in field_names:
        document = getattr(seller, field_name, None)
        if document and getattr(document, 'name', ''):
            return document
    return None


def _seller_document_response(document, download=False):
    if not document or not getattr(document, 'name', ''):
        raise Http404('Document not found.')
    try:
        file_handle = document.storage.open(document.name, 'rb')
    except (FileNotFoundError, OSError):
        raise Http404('Document not found.')
    return FileResponse(file_handle, as_attachment=download, filename=os.path.basename(document.name))


def _seller_document_rows(seller):
    rows = []
    for document_key, label, _field_names, show_if_missing in SELLER_ADMIN_DOCUMENT_FIELDS:
        document = _seller_document_file(seller, document_key)
        if not document and not show_if_missing:
            continue
        view_url = ''
        download_url = ''
        if document:
            view_url = reverse('admin-seller-document', kwargs={'pk': seller.pk, 'document_key': document_key})
            download_url = f'{view_url}?download=1'
        rows.append(
            {
                'label': label,
                'document': document,
                'view_url': view_url,
                'download_url': download_url,
            }
        )
    return rows


def _seller_extra_document_rows(seller):
    rows = []
    for extra in seller.extra_documents.all():
        view_url = reverse('admin-seller-extra-document', kwargs={'pk': seller.pk, 'document_pk': extra.pk})
        rows.append(
            {
                'label': extra.display_name,
                'view_url': view_url,
                'download_url': f'{view_url}?download=1',
            }
        )
    return rows


@user_passes_test(_staff_required, login_url='login')
def admin_seller_document(request, pk, document_key):
    seller = get_object_or_404(SellerApplication, pk=pk)
    document = _seller_document_file(seller, document_key)
    if not document:
        raise Http404('Document not found.')
    return _seller_document_response(document, download=request.GET.get('download') == '1')


@user_passes_test(_staff_required, login_url='login')
def admin_seller_extra_document(request, pk, document_pk):
    seller = get_object_or_404(SellerApplication, pk=pk)
    extra_document = get_object_or_404(SellerApplicationExtraDocument, pk=document_pk, application=seller)
    return _seller_document_response(extra_document.file, download=request.GET.get('download') == '1')


@user_passes_test(_staff_required, login_url='login')
def admin_seller_detail(request, pk):
    seller = get_object_or_404(SellerApplication.objects.prefetch_related('extra_documents'), pk=pk)
    products = (
        SpiceItem.objects.filter(seller=seller)
        .select_related('category')
        .prefetch_related('gallery_images')
        .order_by('-updated_at', 'name')
    )
    order_items = (
        OrderItem.objects.filter(seller=seller)
        .select_related('order', 'product')
        .order_by('-order__created_at')
    )
    order_value = order_items.exclude(
        order__status__in=[Order.Status.CANCELLED, Order.Status.RETURNED],
    ).aggregate(total=Sum('line_total')).get('total') or Decimal('0')
    commission = order_value * Decimal('0.10')
    return render(
        request,
        'admin_panel/seller_detail.html',
        _admin_context(
            'user-management',
            'sellers',
            seller=seller,
            seller_status_tone=_seller_status_tone(seller.status),
            products=products,
            order_items=order_items,
            order_value=order_value,
            commission=commission,
            seller_earning=order_value - commission,
            seller_document_rows=_seller_document_rows(seller),
            seller_extra_document_rows=_seller_extra_document_rows(seller),
            review_action=request.GET.get('action', ''),
        ),
    )


@user_passes_test(_staff_required, login_url='login')
def admin_seller_edit(request, pk):
    seller = get_object_or_404(SellerApplication, pk=pk)
    form = AdminSellerApplicationEditForm(request.POST or None, request.FILES or None, instance=seller)
    if request.method == 'POST' and form.is_valid():
        application = form.save()
        if application.status == SellerApplication.Status.APPROVED:
            _ensure_seller_user(application)
        if form.generated_password:
            messages.success(request, f'Seller updated. New password: {form.generated_password}')
        else:
            messages.success(request, 'Seller updated successfully.')
        return redirect('admin-seller-detail', pk=application.pk)

    return _render_admin_form_page(
        request,
        'user-management',
        'sellers',
        title=f'Edit Seller: {seller.store_name}',
        subtitle='Update registration, KYC, bank, documents, status, and optional login password.',
        form=form,
        back_url='admin-sellers',
    )


@user_passes_test(_staff_required, login_url='login')
@require_http_methods(['GET', 'POST'])
def admin_seller_delete(request, pk):
    seller = get_object_or_404(SellerApplication, pk=pk)
    if request.method == 'POST':
        seller.delete()
        messages.success(request, 'Seller application deleted successfully.')
        return redirect('admin-sellers')

    return render(
        request,
        'admin_panel/confirm_delete.html',
        _admin_context(
            'user-management',
            'sellers',
            title='Delete Seller',
            object_label=seller.store_name,
            back_url='admin-sellers',
        ),
    )


@user_passes_test(_staff_required, login_url='login')
@require_http_methods(['POST'])
def admin_seller_status(request, pk, status):
    seller = get_object_or_404(SellerApplication, pk=pk)
    valid_statuses = {choice[0] for choice in SellerApplication.Status.choices}
    if status not in valid_statuses:
        messages.error(request, 'Invalid seller status.')
        return redirect('admin-sellers')

    remark = (request.POST.get('admin_remark') or request.POST.get('admin_note') or '').strip()
    if status in {SellerApplication.Status.REJECTED, SellerApplication.Status.MORE_INFO} and not remark:
        messages.error(request, 'Admin remark is required for this action.')
        return redirect('admin-seller-detail', pk=seller.pk)

    seller.status = status
    if remark:
        seller.admin_remark = remark
        seller.admin_note = remark[:240]
    seller.reviewed_by = request.user
    seller.reviewed_at = timezone.now()
    seller.save(update_fields=['status', 'admin_note', 'admin_remark', 'reviewed_by', 'reviewed_at', 'updated_at'])

    if seller.status == SellerApplication.Status.APPROVED:
        _ensure_seller_user(seller)
        messages.success(request, f'{seller.store_name} approved. Seller can login now.')
    elif seller.status == SellerApplication.Status.REJECTED:
        messages.warning(request, f'{seller.store_name} rejected.')
    elif seller.status == SellerApplication.Status.MORE_INFO:
        messages.info(request, f'More information requested from {seller.store_name}.')
    else:
        messages.info(request, f'{seller.store_name} moved to pending.')
    return redirect(request.POST.get('next') or 'admin-sellers')


@user_passes_test(_staff_required, login_url='login')
def admin_report_sales(request):
    orders = list(_orders_for_admin_section('all-orders')[:50])
    revenue_total = Order.objects.aggregate(total=Sum('total_amount')).get('total') or Decimal('0')
    paid_total = Order.objects.filter(payment_status=Order.PaymentStatus.PAID).aggregate(total=Sum('total_amount')).get('total') or Decimal('0')
    refund_total = ReturnRequest.objects.aggregate(total=Sum('refund_amount')).get('total') or Decimal('0')
    table_rows, table_actions = _order_table_data(orders)

    return _render_admin_overview(
        request,
        nav_group='reports-analytics',
        section='revenue-reports',
        title='Revenue Reports',
        subtitle='Revenue report generated from saved order and refund records.',
        summary_cards=[],
        insights=[
            _insight('Total revenue', f'{_format_currency(revenue_total)} is recorded across all orders.', 'This uses the current order table.'),
            _insight('Paid revenue', f'{_format_currency(paid_total)} is marked paid.', 'COD and pending payments stay visible in the table for follow-up.'),
            _insight('Refund exposure', f'{_format_currency(refund_total)} is currently recorded in return/refund requests.', 'Approved and pending refund records both remain auditable.'),
        ],
        quick_actions=[
            _action('Open Orders', reverse('admin-orders'), 'primary'),
            _action('Payment Management', _section_url('payment-management', 'all-payments')),
            _action('Return & Refund', _section_url('return-refund-management', 'return-requests')),
        ],
        table_title='Revenue Orders',
        table_subtitle='Order amount, seller, payment, and status rows from the database.',
        table_headers=['Order ID', 'Customer', 'Seller', 'Product Count', 'Amount', 'Payment Status', 'Order Status', 'Date'],
        table_rows=table_rows,
        table_actions=table_actions,
        empty_message='No order records found for revenue reporting.',
        primary_action=_action('Open Orders', reverse('admin-orders'), 'primary'),
    )


@user_passes_test(_staff_required, login_url='login')
def admin_report_inventory(request):
    categories = list(
        Category.objects.annotate(
            active_items=Count('items', filter=Q(items__is_active=True), distinct=True),
            hidden_items=Count('items', filter=Q(items__is_active=False), distinct=True),
            stock_units=Sum('items__stock', filter=Q(items__is_active=True)),
            low_items=Count('items', filter=Q(items__is_active=True, items__stock__gt=0, items__stock__lte=10), distinct=True),
            out_items=Count('items', filter=Q(items__is_active=True, items__stock=0), distinct=True),
        ).order_by('-stock_units', 'name')
    )
    top_inventory = max(categories, key=lambda category: category.stock_units or 0, default=None)
    urgent_category = max(
        categories,
        key=lambda category: (category.low_items or 0) + (category.out_items or 0),
        default=None,
    )
    snapshot = _admin_snapshot()

    table_rows = [
        [
            _cell(category.name),
            _cell(category.active_items),
            _cell(category.stock_units or 0),
            _cell(category.low_items or 0),
            _cell(category.out_items or 0),
        ]
        for category in categories
    ]

    return _render_admin_overview(
        request,
        nav_group='inventory-management',
        section='stock-report',
        title='Inventory Report',
        subtitle='Live stock health across the categories currently powering the storefront.',
        summary_cards=[
            _card('c-blue', 'fas fa-boxes-stacked', 'Total Stock Units', snapshot['total_stock']),
            _card('c-red', 'fas fa-clock', 'Low Stock Items', snapshot['low_stock_count']),
            _card('c-purple', 'fas fa-ban', 'Out of Stock Items', snapshot['out_stock_count']),
            _card('c-green', 'fas fa-eye', 'Visible Products', snapshot['active_item_count']),
        ],
        insights=[
            _insight(
                'Deepest inventory',
                (
                    f'{top_inventory.name} currently carries the highest stock units.'
                    if top_inventory
                    else 'No inventory data available yet.'
                ),
                'Useful for promo planning and shipping focus.',
            ),
            _insight(
                'Attention needed',
                (
                    f'{urgent_category.name} has the highest combined low and out-of-stock pressure.'
                    if urgent_category
                    else 'No urgent inventory category detected.'
                ),
                'This is the first category to inspect before running promotions.',
            ),
            _insight('Recommended rhythm', 'Review this page alongside Products and Shipping whenever stock changes in bulk.', 'That keeps storefront promises aligned with actual inventory.'),
        ],
        quick_actions=[
            _action('Open Products', reverse('admin-items'), 'primary'),
            _action('Shipping Board', reverse('admin-shipping')),
            _action('Sales Report', reverse('admin-report-sales')),
        ],
        table_title='Inventory by category',
        table_subtitle='Category-level stock, low-stock pressure, and out-of-stock signals.',
        table_headers=['Category', 'Active Items', 'Stock Units', 'Low Stock', 'Out of Stock'],
        table_rows=table_rows,
        empty_message='No categories available for inventory reporting yet.',
        primary_action=_action('Open Products', reverse('admin-items'), 'primary'),
    )


@user_passes_test(_staff_required, login_url='login')
def admin_report_customers(request):
    now = timezone.now()
    month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    customers = list(User.objects.filter(is_staff=False).order_by('date_joined'))
    total_customers = len(customers)
    new_this_month = len([customer for customer in customers if customer.date_joined >= month_start])
    new_this_week = len([customer for customer in customers if customer.date_joined >= now - timedelta(days=7)])
    staff_count = User.objects.filter(is_staff=True).count()

    monthly = {}
    running_total = 0
    for customer in customers:
        key = customer.date_joined.strftime('%b %Y')
        if key not in monthly:
            monthly[key] = {'count': 0, 'latest': customer}
        monthly[key]['count'] += 1
        monthly[key]['latest'] = customer

    month_rows = []
    for month, payload in monthly.items():
        running_total += payload['count']
        latest_name = payload['latest'].first_name or payload['latest'].username
        month_rows.append(
            [
                _cell(month),
                _cell(payload['count']),
                _cell(running_total),
                _cell(latest_name),
            ]
        )

    strongest_month = max(monthly.items(), key=lambda item: item[1]['count'], default=None)

    return _render_admin_overview(
        request,
        nav_group='reports-analytics',
        section='customer-report',
        title='Customer Report',
        subtitle='Signup trends and account growth from the current Lexvers user base.',
        summary_cards=[
            _card('c-blue', 'fas fa-users', 'Total Customers', total_customers),
            _card('c-red', 'fas fa-calendar-check', 'New This Month', new_this_month),
            _card('c-purple', 'fas fa-bolt', 'New This Week', new_this_week),
            _card('c-green', 'fas fa-user-shield', 'Staff Accounts', staff_count),
        ],
        insights=[
            _insight(
                'Best signup month',
                (
                    f'{strongest_month[0]} delivered the strongest signup count so far.'
                    if strongest_month
                    else 'No monthly customer trend is available yet.'
                ),
                'Use banners and homepage edits to support the next push.',
            ),
            _insight('Operational use', 'This report is useful even before order data exists because it tracks account growth and registration momentum.', 'It pairs well with the People > Customers directory.'),
            _insight('Next upgrade', 'Once marketing or orders are connected, this report can expand into repeat buyers and retention segments.', 'The structure is already ready for that future data.'),
        ],
        quick_actions=[
            _action('Open Customers', reverse('admin-customers'), 'primary'),
            _action('Website Edit', reverse('admin-website-edit')),
            _action('Sales Report', reverse('admin-report-sales')),
        ],
        table_title='Monthly signup trend',
        table_subtitle='Customer account growth based on registration dates.',
        table_headers=['Month', 'New Customers', 'Cumulative Total', 'Latest Signup'],
        table_rows=month_rows[-6:],
        empty_message='No customer signups available for reporting yet.',
        primary_action=_action('Open Customers', reverse('admin-customers'), 'primary'),
    )


@user_passes_test(_staff_required, login_url='login')
def admin_website_edit(request):
    homepage_settings = HomePageSetting.load()
    settings_form = HomePageSettingForm(instance=homepage_settings)
    large_banner_form = BannerForm(prefix='large', fixed_placement=Banner.BannerPlacement.LARGE)
    compact_banner_form = BannerForm(prefix='compact', fixed_placement=Banner.BannerPlacement.COMPACT)

    if request.method == 'POST':
        action = request.POST.get('action')

        if action == 'settings':
            settings_form = HomePageSettingForm(request.POST, instance=homepage_settings)
            if settings_form.is_valid():
                settings_form.save()
                messages.success(request, 'Home page hero settings updated.')
                return redirect('admin-website-edit')

        if action == 'large-banner':
            large_banner_form = BannerForm(
                request.POST,
                request.FILES,
                prefix='large',
                fixed_placement=Banner.BannerPlacement.LARGE,
            )
            if large_banner_form.is_valid():
                large_banner_form.save()
                messages.success(request, 'Large hero photo added.')
                return redirect('admin-website-edit')

        if action == 'compact-banner':
            compact_banner_form = BannerForm(
                request.POST,
                request.FILES,
                prefix='compact',
                fixed_placement=Banner.BannerPlacement.COMPACT,
            )
            if compact_banner_form.is_valid():
                compact_banner_form.save()
                messages.success(request, 'Small slider photo added.')
                return redirect('admin-website-edit')

        if action == 'delete-banner':
            banner = get_object_or_404(Banner, pk=request.POST.get('banner_id'))
            banner.delete()
            messages.success(request, 'Hero banner removed.')
            return redirect('admin-website-edit')

    snapshot = _admin_snapshot()
    large_banners = Banner.objects.filter(placement=Banner.BannerPlacement.LARGE).order_by('display_order', '-updated_at')
    compact_banners = Banner.objects.filter(placement=Banner.BannerPlacement.COMPACT).order_by('display_order', '-updated_at')

    return render(
        request,
        'admin_panel/home_page_editor.html',
        _admin_context(
            'content-management',
            'home-banners',
            title='Home Page',
            subtitle='Control the Top Deals large hero, small photo slider, and homepage merchandising rows.',
            summary_cards=[
                _card('c-blue', 'fas fa-panorama', 'Large Hero Photos', snapshot['large_banner_count']),
                _card('c-red', 'fas fa-images', 'Small Slider Photos', snapshot['compact_banner_count']),
                _card('c-purple', 'fas fa-toggle-on', 'Large Hero', 'On' if homepage_settings.hero_enabled else 'Off'),
                _card('c-green', 'fas fa-toggle-on', 'Small Slider', 'On' if homepage_settings.compact_hero_enabled else 'Off'),
            ],
            settings_form=settings_form,
            large_banner_form=large_banner_form,
            compact_banner_form=compact_banner_form,
            large_banners=large_banners,
            compact_banners=compact_banners,
            homepage_settings=homepage_settings,
        ),
    )


@user_passes_test(_staff_required, login_url='login')
def admin_website_about(request):
    sellers = list(SellerApplication.objects.filter(status=SellerApplication.Status.APPROVED).order_by('-updated_at')[:50])
    table_rows = [
        [
            _cell(seller.store_name),
            _cell(seller.name),
            _cell(seller.get_business_type_display()),
            _cell(seller.products.count()),
            _cell(seller.get_status_display(), _seller_status_tone(seller.status)),
        ]
        for seller in sellers
    ]
    table_actions = [[_action('Details', reverse('admin-seller-detail', kwargs={'pk': seller.pk}), 'view')] for seller in sellers]

    return _render_admin_overview(
        request,
        nav_group='content-management',
        section='about-us',
        title='About Us',
        subtitle='Live seller records that can support public About content.',
        summary_cards=[],
        insights=[],
        quick_actions=[
            _action('Open Sellers / Artisans', reverse('admin-sellers'), 'primary'),
            _action('View Collections', reverse('admin-collections')),
            _action('Open Products', reverse('admin-items')),
        ],
        table_title='Approved sellers',
        table_subtitle='Only saved seller records are shown here.',
        table_headers=['Store', 'Seller', 'Business Type', 'Products', 'Status'],
        table_rows=table_rows,
        table_actions=table_actions,
        empty_message='No approved seller records found yet.',
        primary_action=_action('Open Sellers / Artisans', reverse('admin-sellers'), 'primary'),
    )


@user_passes_test(_staff_required, login_url='login')
def admin_website_contact(request):
    admins = list(User.objects.filter(is_staff=True).order_by('-is_superuser', 'username'))
    table_rows = [
        [
            _cell(user.first_name or user.username),
            _cell(user.email or 'Not provided'),
            _cell('Superuser' if user.is_superuser else 'Staff admin', 'success' if user.is_superuser else 'info'),
            _cell(user.date_joined.strftime('%d %b %Y')),
        ]
        for user in admins
    ]

    return _render_admin_overview(
        request,
        nav_group='content-management',
        section='faq',
        title='Contact Page',
        subtitle='Live admin contacts that can be used for public support content.',
        summary_cards=[],
        insights=[],
        quick_actions=[
            _action('Profile Settings', reverse('admin-settings'), 'primary'),
            _action('Customer Report', reverse('admin-report-customers')),
        ],
        table_title='Admin contact records',
        table_subtitle='Only saved admin user records are shown here.',
        table_headers=['Name', 'Email', 'Role', 'Joined'],
        table_rows=table_rows,
        empty_message='No admin contact records found.',
        primary_action=_action('Profile Settings', reverse('admin-settings'), 'primary'),
    )


@user_passes_test(_staff_required, login_url='login')
def admin_website_terms(request):
    return _render_admin_overview(
        request,
        nav_group='content-management',
        section='terms-conditions',
        title='Terms & Privacy',
        subtitle='Static policy records will appear here once a content model is added.',
        summary_cards=[],
        insights=[],
        quick_actions=[
            _action('Open Shipping Settings', reverse('admin-settings-shipping'), 'primary'),
            _action('Returns Workflow', reverse('admin-returns')),
            _action('Contact Page', reverse('admin-website-contact')),
        ],
        table_title='Policy records',
        table_subtitle='Fake policy rows removed.',
        table_headers=['Policy', 'Status', 'Updated'],
        table_rows=[],
        empty_message='No static policy records are stored yet.',
        primary_action=_action('Open Shipping Settings', reverse('admin-settings-shipping'), 'primary'),
    )


@user_passes_test(_staff_required, login_url='login')
def admin_website_wish(request):
    saved_products = list(
        SavedProduct.objects.select_related('user', 'product', 'product__category')
        .order_by('-created_at')[:50]
    )
    table_rows = []
    table_actions = []
    for saved in saved_products:
        table_rows.append(
            [
                _cell(saved.user.first_name or saved.user.username),
                _cell(saved.product.name if saved.product else 'Product removed'),
                _cell(saved.product.category.name if saved.product and saved.product.category else 'General'),
                _cell(_format_currency(saved.product.price) if saved.product else 'Rs. 0'),
                _cell(saved.created_at.strftime('%d %b %Y')),
            ]
        )
        if saved.product:
            table_actions.append([_action('View Product', reverse('admin-item-detail', kwargs={'pk': saved.product.pk}), 'view')])
        else:
            table_actions.append([])

    return _render_admin_overview(
        request,
        nav_group='content-management',
        section='faq',
        title='Website Wish',
        subtitle='Saved product rows from customer accounts.',
        summary_cards=[],
        insights=[],
        quick_actions=[
            _action('Open Customers', reverse('admin-customers'), 'primary'),
            _action('View Home Page', reverse('admin-website-edit')),
            _action('Open Products', reverse('admin-items')),
        ],
        table_title='Saved products',
        table_subtitle='Customer saved-product data already stored in the database.',
        table_headers=['Customer', 'Product', 'Category', 'Price', 'Saved'],
        table_rows=table_rows,
        table_actions=table_actions,
        empty_message='No saved products found yet.',
        primary_action=_action('Open Customers', reverse('admin-customers'), 'primary'),
    )


@user_passes_test(_staff_required, login_url='login')
def admin_settings(request):
    profile = _touch_admin_security_profile(request)
    documents = AdminImportantDocument.objects.filter(user=request.user)
    profile_form = AdminProfileForm(user=request.user, instance=profile)
    media_form = AdminMediaForm(instance=profile)
    password_form = AdminPasswordChangeForm(request.user)
    document_form = AdminImportantDocumentForm()
    active_tab = request.GET.get('tab') or 'profile'

    if request.method == 'POST':
        action = request.POST.get('action', '').strip()
        active_tab = {
            'profile': 'account',
            'media': 'account',
            'password': 'security',
            'document': 'documents',
            'delete_document': 'documents',
        }.get(action, 'profile')
        if action == 'profile':
            profile_form = AdminProfileForm(request.POST, user=request.user, instance=profile)
            if profile_form.is_valid():
                profile_form.save()
                messages.success(request, 'Admin profile updated successfully.')
                return redirect(f"{reverse('admin-settings')}?tab=profile")
            messages.error(request, 'Please fix the profile details and try again.')
        elif action == 'media':
            media_form = AdminMediaForm(request.POST, request.FILES, instance=profile)
            remove_logo = request.POST.get('remove_logo') == '1'
            remove_photo = request.POST.get('remove_profile_photo') == '1'
            if media_form.is_valid():
                media_profile = media_form.save(commit=False)
                if remove_logo and media_profile.logo:
                    media_profile.logo.delete(save=False)
                    media_profile.logo = None
                if remove_photo and media_profile.profile_photo:
                    media_profile.profile_photo.delete(save=False)
                    media_profile.profile_photo = None
                media_profile.save()
                messages.success(request, 'Admin media updated successfully.')
                return redirect(f"{reverse('admin-settings')}?tab=account")
            messages.error(request, 'Please upload a valid image and try again.')
        elif action == 'password':
            password_form = AdminPasswordChangeForm(request.user, request.POST)
            if password_form.is_valid():
                password_form.save()
                update_session_auth_hash(request, password_form.user)
                messages.success(request, 'Password changed securely.')
                return redirect(f"{reverse('admin-settings')}?tab=security")
            messages.error(request, 'Password change failed. Check the old password and validation rules.')
        elif action == 'document':
            document_form = AdminImportantDocumentForm(request.POST, request.FILES)
            if document_form.is_valid():
                document = document_form.save(commit=False)
                document.user = request.user
                document.save()
                messages.success(request, 'Important document uploaded.')
                return redirect(f"{reverse('admin-settings')}?tab=documents")
            messages.error(request, 'Please provide a document name and upload file.')
        elif action == 'delete_document':
            document = get_object_or_404(AdminImportantDocument, pk=request.POST.get('document_id'), user=request.user)
            if document.document:
                document.document.delete(save=False)
            document.delete()
            messages.success(request, 'Important document deleted.')
            return redirect(f"{reverse('admin-settings')}?tab=documents")
        else:
            messages.error(request, 'Invalid settings action.')

    session_key = request.session.session_key
    current_session = {
        'session_key': f'...{session_key[-8:]}' if session_key else 'Not available',
        'ip_address': _client_ip(request) or 'Not available',
        'user_agent': request.META.get('HTTP_USER_AGENT', 'Not available'),
    }

    return render(
        request,
        'admin_panel/settings.html',
        _admin_context(
            'account-settings',
            'admin-profile',
            profile=profile,
            documents=documents,
            profile_form=profile_form,
            media_form=media_form,
            password_form=password_form,
            document_form=document_form,
            current_session=current_session,
            active_tab=active_tab,
        ),
    )


@user_passes_test(_staff_required, login_url='login')
def admin_document_download(request, pk):
    document = get_object_or_404(AdminImportantDocument, pk=pk, user=request.user)
    if not document.document:
        raise Http404('Document file not found.')
    return FileResponse(
        document.document.open('rb'),
        as_attachment=request.GET.get('download') == '1',
        filename=document.file_name or document.name,
    )


@user_passes_test(_staff_required, login_url='login')
def admin_settings_payment(request):
    transactions = list(_payment_transactions_for_admin_section('all-payments')[:50])
    table_rows, table_actions = _payment_table_data(transactions)
    return _render_admin_overview(
        request,
        nav_group='website-settings',
        section='payment-gateway',
        title='Payment Settings',
        subtitle='Payment status table from live customer orders.',
        summary_cards=[],
        insights=[],
        quick_actions=[
            _action('Open Orders', reverse('admin-orders'), 'primary'),
            _action('Profile Settings', reverse('admin-settings')),
            _action('Terms & Privacy', reverse('admin-website-terms')),
        ],
        table_title='Payment records',
        table_subtitle='Order amount, payment method, payment status, and order status.',
        table_headers=['Transaction ID', 'Customer', 'Amount', 'Method', 'Status', 'Date'],
        table_rows=table_rows,
        table_actions=table_actions,
        empty_message='No payment records found yet.',
        primary_action=_action('Open Orders', reverse('admin-orders'), 'primary'),
    )


@user_passes_test(_staff_required, login_url='login')
def admin_settings_shipping(request):
    table_rows, table_actions, table_headers = _shipping_table_data('shipping-charges')

    return _render_admin_overview(
        request,
        nav_group='shipping-management',
        section='shipping-charges',
        title='Shipping Settings',
        subtitle='Shipping charge rows from live orders.',
        summary_cards=[],
        insights=[],
        quick_actions=[
            _action('Open Shipping Board', reverse('admin-shipping'), 'primary'),
            _action('Inventory Report', reverse('admin-report-inventory')),
            _action('Terms & Privacy', reverse('admin-website-terms')),
        ],
        table_title='Shipping charge records',
        table_subtitle='Shipping fee data saved with customer orders.',
        table_headers=table_headers,
        table_rows=table_rows,
        table_actions=table_actions,
        empty_message='No shipping charge records found yet.',
        primary_action=_action('Open Shipping Board', reverse('admin-shipping'), 'primary'),
    )


@user_passes_test(_staff_required, login_url='login')
def admin_settings_admin_users(request):
    messages.info(request, 'Admin profile and security are managed from Account Settings.')
    return redirect('admin-settings')


@user_passes_test(_staff_required, login_url='login')
def admin_items(request):
    _ensure_default_spice_sub_categories()
    items = SpiceItem.objects.select_related('category', 'seller').prefetch_related('gallery_images', 'quantity_options').order_by('-updated_at')
    return render(
        request,
        'admin_panel/items_list.html',
        _admin_context(
            'product-management',
            'all-products',
            items=items,
            category_breakdown=_category_breakdown_queryset(),
            product_categories=Category.objects.order_by('display_order', 'name'),
            product_sellers=SellerApplication.objects.filter(status=SellerApplication.Status.APPROVED).order_by('store_name'),
        ),
    )


@user_passes_test(_staff_required, login_url='login')
def admin_item_create(request):
    form = SpiceItemForm(request.POST or None, request.FILES or None)
    if request.method == 'POST' and form.is_valid():
        item = form.save()
        form.save_quantity_options(item)
        form.save_gallery_images(item)
        messages.success(request, 'Spice item added successfully.')
        return redirect('admin-items')

    return _render_admin_form_page(
        request,
        'product-management',
        'all-products',
        title='Add New Spice Item',
        subtitle='Create a new product for customer panel.',
        form=form,
        back_url='admin-items',
    )


@user_passes_test(_staff_required, login_url='login')
def admin_item_edit(request, pk):
    item = get_object_or_404(SpiceItem.objects.prefetch_related('gallery_images', 'quantity_options'), pk=pk)
    form = SpiceItemForm(request.POST or None, request.FILES or None, instance=item)
    if request.method == 'POST' and form.is_valid():
        item = form.save()
        form.save_quantity_options(item)
        form.save_gallery_images(item)
        messages.success(request, 'Spice item updated successfully.')
        return redirect('admin-items')

    return _render_admin_form_page(
        request,
        'product-management',
        'all-products',
        title=f'Edit: {item.name}',
        subtitle='Update this product details.',
        form=form,
        back_url='admin-items',
    )


@user_passes_test(_staff_required, login_url='login')
@require_http_methods(['GET', 'POST'])
def admin_item_delete(request, pk):
    item = get_object_or_404(SpiceItem, pk=pk)

    if request.method == 'POST':
        item.delete()
        messages.success(request, 'Spice item deleted successfully.')
        return redirect('admin-items')

    return render(
        request,
        'admin_panel/confirm_delete.html',
        _admin_context(
            'product-management',
            'all-products',
            title='Delete Spice Item',
            object_label=item.name,
            back_url='admin-items',
        ),
    )


@user_passes_test(_staff_required, login_url='login')
@require_http_methods(['POST'])
def admin_item_stock_update(request, pk):
    next_url = request.POST.get('next') or _section_url('product-management', 'out-of-stock-products')
    try:
        add_quantity = int(request.POST.get('stock', ''))
    except (TypeError, ValueError):
        messages.error(request, 'Stock quantity valid number hona chahiye.')
        return redirect(next_url)

    if add_quantity < 0:
        messages.error(request, 'Add quantity negative nahi ho sakti.')
        return redirect(next_url)

    with transaction.atomic():
        item = get_object_or_404(SpiceItem.objects.select_for_update(), pk=pk)
        item.stock = item.stock + add_quantity
        if item.initial_stock < item.stock:
            item.initial_stock = item.stock
        item.save(update_fields=['stock', 'initial_stock', 'updated_at'])

    messages.success(request, f'{item.name} available stock updated to {item.stock}.')
    return redirect(next_url)


@user_passes_test(_staff_required, login_url='login')
def admin_item_detail(request, pk):
    item = get_object_or_404(
        SpiceItem.objects.select_related('category', 'seller').prefetch_related('gallery_images'),
        pk=pk,
    )
    return render(
        request,
        'admin_panel/item_detail.html',
        _admin_context(
            'product-management',
            'all-products',
            item=item,
            gallery_images=item.gallery_images.filter(is_active=True),
        ),
    )


@user_passes_test(_staff_required, login_url='login')
def admin_categories(request):
    _ensure_default_spice_sub_categories()
    categories = _category_breakdown_queryset()
    return render(
        request,
        'admin_panel/categories_list.html',
        _admin_context('category-management', 'categories', categories=categories),
    )


def _ensure_default_spice_sub_categories():
    spice_category = Category.objects.filter(slug=SPICE_CATEGORY_SLUG).first()
    if not spice_category:
        return

    for index, option in enumerate(SPICE_SPOTLIGHT, start=1):
        SubCategory.objects.get_or_create(
            category=spice_category,
            slug=option['key'],
            defaults={
                'name': option['label'],
                'icon_label': option['icon'],
                'display_order': index,
                'is_active': True,
            },
        )


def _attach_sub_category_stats(sub_categories):
    category_ids = [sub_category.category_id for sub_category in sub_categories]
    product_stats = (
        SpiceItem.objects.filter(category_id__in=category_ids)
        .exclude(sub_category__exact='')
        .values('category_id', 'sub_category')
        .annotate(total=Count('id'), stock_units=Sum('stock'), brand_total=Count('brand_name', filter=~Q(brand_name=''), distinct=True))
    )
    stats_lookup = {
        (row['category_id'], slugify(row['sub_category']) or row['sub_category'].lower()): row
        for row in product_stats
    }
    for sub_category in sub_categories:
        stats = stats_lookup.get((sub_category.category_id, sub_category.slug), {})
        sub_category.product_total = stats.get('total') or 0
        sub_category.stock_units = stats.get('stock_units') or 0
        sub_category.brand_total = stats.get('brand_total') or 0
    return sub_categories


@user_passes_test(_staff_required, login_url='login')
def admin_subcategories(request):
    _ensure_default_spice_sub_categories()
    sub_categories = _attach_sub_category_stats(
        list(SubCategory.objects.select_related('category').order_by('category__display_order', 'category__name', 'display_order', 'name'))
    )
    return render(
        request,
        'admin_panel/subcategories_list.html',
        _admin_context(
            'category-management',
            'sub-categories',
            sub_categories=sub_categories,
        ),
    )


@user_passes_test(_staff_required, login_url='login')
def admin_subcategory_detail(request, pk):
    sub_category = get_object_or_404(SubCategory.objects.select_related('category'), pk=pk)
    products = (
        SpiceItem.objects.filter(category=sub_category.category)
        .filter(Q(sub_category__iexact=sub_category.name) | Q(sub_category__iexact=sub_category.slug))
        .select_related('category', 'seller')
        .prefetch_related('gallery_images')
        .order_by('-updated_at', 'name')
    )
    return render(
        request,
        'admin_panel/subcategory_detail.html',
        _admin_context(
            'category-management',
            'sub-categories',
            sub_category=sub_category,
            products=products,
            product_total=products.count(),
        ),
    )


@user_passes_test(_staff_required, login_url='login')
def admin_subcategory_create(request, category_pk=None):
    fixed_category = None
    if category_pk:
        fixed_category = get_object_or_404(Category, pk=category_pk)
    form = SubCategoryForm(request.POST or None, request.FILES or None, fixed_category=fixed_category)
    if request.method == 'POST' and form.is_valid():
        form.save()
        messages.success(request, 'Sub-category added successfully.')
        return redirect('admin-subcategories')

    return _render_admin_form_page(
        request,
        'category-management',
        'sub-categories',
        title='New Sub Category',
        subtitle='Create a database-backed sub category under a parent category.',
        form=form,
        back_url='admin-subcategories',
    )


@user_passes_test(_staff_required, login_url='login')
def admin_subcategory_edit(request, pk):
    sub_category = get_object_or_404(SubCategory.objects.select_related('category'), pk=pk)
    form = SubCategoryForm(request.POST or None, request.FILES or None, instance=sub_category)
    if request.method == 'POST' and form.is_valid():
        form.save()
        messages.success(request, 'Sub-category updated successfully.')
        return redirect('admin-subcategories')

    return _render_admin_form_page(
        request,
        'category-management',
        'sub-categories',
        title=f'Edit Sub Category: {sub_category.name}',
        subtitle=f'Update sub-category under {sub_category.category.name}.',
        form=form,
        back_url='admin-subcategories',
    )


@user_passes_test(_staff_required, login_url='login')
@require_http_methods(['GET', 'POST'])
def admin_subcategory_delete(request, pk):
    sub_category = get_object_or_404(SubCategory, pk=pk)
    if request.method == 'POST':
        sub_category.delete()
        messages.success(request, 'Sub-category deleted successfully.')
        return redirect('admin-subcategories')

    return render(
        request,
        'admin_panel/confirm_delete.html',
        _admin_context(
            'category-management',
            'sub-categories',
            title='Delete Sub Category',
            object_label=sub_category.name,
            back_url='admin-subcategories',
        ),
    )


@user_passes_test(_staff_required, login_url='login')
def admin_category_create(request):
    form = CategoryForm(request.POST or None, request.FILES or None)
    if request.method == 'POST' and form.is_valid():
        form.save()
        messages.success(request, 'Category added successfully.')
        return redirect('admin-categories')

    return _render_admin_form_page(
        request,
        'category-management',
        'categories',
        title='Add Category',
        subtitle='Add a new spice category for storefront.',
        form=form,
        back_url='admin-categories',
    )


@user_passes_test(_staff_required, login_url='login')
def admin_category_edit(request, pk):
    category = get_object_or_404(Category, pk=pk)
    form = CategoryForm(request.POST or None, request.FILES or None, instance=category)
    if request.method == 'POST' and form.is_valid():
        form.save()
        messages.success(request, 'Category updated successfully.')
        return redirect('admin-categories')

    return _render_admin_form_page(
        request,
        'category-management',
        'categories',
        title=f'Edit Category: {category.name}',
        subtitle='Update category details.',
        form=form,
        back_url='admin-categories',
    )


@user_passes_test(_staff_required, login_url='login')
@require_http_methods(['GET', 'POST'])
def admin_category_delete(request, pk):
    category = get_object_or_404(Category, pk=pk)

    if request.method == 'POST':
        category.delete()
        messages.success(request, 'Category deleted successfully.')
        return redirect('admin-categories')

    return render(
        request,
        'admin_panel/confirm_delete.html',
        _admin_context(
            'category-management',
            'categories',
            title='Delete Category',
            object_label=category.name,
            back_url='admin-categories',
        ),
    )


@user_passes_test(_staff_required, login_url='login')
def admin_category_products(request, pk):
    category = get_object_or_404(_category_breakdown_queryset(), pk=pk)
    products = (
        SpiceItem.objects.filter(category=category)
        .select_related('category', 'seller')
        .prefetch_related('gallery_images')
        .order_by('-updated_at', 'name')
    )
    totals = products.aggregate(
        current_stock=Sum('stock'),
        initial_stock=Sum('initial_stock'),
        active_products=Count('id', filter=Q(is_active=True)),
        pending_products=Count('id', filter=Q(approval_status=SpiceItem.ApprovalStatus.PENDING)),
        seller_products=Count('id', filter=Q(owner_type=SpiceItem.OwnerType.SELLER)),
        admin_products=Count('id', filter=Q(owner_type=SpiceItem.OwnerType.ADMIN)),
    )
    sub_categories = _attach_sub_category_stats(list(category.sub_categories.order_by('display_order', 'name')))
    brand_breakdown = (
        products.exclude(brand_name__exact='')
        .values('brand_name')
        .annotate(
            product_total=Count('id'),
            stock_units=Sum('stock'),
            seller_products=Count('id', filter=Q(owner_type=SpiceItem.OwnerType.SELLER)),
            admin_products=Count('id', filter=Q(owner_type=SpiceItem.OwnerType.ADMIN)),
        )
        .order_by('brand_name')
    )
    return render(
        request,
        'admin_panel/category_products.html',
        _admin_context(
            'category-management',
            'categories',
            category=category,
            products=products,
            category_totals=totals,
            sub_categories=sub_categories,
            brand_breakdown=brand_breakdown,
        ),
    )


@user_passes_test(_staff_required, login_url='login')
def admin_banners(request):
    banners = Banner.objects.order_by('display_order', '-updated_at')
    return render(request, 'admin_panel/banners_list.html', _admin_context('coupon-offer-management', 'banners', banners=banners))


@user_passes_test(_staff_required, login_url='login')
def admin_banner_create(request):
    form = BannerForm(request.POST or None, request.FILES or None)
    if request.method == 'POST' and form.is_valid():
        form.save()
        messages.success(request, 'Banner added successfully.')
        return redirect('admin-banners')

    return _render_admin_form_page(
        request,
        'coupon-offer-management',
        'banners',
        title='Add Banner',
        subtitle='Create a new top banner for homepage.',
        form=form,
        back_url='admin-banners',
    )


@user_passes_test(_staff_required, login_url='login')
def admin_banner_edit(request, pk):
    banner = get_object_or_404(Banner, pk=pk)
    form = BannerForm(request.POST or None, request.FILES or None, instance=banner)
    if request.method == 'POST' and form.is_valid():
        form.save()
        messages.success(request, 'Banner updated successfully.')
        return redirect('admin-banners')

    return _render_admin_form_page(
        request,
        'coupon-offer-management',
        'banners',
        title=f'Edit Banner: {banner.title}',
        subtitle='Update banner details.',
        form=form,
        back_url='admin-banners',
    )


@user_passes_test(_staff_required, login_url='login')
@require_http_methods(['GET', 'POST'])
def admin_banner_delete(request, pk):
    banner = get_object_or_404(Banner, pk=pk)

    if request.method == 'POST':
        banner.delete()
        messages.success(request, 'Banner deleted successfully.')
        return redirect('admin-banners')

    return render(
        request,
        'admin_panel/confirm_delete.html',
        _admin_context(
            'coupon-offer-management',
            'banners',
            title='Delete Banner',
            object_label=banner.title,
            back_url='admin-banners',
        ),
    )
