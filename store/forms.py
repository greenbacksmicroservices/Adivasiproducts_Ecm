import re

from django import forms
from django.contrib.auth.hashers import make_password
from django.contrib.auth.forms import AuthenticationForm, PasswordChangeForm
from django.contrib.auth.models import User
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError
from django.db.models import Max, Q
from django.utils.crypto import get_random_string

from .models import (
    AdminImportantDocument,
    AdminProfile,
    Banner,
    Category,
    Coupon,
    CourierPartner,
    CustomerAddress,
    CustomerProfile,
    DeliveryArea,
    HomePageSetting,
    NotificationTemplate,
    Offer,
    Order,
    OrderItem,
    ProductDetailImage,
    ProductQuantityOption,
    ProductReview,
    PushNotification,
    ReturnRequest,
    ReviewReport,
    SellerApplication,
    SellerApplicationExtraDocument,
    SellerPayout,
    SellerReview,
    ShipmentTracking,
    ShippingCharge,
    SpiceItem,
    SpiceItemPhoto,
    SubCategory,
    next_product_id,
)


MAX_PRODUCT_GALLERY_IMAGES = 10
MAX_PRODUCT_DETAIL_IMAGES = 10
MAX_ADMIN_QUANTITY_OPTIONS = 10
MAX_SELLER_QUANTITY_OPTIONS = 10
SELLER_APPLICATION_FILE_MAX_BYTES = 5 * 1024 * 1024
SELLER_ALLOWED_FILE_EXTENSIONS = {'jpg', 'jpeg', 'png', 'pdf'}
SELLER_IMAGE_EXTENSIONS = {'jpg', 'jpeg', 'png', 'webp'}
PRODUCT_IMAGE_ALLOWED_EXTENSIONS = {'jpg', 'jpeg', 'png', 'webp'}
PRODUCT_IMAGE_ACCEPT = '.jpg,.jpeg,.png,.webp'
PRODUCT_IMAGE_MAX_BYTES = SELLER_APPLICATION_FILE_MAX_BYTES
SELLER_PRODUCT_CATEGORY_CHOICES = [
    ('grocery-food', 'Grocery & Food'),
    ('spices-masala', 'Spices & Masala'),
    ('fashion-lifestyle', 'Fashion & Lifestyle'),
    ('home-living', 'Home & Living'),
    ('electronics', 'Electronics'),
    ('beauty-personal-care', 'Beauty & Personal Care'),
    ('handmade-crafts', 'Handmade & Crafts'),
    ('local-products', 'Local Products'),
    ('other', 'Other'),
]


class StyledFormMixin:
    def _style_fields(self):
        for field in self.fields.values():
            current_class = field.widget.attrs.get('class', '')
            field.widget.attrs['class'] = f"{current_class} form-input".strip()


class MultipleFileInput(forms.ClearableFileInput):
    allow_multiple_selected = True


class MultipleFileField(forms.FileField):
    widget = MultipleFileInput

    def clean(self, data, initial=None):
        if not data:
            return []
        single_file_clean = super().clean
        if isinstance(data, (list, tuple)):
            return [single_file_clean(item, initial) for item in data]
        return [single_file_clean(data, initial)]


def _seller_file_extension(uploaded_file):
    name = getattr(uploaded_file, 'name', '') or ''
    return name.rsplit('.', 1)[-1].lower() if '.' in name else ''


def _validate_seller_upload(uploaded_file, image_only=False):
    if not uploaded_file:
        return
    extension = _seller_file_extension(uploaded_file)
    allowed_extensions = SELLER_IMAGE_EXTENSIONS if image_only else SELLER_ALLOWED_FILE_EXTENSIONS
    if extension not in allowed_extensions:
        allowed = ', '.join(sorted(allowed_extensions)).upper()
        raise ValidationError(f'Only {allowed} files are allowed.')
    if uploaded_file.size > SELLER_APPLICATION_FILE_MAX_BYTES:
        raise ValidationError('Maximum file size is 5 MB.')


def _validate_product_image_upload(uploaded_file):
    if not uploaded_file:
        return
    extension = _seller_file_extension(uploaded_file)
    if extension not in PRODUCT_IMAGE_ALLOWED_EXTENSIONS:
        raise ValidationError('Only JPG, JPEG, PNG, or WEBP images are allowed.')
    if uploaded_file.size > PRODUCT_IMAGE_MAX_BYTES:
        raise ValidationError('Maximum image size is 5 MB.')


def _clean_indian_phone(value, field_label='Phone number'):
    value = (value or '').strip()
    if not re.fullmatch(r'[6-9]\d{9}', value):
        raise ValidationError(f'{field_label} must be a valid 10 digit number.')
    return value


def _normalize_upper(value):
    return (value or '').strip().upper()


def _preview_next_product_id():
    return next_product_id(SpiceItem)


class SubCategoryChoiceSelect(forms.Select):
    def __init__(self, *args, option_categories=None, **kwargs):
        self.option_categories = option_categories or {}
        super().__init__(*args, **kwargs)

    def create_option(self, name, value, label, selected, index, subindex=None, attrs=None):
        option = super().create_option(name, value, label, selected, index, subindex=subindex, attrs=attrs)
        if value:
            raw_value = str(getattr(value, 'value', value))
            meta = self.option_categories.get(raw_value)
            if meta:
                option['attrs']['data-category-id'] = str(meta['category_id'])
                option['attrs']['data-category-slug'] = meta['category_slug']
                option['attrs']['data-category-name'] = meta['category_name']
        return option


def _sub_category_choice_data(include_inactive=False):
    queryset = SubCategory.objects.select_related('category').order_by(
        'category__display_order',
        'category__name',
        'display_order',
        'name',
    )
    if not include_inactive:
        queryset = queryset.filter(is_active=True)
    records = list(queryset)
    choices = [('', '---------')]
    option_categories = {}
    for record in records:
        value = str(record.pk)
        choices.append((value, record.name))
        option_categories[value] = {
            'category_id': record.category_id,
            'category_slug': record.category.slug,
            'category_name': record.category.name,
            'name': record.name,
        }
    return records, choices, option_categories


class ProductSubCategoryFormMixin:
    def _configure_product_identity_fields(self):
        if 'product_id' in self.fields:
            self.fields['product_id'].initial = self.instance.product_id if self.instance and self.instance.pk else _preview_next_product_id()
            self.fields['product_id'].help_text = 'Auto generated after save.'
            self.fields['product_id'].widget.attrs.update({'readonly': 'readonly'})

    def _configure_product_category_fields(self):
        if 'category' in self.fields:
            self.fields['category'].required = True
            self.fields['category'].queryset = Category.objects.filter(is_active=True).order_by('display_order', 'name')
            self.fields['category'].widget.attrs.update({'data-category-select': 'true'})

        if 'sub_category' not in self.fields:
            return

        records, choices, option_categories = _sub_category_choice_data()
        initial_value = ''
        current_sub_category = (self.instance.sub_category or '').strip() if self.instance and self.instance.pk else ''
        current_category_id = self.instance.category_id if self.instance and self.instance.pk else None
        if current_sub_category:
            for record in records:
                if record.category_id == current_category_id and record.name.lower() == current_sub_category.lower():
                    initial_value = str(record.pk)
                    break
            if not initial_value:
                legacy_value = f'legacy:{current_sub_category}'
                choices.append((legacy_value, current_sub_category))
                option_categories[legacy_value] = {
                    'category_id': current_category_id or '',
                    'category_slug': self.instance.category.slug if self.instance.category else '',
                    'category_name': self.instance.category.name if self.instance.category else '',
                    'name': current_sub_category,
                }
                initial_value = legacy_value

        self.fields['sub_category'].choices = choices
        self.fields['sub_category'].initial = initial_value
        self.fields['sub_category'].required = False
        self.fields['sub_category'].help_text = 'Optional. Options update automatically after selecting Category.'
        self.fields['sub_category'].widget = SubCategoryChoiceSelect(
            option_categories=option_categories,
            attrs={
                'class': 'form-input',
                'data-subcategory-select': 'true',
            },
        )

    def clean_sub_category(self):
        value = self.cleaned_data.get('sub_category')
        if not value:
            return ''
        if isinstance(value, str) and value.startswith('legacy:'):
            return value.split(':', 1)[1][:120]
        try:
            sub_category = SubCategory.objects.select_related('category').get(pk=value)
        except (SubCategory.DoesNotExist, ValueError, TypeError):
            raise ValidationError('Select a valid sub category.')

        category = self.cleaned_data.get('category')
        if category and sub_category.category_id != category.pk:
            raise ValidationError('Selected sub category does not belong to this category.')
        return sub_category.name


