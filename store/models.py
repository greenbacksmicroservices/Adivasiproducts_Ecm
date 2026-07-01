from decimal import Decimal
import os

from django.contrib.auth.models import User
from django.db import models
from django.utils import timezone
from django.utils.crypto import get_random_string
from django.utils.text import slugify


class TimestampedModel(models.Model):
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        abstract = True


def _generate_unique_slug(instance, source_text):
    base_slug = slugify(source_text) or 'item'
    slug = base_slug
    counter = 1
    model_class = instance.__class__

    while model_class.objects.filter(slug=slug).exclude(pk=instance.pk).exists():
        slug = f'{base_slug}-{counter}'
        counter += 1

    return slug


def next_product_id(model_class, instance_pk=None):
    highest_number = 0
    for product_code in model_class.objects.exclude(product_id__exact='').values_list('product_id', flat=True):
        if product_code and product_code.startswith('PRD') and product_code[3:].isdigit():
            highest_number = max(highest_number, int(product_code[3:]))

    next_number = highest_number + 1
    while True:
        candidate = f'PRD{next_number:05d}'
        existing = model_class.objects.filter(product_id=candidate)
        if instance_pk:
            existing = existing.exclude(pk=instance_pk)
        if not existing.exists():
            return candidate
        next_number += 1


class Category(TimestampedModel):
    name = models.CharField(max_length=120, unique=True)
    slug = models.SlugField(max_length=160, unique=True, blank=True)
    description = models.CharField(max_length=240, blank=True)
    icon_emoji = models.CharField(max_length=8, default='SP')
    highlight_color = models.CharField(max_length=20, default='#fff1dc')
    image_url = models.URLField(blank=True)
    image_file = models.ImageField(upload_to='categories/', blank=True, null=True)
    display_order = models.PositiveIntegerField(default=0)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ('display_order', 'name')

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = _generate_unique_slug(self, self.name)
        super().save(*args, **kwargs)

    @property
    def image_source(self):
        if self.image_file:
            return self.image_file.url
        return self.image_url

    def __str__(self):
        return self.name


class SubCategory(TimestampedModel):
    category = models.ForeignKey(Category, related_name='sub_categories', on_delete=models.CASCADE)
    name = models.CharField(max_length=120)
    slug = models.SlugField(max_length=160, blank=True)
    description = models.CharField(max_length=220, blank=True)
    icon_label = models.CharField(max_length=8, blank=True)
    image_file = models.ImageField(upload_to='sub_categories/', blank=True, null=True)
    display_order = models.PositiveIntegerField(default=0)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ('category__display_order', 'category__name', 'display_order', 'name')
        unique_together = ('category', 'slug')

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = _generate_unique_slug(self, self.name)
        if not self.icon_label:
            self.icon_label = ''.join(word[:1] for word in self.name.split()[:2]).upper() or self.name[:2].upper()
        super().save(*args, **kwargs)

    @property
    def image_source(self):
        if self.image_file:
            return self.image_file.url
        return ''

    def __str__(self):
        return f'{self.category.name} / {self.name}'


class Banner(TimestampedModel):
    class BannerPlacement(models.TextChoices):
        LARGE = 'large', 'Large Hero'
        COMPACT = 'compact', 'Small Photo Slider'

    title = models.CharField(max_length=140)
    subtitle = models.CharField(max_length=240, blank=True)
    image_url = models.URLField(blank=True)
    image_file = models.ImageField(upload_to='banners/', blank=True, null=True)
    placement = models.CharField(
        max_length=12,
        choices=BannerPlacement.choices,
        default=BannerPlacement.LARGE,
    )
    cta_text = models.CharField(max_length=60, default='Shop Now')
    cta_link = models.CharField(max_length=240, default='/')
    display_order = models.PositiveIntegerField(default=0)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ('display_order', '-updated_at')

    @property
    def image_source(self):
        if self.image_file:
            return self.image_file.url
        return self.image_url

    def __str__(self):
        return self.title


class HomePageSetting(TimestampedModel):
    hero_enabled = models.BooleanField(default=True)
    hero_interval_ms = models.PositiveIntegerField(default=3000)
    compact_hero_enabled = models.BooleanField(default=True)
    compact_hero_interval_ms = models.PositiveIntegerField(default=3000)

    class Meta:
        verbose_name = 'Home Page Setting'
        verbose_name_plural = 'Home Page Settings'

    @classmethod
    def load(cls):
        setting, _ = cls.objects.get_or_create(
            pk=1,
            defaults={
                'hero_enabled': True,
                'hero_interval_ms': 3000,
                'compact_hero_enabled': True,
                'compact_hero_interval_ms': 3000,
            },
        )
        return setting

    def save(self, *args, **kwargs):
        self.pk = 1
        super().save(*args, **kwargs)

    def __str__(self):
        return 'Home Page Settings'


class CustomerProfile(TimestampedModel):
    class Language(models.TextChoices):
        ENGLISH = 'en', 'English'
        HINDI = 'hi', 'Hindi'
        BENGALI = 'bn', 'Bengali'
        TAMIL = 'ta', 'Tamil'
        TELUGU = 'te', 'Telugu'
        MARATHI = 'mr', 'Marathi'

    user = models.OneToOneField(User, related_name='customer_profile', on_delete=models.CASCADE)
    phone = models.CharField(max_length=20, blank=True)
    photo = models.ImageField(upload_to='customers/photos/', blank=True, null=True)
    language = models.CharField(max_length=8, choices=Language.choices, default=Language.ENGLISH)
    email_verified = models.BooleanField(default=True)

    @property
    def photo_source(self):
        if self.photo:
            return self.photo.url
        return ''

    def __str__(self):
        return self.user.get_full_name() or self.user.username


class AdminProfile(TimestampedModel):
    user = models.OneToOneField(User, related_name='admin_profile', on_delete=models.CASCADE)
    phone = models.CharField(max_length=20, blank=True)
    date_of_birth = models.DateField(null=True, blank=True)
    profile_photo = models.ImageField(upload_to='admin/profile_photos/', blank=True, null=True)
    logo = models.ImageField(upload_to='admin/logos/', blank=True, null=True)
    last_ip_address = models.GenericIPAddressField(null=True, blank=True)
    last_user_agent = models.TextField(blank=True)
    last_seen_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ('user__username',)

    @property
    def profile_photo_source(self):
        if self.profile_photo:
            return self.profile_photo.url
        return ''

    @property
    def logo_source(self):
        if self.logo:
            return self.logo.url
        return ''

    def __str__(self):
        return f'Admin profile: {self.user.get_full_name() or self.user.username}'


class AdminImportantDocument(TimestampedModel):
    user = models.ForeignKey(User, related_name='admin_documents', on_delete=models.CASCADE)
    name = models.CharField(max_length=160)
    document = models.FileField(upload_to='admin/important_documents/')

    class Meta:
        ordering = ('-created_at', 'name')

    @property
    def file_name(self):
        return os.path.basename(self.document.name or '')

    def __str__(self):
        return self.name


class EmailOTP(TimestampedModel):
    class Purpose(models.TextChoices):
        SELLER_REGISTER = 'seller_register', 'Seller registration'
        CUSTOMER_REGISTER = 'customer_register', 'Customer registration'
        LOGIN = 'login', 'Login'
        FORGOT_PASSWORD = 'forgot_password', 'Forgot password'

    email = models.EmailField(db_index=True)
    purpose = models.CharField(max_length=32, choices=Purpose.choices)
    otp_hash = models.CharField(max_length=128)
    expires_at = models.DateTimeField()
    attempts = models.PositiveSmallIntegerField(default=0)
    is_used = models.BooleanField(default=False)
    ip_address = models.GenericIPAddressField(blank=True, null=True)
    user_agent = models.CharField(max_length=255, blank=True)

    class Meta:
        ordering = ('-created_at',)
        indexes = [
            models.Index(fields=['email', 'purpose', 'is_used', 'expires_at']),
            models.Index(fields=['created_at']),
        ]

    def __str__(self):
        return f'{self.email} - {self.get_purpose_display()}'

    @property
    def is_expired(self):
        return timezone.now() >= self.expires_at


