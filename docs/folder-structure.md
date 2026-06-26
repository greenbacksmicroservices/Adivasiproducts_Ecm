# Lexvers Folder Structure

This project is a Django template-based e-commerce app. There is no React/Vite/Next frontend in the current codebase, so the frontend is organized through Django templates and static assets.

## Safety Decision

The installed Django app remains `store`. Its app label, models, migrations, and database table ownership were not renamed because changing app labels after migrations can break production databases.

Backend code is still in `store/`, with the first service extraction under `store/services/`. Future backend splits should be done gradually with compatibility imports and tests.

## Top-Level Layout

```text
Lexvers/
├── config/                  # Django settings, root URL config, ASGI/WSGI
├── store/                   # Main Django app, models, views, forms, urls, services
├── Frontend/
│   ├── templates/           # Section-wise Django templates
│   └── static/              # Section-wise CSS, JS, images, videos
├── media/                   # Uploaded runtime files
├── docs/                    # Project documentation
├── manage.py
├── requirements.txt
└── .env.example
```

## Backend

```text
store/
├── admin.py
├── apps.py
├── consumers.py
├── context_processors.py
├── forms.py
├── models.py
├── otp.py                  # Compatibility shim for old imports
├── routing.py
├── tests.py
├── urls.py
├── views.py
├── services/
│   ├── __init__.py
│   └── otp_service.py      # Email OTP generation, hashing, verification, email sending
├── management/
└── migrations/
```

## Templates

```text
Frontend/templates/
├── layouts/
│   ├── base.html
│   ├── auth_base.html
│   ├── admin_base.html
│   ├── seller_base.html
│   └── customer_base.html
├── partials/
│   ├── alerts.html
│   ├── empty_state.html
│   ├── loading_spinner.html
│   ├── pagination.html
│   └── toast.html
├── auth/
├── website/
│   └── partials/
├── admin_panel/
│   └── partials/
├── seller_panel/
│   ├── orders/
│   ├── partials/
│   └── products/
├── customer_panel/
│   ├── orders/
│   └── partials/
├── products/
│   └── partials/
├── cart/
│   └── partials/
├── checkout/
├── orders/
└── emails/
```

## Static Assets

```text
Frontend/static/
├── css/
│   ├── admin_panel/
│   ├── auth/
│   ├── customer_panel/
│   ├── seller_panel/
│   ├── shared/
│   └── website/
├── js/
│   ├── admin_panel/
│   ├── auth/
│   ├── customer_panel/
│   ├── seller_panel/
│   ├── shared/
│   └── website/
├── images/
│   ├── admin_panel/
│   ├── banners/
│   ├── products/
│   ├── sellers/
│   ├── shared/
│   └── website/
└── videos/
    ├── auth/
    ├── seller_panel/
    └── website/
```

## Where To Add New Files

- New admin template: `Frontend/templates/admin_panel/`
- New seller dashboard template: `Frontend/templates/seller_panel/`
- New seller order/product template: `Frontend/templates/seller_panel/orders/` or `Frontend/templates/seller_panel/products/`
- New customer template: `Frontend/templates/customer_panel/`
- New public website template: `Frontend/templates/website/`
- New product/customer-facing product template: `Frontend/templates/products/`
- New cart or checkout template: `Frontend/templates/cart/` or `Frontend/templates/checkout/`
- New email template: `Frontend/templates/emails/`
- New shared include: `Frontend/templates/partials/`
- New admin CSS: `Frontend/static/css/admin_panel/`
- New seller CSS: `Frontend/static/css/seller_panel/`
- New auth CSS/JS: `Frontend/static/css/auth/` and `Frontend/static/js/auth/`
- New reusable backend service: `store/services/`

## Developer Notes

- Keep URL names backward compatible unless a migration/deployment plan exists.
- Do not rename the `store` Django app without a database migration strategy.
- Keep media upload folders stable because existing database rows point to current media paths.
- Prefer moving backend logic into `store/services/` first, then split view modules only after tests cover the affected URLs.
