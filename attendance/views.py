from datetime import date, datetime, timedelta
from django.core.exceptions import ValidationError
from io import BytesIO
from django.shortcuts import render, redirect, get_object_or_404
from django.http import HttpResponse, JsonResponse, StreamingHttpResponse
from django.contrib.auth.hashers import make_password, check_password
from .models import Student, Attendance, PasswordResetOTP, StudentTodo
from collections import defaultdict
from django.contrib import messages
from django.contrib.auth import login
from .utils import export_attendance_pdf, build_monthly_attendance_status
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
from django.views.decorators.csrf import csrf_exempt
from .models import LeaveRequest
from django.views.decorators.http import require_POST, require_http_methods
import json
from django.db.models import Min, Max
import logging
from smtplib import SMTPException
from .forms import (
    StudentForm,
    LeaveRequestForm,
    PasswordResetRequestForm,
    OTPVerificationForm,
    PasswordResetWithOTPForm,
)

# In-memory capture state
capture_progress = defaultdict(lambda: {"count": 0, "done": False})
logger = logging.getLogger(__name__)

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

    today = timezone.localdate()
    month = int(request.GET.get('month', today.month))
    year = int(request.GET.get('year', today.year))

    report = build_monthly_attendance_status(student, month=month, year=year)
    attendance_status = report["attendance_status"]

    # Export Logic
    export_format = request.GET.get('format')
    if export_format == 'excel':
        export_rows = [
            {
                'Date': row['date'],
                'Day': row['day'],
                'Check-In': row['check_in'],
                'Check-Out': row['check_out'],
                'Status': row['status'],
            }
            for row in attendance_status
        ]
        df = pd.DataFrame(export_rows)
        buffer = BytesIO()
        df.to_excel(buffer, index=False, engine='openpyxl')
        buffer.seek(0)
        response = HttpResponse(
            buffer.getvalue(),
            content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
        )
        response['Content-Disposition'] = f'attachment; filename=attendance_{year}_{month}.xlsx'
        return response
    
    elif export_format == 'pdf':
        # Ensure your utils.py accepts the new status field in attendance_status
        return export_attendance_pdf(request, student, attendance_status, month, year)

    return render(request, 'attendance/attendance_report.html', {
        'student': student,
        'attendance_status': attendance_status,
        'selected_month': month,
        'selected_year': year,
        'year_range': list(range(today.year - 5, today.year + 1)),
        'month_list': list(range(1, 13)),
        'total_present': report['total_present'],
        'total_absent': report['total_absent'],
        'total_leave': report['total_leave'],
    })

def _send_password_reset_otp_email(student, otp):
    subject = "Your password reset OTP"
    expiry_minutes = getattr(settings, "PASSWORD_RESET_OTP_EXPIRY_MINUTES", 10)
    body = (
        f"Hi {student.name},\n\n"
        f"Use this OTP to reset your password: {otp}\n"
        f"This OTP expires in {expiry_minutes} minutes.\n\n"
        "If you did not request this, please ignore this email."
    )
    from_email = (
        getattr(settings, "DEFAULT_FROM_EMAIL", None)
        or getattr(settings, "EMAIL_HOST_USER", None)
        or "no-reply@example.com"
    )
    EmailMessage(subject, body, from_email, [student.email]).send(fail_silently=False)


def forgot_password_view(request):
    form = PasswordResetRequestForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        email = form.cleaned_data["email"]
        student = Student.objects.filter(email=email).first()

        # Avoid account enumeration by returning the same success page.
        if student:
            otp_obj, raw_otp = PasswordResetOTP.generate_for_user(student)
            try:
                _send_password_reset_otp_email(student, raw_otp)
                request.session["password_reset_otp_id"] = otp_obj.id
            except SMTPException:
                otp_obj.delete()
                logger.exception("Failed to send password reset OTP email.")
                messages.error(request, "Email service is unavailable. Please try again shortly.")
                return redirect("forgot-password")

        messages.success(request, "If this email is registered, an OTP has been sent.")
        return redirect("verify-password-otp")
    elif request.method == "POST":
        for field_errors in form.errors.values():
            for error in field_errors:
                messages.error(request, error)

    return render(request, "attendance/forgot_password.html", {"form": form})