class CustomerAddress(TimestampedModel):
    class AddressType(models.TextChoices):
        HOME = 'home', 'Home'
        WORK = 'work', 'Work'
        OTHER = 'other', 'Other'

    user = models.ForeignKey(User, related_name='customer_addresses', on_delete=models.CASCADE)
    label = models.CharField(max_length=60, default='Home')
    full_name = models.CharField(max_length=150)
    phone = models.CharField(max_length=20)
    alternate_phone = models.CharField(max_length=20, blank=True)
    email = models.EmailField(blank=True)
    house = models.CharField(max_length=180, blank=True)
    area = models.CharField(max_length=180, blank=True)
    landmark = models.CharField(max_length=180, blank=True)
    address_line = models.CharField(max_length=240)
    city = models.CharField(max_length=80)
    district = models.CharField(max_length=80, blank=True)
    state = models.CharField(max_length=80)
    pincode = models.CharField(max_length=12)
    country = models.CharField(max_length=80, default='India')
    address_type = models.CharField(max_length=12, choices=AddressType.choices, default=AddressType.HOME)
    is_default = models.BooleanField(default=False)

    class Meta:
        ordering = ('-is_default', '-updated_at')

    def __str__(self):
        return f'{self.label} - {self.city}'

    @property
    def full_address(self):
        parts = [
            self.house,
            self.area or self.address_line,
            self.landmark,
            self.city,
            self.district,
            self.state,
            self.pincode,
            self.country,
        ]
        return ', '.join(str(part).strip() for part in parts if str(part or '').strip())

    def save(self, *args, **kwargs):
        if not self.label:
            self.label = self.get_address_type_display()
        if not self.address_line:
            self.address_line = ', '.join(part for part in [self.house, self.area] if part).strip()[:240]
        super().save(*args, **kwargs)


class SavedProduct(TimestampedModel):
    user = models.ForeignKey(User, related_name='saved_products', on_delete=models.CASCADE)
    product = models.ForeignKey('SpiceItem', related_name='saved_by', on_delete=models.CASCADE)

    class Meta:
        unique_together = ('user', 'product')
        ordering = ('-created_at',)

    def __str__(self):
        return f'{self.user.username} saved {self.product.name}'


class SearchHistory(TimestampedModel):
    user = models.ForeignKey(User, related_name='search_history', on_delete=models.CASCADE)
    term = models.CharField(max_length=120)
    normalized_term = models.CharField(max_length=120)

    class Meta:
        ordering = ('-updated_at',)
        unique_together = ('user', 'normalized_term')
        verbose_name_plural = 'Search histories'

    def save(self, *args, **kwargs):
        self.term = ' '.join((self.term or '').split())[:120]
        self.normalized_term = ' '.join((self.normalized_term or self.term).lower().split())[:120]
        super().save(*args, **kwargs)

    def __str__(self):
        return f'{self.user.username} searched {self.term}'


class Order(TimestampedModel):
    class Status(models.TextChoices):
        PENDING = 'pending', 'Placed'
        CONFIRMED = 'confirmed', 'Confirmed'
        PACKED = 'packed', 'Packed'
        SHIPPED = 'shipped', 'Shipped'
        OUT_FOR_DELIVERY = 'out_for_delivery', 'Out for Delivery'
        DELIVERED = 'delivered', 'Delivered'
        CANCELLED = 'cancelled', 'Cancelled'
        RETURNED = 'returned', 'Returned'

    class PaymentStatus(models.TextChoices):
        PENDING = 'pending', 'Pending'
        PAID = 'paid', 'Paid'
        COD = 'cod', 'Cash on Delivery'
        FAILED = 'failed', 'Failed'
        REFUNDED = 'refunded', 'Refunded'

    order_number = models.CharField(max_length=24, unique=True, blank=True)
    order_id = models.CharField(max_length=24, unique=True, blank=True, null=True)
    customer = models.ForeignKey(User, related_name='orders', on_delete=models.CASCADE)
    address = models.ForeignKey(CustomerAddress, related_name='orders', null=True, blank=True, on_delete=models.SET_NULL)
    customer_name = models.CharField(max_length=150)
    customer_email = models.EmailField(blank=True)
    customer_phone = models.CharField(max_length=20, blank=True)
    alternate_phone = models.CharField(max_length=20, blank=True)
    shipping_address = models.CharField(max_length=320, blank=True)
    address_type = models.CharField(max_length=12, choices=CustomerAddress.AddressType.choices, default=CustomerAddress.AddressType.HOME)
    house = models.CharField(max_length=180, blank=True)
    area = models.CharField(max_length=180, blank=True)
    landmark = models.CharField(max_length=180, blank=True)
    city = models.CharField(max_length=80, blank=True)
    district = models.CharField(max_length=80, blank=True)
    state = models.CharField(max_length=80, blank=True)
    pincode = models.CharField(max_length=12, blank=True)
    country = models.CharField(max_length=80, default='India')
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.PENDING)
    payment_status = models.CharField(max_length=16, choices=PaymentStatus.choices, default=PaymentStatus.COD)
    payment_method = models.CharField(max_length=80, default='Cash on Delivery')
    subtotal = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    shipping_fee = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    discount_amount = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    coupon_code = models.CharField(max_length=40, blank=True)
    total_amount = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    admin_note = models.CharField(max_length=240, blank=True)
    notes = models.TextField(blank=True)
    is_seen_by_admin = models.BooleanField(default=False)
    is_seen_by_seller = models.BooleanField(default=False)

    class Meta:
        ordering = ('-created_at',)

    def save(self, *args, **kwargs):
        if not self.order_number or not self.order_id:
            while True:
                today = timezone.localdate()
                prefix = f'ORD-{today:%Y%m%d}'
                todays_count = self.__class__.objects.filter(created_at__date=today).count()
                candidate = f'{prefix}-{todays_count + 1:04d}'
                if not self.__class__.objects.filter(models.Q(order_number=candidate) | models.Q(order_id=candidate)).exists():
                    self.order_number = self.order_number or candidate
                    self.order_id = self.order_id or self.order_number
                    break
        if not self.order_id:
            self.order_id = self.order_number
        super().save(*args, **kwargs)

    @property
    def status_tone(self):
        if self.status in {self.Status.DELIVERED, self.Status.CONFIRMED}:
            return 'success'
        if self.status in {self.Status.CANCELLED, self.Status.RETURNED}:
            return 'danger'
        if self.status in {self.Status.PENDING, self.Status.PACKED}:
            return 'warning'
        return 'info'

    @property
    def payment_tone(self):
        if self.payment_status in {self.PaymentStatus.PAID, self.PaymentStatus.COD}:
            return 'success'
        if self.payment_status in {self.PaymentStatus.FAILED, self.PaymentStatus.REFUNDED}:
            return 'danger'
        return 'warning'

    @property
    def item_count(self):
        prefetched_items = getattr(self, '_prefetched_objects_cache', {}).get('items')
        if prefetched_items is not None:
            return sum(item.quantity for item in prefetched_items)
        if not self.pk:
            return 0
        return self.items.aggregate(total=models.Sum('quantity')).get('total') or 0

    def __str__(self):
        return self.order_number or f'Order #{self.pk}'

    @property
    def full_name(self):
        return self.customer_name

    @property
    def phone(self):
        return self.customer_phone

    @property
    def email(self):
        return self.customer_email

    @property
    def delivery_charge(self):
        return self.shipping_fee

    @property
    def discount(self):
        return self.discount_amount

    @property
    def order_status(self):
        return self.status

    @property
    def estimated_delivery_message(self):
        return 'Estimated delivery in 4-7 business days.'

    @property
    def address_short(self):
        if self.city or self.state or self.pincode:
            return ', '.join(part for part in [self.city, self.state, self.pincode] if part)
        return (self.shipping_address or 'Address not added')[:80]


