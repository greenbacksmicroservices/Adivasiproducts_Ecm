import secrets
from collections import namedtuple

from django.conf import settings
from django.core.mail import EmailMultiAlternatives
from django.template.loader import render_to_string
from django.utils import timezone
from django.utils.crypto import constant_time_compare, salted_hmac
from django.utils.html import strip_tags

from ..models import EmailOTP


OTPRequestResult = namedtuple('OTPRequestResult', ['sent', 'message', 'cooldown_seconds', 'otp_record'])
OTPVerifyResult = namedtuple('OTPVerifyResult', ['valid', 'message', 'otp_record'])


PURPOSE_COPY = {
    EmailOTP.Purpose.SELLER_REGISTER: {
        'subject': 'Verify your seller registration email',
        'title': 'Seller email verification',
        'summary': 'Use this code to continue your Lexvers seller registration.',
    },
    EmailOTP.Purpose.CUSTOMER_REGISTER: {
        'subject': 'Verify your Lexvers account email',
        'title': 'Customer email verification',
        'summary': 'Use this code to create your Lexvers customer account.',
    },
    EmailOTP.Purpose.LOGIN: {
        'subject': 'Your Lexvers login OTP',
        'title': 'Login with OTP',
        'summary': 'Use this code to securely login to your Lexvers account.',
    },
    EmailOTP.Purpose.FORGOT_PASSWORD: {
        'subject': 'Reset your Lexvers password',
        'title': 'Password reset verification',
        'summary': 'Use this code to verify your password reset request.',
    },
}


def normalize_email(email):
    return (email or '').strip().lower()


def generate_otp():
    return f'{secrets.randbelow(1000000):06d}'


def hash_otp(email, purpose, otp):
    value = f'{normalize_email(email)}:{purpose}:{otp}'
    return salted_hmac('store.email_otp', value, secret=settings.SECRET_KEY).hexdigest()


def _otp_settings():
    return {
        'expiry_minutes': int(getattr(settings, 'EMAIL_OTP_EXPIRY_MINUTES', 10)),
        'cooldown_seconds': int(getattr(settings, 'EMAIL_OTP_RESEND_COOLDOWN_SECONDS', 60)),
        'max_attempts': int(getattr(settings, 'EMAIL_OTP_MAX_ATTEMPTS', 5)),
    }


def _client_ip(request):
    if not request:
        return None
    forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR', '')
    if forwarded_for:
        return forwarded_for.split(',', 1)[0].strip()
    return request.META.get('REMOTE_ADDR') or None


def _user_agent(request):
    if not request:
        return ''
    return (request.META.get('HTTP_USER_AGENT') or '')[:255]


def send_otp_email(email, otp, purpose):
    copy = PURPOSE_COPY.get(purpose, PURPOSE_COPY[EmailOTP.Purpose.LOGIN])
    expiry_minutes = _otp_settings()['expiry_minutes']
    html_body = render_to_string(
        'emails/otp_email.html',
        {
            'otp': otp,
            'purpose': purpose,
            'title': copy['title'],
            'summary': copy['summary'],
            'expiry_minutes': expiry_minutes,
        },
    )
    text_body = strip_tags(html_body)
    message = EmailMultiAlternatives(
        subject=copy['subject'],
        body=text_body,
        from_email=settings.DEFAULT_FROM_EMAIL,
        to=[email],
    )
    message.attach_alternative(html_body, 'text/html')
    message.send(fail_silently=False)


def send_account_email(email, template_name, subject, context=None):
    html_body = render_to_string(template_name, context or {})
    text_body = strip_tags(html_body)
    message = EmailMultiAlternatives(
        subject=subject,
        body=text_body,
        from_email=settings.DEFAULT_FROM_EMAIL,
        to=[email],
    )
    message.attach_alternative(html_body, 'text/html')
    message.send(fail_silently=True)


def create_email_otp(email, purpose, request=None, send_email=True):
    settings_data = _otp_settings()
    email = normalize_email(email)
    now = timezone.now()
    cooldown_starts_at = now - timezone.timedelta(seconds=settings_data['cooldown_seconds'])
    latest = (
        EmailOTP.objects.filter(email__iexact=email, purpose=purpose, is_used=False)
        .order_by('-created_at')
        .first()
    )

    if latest and latest.created_at >= cooldown_starts_at:
        remaining = settings_data['cooldown_seconds'] - int((now - latest.created_at).total_seconds())
        return OTPRequestResult(False, 'Please wait before requesting another OTP.', max(1, remaining), latest)

    EmailOTP.objects.filter(email__iexact=email, purpose=purpose, is_used=False).update(is_used=True)
    otp = generate_otp()
    otp_record = EmailOTP.objects.create(
        email=email,
        purpose=purpose,
        otp_hash=hash_otp(email, purpose, otp),
        expires_at=now + timezone.timedelta(minutes=settings_data['expiry_minutes']),
        ip_address=_client_ip(request),
        user_agent=_user_agent(request),
    )
    if send_email:
        try:
            send_otp_email(email, otp, purpose)
        except Exception:
            otp_record.is_used = True
            otp_record.save(update_fields=['is_used', 'updated_at'])
            raise
    return OTPRequestResult(True, 'OTP sent to your email.', settings_data['cooldown_seconds'], otp_record)


def verify_otp(email, purpose, otp):
    email = normalize_email(email)
    clean_otp = ''.join(ch for ch in str(otp or '') if ch.isdigit())
    if len(clean_otp) != 6:
        return OTPVerifyResult(False, 'Enter the 6 digit OTP.', None)

    otp_record = (
        EmailOTP.objects.filter(email__iexact=email, purpose=purpose, is_used=False)
        .order_by('-created_at')
        .first()
    )
    if not otp_record:
        return OTPVerifyResult(False, 'OTP expired, please request a new one.', None)

    settings_data = _otp_settings()
    if otp_record.is_expired:
        otp_record.is_used = True
        otp_record.save(update_fields=['is_used', 'updated_at'])
        return OTPVerifyResult(False, 'OTP expired, please request a new one.', otp_record)

    if otp_record.attempts >= settings_data['max_attempts']:
        otp_record.is_used = True
        otp_record.save(update_fields=['is_used', 'updated_at'])
        return OTPVerifyResult(False, 'Too many attempts, request a new OTP.', otp_record)

    expected_hash = hash_otp(email, purpose, clean_otp)
    if not constant_time_compare(expected_hash, otp_record.otp_hash):
        otp_record.attempts += 1
        update_fields = ['attempts', 'updated_at']
        if otp_record.attempts >= settings_data['max_attempts']:
            otp_record.is_used = True
            update_fields.append('is_used')
            message = 'Too many attempts, request a new OTP.'
        else:
            remaining = settings_data['max_attempts'] - otp_record.attempts
            message = f'Invalid OTP. {remaining} attempt{"s" if remaining != 1 else ""} left.'
        otp_record.save(update_fields=update_fields)
        return OTPVerifyResult(False, message, otp_record)

    return OTPVerifyResult(True, 'Email verified successfully.', otp_record)


def mark_otp_used(otp_record):
    if otp_record and not otp_record.is_used:
        otp_record.is_used = True
        otp_record.save(update_fields=['is_used', 'updated_at'])


def cleanup_expired_otps():
    now = timezone.now()
    EmailOTP.objects.filter(expires_at__lt=now, is_used=False).update(is_used=True)
    return EmailOTP.objects.filter(expires_at__lt=now - timezone.timedelta(days=7), is_used=True).delete()