def resend_password_otp_view(request):
    if request.method != "POST":
        return redirect("forgot-password")

    otp_id = request.session.get("password_reset_otp_id")
    otp_obj = PasswordResetOTP.objects.filter(id=otp_id, is_used=False).select_related("user").first()
    if not otp_obj or otp_obj.is_expired():
        messages.error(request, "Reset session expired. Please request a new OTP.")
        request.session.pop("password_reset_otp_id", None)
        request.session.pop("password_reset_verified", None)
        return redirect("forgot-password")

    new_otp_obj, raw_otp = PasswordResetOTP.generate_for_user(otp_obj.user)
    try:
        _send_password_reset_otp_email(otp_obj.user, raw_otp)
        request.session["password_reset_otp_id"] = new_otp_obj.id
        request.session["password_reset_verified"] = False
        messages.success(request, "A new OTP has been sent to your email.")
        return redirect("verify-password-otp")
    except SMTPException:
        new_otp_obj.delete()
        logger.exception("Failed to resend password reset OTP email.")
        messages.error(request, "Email service is unavailable. Please try again shortly.")
        return redirect("forgot-password")


def verify_password_otp_view(request):
    otp_id = request.session.get("password_reset_otp_id")
    otp_obj = PasswordResetOTP.objects.filter(id=otp_id).first()
    if not otp_obj or otp_obj.is_used or otp_obj.is_expired():
        messages.error(request, "Reset session expired. Please request a new OTP.")
        request.session.pop("password_reset_otp_id", None)
        request.session.pop("password_reset_verified", None)
        return redirect("forgot-password")

    form = OTPVerificationForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        raw_otp = form.cleaned_data["otp"]
        if otp_obj.verify_otp(raw_otp):
            request.session["password_reset_verified"] = True
            messages.success(request, "OTP verified. Set your new password.")
            return redirect("reset-password")

        otp_obj.attempts += 1
        if otp_obj.attempts >= 5:
            otp_obj.is_used = True
            otp_obj.save(update_fields=["attempts", "is_used"])
            messages.error(request, "Too many invalid attempts. Request a new OTP.")
            request.session.pop("password_reset_otp_id", None)
            request.session.pop("password_reset_verified", None)
            return redirect("forgot-password")
        otp_obj.save(update_fields=["attempts"])
        messages.error(request, "Invalid OTP.")
    elif request.method == "POST":
        for field_errors in form.errors.values():
            for error in field_errors:
                messages.error(request, error)

    return render(
        request,
        "attendance/verify_otp.html",
        {"form": form, "email": otp_obj.user.email},
    )


def reset_password_view(request):
    otp_id = request.session.get("password_reset_otp_id")
    is_verified = request.session.get("password_reset_verified", False)
    otp_obj = PasswordResetOTP.objects.filter(id=otp_id, is_used=False).select_related("user").first()
    if not otp_obj or otp_obj.is_expired() or not is_verified:
        messages.error(request, "Please verify OTP first.")
        return redirect("forgot-password")

    form = PasswordResetWithOTPForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        student = otp_obj.user
        student.password = make_password(form.cleaned_data["password"])
        student.save(update_fields=["password"])
        otp_obj.is_used = True
        otp_obj.save(update_fields=["is_used"])

        request.session.pop("password_reset_otp_id", None)
        request.session.pop("password_reset_verified", None)
        messages.success(request, "Password reset successful. Please log in.")
        return redirect("login_view")
    elif request.method == "POST":
        for field_errors in form.errors.values():
            for error in field_errors:
                messages.error(request, error)

    return render(request, "attendance/reset_password.html", {"form": form})

def course_view(request):
    return render(request, 'attendance/course.html')

def logout_view(request):
    request.session.flush()
    return redirect('login_view')

def leave_view(request):
    return render(request, 'attendance/leave.html')

def leave_history_view(request):
    if 'student_id' not in request.session:
        return redirect('login_view')

    student_id = request.session['student_id']
    student = get_object_or_404(Student, student_id=student_id)

    leave_requests = (
        LeaveRequest.objects
        .filter(student=student)
        .order_by('-submitted_at')
    )

    return render(request, 'attendance/leave_history.html', {
        'student': student,
        'student_name': request.session.get('student_name', student.name),
        'leave_requests': leave_requests,
    })

