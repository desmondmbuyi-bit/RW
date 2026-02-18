from fastapi import FastAPI, HTTPException
from supabase import create_client
import os
from datetime import datetime
from dateutil import parser # Plus robuste pour lire les dates

app = FastAPI()

url = os.getenv("SUPABASE_URL")
key = os.getenv("SUPABASE_KEY")
supabase = create_client(url, key)

@app.get("/")
def home():
    return {"status": "ok"}

@app.get("/verify/{key}")
def verify_license(key: str):
    try:
        response = supabase.table("clients").select("*").eq("license_key", key).execute()
        
        if not response.data:
            raise HTTPException(status_code=404, detail="Cle inexistante")
        
        user = response.data[0]
        
        # 1. Verif activation manuelle
        if not user.get("is_active"):
            raise HTTPException(status_code=403, detail="Licence desactivee")
            
        # 2. Verif expiration
        exp_date_str = user.get("expires_at")
        if exp_date_str:
            # On utilise parser.parse pour eviter les crashs de format
            expiration = parser.parse(exp_date_str)
            if datetime.now().astimezone() > expiration.astimezone():
                # On desactive en DB pour la prochaine fois
                supabase.table("clients").update({"is_active": False}).eq("license_key", key).execute()
                raise HTTPException(status_code=403, detail="Licence expiree")

        return {
            "status": "authorized",
            "email": user.get("email"),
            "data": user.get("data_cloud")
        }
    except HTTPException as he:
        raise he
    except Exception as e:
        # On renvoie l'erreur en JSON pour ne pas faire crash le serveur
        print(f"Erreur interne: {e}")
        raise HTTPException(status_code=500, detail="Erreur interne du serveur")
