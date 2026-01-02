import cv2
import numpy as np
import os
import sys
import django
from keras_facenet import FaceNet
from datetime import datetime
from mtcnn import MTCNN
from django.core.exceptions import ValidationError, ObjectDoesNotExist
import random
import time

# Django Setup
sys.path.insert(0, "/Users/monikamaharjan/Documents/FYP/ex/attendance_system")

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "attendance_system.settings")
django.setup()

from attendance.models import Student

# Constants
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
KNOWN_FACES_DIR = os.path.join(BASE_DIR, "../faces/")

# Load modelscap
embedder = FaceNet()
detector = MTCNN()

# Get student details
if len(sys.argv) < 8:
    print("Error : All fields are required (name, email, phone, address, password, dob, course)")
    sys.exit(1)

name, email, phone, address, password, dob, course = sys.argv[1:8]

# Generate ID
def generate_student_id():
    while True:
        student_id = random.randint(1000, 9999)
        try:
            Student.objects.get(student_id=student_id)
        except ObjectDoesNotExist:
            return student_id

student_id = generate_student_id()

# Parse DOB
try:
    dob_date = datetime.strptime(dob, "%Y-%m-%d").date()
except ValueError:
    print("❌ Invalid date format. Use YYYY-MM-DD.")
    sys.exit(1)

# Create student
try:
    student, created = Student.objects.get_or_create(
        student_id=student_id,
        defaults={
            'name': name,
            'email': email,
            'phone_number': phone,
            'address': address,
            'password': password,
            'dob': dob_date,
            'course': course
        }
    )
    if not created:
        print("⚠️ Student with this ID already exists.")
except ValidationError as e:
    print(f"❌ Validation Error: {e}")
    sys.exit(1)

# Folder
student_folder = os.path.join(KNOWN_FACES_DIR, str(student_id))
os.makedirs(student_folder, exist_ok=True)

# Video stream
cap = cv2.VideoCapture(0)
if not cap.isOpened():
    print("❌ Failed to open video stream.")
    sys.exit(1)

# Helper: Check brightness
def is_too_dark(frame, threshold=40):
    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    brightness = np.mean(gray)
    return brightness < threshold

# Start capture
captured_embeddings = []
print("⏳ Starting automatic face capture. Please look at the camera...")
start_time = time.time()

while len(captured_embeddings) < 10:
    ret, frame = cap.read()
    if not ret:
        continue

    if is_too_dark(frame):
        cv2.putText(frame, "💡 Increase Lighting", (10, 30), cv2.FONT_HERSHEY_SIMPLEX,
                    0.8, (0, 0, 255), 2)
        cv2.imshow("Registering Face", frame)
        if cv2.waitKey(1) & 0xFF == ord("q"):
            break
        continue

    rgb_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
    faces = detector.detect_faces(rgb_frame)

    for face in faces:
        x, y, w, h = face['box']
        x, y = max(0, x), max(0, y)
        if w < 80 or h < 80:
            continue

        face_rgb = rgb_frame[y:y + h, x:x + w]
        face_rgb = cv2.resize(face_rgb, (160, 160))

        embedding = embedder.embeddings([face_rgb])[0]
        captured_embeddings.append(embedding)

        img_path = os.path.join(student_folder, f"{name}_{len(captured_embeddings)}.jpg")
        cv2.imwrite(img_path, frame[y:y + h, x:x + w])
        print(f"✅ Captured image {len(captured_embeddings)}")

    # Show progress
    cv2.putText(frame, f"📸 Captured: {len(captured_embeddings)}/10", (10, 30),
                cv2.FONT_HERSHEY_SIMPLEX, 0.9, (0, 255, 0), 2)
    cv2.imshow("Registering Face", frame)

    if cv2.waitKey(1) & 0xFF == ord("q"):
        break

# Save embedding
if captured_embeddings:
    mean_embedding = np.mean(captured_embeddings, axis=0)
    embedding_path = os.path.join(student_folder, f"{student_id}_embedding.npy")
    np.save(embedding_path, mean_embedding)
    print(f"✅ Saved embedding for {student_id} at {embedding_path}")
else:
    print("❌ No face embeddings captured.")

cap.release()
cv2.destroyAllWindows()

print(f"🎉 Successfully registered {name} with ID {student_id}!")
