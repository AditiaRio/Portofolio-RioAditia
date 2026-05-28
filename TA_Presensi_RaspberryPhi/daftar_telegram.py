import urllib3
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

from telegram import Update
from telegram.ext import Updater, CommandHandler, MessageHandler, Filters, CallbackContext
import os
import cv2
import requests
import tempfile
import numpy as np
import certifi

# ───── Konfigurasi ─────
TOKEN = "7802518936:AAEwdzuUfH7RqnZfXfWJZFosnu6AxgnlL4U"
API_URL = "https://presensismkzk.my.id/api/siswa"
API_CEK_SISWA_URL = "https://presensismkzk.my.id/api/cek-siswa"
dataset_folder = "dataset"
if not os.path.exists(dataset_folder):
    os.makedirs(dataset_folder)

user_state = {}

# ───── Deteksi wajah ringan ─────
face_cascade = cv2.CascadeClassifier(cv2.data.haarcascades + "haarcascade_frontalface_default.xml")

def extract_faces_opencv(frame):
    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    faces_coord = face_cascade.detectMultiScale(gray, scaleFactor=1.1, minNeighbors=5)

    faces = []
    for (x, y, w, h) in faces_coord:
        face = frame[y:y+h, x:x+w]
        face = cv2.resize(face, (224, 224))
        faces.append(face)
    return faces

# ───── /start ─────
def start(update: Update, context: CallbackContext):
    user_id = update.message.from_user.id
    user_state[user_id] = {"step": "nama"}
    update.message.reply_text("Selamat datang! Kirim *nama lengkap* Anda terlebih dahulu.", parse_mode="Markdown")

# ───── Handle Teks ─────
def handle_text(update: Update, context: CallbackContext):
    user_id = update.message.from_user.id
    text = update.message.text.strip()

    if user_id not in user_state:
        update.message.reply_text("Ketik /start untuk memulai.")
        return

    state = user_state[user_id]

    if state["step"] == "nama":
        state["nama"] = text
        state["step"] = "nis"
        update.message.reply_text("Nama diterima. Kirim *NIS* Anda.", parse_mode="Markdown")

    elif state["step"] == "nis":
        if not text.isdigit():
            update.message.reply_text("❗ NIS harus angka. Kirim ulang.")
            return

        state["nis"] = text
        payload = {
            "nis": state["nis"],
            "nama": state["nama"]
        }
        headers = {
        "Content-Type": "application/json",
        "Accept": "application/json",
        "User-Agent": "Mozilla/5.0"
        }

        try:
            print("⏳ Mengirim ke API:", payload)
            cek = requests.post(API_CEK_SISWA_URL, json=payload, headers=headers, verify=certifi.where())
            print("✅ Response:", cek.status_code, cek.text)

            if cek.status_code == 200 and cek.json().get("valid") == True:
                state["step"] = "gender"
                update.message.reply_text("NIS valid. Kirim *jenis kelamin* Anda (L/P).", parse_mode="Markdown")
            else:
                update.message.reply_text("❌ NIS atau nama tidak terdaftar di sekolah.\nHubungi admin.")
                user_state.pop(user_id, None)

        except Exception as e:
            print(f"❌ Error saat verifikasi ke server: {e}")
            update.message.reply_text(f"❌ Gagal menghubungi server:\n{e}")
            user_state.pop(user_id, None)

    elif state["step"] == "gender":
        if text.upper() not in ["L", "P"]:
            update.message.reply_text("❗ Jawaban hanya L atau P. Coba lagi.")
            return
        state["gender"] = text.upper()
        state["step"] = "kelas"
        update.message.reply_text("Jenis kelamin diterima. Kirim *kelas* Anda (misal: XII-RPL).", parse_mode="Markdown")

    elif state["step"] == "kelas":
        state["kelas"] = text.upper()
        state["step"] = "email"
        update.message.reply_text("Kelas diterima. Kirim *email* Anda.", parse_mode="Markdown")

    elif state["step"] == "email":
        if "@" not in text or "." not in text:
            update.message.reply_text("❗ Format email tidak valid. Coba lagi.")
            return
        state["email"] = text
        state["step"] = "video"
        update.message.reply_text("Email diterima ✅. Kirim video wajah Anda.", parse_mode="Markdown")

