from datetime import date, timedelta
from django.shortcuts import render, redirect, get_object_or_404
from django.http import HttpResponse, JsonResponse, StreamingHttpResponse
from django.contrib.auth.hashers import make_password, check_password
from .forms import StudentForm
from .models import Student, Attendance, PasswordReset
from collections import defaultdict
from django.contrib import messages
from django.contrib.auth import login
from .utils import export_attendance_pdf
import calendar
import pandas as pd
import cv2
import numpy as np
import os
import threading
import time
from keras_facenet import FaceNet
from mtcnn import MTCNN
from django.utils import timezone
from django.contrib.auth.models import User
from django.core.mail import EmailMessage
from django.urls import reverse
from django.conf import settings
import datetime
from django.views.decorators.csrf import csrf_exempt
from .models import LeaveRequest
from django.views.decorators.http import require_POST
import json
# In-memory capture state
capture_progress = defaultdict(lambda: {"count": 0, "done": False})

# Load models
embedder = FaceNet()
detector = MTCNN()

# ⬛⬛⬛ AUTH / FORM VIEWS ⬛⬛⬛
def student_login_view(request):
    if request.method == 'POST':
        email = request.POST.get('email')
        password = request.POST.get('password')

        try:
            student = Student.objects.get(email=email)
            if check_password(password, student.password):
                request.session['student_id'] = student.student_id
                request.session['student_name'] = student.name
                return redirect('dashboard')
            else:
                messages.error(request, "❌ Incorrect password.")
        except Student.DoesNotExist:
            messages.error(request, "❌ Email not found.")

    return render(request, 'attendance/login.html')

def attendance_report_view(request):
    if 'student_id' not in request.session:
        return redirect('login_view')

    student_id = request.session['student_id']
    student = get_object_or_404(Student, student_id=student_id)

    today = date.today()
    month = int(request.GET.get('month', today.month))
    year = int(request.GET.get('year', today.year))

    last_day = min(date(year, month, calendar.monthrange(year, month)[1]), today)
    all_dates = [date(year, month, day) for day in range(1, last_day.day + 1)]

    # Fetch all attendance records for this student in the selected month
    attendance_records = Attendance.objects.filter(
        student=student,
        date__year=year,
        date__month=month
    ).values('date', 'check_in', 'check_out')

    # Map dates to their attendance info
    attendance_map = {rec['date']: rec for rec in attendance_records}

    # Build attendance_status list for template and JSON
    attendance_status = []
    for d in all_dates:
        record = attendance_map.get(d)
        if record:
            status = 'Present' if record['check_in'] else 'Absent'
            check_in = record['check_in'].strftime("%H:%M:%S") if record['check_in'] else None
            check_out = record['check_out'].strftime("%H:%M:%S") if record['check_out'] else None
        else:
            status = 'Absent'
            check_in = None
            check_out = None

        attendance_status.append({
            'date': d.strftime("%Y-%m-%d"),
            'status': status,
            'check_in': check_in,
            'check_out': check_out
        })

    total_present = sum(1 for r in attendance_status if r['status'] == 'Present')
    total_absent = sum(1 for r in attendance_status if r['status'] == 'Absent')

    export_format = request.GET.get('format')
    if export_format in ['pdf', 'excel']:
        df = pd.DataFrame(attendance_status)
        if export_format == 'excel':
            response = HttpResponse(content_type='application/vnd.ms-excel')
            response['Content-Disposition'] = f'attachment; filename=attendance_{year}_{month}.xlsx'
            df.to_excel(response, index=False)
            return response
        elif export_format == 'pdf':
            return export_attendance_pdf(request, student, attendance_status, month, year)

    return render(request, 'attendance/attendance_report.html', {
        'student': student,
        'attendance_status': attendance_status,
        'selected_month': month,
        'selected_year': year,
        'year_range': list(range(today.year - 5, today.year + 1)),
        'month_list': list(range(1, 13)),
        'total_present': total_present,
        'total_absent': total_absent
    })

