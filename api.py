from fastapi import FastAPI, HTTPException, Header, Depends
from supabase import create_client
import os
import psycopg2
from psycopg2 import sql
from datetime import datetime
from dateutil import parser
from typing import Optional

app = FastAPI()

# --- CONFIGURATION ---
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")
# Tu dois ajouter cette variable sur Railway (URI de connexion PostgreSQL URI)
DATABASE_URL = os.getenv("DATABASE_URL") 

supabase = create_client(SUPABASE_URL, SUPABASE_KEY)

# --- FONCTIONS UTILITAIRES ---

def get_db_conn():
    """Crée une connexion fraîche à la base de données"""
    return psycopg2.connect(DATABASE_URL)

def verifier_licence_et_get_schema(x_license_key: str = Header(...)):
    """
    C'est le garde du corps. Il vérifie la licence à chaque appel API.
    Il renvoie le nom du schéma SQL propre au client.
    """
    try:
        response = supabase.table("clients").select("*").eq("license_key", x_license_key).execute()
        if not response.data:
            raise HTTPException(status_code=401, detail="Licence invalide")
        
        user = response.data[0]
        if not user.get("is_active"):
            raise HTTPException(status_code=403, detail="Licence désactivée")

        # Vérif expiration
        exp_date_str = user.get("expires_at")
        if exp_date_str:
            expiration = parser.parse(exp_date_str)
            if datetime.now().astimezone() > expiration.astimezone():
                supabase.table("clients").update({"is_active": False}).eq("license_key", x_license_key).execute()
                raise HTTPException(status_code=403, detail="Licence expirée")

        # On crée un nom de schéma unique basé sur la clé (nettoyée)
        # Exemple: schema_abc123
        schema_name = f"client_{x_license_key[:8].lower()}"
        return schema_name
    except HTTPException as he:
        raise he
    except Exception:
        raise HTTPException(status_code=500, detail="Erreur lors de la vérification")

# --- ROUTES API ---

@app.get("/")
def home():
    return {"status": "API SaaS Opérationnelle"}

@app.get("/verify/{key}")
def public_verify(key: str):
    """Utilisé par l'écran de démarrage du logiciel"""
    return verifier_licence_et_get_schema(x_license_key=key)

# --- INITIALISATION BASE DE DONNEES ---
@app.post("/db/init")
def init_db(schema: str = Depends(verifier_licence_et_get_schema)):
    conn = get_db_conn()
    cur = conn.cursor()
    """Utilisé par l'écran de démarrage du logiciel pour valider la clé"""
    try:
        # On vérifie la licence
        response = supabase.table("clients").select("*").eq("license_key", key).execute()
        
        if not response.data:
            raise HTTPException(status_code=404, detail="Clé inexistante")
        
        user = response.data[0]
        
        # Vérif si active
        if not user.get("is_active"):
            raise HTTPException(status_code=403, detail="Licence désactivée")
            
        # Vérif expiration
        exp_date_str = user.get("expires_at")
        if exp_date_str:
            expiration = parser.parse(exp_date_str)
            if datetime.now().astimezone() > expiration.astimezone():
                supabase.table("clients").update({"is_active": False}).eq("license_key", key).execute()
                raise HTTPException(status_code=403, detail="Licence expirée")

        # ✅ ON RENVOIE UN DICTIONNAIRE (JSON) ET NON UNE CHAÎNE
        return {
            "status": "authorized",
            "email": user.get("email"),
            "message": "Licence valide"
        }
        
    except HTTPException as he:
        raise he
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erreur serveur: {str(e)}")
    try:
        # 1. Création du schéma client
        cur.execute(f"CREATE SCHEMA IF NOT EXISTS {schema};")
        cur.execute(f"SET search_path TO {schema};")
        
        # 2. Création des tables si elles n'existent pas
        cur.execute("""
            CREATE TABLE IF NOT EXISTS utilisateurs (
                id SERIAL PRIMARY KEY,
                username TEXT UNIQUE,
                password TEXT,
                role TEXT
            );
            CREATE TABLE IF NOT EXISTS categories (
                id SERIAL PRIMARY KEY,
                nom TEXT UNIQUE
            );
            CREATE TABLE IF NOT EXISTS produits (
                id SERIAL PRIMARY KEY,
                nom TEXT,
                prix DECIMAL,
                quantite INTEGER,
                categorie_id INTEGER REFERENCES categories(id),
                image_path TEXT
            );
            CREATE TABLE IF NOT EXISTS journal_stock (
                id SERIAL PRIMARY KEY,
                produit_id INTEGER REFERENCES produits(id),
                quantite INTEGER,
                date_entree TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
            CREATE TABLE IF NOT EXISTS ventes (
                id SERIAL PRIMARY KEY,
                produit_id INTEGER REFERENCES produits(id),
                quantite INTEGER,
                prix_unitaire DECIMAL,
                date_vente TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
            CREATE TABLE IF NOT EXISTS configuration (
                cle TEXT PRIMARY KEY,
                valeur TEXT
            );
        """)
        
        # 3. Création admin par défaut si vide
        cur.execute("SELECT COUNT(*) FROM utilisateurs")
        if cur.fetchone()[0] == 0:
            cur.execute("INSERT INTO utilisateurs (username, password, role) VALUES ('admin', 'admin', 'Gérant')")
        
        # 4. Taux par défaut
        cur.execute("INSERT INTO configuration (cle, valeur) VALUES ('taux_usd_cdf', '2800') ON CONFLICT DO NOTHING")
        
        # 5. Catégorie par défaut
        cur.execute("INSERT INTO categories (id, nom) VALUES (1, 'Général') ON CONFLICT DO NOTHING")

        conn.commit()
        return {"status": "success", "message": f"Espace {schema} prêt"}
    except Exception as e:
        conn.rollback()
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        cur.close()
        conn.close()

