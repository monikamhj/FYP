# attendance/signals.py
import os
import shutil
from django.db.models.signals import post_delete
from django.dispatch import receiver
from .models import Student
from django.db.models.signals import post_save
from django.dispatch import receiver

from .models import Attendance

@receiver(post_delete, sender=Student)
def delete_student_files(sender, instance, **kwargs):
    face_folder = os.path.join("faces", str(instance.student_id))
    if os.path.exists(face_folder):
        shutil.rmtree(face_folder)
        print(f"🗑️ Deleted folder: {face_folder}")