def ForgotPassword(request):
    if request.method == 'POST':
        email = request.POST.get('email')
        try:
            student = Student.objects.get(email=email)
            reset = PasswordReset.objects.create(user=student)
            reset_url = request.build_absolute_uri(
                reverse('reset-password', kwargs={'reset_id': reset.reset_id})
            )
            email_body = f'Reset your password using the link below:\n\n{reset_url}'
            EmailMessage(
                'Reset your password',
                email_body,
                settings.EMAIL_HOST_USER,
                [email]
            ).send()
            return redirect('password-reset-sent', reset_id=reset.reset_id)
        except Student.DoesNotExist:
            messages.error(request, f"No user with email '{email}' found")
            return redirect('forgot-password')
    return render(request, 'forgot_password.html')

def ResetPassword(request, reset_id):
    try:
        reset = PasswordReset.objects.get(reset_id=reset_id)
    except PasswordReset.DoesNotExist:
        messages.error(request, 'Invalid reset id')
        return redirect('forgot-password')

    if request.method == 'POST':
        password = request.POST.get('password')
        confirm_password = request.POST.get('confirm_password')
        errors = False

        if password != confirm_password:
            messages.error(request, 'Passwords do not match')
            errors = True
        if len(password) < 5:
            messages.error(request, 'Password must be at least 5 characters long')
            errors = True
        if timezone.now() > reset.created_when + datetime.timedelta(minutes=10):
            reset.delete()
            messages.error(request, 'Reset link has expired')
            errors = True

        if not errors:
            user = reset.user
            user.password = make_password(password)
            user.save()
            reset.delete()
            messages.success(request, 'Password reset. Proceed to login')
            return redirect('login_view')

        return redirect('reset-password', reset_id=reset_id)

    return render(request, 'reset_password.html')

def PasswordResetSent(request, reset_id):
    if PasswordReset.objects.filter(reset_id=reset_id).exists():
        return render(request, 'password_reset_sent.html')
    else:
        messages.error(request, 'Invalid reset id')
        return redirect('forgot-password')

def course_view(request):
    return render(request, 'attendance/course.html')

def logout_view(request):
    request.session.flush()
    return redirect('login_view')

def leave_view(request):
    return render(request, 'attendance/leave.html')

def dashboard_view(request):
    if 'student_id' not in request.session:
        return redirect('login_view')
    return render(request, 'attendance/dashboard.html', {
        'student_name': request.session.get('student_name')
    })

def login_view(request):
    return render(request, 'attendance/login.html')

def signup_view(request):
    form = StudentForm()
    return render(request, 'attendance/signup.html', {'form': form})

def register_view(request):
    if request.method == 'POST':
        form = StudentForm(request.POST)
        if form.is_valid():
            student = form.save(commit=False)
            student.password = make_password(form.cleaned_data['password'])
            student.save()
            return redirect('register_face', student_id=student.student_id)
        return JsonResponse({'error': form.errors}, status=400)
    return render(request, 'attendance/signup.html', {'form': StudentForm()})

# ⬛⬛⬛ MJPEG STREAM VIEW ⬛⬛⬛
def gen_frames():
    cap = cv2.VideoCapture(0)
    if not cap.isOpened():
        print("❌ Failed to open camera stream.")
        return

    while True:
        success, frame = cap.read()
        if not success:
            continue

        ret, buffer = cv2.imencode('.jpg', frame)
        if not ret:
            continue
        frame_bytes = buffer.tobytes()

        yield (b'--frame\r\n'
               b'Content-Type: image/jpeg\r\n\r\n' + frame_bytes + b'\r\n\r\n')

    cap.release()

def camera_feed(request):
    return StreamingHttpResponse(gen_frames(),
        content_type='multipart/x-mixed-replace; boundary=frame')

# ⬛⬛⬛ FACE REGISTRATION VIEWS ⬛⬛⬛
def register_face(request, student_id):
    student = get_object_or_404(Student, student_id=student_id)
    return render(request, 'attendance/register_face.html', {'student_id': student_id})