class SellerApplication(TimestampedModel):
    class BusinessType(models.TextChoices):
        INDIVIDUAL = 'individual', 'Individual Seller'
        PROPRIETOR = 'proprietor', 'Proprietorship'
        PARTNERSHIP = 'partnership', 'Partnership'
        PRIVATE_LIMITED = 'private_limited', 'Private Limited'
        LLP = 'llp', 'LLP'
        COMPANY = 'company', 'Company / Pvt Ltd'

    class Status(models.TextChoices):
        PENDING = 'pending', 'Pending Approval'
        APPROVED = 'approved', 'Approved'
        REJECTED = 'rejected', 'Rejected'
        MORE_INFO = 'more_info', 'More Info Required'
        BLOCKED = 'blocked', 'Blocked'

    name = models.CharField(max_length=150)
    email = models.EmailField()
    email_verified = models.BooleanField(default=True)
    phone = models.CharField(max_length=20)
    alternate_phone = models.CharField(max_length=20, blank=True)
    password_hash = models.CharField(max_length=180)
    profile_photo = models.ImageField(upload_to='seller_docs/profile_photos/', blank=True, null=True)
    store_name = models.CharField(max_length=150)
    store_display_name = models.CharField(max_length=150, blank=True)
    store_description = models.TextField(blank=True)
    business_type = models.CharField(
        max_length=20,
        choices=BusinessType.choices,
        default=BusinessType.INDIVIDUAL,
    )
    store_logo = models.ImageField(upload_to='seller_docs/store_logos/', blank=True, null=True)
    store_banner = models.ImageField(upload_to='seller_docs/store_banners/', blank=True, null=True)
    pan_number = models.CharField(max_length=20, blank=True)
    gst_number = models.CharField(max_length=24, blank=True)
    aadhaar_number = models.CharField(max_length=20, blank=True)
    owner_dob = models.DateField(blank=True, null=True)
    owner_address = models.TextField(blank=True)
    gst_available = models.BooleanField(default=False)
    legal_business_name = models.CharField(max_length=180, blank=True)
    tax_pan_number = models.CharField(max_length=20, blank=True)
    bank_account_name = models.CharField(max_length=140, blank=True)
    bank_name = models.CharField(max_length=140, blank=True)
    bank_account_number = models.CharField(max_length=34, blank=True)
    bank_ifsc = models.CharField(max_length=16, blank=True)
    branch_name = models.CharField(max_length=140, blank=True)
    business_address = models.TextField(blank=True)
    pickup_address = models.TextField(blank=True)
    pickup_contact_name = models.CharField(max_length=150, blank=True)
    pickup_phone = models.CharField(max_length=20, blank=True)
    pickup_address_line1 = models.CharField(max_length=220, blank=True)
    pickup_address_line2 = models.CharField(max_length=220, blank=True)
    pickup_city = models.CharField(max_length=90, blank=True)
    pickup_state = models.CharField(max_length=90, blank=True)
    pickup_pincode = models.CharField(max_length=12, blank=True)
    pickup_landmark = models.CharField(max_length=160, blank=True)
    pickup_same_as_owner = models.BooleanField(default=False)
    product_categories = models.TextField(blank=True)
    primary_category = models.CharField(max_length=120, blank=True)
    approx_products_count = models.PositiveIntegerField(blank=True, null=True)
    brand_name = models.CharField(max_length=120, blank=True)
    sells_handmade = models.BooleanField(default=False)
    aadhaar_document = models.FileField(upload_to='seller_docs/aadhaar/', blank=True, null=True)
    aadhaar_front = models.FileField(upload_to='seller_docs/aadhaar_front/', blank=True, null=True)
    aadhaar_back = models.FileField(upload_to='seller_docs/aadhaar_back/', blank=True, null=True)
    pan_document = models.FileField(upload_to='seller_docs/pan/', blank=True, null=True)
    pan_card = models.FileField(upload_to='seller_docs/pan_cards/', blank=True, null=True)
    gst_document = models.FileField(upload_to='seller_docs/gst/', blank=True, null=True)
    trade_license_document = models.FileField(upload_to='seller_docs/trade_license/', blank=True, null=True)
    company_document = models.FileField(upload_to='seller_docs/company/', blank=True, null=True)
    bank_document = models.FileField(upload_to='seller_docs/bank/', blank=True, null=True)
    cancelled_cheque = models.FileField(upload_to='seller_docs/cancelled_cheques/', blank=True, null=True)
    business_registration_certificate = models.FileField(upload_to='seller_docs/business_registration/', blank=True, null=True)
    shop_photo = models.FileField(upload_to='seller_docs/shop_photos/', blank=True, null=True)
    owner_photo = models.FileField(upload_to='seller_docs/owner_photos/', blank=True, null=True)
    business_proof = models.FileField(upload_to='seller_docs/business_proofs/', blank=True, null=True)
    address_proof = models.FileField(upload_to='seller_docs/address/', blank=True, null=True)
    signature_upload = models.FileField(upload_to='seller_docs/signatures/', blank=True, null=True)
    confirm_details = models.BooleanField(default=False)
    terms_accepted = models.BooleanField(default=False)
    approval_access_ack = models.BooleanField(default=False)
    status = models.CharField(
        max_length=12,
        choices=Status.choices,
        default=Status.PENDING,
    )
    admin_note = models.CharField(max_length=240, blank=True)
    admin_remark = models.TextField(blank=True)
    reviewed_by = models.ForeignKey(
        User,
        related_name='reviewed_seller_applications',
        blank=True,
        null=True,
        on_delete=models.SET_NULL,
    )
    reviewed_at = models.DateTimeField(blank=True, null=True)

    class Meta:
        ordering = ('-created_at',)

    def __str__(self):
        return f'{self.store_name} - {self.get_status_display()}'

    @property
    def request_code(self):
        if not self.pk:
            return 'SLR-PENDING'
        return f'SLR-{self.pk:05d}'

    @property
    def product_category_list(self):
        return [item.strip() for item in self.product_categories.split(',') if item.strip()]

    @property
    def pickup_full_address(self):
        parts = [
            self.pickup_address_line1,
            self.pickup_address_line2,
            self.pickup_landmark,
            self.pickup_city,
            self.pickup_state,
            self.pickup_pincode,
        ]
        composed = ', '.join(part for part in parts if part)
        return composed or self.pickup_address

    @property
    def document_fields(self):
        fields = [
            ('Profile Photo', self.profile_photo),
            ('Store Logo', self.store_logo),
            ('Store Banner', self.store_banner),
            ('Aadhaar Front', self.aadhaar_front or self.aadhaar_document),
            ('PAN Card', self.pan_card or self.pan_document),
            ('GST Certificate', self.gst_document),
            ('Business Registration Certificate', self.business_registration_certificate or self.company_document),
            ('Cancelled Cheque / Passbook', self.cancelled_cheque or self.bank_document),
            ('Shop Photo', self.shop_photo),
            ('Owner Photo', self.owner_photo),
            ('Business Proof', self.business_proof or self.trade_license_document),
            ('Address Proof', self.address_proof),
            ('Signature Upload', self.signature_upload),
        ]
        if self.aadhaar_back:
            fields.insert(4, ('Aadhaar Back', self.aadhaar_back))
        return fields


class SellerApplicationExtraDocument(TimestampedModel):
    application = models.ForeignKey(
        SellerApplication,
        related_name='extra_documents',
        on_delete=models.CASCADE,
    )
    document_name = models.CharField(max_length=160, blank=True)
    file = models.FileField(upload_to='seller_docs/extra/')
    original_name = models.CharField(max_length=220, blank=True)

    class Meta:
        ordering = ('created_at',)

    @property
    def display_name(self):
        return self.document_name or self.original_name or os.path.basename(self.file.name or '')

    def __str__(self):
        return self.display_name or f'Extra document #{self.pk}'


