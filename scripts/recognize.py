import cv2
import numpy as np
import os
import sys
import django
from keras_facenet import FaceNet
from mtcnn import MTCNN
from datetime import date
from sklearn.metrics.pairwise import cosine_similarity
from django.utils import timezone
import time

# ----------------------------
# DJANGO SETUP
# ----------------------------
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, BASE_DIR)
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "attendance_system.settings")
django.setup()
from attendance.models import Student, Attendance

# ----------------------------
# LOAD MODELS
# ----------------------------
embedder = FaceNet()
detector = MTCNN()

# ----------------------------
# PATHS
# ----------------------------
KNOWN_FACES_DIR = os.path.join(BASE_DIR, "faces")

# ----------------------------
# HELPER FUNCTIONS
# ----------------------------
def load_known_faces():
    """Load embeddings and IDs of registered students."""
    known_face_encodings = []
    known_face_ids = []

    if not os.path.exists(KNOWN_FACES_DIR):
        print("❌ Faces folder not found.")
        return known_face_encodings, known_face_ids

    for folder in os.listdir(KNOWN_FACES_DIR):
        folder_path = os.path.join(KNOWN_FACES_DIR, folder)
        embedding_path = os.path.join(folder_path, f"{folder}_embedding.npy")

        if os.path.exists(embedding_path):
            encoding = np.load(embedding_path)
            known_face_encodings.append(encoding)
            known_face_ids.append(folder)

    return known_face_encodings, known_face_ids

def mark_attendance(student, min_interval_seconds=60):
    """
    Mark check-in or check-out for the latest session today.
    If the latest session is closed, start a new one with check-in.
    Optionally enforce a minimum interval before checkout.
    """
    today = date.today()
    now = timezone.now()

    # latest record for today
    last_record = (
        Attendance.objects
        .filter(student=student, date=today)
        .order_by('-id')
        .first()
    )

    # No record today -> first CHECK-IN
    if last_record is None:
        Attendance.objects.create(student=student, date=today, check_in=now)
        status = "Check-In Successful"

    # Open session -> CHECK-OUT (with optional wait)
    elif last_record.check_out is None:
        elapsed_seconds = (now - last_record.check_in).total_seconds()
        if elapsed_seconds >= min_interval_seconds:
            last_record.check_out = now
            last_record.save()
            status = "Check-Out Successful"
        else:
            wait_seconds = int(min_interval_seconds - elapsed_seconds)
            status = f"Wait {wait_seconds}s before checkout"

    # Last session closed -> start NEW CHECK-IN
    else:
        Attendance.objects.create(student=student, date=today, check_in=now)
        status = "Check-In Successful"

    return status, now


