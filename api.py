from fastapi import FastAPI, HTTPException
from supabase import create_client
import os

app = FastAPI()

# Vérification sécurisée des variables
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")

if not SUPABASE_URL or not SUPABASE_KEY:
    print("ERREUR : Variables Supabase manquantes !")
    supabase = None
else:
    supabase = create_client(SUPABASE_URL, SUPABASE_KEY)

@app.get("/")
def health():
    return {"status": "online"}

@app.get("/verify/{key}")
def verify_license(key: str):
    if not supabase:
        raise HTTPException(status_code=500, detail="Supabase non configuré")

    try:
        response = (
            supabase
            .table("clients")
            .select("*")
            .eq("license_key", key)
            .eq("is_active", True)
            .execute()
        )

        if not response.data:
            raise HTTPException(status_code=403, detail="Acces refuse")

        return {"status": "authorized", "user": response.data[0]}

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
