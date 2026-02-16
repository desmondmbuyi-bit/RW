from fastapi import FastAPI, HTTPException
from supabase import create_client
import os

app = FastAPI()

# Railway va lire ces variables dans ses réglages (on va les ajouter après)
URL = os.getenv("https://icnlaumwdyrebbzmexiu.supabase.co")
KEY = os.getenv("sb_publishable_5JQlhyKV7IO5gLjMDMRxfA_bs2FMTGd")
supabase = create_client(URL, KEY)

@app.get("/")
def home():
    return {"status": "online", "message": "Vigile de licence prêt"}

@app.get("/verify/{key}")
def verify_license(key: str):
    try:
        response = supabase.table("clients").select("*").eq("license_key", key).eq("is_active", True).execute()
        
        if not response.data:
            raise HTTPException(status_code=403, detail="Acces refuse")
        
        return {"status": "authorized", "user": response.data[0]}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
        "user_data": user["data_cloud"]

    }