class SpiceItem(TimestampedModel):
    class SpiceLevel(models.TextChoices):
        MILD = 'mild', 'Mild'
        MEDIUM = 'medium', 'Medium'
        HOT = 'hot', 'Hot'

    class OwnerType(models.TextChoices):
        ADMIN = 'admin', 'Admin'
        SELLER = 'seller', 'Seller'

    class ApprovalStatus(models.TextChoices):
        PENDING = 'pending', 'Pending Approval'
        APPROVED = 'approved', 'Approved'
        REJECTED = 'rejected', 'Rejected'

    name = models.CharField(max_length=140)
    product_id = models.CharField(max_length=12, unique=True, blank=True, editable=False)
    slug = models.SlugField(max_length=180, unique=True, blank=True)
    category = models.ForeignKey(
        Category,
        related_name='items',
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
    )
    short_description = models.CharField(max_length=220)
    description = models.TextField(blank=True)
    sub_category = models.CharField(max_length=120, blank=True)
    spice_level = models.CharField(
        max_length=10,
        choices=SpiceLevel.choices,
        default=SpiceLevel.MEDIUM,
    )
    brand_name = models.CharField(max_length=120, default='Lexvers')
    pack_size = models.CharField(max_length=60, blank=True)
    sku_code = models.CharField(max_length=80, blank=True)
    specifications = models.TextField(blank=True)
    shipping_weight = models.CharField(max_length=60, blank=True)
    return_available = models.BooleanField(default=True)
    warranty_details = models.CharField(max_length=160, blank=True)
    price = models.DecimalField(max_digits=10, decimal_places=2)
    original_price = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    initial_stock = models.PositiveIntegerField(default=0)
    stock = models.PositiveIntegerField(default=0)
    image_url = models.URLField(blank=True)
    image_file = models.ImageField(upload_to='spices/', blank=True, null=True)
    owner_type = models.CharField(
        max_length=12,
        choices=OwnerType.choices,
        default=OwnerType.ADMIN,
    )
    seller = models.ForeignKey(
        SellerApplication,
        related_name='products',
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
    )
    approval_status = models.CharField(
        max_length=12,
        choices=ApprovalStatus.choices,
        default=ApprovalStatus.APPROVED,
    )
    is_featured = models.BooleanField(default=False)
    is_active = models.BooleanField(default=True)
    display_order = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ('-is_featured', 'display_order', 'name')

    def save(self, *args, **kwargs):
        if not self.product_id:
            self.product_id = next_product_id(self.__class__, self.pk)
        if not self.slug:
            self.slug = _generate_unique_slug(self, self.name)
        if self.initial_stock == 0 and self.stock:
            self.initial_stock = self.stock
        if self.owner_type == self.OwnerType.ADMIN:
            self.seller = None
        super().save(*args, **kwargs)

    @property
    def discount_percent(self):
        if self.original_price and self.original_price > self.price:
            discount = (self.original_price - self.price) / self.original_price
            return int(discount * 100)
        return 0

    @property
    def active_flash_offer(self):
        now = timezone.now()
        if not self.pk:
            return None
        return (
            self.flash_sales.filter(is_active=True)
            .filter(models.Q(starts_at__isnull=True) | models.Q(starts_at__lte=now))
            .filter(models.Q(ends_at__isnull=True) | models.Q(ends_at__gte=now))
            .order_by('-updated_at')
            .first()
        )

    @property
    def effective_price(self):
        offer = self.active_flash_offer
        if not offer:
            return self.price
        return max(self.price - offer.discount_amount_for(self.price), Decimal('0.00')).quantize(Decimal('0.01'))

    @property
    def effective_original_price(self):
        if self.active_flash_offer:
            return self.original_price or self.price
        return self.original_price

    @property
    def effective_discount_percent(self):
        original_price = self.effective_original_price
        effective_price = self.effective_price
        if original_price and original_price > effective_price:
            discount = (original_price - effective_price) / original_price
            return int(discount * 100)
        return 0

    @property
    def image_source(self):
        if self.image_file:
            return self.image_file.url
        if self.image_url:
            return self.image_url

        prefetched_gallery = getattr(self, '_prefetched_objects_cache', {}).get('gallery_images')
        if prefetched_gallery is not None:
            for photo in prefetched_gallery:
                if photo.is_active and photo.image_source:
                    return photo.image_source
            return ''

        if not self.pk:
            return ''

        gallery_photo = self.gallery_images.filter(is_active=True).first()
        if gallery_photo:
            return gallery_photo.image_source
        return ''

    @property
    def stock_state(self):
        if self.stock == 0:
            return 'out'
        if self.stock <= 10:
            return 'low'
        if self.stock <= 35:
            return 'medium'
        return 'high'

    @property
    def pack_display(self):
        return self.pack_size or 'Standard pack'

    @property
    def owner_label(self):
        if self.owner_type == self.OwnerType.SELLER and self.seller:
            return self.seller.store_name
        if self.owner_type == self.OwnerType.SELLER:
            return 'Seller product'
        return 'Admin catalog'

    @property
    def stock_delta(self):
        return self.stock - self.initial_stock

    @property
    def approval_tone(self):
        if self.approval_status == self.ApprovalStatus.APPROVED:
            return 'success'
        if self.approval_status == self.ApprovalStatus.REJECTED:
            return 'danger'
        return 'warning'

    def __str__(self):
        return self.name


class SpiceItemPhoto(TimestampedModel):
    product = models.ForeignKey(
        SpiceItem,
        related_name='gallery_images',
        on_delete=models.CASCADE,
    )
    image_file = models.ImageField(upload_to='spices/gallery/')
    alt_text = models.CharField(max_length=160, blank=True)
    display_order = models.PositiveIntegerField(default=0)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ('display_order', 'id')

    @property
    def image_source(self):
        if self.image_file:
            return self.image_file.url
        return ''

    def __str__(self):
        return self.alt_text or f'{self.product.name} photo'


class ProductDetailImage(TimestampedModel):
    product = models.ForeignKey(
        SpiceItem,
        related_name='detail_images',
        on_delete=models.CASCADE,
    )
    image_file = models.ImageField(upload_to='spices/details/')
    title = models.CharField(max_length=120, blank=True)
    caption = models.CharField(max_length=220, blank=True)
    display_order = models.PositiveIntegerField(default=0)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ('display_order', 'id')

    @property
    def image_source(self):
        if self.image_file:
            return self.image_file.url
        return ''

    def __str__(self):
        return self.title or f'{self.product.name} detail photo'


class ProductQuantityOption(TimestampedModel):
    product = models.ForeignKey(
        SpiceItem,
        related_name='quantity_options',
        on_delete=models.CASCADE,
    )
    label = models.CharField(max_length=60)
    price = models.DecimalField(max_digits=10, decimal_places=2)
    original_price = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    stock = models.PositiveIntegerField(default=0)
    sku_code = models.CharField(max_length=80, blank=True)
    image_file = models.ImageField(upload_to='spices/quantity_options/', blank=True, null=True)
    display_order = models.PositiveIntegerField(default=0)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ('display_order', 'id')
        unique_together = ('product', 'label')

    @property
    def variant_image_source(self):
        if self.image_file:
            return self.image_file.url
        return ''

    @property
    def image_source(self):
        return self.variant_image_source or self.product.image_source

    @property
    def discount_percent(self):
        if self.original_price and self.original_price > self.price:
            discount = (self.original_price - self.price) / self.original_price
            return int(discount * 100)
        return 0

    @property
    def effective_price(self):
        offer = self.product.active_flash_offer
        if not offer:
            return self.price
        return max(self.price - offer.discount_amount_for(self.price), Decimal('0.00')).quantize(Decimal('0.01'))

    @property
    def effective_original_price(self):
        if self.product.active_flash_offer:
            return self.original_price or self.price
        return self.original_price

    @property
    def effective_discount_percent(self):
        original_price = self.effective_original_price
        effective_price = self.effective_price
        if original_price and original_price > effective_price:
            discount = (original_price - effective_price) / original_price
            return int(discount * 100)
        return 0

    def __str__(self):
        return f'{self.product.name} - {self.label}'


