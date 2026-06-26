from django.core.management.base import BaseCommand

from store.models import Banner, Category, SpiceItem


class Command(BaseCommand):
    help = 'Seed Lexvers with multi-category marketplace data.'

    def handle(self, *args, **options):
        categories = [
            {
                'name': 'Spices',
                'description': 'Authentic spices, masalas and herbs.',
                'icon_emoji': 'SP',
                'highlight_color': '#fff4df',
                'display_order': 1,
            },
            {
                'name': 'Silk Sarees',
                'description': 'Handpicked premium silk saree designs.',
                'icon_emoji': 'SS',
                'highlight_color': '#ffe3ea',
                'display_order': 2,
            },
            {
                'name': 'Handlooms',
                'description': 'Traditional handloom lifestyle products.',
                'icon_emoji': 'HL',
                'highlight_color': '#e8f7ff',
                'display_order': 3,
            },
            {
                'name': 'Hand Crafts',
                'description': 'Artisan-made handmade decor and gifts.',
                'icon_emoji': 'HC',
                'highlight_color': '#f5f0ff',
                'display_order': 4,
            },
        ]

        category_map = {}
        for payload in categories:
            category, _ = Category.objects.update_or_create(name=payload['name'], defaults=payload)
            category_map[payload['name']] = category

        valid_category_names = [payload['name'] for payload in categories]
        Category.objects.exclude(name__in=valid_category_names).filter(items__isnull=True).delete()

        items = [
            {
                'name': 'Turmeric Powder Premium',
                'category': 'Spices',
                'short_description': 'Deep color turmeric powder for daily cooking.',
                'description': 'Curcumin-rich haldi with farm-fresh aroma and strong flavor.',
                'spice_level': SpiceItem.SpiceLevel.MEDIUM,
                'brand_name': 'Annapurna Gold',
                'pack_size': '200 g',
                'price': '149.00',
                'original_price': '199.00',
                'stock': 64,
                'image_url': 'https://images.unsplash.com/photo-1615485925600-97c39c4f9d77?auto=format&fit=crop&w=900&q=80',
                'is_featured': True,
                'display_order': 1,
            },
            {
                'name': 'Mustard Seeds Bold',
                'category': 'Spices',
                'short_description': 'Fresh rai seeds for tadka and pickles.',
                'description': 'Whole mustard seeds with sharp flavor and natural oil.',
                'spice_level': SpiceItem.SpiceLevel.MEDIUM,
                'brand_name': 'GramBite Naturals',
                'pack_size': '500 g',
                'price': '189.00',
                'original_price': '239.00',
                'stock': 52,
                'image_url': 'https://images.unsplash.com/photo-1585238341986-9f4e13d6f194?auto=format&fit=crop&w=900&q=80',
                'is_featured': True,
                'display_order': 2,
            },
            {
                'name': 'Kashmiri Chili Powder',
                'category': 'Spices',
                'short_description': 'Bright red chili powder with balanced heat.',
                'description': 'Stone-ground chillies for curry color and mild pungency.',
                'spice_level': SpiceItem.SpiceLevel.HOT,
                'brand_name': 'Zesty Harvest',
                'pack_size': '250 g',
                'price': '169.00',
                'original_price': '219.00',
                'stock': 46,
                'image_url': 'https://images.unsplash.com/photo-1596040033229-a9821ebd058d?auto=format&fit=crop&w=900&q=80',
                'is_featured': True,
                'display_order': 3,
            },
            {
                'name': 'Cumin Seeds Aroma Plus',
                'category': 'Spices',
                'short_description': 'Jeera seeds for tempering and masala blends.',
                'description': 'Sun-dried cumin seeds with warm earthy flavor.',
                'spice_level': SpiceItem.SpiceLevel.MEDIUM,
                'brand_name': 'SpiceNest',
                'pack_size': '400 g',
                'price': '209.00',
                'original_price': '269.00',
                'stock': 58,
                'image_url': 'https://images.unsplash.com/photo-1589308078059-be1415eab4c3?auto=format&fit=crop&w=900&q=80',
                'is_featured': True,
                'display_order': 4,
            },
            {
                'name': 'Black Pepper Malabar',
                'category': 'Spices',
                'short_description': 'Strong aroma and sharp bite from Kerala.',
                'description': 'Farm-sourced whole pepper for grinders and spice blends.',
                'spice_level': SpiceItem.SpiceLevel.HOT,
                'brand_name': 'Kerala Finest',
                'pack_size': '150 g',
                'price': '259.00',
                'original_price': '299.00',
                'stock': 62,
                'image_url': 'https://images.unsplash.com/photo-1610725664285-7c57e6eeac3f?auto=format&fit=crop&w=900&q=80',
                'is_featured': True,
                'display_order': 5,
            },
            {
                'name': 'Green Cardamom Elite',
                'category': 'Spices',
                'short_description': 'Fragrant elaichi for tea, desserts and biryani.',
                'description': 'Premium green cardamom pods with natural sweet aroma.',
                'spice_level': SpiceItem.SpiceLevel.MEDIUM,
                'brand_name': 'Royal Pods',
                'pack_size': '100 g',
                'price': '399.00',
                'original_price': '459.00',
                'stock': 33,
                'image_url': 'https://images.unsplash.com/photo-1606326608690-4e0281b1e588?auto=format&fit=crop&w=900&q=80',
                'is_featured': True,
                'display_order': 6,
            },
            {
                'name': 'Turmeric Lakadong Reserve',
                'category': 'Spices',
                'short_description': 'Strong lakadong turmeric with deep golden color.',
                'description': 'High-curcumin turmeric for immunity and bold taste.',
                'spice_level': SpiceItem.SpiceLevel.MILD,
                'brand_name': 'Meghalaya Roots',
                'pack_size': '300 g',
                'price': '279.00',
                'original_price': '339.00',
                'stock': 40,
                'image_url': 'https://images.unsplash.com/photo-1628771065518-0d82f1938462?auto=format&fit=crop&w=900&q=80',
                'is_featured': False,
                'display_order': 7,
            },
            {
                'name': 'Banarasi Silk Zari Bloom',
                'category': 'Silk Sarees',
                'short_description': 'Royal banarasi weave with zari border.',
                'description': 'Occasion-ready saree with rich pattern and soft drape.',
                'spice_level': SpiceItem.SpiceLevel.MILD,
                'brand_name': 'Varanasi Weaves',
                'pack_size': '1 piece',
                'price': '5499.00',
                'original_price': '6999.00',
                'stock': 12,
                'image_url': 'https://images.unsplash.com/photo-1610030469983-98e550d6193c?auto=format&fit=crop&w=900&q=80',
                'is_featured': True,
                'display_order': 8,
            },
            {
                'name': 'Kanjeevaram Heritage Gold',
                'category': 'Silk Sarees',
                'short_description': 'Classic kanjeevaram silk for festive occasions.',
                'description': 'Authentic texture, vibrant colors and durable weave.',
                'spice_level': SpiceItem.SpiceLevel.MILD,
                'brand_name': 'Temple Loom',
                'pack_size': '1 piece',
                'price': '7299.00',
                'original_price': '8999.00',
                'stock': 9,
                'image_url': 'https://images.unsplash.com/photo-1605518216938-7c31b7b14ad0?auto=format&fit=crop&w=900&q=80',
                'is_featured': True,
                'display_order': 9,
            },
            {
                'name': 'Sambalpuri Ikat Charm',
                'category': 'Silk Sarees',
                'short_description': 'Handloom ikat saree with geometric pattern.',
                'description': 'Elegant everyday silk blend with handcrafted feel.',
                'spice_level': SpiceItem.SpiceLevel.MILD,
                'brand_name': 'Odisha Artline',
                'pack_size': '1 piece',
                'price': '3899.00',
                'original_price': '4699.00',
                'stock': 16,
                'image_url': 'https://images.unsplash.com/photo-1583391733958-6905c52c6f13?auto=format&fit=crop&w=900&q=80',
                'is_featured': False,
                'display_order': 10,
            },
            {
                'name': 'Pure Cotton Handloom Bedsheet',
                'category': 'Handlooms',
                'short_description': 'Breathable handloom bedsheet set.',
                'description': 'Made by traditional weavers with long-staple cotton yarn.',
                'spice_level': SpiceItem.SpiceLevel.MILD,
                'brand_name': 'Crafted Cottons',
                'pack_size': '1 set',
                'price': '1699.00',
                'original_price': '2199.00',
                'stock': 27,
                'image_url': 'https://images.unsplash.com/photo-1600166898405-da9535204843?auto=format&fit=crop&w=900&q=80',
                'is_featured': False,
                'display_order': 11,
            },
            {
                'name': 'Handwoven Bamboo Basket',
                'category': 'Handlooms',
                'short_description': 'Multipurpose bamboo basket for kitchen and decor.',
                'description': 'Eco-friendly weave and sturdy artisan finish.',
                'spice_level': SpiceItem.SpiceLevel.MILD,
                'brand_name': 'NorthEast Looms',
                'pack_size': '1 piece',
                'price': '499.00',
                'original_price': '649.00',
                'stock': 31,
                'image_url': 'https://images.unsplash.com/photo-1528698827591-e19ccd7bc23d?auto=format&fit=crop&w=900&q=80',
                'is_featured': False,
                'display_order': 12,
            },
            {
                'name': 'Terracotta Decor Duo',
                'category': 'Hand Crafts',
                'short_description': 'Handmade terracotta decor for living room.',
                'description': 'Natural clay decor set painted with earthy tones.',
                'spice_level': SpiceItem.SpiceLevel.MILD,
                'brand_name': 'Clay Stories',
                'pack_size': '2 pieces',
                'price': '899.00',
                'original_price': '1199.00',
                'stock': 22,
                'image_url': 'https://images.unsplash.com/photo-1606760227091-3dd870d97f1d?auto=format&fit=crop&w=900&q=80',
                'is_featured': False,
                'display_order': 13,
            },
            {
                'name': 'Wooden Elephant Carving',
                'category': 'Hand Crafts',
                'short_description': 'Detailed hand-carved wooden elephant decor.',
                'description': 'Natural polished wood finish by rural artisans.',
                'spice_level': SpiceItem.SpiceLevel.MILD,
                'brand_name': 'Artisan Trail',
                'pack_size': '1 piece',
                'price': '1299.00',
                'original_price': '1599.00',
                'stock': 18,
                'image_url': 'https://images.unsplash.com/photo-1513519245088-0e12902e5a38?auto=format&fit=crop&w=900&q=80',
                'is_featured': False,
                'display_order': 14,
            },
        ]

        valid_item_names = [payload['name'] for payload in items]
        SpiceItem.objects.exclude(name__in=valid_item_names).delete()
        Category.objects.exclude(name__in=valid_category_names).filter(items__isnull=True).delete()

        for payload in items:
            category_name = payload.pop('category')
            payload['category'] = category_map[category_name]
            SpiceItem.objects.update_or_create(name=payload['name'], defaults=payload)

        banners = [
            {
                'title': 'Spices: Fresh Aroma Collection',
                'subtitle': 'Turmeric, chili, cumin and more with fast delivery.',
                'image_url': 'https://images.unsplash.com/photo-1596040033229-a9821ebd058d?auto=format&fit=crop&w=1200&q=80',
                'cta_text': 'Shop Spices',
                'cta_link': '/?category=spices',
                'display_order': 1,
            },
            {
                'title': 'Silk Sarees Festive Edit',
                'subtitle': 'Handpicked sarees for weddings and celebrations.',
                'image_url': 'https://images.unsplash.com/photo-1605518216938-7c31b7b14ad0?auto=format&fit=crop&w=1200&q=80',
                'cta_text': 'Explore Sarees',
                'cta_link': '/?category=silk-sarees',
                'display_order': 2,
            },
            {
                'title': 'Handlooms And Crafts',
                'subtitle': 'Authentic handmade products by Indian artisans.',
                'image_url': 'https://images.unsplash.com/photo-1606760227091-3dd870d97f1d?auto=format&fit=crop&w=1200&q=80',
                'cta_text': 'See Collection',
                'cta_link': '/?category=handlooms',
                'display_order': 3,
            },
        ]

        for payload in banners:
            Banner.objects.update_or_create(title=payload['title'], defaults=payload)

        self.stdout.write(self.style.SUCCESS('Lexvers sample data created/updated successfully.'))