class LoginForm(StyledFormMixin, AuthenticationForm):
    username = forms.CharField(
        widget=forms.TextInput(
            attrs={
                'placeholder': 'Email ID',
                'autocomplete': 'username',
                'autofocus': True,
            }
        )
    )
    password = forms.CharField(
        widget=forms.PasswordInput(
            attrs={
                'placeholder': 'Password',
                'autocomplete': 'current-password',
            }
        )
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._style_fields()

    def clean(self):
        username = self.cleaned_data.get('username')
        if username:
            lookup_value = username.strip()
            email_user = User.objects.filter(email__iexact=lookup_value).first()
            if email_user:
                self.cleaned_data['username'] = email_user.get_username()
        return super().clean()


class RegisterForm(StyledFormMixin, forms.Form):
    first_name = forms.CharField(max_length=150, required=True)
    email = forms.EmailField(required=True)
    phone = forms.CharField(max_length=20, required=True)
    photo = forms.ImageField(required=False)
    password1 = forms.CharField(
        label='Password',
        widget=forms.PasswordInput(attrs={'autocomplete': 'new-password'}),
    )
    password2 = forms.CharField(
        label='Confirm password',
        widget=forms.PasswordInput(attrs={'autocomplete': 'new-password'}),
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['first_name'].label = 'Full Name'
        self.fields['email'].label = 'Mail ID'
        self.fields['phone'].label = 'Phone'
        self.fields['photo'].label = 'Photo'
        self.fields['first_name'].widget.attrs['placeholder'] = 'Your full name'
        self.fields['email'].widget.attrs['placeholder'] = 'you@example.com'
        self.fields['phone'].widget.attrs['placeholder'] = 'Phone number'
        self.fields['password1'].widget.attrs['placeholder'] = 'Password'
        self.fields['password2'].widget.attrs['placeholder'] = 'Confirm password'
        self.fields['photo'].widget.attrs['accept'] = 'image/*'
        self._style_fields()

    def clean_email(self):
        email = self.cleaned_data['email'].strip().lower()
        if User.objects.filter(email__iexact=email).exists() or User.objects.filter(username__iexact=email).exists():
            raise ValidationError('This email already has an account.')
        return email

    def clean_password1(self):
        password = self.cleaned_data['password1']
        validate_password(password)
        return password

    def clean(self):
        cleaned_data = super().clean()
        password1 = cleaned_data.get('password1')
        password2 = cleaned_data.get('password2')
        if password1 and password2 and password1 != password2:
            self.add_error('password2', 'Passwords do not match.')
        return cleaned_data

    def save(self):
        email = self.cleaned_data['email']
        user = User.objects.create_user(
            username=email,
            email=email,
            password=self.cleaned_data['password1'],
            first_name=self.cleaned_data['first_name'],
        )
        CustomerProfile.objects.create(
            user=user,
            phone=self.cleaned_data['phone'],
            photo=self.cleaned_data.get('photo'),
            email_verified=True,
        )
        return user


class EmailOTPRequestForm(StyledFormMixin, forms.Form):
    email = forms.EmailField(
        label='Email Address',
        widget=forms.EmailInput(attrs={'placeholder': 'you@example.com', 'autocomplete': 'email'}),
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._style_fields()

    def clean_email(self):
        return self.cleaned_data['email'].strip().lower()


class OTPVerifyForm(StyledFormMixin, forms.Form):
    otp = forms.CharField(
        label='OTP',
        min_length=6,
        max_length=6,
        widget=forms.HiddenInput(),
    )

    def clean_otp(self):
        otp = ''.join(ch for ch in self.cleaned_data.get('otp', '') if ch.isdigit())
        if len(otp) != 6:
            raise ValidationError('Enter the 6 digit OTP.')
        return otp


class ForgotPasswordSetForm(StyledFormMixin, forms.Form):
    password1 = forms.CharField(
        label='New Password',
        widget=forms.PasswordInput(attrs={'placeholder': 'New password', 'autocomplete': 'new-password'}),
    )
    password2 = forms.CharField(
        label='Confirm New Password',
        widget=forms.PasswordInput(attrs={'placeholder': 'Confirm new password', 'autocomplete': 'new-password'}),
    )

    def __init__(self, *args, user=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.user = user
        self._style_fields()

    def clean_password1(self):
        password = self.cleaned_data.get('password1')
        validate_password(password, self.user)
        return password

    def clean(self):
        cleaned_data = super().clean()
        password1 = cleaned_data.get('password1')
        password2 = cleaned_data.get('password2')
        if password1 and password2 and password1 != password2:
            self.add_error('password2', 'Passwords do not match.')
        return cleaned_data


class CustomerProfileForm(StyledFormMixin, forms.ModelForm):
    first_name = forms.CharField(max_length=150, required=True, label='Full Name')
    email = forms.EmailField(required=True, label='Mail ID')

    class Meta:
        model = CustomerProfile
        fields = ['first_name', 'email', 'phone', 'photo', 'language']
        labels = {
            'phone': 'Phone',
            'photo': 'Photo',
            'language': 'Language',
        }

    def __init__(self, *args, user=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.user = user or self.instance.user
        self.fields['first_name'].initial = self.user.first_name
        self.fields['email'].initial = self.user.email
        self.fields['photo'].widget.attrs['accept'] = 'image/*'
        self._style_fields()

    def clean_email(self):
        email = self.cleaned_data['email'].strip().lower()
        existing = User.objects.filter(email__iexact=email).exclude(pk=self.user.pk).exists()
        username_existing = User.objects.filter(username__iexact=email).exclude(pk=self.user.pk).exists()
        if existing or username_existing:
            raise ValidationError('This email is already used by another account.')
        return email

    def save(self, commit=True):
        profile = super().save(commit=False)
        self.user.first_name = self.cleaned_data['first_name']
        self.user.email = self.cleaned_data['email']
        self.user.username = self.cleaned_data['email']
        if commit:
            self.user.save(update_fields=['first_name', 'email', 'username'])
            profile.save()
        return profile


class AdminProfileForm(StyledFormMixin, forms.ModelForm):
    name = forms.CharField(max_length=150, required=True, label='Admin name')
    email = forms.EmailField(required=True, label='Gmail / Email')

    class Meta:
        model = AdminProfile
        fields = ['name', 'email', 'phone', 'date_of_birth']
        labels = {
            'phone': 'Phone',
            'date_of_birth': 'Date of birth',
        }
        widgets = {
            'date_of_birth': forms.DateInput(attrs={'type': 'date'}),
        }

    def __init__(self, *args, user=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.user = user or self.instance.user
        self.fields['name'].initial = self.user.first_name or self.user.get_full_name() or self.user.username
        self.fields['email'].initial = self.user.email
        self._style_fields()

    def clean_email(self):
        email = (self.cleaned_data.get('email') or '').strip().lower()
        if User.objects.filter(email__iexact=email).exclude(pk=self.user.pk).exists():
            raise ValidationError('This email is already used by another account.')
        return email

    def save(self, commit=True):
        profile = super().save(commit=False)
        self.user.first_name = self.cleaned_data['name'].strip()
        self.user.email = self.cleaned_data['email']
        self.user.username = self.cleaned_data['email']
        if commit:
            self.user.save(update_fields=['first_name', 'email', 'username'])
            profile.save()
        return profile


class AdminMediaForm(StyledFormMixin, forms.ModelForm):
    class Meta:
        model = AdminProfile
        fields = ['logo', 'profile_photo']
        labels = {
            'logo': 'Logo upload',
            'profile_photo': 'Admin profile photo',
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['logo'].widget.attrs['accept'] = 'image/*'
        self.fields['profile_photo'].widget.attrs['accept'] = 'image/*'
        self._style_fields()


class AdminPasswordChangeForm(PasswordChangeForm, StyledFormMixin):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field in self.fields.values():
            field.help_text = ''
        self._style_fields()


class AdminImportantDocumentForm(StyledFormMixin, forms.ModelForm):
    class Meta:
        model = AdminImportantDocument
        fields = ['name', 'document']
        labels = {
            'name': 'Document name',
            'document': 'Document upload',
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['document'].widget.attrs['accept'] = '.pdf,.jpg,.jpeg,.png,.webp,.doc,.docx'
        self._style_fields()


class CustomerAddressForm(StyledFormMixin, forms.ModelForm):
    class Meta:
        model = CustomerAddress
        fields = [
            'address_type',
            'label',
            'full_name',
            'phone',
            'alternate_phone',
            'email',
            'house',
            'area',
            'landmark',
            'city',
            'district',
            'state',
            'pincode',
            'country',
            'is_default',
        ]
        labels = {
            'label': 'Address name',
            'full_name': 'Full name',
            'alternate_phone': 'Alternate phone number',
            'house': 'House / Flat / Building',
            'area': 'Area / Street / Village',
            'pincode': 'PIN code',
            'is_default': 'Use as default address',
            'address_type': 'Address type',
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['label'].required = False
        self.fields['alternate_phone'].required = False
        self.fields['email'].required = False
        self.fields['landmark'].required = False
        self.fields['house'].required = True
        self.fields['area'].required = True
        self.fields['city'].required = True
        self.fields['district'].required = True
        self.fields['state'].required = True
        self.fields['pincode'].required = True
        self.fields['country'].initial = self.fields['country'].initial or 'India'
        self.fields['country'].widget.attrs['readonly'] = 'readonly'
        placeholders = {
            'full_name': 'Receiver full name',
            'phone': '10 digit phone number',
            'alternate_phone': 'Optional alternate phone',
            'email': 'Optional email',
            'house': 'House no, flat, floor, building',
            'area': 'Street, area, village',
            'landmark': 'Nearby landmark',
            'city': 'City',
            'district': 'District',
            'state': 'State',
            'pincode': 'PIN code',
        }
        for field_name, placeholder in placeholders.items():
            self.fields[field_name].widget.attrs['placeholder'] = placeholder
        self._style_fields()

    def clean_phone(self):
        phone = (self.cleaned_data.get('phone') or '').strip()
        digits = re.sub(r'\D', '', phone)
        if len(digits) == 12 and digits.startswith('91'):
            return phone
        if len(digits) != 10:
            raise ValidationError('Enter a valid 10 digit phone number.')
        return phone

    def clean_alternate_phone(self):
        phone = (self.cleaned_data.get('alternate_phone') or '').strip()
        if not phone:
            return ''
        digits = re.sub(r'\D', '', phone)
        if len(digits) == 12 and digits.startswith('91'):
            return phone
        if len(digits) != 10:
            raise ValidationError('Enter a valid 10 digit alternate phone number.')
        return phone

    def clean_pincode(self):
        pincode = (self.cleaned_data.get('pincode') or '').strip()
        if not re.fullmatch(r'\d{6}', pincode):
            raise ValidationError('Enter a valid 6 digit PIN code.')
        if DeliveryArea.objects.exists():
            area = DeliveryArea.objects.filter(pincode=pincode, is_active=True, is_serviceable=True).first()
            if not area:
                raise ValidationError('Delivery is not available for this PIN code right now.')
        return pincode


def _generate_admin_password():
    return get_random_string(
        12,
        allowed_chars='ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz23456789',
    )


def _build_form_fieldsets(form, definitions):
    fieldsets = []
    for title, description, field_names in definitions:
        fields = [form[field_name] for field_name in field_names if field_name in form.fields]
        if fields:
            fieldsets.append(
                {
                    'title': title,
                    'description': description,
                    'fields': fields,
                }
            )
    return fieldsets


class AdminCustomerForm(StyledFormMixin, forms.Form):
    first_name = forms.CharField(max_length=150, required=True, label='Full Name')
    email = forms.EmailField(required=True, label='Email')
    phone = forms.CharField(max_length=20, required=True, label='Phone')
    photo = forms.ImageField(required=False, label='Profile photo')
    is_active = forms.BooleanField(required=False, initial=True, label='Active customer account')
    generate_password = forms.BooleanField(required=False, label='Generate password automatically')
    password1 = forms.CharField(
        required=False,
        label='Temporary password',
        widget=forms.PasswordInput(attrs={'autocomplete': 'new-password'}),
    )
    password2 = forms.CharField(
        required=False,
        label='Confirm temporary password',
        widget=forms.PasswordInput(attrs={'autocomplete': 'new-password'}),
    )
    address_line = forms.CharField(
        required=False,
        label='Address',
        widget=forms.Textarea(attrs={'rows': 3}),
    )
    city = forms.CharField(max_length=80, required=False)
    state = forms.CharField(max_length=80, required=False)
    pincode = forms.CharField(max_length=12, required=False, label='PIN code')

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.generated_password = ''
        self.fields['first_name'].widget.attrs['placeholder'] = 'Customer full name'
        self.fields['email'].widget.attrs.update({'placeholder': 'customer@example.com', 'autocomplete': 'email'})
        self.fields['phone'].widget.attrs['placeholder'] = '10 digit phone number'
        self.fields['photo'].widget.attrs['accept'] = 'image/*'
        self.fields['password1'].help_text = 'Required unless automatic password generation is selected.'
        self.fields['address_line'].help_text = 'Optional. If any address field is filled, address, city, state, and PIN code are required.'
        self.admin_fieldsets = _build_form_fieldsets(
            self,
            [
                ('Customer Details', 'Create a customer login and profile.', ['first_name', 'email', 'phone', 'photo', 'is_active']),
                ('Password', 'Set a temporary password or let the system generate one.', ['generate_password', 'password1', 'password2']),
                ('Optional Address', 'Save a first delivery address if available.', ['address_line', 'city', 'state', 'pincode']),
            ],
        )
        self._style_fields()

    def clean_email(self):
        email = self.cleaned_data['email'].strip().lower()
        if User.objects.filter(email__iexact=email).exists() or User.objects.filter(username__iexact=email).exists():
            raise ValidationError('This email already has an account.')
        return email

    def clean_phone(self):
        phone = _clean_indian_phone(self.cleaned_data.get('phone'), 'Phone number')
        if CustomerProfile.objects.filter(phone=phone).exists():
            raise ValidationError('This phone number is already used by another customer.')
        return phone

    def clean_password1(self):
        password = self.cleaned_data.get('password1', '')
        if password:
            validate_password(password)
        return password

    def clean(self):
        cleaned_data = super().clean()
        generate_password = cleaned_data.get('generate_password')
        password1 = cleaned_data.get('password1')
        password2 = cleaned_data.get('password2')
        if not generate_password and not password1:
            self.add_error('password1', 'Enter a temporary password or choose automatic generation.')
        if not generate_password and password1 and not password2:
            self.add_error('password2', 'Confirm the temporary password.')
        if password1 and password2 and password1 != password2:
            self.add_error('password2', 'Passwords do not match.')

        address_fields = ['address_line', 'city', 'state', 'pincode']
        has_address = any((cleaned_data.get(field_name) or '').strip() for field_name in address_fields)
        if has_address:
            for field_name in address_fields:
                if not (cleaned_data.get(field_name) or '').strip():
                    self.add_error(field_name, 'This field is required when adding an address.')
            pincode = (cleaned_data.get('pincode') or '').strip()
            if pincode and not re.fullmatch(r'\d{6}', pincode):
                self.add_error('pincode', 'Enter a valid 6 digit PIN code.')
        return cleaned_data

    def save(self):
        password = self.cleaned_data.get('password1')
        if self.cleaned_data.get('generate_password'):
            password = _generate_admin_password()
            self.generated_password = password

        email = self.cleaned_data['email']
        user = User.objects.create_user(
            username=email,
            email=email,
            password=password,
            first_name=self.cleaned_data['first_name'],
        )
        user.is_active = self.cleaned_data.get('is_active', True)
        user.save(update_fields=['is_active'])

        CustomerProfile.objects.create(
            user=user,
            phone=self.cleaned_data['phone'],
            photo=self.cleaned_data.get('photo'),
            email_verified=True,
        )

        if any((self.cleaned_data.get(field_name) or '').strip() for field_name in ['address_line', 'city', 'state', 'pincode']):
            CustomerAddress.objects.create(
                user=user,
                label='Home',
                full_name=self.cleaned_data['first_name'],
                phone=self.cleaned_data['phone'],
                email=email,
                address_line=self.cleaned_data.get('address_line', '').strip(),
                city=self.cleaned_data.get('city', '').strip(),
                state=self.cleaned_data.get('state', '').strip(),
                pincode=self.cleaned_data.get('pincode', '').strip(),
                is_default=True,
            )
        return user


class AdminCustomerEditForm(StyledFormMixin, forms.ModelForm):
    first_name = forms.CharField(max_length=150, required=True, label='Full Name')
    email = forms.EmailField(required=True, label='Mail ID')
    new_password = forms.CharField(
        required=False,
        label='New password',
        widget=forms.TextInput(attrs={'autocomplete': 'new-password'}),
        help_text='Optional. Fill this or tick generate password below.',
    )
    generate_password = forms.BooleanField(
        required=False,
        label='Generate new password automatically',
    )

    class Meta:
        model = CustomerProfile
        fields = ['first_name', 'email', 'phone', 'photo', 'language', 'new_password', 'generate_password']
        labels = {
            'phone': 'Phone',
            'photo': 'Photo',
            'language': 'Language',
        }

    def __init__(self, *args, user=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.user = user or self.instance.user
        self.generated_password = ''
        self.fields['first_name'].initial = self.user.first_name
        self.fields['email'].initial = self.user.email
        self.fields['photo'].widget.attrs['accept'] = 'image/*'
        self._style_fields()

    def clean_email(self):
        email = self.cleaned_data['email'].strip().lower()
        email_exists = User.objects.filter(email__iexact=email).exclude(pk=self.user.pk).exists()
        username_exists = User.objects.filter(username__iexact=email).exclude(pk=self.user.pk).exists()
        if email_exists or username_exists:
            raise ValidationError('This email is already used by another account.')
        return email

    def clean_new_password(self):
        password = self.cleaned_data.get('new_password', '')
        if password:
            validate_password(password, self.user)
        return password

    def save(self, commit=True):
        profile = super().save(commit=False)
        self.user.first_name = self.cleaned_data['first_name']
        self.user.email = self.cleaned_data['email']
        self.user.username = self.cleaned_data['email']

        password = self.cleaned_data.get('new_password', '')
        if self.cleaned_data.get('generate_password'):
            password = _generate_admin_password()
            self.generated_password = password
        if password:
            self.user.set_password(password)

        if commit:
            self.user.save()
            profile.save()
        return profile


class LegacyAdminSellerApplicationForm(StyledFormMixin, forms.ModelForm):
    password = forms.CharField(
        widget=forms.PasswordInput(attrs={'autocomplete': 'new-password'}),
        help_text='Seller can login with this password after approval.',
    )

    class Meta:
        model = SellerApplication
        fields = [
            'name',
            'email',
            'phone',
            'password',
            'store_name',
            'business_type',
            'aadhaar_number',
            'pan_number',
            'gst_number',
            'bank_account_name',
            'bank_account_number',
            'bank_ifsc',
            'business_address',
            'pickup_address',
            'aadhaar_document',
            'pan_document',
            'gst_document',
            'trade_license_document',
            'company_document',
            'bank_document',
            'address_proof',
            'status',
            'admin_note',
        ]
        widgets = {
            'business_address': forms.Textarea(attrs={'rows': 3}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._style_fields()
        self.fields['status'].initial = SellerApplication.Status.APPROVED
        for field_name in ['aadhaar_number', 'pan_number', 'gst_number', 'bank_account_name', 'bank_account_number', 'bank_ifsc', 'business_address', 'pickup_address', 'admin_note']:
            self.fields[field_name].required = False
        for field_name in ['aadhaar_document', 'pan_document', 'gst_document', 'trade_license_document', 'company_document', 'bank_document', 'address_proof']:
            self.fields[field_name].required = False
            self.fields[field_name].widget.attrs['accept'] = '.pdf,.jpg,.jpeg,.png'

    def clean_email(self):
        email = self.cleaned_data['email'].strip().lower()
        exists = SellerApplication.objects.filter(email__iexact=email).exists()
        if exists:
            raise ValidationError('A seller application with this email already exists.')
        return email

    def save(self, commit=True):
        application = super().save(commit=False)
        application.password_hash = make_password(self.cleaned_data['password'])
        application.email_verified = True
        if commit:
            application.save()
        return application


class CategoryForm(StyledFormMixin, forms.ModelForm):
    class Meta:
        model = Category
        fields = [
            'name',
            'description',
            'icon_emoji',
            'highlight_color',
            'image_file',
            'display_order',
            'is_active',
        ]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._style_fields()
        self.fields['image_file'].label = 'Upload Category Photo'
        self.fields['image_file'].widget.attrs['accept'] = 'image/*'


class SubCategoryForm(StyledFormMixin, forms.ModelForm):
    class Meta:
        model = SubCategory
        fields = [
            'category',
            'name',
            'image_file',
        ]
        labels = {
            'name': 'Sub Category Name',
            'category': 'Category',
            'image_file': 'Photo',
        }

    def __init__(self, *args, fixed_category=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.fixed_category = fixed_category
        self.fields['category'].queryset = Category.objects.order_by('display_order', 'name')
        self.fields['category'].required = True
        self.fields['name'].required = True
        self.fields['image_file'].required = not bool(self.instance and self.instance.pk and self.instance.image_file)
        self.fields['image_file'].widget.attrs['accept'] = 'image/*'
        if fixed_category:
            self.fields['category'].initial = fixed_category
            self.fields['category'].widget = forms.HiddenInput()
        self._style_fields()

    def clean(self):
        cleaned_data = super().clean()
        if self.fixed_category:
            cleaned_data['category'] = self.fixed_category
        image_file = cleaned_data.get('image_file')
        if not image_file and not (self.instance and self.instance.pk and self.instance.image_file):
            self.add_error('image_file', 'Upload a sub category photo.')
        return cleaned_data


class BannerForm(StyledFormMixin, forms.ModelForm):
    class Meta:
        model = Banner
        fields = [
            'title',
            'subtitle',
            'image_file',
            'placement',
            'cta_text',
            'cta_link',
            'display_order',
            'is_active',
        ]

    def __init__(self, *args, fixed_placement=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.fixed_placement = fixed_placement
        self._style_fields()
        self.fields['image_file'].label = 'Upload Banner Photo'
        self.fields['image_file'].widget.attrs['accept'] = 'image/*'
        self.fields['placement'].help_text = 'Choose Large Hero for the big banner or Small Photo Slider for the compact photo-only strip.'
        if fixed_placement:
            self.fields['placement'].initial = fixed_placement
            self.fields['placement'].widget = forms.HiddenInput()

    def clean(self):
        cleaned_data = super().clean()
        image_file = cleaned_data.get('image_file')
        if self.fixed_placement:
            cleaned_data['placement'] = self.fixed_placement

        if not image_file and not self.instance.image_source:
            self.add_error('image_file', 'Upload an image file.')
        return cleaned_data


class HomePageSettingForm(StyledFormMixin, forms.ModelForm):
    class Meta:
        model = HomePageSetting
        fields = [
            'hero_enabled',
            'hero_interval_ms',
            'compact_hero_enabled',
            'compact_hero_interval_ms',
        ]
        labels = {
            'hero_enabled': 'Show large hero banner on Top Deals',
            'hero_interval_ms': 'Large hero slide speed',
            'compact_hero_enabled': 'Show small photo slider on Top Deals',
            'compact_hero_interval_ms': 'Small slider speed',
        }
        help_texts = {
            'hero_interval_ms': 'Use 3000 for automatic large hero change every 3 seconds.',
            'compact_hero_interval_ms': 'Use 3000 for automatic small photo slide every 3 seconds.',
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._style_fields()
        self.fields['hero_interval_ms'].widget.attrs.update({
            'min': 1500,
            'step': 500,
        })
        self.fields['compact_hero_interval_ms'].widget.attrs.update({
            'min': 1500,
            'step': 500,
        })


class SellerApplicationForm(StyledFormMixin, forms.ModelForm):
    password = forms.CharField(
        label='Password',
        widget=forms.PasswordInput(attrs={'placeholder': 'Create password', 'autocomplete': 'new-password'}),
    )
    confirm_password = forms.CharField(
        label='Confirm Password',
        widget=forms.PasswordInput(attrs={'placeholder': 'Confirm password', 'autocomplete': 'new-password'}),
    )
    confirm_bank_account_number = forms.CharField(
        label='Confirm Account Number',
        widget=forms.TextInput(attrs={'placeholder': 'Re-enter account number', 'autocomplete': 'off'}),
    )
    gst_available = forms.TypedChoiceField(
        label='GST Available?',
        choices=(('no', 'No'), ('yes', 'Yes')),
        coerce=lambda value: value == 'yes',
        empty_value=False,
        widget=forms.RadioSelect,
    )
    product_categories = forms.MultipleChoiceField(
        label='Product Categories',
        choices=SELLER_PRODUCT_CATEGORY_CHOICES,
        widget=forms.SelectMultiple(attrs={'size': 6}),
    )
    primary_category = forms.ChoiceField(
        label='Primary Category',
        choices=[('', 'Select primary category')] + SELLER_PRODUCT_CATEGORY_CHOICES,
    )
    sells_handmade = forms.TypedChoiceField(
        label='Do you sell handmade/local products?',
        choices=(('no', 'No'), ('yes', 'Yes')),
        coerce=lambda value: value == 'yes',
        empty_value=False,
        widget=forms.RadioSelect,
    )
    extra_documents = MultipleFileField(
        required=False,
        label='Any Extra Document',
        help_text='Optional. JPG, PNG, or PDF up to 5 MB each.',
        widget=MultipleFileInput(attrs={'multiple': True, 'accept': '.jpg,.jpeg,.png,.pdf'}),
    )

    class Meta:
        model = SellerApplication
        fields = [
            'name',
            'email',
            'phone',
            'alternate_phone',
            'profile_photo',
            'store_name',
            'store_display_name',
            'store_description',
            'business_type',
            'store_logo',
            'store_banner',
            'aadhaar_number',
            'pan_number',
            'owner_dob',
            'owner_address',
            'aadhaar_front',
            'aadhaar_back',
            'pan_card',
            'gst_available',
            'gst_number',
            'legal_business_name',
            'tax_pan_number',
            'gst_document',
            'business_registration_certificate',
            'bank_account_name',
            'bank_name',
            'bank_account_number',
            'bank_ifsc',
            'branch_name',
            'cancelled_cheque',
            'pickup_contact_name',
            'pickup_phone',
            'pickup_address_line1',
            'pickup_address_line2',
            'pickup_city',
            'pickup_state',
            'pickup_pincode',
            'pickup_landmark',
            'pickup_same_as_owner',
            'product_categories',
            'primary_category',
            'approx_products_count',
            'brand_name',
            'sells_handmade',
            'shop_photo',
            'owner_photo',
            'business_proof',
            'address_proof',
            'signature_upload',
            'confirm_details',
            'terms_accepted',
            'approval_access_ack',
        ]
        labels = {
            'name': 'Full Name',
            'email': 'Email Address',
            'phone': 'Phone Number',
            'alternate_phone': 'Alternate Phone Number',
            'profile_photo': 'Profile Photo',
            'store_name': 'Shop Name',
            'store_display_name': 'Store Display Name',
            'store_description': 'Store Description',
            'business_type': 'Business Type',
            'store_logo': 'Store Logo',
            'store_banner': 'Store Banner',
            'aadhaar_number': 'Aadhaar Number',
            'pan_number': 'PAN Number',
            'owner_dob': 'Owner DOB',
            'owner_address': 'Owner Address',
            'aadhaar_front': 'Aadhaar Front Upload',
            'aadhaar_back': 'Aadhaar Back Upload',
            'pan_card': 'PAN Card Upload',
            'gst_number': 'GST Number',
            'legal_business_name': 'Legal Business Name',
            'tax_pan_number': 'PAN Number',
            'gst_document': 'GST Certificate Upload',
            'business_registration_certificate': 'Business Registration Certificate',
            'bank_account_name': 'Account Holder Name',
            'bank_name': 'Bank Name',
            'bank_account_number': 'Account Number',
            'bank_ifsc': 'IFSC Code',
            'branch_name': 'Branch Name',
            'cancelled_cheque': 'Cancelled Cheque / Passbook Upload',
            'pickup_contact_name': 'Pickup Contact Name',
            'pickup_phone': 'Pickup Phone',
            'pickup_address_line1': 'Address Line 1',
            'pickup_address_line2': 'Address Line 2',
            'pickup_city': 'City',
            'pickup_state': 'State',
            'pickup_pincode': 'Pincode',
            'pickup_landmark': 'Landmark',
            'pickup_same_as_owner': 'Same as owner address',
            'approx_products_count': 'Approx Products Count',
            'brand_name': 'Brand Name',
            'shop_photo': 'Shop Photo',
            'owner_photo': 'Owner Photo',
            'business_proof': 'Business Proof',
            'address_proof': 'Address Proof',
            'signature_upload': 'Signature Upload',
            'confirm_details': 'I confirm all details are correct.',
            'terms_accepted': 'I agree to marketplace seller terms and conditions.',
            'approval_access_ack': 'I agree that dashboard access will be enabled only after admin approval.',
        }
        widgets = {
            'owner_dob': forms.DateInput(attrs={'type': 'date'}),
            'store_description': forms.Textarea(attrs={'rows': 4}),
            'owner_address': forms.Textarea(attrs={'rows': 4}),
            'pickup_address_line1': forms.TextInput(),
            'pickup_address_line2': forms.TextInput(),
            'confirm_details': forms.CheckboxInput(),
            'terms_accepted': forms.CheckboxInput(),
            'approval_access_ack': forms.CheckboxInput(),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.extra_document_rows = []
        self.fields['password'].help_text = 'Dashboard login is enabled only after admin approval.'
        if self.instance and self.instance.pk and self.instance.product_categories:
            self.initial['product_categories'] = self.instance.product_category_list
        if self.instance and self.instance.pk:
            self.initial['gst_available'] = 'yes' if self.instance.gst_available else 'no'
            self.initial['sells_handmade'] = 'yes' if self.instance.sells_handmade else 'no'

        required_fields = [
            'name',
            'email',
            'phone',
            'password',
            'confirm_password',
            'store_name',
            'store_display_name',
            'store_description',
            'business_type',
            'aadhaar_number',
            'pan_number',
            'owner_dob',
            'owner_address',
            'aadhaar_front',
            'pan_card',
            'gst_available',
            'legal_business_name',
            'tax_pan_number',
            'bank_account_name',
            'bank_name',
            'bank_account_number',
            'confirm_bank_account_number',
            'bank_ifsc',
            'branch_name',
            'cancelled_cheque',
            'pickup_contact_name',
            'pickup_phone',
            'pickup_address_line1',
            'pickup_city',
            'pickup_state',
            'pickup_pincode',
            'product_categories',
            'primary_category',
            'approx_products_count',
            'sells_handmade',
            'shop_photo',
            'owner_photo',
            'business_proof',
            'address_proof',
            'signature_upload',
            'confirm_details',
            'terms_accepted',
            'approval_access_ack',
        ]
        for field_name in required_fields:
            if field_name in self.fields:
                self.fields[field_name].required = True

        for field_name in ['alternate_phone', 'profile_photo', 'store_logo', 'store_banner', 'gst_number', 'gst_document', 'business_registration_certificate', 'pickup_address_line2', 'pickup_landmark', 'brand_name', 'extra_documents']:
            if field_name in self.fields:
                self.fields[field_name].required = False

        self.order_fields([
            'name',
            'email',
            'phone',
            'alternate_phone',
            'password',
            'confirm_password',
            'profile_photo',
            'store_name',
            'store_display_name',
            'store_description',
            'business_type',
            'store_logo',
            'store_banner',
            'aadhaar_number',
            'pan_number',
            'owner_dob',
            'owner_address',
            'aadhaar_front',
            'aadhaar_back',
            'pan_card',
            'gst_available',
            'gst_number',
            'legal_business_name',
            'tax_pan_number',
            'gst_document',
            'business_registration_certificate',
            'bank_account_name',
            'bank_name',
            'bank_account_number',
            'confirm_bank_account_number',
            'bank_ifsc',
            'branch_name',
            'cancelled_cheque',
            'pickup_contact_name',
            'pickup_phone',
            'pickup_address_line1',
            'pickup_address_line2',
            'pickup_city',
            'pickup_state',
            'pickup_pincode',
            'pickup_landmark',
            'pickup_same_as_owner',
            'product_categories',
            'primary_category',
            'approx_products_count',
            'brand_name',
            'sells_handmade',
            'shop_photo',
            'owner_photo',
            'business_proof',
            'address_proof',
            'signature_upload',
            'extra_documents',
            'confirm_details',
            'terms_accepted',
            'approval_access_ack',
        ])
        self._style_fields()

        placeholders = {
            'name': 'Enter your full name',
            'email': 'seller@example.com',
            'phone': '10 digit phone number',
            'alternate_phone': 'Optional alternate number',
            'store_name': 'Your shop name',
            'store_display_name': 'Name shown to customers',
            'store_description': 'Tell customers what you sell',
            'aadhaar_number': '12 digit Aadhaar number',
            'pan_number': 'ABCDE1234F',
            'owner_address': 'Full owner address',
            'gst_number': '22AAAAA0000A1Z5',
            'legal_business_name': 'Registered business name',
            'tax_pan_number': 'ABCDE1234F',
            'bank_account_name': 'Account holder name',
            'bank_name': 'Bank name',
            'bank_account_number': 'Account number',
            'bank_ifsc': 'ABCD0123456',
            'branch_name': 'Branch name',
            'pickup_contact_name': 'Pickup contact person',
            'pickup_phone': '10 digit pickup phone',
            'pickup_address_line1': 'House, floor, building, street',
            'pickup_address_line2': 'Optional area / locality',
            'pickup_city': 'City',
            'pickup_state': 'State',
            'pickup_pincode': '6 digit pincode',
            'pickup_landmark': 'Optional nearby landmark',
            'approx_products_count': 'Example: 50',
            'brand_name': 'Optional brand name',
        }
        for field_name, placeholder in placeholders.items():
            if field_name in self.fields:
                self.fields[field_name].widget.attrs['placeholder'] = placeholder

        for field_name, field in self.fields.items():
            if isinstance(field.widget, forms.CheckboxInput):
                continue
            if field_name in {'gst_available', 'sells_handmade'}:
                field.widget.attrs['class'] = 'choice-radio-list'
        for field_name in [
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
        ]:
            if field_name in self.fields:
                self.fields[field_name].widget.attrs['accept'] = '.jpg,.jpeg,.png,.pdf'
        for field_name in ['profile_photo', 'store_logo', 'store_banner']:
            self.fields[field_name].widget.attrs['accept'] = '.jpg,.jpeg,.png'

    def _required_confirmation_fields(self):
        return ['confirm_details', 'terms_accepted', 'approval_access_ack']

    def clean_email(self):
        email = self.cleaned_data['email'].strip().lower()
        if SellerApplication.objects.filter(email__iexact=email).exclude(pk=self.instance.pk).exists():
            raise ValidationError('A seller application with this email already exists.')
        user_exists = User.objects.filter(email__iexact=email).exists() or User.objects.filter(username__iexact=email).exists()
        if user_exists:
            raise ValidationError('This email already has an account. Please use another email or contact admin.')
        return email

    def clean_phone(self):
        return _clean_indian_phone(self.cleaned_data.get('phone'), 'Phone number')

    def clean_alternate_phone(self):
        value = (self.cleaned_data.get('alternate_phone') or '').strip()
        return _clean_indian_phone(value, 'Alternate phone number') if value else ''

    def clean_pickup_phone(self):
        return _clean_indian_phone(self.cleaned_data.get('pickup_phone'), 'Pickup phone')

    def clean_aadhaar_number(self):
        value = re.sub(r'\s+', '', self.cleaned_data.get('aadhaar_number') or '')
        if not re.fullmatch(r'\d{12}', value):
            raise ValidationError('Aadhaar number must be 12 digits.')
        return value

    def clean_pan_number(self):
        value = _normalize_upper(self.cleaned_data.get('pan_number'))
        if not re.fullmatch(r'[A-Z]{5}[0-9]{4}[A-Z]', value):
            raise ValidationError('Enter a valid PAN number, for example ABCDE1234F.')
        return value

    def clean_tax_pan_number(self):
        value = _normalize_upper(self.cleaned_data.get('tax_pan_number'))
        if not re.fullmatch(r'[A-Z]{5}[0-9]{4}[A-Z]', value):
            raise ValidationError('Enter a valid tax PAN number, for example ABCDE1234F.')
        return value

    def clean_gst_number(self):
        value = _normalize_upper(self.cleaned_data.get('gst_number'))
        if value and not re.fullmatch(r'\d{2}[A-Z]{5}\d{4}[A-Z][A-Z\d]Z[A-Z\d]', value):
            raise ValidationError('Enter a valid GST number.')
        return value

    def clean_bank_ifsc(self):
        value = _normalize_upper(self.cleaned_data.get('bank_ifsc'))
        if not re.fullmatch(r'[A-Z]{4}0[A-Z0-9]{6}', value):
            raise ValidationError('Enter a valid IFSC code.')
        return value

    def clean_bank_account_number(self):
        value = re.sub(r'\s+', '', self.cleaned_data.get('bank_account_number') or '')
        if not re.fullmatch(r'\d{9,18}', value):
            raise ValidationError('Account number must be 9 to 18 digits.')
        return value

    def clean_confirm_bank_account_number(self):
        return re.sub(r'\s+', '', self.cleaned_data.get('confirm_bank_account_number') or '')

    def clean_pickup_pincode(self):
        value = (self.cleaned_data.get('pickup_pincode') or '').strip()
        if not re.fullmatch(r'\d{6}', value):
            raise ValidationError('Pincode must be 6 digits.')
        return value

    def clean_product_categories(self):
        values = self.cleaned_data.get('product_categories') or []
        return ','.join(values)

    def clean_approx_products_count(self):
        value = self.cleaned_data.get('approx_products_count')
        if value is None or value <= 0:
            raise ValidationError('Approx products count must be greater than zero.')
        return value

    def clean_password(self):
        password = self.cleaned_data.get('password')
        if password:
            validate_password(password)
        return password

    def _extra_document_indexes(self):
        if hasattr(self.data, 'getlist'):
            raw_indexes = self.data.getlist('extra_document_indexes')
        else:
            raw_value = self.data.get('extra_document_indexes', [])
            raw_indexes = raw_value if isinstance(raw_value, (list, tuple)) else [raw_value]

        indexes = []
        seen = set()
        for raw_index in raw_indexes:
            index = str(raw_index or '').strip()
            if not index or index in seen:
                continue
            indexes.append(index)
            seen.add(index)
        return indexes

    def _collect_extra_document_rows(self):
        rows = []
        for index in self._extra_document_indexes():
            name_key = f'extra_document_name_{index}'
            file_key = f'extra_document_file_{index}'
            document_name = (self.data.get(name_key) or '').strip()
            uploaded_file = self.files.get(file_key) if hasattr(self.files, 'get') else None
            if not document_name and not uploaded_file:
                continue
            rows.append(
                {
                    'index': index,
                    'document_name': document_name,
                    'file': uploaded_file,
                }
            )
        return rows

    def clean(self):
        cleaned_data = super().clean()
        password = cleaned_data.get('password')
        confirm_password = cleaned_data.get('confirm_password')
        if password and confirm_password and password != confirm_password:
            self.add_error('confirm_password', 'Passwords do not match.')

        account_number = cleaned_data.get('bank_account_number')
        confirm_account_number = cleaned_data.get('confirm_bank_account_number')
        if account_number and confirm_account_number and account_number != confirm_account_number:
            self.add_error('confirm_bank_account_number', 'Account number and confirm account number must match.')

        gst_available = cleaned_data.get('gst_available')
        if gst_available and not cleaned_data.get('gst_number'):
            self.add_error('gst_number', 'GST number is required when GST is available.')
        if gst_available and not cleaned_data.get('gst_document'):
            self.add_error('gst_document', 'GST certificate is required when GST is available.')

        selected_categories = set((cleaned_data.get('product_categories') or '').split(','))
        primary_category = cleaned_data.get('primary_category')
        if primary_category and primary_category not in selected_categories:
            self.add_error('primary_category', 'Primary category must be selected in product categories.')

        for checkbox_name in self._required_confirmation_fields():
            if not cleaned_data.get(checkbox_name):
                self.add_error(checkbox_name, 'This confirmation is required.')

        file_fields = [
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
        ]
        image_fields = {'profile_photo', 'store_logo', 'store_banner'}
        for field_name in sorted(image_fields) + file_fields:
            uploaded_file = cleaned_data.get(field_name)
            if not uploaded_file:
                continue
            try:
                _validate_seller_upload(uploaded_file, image_only=field_name in image_fields)
            except ValidationError as exc:
                self.add_error(field_name, exc)

        for uploaded_file in cleaned_data.get('extra_documents') or []:
            try:
                _validate_seller_upload(uploaded_file)
            except ValidationError as exc:
                self.add_error('extra_documents', exc)
        self.extra_document_rows = self._collect_extra_document_rows()
        for row in self.extra_document_rows:
            if row['file'] and not row['document_name']:
                self.add_error('extra_documents', 'Document name is required for each uploaded extra document.')
            if row['document_name'] and not row['file']:
                self.add_error('extra_documents', f'Upload a file for extra document "{row["document_name"]}".')
            if row['file']:
                try:
                    _validate_seller_upload(row['file'])
                except ValidationError as exc:
                    self.add_error('extra_documents', exc)
        return cleaned_data

    def save(self, commit=True):
        application = super().save(commit=False)
        application.email = self.cleaned_data['email']
        application.password_hash = make_password(self.cleaned_data['password'])
        application.email_verified = True
        application.status = SellerApplication.Status.PENDING
        application.store_display_name = application.store_display_name or application.store_name
        application.business_address = application.owner_address
        application.pickup_address = application.pickup_full_address
        application.admin_note = ''
        application.admin_remark = ''
        application.reviewed_by = None
        application.reviewed_at = None
        if commit:
            application.save()
            for uploaded_file in self.cleaned_data.get('extra_documents') or []:
                SellerApplicationExtraDocument.objects.create(
                    application=application,
                    document_name=getattr(uploaded_file, 'name', ''),
                    file=uploaded_file,
                    original_name=getattr(uploaded_file, 'name', ''),
                )
            for row in self.extra_document_rows:
                if not row['document_name'] or not row['file']:
                    continue
                SellerApplicationExtraDocument.objects.create(
                    application=application,
                    document_name=row['document_name'],
                    file=row['file'],
                    original_name=getattr(row['file'], 'name', ''),
                )
        return application


class AdminSellerApplicationForm(SellerApplicationForm):
    status = forms.ChoiceField(
        label='Seller status',
        choices=SellerApplication.Status.choices,
        initial=SellerApplication.Status.APPROVED,
    )

    class Meta(SellerApplicationForm.Meta):
        fields = SellerApplicationForm.Meta.fields + [
            'status',
        ]

    def _required_confirmation_fields(self):
        return []

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if not self.is_bound:
            self.fields['status'].initial = SellerApplication.Status.APPROVED
        self.fields['password'].help_text = 'Seller can login with this password after approval.'
        self.fields['confirm_password'].help_text = 'Repeat the seller login password.'
        self.fields['status'].help_text = 'Use Approved to create seller panel access immediately, or Pending Approval to create a request.'
        admin_required_fields = {
            'name',
            'email',
            'phone',
            'password',
            'confirm_password',
            'store_name',
            'business_type',
            'aadhaar_number',
            'pan_number',
            'aadhaar_front',
            'pan_card',
            'gst_available',
            'bank_account_name',
            'bank_name',
            'bank_account_number',
            'confirm_bank_account_number',
            'bank_ifsc',
            'pickup_contact_name',
            'pickup_phone',
            'pickup_address_line1',
            'pickup_city',
            'pickup_state',
            'pickup_pincode',
            'product_categories',
            'primary_category',
            'approx_products_count',
            'sells_handmade',
            'cancelled_cheque',
            'status',
        }
        for field_name, field in self.fields.items():
            field.required = field_name in admin_required_fields
        for field_name in ['confirm_details', 'terms_accepted', 'approval_access_ack']:
            if field_name in self.fields:
                self.fields[field_name].required = False
                self.fields[field_name].initial = True
        self.supports_extra_document_rows = True
        self.admin_fieldsets = _build_form_fieldsets(
            self,
            [
                (
                    'Personal Details',
                    'Seller owner login and contact information.',
                    ['name', 'email', 'phone', 'alternate_phone', 'password', 'confirm_password', 'profile_photo'],
                ),
                (
                    'Store Details',
                    'Customer-facing shop identity.',
                    ['store_name', 'store_display_name', 'store_description', 'business_type', 'store_logo', 'store_banner'],
                ),
                (
                    'Owner KYC Details',
                    'Owner identity information used for approval.',
                    ['aadhaar_number', 'pan_number', 'owner_dob', 'owner_address'],
                ),
                (
                    'GST & Tax Details',
                    'Tax registration and legal business details.',
                    ['gst_available', 'gst_number', 'legal_business_name', 'tax_pan_number'],
                ),
                (
                    'Bank Details',
                    'Settlement account for seller payouts.',
                    ['bank_account_name', 'bank_name', 'bank_account_number', 'confirm_bank_account_number', 'bank_ifsc', 'branch_name'],
                ),
                (
                    'Pickup Address',
                    'Address used for order pickup.',
                    ['pickup_contact_name', 'pickup_phone', 'pickup_address_line1', 'pickup_address_line2', 'pickup_city', 'pickup_state', 'pickup_pincode', 'pickup_landmark', 'pickup_same_as_owner'],
                ),
                (
                    'Product Category',
                    'Catalog profile for the seller account.',
                    ['product_categories', 'primary_category', 'approx_products_count', 'brand_name', 'sells_handmade'],
                ),
                (
                    'Documents Upload',
                    'Upload required KYC, bank, and business documents.',
                    ['aadhaar_front', 'aadhaar_back', 'pan_card', 'gst_document', 'business_registration_certificate', 'cancelled_cheque', 'shop_photo', 'owner_photo', 'business_proof', 'address_proof', 'signature_upload'],
                ),
                (
                    'Admin Access',
                    'Choose when seller panel login is enabled.',
                    ['status'],
                ),
            ],
        )

    def clean_phone(self):
        phone = super().clean_phone()
        if SellerApplication.objects.filter(phone=phone).exists():
            raise ValidationError('This phone number is already used by another seller.')
        return phone

    def clean_store_name(self):
        store_name = (self.cleaned_data.get('store_name') or '').strip()
        if SellerApplication.objects.filter(store_name__iexact=store_name).exists():
            raise ValidationError('This shop name is already used by another seller.')
        return store_name

    def clean_tax_pan_number(self):
        value = _normalize_upper(self.cleaned_data.get('tax_pan_number'))
        if value and not re.fullmatch(r'[A-Z]{5}[0-9]{4}[A-Z]', value):
            raise ValidationError('Enter a valid tax PAN number, for example ABCDE1234F.')
        return value

    def save(self, commit=True):
        application = super(SellerApplicationForm, self).save(commit=False)
        application.email = self.cleaned_data['email']
        application.password_hash = make_password(self.cleaned_data['password'])
        application.email_verified = True
        application.status = self.cleaned_data.get('status') or SellerApplication.Status.APPROVED
        application.confirm_details = True
        application.terms_accepted = True
        application.approval_access_ack = True
        application.store_display_name = application.store_display_name or application.store_name
        application.business_address = application.owner_address
        application.pickup_address = application.pickup_full_address
        application.admin_note = ''
        application.admin_remark = ''
        application.reviewed_by = None
        application.reviewed_at = None
        if commit:
            application.save()
            for uploaded_file in self.cleaned_data.get('extra_documents') or []:
                SellerApplicationExtraDocument.objects.create(
                    application=application,
                    document_name=getattr(uploaded_file, 'name', ''),
                    file=uploaded_file,
                    original_name=getattr(uploaded_file, 'name', ''),
                )
            for row in self.extra_document_rows:
                if not row['document_name'] or not row['file']:
                    continue
                SellerApplicationExtraDocument.objects.create(
                    application=application,
                    document_name=row['document_name'],
                    file=row['file'],
                    original_name=getattr(row['file'], 'name', ''),
                )
        return application


class SellerProfileForm(StyledFormMixin, forms.ModelForm):
    class Meta:
        model = SellerApplication
        fields = [
            'name',
            'email',
            'phone',
            'alternate_phone',
        ]
        labels = {
            'name': 'Seller name',
            'email': 'Email',
            'phone': 'Phone',
            'alternate_phone': 'Alternate phone',
        }

    def __init__(self, *args, user=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.user = user
        self.fields['alternate_phone'].required = False
        self._style_fields()

    def clean_email(self):
        email = (self.cleaned_data.get('email') or '').strip().lower()
        if SellerApplication.objects.filter(email__iexact=email).exclude(pk=self.instance.pk).exists():
            raise ValidationError('This email is already used by another seller.')
        user_query = User.objects.filter(Q(email__iexact=email) | Q(username__iexact=email))
        if self.user:
            user_query = user_query.exclude(pk=self.user.pk)
        if user_query.exists():
            raise ValidationError('This email is already used by another account.')
        return email

    def clean_phone(self):
        return _clean_indian_phone(self.cleaned_data.get('phone'), 'Phone number')

    def clean_alternate_phone(self):
        value = (self.cleaned_data.get('alternate_phone') or '').strip()
        return _clean_indian_phone(value, 'Alternate phone number') if value else ''

    def save(self, commit=True):
        application = super().save(commit=False)
        if self.user:
            self.user.first_name = application.name
            self.user.email = application.email
            self.user.username = application.email
            if commit:
                self.user.save(update_fields=['first_name', 'email', 'username'])
        if commit:
            application.save()
        return application


class SellerPasswordChangeForm(PasswordChangeForm, StyledFormMixin):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field in self.fields.values():
            field.help_text = ''
        self._style_fields()


class SellerStoreProfileForm(StyledFormMixin, forms.ModelForm):
    class Meta:
        model = SellerApplication
        fields = [
            'store_name',
            'store_display_name',
            'store_description',
            'business_type',
            'store_logo',
            'store_banner',
            'primary_category',
            'product_categories',
            'brand_name',
            'gst_available',
            'gst_number',
            'legal_business_name',
            'tax_pan_number',
            'pan_number',
            'business_address',
            'pickup_address',
        ]
        labels = {
            'store_name': 'Store / business name',
            'store_display_name': 'Store display name',
            'store_description': 'Store description',
            'business_type': 'Business type',
            'store_logo': 'Store logo',
            'store_banner': 'Store banner',
            'primary_category': 'Store category',
            'product_categories': 'Product categories',
            'brand_name': 'Brand name',
            'gst_available': 'GST available',
            'gst_number': 'GST number',
            'legal_business_name': 'Legal business name',
            'tax_pan_number': 'Tax PAN number',
            'pan_number': 'PAN number',
            'business_address': 'Business address',
            'pickup_address': 'Pickup address',
        }
        widgets = {
            'store_description': forms.Textarea(attrs={'rows': 4}),
            'product_categories': forms.Textarea(attrs={'rows': 3}),
            'business_address': forms.Textarea(attrs={'rows': 4}),
            'pickup_address': forms.Textarea(attrs={'rows': 4}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field_name in [
            'store_display_name',
            'store_description',
            'store_logo',
            'store_banner',
            'primary_category',
            'product_categories',
            'brand_name',
            'gst_number',
            'legal_business_name',
            'tax_pan_number',
            'pan_number',
            'business_address',
            'pickup_address',
        ]:
            self.fields[field_name].required = False
        self.fields['store_logo'].widget.attrs['accept'] = '.jpg,.jpeg,.png,.webp,image/*'
        self.fields['store_banner'].widget.attrs['accept'] = '.jpg,.jpeg,.png,.webp,image/*'
        self._style_fields()


class SellerBankDetailsForm(StyledFormMixin, forms.ModelForm):
    class Meta:
        model = SellerApplication
        fields = [
            'bank_name',
            'bank_account_name',
            'bank_account_number',
            'bank_ifsc',
            'branch_name',
            'cancelled_cheque',
        ]
        labels = {
            'bank_name': 'Bank name',
            'bank_account_name': 'Account holder name',
            'bank_account_number': 'Account number',
            'bank_ifsc': 'IFSC code',
            'branch_name': 'Branch',
            'cancelled_cheque': 'Cancelled cheque / passbook',
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field in self.fields.values():
            field.required = False
        self.fields['cancelled_cheque'].widget.attrs['accept'] = '.pdf,.jpg,.jpeg,.png'
        self._style_fields()

    def clean_bank_account_number(self):
        value = (self.cleaned_data.get('bank_account_number') or '').strip()
        if value and not re.fullmatch(r'[0-9]{6,34}', value):
            raise ValidationError('Enter a valid bank account number.')
        return value

    def clean_bank_ifsc(self):
        value = _normalize_upper(self.cleaned_data.get('bank_ifsc'))
        if value and not re.fullmatch(r'[A-Z]{4}0[A-Z0-9]{6}', value):
            raise ValidationError('Enter a valid IFSC code, for example ABCD0123456.')
        return value


class SellerDocumentsForm(StyledFormMixin, forms.ModelForm):
    class Meta:
        model = SellerApplication
        fields = [
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
        ]
        labels = {
            'aadhaar_front': 'Aadhaar front',
            'aadhaar_back': 'Aadhaar back',
            'pan_card': 'PAN card',
            'gst_document': 'GST certificate',
            'business_registration_certificate': 'Business registration certificate',
            'cancelled_cheque': 'Cancelled cheque / passbook',
            'shop_photo': 'Shop photo',
            'owner_photo': 'Owner photo',
            'business_proof': 'Business proof',
            'address_proof': 'Address proof',
            'signature_upload': 'Signature',
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field in self.fields.values():
            field.required = False
        for field_name in [
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
        ]:
            self.fields[field_name].widget.attrs['accept'] = '.pdf,.jpg,.jpeg,.png'
        self._style_fields()


class ProductQuantityOptionFormMixin:
    quantity_option_slots = MAX_ADMIN_QUANTITY_OPTIONS

    def _quantity_prefix(self, index):
        return f'quantity_option_{index}'

    def _quantity_field_names(self):
        field_names = []
        for index in range(1, self.quantity_option_slots + 1):
            prefix = self._quantity_prefix(index)
            field_names.extend([
                f'{prefix}_label',
                f'{prefix}_price',
                f'{prefix}_original_price',
                f'{prefix}_stock',
                f'{prefix}_sku',
                f'{prefix}_image',
            ])
            existing = self._quantity_existing_by_slot.get(index)
            if existing:
                field_names.append(f'{prefix}_remove')
        return field_names

    def _configure_quantity_option_fields(self):
        self.quantity_existing = []
        self._quantity_existing_by_slot = {}
        if self.instance and self.instance.pk:
            self.quantity_existing = list(self.instance.quantity_options.filter(is_active=True))

        for index in range(1, self.quantity_option_slots + 1):
            existing = self.quantity_existing[index - 1] if index <= len(self.quantity_existing) else None
            if existing:
                self._quantity_existing_by_slot[index] = existing

            prefix = self._quantity_prefix(index)
            self.fields[f'{prefix}_label'] = forms.CharField(
                required=False,
                max_length=60,
                label=f'Quantity {index} label',
                initial=existing.label if existing else '',
                help_text='Example: 100Gm, 200Gm, 500Gm.',
            )
            self.fields[f'{prefix}_price'] = forms.DecimalField(
                required=False,
                min_value=0,
                max_digits=10,
                decimal_places=2,
                label=f'Quantity {index} price',
                initial=existing.price if existing else None,
                help_text='Selling price for this quantity.',
            )
            self.fields[f'{prefix}_original_price'] = forms.DecimalField(
                required=False,
                min_value=0,
                max_digits=10,
                decimal_places=2,
                label=f'Quantity {index} MRP',
                initial=existing.original_price if existing else None,
                help_text='Optional compare price to show discount.',
            )
            self.fields[f'{prefix}_stock'] = forms.IntegerField(
                required=False,
                min_value=0,
                label=f'Quantity {index} stock',
                initial=existing.stock if existing else None,
                help_text='Available stock for this quantity option.',
            )
            self.fields[f'{prefix}_sku'] = forms.CharField(
                required=False,
                max_length=80,
                label=f'Quantity {index} SKU',
                initial=existing.sku_code if existing else '',
                help_text='Optional SKU for this quantity.',
            )
            self.fields[f'{prefix}_image'] = forms.ImageField(
                required=False,
                label=f'Quantity {index} photo',
                help_text='Optional. Detail photo changes when customer selects this quantity.',
            )
            self.fields[f'{prefix}_image'].widget.attrs['accept'] = PRODUCT_IMAGE_ACCEPT

            if existing:
                self.fields[f'{prefix}_remove'] = forms.BooleanField(
                    required=False,
                    label=f'Remove quantity {existing.label}',
                    help_text='Tick this and save to delete this quantity option.',
                )
        self.product_quantity_field_names = self._quantity_field_names()

    @property
    def quantity_rows(self):
        rows = []
        for index in range(1, self.quantity_option_slots + 1):
            prefix = self._quantity_prefix(index)
            if f'{prefix}_label' not in self.fields:
                continue
            rows.append(
                {
                    'index': index,
                    'label': self[f'{prefix}_label'],
                    'price': self[f'{prefix}_price'],
                    'original_price': self[f'{prefix}_original_price'],
                    'stock': self[f'{prefix}_stock'],
                    'sku': self[f'{prefix}_sku'],
                    'image': self[f'{prefix}_image'],
                    'remove': self[f'{prefix}_remove'] if f'{prefix}_remove' in self.fields else None,
                    'existing': self._quantity_existing_by_slot.get(index),
                    'image_url': self._quantity_existing_by_slot.get(index).variant_image_source if self._quantity_existing_by_slot.get(index) else '',
                }
            )
        return rows

    def _clean_quantity_options(self, cleaned_data):
        seen_labels = set()
        for index in range(1, self.quantity_option_slots + 1):
            prefix = self._quantity_prefix(index)
            existing = self._quantity_existing_by_slot.get(index)
            remove = cleaned_data.get(f'{prefix}_remove')
            if remove:
                continue

            label = (cleaned_data.get(f'{prefix}_label') or '').strip()
            price = cleaned_data.get(f'{prefix}_price')
            original_price = cleaned_data.get(f'{prefix}_original_price')
            stock = cleaned_data.get(f'{prefix}_stock')
            sku = (cleaned_data.get(f'{prefix}_sku') or '').strip()
            image = cleaned_data.get(f'{prefix}_image')
            has_any_value = bool(label or price is not None or original_price is not None or stock is not None or sku or image)

            if not has_any_value:
                continue
            if not label:
                self.add_error(f'{prefix}_label', 'Quantity label required hai.')
                continue
            if price is None:
                self.add_error(f'{prefix}_price', 'Quantity price required hai.')
            if stock is None:
                self.add_error(f'{prefix}_stock', 'Stock quantity required hai.')
            if image:
                try:
                    _validate_product_image_upload(image)
                except ValidationError as error:
                    self.add_error(f'{prefix}_image', error)

            normalized_label = label.lower()
            if normalized_label in seen_labels:
                self.add_error(f'{prefix}_label', 'Same quantity label repeat nahi ho sakta.')
            seen_labels.add(normalized_label)

            if original_price is not None and price is not None and original_price < price:
                self.add_error(f'{prefix}_original_price', 'MRP selling price se kam nahi hona chahiye.')

        return cleaned_data

    def save_quantity_options(self, product):
        saved_any = False
        for index in range(1, self.quantity_option_slots + 1):
            prefix = self._quantity_prefix(index)
            existing = self._quantity_existing_by_slot.get(index)

            if existing and self.cleaned_data.get(f'{prefix}_remove'):
                existing.delete()
                continue

            label = (self.cleaned_data.get(f'{prefix}_label') or '').strip()
            price = self.cleaned_data.get(f'{prefix}_price')
            if not label or price is None:
                if existing and not label:
                    existing.delete()
                continue

            option = existing or ProductQuantityOption(product=product)
            option.label = label
            option.price = price
            option.original_price = self.cleaned_data.get(f'{prefix}_original_price')
            option.stock = self.cleaned_data.get(f'{prefix}_stock') or 0
            option.sku_code = (self.cleaned_data.get(f'{prefix}_sku') or '').strip()
            option.display_order = index
            option.is_active = True
            uploaded_image = self.cleaned_data.get(f'{prefix}_image')
            if uploaded_image:
                if option.pk and option.image_file:
                    option.image_file.delete(save=False)
                option.image_file = uploaded_image
            option.save()
            saved_any = True

        if product.quantity_options.filter(is_active=True).exists() or saved_any:
            total_stock = sum(option.stock for option in product.quantity_options.filter(is_active=True))
            product.stock = total_stock
            if product.initial_stock < total_stock:
                product.initial_stock = total_stock
            product.save(update_fields=['stock', 'initial_stock', 'updated_at'])


class SpiceItemForm(ProductSubCategoryFormMixin, ProductQuantityOptionFormMixin, StyledFormMixin, forms.ModelForm):
    product_id = forms.CharField(label='Product ID', required=False, disabled=True)
    sub_category = forms.ChoiceField(label='Sub Category', required=False)
    gallery_image_1 = forms.ImageField(required=False, label='Gallery Photo 1')
    gallery_image_2 = forms.ImageField(required=False, label='Gallery Photo 2')
    gallery_image_3 = forms.ImageField(required=False, label='Gallery Photo 3')
    gallery_image_4 = forms.ImageField(required=False, label='Gallery Photo 4')
    gallery_image_5 = forms.ImageField(required=False, label='Gallery Photo 5')
    gallery_image_6 = forms.ImageField(required=False, label='Gallery Photo 6')

    class Meta:
        model = SpiceItem
        fields = [
            'name',
            'category',
            'sub_category',
            'short_description',
            'description',
            'spice_level',
            'brand_name',
            'pack_size',
            'sku_code',
            'specifications',
            'shipping_weight',
            'return_available',
            'warranty_details',
            'price',
            'original_price',
            'initial_stock',
            'stock',
            'image_file',
            'owner_type',
            'seller',
            'approval_status',
            'is_featured',
            'is_active',
            'display_order',
        ]
        labels = {
            'sub_category': 'Sub-category',
            'brand_name': 'Company',
            'sku_code': 'SKU code',
            'shipping_weight': 'Shipping weight',
            'return_available': 'Return available',
            'warranty_details': 'Warranty details',
            'initial_stock': 'Initial stock',
            'stock': 'Current stock',
            'owner_type': 'Product owner',
            'approval_status': 'Approval status',
        }
        widgets = {
            'description': forms.Textarea(attrs={'rows': 4}),
            'specifications': forms.Textarea(attrs={'rows': 4}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for index in range(1, MAX_PRODUCT_GALLERY_IMAGES + 1):
            field_name = f'gallery_image_{index}'
            if field_name not in self.fields:
                self.fields[field_name] = forms.ImageField(required=False, label=f'Gallery Photo {index}')

        self.gallery_existing = []
        if self.instance and self.instance.pk:
            self.gallery_existing = list(self.instance.gallery_images.filter(is_active=True))
            for photo in self.gallery_existing:
                self.fields[f'remove_gallery_{photo.pk}'] = forms.BooleanField(
                    required=False,
                    label=f'Remove gallery photo #{photo.display_order or photo.pk}',
                    help_text='Tick this and save to remove this product detail photo.',
                )

        self._configure_quantity_option_fields()
        model_fields = ['product_id'] + list(self.Meta.fields)
        quantity_fields = self._quantity_field_names()
        gallery_fields = [f'gallery_image_{index}' for index in range(1, MAX_PRODUCT_GALLERY_IMAGES + 1)]
        remove_fields = [f'remove_gallery_{photo.pk}' for photo in self.gallery_existing]
        self.order_fields(model_fields + quantity_fields + gallery_fields + remove_fields)

        self._style_fields()
        self._configure_product_identity_fields()
        self._configure_product_category_fields()
        self.fields['image_file'].label = 'Upload Product Photo'
        self.fields['image_file'].widget.attrs['accept'] = PRODUCT_IMAGE_ACCEPT
        self.fields['image_file'].help_text = 'Main product photo shown on cards and as first detail image.'
        self.fields['initial_stock'].help_text = 'Original stock quantity for stock history comparison.'
        self.fields['stock'].help_text = 'Current available stock shown on storefront.'
        self.fields['seller'].help_text = 'Select only when product owner is Seller.'
        self.fields['approval_status'].help_text = 'Seller products can stay pending until admin approval.'

        for index in range(1, MAX_PRODUCT_GALLERY_IMAGES + 1):
            field = self.fields[f'gallery_image_{index}']
            field.help_text = 'Optional extra product photo for detail page gallery.'
            field.widget.attrs['accept'] = PRODUCT_IMAGE_ACCEPT

    def clean(self):
        cleaned_data = super().clean()
        image_file = cleaned_data.get('image_file')
        if image_file:
            try:
                _validate_product_image_upload(image_file)
            except ValidationError as error:
                self.add_error('image_file', error)

        remove_count = sum(
            1
            for photo in self.gallery_existing
            if cleaned_data.get(f'remove_gallery_{photo.pk}')
        )
        upload_count = sum(
            1
            for index in range(1, MAX_PRODUCT_GALLERY_IMAGES + 1)
            if cleaned_data.get(f'gallery_image_{index}')
        )
        for index in range(1, MAX_PRODUCT_GALLERY_IMAGES + 1):
            uploaded_image = cleaned_data.get(f'gallery_image_{index}')
            if uploaded_image:
                try:
                    _validate_product_image_upload(uploaded_image)
                except ValidationError as error:
                    self.add_error(f'gallery_image_{index}', error)

        final_count = len(self.gallery_existing) - remove_count + upload_count
        if final_count > MAX_PRODUCT_GALLERY_IMAGES:
            raise ValidationError(
                f'Product detail gallery can keep maximum {MAX_PRODUCT_GALLERY_IMAGES} photos. '
                'Remove old gallery photos or upload fewer new photos.'
            )
        return self._clean_quantity_options(cleaned_data)

    def save_gallery_images(self, product):
        for photo in self.gallery_existing:
            if self.cleaned_data.get(f'remove_gallery_{photo.pk}'):
                photo.delete()

        gallery_meta = product.gallery_images.aggregate(max_order=Max('display_order'))
        next_order = (gallery_meta.get('max_order') or 0) + 1
        current_count = product.gallery_images.filter(is_active=True).count()

        for index in range(1, MAX_PRODUCT_GALLERY_IMAGES + 1):
            uploaded_image = self.cleaned_data.get(f'gallery_image_{index}')
            if not uploaded_image or current_count >= MAX_PRODUCT_GALLERY_IMAGES:
                continue

            SpiceItemPhoto.objects.create(
                product=product,
                image_file=uploaded_image,
                alt_text=f'{product.name} photo {next_order}',
                display_order=next_order,
            )
            next_order += 1
            current_count += 1


class SellerProductForm(ProductSubCategoryFormMixin, ProductQuantityOptionFormMixin, StyledFormMixin, forms.ModelForm):
    quantity_option_slots = MAX_SELLER_QUANTITY_OPTIONS
    product_id = forms.CharField(label='Product ID', required=False, disabled=True)
    sub_category = forms.ChoiceField(label='Sub Category', required=False)

    class Meta:
        model = SpiceItem
        fields = [
            'name',
            'category',
            'sub_category',
            'brand_name',
            'image_file',
            'price',
            'original_price',
            'stock',
            'sku_code',
            'short_description',
            'description',
            'specifications',
            'shipping_weight',
            'return_available',
            'warranty_details',
            'pack_size',
            'spice_level',
        ]
        labels = {
            'name': 'Product name',
            'category': 'Category',
            'sub_category': 'Sub-category',
            'brand_name': 'Company',
            'image_file': 'Main product image',
            'price': 'Base / selling price',
            'original_price': 'MRP / compare price',
            'stock': 'Stock quantity',
            'sku_code': 'SKU code',
            'short_description': 'Short description',
            'shipping_weight': 'Shipping weight',
            'return_available': 'Return available',
            'warranty_details': 'Warranty details',
            'pack_size': 'Default pack size',
        }
        widgets = {
            'description': forms.Textarea(attrs={'rows': 4}),
            'specifications': forms.Textarea(attrs={'rows': 4}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.gallery_existing = []
        self.detail_existing = []
        if self.instance and self.instance.pk:
            self.gallery_existing = list(self.instance.gallery_images.filter(is_active=True))
            self.detail_existing = list(self.instance.detail_images.filter(is_active=True))

        self._configure_gallery_fields()
        self._configure_detail_image_fields()
        self._configure_quantity_option_fields()
        self._style_fields()

        media_fields = self._gallery_field_names() + self._detail_field_names()
        self.order_fields(['product_id'] + list(self.Meta.fields) + self._quantity_field_names() + media_fields)
        self._configure_product_identity_fields()
        self._configure_product_category_fields()
        self.fields['image_file'].required = not bool(self.instance and self.instance.pk and self.instance.image_source)
        self.fields['image_file'].widget.attrs['accept'] = PRODUCT_IMAGE_ACCEPT
        self.fields['image_file'].help_text = 'Required. Main product photo shown on cards and as first detail image.'
        self.fields['original_price'].help_text = 'Use higher MRP/compare price to show discount.'
        self.fields['stock'].widget.attrs.update({'min': 0})
        self.fields['return_available'].initial = True

    def _configure_gallery_fields(self):
        for photo in self.gallery_existing:
            self.fields[f'gallery_replace_{photo.pk}'] = forms.ImageField(
                required=False,
                label='Replace photo',
                help_text='Optional. Upload a new image to replace this gallery photo.',
            )
            self.fields[f'gallery_replace_{photo.pk}'].widget.attrs['accept'] = PRODUCT_IMAGE_ACCEPT
            self.fields[f'gallery_remove_{photo.pk}'] = forms.BooleanField(
                required=False,
                label='Remove photo',
            )

        for index in range(1, MAX_PRODUCT_GALLERY_IMAGES + 1):
            self.fields[f'gallery_image_{index}'] = forms.ImageField(
                required=False,
                label=f'Gallery photo {index}',
                help_text='Optional gallery photo for customer product page.',
            )
            self.fields[f'gallery_image_{index}'].widget.attrs['accept'] = PRODUCT_IMAGE_ACCEPT

    def _configure_detail_image_fields(self):
        for photo in self.detail_existing:
            self.fields[f'detail_existing_{photo.pk}_title'] = forms.CharField(
                required=False,
                max_length=120,
                label='Title',
                initial=photo.title,
            )
            self.fields[f'detail_existing_{photo.pk}_caption'] = forms.CharField(
                required=False,
                max_length=220,
                label='Caption',
                initial=photo.caption,
            )
            self.fields[f'detail_replace_{photo.pk}'] = forms.ImageField(
                required=False,
                label='Replace photo',
                help_text='Optional. Upload a new detail image.',
            )
            self.fields[f'detail_replace_{photo.pk}'].widget.attrs['accept'] = PRODUCT_IMAGE_ACCEPT
            self.fields[f'detail_remove_{photo.pk}'] = forms.BooleanField(
                required=False,
                label='Remove detail photo',
            )

        for index in range(1, MAX_PRODUCT_DETAIL_IMAGES + 1):
            self.fields[f'detail_image_{index}'] = forms.ImageField(
                required=False,
                label=f'Detail photo {index}',
                help_text='Optional product detail / more details photo.',
            )
            self.fields[f'detail_image_{index}'].widget.attrs['accept'] = PRODUCT_IMAGE_ACCEPT
            self.fields[f'detail_title_{index}'] = forms.CharField(
                required=False,
                max_length=120,
                label='Title',
            )
            self.fields[f'detail_caption_{index}'] = forms.CharField(
                required=False,
                max_length=220,
                label='Caption',
            )

    def _gallery_field_names(self):
        names = []
        for photo in self.gallery_existing:
            names.extend([f'gallery_replace_{photo.pk}', f'gallery_remove_{photo.pk}'])
        names.extend(f'gallery_image_{index}' for index in range(1, MAX_PRODUCT_GALLERY_IMAGES + 1))
        return names

    def _detail_field_names(self):
        names = []
        for photo in self.detail_existing:
            names.extend([
                f'detail_existing_{photo.pk}_title',
                f'detail_existing_{photo.pk}_caption',
                f'detail_replace_{photo.pk}',
                f'detail_remove_{photo.pk}',
            ])
        for index in range(1, MAX_PRODUCT_DETAIL_IMAGES + 1):
            names.extend([f'detail_image_{index}', f'detail_title_{index}', f'detail_caption_{index}'])
        return names

    @property
    def gallery_upload_rows(self):
        return [
            {
                'index': index,
                'image': self[f'gallery_image_{index}'],
            }
            for index in range(1, MAX_PRODUCT_GALLERY_IMAGES + 1)
        ]

    @property
    def gallery_existing_rows(self):
        return [
            {
                'photo': photo,
                'replace': self[f'gallery_replace_{photo.pk}'],
                'remove': self[f'gallery_remove_{photo.pk}'],
            }
            for photo in self.gallery_existing
        ]

    @property
    def detail_upload_rows(self):
        return [
            {
                'index': index,
                'image': self[f'detail_image_{index}'],
                'title': self[f'detail_title_{index}'],
                'caption': self[f'detail_caption_{index}'],
            }
            for index in range(1, MAX_PRODUCT_DETAIL_IMAGES + 1)
        ]

    @property
    def detail_existing_rows(self):
        return [
            {
                'photo': photo,
                'title': self[f'detail_existing_{photo.pk}_title'],
                'caption': self[f'detail_existing_{photo.pk}_caption'],
                'replace': self[f'detail_replace_{photo.pk}'],
                'remove': self[f'detail_remove_{photo.pk}'],
            }
            for photo in self.detail_existing
        ]

    def clean(self):
        cleaned_data = super().clean()
        image_file = cleaned_data.get('image_file')
        image_was_uploaded = bool(self.files.get(self.add_prefix('image_file')))
        if not image_file and not image_was_uploaded and not (self.instance and self.instance.pk and self.instance.image_source):
            self.add_error('image_file', 'Main product image required hai.')
        if image_file:
            try:
                _validate_product_image_upload(image_file)
            except ValidationError as error:
                self.add_error('image_file', error)

        price = cleaned_data.get('price')
        original_price = cleaned_data.get('original_price')
        if original_price is not None and price is not None and original_price < price:
            self.add_error('original_price', 'MRP selling price se kam nahi hona chahiye.')

        self._clean_gallery_images(cleaned_data)
        self._clean_detail_images(cleaned_data)
        return self._clean_quantity_options(cleaned_data)

    def _clean_gallery_images(self, cleaned_data):
        remove_count = sum(
            1
            for photo in self.gallery_existing
            if cleaned_data.get(f'gallery_remove_{photo.pk}')
        )
        upload_count = 0

        for photo in self.gallery_existing:
            replacement = cleaned_data.get(f'gallery_replace_{photo.pk}')
            if replacement:
                try:
                    _validate_product_image_upload(replacement)
                except ValidationError as error:
                    self.add_error(f'gallery_replace_{photo.pk}', error)

        for index in range(1, MAX_PRODUCT_GALLERY_IMAGES + 1):
            uploaded_image = cleaned_data.get(f'gallery_image_{index}')
            if not uploaded_image:
                continue
            upload_count += 1
            try:
                _validate_product_image_upload(uploaded_image)
            except ValidationError as error:
                self.add_error(f'gallery_image_{index}', error)

        final_count = len(self.gallery_existing) - remove_count + upload_count
        if final_count > MAX_PRODUCT_GALLERY_IMAGES:
            raise ValidationError(f'Gallery photos maximum {MAX_PRODUCT_GALLERY_IMAGES} allowed hain.')

    def _clean_detail_images(self, cleaned_data):
        remove_count = sum(
            1
            for photo in self.detail_existing
            if cleaned_data.get(f'detail_remove_{photo.pk}')
        )
        upload_count = 0

        for photo in self.detail_existing:
            replacement = cleaned_data.get(f'detail_replace_{photo.pk}')
            if replacement:
                try:
                    _validate_product_image_upload(replacement)
                except ValidationError as error:
                    self.add_error(f'detail_replace_{photo.pk}', error)

        for index in range(1, MAX_PRODUCT_DETAIL_IMAGES + 1):
            uploaded_image = cleaned_data.get(f'detail_image_{index}')
            uploaded_image_present = bool(self.files.get(self.add_prefix(f'detail_image_{index}')))
            title = (cleaned_data.get(f'detail_title_{index}') or '').strip()
            caption = (cleaned_data.get(f'detail_caption_{index}') or '').strip()
            if not uploaded_image:
                if (title or caption) and not uploaded_image_present:
                    self.add_error(f'detail_image_{index}', 'Detail photo upload karein ya empty row hata dein.')
                continue
            upload_count += 1
            try:
                _validate_product_image_upload(uploaded_image)
            except ValidationError as error:
                self.add_error(f'detail_image_{index}', error)

        final_count = len(self.detail_existing) - remove_count + upload_count
        if final_count > MAX_PRODUCT_DETAIL_IMAGES:
            raise ValidationError(f'Product detail photos maximum {MAX_PRODUCT_DETAIL_IMAGES} allowed hain.')

    def save_gallery_images(self, product):
        for photo in self.gallery_existing:
            if self.cleaned_data.get(f'gallery_remove_{photo.pk}'):
                if photo.image_file:
                    photo.image_file.delete(save=False)
                photo.delete()
                continue

            replacement = self.cleaned_data.get(f'gallery_replace_{photo.pk}')
            if replacement:
                if photo.image_file:
                    photo.image_file.delete(save=False)
                photo.image_file = replacement
                photo.alt_text = photo.alt_text or f'{product.name} photo {photo.display_order or photo.pk}'
                photo.save(update_fields=['image_file', 'alt_text', 'updated_at'])

        gallery_meta = product.gallery_images.aggregate(max_order=Max('display_order'))
        next_order = (gallery_meta.get('max_order') or 0) + 1
        current_count = product.gallery_images.filter(is_active=True).count()

        for index in range(1, MAX_PRODUCT_GALLERY_IMAGES + 1):
            uploaded_image = self.cleaned_data.get(f'gallery_image_{index}')
            if not uploaded_image or current_count >= MAX_PRODUCT_GALLERY_IMAGES:
                continue

            SpiceItemPhoto.objects.create(
                product=product,
                image_file=uploaded_image,
                alt_text=f'{product.name} gallery photo {next_order}',
                display_order=next_order,
            )
            next_order += 1
            current_count += 1

    def save_detail_images(self, product):
        for photo in self.detail_existing:
            if self.cleaned_data.get(f'detail_remove_{photo.pk}'):
                if photo.image_file:
                    photo.image_file.delete(save=False)
                photo.delete()
                continue

            changed_fields = []
            title = (self.cleaned_data.get(f'detail_existing_{photo.pk}_title') or '').strip()
            caption = (self.cleaned_data.get(f'detail_existing_{photo.pk}_caption') or '').strip()
            if photo.title != title:
                photo.title = title
                changed_fields.append('title')
            if photo.caption != caption:
                photo.caption = caption
                changed_fields.append('caption')

            replacement = self.cleaned_data.get(f'detail_replace_{photo.pk}')
            if replacement:
                if photo.image_file:
                    photo.image_file.delete(save=False)
                photo.image_file = replacement
                changed_fields.append('image_file')

            if changed_fields:
                changed_fields.append('updated_at')
                photo.save(update_fields=changed_fields)

        detail_meta = product.detail_images.aggregate(max_order=Max('display_order'))
        next_order = (detail_meta.get('max_order') or 0) + 1
        current_count = product.detail_images.filter(is_active=True).count()

        for index in range(1, MAX_PRODUCT_DETAIL_IMAGES + 1):
            uploaded_image = self.cleaned_data.get(f'detail_image_{index}')
            if not uploaded_image or current_count >= MAX_PRODUCT_DETAIL_IMAGES:
                continue

            ProductDetailImage.objects.create(
                product=product,
                image_file=uploaded_image,
                title=(self.cleaned_data.get(f'detail_title_{index}') or '').strip(),
                caption=(self.cleaned_data.get(f'detail_caption_{index}') or '').strip(),
                display_order=next_order,
            )
            next_order += 1
            current_count += 1


class AdminSellerApplicationEditForm(StyledFormMixin, forms.ModelForm):
    password = forms.CharField(
        required=False,
        label='New seller password',
        widget=forms.TextInput(attrs={'autocomplete': 'new-password'}),
        help_text='Optional. Fill this or tick generate password below.',
    )
    generate_password = forms.BooleanField(
        required=False,
        label='Generate new password automatically',
    )

    class Meta:
        model = SellerApplication
        fields = [
            'name',
            'email',
            'phone',
            'password',
            'generate_password',
            'store_name',
            'business_type',
            'aadhaar_number',
            'pan_number',
            'gst_number',
            'bank_account_name',
            'bank_account_number',
            'bank_ifsc',
            'business_address',
            'pickup_address',
            'aadhaar_document',
            'pan_document',
            'gst_document',
            'trade_license_document',
            'company_document',
            'bank_document',
            'address_proof',
            'status',
            'admin_note',
        ]
        widgets = {
            'business_address': forms.Textarea(attrs={'rows': 4}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.generated_password = ''
        for field_name in ['aadhaar_document', 'pan_document', 'gst_document', 'trade_license_document', 'company_document', 'bank_document', 'address_proof']:
            self.fields[field_name].widget.attrs['accept'] = '.pdf,.jpg,.jpeg,.png'
        self._style_fields()

    def clean_email(self):
        email = self.cleaned_data['email'].strip().lower()
        exists = SellerApplication.objects.filter(email__iexact=email).exclude(pk=self.instance.pk).exists()
        if exists:
            raise ValidationError('A seller application with this email already exists.')
        return email

    def clean_password(self):
        password = self.cleaned_data.get('password', '')
        if password:
            validate_password(password)
        return password

    def save(self, commit=True):
        application = super().save(commit=False)
        password = self.cleaned_data.get('password', '')
        if self.cleaned_data.get('generate_password'):
            password = _generate_admin_password()
            self.generated_password = password
        if password:
            application.password_hash = make_password(password)
        if commit:
            application.save()
        return application


class AdminOrderForm(StyledFormMixin, forms.ModelForm):
    class Meta:
        model = Order
        fields = [
            'status',
            'payment_status',
            'payment_method',
            'customer_name',
            'customer_phone',
            'customer_email',
            'alternate_phone',
            'house',
            'area',
            'landmark',
            'city',
            'district',
            'state',
            'pincode',
            'country',
            'shipping_address',
            'admin_note',
            'notes',
        ]
        labels = {
            'shipping_address': 'Shipping address',
            'admin_note': 'Admin note',
            'customer_name': 'Customer name',
            'customer_phone': 'Phone',
            'customer_email': 'Email',
            'house': 'House / Flat / Building',
            'area': 'Area / Street / Village',
        }
        widgets = {
            'shipping_address': forms.Textarea(attrs={'rows': 3}),
            'notes': forms.Textarea(attrs={'rows': 3}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._style_fields()


class AdminDateTimeWidgetMixin:
    datetime_fields = ()

    def _style_datetime_fields(self):
        for field_name in self.datetime_fields:
            if field_name not in self.fields:
                continue
            self.fields[field_name].widget = forms.DateTimeInput(
                attrs={'type': 'datetime-local', 'class': 'form-input'},
                format='%Y-%m-%dT%H:%M',
            )
            self.fields[field_name].input_formats = ['%Y-%m-%dT%H:%M', '%Y-%m-%d %H:%M:%S', '%Y-%m-%d %H:%M']
            value = self.initial.get(field_name)
            if value:
                self.initial[field_name] = value.strftime('%Y-%m-%dT%H:%M')


class CouponForm(AdminDateTimeWidgetMixin, StyledFormMixin, forms.ModelForm):
    datetime_fields = ('starts_at', 'ends_at')

    class Meta:
        model = Coupon
        fields = [
            'code',
            'title',
            'owner_type',
            'seller',
            'approval_status',
            'discount_type',
            'discount_value',
            'min_order_amount',
            'max_discount',
            'starts_at',
            'ends_at',
            'usage_limit',
            'used_count',
            'is_active',
        ]
        labels = {
            'min_order_amount': 'Minimum order amount',
            'max_discount': 'Maximum discount',
            'starts_at': 'Start date and time',
            'ends_at': 'End date and time',
            'used_count': 'Already used count',
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['seller'].required = False
        self.fields['seller'].queryset = SellerApplication.objects.filter(status=SellerApplication.Status.APPROVED).order_by('store_name')
        self._style_fields()
        self._style_datetime_fields()

    def clean_code(self):
        return (self.cleaned_data.get('code') or '').strip().upper()

    def clean(self):
        cleaned_data = super().clean()
        discount_type = cleaned_data.get('discount_type')
        discount_value = cleaned_data.get('discount_value') or 0
        starts_at = cleaned_data.get('starts_at')
        ends_at = cleaned_data.get('ends_at')
        usage_limit = cleaned_data.get('usage_limit')
        used_count = cleaned_data.get('used_count') or 0
        owner_type = cleaned_data.get('owner_type')
        seller = cleaned_data.get('seller')

        if discount_value <= 0:
            self.add_error('discount_value', 'Discount value must be greater than zero.')
        if discount_type == Coupon.DiscountType.PERCENT and discount_value > 100:
            self.add_error('discount_value', 'Percentage discount cannot be more than 100.')
        if starts_at and ends_at and starts_at >= ends_at:
            self.add_error('ends_at', 'End date must be after start date.')
        if usage_limit is not None and used_count > usage_limit:
            self.add_error('usage_limit', 'Usage limit cannot be lower than used count.')
        if owner_type == Coupon.OwnerType.SELLER and not seller:
            self.add_error('seller', 'Select a seller for seller coupons.')
        return cleaned_data


class OfferForm(AdminDateTimeWidgetMixin, StyledFormMixin, forms.ModelForm):
    datetime_fields = ('starts_at', 'ends_at')

    class Meta:
        model = Offer
        fields = [
            'title',
            'description',
            'products',
            'discount_type',
            'discount_value',
            'starts_at',
            'ends_at',
            'is_active',
        ]
        widgets = {
            'description': forms.Textarea(attrs={'rows': 4}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['products'].queryset = SpiceItem.objects.order_by('name')
        self.fields['products'].help_text = 'Select products included in this flash sale. Leave empty only for draft planning.'
        self._style_fields()
        self._style_datetime_fields()

    def clean(self):
        cleaned_data = super().clean()
        discount_type = cleaned_data.get('discount_type')
        discount_value = cleaned_data.get('discount_value') or 0
        starts_at = cleaned_data.get('starts_at')
        ends_at = cleaned_data.get('ends_at')
        if discount_value <= 0:
            self.add_error('discount_value', 'Discount value must be greater than zero.')
        if discount_type == Offer.DiscountType.PERCENT and discount_value > 100:
            self.add_error('discount_value', 'Percentage discount cannot be more than 100.')
        if starts_at and ends_at and starts_at >= ends_at:
            self.add_error('ends_at', 'End date must be after start date.')
        return cleaned_data


class ShippingChargeForm(StyledFormMixin, forms.ModelForm):
    class Meta:
        model = ShippingCharge
        fields = ['name', 'min_order_value', 'max_order_value', 'charge', 'free_delivery_threshold', 'is_active']
        labels = {
            'min_order_value': 'Minimum order amount',
            'max_order_value': 'Maximum order amount',
            'free_delivery_threshold': 'Free delivery threshold',
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._style_fields()

    def clean(self):
        cleaned_data = super().clean()
        min_value = cleaned_data.get('min_order_value') or 0
        max_value = cleaned_data.get('max_order_value')
        charge = cleaned_data.get('charge') or 0
        threshold = cleaned_data.get('free_delivery_threshold')
        if max_value is not None and max_value < min_value:
            self.add_error('max_order_value', 'Maximum amount must be greater than or equal to minimum amount.')
        if charge < 0:
            self.add_error('charge', 'Delivery charge cannot be negative.')
        if threshold is not None and threshold < min_value:
            self.add_error('free_delivery_threshold', 'Free delivery threshold cannot be below minimum amount.')
        return cleaned_data


class CourierPartnerForm(StyledFormMixin, forms.ModelForm):
    class Meta:
        model = CourierPartner
        fields = ['name', 'contact_name', 'contact_phone', 'contact_email', 'website_url', 'tracking_url', 'api_details', 'is_active']
        widgets = {
            'api_details': forms.Textarea(attrs={'rows': 4}),
        }
        help_texts = {
            'tracking_url': 'Optional. Use {tracking_number} in the URL if the courier supports direct tracking links.',
            'api_details': 'Optional provider notes or API credentials reference. Avoid storing production secrets here.',
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._style_fields()


class DeliveryAreaForm(StyledFormMixin, forms.ModelForm):
    class Meta:
        model = DeliveryArea
        fields = ['pincode', 'city', 'state', 'is_serviceable', 'cod_available', 'estimated_days', 'is_active']
        labels = {
            'is_serviceable': 'Serviceable',
            'cod_available': 'COD available',
            'estimated_days': 'Estimated delivery days',
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._style_fields()

    def clean_pincode(self):
        pincode = (self.cleaned_data.get('pincode') or '').strip()
        if not re.fullmatch(r'\d{6}', pincode):
            raise ValidationError('Enter a valid 6 digit PIN code.')
        return pincode


class ShipmentTrackingForm(AdminDateTimeWidgetMixin, StyledFormMixin, forms.ModelForm):
    datetime_fields = ('shipped_at', 'delivered_at')

    class Meta:
        model = ShipmentTracking
        fields = ['order', 'courier', 'tracking_number', 'tracking_url', 'status', 'last_location', 'admin_note', 'shipped_at', 'delivered_at']
        widgets = {
            'admin_note': forms.Textarea(attrs={'rows': 3}),
        }
        labels = {
            'tracking_number': 'Tracking ID',
            'tracking_url': 'Tracking URL',
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['order'].queryset = Order.objects.order_by('-created_at')
        self.fields['courier'].queryset = CourierPartner.objects.filter(is_active=True).order_by('name')
        self._style_fields()
        self._style_datetime_fields()


class ReturnRequestForm(StyledFormMixin, forms.ModelForm):
    class Meta:
        model = ReturnRequest
        fields = [
            'order',
            'order_item',
            'customer',
            'reason',
            'details',
            'proof_file',
            'proof_url',
            'refund_amount',
            'status',
            'refund_status',
            'pickup_status',
            'admin_note',
        ]
        widgets = {
            'details': forms.Textarea(attrs={'rows': 4}),
            'admin_note': forms.Textarea(attrs={'rows': 3}),
        }
        labels = {
            'proof_file': 'Proof image/video',
            'proof_url': 'Proof URL',
            'refund_amount': 'Refund amount',
            'admin_note': 'Admin remark',
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['order'].queryset = Order.objects.order_by('-created_at')
        self.fields['order_item'].queryset = OrderItem.objects.select_related('order').order_by('-order__created_at')
        self.fields['customer'].required = False
        self._style_fields()

    def clean(self):
        cleaned_data = super().clean()
        order = cleaned_data.get('order')
        order_item = cleaned_data.get('order_item')
        refund_amount = cleaned_data.get('refund_amount') or 0
        if order_item and order and order_item.order_id != order.pk:
            self.add_error('order_item', 'Selected item does not belong to this order.')
        if refund_amount < 0:
            self.add_error('refund_amount', 'Refund amount cannot be negative.')
        if order and order.status not in {Order.Status.DELIVERED, Order.Status.RETURNED} and cleaned_data.get('status') != ReturnRequest.Status.REJECTED:
            self.add_error('order', 'Return or refund can be opened only for delivered or already returned orders.')
        return cleaned_data


class ProductReviewForm(StyledFormMixin, forms.ModelForm):
    class Meta:
        model = ProductReview
        fields = ['product', 'customer', 'customer_name', 'rating', 'title', 'comment', 'status']
        widgets = {
            'comment': forms.Textarea(attrs={'rows': 4}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['customer'].required = False
        self._style_fields()

    def clean_rating(self):
        rating = self.cleaned_data.get('rating') or 0
        if rating < 1 or rating > 5:
            raise ValidationError('Rating must be between 1 and 5.')
        return rating


class SellerReviewForm(StyledFormMixin, forms.ModelForm):
    class Meta:
        model = SellerReview
        fields = ['seller', 'customer', 'customer_name', 'rating', 'comment', 'status', 'admin_note']
        widgets = {
            'comment': forms.Textarea(attrs={'rows': 4}),
            'admin_note': forms.Textarea(attrs={'rows': 3}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['seller'].queryset = SellerApplication.objects.order_by('store_name')
        self.fields['customer'].required = False
        self._style_fields()

    def clean_rating(self):
        rating = self.cleaned_data.get('rating') or 0
        if rating < 1 or rating > 5:
            raise ValidationError('Rating must be between 1 and 5.')
        return rating


class ReviewReportForm(StyledFormMixin, forms.ModelForm):
    class Meta:
        model = ReviewReport
        fields = ['product_review', 'seller_review', 'reporter', 'reporter_name', 'reason', 'details', 'status', 'admin_note']
        widgets = {
            'details': forms.Textarea(attrs={'rows': 4}),
            'admin_note': forms.Textarea(attrs={'rows': 3}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['reporter'].required = False
        self.fields['product_review'].required = False
        self.fields['seller_review'].required = False
        self._style_fields()

    def clean(self):
        cleaned_data = super().clean()
        product_review = cleaned_data.get('product_review')
        seller_review = cleaned_data.get('seller_review')
        if bool(product_review) == bool(seller_review):
            raise ValidationError('Select exactly one product review or seller review.')
        return cleaned_data


class NotificationTemplateForm(StyledFormMixin, forms.ModelForm):
    class Meta:
        model = NotificationTemplate
        fields = ['name', 'slug', 'template_type', 'purpose', 'subject', 'body', 'available_variables', 'is_active']
        widgets = {
            'body': forms.Textarea(attrs={'rows': 6}),
        }
        help_texts = {
            'available_variables': 'Supported examples: {{customer_name}}, {{order_id}}, {{seller_name}}, {{amount}}.',
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._style_fields()

    def clean_body(self):
        body = self.cleaned_data.get('body') or ''
        if not body.strip():
            raise ValidationError('Template body is required.')
        return body


class PushNotificationForm(StyledFormMixin, forms.ModelForm):
    class Meta:
        model = PushNotification
        fields = ['title', 'message', 'audience', 'customers', 'sellers', 'status']
        widgets = {
            'message': forms.Textarea(attrs={'rows': 4}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['customers'].queryset = User.objects.filter(is_staff=False).order_by('first_name', 'email')
        self.fields['sellers'].queryset = SellerApplication.objects.filter(status=SellerApplication.Status.APPROVED).order_by('store_name')
        self.fields['customers'].required = False
        self.fields['sellers'].required = False
        self._style_fields()

    def clean(self):
        cleaned_data = super().clean()
        audience = cleaned_data.get('audience')
        customers = cleaned_data.get('customers')
        sellers = cleaned_data.get('sellers')
        if audience == PushNotification.Audience.SELECTED_CUSTOMERS and not customers:
            self.add_error('customers', 'Select at least one customer.')
        if audience == PushNotification.Audience.SELECTED_SELLERS and not sellers:
            self.add_error('sellers', 'Select at least one seller.')
        return cleaned_data


class SellerPayoutForm(StyledFormMixin, forms.ModelForm):
    class Meta:
        model = SellerPayout
        fields = ['seller', 'requested_by', 'amount', 'bank_account', 'upi_id', 'remarks', 'transaction_reference', 'admin_note', 'status']
        widgets = {
            'remarks': forms.Textarea(attrs={'rows': 3}),
            'admin_note': forms.Textarea(attrs={'rows': 3}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['seller'].queryset = SellerApplication.objects.filter(status=SellerApplication.Status.APPROVED).order_by('store_name')
        self.fields['requested_by'].required = False
        self._style_fields()

    def clean_amount(self):
        amount = self.cleaned_data.get('amount') or 0
        if amount <= 0:
            raise ValidationError('Payout amount must be greater than zero.')
        return amount
