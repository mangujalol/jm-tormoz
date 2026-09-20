from datetime import datetime
from flask import Flask, jsonify, request
from flask_cors import CORS

app = Flask(__name__)
CORS(app)  # Frontend va backend bir-biri bilan erkin gaplashishi uchun

# Vaqtinchalik xotiradagi baza (Ma'lumotlar o'chib ketmasligi uchun uni keyinchalik MongoDB yoki SQLite ga ulash mumkin)
# Hozircha sinov uchun oddiy lug'at (dictionary) ishlatamiz
pads_db = []
logs_db = []


@app.route("/")
def home():
  return "JM Tormoz Nazorati Backend ishlayapti! 🚀"


# Hamma kolodkalar holatini olish
@app.route("/api/pads", methods=["GET"])
def get_pads():
  return jsonify(pads_db)


# Kolodka almashtirilganda ma'lumotni yangilash va logga qo'shish
@app.route("/api/replace", methods=["POST"])
def replace_pad():
  data = request.json
  train_number = data.get("train_number")
  wagon_code = data.get("wagon_code")
  bogie_number = data.get("bogie_number")
  pad_index = data.get("pad_index")
  user_name = data.get("user_name", "Anonim")

  # Eski ma'lumot bormi tekshiramiz, bo'lsa yangilaymiz, yo'qsa qo'shamiz
  found = False
  for item in pads_db:
    if (
        item.get("train_number") == train_number
        and item.get("wagon_code") == wagon_code
        and item.get("pad_index") == pad_index
    ):
      item["days_used"] = 0
      item["updated_at"] = datetime.now().isoformat()
      found = True
      break

  if not found:
    pads_db.append({
        "train_number": train_number,
        "wagon_code": wagon_code,
        "pad_index": pad_index,
        "days_used": 0,
        "updated_at": datetime.now().isoformat(),
    })

  # Tarixga (log) yozish
  log_entry = {
      "id": str(len(logs_db) + 1),
      "train_number": train_number,
      "wagon_code": wagon_code,
      "bogie_number": bogie_number,
      "pad_index": pad_index,
      "user_name": user_name,
      "created_at": datetime.now().isoformat(),
  }
  logs_db.insert(0, log_entry)  # Yangisini boshiga qo'shish

  return jsonify({"status": "success", "message": "Muvaffaqiyatli yangilandi!"})


# O'zgarishlar tarixini olish
@app.route("/api/logs", methods=["GET"])
def get_logs():
  return jsonify(logs_db)


if __name__ == "__main__":
  app.run(debug=True)