from fastapi import FastAPI, HTTPException
from supabase import create_client
import os

app = FastAPI()

# Utilise tes identifiants Supabase ici
URL = "https://icnlaumwdyrebbzmexiu.supabase.co"
KEY = "sb_publishable_5JQlhyKV7IO5gLjMDMRxfA_bs2FMTGd"
supabase = create_client(URL, KEY)

@app.get("/")
def home():
    return {"message": "Serveur de vérification actif"}

@app.get("/verify/{key}")
def verify_license(key: str):
    # On cherche dans la table 'clients' si la clé existe
    try:
        response = supabase.table("clients").select("*").eq("license_key", key).eq("is_active", True).execute()
        
        if not response.data:
            raise HTTPException(status_code=403, detail="Clé invalide ou compte désactivé")
        
        # Si trouvé, on renvoie les infos du client (ton 'logiciel' pourra les utiliser)
        user_info = response.data[0]
        return {
            "status": "authorized",
            "client_email": user_info['email'],
            "data_cloud": user_info.get('data_cloud', {}) # Les datas dont tu parlais
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
        "message": "Accès autorisé",
        "user_data": user["data_cloud"]

    }

