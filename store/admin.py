from django.contrib import admin

from .models import (
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
    NotificationTemplate,
    Order,
    OrderItem,
    OrderNotification,
    OrderStatusHistory,
    Offer,
    Payment,
    ProductQuantityOption,
    ProductReview,
    PushNotification,
    ReturnRequest,
    ReviewReport,
    SavedProduct,
    SearchHistory,
    SellerPayout,
    SellerApplication,
    SellerApplicationExtraDocument,
    SellerReview,
    ShipmentTracking,
    ShippingCharge,
    SpiceItem,
    SpiceItemPhoto,
    SubCategory,
    WebsiteSetting,
)


@admin.register(Category)
class CategoryAdmin(admin.ModelAdmin):
    list_display = ('name', 'is_active', 'display_order', 'updated_at')
    list_filter = ('is_active',)
    search_fields = ('name', 'description')
    prepopulated_fields = {'slug': ('name',)}


@admin.register(Banner)
class BannerAdmin(admin.ModelAdmin):
    list_display = ('title', 'display_order', 'is_active', 'updated_at')
    list_filter = ('is_active',)
    search_fields = ('title', 'subtitle')


@admin.register(SubCategory)
class SubCategoryAdmin(admin.ModelAdmin):
    list_display = ('name', 'category', 'is_active', 'display_order', 'updated_at')
    list_filter = ('is_active', 'category')
    search_fields = ('name', 'category__name', 'description')
    prepopulated_fields = {'slug': ('name',)}


class SellerApplicationExtraDocumentInline(admin.TabularInline):
    model = SellerApplicationExtraDocument
    extra = 0
    fields = ('document_name', 'file', 'original_name', 'created_at')
    readonly_fields = ('created_at',)


@admin.register(SellerApplication)
class SellerApplicationAdmin(admin.ModelAdmin):
    list_display = ('request_code', 'store_name', 'name', 'email', 'email_verified', 'phone', 'business_type', 'primary_category', 'status', 'created_at')
    list_filter = ('status', 'business_type', 'email_verified')
    search_fields = ('store_name', 'name', 'email', 'phone', 'pan_number', 'gst_number')
    readonly_fields = ('password_hash', 'request_code', 'created_at', 'updated_at')
    inlines = (SellerApplicationExtraDocumentInline,)


@admin.register(SellerApplicationExtraDocument)
class SellerApplicationExtraDocumentAdmin(admin.ModelAdmin):
    list_display = ('application', 'document_name', 'original_name', 'created_at')
    search_fields = ('application__store_name', 'application__email', 'document_name', 'original_name')


@admin.register(CustomerProfile)
class CustomerProfileAdmin(admin.ModelAdmin):
    list_display = ('user', 'phone', 'language', 'email_verified', 'updated_at')
    list_filter = ('language', 'email_verified')
    search_fields = ('user__username', 'user__email', 'user__first_name', 'phone')


@admin.register(EmailOTP)
class EmailOTPAdmin(admin.ModelAdmin):
    list_display = ('email', 'purpose', 'expires_at', 'attempts', 'is_used', 'created_at')
    list_filter = ('purpose', 'is_used', 'created_at')
    search_fields = ('email',)
    readonly_fields = ('email', 'purpose', 'otp_hash', 'expires_at', 'attempts', 'is_used', 'ip_address', 'user_agent', 'created_at', 'updated_at')


@admin.register(CustomerAddress)
class CustomerAddressAdmin(admin.ModelAdmin):
    list_display = ('user', 'label', 'city', 'state', 'pincode', 'is_default', 'updated_at')
    list_filter = ('is_default', 'state')
    search_fields = ('user__email', 'full_name', 'phone', 'city', 'pincode')


@admin.register(SavedProduct)
class SavedProductAdmin(admin.ModelAdmin):
    list_display = ('user', 'product', 'created_at')
    search_fields = ('user__email', 'product__name')


@admin.register(SearchHistory)
class SearchHistoryAdmin(admin.ModelAdmin):
    list_display = ('user', 'term', 'updated_at')
    search_fields = ('user__email', 'user__username', 'term')
    readonly_fields = ('normalized_term', 'created_at', 'updated_at')


class SpiceItemPhotoInline(admin.TabularInline):
    model = SpiceItemPhoto
    extra = 3
    max_num = 6
    fields = ('image_file', 'alt_text', 'display_order', 'is_active')


class ProductQuantityOptionInline(admin.TabularInline):
    model = ProductQuantityOption
    extra = 0
    fields = ('label', 'price', 'original_price', 'stock', 'display_order', 'is_active')


