"""
Atlantic Re IA — Authentication & access control
"""
import streamlit as st


def get_admin_password():
    try: return st.secrets["admin_password"]
    except: return "Admin@AtlanticRe2026"


def get_users_details():
    """
    Retourne les utilisateurs sous forme normalisée.
    Formats acceptés dans st.secrets :
      [users]
      "email" = "CODE"
      ou
      [users."email"]
      code = "CODE"
      poste = "Actuaire"
    """
    fallback = {
        "demo@atlanticre.ia": {
            "code": "DEMO2026",
            "poste": "Utilisateur démo",
            "nom": "Compte Démo",
            "statut": "Actif",
        }
    }
    try:
        raw_users = dict(st.secrets.get("users", {}))
    except Exception:
        raw_users = {}

    if not raw_users:
        return fallback

    details = {}
    for email, value in raw_users.items():
        email_norm = str(email).lower().strip()
        if isinstance(value, dict):
            v = dict(value)
            code_val = str(v.get("code", v.get("password", v.get("cle", "")))).strip()
            details[email_norm] = {
                "code":   code_val,
                "poste":  str(v.get("poste", v.get("role", "Non renseigné"))),
                "nom":    str(v.get("nom", v.get("name", ""))),
                "statut": str(v.get("statut", "Actif")),
            }
        else:
            details[email_norm] = {
                "code":   str(value).strip(),
                "poste":  "Non renseigné",
                "nom":    "",
                "statut": "Actif",
            }
    return details


def get_users():
    """Compatibilité : retourne {email: code}."""
    return {email: info.get("code", "") for email, info in get_users_details().items()}


def check_access(email, code):
    email_norm = email.lower().strip()
    details = get_users_details().get(email_norm, {})
    statut = str(details.get("statut", "Actif")).lower()
    if statut in ["suspendu", "bloqué", "bloque", "inactif"]:
        return False
    return details.get("code", "") == code.strip()
