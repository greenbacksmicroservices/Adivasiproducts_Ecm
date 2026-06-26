from django.db import migrations
from django.utils.text import slugify


def normalize_admin_management_data(apps, schema_editor):
    ShipmentTracking = apps.get_model('store', 'ShipmentTracking')
    NotificationTemplate = apps.get_model('store', 'NotificationTemplate')

    def normalized_status(value):
        raw = (value or '').strip().lower().replace('-', ' ').replace('_', ' ')
        exact = {
            'pending': 'pending',
            'pending pickup': 'pending',
            'processing': 'pending',
            'packed': 'packed',
            'ready to ship': 'packed',
            'shipped': 'shipped',
            'in transit': 'shipped',
            'dispatched': 'shipped',
            'out for delivery': 'out_for_delivery',
            'delivered': 'delivered',
            'completed': 'delivered',
            'cancelled': 'cancelled',
            'canceled': 'cancelled',
        }
        if raw in exact:
            return exact[raw]
        if 'out' in raw and 'deliver' in raw:
            return 'out_for_delivery'
        if 'deliver' in raw:
            return 'delivered'
        if 'cancel' in raw:
            return 'cancelled'
        if 'ship' in raw or 'transit' in raw or 'dispatch' in raw:
            return 'shipped'
        if 'pack' in raw:
            return 'packed'
        return 'pending'

    for shipment in ShipmentTracking.objects.all().only('id', 'status'):
        new_status = normalized_status(shipment.status)
        if shipment.status != new_status:
            shipment.status = new_status
            shipment.save(update_fields=['status'])

    used_slugs = set()
    for template in NotificationTemplate.objects.all().only('id', 'name', 'slug'):
        base = slugify(template.slug or template.name) or f'template-{template.pk}'
        candidate = base
        suffix = 2
        while candidate in used_slugs:
            candidate = f'{base}-{suffix}'
            suffix += 1
        used_slugs.add(candidate)
        if template.slug != candidate:
            template.slug = candidate
            template.save(update_fields=['slug'])


class Migration(migrations.Migration):

    dependencies = [
        ('store', '0021_coupon_approval_status_coupon_max_discount_and_more'),
    ]

    operations = [
        migrations.RunPython(normalize_admin_management_data, migrations.RunPython.noop),
    ]