@admin.register(SpiceItem)
class SpiceItemAdmin(admin.ModelAdmin):
    list_display = (
        'product_id',
        'name',
        'category',
        'price',
        'initial_stock',
        'stock',
        'owner_type',
        'approval_status',
        'is_featured',
        'is_active',
        'updated_at',
    )
    list_filter = ('is_active', 'is_featured', 'owner_type', 'approval_status', 'spice_level', 'category')
    search_fields = ('product_id', 'name', 'short_description', 'sku_code', 'category__name', 'seller__store_name')
    readonly_fields = ('product_id', 'created_at', 'updated_at')
    prepopulated_fields = {'slug': ('name',)}
    inlines = [ProductQuantityOptionInline, SpiceItemPhotoInline]


@admin.register(SpiceItemPhoto)
class SpiceItemPhotoAdmin(admin.ModelAdmin):
    list_display = ('product', 'display_order', 'is_active', 'updated_at')
    list_filter = ('is_active',)
    search_fields = ('product__name', 'alt_text')


class OrderItemInline(admin.TabularInline):
    model = OrderItem
    extra = 0
    readonly_fields = ('line_total',)
    fields = ('product', 'quantity_option', 'seller', 'product_name', 'quantity', 'unit_price', 'line_total', 'item_status')


@admin.register(Order)
class OrderAdmin(admin.ModelAdmin):
    list_display = ('order_number', 'customer_name', 'status', 'payment_status', 'total_amount', 'is_seen_by_admin', 'created_at')
    list_filter = ('status', 'payment_status', 'created_at')
    search_fields = ('order_number', 'order_id', 'customer_name', 'customer_email', 'customer_phone')
    readonly_fields = ('order_number', 'order_id', 'subtotal', 'shipping_fee', 'discount_amount', 'total_amount', 'created_at', 'updated_at')
    inlines = [OrderItemInline]


@admin.register(OrderItem)
class OrderItemAdmin(admin.ModelAdmin):
    list_display = ('order', 'product_name', 'seller_name', 'quantity', 'unit_price', 'line_total', 'item_status')
    list_filter = ('seller', 'item_status')
    search_fields = ('order__order_number', 'product_name', 'seller_name')


class CartItemInline(admin.TabularInline):
    model = CartItem
    extra = 0
    fields = ('product', 'quantity_option', 'quantity', 'unit_price')


@admin.register(Cart)
class CartAdmin(admin.ModelAdmin):
    list_display = ('user', 'status', 'item_count', 'updated_at')
    list_filter = ('status',)
    search_fields = ('user__email', 'user__username')
    inlines = [CartItemInline]


@admin.register(CartItem)
class CartItemAdmin(admin.ModelAdmin):
    list_display = ('cart', 'product', 'quantity_option', 'quantity', 'unit_price', 'updated_at')
    search_fields = ('cart__user__email', 'product__name')


@admin.register(Payment)
class PaymentAdmin(admin.ModelAdmin):
    list_display = ('payment_id', 'order', 'method', 'status', 'amount', 'is_demo', 'created_at')
    list_filter = ('method', 'status', 'is_demo')
    search_fields = ('payment_id', 'order__order_number', 'razorpay_payment_id')


@admin.register(OrderStatusHistory)
class OrderStatusHistoryAdmin(admin.ModelAdmin):
    list_display = ('order', 'order_item', 'status', 'changed_by', 'created_at')
    list_filter = ('status',)
    search_fields = ('order__order_number', 'note')


@admin.register(OrderNotification)
class OrderNotificationAdmin(admin.ModelAdmin):
    list_display = ('title', 'audience', 'notification_type', 'order', 'seller', 'user', 'is_read', 'created_at')
    list_filter = ('audience', 'notification_type', 'is_read')
    search_fields = ('title', 'message', 'order__order_number', 'seller__store_name', 'user__email')


@admin.register(ProductQuantityOption)
class ProductQuantityOptionAdmin(admin.ModelAdmin):
    list_display = ('product', 'label', 'price', 'original_price', 'stock', 'display_order', 'is_active', 'updated_at')
    list_filter = ('is_active',)
    search_fields = ('product__name', 'label', 'sku_code')


@admin.register(Coupon)
class CouponAdmin(admin.ModelAdmin):
    list_display = ('code', 'title', 'owner_type', 'seller', 'discount_type', 'discount_value', 'min_order_amount', 'usage_limit', 'used_count', 'approval_status', 'is_active')
    list_filter = ('owner_type', 'approval_status', 'discount_type', 'is_active')
    search_fields = ('code', 'title', 'seller__store_name')


