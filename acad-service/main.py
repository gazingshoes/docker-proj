from fastapi import FastAPI, HTTPException, Header, Depends
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import psycopg2
import os
import jwt  # Needs pyjwt installed
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

# --- SECURITY: Verify Token Dependency ---
async def verify_token(authorization: str = Header(None)):
    if not authorization:
        raise HTTPException(status_code=401, detail="Missing Authorization Header")
    
    try:
        token = authorization.split(" ")[1] # Bearer <token>
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

# --- UPDATED ENDPOINT: Detailed IPS with Auth ---
@app.get("/api/acad/ips/{nim}")
async def get_ips_detail(nim: str, user=Depends(verify_token)):
    try:
        with get_db_connection() as conn:
            cursor = conn.cursor()
            
            # 1. Get Student Info
            cursor.execute("SELECT nim, nama, jurusan, angkatan FROM mahasiswa WHERE nim = %s", (nim,))
            student = cursor.fetchone()
            
            if not student:
                raise HTTPException(status_code=404, detail="Mahasiswa tidak ditemukan")

            # 2. Get Detailed Transcript
            query = """
            SELECT 
                mk.kode_mk,
                mk.nama_mk,
                mk.sks,
                k.nilai,
                bn.bobot,
                k.semester
            FROM krs k
            JOIN mata_kuliah mk ON k.kode_mk = mk.kode_mk
            JOIN bobot_nilai bn ON k.nilai = bn.nilai
            WHERE k.nim = %s
            ORDER BY k.semester ASC, mk.nama_mk ASC
            """
            cursor.execute(query, (nim,))
            rows = cursor.fetchall()
            
            # 3. Calculate Logic in Python
            transcript = []
            total_sks = 0
            total_points = 0
            
            for r in rows:
                sks = r[2]
                bobot = r[4]
                
                total_sks += sks
                total_points += (sks * bobot)
                
                transcript.append({
                    "kode": r[0],
                    "mata_kuliah": r[1],
                    "sks": sks,
                    "nilai": r[3],
                    "bobot": bobot,
                    "semester": r[5]
                })

            ips = round(total_points / total_sks, 2) if total_sks > 0 else 0.0

            return {
                "nim": student[0],
                "nama": student[1],
                "prodi": student[2],
                "angkatan": student[3],
                "total_sks": total_sks,
                "ips": ips,
                "transcript": transcript
            }

    except HTTPException as he:
        raise he
    except Exception as e:
        print(f"Error: {e}")
        raise HTTPException(status_code=500, detail=str(e))