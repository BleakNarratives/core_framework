(() => {
  const form = document.querySelector('form[action*="/review"]');
  const recipient = document.querySelector('#review-recipient');
  if (!form || !recipient) return;

  form.addEventListener('submit', (event) => {
    const address = recipient.value.trim();
    if (!address) {
      event.preventDefault();
      recipient.focus();
      recipient.setCustomValidity('Enter the recipient after checking the original Pytch record.');
      recipient.reportValidity();
      return;
    }

    let hidden = form.querySelector('input[name="recipient"]');
    if (!hidden) {
      hidden = document.createElement('input');
      hidden.type = 'hidden';
      hidden.name = 'recipient';
      form.append(hidden);
    }
    hidden.value = address;
  });

  recipient.addEventListener('input', () => recipient.setCustomValidity(''));
})();
