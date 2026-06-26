from django.contrib.auth.models import User
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase
from django.test import override_settings
from django.urls import reverse

from .forms import SellerApplicationForm
from .models import Cart, CartItem, Category, EmailOTP, Order, OrderItem, ProductQuantityOption, SellerApplication, SpiceItem, SubCategory
from .views import SELLER_REGISTER_VERIFIED_SESSION_KEY


class CatalogSyncTests(TestCase):
    def setUp(self):
        self.food = Category.objects.create(name='Food', slug='food', is_active=True)
        self.spices = Category.objects.create(name='Spices', slug='spices', is_active=True)
        self.veg = SubCategory.objects.create(category=self.food, name='Veg', slug='veg', is_active=True)

    def test_product_id_is_generated(self):
        product = SpiceItem.objects.create(
            name='Paneer Butter Masala',
            category=self.food,
            sub_category='Veg',
            short_description='Ready to cook',
            price=120,
            stock=8,
            is_active=True,
            approval_status=SpiceItem.ApprovalStatus.APPROVED,
        )

        self.assertRegex(product.product_id, r'^PRD\d{5}$')

    def test_food_category_routes_render_products(self):
        SpiceItem.objects.create(
            name='Food Route Product',
            category=self.food,
            sub_category='Veg',
            short_description='Visible food product',
            price=140,
            stock=5,
            is_active=True,
            approval_status=SpiceItem.ApprovalStatus.APPROVED,
        )

        for url in [reverse('category-page', kwargs={'slug': 'food'}), reverse('store-category', kwargs={'slug': 'food'})]:
            response = self.client.get(url)
            self.assertEqual(response.status_code, 200)
            self.assertContains(response, 'Food Route Product')
            self.assertContains(response, 'Veg')

    def test_sub_category_options_are_database_driven(self):
        response = self.client.get(reverse('sub-category-options'), {'category_id': self.food.pk})

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['options'][0]['name'], 'Veg')

    def test_seller_product_create_goes_live(self):
        user = User.objects.create_user(username='seller@example.com', email='seller@example.com', password='pass12345')
        SellerApplication.objects.create(
            name='Seller',
            email='seller@example.com',
            phone='1234567890',
            password_hash='hash',
            store_name='Seller Store',
            status=SellerApplication.Status.APPROVED,
        )
        self.client.login(username='seller@example.com', password='pass12345')

        response = self.client.post(
            reverse('seller-product-create'),
            {
                'name': 'Seller Food Product',
                'category': self.food.pk,
                'sub_category': self.veg.pk,
                'brand_name': 'Seller Co',
                'price': '99.00',
                'original_price': '',
                'stock': '12',
                'sku_code': '',
                'short_description': 'Seller live item',
                'description': '',
                'specifications': '',
                'shipping_weight': '',
                'warranty_details': '',
                'pack_size': '',
                'spice_level': SpiceItem.SpiceLevel.MEDIUM,
            },
        )

        self.assertEqual(response.status_code, 302)
        product = SpiceItem.objects.get(name='Seller Food Product')
        self.assertEqual(product.product_id[:3], 'PRD')
        self.assertEqual(product.sub_category, 'Veg')
        self.assertTrue(product.is_active)
        self.assertEqual(product.approval_status, SpiceItem.ApprovalStatus.APPROVED)

    def test_admin_product_and_subcategory_pages_render(self):
        staff = User.objects.create_user(username='admin@example.com', email='admin@example.com', password='pass12345', is_staff=True)
        SpiceItem.objects.create(
            name='Admin Render Product',
            category=self.food,
            sub_category='Veg',
            short_description='Admin visible item',
            price=110,
            stock=4,
            is_active=True,
            approval_status=SpiceItem.ApprovalStatus.APPROVED,
        )
        self.client.login(username='admin@example.com', password='pass12345')

        for url in [
            reverse('admin-items'),
            reverse('admin-subcategories'),
            reverse('admin-subcategory-detail', kwargs={'pk': self.veg.pk}),
        ]:
            response = self.client.get(url)
            self.assertEqual(response.status_code, 200)

    def test_variant_image_is_used_for_cart_and_order_items(self):
        customer = User.objects.create_user(username='buyer@example.com', email='buyer@example.com', password='pass12345')
        product = SpiceItem.objects.create(
            name='Variant Image Product',
            category=self.food,
            sub_category='Veg',
            short_description='Variant image item',
            price=100,
            stock=8,
            image_url='https://example.com/product.webp',
            is_active=True,
            approval_status=SpiceItem.ApprovalStatus.APPROVED,
        )
        option = ProductQuantityOption.objects.create(
            product=product,
            label='300 gm',
            price=120,
            stock=4,
            image_file='spices/quantity_options/variant-300.webp',
        )
        cart = Cart.objects.create(user=customer)
        cart_item = CartItem.objects.create(cart=cart, product=product, quantity_option=option, quantity=1, unit_price=option.price)
        order = Order.objects.create(customer=customer, customer_name='Buyer', customer_phone='9999999999')
        order_item = OrderItem.objects.create(
            order=order,
            product=product,
            quantity_option=option,
            product_name=product.name,
            product_image=product.image_url,
            pack_size=option.label,
            unit_price=option.price,
            quantity=1,
        )

        self.assertIn('variant-300.webp', cart_item.display_image)
        self.assertIn('variant-300.webp', order_item.display_image)

    def test_product_detail_exposes_each_quantity_image(self):
        product = SpiceItem.objects.create(
            name='Quantity Switch Product',
            category=self.food,
            sub_category='Veg',
            short_description='Quantity switch item',
            price=100,
            stock=8,
            image_url='https://example.com/product.webp',
            is_active=True,
            approval_status=SpiceItem.ApprovalStatus.APPROVED,
        )
        ProductQuantityOption.objects.create(
            product=product,
            label='200 gm',
            price=100,
            stock=3,
            image_file='spices/quantity_options/variant-200.webp',
        )
        ProductQuantityOption.objects.create(
            product=product,
            label='300 gm',
            price=140,
            stock=4,
            image_file='spices/quantity_options/variant-300.webp',
        )

        response = self.client.get(reverse('product-detail', kwargs={'slug': product.slug}))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'variant-200.webp')
        self.assertContains(response, 'variant-300.webp')
        self.assertContains(response, 'data-option-variant-image')