def edit_leave_request_view(request, leave_id):
    if 'student_id' not in request.session:
        return redirect('login_view')

    student_id = request.session['student_id']
    student = get_object_or_404(Student, student_id=student_id)
    leave_request = get_object_or_404(LeaveRequest, id=leave_id, student=student)

    if leave_request.status != 'pending':
        messages.error(request, "You can only edit pending leave requests.")
        return redirect('leave_history')

    if request.method == 'POST':
        form = LeaveRequestForm(request.POST, instance=leave_request)
        if form.is_valid():
            form.save()
            messages.success(request, "Leave request updated.")
            return redirect('leave_history')
    else:
        form = LeaveRequestForm(instance=leave_request)

    return render(request, 'attendance/edit_leave_request.html', {
        'student': student,
        'student_name': request.session.get('student_name', student.name),
        'form': form,
        'leave_request': leave_request,
    })

@require_POST
def delete_leave_request_view(request, leave_id):
    if 'student_id' not in request.session:
        return redirect('login_view')

    student_id = request.session['student_id']
    student = get_object_or_404(Student, student_id=student_id)
    leave_request = get_object_or_404(LeaveRequest, id=leave_id, student=student)

    if leave_request.status != 'pending':
        messages.error(request, "You can only delete pending leave requests.")
        return redirect('leave_history')

    leave_request.delete()
    messages.success(request, "Leave request deleted.")
    return redirect('leave_history')

def _get_logged_in_student(request):
    if 'student_id' not in request.session:
        return None
    return get_object_or_404(Student, student_id=request.session['student_id'])


def _serialize_todo(todo):
    return {
        'id': todo.id,
        'text': todo.text,
        'done': todo.is_done,
    }


@require_http_methods(['GET', 'POST'])
def student_todos_api(request):
    student = _get_logged_in_student(request)
    if not student:
        return JsonResponse({'error': 'Unauthorized'}, status=401)

    if request.method == 'GET':
        todos = StudentTodo.objects.filter(student=student)
        return JsonResponse({'todos': [_serialize_todo(t) for t in todos]})

    try:
        data = json.loads(request.body.decode('utf-8'))
    except (json.JSONDecodeError, UnicodeDecodeError):
        return JsonResponse({'error': 'Invalid JSON'}, status=400)

    text = (data.get('text') or '').strip()
    if not text:
        return JsonResponse({'error': 'Task text is required'}, status=400)
    if len(text) > 200:
        return JsonResponse({'error': 'Task text must be 200 characters or fewer'}, status=400)

    todo = StudentTodo.objects.create(student=student, text=text)
    return JsonResponse({'todo': _serialize_todo(todo)}, status=201)


@require_http_methods(['PATCH', 'DELETE'])
def student_todo_detail_api(request, todo_id):
    student = _get_logged_in_student(request)
    if not student:
        return JsonResponse({'error': 'Unauthorized'}, status=401)

    todo = get_object_or_404(StudentTodo, id=todo_id, student=student)

    if request.method == 'DELETE':
        todo.delete()
        return JsonResponse({'success': True})

    try:
        data = json.loads(request.body.decode('utf-8'))
    except (json.JSONDecodeError, UnicodeDecodeError):
        return JsonResponse({'error': 'Invalid JSON'}, status=400)

    if 'done' in data:
        todo.is_done = bool(data['done'])
        todo.save(update_fields=['is_done', 'updated_at'])

    return JsonResponse({'todo': _serialize_todo(todo)})


