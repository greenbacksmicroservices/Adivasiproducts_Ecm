(function () {
  function showToast(message, type) {
    if (!message) return;
    let wrap = document.querySelector('[data-otp-toast-wrap]');
    if (!wrap) {
      wrap = document.createElement('div');
      wrap.className = 'otp-toast-wrap';
      wrap.setAttribute('data-otp-toast-wrap', '1');
      document.body.appendChild(wrap);
    }
    const toast = document.createElement('div');
    toast.className = 'otp-toast' + (type === 'error' ? ' error' : '');
    toast.textContent = message;
    wrap.appendChild(toast);
    window.setTimeout(function () {
      toast.remove();
    }, 4200);
  }

  function setLoading(button, loading) {
    if (!button) return;
    button.disabled = loading;
    button.classList.toggle('is-loading', loading);
  }

  function bindOtpCard(card) {
    const boxes = Array.from(card.querySelectorAll('[data-otp-box]'));
    const hidden = card.querySelector('[data-otp-hidden]');
    const form = card.querySelector('[data-otp-form]');
    if (!boxes.length || !hidden || !form) return;

    function syncHidden() {
      hidden.value = boxes.map(function (box) { return box.value; }).join('');
    }

    boxes.forEach(function (box, index) {
      box.addEventListener('input', function () {
        const value = box.value.replace(/\D/g, '').slice(-1);
        box.value = value;
        syncHidden();
        if (value && boxes[index + 1]) {
          boxes[index + 1].focus();
        }
      });

      box.addEventListener('keydown', function (event) {
        if (event.key === 'Backspace' && !box.value && boxes[index - 1]) {
          boxes[index - 1].focus();
        }
        if (event.key === 'ArrowLeft' && boxes[index - 1]) {
          event.preventDefault();
          boxes[index - 1].focus();
        }
        if (event.key === 'ArrowRight' && boxes[index + 1]) {
          event.preventDefault();
          boxes[index + 1].focus();
        }
      });

      box.addEventListener('paste', function (event) {
        event.preventDefault();
        const pasted = (event.clipboardData || window.clipboardData).getData('text').replace(/\D/g, '').slice(0, 6);
        if (!pasted) return;
        boxes.forEach(function (item, pasteIndex) {
          item.value = pasted[pasteIndex] || '';
        });
        syncHidden();
        const focusIndex = Math.min(pasted.length, boxes.length) - 1;
        boxes[Math.max(focusIndex, 0)].focus();
      });
    });

    form.addEventListener('submit', function (event) {
      syncHidden();
      if (hidden.value.length !== 6) {
        event.preventDefault();
        showToast('Enter the 6 digit OTP.', 'error');
        return;
      }
      setLoading(form.querySelector('[data-loading-button]'), true);
    });

    boxes[0].focus();
  }

  function bindRequestForms() {
    document.querySelectorAll('[data-loading-form]').forEach(function (form) {
      form.addEventListener('submit', function () {
        setLoading(form.querySelector('[data-loading-button]'), true);
      });
    });
  }

  function bindCountdowns() {
    document.querySelectorAll('[data-resend-button]').forEach(function (button) {
      const hint = document.querySelector(button.getAttribute('data-hint-target'));
      let remaining = parseInt(button.getAttribute('data-cooldown') || '0', 10);
      const originalText = button.getAttribute('data-original-text') || button.textContent.trim() || 'Resend OTP';
      button.setAttribute('data-original-text', originalText);

      function render() {
        if (remaining > 0) {
          button.disabled = true;
          button.textContent = 'Resend in ' + remaining + 's';
          if (hint) hint.textContent = 'You can request a new OTP in ' + remaining + ' seconds.';
          remaining -= 1;
          window.setTimeout(render, 1000);
        } else {
          button.disabled = false;
          button.textContent = originalText;
          if (hint) hint.textContent = 'Did not get the OTP? You can resend it now.';
        }
      }

      render();
    });

    document.querySelectorAll('[data-resend-form]').forEach(function (form) {
      form.addEventListener('submit', function () {
        setLoading(form.querySelector('[data-resend-button]'), true);
      });
    });
  }

  document.addEventListener('DOMContentLoaded', function () {
    document.querySelectorAll('[data-otp-card]').forEach(bindOtpCard);
    bindRequestForms();
    bindCountdowns();
    document.querySelectorAll('[data-otp-toast]').forEach(function (item) {
      showToast(item.getAttribute('data-otp-toast'), item.getAttribute('data-otp-toast-type'));
    });
  });
})();
