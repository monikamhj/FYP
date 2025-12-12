// Get CSRF token from cookie
function getCookie(name) {
  let cookieValue = null;
  if (document.cookie && document.cookie !== "") {
      const cookies = document.cookie.split(";");
      for (let i = 0; i < cookies.length; i++) {
          const cookie = cookies[i].trim();
          if (cookie.substring(0, name.length + 1) === name + "=") {
              cookieValue = decodeURIComponent(cookie.substring(name.length + 1));
              break;
          }
      }
  }
  return cookieValue;
}
const csrftoken = getCookie('csrftoken');

document.addEventListener('DOMContentLoaded', function () {
  // Set max date for DOB to today
  const today = new Date();
  const yyyy = today.getFullYear();
  const mm = String(today.getMonth() + 1).padStart(2, '0');
  const dd = String(today.getDate()).padStart(2, '0');
  const todayString = `${yyyy}-${mm}-${dd}`;
  document.getElementById('dob').setAttribute('max', todayString);

  const signupForm = document.getElementById('signup-form');
  const passwordInput = document.getElementById('password');
  const confirmPasswordInput = document.getElementById('confirm-password');
  const passwordMatchIndicator = document.getElementById('password-match');
  const togglePasswordBtn = document.getElementById('toggle-password');
  const toggleConfirmPasswordBtn = document.getElementById('toggle-confirm-password');
  const toast = document.getElementById('toast');
  const toastMessage = document.getElementById('toast-message');

  // Toggle password visibility
  togglePasswordBtn.addEventListener('click', function () {
      if (passwordInput.type === 'password') {
          passwordInput.type = 'text';
          togglePasswordBtn.innerHTML = '<svg xmlns="http://www.w3.org/2000/svg" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" class="eye-icon"><path d="M2 12s3-7 10-7 10 7 10 7-3 7-10 7-10-7-10-7Z"/><line x1="2" x2="22" y1="12" y2="12"/></svg>';
      } else {
          passwordInput.type = 'password';
          togglePasswordBtn.innerHTML = '<svg xmlns="http://www.w3.org/2000/svg" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" class="eye-icon"><path d="M2 12s3-7 10-7 10 7 10 7-3 7-10 7-10-7-10-7Z"/><circle cx="12" cy="12" r="3"/></svg>';
      }
  });

  // Toggle confirm password visibility
  toggleConfirmPasswordBtn.addEventListener('click', function () {
      if (confirmPasswordInput.type === 'password') {
          confirmPasswordInput.type = 'text';
          toggleConfirmPasswordBtn.innerHTML = '<svg xmlns="http://www.w3.org/2000/svg" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" class="eye-icon"><path d="M2 12s3-7 10-7 10 7 10 7-3 7-10 7-10-7-10-7Z"/><line x1="2" x2="22" y1="12" y2="12"/></svg>';
      } else {
          confirmPasswordInput.type = 'password';
          toggleConfirmPasswordBtn.innerHTML = '<svg xmlns="http://www.w3.org/2000/svg" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" class="eye-icon"><path d="M2 12s3-7 10-7 10 7 10 7-3 7-10 7-10-7-10-7Z"/><circle cx="12" cy="12" r="3"/></svg>';
      }
  });

  // Check if passwords match
  function checkPasswordMatch() {
      if (confirmPasswordInput.value === '') {
          passwordMatchIndicator.textContent = '';
          passwordMatchIndicator.classList.remove('match', 'no-match');
          return;
      }

      if (passwordInput.value === confirmPasswordInput.value) {
          passwordMatchIndicator.textContent = '✓';
          passwordMatchIndicator.classList.add('match');
          passwordMatchIndicator.classList.remove('no-match');
      } else {
          passwordMatchIndicator.textContent = '✗';
          passwordMatchIndicator.classList.add('no-match');
          passwordMatchIndicator.classList.remove('match');
      }
  }

  passwordInput.addEventListener('input', checkPasswordMatch);
  confirmPasswordInput.addEventListener('input', checkPasswordMatch);

  // Form submission using AJAX with CSRF
  signupForm.addEventListener("submit", function (e) {
      e.preventDefault();

      const formData = new FormData(this);

      fetch("{% url 'register_view' %}", {
          method: "POST",
          body: formData,
          headers: {
              "X-CSRFToken": csrftoken
          }
      })
          .then(response => response.json())
          .then(data => {
              if (data.success) {
                  showToast(data.success, 'success');
                  setTimeout(() => {
                      window.location.href = "{% url 'login_view' %}";
                  }, 2000);
              } else if (data.error) {
                  showToast(data.error, 'error');
              }
          })
          .catch(error => {
              console.error('Error:', error);
              showToast('An error occurred. Please try again later.', 'error');
          });
  });

  // Show toast message
  function showToast(message, type = 'error') {
      toastMessage.textContent = message;
      toast.style.backgroundColor = type === 'error' ? '#ef4444' : '#10b981';
      toast.classList.add('show');

      setTimeout(() => {
          toast.classList.remove('show');
      }, 3000);
  }
});