class Cart(TimestampedModel):
    class Status(models.TextChoices):
        ACTIVE = 'active', 'Active'
        ORDERED = 'ordered', 'Ordered'
        ABANDONED = 'abandoned', 'Abandoned'

    user = models.OneToOneField(User, related_name='cart', on_delete=models.CASCADE)
    status = models.CharField(max_length=12, choices=Status.choices, default=Status.ACTIVE)

    class Meta:
        ordering = ('-updated_at',)

    @property
    def subtotal(self):
        prefetched_items = getattr(self, '_prefetched_objects_cache', {}).get('items')
        if prefetched_items is not None:
            return sum(item.line_total for item in prefetched_items)
        return sum(item.line_total for item in self.items.select_related('product', 'quantity_option'))

    @property
    def item_count(self):
        prefetched_items = getattr(self, '_prefetched_objects_cache', {}).get('items')
        if prefetched_items is not None:
            return sum(item.quantity for item in prefetched_items)
        return self.items.aggregate(total=models.Sum('quantity')).get('total') or 0

    def __str__(self):
        return f'Cart - {self.user.username}'


class CartItem(TimestampedModel):
    cart = models.ForeignKey(Cart, related_name='items', on_delete=models.CASCADE)
    product = models.ForeignKey(SpiceItem, related_name='cart_items', on_delete=models.CASCADE)
    quantity_option = models.ForeignKey(ProductQuantityOption, related_name='cart_items', null=True, blank=True, on_delete=models.SET_NULL)
    quantity = models.PositiveIntegerField(default=1)
    unit_price = models.DecimalField(max_digits=10, decimal_places=2, default=0)

    class Meta:
        ordering = ('-updated_at',)
        unique_together = ('cart', 'product', 'quantity_option')

    @property
    def line_total(self):
        return self.unit_price * self.quantity

    @property
    def stock_available(self):
        if self.quantity_option:
            return self.quantity_option.stock
        return self.product.stock

    @property
    def display_pack(self):
        if self.quantity_option:
            return self.quantity_option.label
        return self.product.pack_display

    @property
    def selected_variant_image(self):
        if self.quantity_option:
            return self.quantity_option.variant_image_source
        return ''

    @property
    def display_image(self):
        return self.selected_variant_image or self.product.image_source

    def save(self, *args, **kwargs):
        if not self.unit_price:
            self.unit_price = self.quantity_option.effective_price if self.quantity_option else self.product.effective_price
        super().save(*args, **kwargs)

    def __str__(self):
        return f'{self.product.name} x {self.quantity}'


class OrderItem(TimestampedModel):
    order = models.ForeignKey(Order, related_name='items', on_delete=models.CASCADE)
    product = models.ForeignKey(SpiceItem, related_name='order_items', null=True, blank=True, on_delete=models.SET_NULL)
    quantity_option = models.ForeignKey(ProductQuantityOption, related_name='order_items', null=True, blank=True, on_delete=models.SET_NULL)
    seller = models.ForeignKey(SellerApplication, related_name='order_items', null=True, blank=True, on_delete=models.SET_NULL)
    product_name = models.CharField(max_length=160)
    product_image = models.CharField(max_length=500, blank=True)
    category_name = models.CharField(max_length=120, blank=True)
    brand_name = models.CharField(max_length=120, blank=True)
    pack_size = models.CharField(max_length=60, blank=True)
    seller_name = models.CharField(max_length=150, blank=True)
    unit_price = models.DecimalField(max_digits=10, decimal_places=2)
    quantity = models.PositiveIntegerField(default=1)
    line_total = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    item_status = models.CharField(max_length=16, choices=Order.Status.choices, default=Order.Status.PENDING)
    seller_note = models.CharField(max_length=240, blank=True)
    is_seen_by_seller = models.BooleanField(default=False)

    class Meta:
        ordering = ('order__created_at', 'product_name')

    def save(self, *args, **kwargs):
        self.line_total = self.unit_price * self.quantity
        super().save(*args, **kwargs)

    @property
    def commission_amount(self):
        return self.line_total * Decimal('0.10')

    @property
    def seller_earning(self):
        return self.line_total - self.commission_amount

    @property
    def price(self):
        return self.unit_price

    @property
    def total_price(self):
        return self.line_total

    @property
    def selected_variant_image(self):
        if self.quantity_option:
            return self.quantity_option.variant_image_source
        return ''

    @property
    def display_image(self):
        product_image = self.product.image_source if self.product_id and self.product else ''
        return self.selected_variant_image or self.product_image or product_image

    @property
    def status_tone(self):
        if self.item_status in {Order.Status.DELIVERED, Order.Status.CONFIRMED}:
            return 'success'
        if self.item_status in {Order.Status.CANCELLED, Order.Status.RETURNED}:
            return 'danger'
        if self.item_status in {Order.Status.PENDING, Order.Status.PACKED}:
            return 'warning'
        return 'info'

    def __str__(self):
        return f'{self.product_name} x {self.quantity}'


class PaymentTransaction(TimestampedModel):
    class Status(models.TextChoices):
        PENDING = 'pending', 'Pending'
        SUCCESS = 'success', 'Success'
        FAILED = 'failed', 'Failed'
        REFUNDED = 'refunded', 'Refunded'

    transaction_id = models.CharField(max_length=40, unique=True, blank=True)
    order = models.ForeignKey(Order, related_name='payment_transactions', null=True, blank=True, on_delete=models.SET_NULL)
    customer = models.ForeignKey(User, related_name='payment_transactions', null=True, blank=True, on_delete=models.SET_NULL)
    amount = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    method = models.CharField(max_length=80, default='Cash on Delivery')
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.PENDING)
    gateway_reference = models.CharField(max_length=120, blank=True)
    admin_note = models.CharField(max_length=240, blank=True)

    class Meta:
        ordering = ('-created_at',)

    def save(self, *args, **kwargs):
        if not self.transaction_id:
            while True:
                candidate = f'TXN{timezone.now():%Y%m%d}{get_random_string(8).upper()}'
                if not self.__class__.objects.filter(transaction_id=candidate).exists():
                    self.transaction_id = candidate
                    break
        super().save(*args, **kwargs)

    @property
    def status_tone(self):
        if self.status == self.Status.SUCCESS:
            return 'success'
        if self.status in {self.Status.FAILED, self.Status.REFUNDED}:
            return 'danger'
        return 'warning'

    def __str__(self):
        return self.transaction_id


class Payment(TimestampedModel):
    class Method(models.TextChoices):
        ONLINE = 'online', 'Online Payment'
        COD = 'cod', 'Cash on Delivery'
        DEMO = 'demo', 'Demo Payment'

    class Status(models.TextChoices):
        PENDING = 'pending', 'Pending'
        PAID = 'paid', 'Paid'
        FAILED = 'failed', 'Failed'
        REFUNDED = 'refunded', 'Refunded'

    payment_id = models.CharField(max_length=40, unique=True, blank=True)
    order = models.OneToOneField(Order, related_name='payment', on_delete=models.CASCADE)
    customer = models.ForeignKey(User, related_name='payments', null=True, blank=True, on_delete=models.SET_NULL)
    amount = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    method = models.CharField(max_length=16, choices=Method.choices, default=Method.COD)
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.PENDING)
    razorpay_order_id = models.CharField(max_length=120, blank=True)
    razorpay_payment_id = models.CharField(max_length=120, blank=True)
    razorpay_signature = models.CharField(max_length=240, blank=True)
    gateway_response = models.JSONField(default=dict, blank=True)
    is_demo = models.BooleanField(default=False)

    class Meta:
        ordering = ('-created_at',)

    def save(self, *args, **kwargs):
        if not self.payment_id:
            while True:
                candidate = f'PAY-{timezone.now():%Y%m%d}-{get_random_string(6).upper()}'
                if not self.__class__.objects.filter(payment_id=candidate).exists():
                    self.payment_id = candidate
                    break
        super().save(*args, **kwargs)

    @property
    def status_tone(self):
        if self.status == self.Status.PAID:
            return 'success'
        if self.status == self.Status.FAILED:
            return 'danger'
        if self.status == self.Status.REFUNDED:
            return 'secondary'
        return 'warning'

    def __str__(self):
        return self.payment_id


