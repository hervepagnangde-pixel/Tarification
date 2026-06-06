"""
Atlantic Re IA — Database module
PostgreSQL (Supabase) avec fallback SQLite local.
"""
import os, json
import streamlit as st
import numpy as np
import pandas as pd
from datetime import datetime

def _get_db_url():
    """Lit DATABASE_URL depuis st.secrets à chaque appel."""
    url = None
    try:
        # Streamlit Cloud secrets
        url = st.secrets.get("DATABASE_URL")
    except Exception:
        pass
    if not url:
        # Fallback env variable
        url = os.environ.get("DATABASE_URL")
    if not url:
        return None
    # Accepte "postgres://" ET "postgresql://"
    if url.startswith("postgres://"):
        url = url.replace("postgres://", "postgresql://", 1)
    return url if url.startswith("postgresql://") else None

def _get_conn():
    """Retourne une connexion SQLite ou PostgreSQL selon la config."""
    url = _get_db_url()
    if url:
        import psycopg2
        return psycopg2.connect(url), "pg"
    import sqlite3
    _DB_PATH = os.environ.get("ATLANTICRE_DB", "/tmp/atlanticre_sessions.db")
    return sqlite3.connect(_DB_PATH), "sqlite"

def _ph(n=1):
    """Placeholder SQL : %s pour PostgreSQL, ? pour SQLite."""
    url = _get_db_url()
    if url: return ",".join(["%s"]*n) if n>1 else "%s"
    return ",".join(["?"]*n) if n>1 else "?"

def db_init():
    """Crée les tables si elles n'existent pas."""
    con, db = _get_conn()
    cur = con.cursor()
    if db == "pg":
        cur.execute("""
            CREATE TABLE IF NOT EXISTS sessions (
                id          SERIAL PRIMARY KEY,
                user_email  TEXT NOT NULL,
                nom_session TEXT,
                gnpi        FLOAT,
                programme   TEXT,
                version_code TEXT DEFAULT '1.0',
                created_at  TIMESTAMP DEFAULT NOW(),
                updated_at  TIMESTAMP DEFAULT NOW()
            )""")
        cur.execute("""
            CREATE TABLE IF NOT EXISTS resultats (
                id         SERIAL PRIMARY KEY,
                session_id INTEGER REFERENCES sessions(id) ON DELETE CASCADE,
                etape      TEXT,
                data_json  TEXT,
                created_at TIMESTAMP DEFAULT NOW()
            )""")
        cur.execute("""
            CREATE TABLE IF NOT EXISTS audit_log (
                id         SERIAL PRIMARY KEY,
                user_email TEXT,
                session_id INTEGER,
                action     TEXT,
                details    TEXT,
                ip_hash    TEXT,
                created_at TIMESTAMP DEFAULT NOW()
            )""")
    else:
        cur.executescript("""
            CREATE TABLE IF NOT EXISTS sessions (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                user_email  TEXT NOT NULL,
                nom_session TEXT,
                gnpi        REAL,
                programme   TEXT,
                version_code TEXT DEFAULT '1.0',
                created_at  TEXT DEFAULT (datetime('now','localtime')),
                updated_at  TEXT DEFAULT (datetime('now','localtime'))
            );
            CREATE TABLE IF NOT EXISTS resultats (
                id         INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id INTEGER REFERENCES sessions(id) ON DELETE CASCADE,
                etape      TEXT,
                data_json  TEXT,
                created_at TEXT DEFAULT (datetime('now','localtime'))
            );
            CREATE TABLE IF NOT EXISTS audit_log (
                id         INTEGER PRIMARY KEY AUTOINCREMENT,
                user_email TEXT,
                session_id INTEGER,
                action     TEXT,
                details    TEXT,
                ip_hash    TEXT,
                created_at TEXT DEFAULT (datetime('now','localtime'))
            );""")
    con.commit(); con.close()


def db_audit(user_email, action, details="", session_id=None):
    """Enregistre une action dans le journal d'audit."""
    try:
        import hashlib
        db_init()
        con, db = _get_conn(); p = _ph()
        # Hash de l'email pour pseudo-anonymisation
        ip_hash = hashlib.sha256(user_email.encode()).hexdigest()[:12]
        cur = con.cursor()
        cur.execute(
            f"INSERT INTO audit_log (user_email,session_id,action,details,ip_hash) VALUES ({_ph(5)})",
            (user_email, session_id, action, details[:500], ip_hash))
        con.commit(); con.close()
    except Exception:
        pass  # Audit ne doit jamais bloquer l'application