def draw_success_message(frame, student_name, status):
    """Draw a prominent success banner on the camera frame."""
    overlay = frame.copy()
    h, w = frame.shape[:2]
    cv2.rectangle(overlay, (0, 0), (w, h), (0, 0, 0), -1)
    frame[:] = cv2.addWeighted(overlay, 0.35, frame, 0.65, 0)

    if "Check-In" in status:
        title = "Check-In Successful!"
        color = (0, 200, 0)
    elif "Check-Out" in status:
        title = "Check-Out Successful!"
        color = (0, 140, 255)
    else:
        title = status
        color = (0, 255, 255)

    cv2.putText(
        frame, title, (40, h // 2 - 40),
        cv2.FONT_HERSHEY_SIMPLEX, 1.2, color, 3, cv2.LINE_AA,
    )
    cv2.putText(
        frame, student_name, (40, h // 2 + 10),
        cv2.FONT_HERSHEY_SIMPLEX, 1.0, (255, 255, 255), 2, cv2.LINE_AA,
    )
    cv2.putText(
        frame, "Press Q to quit", (40, h // 2 + 55),
        cv2.FONT_HERSHEY_SIMPLEX, 0.7, (220, 220, 220), 2, cv2.LINE_AA,
    )


def cleanup_camera(cap):
    cap.release()
    cv2.destroyAllWindows()


def show_success_and_exit(cap, frame, student_name, status, display_seconds=2.5):
    """Show success overlay briefly; allow early exit with Q."""
    draw_success_message(frame, student_name, status)
    cv2.imshow("Face Recognition", frame)
    print(f"SUCCESS: {status} for {student_name}")

    end_time = time.time() + display_seconds
    while time.time() < end_time:
        key = cv2.waitKey(50) & 0xFF
        if key == ord("q"):
            break

    cleanup_camera(cap)


# ----------------------------
# FACE RECOGNITION LOOP
# ----------------------------
def recognize_face():
    known_face_encodings, known_face_ids = load_known_faces()
    if not known_face_encodings:
        print("❌ No registered faces found.")
        return

    cap = cv2.VideoCapture(0)
    if not cap.isOpened():
        print("❌ Could not open camera.")
        return

    print("Starting face recognition... Press Q to quit.")

    recognized_faces = {}  # matched_id -> {"coords": (x,y,w,h), "status": status, "last_seen": timestamp}
    window_name = "Face Recognition"
    cv2.namedWindow(window_name, cv2.WINDOW_NORMAL)

    while True:
        ret, frame = cap.read()
        if not ret:
            continue

        rgb_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        detections = detector.detect_faces(rgb_frame)

        # Process each detected face
        for detection in detections:
            x, y, w, h = detection['box']
            x, y = max(0, x), max(0, y)
            if w < 80 or h < 80:
                continue

            face_crop = rgb_frame[y:y+h, x:x+w]
            face_crop = cv2.resize(face_crop, (160, 160))
            embedding = embedder.embeddings([face_crop])[0]

            similarities = [cosine_similarity([embedding], [enc])[0][0] for enc in known_face_encodings]
            best_index = np.argmax(similarities)
            best_score = similarities[best_index]
            matched_id = known_face_ids[best_index]

            if best_score > 0.6:
                last_seen = recognized_faces.get(matched_id, {}).get("last_seen", 0)
                if time.time() - last_seen < 5:  # avoid rapid re-recognition
                    continue

                recognized_faces[matched_id] = {"coords": (x, y, w, h), "last_seen": time.time()}

                try:
                    student = Student.objects.get(student_id=matched_id)
                    status, _ = mark_attendance(student, min_interval_seconds=60)
                    recognized_faces[matched_id]["status"] = status
                    print(f"{status} for {student.name}")

                    if status in ["Check-In Successful", "Check-Out Successful"]:
                        show_success_and_exit(cap, frame, student.name, status)
                        return

                except Student.DoesNotExist:
                    print(f"Student with ID {matched_id} not found.")

        # Draw all recognized faces persistently
        for info in recognized_faces.values():
            x, y, w, h = info["coords"]
            status = info.get("status", "")
            if "Check-In" in status:
                color = (0, 255, 0)  # Green
            elif "Check-Out" in status:
                color = (255, 0, 0)  # Blue
            elif "Wait" in status:
                color = (0, 165, 255)  # Orange
            else:
                color = (0, 255, 255)  # Yellow

            cv2.rectangle(frame, (x, y), (x+w, y+h), color, 2)
            cv2.putText(frame, f"{status}", (x, y-10), cv2.FONT_HERSHEY_SIMPLEX, 0.8, color, 2)

        cv2.putText(
            frame, "Press Q to quit", (10, 30),
            cv2.FONT_HERSHEY_SIMPLEX, 0.7, (200, 200, 200), 2, cv2.LINE_AA,
        )
        cv2.imshow(window_name, frame)
        if cv2.waitKey(1) & 0xFF == ord("q"):
            print("Quit requested. Closing camera...")
            break

    cleanup_camera(cap)

# ----------------------------
# MAIN
# ----------------------------
if __name__ == "__main__":
    recognize_face()