# ───── Proses Video ─────
def proses_video(video_path, output_folder, nis, nama, max_wajah=5):
    cap = cv2.VideoCapture(video_path)
    simpan = 0
    frame_index = 0

    if not os.path.exists(output_folder):
        os.makedirs(output_folder)

    while True:
        ret, frame = cap.read()
        if not ret or simpan >= max_wajah:
            break

        frame_index += 1
        if frame_index % 10 != 0:
            continue

        faces = extract_faces_opencv(frame)

        if faces:
            face = faces[0]
            folder_nama = f"{nis}_{nama.replace(' ', '_')}"
            output_folder = os.path.join("dataset", folder_nama)

            if not os.path.exists(output_folder):
                os.makedirs(output_folder)

            filename = f"User.{nis}.{simpan+1}.jpg"
            path = os.path.join(output_folder, filename)
            cv2.imwrite(path, face, [int(cv2.IMWRITE_JPEG_QUALITY), 95])
            simpan += 1

    cap.release()
    return simpan

# ───── Handle Video ─────
def handle_video(update: Update, context: CallbackContext):
    user_id = update.message.from_user.id

    if user_id not in user_state or user_state[user_id]["step"] != "video":
        update.message.reply_text("Silakan mulai dengan /start dan ikuti instruksi.")
        return

    state = user_state[user_id]
    nama = state["nama"]
    nis = state["nis"]
    gender = state["gender"]
    kelas = state["kelas"]
    email = state["email"]

    video = update.message.video or update.message.document
    if not video:
        update.message.reply_text("❌ File bukan video. Silakan kirim ulang.")
        return

    folder_name = f"{nis}_{nama.replace(' ', '_')}"
    folder_user = os.path.join(dataset_folder, folder_name)
    if not os.path.exists(folder_user):
        os.makedirs(folder_user)

    file = video.get_file()
    with tempfile.NamedTemporaryFile(suffix=".mp4") as tmp_file:
        file.download(custom_path=tmp_file.name)
        update.message.reply_text("📥 Video diterima. Sedang diproses...")

        total_disimpan = proses_video(tmp_file.name, folder_user, nis, nama, max_wajah=5)

    if total_disimpan == 0:
        update.message.reply_text("❌ Tidak ada wajah terdeteksi. Silakan kirim ulang video yang lebih jelas.")
        return

    update.message.reply_text(f"✅ Berhasil menyimpan {total_disimpan} gambar wajah dari video.")

    # Kirim ke server
    payload = {
        "nis": nis,
        "nama": nama,
        "jenis_kelamin": gender,
        "kelas": kelas,
        "email": email,
        "foto": f"{folder_name}/User.{nis}.1.jpg"
    }
    headers = {
        "Content-Type": "application/json",
        "Accept": "application/json",
        "User-Agent": "Mozilla/5.0"
    }

    try:
        response = requests.post(API_URL, json=payload, headers=headers, verify=False)
        response.raise_for_status()
        update.message.reply_text(f"🎉 Pendaftaran selesai untuk *{nama}* (NIS: {nis}).", parse_mode="Markdown")
    except requests.exceptions.RequestException as e:
        update.message.reply_text(f"❌ Gagal mengirim data ke server:\n{e}")

    user_state.pop(user_id, None)

# ───── Main ─────
def main():
    updater = Updater(TOKEN, use_context=True)
    dp = updater.dispatcher

    dp.add_handler(CommandHandler("start", start))
    dp.add_handler(MessageHandler(Filters.text & ~Filters.command, handle_text))
    dp.add_handler(MessageHandler(Filters.video | Filters.document.category("video"), handle_video))

    updater.start_polling()
    print("[BOT] Aktif!")
    updater.idle()

if __name__ == "__main__":
    main()
