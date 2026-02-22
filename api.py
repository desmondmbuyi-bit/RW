from fastapi import FastAPI, HTTPException, Header, Depends
from supabase import create_client
import os
import psycopg2
from psycopg2 import sql
from datetime import datetime
from dateutil import parser
from typing import Optional
from fastapi.middleware.cors import CORSMiddleware

app = FastAPI()

# --- CONFIGURATION ---
# Ces variables doivent être définies dans l'onglet "Variables" sur Railway
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")
DATABASE_URL = os.getenv("DATABASE_URL") 

supabase = create_client(SUPABASE_URL, SUPABASE_KEY)

# --- FONCTION DE CONNEXION DB ---
def get_db_conn():
    return psycopg2.connect(DATABASE_URL)

# --- LE GARDE DU CORPS (Vérification de Licence) ---
def verifier_licence_et_get_schema(x_license_key: str = Header(...)):
    """
    Vérifie la validité de la licence et retourne le nom du schéma SQL associé.
    Utilisé comme dépendance pour protéger toutes les routes privées.
    """
    try:
        response = supabase.table("clients").select("*").eq("license_key", x_license_key).execute()
        if not response.data:
            raise HTTPException(status_code=401, detail="Licence invalide")
        
        user = response.data[0]
        if not user.get("is_active"):
            raise HTTPException(status_code=403, detail="Licence désactivée")

        # Vérification de l'expiration
        exp_date_str = user.get("expires_at")
        if exp_date_str:
            expiration = parser.parse(exp_date_str)
            if datetime.now().astimezone() > expiration.astimezone():
                # Désactivation automatique en base si expiré
                supabase.table("clients").update({"is_active": False}).eq("license_key", x_license_key).execute()
                raise HTTPException(status_code=403, detail="Licence expirée")

        # Nom de schéma unique par client (basé sur les 8 premiers caractères de la clé)
        schema_name = f"client_{x_license_key[:8].lower()}"
        return schema_name
    except HTTPException:
        raise
    except Exception as e:
        print(f"Erreur Licence: {e}")
        raise HTTPException(status_code=500, detail="Erreur lors de la vérification")

# --- ROUTES PUBLIQUES ---

@app.get("/")
def home():
    return {"status": "API SaaS v2.0 opérationnelle"}

@app.get("/verify/{key}")
def public_verify(key: str):
    """
    Route appelée par le logiciel au démarrage. 
    Correction de l'erreur 'AttributeError' : renvoie un dictionnaire JSON.
    """
    try:
        # On utilise la fonction de vérification existante
        schema = verifier_licence_et_get_schema(x_license_key=key)
        
        # On récupère les infos client pour l'affichage
        response = supabase.table("clients").select("email").eq("license_key", key).execute()
        email = response.data[0].get("email") if response.data else "Utilisateur"

        return {
            "status": "authorized",
            "email": email,
            "schema": schema
        }
    except HTTPException as he:
        raise he
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# --- ROUTES PRIVÉES (Nécessitent la clé de licence dans le header) ---