def dashboard_view(request):
    if 'student_id' not in request.session:
        return redirect('login_view')

    student = get_object_or_404(Student, student_id=request.session['student_id'])
    today = timezone.localdate()
    month = int(request.GET.get('month', today.month))
    year = int(request.GET.get('year', today.year))

    report = build_monthly_attendance_status(student, month=month, year=year)

    return render(request, 'attendance/dashboard.html', {
        'student_name': request.session.get('student_name', student.name),
        'student': student,
        'attendance_status': report['attendance_status'],
        'total_present': report['total_present'],
        'total_absent': report['total_absent'],
        'total_leave': report['total_leave'],
        'selected_month': month,
        'selected_year': year,
        'year_range': list(range(today.year - 5, today.year + 1)),
        'month_list': list(range(1, 13)),
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
            # Frontend signup uses fetch() and expects JSON.
            # When the JS sends the CSRF token as a header, treat as AJAX.
            if request.headers.get('X-CSRFToken'):
                return JsonResponse({
                    'success': 'Registration successful!',
                    'redirect': reverse('register_face', kwargs={'student_id': student.student_id})
                })
            return redirect('register_face', student_id=student.student_id)
        # Fetch() expects a JSON error payload.
        return JsonResponse({'error': str(form.errors)}, status=400)
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

    capture_progress[student_id] = {"count": 0, "done": False, "cancelled": False}
    captured_embeddings = []

    def capture_thread():
        cap = cv2.VideoCapture(0)
        if not cap.isOpened():
            print("❌ Failed to open stream for capture.")
            return

        count = 0
        while count < 10 and not capture_progress[student_id].get("cancelled", False):
            success, frame = cap.read()
            if not success:
                continue

            try:
                rgb_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                faces = detector.detect_faces(rgb_frame)

                for face in faces:
                    if capture_progress[student_id].get("cancelled", False):
                        break

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

        if captured_embeddings and not capture_progress[student_id].get("cancelled", False):
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
    """Shown after face registration completes. Does not record attendance."""
    student = get_object_or_404(Student, student_id=student_id)
    return render(request, "attendance/face_success.html", {
        "student": student,
        "time": timezone.now(),
    })


def cancel_capture(request, student_id):
    # Signal the background thread to stop and avoid saving embeddings/images.
    capture_progress[student_id] = {"count": 0, "done": True, "cancelled": True}
    return JsonResponse({'status': 'cancelled'})

MONTHLY_LEAVE_LIMIT = 2
MONTHLY_LEAVE_LIMIT_MESSAGE = (
    "You have already taken two leaves this month. "
    "Only 2 leave applications are allowed per month."
)


def _parse_leave_date(value):
    if isinstance(value, date):
        return value
    return datetime.strptime(value, "%Y-%m-%d").date()


def _monthly_leave_count(student, from_date):
    return LeaveRequest.objects.filter(
        student=student,
        from_date__month=from_date.month,
        from_date__year=from_date.year,
    ).count()


@csrf_exempt
@require_POST
def submit_leave(request):
    try:
        data = json.loads(request.body)
        student_id = request.session.get('student_id')

        if not student_id:
            return JsonResponse({'error': 'Unauthorized'}, status=401)

        try:
            student = Student.objects.get(student_id=student_id)
        except Student.DoesNotExist:
            return JsonResponse({'error': 'Student not found'}, status=404)

        from_date_raw = data.get('from_date')
        to_date_raw = data.get('to_date') or from_date_raw
        reason = (data.get('reason') or '').strip()
        category = data.get('category', 'other')

        if not from_date_raw:
            return JsonResponse({'error': 'Please select a start date.'}, status=400)
        if not reason:
            return JsonResponse({'error': 'Please provide a reason for your leave.'}, status=400)

        try:
            from_date = _parse_leave_date(from_date_raw)
            to_date = _parse_leave_date(to_date_raw)
        except (TypeError, ValueError):
            return JsonResponse({'error': 'Invalid date format.'}, status=400)

        if _monthly_leave_count(student, from_date) >= MONTHLY_LEAVE_LIMIT:
            return JsonResponse({'error': MONTHLY_LEAVE_LIMIT_MESSAGE}, status=400)

        leave = LeaveRequest(
            student=student,
            from_date=from_date,
            to_date=to_date,
            reason=reason,
            category=category,
        )
        try:
            leave.save()
        except ValidationError as exc:
            error_message = exc.messages[0] if getattr(exc, "messages", None) else str(exc)
            return JsonResponse({'error': error_message}, status=400)

        return JsonResponse({'message': 'Leave application submitted successfully.'})

    except json.JSONDecodeError:
        return JsonResponse({'error': 'Invalid request data.'}, status=400)
    except Exception as e:
        logger.exception("submit_leave failed")
        return JsonResponse({'error': 'Something went wrong. Please try again.'}, status=500)