# --- GESTION UTILISATEURS ---
@app.post("/users/auth")
def auth_user(data: dict, schema: str = Depends(verifier_licence_et_get_schema)):
    conn = get_db_conn()
    cur = conn.cursor()
    cur.execute(f"SET search_path TO {schema}")
    cur.execute("SELECT id, role FROM utilisateurs WHERE username = %s AND password = %s", (data['username'], data['password']))
    user = cur.fetchone()
    conn.close()
    if user:
        return {"authorized": True, "user": {"id": user[0], "role": user[1]}}
    return {"authorized": False}

@app.get("/users")
def get_users(schema: str = Depends(verifier_licence_et_get_schema)):
    conn = get_db_conn()
    cur = conn.cursor()
    cur.execute(f"SET search_path TO {schema}")
    cur.execute("SELECT id, username, role FROM utilisateurs")
    users = cur.fetchall()
    conn.close()
    return {"data": users}

# --- GESTION PRODUITS ---
@app.get("/produits")
def get_prods(cat_id: Optional[int] = None, schema: str = Depends(verifier_licence_et_get_schema)):
    conn = get_db_conn()
    cur = conn.cursor()
    cur.execute(f"SET search_path TO {schema}")
    if cat_id:
        cur.execute("SELECT p.id, p.nom, p.prix, p.quantite, c.nom, p.image_path FROM produits p JOIN categories c ON p.categorie_id = c.id WHERE p.categorie_id = %s", (cat_id,))
    else:
        cur.execute("SELECT p.id, p.nom, p.prix, p.quantite, c.nom, p.image_path FROM produits p JOIN categories c ON p.categorie_id = c.id")
    res = cur.fetchall()
    conn.close()
    return {"data": res}

@app.post("/produits")
def add_prod(p: dict, schema: str = Depends(verifier_licence_et_get_schema)):
    conn = get_db_conn()
    cur = conn.cursor()
    cur.execute(f"SET search_path TO {schema}")
    cur.execute("INSERT INTO produits (nom, prix, quantite, categorie_id, image_path) VALUES (%s, %s, %s, %s, %s)", 
                (p['nom'], p['prix'], p['quantite'], p['categorie_id'], p['image_path']))
    conn.commit()
    conn.close()
    return {"status": "success"}

# --- GESTION VENTES ---
@app.post("/ventes")
def make_sale(v: dict, schema: str = Depends(verifier_licence_et_get_schema)):
    conn = get_db_conn()
    cur = conn.cursor()
    try:
        cur.execute(f"SET search_path TO {schema}")
        # Vérif stock
        cur.execute("SELECT quantite, prix FROM produits WHERE id = %s", (v['produit_id'],))
        p_info = cur.fetchone()
        if not p_info or p_info[0] < v['quantite']:
            return {"status": "error", "message": "Stock insuffisant"}
        
        # Déduire stock
        cur.execute("UPDATE produits SET quantite = quantite - %s WHERE id = %s", (v['quantite'], v['produit_id']))
        # Enregistrer vente
        cur.execute("INSERT INTO ventes (produit_id, quantite, prix_unitaire) VALUES (%s, %s, %s)", 
                    (v['produit_id'], v['quantite'], p_info[1]))
        conn.commit()
        return {"status": "success"}
    except Exception as e:
        conn.rollback()
        return {"status": "error", "message": str(e)}
    finally:
        conn.close()

# --- GESTION TAUX ---
@app.get("/config/taux")
def get_taux(schema: str = Depends(verifier_licence_et_get_schema)):
    conn = get_db_conn()
    cur = conn.cursor()
    cur.execute(f"SET search_path TO {schema}")
    cur.execute("SELECT valeur FROM configuration WHERE cle = 'taux_usd_cdf'")
    val = cur.fetchone()
    conn.close()
    return {"valeur": val[0] if val else "2800"}

# NOTE : J'ai omis certaines routes répétitives (DELETE, UPDATE) pour la brièveté, 
# mais la structure est là. Tu peux les ajouter sur le même modèle.

