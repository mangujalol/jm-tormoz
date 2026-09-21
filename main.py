import os
from datetime import datetime
from typing import List, Optional
from fastapi import FastAPI, Depends, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
import pandas as pd
from pydantic import BaseModel
from sqlalchemy import create_engine, Column, Integer, String, DateTime
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, Session
import io

# --- MA'LUMOTLAR BAZASINI SOZLASH (PostgreSQL yoki SQLite) ---
# Render'dan DATABASE_URL o'qib olinadi, bo'lmasa lokalda sqlite ishlatiladi
SQLALCHEMY_DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./tormoz_nazorat.db")

# Render ba'zan 'postgres://' beradi, SQLAlchemy uni 'postgresql://' qilishni talab qiladi
if SQLALCHEMY_DATABASE_URL and SQLALCHEMY_DATABASE_URL.startswith("postgres://"):
    SQLALCHEMY_DATABASE_URL = SQLALCHEMY_DATABASE_URL.replace("postgres://", "postgresql://", 1)

if SQLALCHEMY_DATABASE_URL.startswith("sqlite"):
    engine = create_engine(SQLALCHEMY_DATABASE_URL, connect_args={"check_same_thread": False})
else:
    engine = create_engine(SQLALCHEMY_DATABASE_URL)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

# --- DB MODELLARI ---
class PadDB(Base):
    __tablename__ = "pads"
    id = Column(Integer, primary_key=True, index=True)
    train_number = Column(String, index=True)
    wagon_code = Column(String, index=True)
    pad_index = Column(Integer, index=True)
    days_used = Column(Integer, default=0)

class LogDB(Base):
    __tablename__ = "logs"
    id = Column(Integer, primary_key=True, index=True)
    train_number = Column(String, index=True)
    wagon_code = Column(String, index=True)
    bogie_number = Column(Integer)
    pad_index = Column(Integer)
    user_name = Column(String)
    created_at = Column(DateTime, default=datetime.utcnow)

Base.metadata.create_all(bind=engine)

# --- FASTAPI ILOVASI ---
app = FastAPI(title="JM Tormoz Nazorati API", version="1.0")

# CORS sozlamalari (Frontend erkin ulanishi uchun)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Ishlab chiqarishda aniq domenlarni ko'rsatish tavsiya etiladi
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Bog'lanish (Session) olish uchun yordamchifunksiya
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

# --- PYDANTIC SXEMALARI ---
class ReplaceRequest(BaseModel):
    train_number: str
    wagon_code: str
    bogie_number: int
    pad_index: int
    user_name: str

# --- BOSHLANG'ICH MA'LUMOTLARNI TO'LDIRISH (AGAR BO'SH BO'LSA) ---
def init_db_data():
    db = SessionLocal()
    if db.query(PadDB).count() == 0:
        trains = ['01', '02', '03', '04', '05', '06']
        wagons = ['TC1', '2', '3', '4', '5', '6', 'TC2']
        for t in trains:
            for w in wagons:
                for i in range(1, 17):
                    db.add(PadDB(train_number=t, wagon_code=w, pad_index=i, days_used=10)) # Boshlang'ich kunlar
        db.commit()
    db.close()

init_db_data()

# --- ENDPOINTLAR ---

@app.get("/api/pads")
def get_pads(db: Session = Depends(get_db)):
    pads = db.query(PadDB).all()
    return pads

@app.get("/api/logs")
def get_logs(db: Session = Depends(get_db)):
    logs = db.query(LogDB).order_by(LogDB.created_at.desc()).all()
    return logs

@app.post("/api/replace")
def replace_pad(data: ReplaceRequest, db: Session = Depends(get_db)):
    # Kolodkani topish va kunini 0 ga tushirish
    pad = db.query(PadDB).filter(
        PadDB.train_number == data.train_number,
        PadDB.wagon_code == data.wagon_code,
        PadDB.pad_index == data.pad_index
    ).first()
    
    if pad:
        pad.days_used = 0
    else:
        # Agar bazada bo'lmasa, yaratamiz
        pad = PadDB(
            train_number=data.train_number,
            wagon_code=data.wagon_code,
            pad_index=data.pad_index,
            days_used=0
        )
        db.add(pad)
    
    # Log yozish
    new_log = LogDB(
        train_number=data.train_number,
        wagon_code=data.wagon_code,
        bogie_number=data.bogie_number,
        pad_index=data.pad_index,
        user_name=data.user_name,
        created_at=datetime.utcnow()
    )
    db.add(new_log)
    db.commit()
    
    return {"status": "success", "message": "Kolodka muvaffaqiyatli almashtirildi"}

@app.delete("/api/logs/{log_id}")
def delete_log(log_id: int, db: Session = Depends(get_db)):
    log = db.query(LogDB).filter(LogDB.id == log_id).first()
    if not log:
        raise HTTPException(status_code=404, detail="Log topilmadi")
    
    db.delete(log)
    db.commit()
    return {"status": "success", "message": "Log o'chirildi"}

@app.get("/report/export-excel")
def export_excel(train: Optional[str] = '01', db: Session = Depends(get_db)):
    logs = db.query(LogDB).filter(LogDB.train_number == train).all()
    
    # Kolodka indekslarini ularning matnli nomlariga moslashtirish uchun lug'at
    pad_names = {
        1: 'ChT1', 2: 'ChI2', 3: 'ÖI2', 4: 'ÖT1',
        5: 'ChT3', 6: 'ChI4', 7: 'ÖI4', 8: 'ÖT3',
        9: 'ChT5', 10: 'ChI6', 11: 'ÖI6', 12: 'ÖT5',
        13: 'ChT7', 14: 'ChI8', 15: 'ÖI8', 16: 'ÖT7'
    }
    
    data = []
    for l in logs:
        # Indeksdan mos nomni olamiz, agar topilmasa raqamning o'zi qoladi
        pad_code = pad_names.get(l.pad_index, f"K{l.pad_index}")
        
        data.append({
            "Poyezd №": l.train_number,
            "Vagon": l.wagon_code,
            "Aravacha": l.bogie_number,
            "Kolodka": pad_code,  # Endi bu yerda ChT1, ÖI2 kabi nomlar yoziladi
            "Mas'ul Xodim": l.user_name,
            "Almashtirilgan Sana/Vaqt": l.created_at.strftime("%Y-%m-%d %H:%M")
        })
        
    df = pd.DataFrame(data)
    
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        df.to_excel(writer, index=False, sheet_name=f"Poyezd_{train}_Tarix")
    output.seek(0)
    
    headers = {
        'Content-Disposition': f'attachment; filename="Poyezd_{train}_Hisobot.xlsx"'
    }
    return StreamingResponse(output, headers=headers, media_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')