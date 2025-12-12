document.addEventListener('DOMContentLoaded', function() {
  // Calendar state
  let fromDate = null;
  let toDate = null;
  let currentFromMonth = new Date();
  let currentToMonth = new Date();

  // DOM elements
  const fromCalendarDays = document.getElementById('fromCalendarDays');
  const toCalendarDays = document.getElementById('toCalendarDays');
  const currentMonthFromEl = document.getElementById('currentMonthFrom');
  const currentMonthToEl = document.getElementById('currentMonthTo');
  const prevMonthFromBtn = document.getElementById('prevMonthFrom');
  const nextMonthFromBtn = document.getElementById('nextMonthFrom');
  const prevMonthToBtn = document.getElementById('prevMonthTo');
  const nextMonthToBtn = document.getElementById('nextMonthTo');
  const leaveForm = document.getElementById('leaveForm');
  const reasonInput = document.getElementById('reason');
  const toast = document.getElementById('toast');

  // Initialize calendars
  updateCalendar(fromCalendarDays, currentFromMonth, 'from');
  updateCalendar(toCalendarDays, currentToMonth, 'to');
  updateMonthDisplay(currentMonthFromEl, currentFromMonth);
  updateMonthDisplay(currentMonthToEl, currentToMonth);

  // Event listeners for month navigation
  prevMonthFromBtn.addEventListener('click', () => {
    currentFromMonth.setMonth(currentFromMonth.getMonth() - 1);
    updateCalendar(fromCalendarDays, currentFromMonth, 'from');
    updateMonthDisplay(currentMonthFromEl, currentFromMonth);
  });

  nextMonthFromBtn.addEventListener('click', () => {
    currentFromMonth.setMonth(currentFromMonth.getMonth() + 1);
    updateCalendar(fromCalendarDays, currentFromMonth, 'from');
    updateMonthDisplay(currentMonthFromEl, currentFromMonth);
  });

  prevMonthToBtn.addEventListener('click', () => {
    currentToMonth.setMonth(currentToMonth.getMonth() - 1);
    updateCalendar(toCalendarDays, currentToMonth, 'to');
    updateMonthDisplay(currentMonthToEl, currentToMonth);
  });

  nextMonthToBtn.addEventListener('click', () => {
    currentToMonth.setMonth(currentToMonth.getMonth() + 1);
    updateCalendar(toCalendarDays, currentToMonth, 'to');
    updateMonthDisplay(currentMonthToEl, currentToMonth);
  });

  // ✅ Form submission with AJAX
  leaveForm.addEventListener('submit', function(e) {
    e.preventDefault();

    if (!fromDate) {
      showToast('Error', 'Please select a start date for your leave', 'error');
      return;
    }

    if (!reasonInput.value.trim()) {
      showToast('Error', 'Please provide a reason for your leave', 'error');
      return;
    }

    const fromDateStr = formatDate(fromDate);
    const toDateStr = toDate ? formatDate(toDate) : fromDateStr;

    fetch("/submit-leave/", {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "X-CSRFToken": getCookie("csrftoken"),
      },
      body: JSON.stringify({
        from_date: fromDateStr,
        to_date: toDateStr,
        reason: reasonInput.value.trim()
      })
    })
    .then(res => res.json())
    .then(data => {
      showToast('Success', data.message, 'success');
      fromDate = null;
      toDate = null;
      reasonInput.value = '';
      updateCalendar(fromCalendarDays, currentFromMonth, 'from');
      updateCalendar(toCalendarDays, currentToMonth, 'to');
    })
    .catch(err => {
      showToast('Error', 'Something went wrong. Try again.', 'error');
      console.error(err);
    });
  });

  // 🔐 CSRF helper function
  function getCookie(name) {
    let cookieValue = null;
    if (document.cookie && document.cookie !== '') {
      const cookies = document.cookie.split(';');
      for (let i = 0; i < cookies.length; i++) {
        const cookie = cookies[i].trim();
        if (cookie.substring(0, name.length + 1) === (name + '=')) {
          cookieValue = decodeURIComponent(cookie.substring(name.length + 1));
          break;
        }
      }
    }
    return cookieValue;
  }

  // Calendar rendering functions
  function updateCalendar(calendarEl, date, calendarType) {
    calendarEl.innerHTML = '';
    const year = date.getFullYear();
    const month = date.getMonth();
    const firstDay = new Date(year, month, 1).getDay();
    const daysInMonth = new Date(year, month + 1, 0).getDate();
    for (let i = 0; i < firstDay; i++) {
      const emptyDay = document.createElement('button');
      emptyDay.disabled = true;
      emptyDay.classList.add('disabled');
      calendarEl.appendChild(emptyDay);
    }

    const today = new Date();
    today.setHours(0, 0, 0, 0);

    for (let day = 1; day <= daysInMonth; day++) {
      const dayBtn = document.createElement('button');
      dayBtn.textContent = day;
      dayBtn.type = 'button';

      const currentDate = new Date(year, month, day);
      currentDate.setHours(0, 0, 0, 0);

      if (currentDate.getTime() === today.getTime()) dayBtn.classList.add('today');
      if (fromDate && currentDate.getTime() === fromDate.getTime()) dayBtn.classList.add('selected');
      if (toDate && currentDate.getTime() === toDate.getTime()) dayBtn.classList.add('selected');
      if (fromDate && toDate && currentDate > fromDate && currentDate < toDate) dayBtn.classList.add('in-range');

      if (currentDate < today) {
        dayBtn.disabled = true;
        dayBtn.classList.add('disabled');
      } else {
        dayBtn.addEventListener('click', () => {
          if (calendarType === 'from') {
            fromDate = new Date(year, month, day);
            if (toDate && toDate < fromDate) toDate = null;
          } else {
            if (fromDate) {
              toDate = new Date(year, month, day);
              if (toDate < fromDate) [fromDate, toDate] = [toDate, fromDate];
            }
          }
          updateCalendar(fromCalendarDays, currentFromMonth, 'from');
          updateCalendar(toCalendarDays, currentToMonth, 'to');
        });
      }

      calendarEl.appendChild(dayBtn);
    }
  }

  function updateMonthDisplay(element, date) {
    const monthNames = ['January', 'February', 'March', 'April', 'May', 'June',
                        'July', 'August', 'September', 'October', 'November', 'December'];
    element.textContent = `${monthNames[date.getMonth()]} ${date.getFullYear()}`;
  }

  function formatDate(date) {
    if (!date) return '';
    const day = date.getDate().toString().padStart(2, '0');
    const month = (date.getMonth() + 1).toString().padStart(2, '0');
    const year = date.getFullYear();
    return `${year}-${month}-${day}`; // Format for Django (YYYY-MM-DD)
  }

  function showToast(title, message, type) {
    const toastTitle = document.querySelector('.toast-title');
    const toastMessage = document.querySelector('.toast-message');
    toastTitle.textContent = title;
    toastMessage.textContent = message;
    toast.className = `toast show ${type}`;
    setTimeout(() => {
      toast.className = 'toast';
    }, 5000);
  }
});