@admin.register(CouponRedemption)
class CouponRedemptionAdmin(admin.ModelAdmin):
    list_display = ('coupon', 'order', 'user', 'discount_amount', 'created_at')
    search_fields = ('coupon__code', 'order__order_number', 'user__email')
    readonly_fields = ('created_at', 'updated_at')


@admin.register(Offer)
class OfferAdmin(admin.ModelAdmin):
    list_display = ('title', 'discount_type', 'discount_value', 'starts_at', 'ends_at', 'is_active', 'updated_at')
    list_filter = ('discount_type', 'is_active')
    search_fields = ('title', 'description', 'products__name')
    filter_horizontal = ('products',)


@admin.register(ShippingCharge)
class ShippingChargeAdmin(admin.ModelAdmin):
    list_display = ('name', 'min_order_value', 'max_order_value', 'charge', 'free_delivery_threshold', 'is_active')
    list_filter = ('is_active',)
    search_fields = ('name',)


@admin.register(CourierPartner)
class CourierPartnerAdmin(admin.ModelAdmin):
    list_display = ('name', 'contact_name', 'contact_phone', 'contact_email', 'is_active')
    list_filter = ('is_active',)
    search_fields = ('name', 'contact_name', 'contact_phone', 'contact_email')


@admin.register(DeliveryArea)
class DeliveryAreaAdmin(admin.ModelAdmin):
    list_display = ('pincode', 'city', 'state', 'is_serviceable', 'cod_available', 'estimated_days', 'is_active')
    list_filter = ('state', 'is_serviceable', 'cod_available', 'is_active')
    search_fields = ('pincode', 'city', 'state')


@admin.register(ShipmentTracking)
class ShipmentTrackingAdmin(admin.ModelAdmin):
    list_display = ('order', 'courier', 'tracking_number', 'status', 'last_location', 'updated_at')
    list_filter = ('status', 'courier')
    search_fields = ('order__order_number', 'tracking_number', 'last_location')


@admin.register(ReturnRequest)
class ReturnRequestAdmin(admin.ModelAdmin):
    list_display = ('order', 'order_item', 'customer', 'status', 'refund_status', 'created_at', 'processed_at')
    list_filter = ('status', 'refund_status', 'created_at')
    search_fields = ('order__order_number', 'customer__email', 'reason', 'admin_remark')


@admin.register(ProductReview)
class ProductReviewAdmin(admin.ModelAdmin):
    list_display = ('product', 'reviewer_label', 'rating', 'status', 'created_at')
    list_filter = ('rating', 'status')
    search_fields = ('product__name', 'customer__email', 'customer_name', 'comment')


@admin.register(SellerReview)
class SellerReviewAdmin(admin.ModelAdmin):
    list_display = ('seller', 'reviewer_label', 'rating', 'status', 'created_at')
    list_filter = ('rating', 'status')
    search_fields = ('seller__store_name', 'customer__email', 'customer_name', 'comment')


@admin.register(ReviewReport)
class ReviewReportAdmin(admin.ModelAdmin):
    list_display = ('review_label', 'reporter_label', 'reason', 'status', 'created_at')
    list_filter = ('status',)
    search_fields = ('reason', 'details', 'reporter__email', 'reporter_name')


@admin.register(PushNotification)
class PushNotificationAdmin(admin.ModelAdmin):
    list_display = ('title', 'audience', 'recipient_count', 'status', 'sent_at', 'sent_by')
    list_filter = ('audience', 'status')
    search_fields = ('title', 'message', 'sent_by__email')
    filter_horizontal = ('customers', 'sellers')


@admin.register(NotificationTemplate)
class NotificationTemplateAdmin(admin.ModelAdmin):
    list_display = ('name', 'template_type', 'purpose', 'is_active', 'updated_at')
    list_filter = ('template_type', 'is_active')
    search_fields = ('name', 'subject', 'purpose', 'body')


@admin.register(SellerPayout)
class SellerPayoutAdmin(admin.ModelAdmin):
    list_display = ('payout_id', 'seller', 'amount', 'status', 'processed_at', 'created_at')
    list_filter = ('status',)
    search_fields = ('payout_id', 'seller__store_name', 'transaction_reference')


@admin.register(WebsiteSetting)
class WebsiteSettingAdmin(admin.ModelAdmin):
    list_display = ('key', 'label', 'group', 'is_active', 'updated_at')
    list_filter = ('group', 'is_active')
    search_fields = ('key', 'label', 'value')