def db_save_session(user_email, gnpi_val, tranches, nom=None):
    db_init()
    import json
    sid = st.session_state.get("db_session_id")
    prog_json = json.dumps(tranches, default=str)
    con, db = _get_conn(); cur = con.cursor()
    p = _ph()
    if sid:
        if db == "pg":
            cur.execute(f"UPDATE sessions SET gnpi={p},programme={p},updated_at=NOW() WHERE id={p}",
                        (gnpi_val, prog_json, sid))
        else:
            cur.execute(f"UPDATE sessions SET gnpi={p},programme={p},updated_at=datetime('now','localtime') WHERE id={p}",
                        (gnpi_val, prog_json, sid))
    else:
        nom_auto = nom or f"Session {datetime.now().strftime('%d/%m/%Y %H:%M')}"
        if db == "pg":
            cur.execute(f"INSERT INTO sessions (user_email,gnpi,programme,nom_session) VALUES ({_ph(4)}) RETURNING id",
                        (user_email, gnpi_val, prog_json, nom_auto))
            sid = cur.fetchone()[0]
        else:
            cur.execute(f"INSERT INTO sessions (user_email,gnpi,programme,nom_session) VALUES ({_ph(4)})",
                        (user_email, gnpi_val, prog_json, nom_auto))
            sid = cur.lastrowid
        st.session_state["db_session_id"] = sid
    con.commit(); con.close()
    return sid

def db_save_etape(etape, data):
    db_init()
    import json
    sid = st.session_state.get("db_session_id")
    if not sid: return
    con, db = _get_conn(); cur = con.cursor(); p = _ph()
    # Vérifie que la session existe dans CETTE base (SQLite → PG peut diverger)
    cur.execute(f"SELECT id FROM sessions WHERE id={p}", (sid,))
    if not cur.fetchone():
        # Session introuvable → réinitialise et crée une nouvelle
        st.session_state.pop("db_session_id", None)
        con.close()
        return  # sera recréée au prochain db_save_session
    cur.execute(f"DELETE FROM resultats WHERE session_id={p} AND etape={p}", (sid, etape))
    cur.execute(f"INSERT INTO resultats (session_id,etape,data_json) VALUES ({_ph(3)})",
                (sid, etape, json.dumps(data, default=str)))
    con.commit(); con.close()

def db_load_session(session_id):
    db_init()
    import json, pandas as pd
    con, db = _get_conn(); cur = con.cursor(); p = _ph()
    cur.execute(f"SELECT etape,data_json FROM resultats WHERE session_id={p}", (session_id,))
    rows = cur.fetchall()
    cur.execute(f"SELECT gnpi,programme,nom_session FROM sessions WHERE id={p}", (session_id,))
    sess = cur.fetchone(); con.close()
    if not sess: return None
    st.session_state["db_session_id"] = session_id
    for etape, data_json in rows:
        d = json.loads(data_json)
        if etape == "bc":   st.session_state["resultats_bc"] = d
        elif etape == "sim":st.session_state["resultats_sim"] = d
        elif etape == "mkt":
            st.session_state["resultats_mkt"]  = d.get("resultats_mkt",[])
            st.session_state["taux_mkt_final"] = d.get("taux_mkt_final",[])
        elif etape == "rapport":
            rows_r = d.get("rows",[])
            if rows_r:
                st.session_state["df_rapport"]   = pd.DataFrame(rows_r)
                st.session_state["prime_totale"] = d.get("prime_totale", 0)
    return sess[2] or f"Session #{session_id}"

def db_list_sessions(user_email):
    db_init()
    con, db = _get_conn(); cur = con.cursor(); p = _ph()
    cur.execute(f"""SELECT id,nom_session,gnpi,
        {"to_char(created_at,'DD/MM/YYYY HH24:MI')" if db=="pg" else "created_at"},
        {"to_char(updated_at,'DD/MM/YYYY HH24:MI')" if db=="pg" else "updated_at"}
        FROM sessions WHERE user_email={p} ORDER BY updated_at DESC LIMIT 50""",
        (user_email,))
    rows = cur.fetchall(); con.close()
    return rows

def db_delete_session(session_id):
    db_init()
    con, _ = _get_conn(); p = _ph()
    con.execute(f"DELETE FROM sessions WHERE id={p}", (session_id,))
    con.commit(); con.close()

def db_get_previous_session(user_email, current_id):
    db_init()
    import json
    con, db = _get_conn(); cur = con.cursor(); p = _ph()
    cur.execute(f"""SELECT id FROM sessions WHERE user_email={p} AND id!={p}
        ORDER BY updated_at DESC LIMIT 1""", (user_email, current_id or 0))
    row = cur.fetchone()
    if not row: con.close(); return None
    cur.execute(f"SELECT data_json FROM resultats WHERE session_id={p} AND etape='rapport'", (row[0],))
    rr = cur.fetchone(); con.close()
    if rr: return json.loads(rr[0]).get("rows",[])
    return None
