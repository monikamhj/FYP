function setupPasswordToggle(buttonId, inputId) {
  const button = document.getElementById(buttonId);
  const input = document.getElementById(inputId);

  if (button && input) {
    button.addEventListener('click', () => {
      const type = input.type === 'password' ? 'text' : 'password';
      input.type = type;

      const icon = button.querySelector('svg');
      if (type === 'text') {
        icon.outerHTML = '<svg>...</svg>'; // show icon
        button.setAttribute('aria-label', 'Hide password');
      } else {
        icon.outerHTML = '<svg>...</svg>'; // hide icon
        button.setAttribute('aria-label', 'Show password');
      }
    });
  }
}

// Then call it like this
setupPasswordToggle('toggle-password', 'password');
setupPasswordToggle('toggle-confirm-password', 'confirm-password');
