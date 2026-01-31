document.addEventListener("DOMContentLoaded", function () {
  const calendar = document.getElementById("attendance-calendar");
  const statusData = JSON.parse(document.getElementById("attendance-data").textContent);

  const monthSelect = document.getElementById('month');
  const yearSelect = document.getElementById('year');
  const month = parseInt(monthSelect.value);
  const year = parseInt(yearSelect.value);

  // 1. Nepali Public Holidays 2026 (Major Dates)
  const publicHolidays = {
    "01-11": "Prithvi Jayanti",
    "01-14": "Maghe Sankranti",
    "01-30": "Martyrs' Day",
    "02-15": "Maha Shivaratri",
    "02-19": "Prajatantra Diwas",
    "03-02": "Holi (Hilly)",
    "03-03": "Holi (Terai)",
    "04-14": "Nepali New Year",
    "05-01": "Labour Day",
    "09-19": "Constitution Day",
    "10-21": "Vijaya Dashami",
    "11-11": "Bhai Tika"
  };

  const attendanceMap = {};
  statusData.forEach(record => {
    attendanceMap[record.date] = record;
  });

  const firstDay = new Date(year, month - 1, 1).getDay();
  const totalDays = new Date(year, month, 0).getDate();

  let html = '<table class="calendar-table"><thead><tr>';
  const days = ['Su', 'Mo', 'Tu', 'We', 'Th', 'Fr', 'Sa'];
  days.forEach(d => html += `<th>${d}</th>`);
  html += '</tr></thead><tbody><tr>';

  for (let i = 0; i < firstDay; i++) html += '<td></td>';

  for (let day = 1; day <= totalDays; day++) {
    const dateObj = new Date(year, month - 1, day);
    const dayOfWeek = dateObj.getDay(); // 6 is Saturday
    const dateStr = `${year}-${String(month).padStart(2, '0')}-${String(day).padStart(2, '0')}`;
    const holidayKey = `${String(month).padStart(2, '0')}-${String(day).padStart(2, '0')}`;
    
    const record = attendanceMap[dateStr];
    let cellClass = "";
    let statusText = "";

    // Priority Logic: Holiday > Saturday > Leave > Attendance
    if (publicHolidays[holidayKey]) {
      cellClass = "cal-holiday";
      statusText = `<div class="status-label">${publicHolidays[holidayKey]}</div>`;
    } else if (dayOfWeek === 6) {
      cellClass = "cal-saturday";
      statusText = `<div class="status-label">Holiday</div>`;
    } else if (record && record.status === "On Leave") {
      cellClass = "cal-leave";
      statusText = `<div class="status-label">On Leave</div>`;
    } else if (record) {
      cellClass = record.status.toLowerCase(); // 'present' or 'absent'
    }

    let checkInText = (record && record.check_in && record.check_in !== "—") ? `<div class="check-time">In: ${record.check_in}</div>` : '';
    let checkOutText = (record && record.check_out && record.check_out !== "—") ? `<div class="check-time">Out: ${record.check_out}</div>` : '';

    html += `<td class="${cellClass}">
               <div class="day-number">${day}</div>
               ${statusText}
               ${checkInText}
               ${checkOutText}
             </td>`;

    if ((firstDay + day - 1) % 7 === 6) html += '</tr><tr>';
  }

  html += '</tr></tbody></table>';
  calendar.innerHTML = html;
});