@app.post("/db/init")
def init_db(schema: str = Depends(verifier_licence_et_get_schema)):
    """Crée l'architecture des tables pour le client s'il est nouveau"""
    conn = get_db_conn()
    cur = conn.cursor()
    try:
        cur.execute(f"CREATE SCHEMA IF NOT EXISTS {schema};")
        cur.execute(f"SET search_path TO {schema};")
        
        cur.execute("""
            CREATE TABLE IF NOT EXISTS utilisateurs (id SERIAL PRIMARY KEY, username TEXT UNIQUE, password TEXT, role TEXT);
            CREATE TABLE IF NOT EXISTS categories (id SERIAL PRIMARY KEY, nom TEXT UNIQUE);
            CREATE TABLE IF NOT EXISTS produits (id SERIAL PRIMARY KEY, nom TEXT, prix DECIMAL, quantite INTEGER, categorie_id INTEGER REFERENCES categories(id), image_path TEXT);
            CREATE TABLE IF NOT EXISTS journal_stock (id SERIAL PRIMARY KEY, produit_id INTEGER REFERENCES produits(id), quantite INTEGER, date_entree TIMESTAMP DEFAULT CURRENT_TIMESTAMP);
            CREATE TABLE IF NOT EXISTS ventes (id SERIAL PRIMARY KEY, produit_id INTEGER REFERENCES produits(id), quantite INTEGER, prix_unitaire DECIMAL, date_vente TIMESTAMP DEFAULT CURRENT_TIMESTAMP);
            CREATE TABLE IF NOT EXISTS configuration (cle TEXT PRIMARY KEY, valeur TEXT);
        """)
        
        # Données par défaut
        cur.execute("SELECT COUNT(*) FROM utilisateurs")
        if cur.fetchone()[0] == 0:
            cur.execute("INSERT INTO utilisateurs (username, password, role) VALUES ('admin', 'admin', 'Gérant')")
        
        cur.execute("INSERT INTO configuration (cle, valeur) VALUES ('taux_usd_cdf', '2800') ON CONFLICT DO NOTHING")
        cur.execute("INSERT INTO categories (id, nom) VALUES (1, 'Général') ON CONFLICT DO NOTHING")

        conn.commit()
        return {"status": "success"}
    except Exception as e:
        conn.rollback()
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        conn.close()

# --- UTILISATEURS ---
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

@app.post("/users")
def add_user(u: dict, schema: str = Depends(verifier_licence_et_get_schema)):
    conn = get_db_conn()
    cur = conn.cursor()
    try:
        cur.execute(f"SET search_path TO {schema}")
        cur.execute("INSERT INTO utilisateurs (username, password, role) VALUES (%s, %s, %s)", (u['username'], u['password'], u['role']))
        conn.commit()
        return {"status": "success"}
    except:
        return {"status": "error"}
    finally: conn.close()

@app.delete("/users/{uid}")
def del_user(uid: int, schema: str = Depends(verifier_licence_et_get_schema)):
    conn = get_db_conn()
    cur = conn.cursor()
    cur.execute(f"SET search_path TO {schema}")
    cur.execute("DELETE FROM utilisateurs WHERE id = %s", (uid,))
    conn.commit()
    conn.close()
    return {"status": "success"}

# --- CATEGORIES ---
@app.get("/categories")
def get_cats(schema: str = Depends(verifier_licence_et_get_schema)):
    conn = get_db_conn()
    cur = conn.cursor()
    cur.execute(f"SET search_path TO {schema}")
    cur.execute("SELECT id, nom FROM categories")
    res = cur.fetchall()
    conn.close()
    return {"data": res}

@app.post("/categories")
def add_cat(c: dict, schema: str = Depends(verifier_licence_et_get_schema)):
    conn = get_db_conn()
    cur = conn.cursor()
    try:
        cur.execute(f"SET search_path TO {schema}")
        cur.execute("INSERT INTO categories (nom) VALUES (%s)", (c['nom'],))
        conn.commit()
        return {"status": "success"}
    except: return {"status": "error"}
    finally: conn.close()

@app.delete("/categories/{cid}")
def del_cat(cid: int, schema: str = Depends(verifier_licence_et_get_schema)):
    conn = get_db_conn()
    cur = conn.cursor()
    cur.execute(f"SET search_path TO {schema}")
    cur.execute("DELETE FROM categories WHERE id = %s", (cid,))
    conn.commit()
    conn.close()
    return {"status": "success"}

# --- PRODUITS ---
@app.get("/produits")
def get_prods(cat_id: Optional[str] = None, schema: str = Depends(verifier_licence_et_get_schema)):
    conn = get_db_conn()
    cur = conn.cursor()
    cur.execute(f"SET search_path TO {schema}")
    if cat_id and cat_id != "Toutes":
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

@app.put("/produits/{pid}")
def update_prod(pid: int, p: dict, schema: str = Depends(verifier_licence_et_get_schema)):
    conn = get_db_conn()
    cur = conn.cursor()
    cur.execute(f"SET search_path TO {schema}")
    cur.execute("UPDATE produits SET nom=%s, prix=%s, quantite=%s, categorie_id=%s, image_path=%s WHERE id=%s",
                (p['nom'], p['prix'], p['quantite'], p['categorie_id'], p['image_path'], pid))
    conn.commit()
    conn.close()
    return {"status": "success"}