class OrderStatusHistory(TimestampedModel):
    order = models.ForeignKey(Order, related_name='status_history', on_delete=models.CASCADE)
    order_item = models.ForeignKey(OrderItem, related_name='status_history', null=True, blank=True, on_delete=models.CASCADE)
    changed_by = models.ForeignKey(User, related_name='order_status_changes', null=True, blank=True, on_delete=models.SET_NULL)
    status = models.CharField(max_length=16, choices=Order.Status.choices)
    note = models.CharField(max_length=240, blank=True)

    class Meta:
        ordering = ('created_at',)
        verbose_name_plural = 'Order status histories'

    def __str__(self):
        return f'{self.order.order_number} - {self.get_status_display()}'


class OrderNotification(TimestampedModel):
    class Audience(models.TextChoices):
        ADMIN = 'admin', 'Admin'
        SELLER = 'seller', 'Seller'
        CUSTOMER = 'customer', 'Customer'

    class Type(models.TextChoices):
        NEW_ORDER = 'new_order', 'New order received'
        STATUS_UPDATED = 'status_updated', 'Order status updated'
        PAYMENT_UPDATED = 'payment_updated', 'Payment updated'

    audience = models.CharField(max_length=12, choices=Audience.choices)
    notification_type = models.CharField(max_length=24, choices=Type.choices, default=Type.NEW_ORDER)
    user = models.ForeignKey(User, related_name='order_notifications', null=True, blank=True, on_delete=models.CASCADE)
    seller = models.ForeignKey(SellerApplication, related_name='order_notifications', null=True, blank=True, on_delete=models.CASCADE)
    order = models.ForeignKey(Order, related_name='notifications', on_delete=models.CASCADE)
    order_item = models.ForeignKey(OrderItem, related_name='notifications', null=True, blank=True, on_delete=models.CASCADE)
    title = models.CharField(max_length=160)
    message = models.CharField(max_length=280, blank=True)
    is_read = models.BooleanField(default=False)

    class Meta:
        ordering = ('-created_at',)

    def __str__(self):
        return self.title


class ReturnRequest(TimestampedModel):
    class Status(models.TextChoices):
        PENDING = 'pending', 'Pending'
        APPROVED = 'approved', 'Approved'
        REJECTED = 'rejected', 'Rejected'

    class RefundStatus(models.TextChoices):
        NOT_REQUESTED = 'not_requested', 'Not Requested'
        REQUESTED = 'requested', 'Requested'
        APPROVED = 'approved', 'Approved'
        REJECTED = 'rejected', 'Rejected'
        PROCESSING = 'processing', 'Processing'
        COMPLETED = 'completed', 'Completed'
        FAILED = 'failed', 'Failed'

    order = models.ForeignKey(Order, related_name='return_requests', on_delete=models.CASCADE)
    order_item = models.ForeignKey(OrderItem, related_name='return_requests', null=True, blank=True, on_delete=models.SET_NULL)
    customer = models.ForeignKey(User, related_name='return_requests', null=True, blank=True, on_delete=models.SET_NULL)
    reason = models.CharField(max_length=240)
    details = models.TextField(blank=True)
    proof_file = models.FileField(upload_to='returns/proofs/', blank=True, null=True)
    proof_url = models.URLField(blank=True)
    refund_amount = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.PENDING)
    refund_status = models.CharField(max_length=20, choices=RefundStatus.choices, default=RefundStatus.REQUESTED)
    pickup_status = models.CharField(max_length=80, default='Not scheduled')
    admin_note = models.CharField(max_length=240, blank=True)
    processed_by = models.ForeignKey(User, related_name='processed_returns', null=True, blank=True, on_delete=models.SET_NULL)
    processed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ('-created_at',)

    @property
    def status_tone(self):
        if self.status == self.Status.APPROVED:
            return 'success'
        if self.status == self.Status.REJECTED:
            return 'danger'
        return 'warning'

    @property
    def refund_tone(self):
        if self.refund_status == self.RefundStatus.COMPLETED:
            return 'success'
        if self.refund_status in {self.RefundStatus.REJECTED, self.RefundStatus.FAILED}:
            return 'danger'
        if self.refund_status in {self.RefundStatus.PROCESSING, self.RefundStatus.APPROVED}:
            return 'info'
        return 'warning'

    @property
    def proof_source(self):
        if self.proof_file:
            return self.proof_file.url
        return self.proof_url

    def __str__(self):
        return f'Return {self.order.order_number}'


class Coupon(TimestampedModel):
    class DiscountType(models.TextChoices):
        PERCENT = 'percent', 'Percent'
        FLAT = 'flat', 'Flat Amount'

    class OwnerType(models.TextChoices):
        ADMIN = 'admin', 'Admin'
        SELLER = 'seller', 'Seller'

    class ApprovalStatus(models.TextChoices):
        PENDING = 'pending', 'Pending'
        APPROVED = 'approved', 'Approved'
        REJECTED = 'rejected', 'Rejected'

    code = models.CharField(max_length=40, unique=True)
    title = models.CharField(max_length=140)
    discount_type = models.CharField(max_length=16, choices=DiscountType.choices, default=DiscountType.PERCENT)
    discount_value = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    min_order_amount = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    max_discount = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    starts_at = models.DateTimeField(null=True, blank=True)
    ends_at = models.DateTimeField(null=True, blank=True)
    usage_limit = models.PositiveIntegerField(null=True, blank=True)
    used_count = models.PositiveIntegerField(default=0)
    owner_type = models.CharField(max_length=12, choices=OwnerType.choices, default=OwnerType.ADMIN)
    seller = models.ForeignKey(SellerApplication, related_name='coupons', null=True, blank=True, on_delete=models.SET_NULL)
    approval_status = models.CharField(max_length=16, choices=ApprovalStatus.choices, default=ApprovalStatus.APPROVED)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ('-updated_at', 'code')

    def save(self, *args, **kwargs):
        self.code = (self.code or '').strip().upper()
        if self.owner_type == self.OwnerType.ADMIN:
            self.seller = None
            if not self.approval_status:
                self.approval_status = self.ApprovalStatus.APPROVED
        super().save(*args, **kwargs)

    @property
    def owner_label(self):
        if self.owner_type == self.OwnerType.SELLER and self.seller:
            return self.seller.store_name
        if self.owner_type == self.OwnerType.SELLER:
            return 'Seller'
        return 'Admin'

    @property
    def status_tone(self):
        if self.is_active and self.approval_status == self.ApprovalStatus.APPROVED and self.is_within_window:
            return 'success'
        if self.approval_status == self.ApprovalStatus.REJECTED or not self.is_active:
            return 'danger'
        return 'warning'

    @property
    def is_within_window(self):
        now = timezone.now()
        if self.starts_at and self.starts_at > now:
            return False
        if self.ends_at and self.ends_at < now:
            return False
        return True

    @property
    def usage_remaining(self):
        if self.usage_limit is None:
            return None
        return max(self.usage_limit - self.used_count, 0)

    def can_apply(self, subtotal):
        subtotal = subtotal or Decimal('0.00')
        if not self.is_active or self.approval_status != self.ApprovalStatus.APPROVED:
            return False, 'Coupon is inactive or not approved.'
        if not self.is_within_window:
            return False, 'Coupon is expired or not started yet.'
        if self.usage_limit is not None and self.used_count >= self.usage_limit:
            return False, 'Coupon usage limit reached.'
        if subtotal < self.min_order_amount:
            return False, f'Minimum order amount is {self.min_order_amount}.'
        return True, ''

    def calculate_discount(self, subtotal):
        allowed, _message = self.can_apply(subtotal)
        if not allowed:
            return Decimal('0.00')
        subtotal = subtotal or Decimal('0.00')
        if self.discount_type == self.DiscountType.PERCENT:
            discount = (subtotal * self.discount_value) / Decimal('100')
        else:
            discount = self.discount_value
        if self.max_discount is not None:
            discount = min(discount, self.max_discount)
        return min(discount, subtotal).quantize(Decimal('0.01'))

    def __str__(self):
        return self.code


