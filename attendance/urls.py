from django.urls import path
from . import views
from .views import submit_leave

urlpatterns = [
    path('leave/', views.leave_view, name='leave_view'),
    path('dashboard/', views.dashboard_view, name='dashboard'),
    path('login/', views.student_login_view, name='login_view'),
    path('signup/', views.signup_view, name='signup_view'),
    path('register/', views.register_view, name='register_view'),
    path('register/face/<int:student_id>/', views.register_face, name='register_face'),
    path('camera_feed/', views.camera_feed, name='camera_feed'),
    path('start_capture_api/<int:student_id>/', views.start_capture_api, name='start_capture_api'),
    path('check_progress/<int:student_id>/', views.check_capture_progress, name='check_progress'),
    path('face_success/<int:student_id>/', views.face_success, name='face_success'),
    path('logout/', views.logout_view, name='logout'),
    path('course/', views.course_view, name='course'),
    path('report/', views.attendance_report_view, name='attendance_report'),
    path('forgot-password/', views.ForgotPassword, name='forgot-password'),
    path('password-reset-sent/<str:reset_id>/', views.PasswordResetSent, name='password-reset-sent'),
    path('reset-password/<str:reset_id>/', views.ResetPassword, name='reset-password'),
    path('cancel_capture/<int:student_id>/', views.cancel_capture, name='cancel_capture'),
    path('submit-leave/', submit_leave, name='submit_leave'),
]