from fastapi import FastAPI, HTTPException, Header, Depends
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import psycopg2
import os
import jwt
from datetime import datetime
from contextlib import contextmanager

app = FastAPI(title="Academic Service", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Configs
DB_CONFIG = {
    'host': os.getenv('DB_HOST', 'localhost'),
    'port': os.getenv('DB_PORT', '5432'),
    'database': os.getenv('DB_NAME', 'acad_db'),
    'user': os.getenv('DB_USER', 'user'),
    'password': os.getenv('DB_PASSWORD', 'password')
}
JWT_SECRET = os.getenv("JWT_SECRET", "secret")

@contextmanager
def get_db_connection():
    conn = psycopg2.connect(**DB_CONFIG)
    try:
        yield conn
        conn.commit()
    except Exception as e:
        conn.rollback()
        raise e
    finally:
        conn.close()

# --- SECURITY ---
async def verify_token(authorization: str = Header(None)):
    if not authorization:
        raise HTTPException(status_code=401, detail="Missing Authorization Header")
    try:
        token = authorization.split(" ")[1]
        payload = jwt.decode(token, JWT_SECRET, algorithms=["HS256"])
        return payload
    except Exception as e:
        raise HTTPException(status_code=401, detail="Invalid or Expired Token")

@app.on_event("startup")
async def startup_event():
    try:
        with get_db_connection() as conn:
            print("Acad Service: Connected to PostgreSQL")
    except Exception as e:
        print(f"Acad Service: PostgreSQL connection error: {e}")

@app.get("/health")
async def health_check():
    return {"status": "Acad Service is running", "timestamp": datetime.now().isoformat()}

# --- STUDENT IPS ENDPOINT ---
@app.get("/api/acad/ips/{nim}")
async def get_ips_detail(nim: str, user=Depends(verify_token)):
    try:
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT nim, nama, jurusan, angkatan FROM mahasiswa WHERE nim = %s", (nim,))
            student = cursor.fetchone()
            if not student:
                raise HTTPException(status_code=404, detail="Mahasiswa tidak ditemukan")

            query = """
            SELECT mk.kode_mk, mk.nama_mk, mk.sks, k.nilai, bn.bobot, k.semester
            FROM krs k
            JOIN mata_kuliah mk ON k.kode_mk = mk.kode_mk
            JOIN bobot_nilai bn ON k.nilai = bn.nilai
            WHERE k.nim = %s
            ORDER BY k.semester ASC, mk.nama_mk ASC
            """
            cursor.execute(query, (nim,))
            rows = cursor.fetchall()
            
            transcript = []
            total_sks = 0
            total_points = 0
            for r in rows:
                sks = r[2]
                bobot = r[4]
                total_sks += sks
                total_points += (sks * bobot)
                transcript.append({
                    "kode": r[0], "mata_kuliah": r[1], "sks": sks, 
                    "nilai": r[3], "bobot": bobot, "semester": r[5]
                })

            ips = round(total_points / total_sks, 2) if total_sks > 0 else 0.0
            return {
                "nim": student[0], "nama": student[1], "prodi": student[2],
                "angkatan": student[3], "total_sks": total_sks, "ips": ips, "transcript": transcript
            }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# --- INPUT MODELS ---
class MahasiswaInput(BaseModel):
    nim: str
    nama: str
    jurusan: str
    angkatan: int

class MataKuliahInput(BaseModel):
    kode_mk: str
    nama_mk: str
    sks: int

class KRSInput(BaseModel):
    nim: str
    kode_mk: str
    semester: int
    nilai: str

# --- ADMIN POST ENDPOINTS ---
@app.post("/api/acad/mahasiswa")
async def add_mahasiswa(data: MahasiswaInput, user=Depends(verify_token)):
    try:
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("INSERT INTO mahasiswa (nim, nama, jurusan, angkatan) VALUES (%s, %s, %s, %s)", 
                           (data.nim, data.nama, data.jurusan, data.angkatan))
            return {"message": "Mahasiswa berhasil ditambahkan"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/acad/matakuliah")
async def add_matakuliah(data: MataKuliahInput, user=Depends(verify_token)):
    try:
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("INSERT INTO mata_kuliah (kode_mk, nama_mk, sks) VALUES (%s, %s, %s)", 
                           (data.kode_mk, data.nama_mk, data.sks))
            return {"message": "Mata Kuliah berhasil ditambahkan"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/acad/krs")
async def add_krs(data: KRSInput, user=Depends(verify_token)):
    try:
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT nilai FROM bobot_nilai WHERE nilai = %s", (data.nilai,))
            if not cursor.fetchone():
                raise HTTPException(status_code=400, detail="Nilai tidak valid")
            cursor.execute("INSERT INTO krs (nim, kode_mk, semester, nilai) VALUES (%s, %s, %s, %s)", 
                           (data.nim, data.kode_mk, data.semester, data.nilai))
            return {"message": "Data KRS berhasil ditambahkan"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# --- NEW: ADMIN GET LIST ENDPOINTS (Display Data) ---
@app.get("/api/acad/mahasiswa")
async def get_all_mahasiswa(user=Depends(verify_token)):
    try:
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT nim, nama, jurusan, angkatan FROM mahasiswa ORDER BY nim")
            rows = cursor.fetchall()
            return [{"nim": r[0], "nama": r[1], "jurusan": r[2], "angkatan": r[3]} for r in rows]
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/acad/matakuliah")
async def get_all_matakuliah(user=Depends(verify_token)):
    try:
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT kode_mk, nama_mk, sks FROM mata_kuliah ORDER BY kode_mk")
            rows = cursor.fetchall()
            return [{"kode_mk": r[0], "nama_mk": r[1], "sks": r[2]} for r in rows]
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))