class Offer(TimestampedModel):
    class DiscountType(models.TextChoices):
        PERCENT = 'percent', 'Percent'
        FLAT = 'flat', 'Flat Amount'

    title = models.CharField(max_length=140)
    description = models.TextField(blank=True)
    products = models.ManyToManyField(SpiceItem, related_name='flash_sales', blank=True)
    discount_type = models.CharField(max_length=16, choices=DiscountType.choices, default=DiscountType.PERCENT)
    discount_value = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    starts_at = models.DateTimeField(null=True, blank=True)
    ends_at = models.DateTimeField(null=True, blank=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ('-updated_at', 'title')

    @property
    def is_live(self):
        now = timezone.now()
        if not self.is_active:
            return False
        if self.starts_at and self.starts_at > now:
            return False
        if self.ends_at and self.ends_at < now:
            return False
        return True

    @property
    def status_tone(self):
        return 'success' if self.is_live else 'warning' if self.is_active else 'danger'

    def discount_amount_for(self, price):
        price = price or Decimal('0.00')
        if self.discount_type == self.DiscountType.PERCENT:
            discount = (price * self.discount_value) / Decimal('100')
        else:
            discount = self.discount_value
        return min(discount, price).quantize(Decimal('0.01'))

    def __str__(self):
        return self.title


class ShippingCharge(TimestampedModel):
    name = models.CharField(max_length=120)
    min_order_value = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    max_order_value = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    charge = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    free_delivery_threshold = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ('name',)

    def applies_to(self, subtotal):
        subtotal = subtotal or Decimal('0.00')
        if subtotal < self.min_order_value:
            return False
        if self.max_order_value is not None and subtotal > self.max_order_value:
            return False
        return True

    def charge_for(self, subtotal):
        subtotal = subtotal or Decimal('0.00')
        if self.free_delivery_threshold is not None and subtotal >= self.free_delivery_threshold:
            return Decimal('0.00')
        return self.charge

    def __str__(self):
        return self.name


class CourierPartner(TimestampedModel):
    name = models.CharField(max_length=140)
    contact_name = models.CharField(max_length=120, blank=True)
    contact_phone = models.CharField(max_length=20, blank=True)
    contact_email = models.EmailField(blank=True)
    website_url = models.URLField(blank=True)
    tracking_url = models.URLField(blank=True)
    api_details = models.TextField(blank=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ('name',)

    def __str__(self):
        return self.name


class DeliveryArea(TimestampedModel):
    pincode = models.CharField(max_length=12)
    city = models.CharField(max_length=80)
    state = models.CharField(max_length=80)
    is_serviceable = models.BooleanField(default=True)
    cod_available = models.BooleanField(default=True)
    estimated_days = models.PositiveSmallIntegerField(default=5)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ('state', 'city', 'pincode')
        unique_together = ('pincode', 'city')

    @property
    def status_tone(self):
        if self.is_active and self.is_serviceable:
            return 'success'
        return 'danger'

    def __str__(self):
        return f'{self.city} - {self.pincode}'


class ShipmentTracking(TimestampedModel):
    class Status(models.TextChoices):
        PENDING = 'pending', 'Pending'
        PACKED = 'packed', 'Packed'
        SHIPPED = 'shipped', 'Shipped'
        OUT_FOR_DELIVERY = 'out_for_delivery', 'Out for Delivery'
        DELIVERED = 'delivered', 'Delivered'
        CANCELLED = 'cancelled', 'Cancelled'

    order = models.ForeignKey(Order, related_name='shipments', on_delete=models.CASCADE)
    courier = models.ForeignKey(CourierPartner, related_name='shipments', null=True, blank=True, on_delete=models.SET_NULL)
    tracking_number = models.CharField(max_length=120, blank=True)
    tracking_url = models.URLField(blank=True)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.PENDING)
    last_location = models.CharField(max_length=160, blank=True)
    admin_note = models.CharField(max_length=240, blank=True)
    shipped_at = models.DateTimeField(null=True, blank=True)
    delivered_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ('-updated_at',)

    @property
    def status_tone(self):
        if self.status == self.Status.DELIVERED:
            return 'success'
        if self.status == self.Status.CANCELLED:
            return 'danger'
        if self.status == self.Status.PENDING:
            return 'warning'
        return 'info'

    @property
    def tracking_link(self):
        if self.tracking_url:
            return self.tracking_url
        if self.courier and self.courier.tracking_url:
            if '{tracking_number}' in self.courier.tracking_url:
                return self.courier.tracking_url.replace('{tracking_number}', self.tracking_number or '')
            return self.courier.tracking_url
        return ''

    def __str__(self):
        return self.tracking_number or self.order.order_number


class ProductReview(TimestampedModel):
    class Status(models.TextChoices):
        PENDING = 'pending', 'Pending'
        APPROVED = 'approved', 'Approved'
        REJECTED = 'rejected', 'Rejected'
        HIDDEN = 'hidden', 'Hidden'

    product = models.ForeignKey(SpiceItem, related_name='reviews', on_delete=models.CASCADE)
    customer = models.ForeignKey(User, related_name='product_reviews', null=True, blank=True, on_delete=models.SET_NULL)
    customer_name = models.CharField(max_length=120, blank=True)
    rating = models.PositiveSmallIntegerField(default=5)
    title = models.CharField(max_length=140, blank=True)
    comment = models.TextField(blank=True)
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.PENDING)

    class Meta:
        ordering = ('-created_at',)

    @property
    def status_tone(self):
        if self.status == self.Status.APPROVED:
            return 'success'
        if self.status in {self.Status.HIDDEN, self.Status.REJECTED}:
            return 'danger'
        return 'warning'

    @property
    def reviewer_label(self):
        if self.customer_name:
            return self.customer_name
        if self.customer:
            return self.customer.get_full_name() or self.customer.username
        return 'Customer'

    def __str__(self):
        return f'{self.product.name} - {self.rating}'


class SellerReview(TimestampedModel):
    class Status(models.TextChoices):
        PENDING = 'pending', 'Pending'
        APPROVED = 'approved', 'Approved'
        REJECTED = 'rejected', 'Rejected'
        HIDDEN = 'hidden', 'Hidden'

    seller = models.ForeignKey(SellerApplication, related_name='reviews', on_delete=models.CASCADE)
    customer = models.ForeignKey(User, related_name='seller_reviews', null=True, blank=True, on_delete=models.SET_NULL)
    customer_name = models.CharField(max_length=120, blank=True)
    rating = models.PositiveSmallIntegerField(default=5)
    comment = models.TextField(blank=True)
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.PENDING)
    admin_note = models.CharField(max_length=240, blank=True)

    class Meta:
        ordering = ('-created_at',)

    @property
    def reviewer_label(self):
        if self.customer_name:
            return self.customer_name
        if self.customer:
            return self.customer.get_full_name() or self.customer.username
        return 'Customer'

    @property
    def status_tone(self):
        if self.status == self.Status.APPROVED:
            return 'success'
        if self.status in {self.Status.REJECTED, self.Status.HIDDEN}:
            return 'danger'
        return 'warning'

    def __str__(self):
        return f'{self.seller.store_name} - {self.rating}'