@csrf_exempt
def start_capture_api(request, student_id):
    student = get_object_or_404(Student, student_id=student_id)
    name = student.name
    student_folder = os.path.join("faces", str(student_id))
    os.makedirs(student_folder, exist_ok=True)

    capture_progress[student_id] = {"count": 0, "done": False}
    captured_embeddings = []

    def capture_thread():
        cap = cv2.VideoCapture(0)
        if not cap.isOpened():
            print("❌ Failed to open stream for capture.")
            return

        count = 0
        while count < 10:
            success, frame = cap.read()
            if not success:
                continue

            try:
                rgb_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                faces = detector.detect_faces(rgb_frame)

                for face in faces:
                    x, y, w, h = face['box']
                    if w < 80 or h < 80:
                        continue

                    face_rgb = rgb_frame[y:y+h, x:x+w]
                    face_rgb = cv2.resize(face_rgb, (160, 160))

                    embedding = embedder.embeddings([face_rgb])[0]
                    captured_embeddings.append(embedding)

                    img_name = f"{name}_{count+1}.jpg"
                    save_path = os.path.join(student_folder, img_name)
                    cv2.imwrite(save_path, frame[y:y+h, x:x+w])

                    count += 1
                    capture_progress[student_id]['count'] = count
                    print(f"✅ Captured {count}/10")

                    time.sleep(0.5)
                    break
            except Exception as e:
                print(f"⚠️ Error during capture: {e}")
                continue

        cap.release()

        if captured_embeddings:
            mean_embedding = np.mean(captured_embeddings, axis=0)
            np.save(os.path.join(student_folder, f"{student_id}_embedding.npy"), mean_embedding)
            print("✅ Embedding saved.")

        capture_progress[student_id]['done'] = True
        print("✅ Face capture complete.")

    threading.Thread(target=capture_thread).start()
    return JsonResponse({'status': 'started'})

def check_capture_progress(request, student_id):
    return JsonResponse(capture_progress.get(student_id, {"count": 0, "done": False}))

def face_success(request, student_id):
    student = Student.objects.get(student_id=student_id)
    today = date.today()
    now = timezone.now()

    # Latest attendance entry for today
    last_record = (
        Attendance.objects
        .filter(student=student, date=today)
        .order_by('-id')
        .first()
    )

    # Case 1: no record today → first CHECK-IN
    if last_record is None:
        Attendance.objects.create(
            student=student,
            date=today,
            check_in=now
        )
        status = "Check-In Successful"

    # Case 2: open session → CHECK-OUT
    elif last_record.check_out is None:
        last_record.check_out = now
        last_record.save()
        status = "Check-Out Successful"

    # Case 3: last session closed → start NEW CHECK-IN
    else:
        Attendance.objects.create(
            student=student,
            date=today,
            check_in=now
        )
        status = "Check-In Successful"

    return render(request, "attendance/face_success.html", {
        "student": student,
        "status": status,
        "time": now,
    })


def cancel_capture(request, student_id):
    capture_progress[student_id] = {"count": 0, "done": True}
    return JsonResponse({'status': 'cancelled'})

@csrf_exempt
@require_POST
def submit_leave(request):
    try:
        print("📥 POST request received at /submit-leave/")
        print("📦 Raw body:", request.body)

        data = json.loads(request.body)
        student_id = request.session.get('student_id')
        print("🆔 Session student_id:", student_id)

        if not student_id:
            print("❌ No student_id found in session.")
            return JsonResponse({'error': 'Unauthorized'}, status=401)

        try:
            student = Student.objects.get(student_id=student_id)
        except Student.DoesNotExist:
            print("❌ Student not found for ID:", student_id)
            return JsonResponse({'error': 'Student not found'}, status=404)

        from_date = data.get('from_date')
        to_date = data.get('to_date') or from_date
        reason = data.get('reason')

        print("📅 From:", from_date)
        print("📅 To:", to_date)
        print("📝 Reason:", reason)

        leave = LeaveRequest.objects.create(
            student=student,
            from_date=from_date,
            to_date=to_date,
            reason=reason
        )
        print("✅ LeaveRequest created:", leave)

        return JsonResponse({'message': 'Leave application submitted! ✅'})

    except Exception as e:
        print("🔥 Exception:", e)
        return JsonResponse({'error': str(e)}, status=500)