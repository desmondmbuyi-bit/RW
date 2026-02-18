from fastapi import FastAPI, HTTPException
from supabase import create_client
import os
from datetime import datetime

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
    try:
        response = supabase.table("clients").select("*").eq("license_key", key).eq("is_active", True).execute()
        
        if not response.data:
            raise HTTPException(status_code=403, detail="Acces refuse")
        
        user_info = response.data[0]
        # 1. Vérifier si activé manuellement
        if not user["is_active"]:
            raise HTTPException(status_code=403, detail="Licence désactivée manuellement")
    
    # 2. Vérifier la date d'expiration
        if user["expires_at"]:
        expiration = datetime.fromisoformat(user["expires_at"].replace('Z', '+00:00'))
            if datetime.now().astimezone() > expiration.astimezone():
            # Optionnel : on peut désactiver la licence en DB automatiquement ici
            supabase.table("clients").update({"is_active": False}).eq("license_key", key).execute()
                raise HTTPException(status_code=403, detail="Licence expirée (30 jours dépassés)")
        
        # On force ici les noms des clés renvoyées pour correspondre au logiciel
        return {
            "status": "authorized",
            "email": user_info.get("email"), # Vérifie que 'email' est bien le nom dans Supabase
            "data": user_info.get("data_cloud") # Vérifie que 'data_cloud' est bien le nom dans Supabase
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
        if not response.data:
            raise HTTPException(status_code=404, detail="Clé introuvable")
    
    

        