class ReviewReport(TimestampedModel):
    class Status(models.TextChoices):
        PENDING = 'pending', 'Pending'
        APPROVED = 'approved', 'Approved'
        REJECTED = 'rejected', 'Rejected'
        REMOVED = 'removed', 'Removed'

    product_review = models.ForeignKey(ProductReview, related_name='reports', null=True, blank=True, on_delete=models.CASCADE)
    seller_review = models.ForeignKey(SellerReview, related_name='reports', null=True, blank=True, on_delete=models.CASCADE)
    reporter = models.ForeignKey(User, related_name='review_reports', null=True, blank=True, on_delete=models.SET_NULL)
    reporter_name = models.CharField(max_length=120, blank=True)
    reason = models.CharField(max_length=200)
    details = models.TextField(blank=True)
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.PENDING)
    admin_note = models.CharField(max_length=240, blank=True)

    class Meta:
        ordering = ('-created_at',)

    @property
    def review_label(self):
        if self.product_review:
            return f'Product: {self.product_review.product.name}'
        if self.seller_review:
            return f'Seller: {self.seller_review.seller.store_name}'
        return 'Review not linked'

    @property
    def reporter_label(self):
        if self.reporter_name:
            return self.reporter_name
        if self.reporter:
            return self.reporter.get_full_name() or self.reporter.username
        return 'Reporter'

    @property
    def status_tone(self):
        if self.status == self.Status.APPROVED:
            return 'success'
        if self.status in {self.Status.REJECTED, self.Status.REMOVED}:
            return 'danger'
        return 'warning'

    def __str__(self):
        return f'{self.review_label} reported'


class CouponRedemption(TimestampedModel):
    coupon = models.ForeignKey(Coupon, related_name='redemptions', on_delete=models.CASCADE)
    user = models.ForeignKey(User, related_name='coupon_redemptions', null=True, blank=True, on_delete=models.SET_NULL)
    order = models.OneToOneField(Order, related_name='coupon_redemption', on_delete=models.CASCADE)
    discount_amount = models.DecimalField(max_digits=10, decimal_places=2, default=0)

    class Meta:
        ordering = ('-created_at',)

    def __str__(self):
        return f'{self.coupon.code} - {self.order.order_number}'


class PushNotification(TimestampedModel):
    class Audience(models.TextChoices):
        ALL = 'all', 'All users'
        CUSTOMERS = 'customers', 'All customers'
        SELLERS = 'sellers', 'All sellers'
        SELECTED_CUSTOMERS = 'selected_customers', 'Selected customers'
        SELECTED_SELLERS = 'selected_sellers', 'Selected sellers'

    class Status(models.TextChoices):
        DRAFT = 'draft', 'Draft'
        SENT = 'sent', 'Sent'
        FAILED = 'failed', 'Failed'

    title = models.CharField(max_length=160)
    message = models.TextField()
    audience = models.CharField(max_length=24, choices=Audience.choices, default=Audience.ALL)
    customers = models.ManyToManyField(User, related_name='push_notifications', blank=True)
    sellers = models.ManyToManyField(SellerApplication, related_name='push_notifications', blank=True)
    sent_by = models.ForeignKey(User, related_name='sent_push_notifications', null=True, blank=True, on_delete=models.SET_NULL)
    sent_at = models.DateTimeField(null=True, blank=True)
    recipient_count = models.PositiveIntegerField(default=0)
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.DRAFT)
    is_read = models.BooleanField(default=False)

    class Meta:
        ordering = ('-created_at',)

    @property
    def status_tone(self):
        if self.status == self.Status.SENT:
            return 'success'
        if self.status == self.Status.FAILED:
            return 'danger'
        return 'warning'

    def __str__(self):
        return self.title


class SellerPayout(TimestampedModel):
    class Status(models.TextChoices):
        PENDING = 'pending', 'Pending'
        APPROVED = 'approved', 'Approved'
        PAID = 'paid', 'Paid'
        FAILED = 'failed', 'Failed'
        REJECTED = 'rejected', 'Rejected'

    payout_id = models.CharField(max_length=32, unique=True, blank=True)
    seller = models.ForeignKey(SellerApplication, related_name='payouts', on_delete=models.CASCADE)
    requested_by = models.ForeignKey(User, related_name='seller_payout_requests', null=True, blank=True, on_delete=models.SET_NULL)
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    bank_account = models.CharField(max_length=80, blank=True)
    upi_id = models.CharField(max_length=80, blank=True)
    remarks = models.TextField(blank=True)
    transaction_reference = models.CharField(max_length=120, blank=True)
    admin_note = models.CharField(max_length=240, blank=True)
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.PENDING)
    processed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ('-created_at',)

    def save(self, *args, **kwargs):
        if not self.payout_id:
            while True:
                candidate = f'PO-{timezone.now():%Y%m%d}-{get_random_string(6).upper()}'
                if not self.__class__.objects.filter(payout_id=candidate).exists():
                    self.payout_id = candidate
                    break
        super().save(*args, **kwargs)

    @property
    def status_tone(self):
        if self.status in {self.Status.APPROVED, self.Status.PAID}:
            return 'success'
        if self.status in {self.Status.FAILED, self.Status.REJECTED}:
            return 'danger'
        return 'warning'

    def __str__(self):
        return self.payout_id


class SupportTicket(TimestampedModel):
    class TicketType(models.TextChoices):
        CUSTOMER = 'customer', 'Customer'
        SELLER = 'seller', 'Seller'
        COMPLAINT = 'complaint', 'Complaint'

    class Status(models.TextChoices):
        OPEN = 'open', 'Open'
        REPLIED = 'replied', 'Replied'
        CLOSED = 'closed', 'Closed'

    ticket_type = models.CharField(max_length=16, choices=TicketType.choices, default=TicketType.CUSTOMER)
    subject = models.CharField(max_length=160)
    customer = models.ForeignKey(User, related_name='support_tickets', null=True, blank=True, on_delete=models.SET_NULL)
    seller = models.ForeignKey(SellerApplication, related_name='support_tickets', null=True, blank=True, on_delete=models.SET_NULL)
    message = models.TextField()
    admin_reply = models.TextField(blank=True)
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.OPEN)

    class Meta:
        ordering = ('-updated_at',)

    @property
    def status_tone(self):
        if self.status == self.Status.CLOSED:
            return 'success'
        if self.status == self.Status.REPLIED:
            return 'info'
        return 'warning'

    def __str__(self):
        return self.subject


class StaticContent(TimestampedModel):
    class Page(models.TextChoices):
        ABOUT = 'about-us', 'About Us'
        TERMS = 'terms', 'Terms & Conditions'
        PRIVACY = 'privacy-policy', 'Privacy Policy'
        RETURN = 'return-policy', 'Return Policy'
        FAQ = 'faq', 'FAQ'

    page = models.CharField(max_length=24, choices=Page.choices, unique=True)
    title = models.CharField(max_length=160)
    body = models.TextField(blank=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ('page',)

    def __str__(self):
        return self.get_page_display()


class NotificationTemplate(TimestampedModel):
    class TemplateType(models.TextChoices):
        EMAIL = 'email', 'Email'
        SMS = 'sms', 'SMS'
        PUSH = 'push', 'Push'

    name = models.CharField(max_length=140)
    slug = models.SlugField(max_length=160, blank=True)
    template_type = models.CharField(max_length=16, choices=TemplateType.choices, default=TemplateType.EMAIL)
    subject = models.CharField(max_length=160, blank=True)
    body = models.TextField()
    available_variables = models.CharField(max_length=240, blank=True, default='{{customer_name}}, {{order_id}}, {{seller_name}}, {{amount}}')
    purpose = models.CharField(max_length=80, blank=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ('template_type', 'name')

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = slugify(self.name) or 'template'
        super().save(*args, **kwargs)

    def __str__(self):
        return f'{self.name} ({self.get_template_type_display()})'


class WebsiteSetting(TimestampedModel):
    key = models.CharField(max_length=80, unique=True)
    label = models.CharField(max_length=140)
    value = models.TextField(blank=True)
    group = models.CharField(max_length=60, default='Store Configuration')
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ('group', 'label')

    def __str__(self):
        return self.label
