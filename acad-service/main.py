from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
import psycopg2
import os
from datetime import datetime
from contextlib import contextmanager

app = FastAPI(title="Academic Service", version="1.0.0")

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Database configuration
DB_CONFIG = {
    'host': os.getenv('DB_HOST', 'localhost'),
    'port': os.getenv('DB_PORT', '5432'),
    'database': os.getenv('DB_NAME', 'acad_db'),
    'user': os.getenv('DB_USER', 'user'),
    'password': os.getenv('DB_PASSWORD', 'password')
}

# Database connection pool
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

@app.on_event("startup")
async def startup_event():
    try:
        with get_db_connection() as conn:
            print("Acad Service: Connected to PostgreSQL")
    except Exception as e:
        print(f"Acad Service: PostgreSQL connection error: {e}")

# Health check
@app.get("/health")
async def health_check():
    return {
        "status": "Acad Service is running",
        "timestamp": datetime.now().isoformat()
    }

# 1. Endpoint Ambil Data Mahasiswa (Dasar)
@app.get("/api/acad/mahasiswa")
async def get_mahasiswas():
    try:
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT nim, nama, jurusan, angkatan FROM mahasiswa")
            rows = cursor.fetchall()
            return [{"nim": r[0], "nama": r[1], "jurusan": r[2], "angkatan": r[3]} for r in rows]
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# 2. Endpoint Hitung IPS (TUGAS WAJIB UAS)
@app.get("/api/acad/ips/{nim}")
async def get_ips_mahasiswa(nim: str):
    try:
        with get_db_connection() as conn:
            cursor = conn.cursor()
            
            # Query Join 4 Tabel: Mahasiswa -> KRS -> Mata Kuliah -> Bobot
            query = """
            SELECT 
                m.nim, 
                m.nama, 
                k.semester,
                SUM(mk.sks * bn.bobot) as total_bobot,
                SUM(mk.sks) as total_sks
            FROM mahasiswa m
            JOIN krs k ON m.nim = k.nim
            JOIN mata_kuliah mk ON k.kode_mk = mk.kode_mk
            JOIN bobot_nilai bn ON k.nilai = bn.nilai
            WHERE m.nim = %s
            GROUP BY m.nim, m.nama, k.semester
            """
            
            cursor.execute(query, (nim,))
            rows = cursor.fetchall()
            
            if not rows:
                raise HTTPException(status_code=404, detail="Data nilai tidak ditemukan untuk NIM tersebut")

            hasil_ips = []
            for row in rows:
                # Rumus IPS: Total (SKS * Bobot) / Total SKS
                ips = row[3] / row[4] if row[4] > 0 else 0
                hasil_ips.append({
                    "nim": row[0],
                    "nama": row[1],
                    "semester": row[2],
                    "ips": round(ips, 2)
                })
                
            return hasil_ips

    except Exception as e:
        print(f"Error: {e}")
        raise HTTPException(status_code=500, detail=str(e))