class SellerRegistrationFlowTests(TestCase):
    def seller_data(self, email='seller-new@example.com'):
        return {
            'name': 'New Seller',
            'email': email,
            'phone': '9876543210',
            'alternate_phone': '',
            'password': 'StrongPass123!',
            'confirm_password': 'StrongPass123!',
            'store_name': 'New Seller Store',
            'store_display_name': 'New Seller Store',
            'store_description': 'Fresh regional products.',
            'business_type': SellerApplication.BusinessType.INDIVIDUAL,
            'aadhaar_number': '123456789012',
            'pan_number': 'ABCDE1234F',
            'owner_dob': '1990-01-01',
            'owner_address': 'Owner address',
            'gst_available': 'no',
            'gst_number': '',
            'legal_business_name': 'New Seller Store',
            'tax_pan_number': 'ABCDE1234F',
            'bank_account_name': 'New Seller',
            'bank_name': 'Test Bank',
            'bank_account_number': '123456789012',
            'confirm_bank_account_number': '123456789012',
            'bank_ifsc': 'ABCD0123456',
            'branch_name': 'Main Branch',
            'pickup_contact_name': 'New Seller',
            'pickup_phone': '9876543210',
            'pickup_address_line1': 'Pickup address',
            'pickup_address_line2': '',
            'pickup_city': 'Kolkata',
            'pickup_state': 'West Bengal',
            'pickup_pincode': '700001',
            'pickup_landmark': '',
            'product_categories': ['spices-masala'],
            'primary_category': 'spices-masala',
            'approx_products_count': '10',
            'brand_name': '',
            'sells_handmade': 'no',
            'confirm_details': 'on',
            'terms_accepted': 'on',
            'approval_access_ack': 'on',
            'extra_document_indexes': ['row_1', 'row_empty'],
            'extra_document_name_row_1': 'FSSAI License',
            'extra_document_name_row_empty': '',
        }

    def seller_files(self):
        def doc(name):
            return SimpleUploadedFile(name, b'%PDF-1.4 test file', content_type='application/pdf')

        return {
            'aadhaar_front': doc('aadhaar-front.pdf'),
            'pan_card': doc('pan-card.pdf'),
            'cancelled_cheque': doc('cancelled-cheque.pdf'),
            'shop_photo': doc('shop-photo.pdf'),
            'owner_photo': doc('owner-photo.pdf'),
            'business_proof': doc('business-proof.pdf'),
            'address_proof': doc('address-proof.pdf'),
            'signature_upload': doc('signature.pdf'),
            'extra_document_file_row_1': doc('fssai.pdf'),
        }

    def seller_payload(self, email='seller-new@example.com'):
        payload = self.seller_data(email=email)
        payload.update(self.seller_files())
        return payload

    def test_seller_form_saves_named_extra_document_and_optional_aadhaar_back(self):
        form = SellerApplicationForm(data=self.seller_data(), files=self.seller_files())

        self.assertTrue(form.is_valid(), form.errors.as_json())
        application = form.save()

        self.assertFalse(application.aadhaar_back)
        extra_document = application.extra_documents.get()
        self.assertEqual(extra_document.document_name, 'FSSAI License')
        self.assertEqual(extra_document.original_name, 'fssai.pdf')

    def test_seller_submit_requires_verified_email_session(self):
        response = self.client.post(reverse('seller-register'), data=self.seller_payload())

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Verify this email with OTP before submitting your seller request.')
        self.assertFalse(SellerApplication.objects.exists())

    def test_seller_submit_creates_pending_request_after_email_verification(self):
        email = 'verified-seller@example.com'
        session = self.client.session
        session[SELLER_REGISTER_VERIFIED_SESSION_KEY] = {'email': email, 'verified': True}
        session.save()

        response = self.client.post(reverse('seller-register'), data=self.seller_payload(email=email))

        self.assertEqual(response.status_code, 302)
        application = SellerApplication.objects.get(email=email)
        self.assertEqual(application.status, SellerApplication.Status.PENDING)
        self.assertTrue(application.email_verified)
        self.assertEqual(application.extra_documents.get().document_name, 'FSSAI License')

    @override_settings(EMAIL_BACKEND='django.core.mail.backends.locmem.EmailBackend')
    def test_seller_otp_request_does_not_expose_otp(self):
        response = self.client.post(reverse('seller-register-send-otp'), {'email': 'otp-seller@example.com'})

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertTrue(payload['success'])
        self.assertNotIn('otp', payload)
        self.assertTrue(EmailOTP.objects.filter(email='otp-seller@example.com', purpose=EmailOTP.Purpose.SELLER_REGISTER).exists())
