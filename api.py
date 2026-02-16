from fastapi import FastAPI, HTTPException
from supabase import create_client

app = FastAPI()

URL = "https://icnlaumwdyrebbzmexiu.supabase.co"
KEY = "sb_publishable_5JQlhyKV7IO5gLjMDMRxfA_bs2FMTGd"
supabase = create_client(URL, KEY)

@app.get("/verify/{key}")
def verify_license(key: str):
    # Chercher le client avec cette clé
    client = supabase.table("clients").select("*").eq("license_key", key).execute()
    
    if not client.data:
        raise HTTPException(status_code=404, detail="Clé invalide")
    
    user = client.data[0]
    if not user["is_active"]:
        return {"status": "denied", "message": "Compte suspendu"}
    
    return {
        "status": "success",
        "message": "Accès autorisé",
        "user_data": user["data_cloud"]
    }