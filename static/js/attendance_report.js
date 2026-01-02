document.addEventListener("DOMContentLoaded", function () {
  const calendar = document.getElementById("attendance-calendar");
  const statusData = JSON.parse(document.getElementById("attendance-data").textContent);

  // Get selected month and year from the form
  const monthSelect = document.getElementById('month');
  const yearSelect = document.getElementById('year');
  const month = parseInt(monthSelect.value); // 1-12
  const year = parseInt(yearSelect.value);

  // Create a map for fast lookup of attendance info by date
  const attendanceMap = {};
  statusData.forEach(record => {
    const dateKey = record.date;  // e.g. "2025-12-21"
    // always keep the latest record for that date
    attendanceMap[dateKey] = {
      date: dateKey,
      check_in: record.check_in,
      check_out: record.check_out,
      status: record.status
    };
  });

  // Calculate first day of the month and total days
  const firstDay = new Date(year, month - 1, 1).getDay(); // 0 = Sunday
  const totalDays = new Date(year, month, 0).getDate();

  // Build calendar HTML
  let html = '<table class="calendar-table"><thead><tr>';
  const days = ['Su', 'Mo', 'Tu', 'We', 'Th', 'Fr', 'Sa'];
  for (let d of days) html += `<th>${d}</th>`;
  html += '</tr></thead><tbody><tr>';

  // Empty cells before first day
  for (let i = 0; i < firstDay; i++) html += '<td></td>';

  // Days of the month
  for (let day = 1; day <= totalDays; day++) {
    const fullDate = `${year}-${String(month).padStart(2, '0')}-${String(day).padStart(2, '0')}`;
    const record = attendanceMap[fullDate];

    let checkInText = '';
    let checkOutText = '';

    if (record) {
      checkInText = record.check_in ? `<div class="check-time">In: ${record.check_in}</div>` : '';
      checkOutText = record.check_out ? `<div class="check-time">Out: ${record.check_out}</div>` : '';
    }

    html += `<td>
               <div class="day-number">${day}</div>
               ${checkInText}
               ${checkOutText}
             </td>`;

    if ((firstDay + day - 1) % 7 === 6) html += '</tr><tr>'; // new week
  }

  html += '</tr></tbody></table>';
  calendar.innerHTML = html;
});
