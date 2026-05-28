import cv2
import os
import RPi.GPIO as GPIO
import time
import numpy as np
import requests
from datetime import datetime, date
from deepface import DeepFace

# GPIO Setup
BUZZER_PIN = 17
BUTTON_PIN = 26
TRIG_PIN = 23
ECHO_PIN = 24
LED_PIN = 16

GPIO.setmode(GPIO.BCM)
GPIO.setup(BUZZER_PIN, GPIO.OUT)
GPIO.setup(BUTTON_PIN, GPIO.IN, pull_up_down=GPIO.PUD_UP)
GPIO.setup(TRIG_PIN, GPIO.OUT)
GPIO.setup(ECHO_PIN, GPIO.IN)
GPIO.setup(LED_PIN, GPIO.OUT)

# Path
DATASET_PATH = 'dataset'
TEMP_IMAGE = 'frame_temp.jpg'

# Absensi cache
sudah_absen = {}

# Toggle pendeteksian wajah
deteksi_aktif = True
last_button_state = GPIO.input(BUTTON_PIN)
last_toggle_time = time.time()

def ukur_jarak():
    GPIO.output(TRIG_PIN, False)
    time.sleep(0.1)
    GPIO.output(TRIG_PIN, True)
    time.sleep(0.00001)
    GPIO.output(TRIG_PIN, False)

    pulse_start = pulse_end = None
    timeout = time.time() + 1

    while GPIO.input(ECHO_PIN) == 0:
        pulse_start = time.time()
        if pulse_start > timeout:
            return 1000

    while GPIO.input(ECHO_PIN) == 1:
        pulse_end = time.time()
        if pulse_end > timeout:
            return 1000

    if pulse_start and pulse_end:
        duration = pulse_end - pulse_start
        distance = duration * 17150
        return round(distance, 2)
    else:
        return 1000

def kirim_absensi(nis, nama, status):
    url = "https://presensismkzk.my.id/api/absensi"
    data = {
        "nis": nis,
        "nama": nama,
        "waktu": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "keterangan": status
    }
    headers = {
        "Content-Type": "application/json",
        "User-Agent": "RaspberryPi-Presensi/1.0"
    }
    try:
        r = requests.post(url, json=data, headers=headers, timeout=10)
        return r.status_code == 200
    except:
        return False

def proses_deteksi():
    global deteksi_aktif, last_button_state, last_toggle_time

    print("[INFO] Sistem siap dengan DeepFace.")
    cam = cv2.VideoCapture(0, cv2.CAP_V4L2)
    cam.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc(*'MJPG'))
    cam.set(cv2.CAP_PROP_FRAME_WIDTH, 320)
    cam.set(cv2.CAP_PROP_FRAME_HEIGHT, 240)

    while True:
        # Tombol toggle ON/OFF
        current_button_state = GPIO.input(BUTTON_PIN)
        if current_button_state == GPIO.LOW and last_button_state == GPIO.HIGH and (time.time() - last_toggle_time) > 0.5:
            deteksi_aktif = not deteksi_aktif
            last_toggle_time = time.time()
            state = "AKTIF" if deteksi_aktif else "NON-AKTIF"
            print(f"[INFO] Mode deteksi: {state}")

        last_button_state = current_button_state

        # LED menunjukkan status deteksi
        GPIO.output(LED_PIN, GPIO.LOW if deteksi_aktif else GPIO.HIGH)

        if not deteksi_aktif or ukur_jarak() > 50:
            time.sleep(0.1)
            continue

        ret, frame = cam.read()
        if not ret:
            continue

        cv2.imwrite(TEMP_IMAGE, frame)
        if not os.path.exists(TEMP_IMAGE) or os.path.getsize(TEMP_IMAGE) < 10000:
            print("[WARNING] Gambar rusak atau terlalu kecil.")
            continue

        try:
            results = DeepFace.find(
                img_path=TEMP_IMAGE,
                db_path=DATASET_PATH,
                enforce_detection=False,
                model_name="SFace",
                detector_backend="opencv"
            )

            if isinstance(results, list) and len(results) > 0 and not results[0].empty:
                best_match = results[0].iloc[0]
                path = best_match["identity"]
                confidence = best_match["distance"]

                threshold = 0.4
                if np.isnan(confidence) or confidence >= threshold:
                    print(f"[WARNING] Wajah dikenali tapi confidence terlalu tinggi: {confidence:.4f} (≥ {threshold})")
                    continue  # Lewati jika confidence terlalu tinggi atau tidak valid

                folder_name = os.path.basename(os.path.dirname(path))
                nis, nama = folder_name.split("_", 1) if "_" in folder_name else ("00000", folder_name)

                tanggal = date.today().isoformat()
                now = datetime.now()
                jam, menit = now.hour, now.minute

                if 6 <= jam < 7 or (jam == 7 and menit <= 10):
                    status = "Tepat Waktu"
                elif 7 < jam < 12 or (jam == 7 and menit > 10):
                    status = "Terlambat"
                else:
                    status = "Pulang"

                key = (nis, status, tanggal)
                if key not in sudah_absen:
                    if kirim_absensi(nis, nama, status):
                        sudah_absen[key] = True
                        GPIO.output(BUZZER_PIN, GPIO.HIGH)
                        time.sleep(0.3)
                        GPIO.output(BUZZER_PIN, GPIO.LOW)
                        print(f"[INFO] {nama} ({nis}) tercatat sebagai {status}")
                    else:
                        print(f"[ERROR] Gagal kirim data untuk {nama}")
                else:
                    print(f"[INFO] {nama} sudah absen hari ini sebagai {status}")
            else:
                print("[INFO] Tidak ada wajah dikenali.")

        except Exception as e:
            print(f"[ERROR] DeepFace error: {e}")

        if os.path.exists(TEMP_IMAGE):
            os.remove(TEMP_IMAGE)

    cam.release()

if __name__ == "__main__":
    try:
        proses_deteksi()
    except KeyboardInterrupt:
        print("\n[INFO] Dihentikan oleh pengguna.")
    finally:
        GPIO.cleanup()