@app.delete("/produits/{pid}")
def del_prod(pid: int, schema: str = Depends(verifier_licence_et_get_schema)):
    conn = get_db_conn()
    cur = conn.cursor()
    cur.execute(f"SET search_path TO {schema}")
    cur.execute("DELETE FROM produits WHERE id = %s", (pid,))
    conn.commit()
    conn.close()
    return {"status": "success"}

# --- STOCK ---
@app.post("/stock/entree")
def add_stock(s: dict, schema: str = Depends(verifier_licence_et_get_schema)):
    conn = get_db_conn()
    cur = conn.cursor()
    cur.execute(f"SET search_path TO {schema}")
    cur.execute("UPDATE produits SET quantite = quantite + %s WHERE id = %s", (s['quantite'], s['produit_id']))
    cur.execute("INSERT INTO journal_stock (produit_id, quantite) VALUES (%s, %s)", (s['produit_id'], s['quantite']))
    conn.commit()
    conn.close()
    return {"status": "success"}

@app.get("/stock/journal")
def get_stock_log(schema: str = Depends(verifier_licence_et_get_schema)):
    conn = get_db_conn()
    cur = conn.cursor()
    cur.execute(f"SET search_path TO {schema}")
    cur.execute("SELECT j.date_entree, p.nom, j.quantite FROM journal_stock j JOIN produits p ON j.produit_id = p.id ORDER BY j.date_entree DESC")
    res = cur.fetchall()
    conn.close()
    return {"data": res}

# --- VENTES ---
@app.post("/ventes")
def make_sale(v: dict, schema: str = Depends(verifier_licence_et_get_schema)):
    conn = get_db_conn()
    cur = conn.cursor()
    try:
        cur.execute(f"SET search_path TO {schema}")
        cur.execute("SELECT quantite, prix FROM produits WHERE id = %s", (v['produit_id'],))
        p = cur.fetchone()
        if not p or p[0] < v['quantite']: return {"status": "error", "message": "Stock insuffisant"}
        
        cur.execute("UPDATE produits SET quantite = quantite - %s WHERE id = %s", (v['quantite'], v['produit_id']))
        cur.execute("INSERT INTO ventes (produit_id, quantite, prix_unitaire) VALUES (%s, %s, %s)", (v['produit_id'], v['quantite'], p[1]))
        conn.commit()
        return {"status": "success"}
    except Exception as e: return {"status": "error", "message": str(e)}
    finally: conn.close()

@app.get("/ventes")
def get_sales(debut: str, fin: str, schema: str = Depends(verifier_licence_et_get_schema)):
    conn = get_db_conn()
    cur = conn.cursor()
    cur.execute(f"SET search_path TO {schema}")
    query = """
        SELECT v.date_vente, p.nom, v.quantite, v.prix_unitaire, (v.quantite * v.prix_unitaire) as total 
        FROM ventes v JOIN produits p ON v.produit_id = p.id 
        WHERE v.date_vente::date BETWEEN %s AND %s ORDER BY v.date_vente DESC
    """
    cur.execute(query, (debut, fin))
    res = cur.fetchall()
    conn.close()
    return {"data": res}

# --- CONFIG ---
@app.get("/config/taux")
def get_taux(schema: str = Depends(verifier_licence_et_get_schema)):
    conn = get_db_conn()
    cur = conn.cursor()
    cur.execute(f"SET search_path TO {schema}")
    cur.execute("SELECT valeur FROM configuration WHERE cle = 'taux_usd_cdf'")
    val = cur.fetchone()
    conn.close()
    return {"valeur": val[0] if val else "2800"}

@app.post("/config/taux")
def set_taux(t: dict, schema: str = Depends(verifier_licence_et_get_schema)):
    conn = get_db_conn()
    cur = conn.cursor()
    cur.execute(f"SET search_path TO {schema}")
    cur.execute("INSERT INTO configuration (cle, valeur) VALUES ('taux_usd_cdf', %s) ON CONFLICT (cle) DO UPDATE SET valeur = %s", (t['valeur'], t['valeur']))
    conn.commit()
    conn.close()
    return {"status": "success"}

