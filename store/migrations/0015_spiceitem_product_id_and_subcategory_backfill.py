from django.db import migrations, models
from django.utils.text import slugify


def backfill_product_ids_and_sub_categories(apps, schema_editor):
    SpiceItem = apps.get_model('store', 'SpiceItem')
    SubCategory = apps.get_model('store', 'SubCategory')

    used_product_ids = set(
        SpiceItem.objects.exclude(product_id__isnull=True)
        .exclude(product_id__exact='')
        .values_list('product_id', flat=True)
    )
    next_number = 1

    for product in SpiceItem.objects.order_by('id'):
        update_fields = []
        if not product.product_id:
            while True:
                candidate = f'PRD{next_number:05d}'
                next_number += 1
                if candidate not in used_product_ids:
                    product.product_id = candidate
                    used_product_ids.add(candidate)
                    update_fields.append('product_id')
                    break

        if update_fields:
            product.save(update_fields=update_fields)

        sub_category_name = (product.sub_category or '').strip()
        if not product.category_id or not sub_category_name:
            continue

        base_slug = slugify(sub_category_name) or f'sub-category-{product.pk}'
        slug = base_slug
        counter = 1
        while SubCategory.objects.filter(category_id=product.category_id, slug=slug).exists():
            existing = SubCategory.objects.filter(category_id=product.category_id, slug=slug).first()
            if existing and existing.name.lower() == sub_category_name.lower():
                break
            slug = f'{base_slug}-{counter}'
            counter += 1

        SubCategory.objects.get_or_create(
            category_id=product.category_id,
            slug=slug,
            defaults={
                'name': sub_category_name,
                'icon_label': ''.join(word[:1] for word in sub_category_name.split()[:2]).upper() or sub_category_name[:2].upper(),
                'is_active': True,
            },
        )


def reverse_backfill(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ('store', '0014_productreview_customer_name'),
    ]

    operations = [
        migrations.AddField(
            model_name='spiceitem',
            name='product_id',
            field=models.CharField(blank=True, editable=False, max_length=12, null=True, unique=True),
        ),
        migrations.RunPython(backfill_product_ids_and_sub_categories, reverse_backfill),
        migrations.AlterField(
            model_name='spiceitem',
            name='product_id',
            field=models.CharField(blank=True, editable=False, max_length=12, unique=True),
        ),
    ]
