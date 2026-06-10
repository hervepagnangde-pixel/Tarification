"""
Atlantic Re IA — Application principale (app.py)
Point d'entrée Streamlit. Tous les modules métier sont dans modules/.

Structure : 
  modules/db.py, pdf_gen.py, notifications.py, auth.py, ui.py
  modules/prompts.py, actuarial.py, optimization.py, resources.py 
  modules/agents_v2.py, labo.py, agent_python.py, tools_exec.py
"""
import streamlit as st
import anthropic
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import json
import secrets as secrets_lib
from PIL import Image
import os
from datetime import datetime

# ── Imports modules ───────────────────────────────────────────────────────────
from modules.db import (
    _get_db_url, _get_conn, _ph,
    db_init, db_audit, db_save_session, db_save_etape,
    db_load_session, db_list_sessions, db_delete_session, db_get_previous_session,
)
from modules.pdf_gen import (
    generer_pdf_rapport, _pdf_signature_qr,
    envoyer_webhook_notification, generer_pptx_rapport,
)
from modules.notifications import (
    _normaliser_destinataires_email, envoyer_notification_email,
    notifier_consultation, generer_pdf_rapport_courant,
    envoyer_rapport_pdf_email, get_destinataires_notifications_agent,
)
from modules.auth import (
    get_admin_password, get_users_details, get_users, check_access,
)
from modules.ui import (
    CSS_ATLANTICRE, card, section_header, tableau_resultats, progress_steps,
    tooltip, html_glossaire_inline, GLOSSAIRE_ACTUARIEL,
)
from modules.prompts import (
    prompt_inputs, _charger_few_shot_dynamiques,
    build_prompt, claude_stream, guide_prompt,
)
from modules.actuarial import (
    selectionner_seuil_pareto, identifier_sinistres_majeurs_gpd,
    identifier_sinistres_majeurs, section_analyse_distributions,
    buehlmann_straub_credibility, bootstrap_ci_bc,
    _hill_estimates, _mean_excess, _gertensgarbe_k,
    _fit_severity, _fit_frequency, _threshold_table,
    detecter_seuil_optimal_tve, comparer_lois_ajustement, afficher_selection_loi,
)
from modules.optimization import (
    _json_safe, optimiser_programme_variantes, afficher_variantes_optimisation,
    afficher_panneau_audit, _lookup_taux, _lookup_result,
)
from modules.resources import (
    RESSOURCES_ACTUARIELLES, SCRIPTS_R_TARIFICATION,
    afficher_ressources_actuarielles, afficher_integration_r,
)
from modules.agents_v2 import (
    AgentRaisonnement, AgentCritique, AgentML, AgentMemoireMetier,
    AgentChallenger, AgentOptimisationProgramme,
    afficher_plan_agentique, afficher_critique_agentique,
    afficher_memoire_metier, afficher_challenger,
    afficher_optimisation_avancee, afficher_ml_agentique,
)
from modules.labo import AgentLaboTarification, _labo_display_section
from modules.agent_python import AgentActuarielPython
from modules.tools_exec import (
    _executer_burning_cost, _executer_simulation, _executer_market_curve,
)

# ═══════════════════════════════════════════════════════════════════════════════
# SET PAGE CONFIG
# ═══════════════════════════════════════════════════════════════════════════════
try:
    icon = Image.open("icon.png")
    st.set_page_config(page_title="Atlantic Re IA", layout="wide", page_icon=icon)
except:
    st.set_page_config(page_title="Atlantic Re IA", layout="wide", page_icon=None)


# ═══════════════════════════════════════════════════════════════════════════════
# AUTHENTICATION
# ═══════════════════════════════════════════════════════════════════════════════
# ACCESS CONTROL
# ════════════════════════════════════════════

def get_admin_password():
    try: return st.secrets["admin_password"]
    except: return "Admin@AtlanticRe2026"

def get_users():
    try: return dict(st.secrets["users"])
    except: return {"demo@atlanticre.ia": "DEMO2026"}

def check_access(email, code):
    return get_users().get(email.lower().strip()) == code.strip()

if "authenticated" not in st.session_state:
    st.session_state["authenticated"] = False

if not st.session_state["authenticated"]:
    st.markdown("""
    <style>
    .stApp { background: linear-gradient(135deg, #1a1a1a 0%, #2d8a4e 100%); }
    .stButton > button { background-color: #1a1a1a; color: white; border: 2px solid #2d8a4e; border-radius: 8px; padding: 8px 20px; font-weight: 600; }
    .stButton > button:hover { background-color: #2d8a4e; }
    </style>
    """, unsafe_allow_html=True)
    col1, col2, col3 = st.columns([1,2,1])
    with col2:
        st.markdown("<div style='text-align:center; padding:40px 0 20px 0'>", unsafe_allow_html=True)
        st.markdown("# ")
        st.markdown("### Atlantic Re IA")
        st.caption("Tarification Réassurance Non-Proportionnelle")
        st.markdown("</div>", unsafe_allow_html=True)
        st.divider()
        email = st.text_input(" Adresse email", placeholder="votre@email.com", key="login_email")
        code  = st.text_input(" Code d'accès", type="password", placeholder="CODE123", key="login_code")
        if st.button("Se connecter", type="primary", use_container_width=True):
            if check_access(email, code):
                st.session_state["authenticated"] = True
                st.session_state["user_email"]    = email
                st.rerun()
            else:
                st.error(" Email ou code d'accès incorrect")
        st.caption("Accès réservé. Contactez l'administrateur.")
    st.stop()

# ════════════════════════════════════════════
# LANDING PAGE
# ════════════════════════════════════════════

if "page" not in st.session_state:
    st.session_state["page"] = "landing"
    # Auto-init DB
    try: db_init()
    except: pass

if st.session_state["page"] == "landing":
    st.markdown("""
    <style>
    .stApp { background: linear-gradient(135deg, #0d0d0d 0%, #1a1a1a 50%, #0d2b1a 100%) !important; }
    </style>
    """, unsafe_allow_html=True)

    st.markdown("""
    <div style="display:flex;flex-direction:column;align-items:center;justify-content:center;
        min-height:85vh;text-align:center;padding:40px 20px">
        <div style="width:160px;height:160px;margin-bottom:32px">
            <svg viewBox="0 0 160 160" xmlns="http://www.w3.org/2000/svg">
                <circle cx="80" cy="80" r="75" fill="none" stroke="#2d8a4e" stroke-width="2" opacity="0.3"/>
                <circle cx="80" cy="80" r="65" fill="none" stroke="#2d8a4e" stroke-width="1" opacity="0.2"/>
                <circle cx="80" cy="80" r="55" fill="#1a1a1a" stroke="#2d8a4e" stroke-width="2"/>
                <circle cx="80" cy="75" r="32" fill="#2d2d2d"/>
                <circle cx="68" cy="70" r="6" fill="#2d8a4e"/>
                <circle cx="92" cy="70" r="6" fill="#2d8a4e"/>
                <circle cx="70" cy="69" r="2" fill="white"/>
                <circle cx="94" cy="69" r="2" fill="white"/>
                <path d="M 67 83 Q 80 93 93 83" stroke="#2d8a4e" stroke-width="2.5" fill="none" stroke-linecap="round"/>
                <line x1="80" y1="43" x2="80" y2="30" stroke="#2d8a4e" stroke-width="2"/>
                <circle cx="80" cy="27" r="5" fill="#2d8a4e"/>
                <line x1="68" y1="45" x2="58" y2="33" stroke="#2d8a4e" stroke-width="1.5"/>
                <circle cx="55" cy="30" r="3" fill="#2d8a4e" opacity="0.6"/>
                <line x1="92" y1="45" x2="102" y2="33" stroke="#2d8a4e" stroke-width="1.5"/>
                <circle cx="105" cy="30" r="3" fill="#2d8a4e" opacity="0.6"/>
                <rect x="58" y="100" width="44" height="18" rx="9" fill="#2d8a4e"/>
                <text x="80" y="113" text-anchor="middle" fill="white" font-size="10" font-weight="bold">IA</text>
            </svg>
        </div>
        <h1 style="color:white;font-size:42px;font-weight:800;margin:0 0 8px 0;letter-spacing:-1px;font-family:Inter,sans-serif">
            Atlantic Re <span style="color:#2d8a4e">IA</span>
        </h1>
        <p style="color:#aaa;font-size:16px;margin:0 0 8px 0">Moteur de tarification · Réassurance Non-Proportionnelle</p>
        <p style="color:#666;font-size:13px;margin:0 0 40px 0">Atlantic Re · Automobile · Maroc</p>
        <div style="display:flex;gap:16px;margin-bottom:48px;flex-wrap:wrap;justify-content:center">
            <div style="background:rgba(45,138,78,0.1);border:1px solid rgba(45,138,78,0.3);border-radius:12px;padding:16px 20px;min-width:140px">
                <div style="font-size:24px;margin-bottom:6px"></div>
                <div style="color:white;font-size:13px;font-weight:600">Burning Cost</div>
                <div style="color:#888;font-size:11px">As-If · Stabilisation · CL</div>
            </div>
            <div style="background:rgba(45,138,78,0.1);border:1px solid rgba(45,138,78,0.3);border-radius:12px;padding:16px 20px;min-width:140px">
                <div style="font-size:24px;margin-bottom:6px"></div>
                <div style="color:white;font-size:13px;font-weight:600">Simulation</div>
                <div style="color:#888;font-size:11px">Pareto · Poisson · TVE</div>
            </div>
            <div style="background:rgba(45,138,78,0.1);border:1px solid rgba(45,138,78,0.3);border-radius:12px;padding:16px 20px;min-width:140px">
                <div style="font-size:24px;margin-bottom:6px"></div>
                <div style="color:white;font-size:13px;font-weight:600">Courbe de référence marché</div>
                <div style="color:#888;font-size:11px">Modèle puissance log-log</div>
            </div>
            <div style="background:rgba(45,138,78,0.1);border:1px solid rgba(45,138,78,0.3);border-radius:12px;padding:16px 20px;min-width:140px">
                <div style="font-size:24px;margin-bottom:6px"></div>
                <div style="color:white;font-size:13px;font-weight:600">Assistant d’interprétation actuarielle</div>
                <div style="color:#888;font-size:11px">Analyse · Recommandations</div>
            </div>
        </div>
    </div>
    """, unsafe_allow_html=True)

    col1, col2, col3 = st.columns([1, 2, 1])
    with col2:
        if st.button("  Lancer l'outil de tarification", type="primary", use_container_width=True):
            st.session_state["page"] = "app"
            st.rerun()
        st.markdown(f"<p style='text-align:center;color:#555;font-size:12px;margin-top:12px'>Connecté : {st.session_state.get('user_email','')}</p>", unsafe_allow_html=True)
    st.stop()

# ════════════════════════════════════════════
# APP CONFIG CSS — Design Atlantic Re (inspiré Orange BF)

# ═══════════════════════════════════════════════════════════════════════════════
# CSS INJECTION
# ═══════════════════════════════════════════════════════════════════════════════
st.markdown(f"<style>{CSS_ATLANTICRE}</style>", unsafe_allow_html=True)

# ═══════════════════════════════════════════════════════════════════════════════
# SIDEBAR + ACCUEIL + TABS (UI principale)
# ═══════════════════════════════════════════════════════════════════════════════
st.title("Atlantic Re")
st.caption(f"Connecté : {st.session_state.get('user_email','')} | Burning cost · Simulation · Courbe de référence marché · IA")

with st.sidebar:
    if st.button(" Déconnexion"):
        st.session_state["authenticated"] = False; st.rerun()
    if st.button(" Accueil"):
        st.session_state["page"] = "landing"; st.rerun()
    st.markdown("###  Configuration")
    api_key = st.text_input(" Clé API Claude", type="password", placeholder="sk-ant-...",
                           help="Analyses copilote : Haiku (économique) | Agent autonome : Opus (puissant)")
    if api_key:
        st.caption(" Haiku pour analyses |  Opus pour agents autonomes uniquement")
    gnpi    = st.number_input(" GNPI (MAD)", value=183_000_000, step=1_000_000)
    st.session_state['gnpi'] = gnpi
    st.divider()
    st.markdown("###  Statut des étapes")
    for nom, key in [("Programme","df_prog"),("Données","df_liq"),
                     ("Burning cost","resultats_bc"),("Simulation","resultats_sim"),
                     ("Courbe de référence marché","resultats_mkt")]:
        st.markdown(f"{'' if key in st.session_state else ''} {nom}")
    st.divider()
    st.divider()
    st.markdown("###  Base de données")
    _db_url_val = _get_db_url()
    _db_type = " PostgreSQL (Supabase)" if _db_url_val else " SQLite local"
    _db_sid  = st.session_state.get("db_session_id")
    st.markdown(f"{_db_type}")
    if not _db_url_val:
        try:
            raw = st.secrets.get("DATABASE_URL", "")
            if raw:
                st.caption(f" Format inattendu : {raw[:25]}...")
            else:
                st.caption(" DATABASE_URL absent des Secrets")
        except:
            st.caption(" Secrets non accessibles")

    if st.button(" Tester la connexion DB", key="btn_test_db", use_container_width=True):
        st.markdown("---")
        # 1. Lecture secrets
        raw_url = None
        try:
            raw_url = st.secrets.get("DATABASE_URL")
            if raw_url:
                st.success(f" Secret trouvé : {raw_url[:30]}...")
            else:
                st.error(" DATABASE_URL vide ou absent des Secrets")
        except Exception as e:
            st.error(f" Erreur lecture secrets : {e}")

        # 2. Normalisation URL
        if raw_url:
            if raw_url.startswith("postgres://"):
                raw_url = raw_url.replace("postgres://", "postgresql://", 1)
                st.info(" URL normalisée : postgres:// → postgresql://")

        # 3. Test connexion
        if raw_url and raw_url.startswith("postgresql://"):
            try:
                import psycopg2
                con = psycopg2.connect(raw_url, connect_timeout=5)
                cur = con.cursor()
                cur.execute("SELECT version()")
                v = cur.fetchone()[0]
                con.close()
                st.success(f" Connexion PostgreSQL OK !")
                st.caption(v[:60])
            except ImportError:
                st.error(" psycopg2 non installé — ajoutez psycopg2-binary dans requirements.txt")
            except Exception as e:
                st.error(f" Connexion échouée : {e}")
        elif raw_url:
            st.error(f" Format URL non reconnu : {raw_url[:40]}")
    if _db_sid:
        chargé_sidebar = []
        if "resultats_bc"   in st.session_state: chargé_sidebar.append(" BC")
        if "resultats_sim"  in st.session_state: chargé_sidebar.append(" Sim")
        if "taux_mkt_final" in st.session_state and st.session_state.get("taux_mkt_final"): chargé_sidebar.append(" Mkt")
        if "df_rapport"     in st.session_state: chargé_sidebar.append(" Rapport")
        st.caption(f"Session #{_db_sid}")
        if chargé_sidebar:
            st.caption(" · ".join(chargé_sidebar))
    else:
        st.caption("Aucune session active")
    if st.button(" Sauvegarder maintenant", key="btn_save_now", use_container_width=True):
        try:
            sid = db_save_session(st.session_state.get("user_email",""), gnpi,
                                     st.session_state.get("tranches_input", []))
            if "resultats_bc" in st.session_state:
                db_save_etape("bc", [{k:v for k,v in r.items() if k!="detail_annuel"}
                                      for r in st.session_state["resultats_bc"]])
            if "resultats_sim" in st.session_state:
                db_save_etape("sim", st.session_state["resultats_sim"])
            if "resultats_mkt" in st.session_state:
                db_save_etape("mkt", {"resultats_mkt": [{k:v for k,v in r.items() if k!="taux_tranches"}
                                       for r in st.session_state["resultats_mkt"]],
                                      "taux_mkt_final": st.session_state.get("taux_mkt_final",[])})
            if st.session_state.get("df_rapport") is not None:
                db_save_etape("rapport", {"rows": st.session_state["df_rapport"].to_dict("records"),
                                           "prime_totale": st.session_state.get("prime_totale",0)})
            st.success(f" Sauvegardé — Session #{sid}")
            st.rerun()
        except Exception as _e:
            st.error(f"Erreur DB : {_e}")

    # ── Test email SMTP ──────────────────────────────────────
    st.markdown("###  Email SMTP")
    _smtp_user_diag = ""
    _smtp_pass_diag = ""
    try:
        _smtp_user_diag = st.secrets["SMTP_USER"]
        _smtp_pass_diag = st.secrets["SMTP_PASS"]
    except: pass

    if _smtp_user_diag:
        _masked_pass = _smtp_pass_diag[:2] + "****" + _smtp_pass_diag[-2:] if len(_smtp_pass_diag) > 4 else "****"
        _is_app_pwd  = len(_smtp_pass_diag.replace(" ","")) == 16 and _smtp_pass_diag.replace(" ","").isalnum()
        st.caption(f"SMTP_USER : {_smtp_user_diag}")
        st.caption(f"SMTP_PASS : {_masked_pass}")
        if _is_app_pwd:
            st.success(" App Password détecté (16 caractères)")
        else:
            st.warning(
                f" SMTP_PASS ({len(_smtp_pass_diag)} car.) semble être le mot de passe ordinaire. "
                "Gmail exige un **App Password** (16 caractères alphanumériques)."
            )
            st.markdown("""
            **Comment créer un App Password Gmail :**
            1. [myaccount.google.com](https://myaccount.google.com) → **Sécurité**
            2. **Validation en 2 étapes** (doit être activée)
            3. → **Mots de passe des applications**
            4. Créer → Nom : "Atlantic Re IA" → **Générer**
            5. Copier les **16 caractères** (ex: `abcd efgh ijkl mnop`)
            6. Dans Secrets Streamlit : `SMTP_PASS = "abcdefghijklmnop"` (sans espaces)
            """)
    else:
        st.caption("SMTP_USER non trouvé dans les Secrets")

    if st.button(" Tester l'envoi email", key="btn_test_smtp", use_container_width=True):
        with st.spinner("Envoi en cours..."):
            ok, msg_smtp = envoyer_notification_email(
                "Test Atlantic Re IA",
                "<p>Test de configuration email depuis Atlantic Re IA.</p>"
                f"<p>Utilisateur : {st.session_state.get('user_email','')}</p>",
                "hervepagnangde@gmail.com"
            )
        if ok:
            st.success(f" {msg_smtp}")
        else:
            st.error(f" {msg_smtp}")

    st.divider()
    st.markdown("###  Notifications Slack / Teams")
    slack_wh_cfg = ""
    teams_wh_cfg = ""
    try: slack_wh_cfg = st.secrets.get("SLACK_WEBHOOK_URL","")
    except: pass
    try: teams_wh_cfg = st.secrets.get("TEAMS_WEBHOOK_URL","")
    except: pass
    if slack_wh_cfg: st.caption(f" Slack webhook configuré")
    elif teams_wh_cfg: st.caption(f" Teams webhook configuré")
    else:
        st.caption("Configurez SLACK_WEBHOOK_URL ou TEAMS_WEBHOOK_URL dans les Secrets pour activer.")
    if st.button(" Test webhook", key="btn_test_webhook", use_container_width=True):
        wh_r = envoyer_webhook_notification(
            "Test Atlantic Re IA",
            f"Test depuis la sidebar · Utilisateur : {st.session_state.get('user_email','')}",
            niveau="info")
        if wh_r:
            for svc, ok_w, msg_w in wh_r:
                (st.success if ok_w else st.error)(f"{svc} : {msg_w}")
        else:
            st.info("Aucun webhook configuré dans les Secrets.")
    instructions_globales = st.text_area("Contexte portefeuille",
        height=120, key="instructions_globales",
        help="Inclus dans TOUS les prompts Claude")

# ════════════════════════════════════════════
# ACCUEIL INTELLIGENT
# ════════════════════════════════════════════

# ── Bandeau accueil statique (0 token) ──
etapes_faites     = [n for n, k in [("Programme","df_prog"),("Triangle","df_liq"),
                      ("Burning Cost","resultats_bc"),("Simulation","resultats_sim"),
                      ("Courbe de référence marché","resultats_mkt")] if k in st.session_state]
etapes_manquantes = [n for n, k in [("Programme","df_prog"),("Triangle","df_liq"),
                      ("Burning Cost","resultats_bc"),("Simulation","resultats_sim"),
                      ("Courbe de référence marché","resultats_mkt")] if k not in st.session_state]
prochaine   = etapes_manquantes[0] if etapes_manquantes else " Toutes les étapes complétées !"

# ── Dashboard exécutif ──────────────────────────────────────────────────────
pt_exec   = st.session_state.get("prime_totale", 0)
tg_exec   = pt_exec / gnpi if gnpi and pt_exec else 0
n_atyp    = len(st.session_state.get("bc_annees_exclues_set", set()))
alpha_v   = st.session_state.get("alpha_est", None)
lmbd_v    = st.session_state.get("lambda_est", None)

kpi_html = ""
if pt_exec:
    kpi_html += f"""<div class="exec-kpi-item">
      <div style="font-size:11px;color:#5a7a8a;font-weight:700;text-transform:uppercase;letter-spacing:0.5px">Prime totale</div>
      <div style="font-size:22px;font-weight:800;color:#0d2b3e">{pt_exec:,.0f} <span style="font-size:13px;font-weight:400">MAD</span></div></div>"""
    kpi_html += f"""<div class="exec-kpi-item">
      <div style="font-size:11px;color:#5a7a8a;font-weight:700;text-transform:uppercase;letter-spacing:0.5px">Taux global</div>
      <div style="font-size:22px;font-weight:800;color:#0d2b3e">{tg_exec:.4%}</div></div>"""
if alpha_v:
    kpi_html += f"""<div class="exec-kpi-item">
      <div style="font-size:11px;color:#5a7a8a;font-weight:700;text-transform:uppercase;letter-spacing:0.5px">Alpha Pareto</div>
      <div style="font-size:22px;font-weight:800;color:#0d2b3e">{alpha_v:.4f}</div></div>"""
if n_atyp:
    kpi_html += f"""<div class="exec-kpi-item" style="border-top-color:#e74c3c">
      <div style="font-size:11px;color:#e74c3c;font-weight:700;text-transform:uppercase;letter-spacing:0.5px">Années exclues</div>
      <div style="font-size:22px;font-weight:800;color:#e74c3c">{n_atyp}</div></div>"""

etapes_status = "".join([
    f"<span style='background:{'#00b5a5' if e in etapes_faites else '#e2e8f0'};color:{'white' if e in etapes_faites else '#5a7a8a'};"
    f"padding:3px 10px;border-radius:20px;font-size:11px;font-weight:600;margin:2px'>{e}</span>"
    for e, _ in [("Programme","df_prog"),("Triangle","df_liq"),
                  ("Burning Cost","resultats_bc"),("Simulation","resultats_sim"),
                  ("Courbe de référence marché","resultats_mkt")]
])

st.markdown(f"""
<div style="background:linear-gradient(135deg,#0d2b3e 0%,#1e3a52 60%,#004d40 100%);
    padding:20px 28px;margin-bottom:16px;box-shadow:0 6px 20px rgba(0,0,0,0.2)">
  <div style="display:flex;justify-content:space-between;align-items:flex-start;flex-wrap:wrap;gap:12px">
    <div>
      <div style="font-size:17px;font-weight:700;color:white"> Atlantic Re IA — Tarification XL</div>
      <div style="font-size:12px;color:rgba(255,255,255,0.6);margin-top:4px">{etapes_status}</div>
      <div style="font-size:12px;color:#f59e0b;margin-top:6px"> Prochaine : <b style="color:white">{prochaine}</b></div>
    </div>
    {f'<div style="display:flex;gap:8px;flex-wrap:wrap">{kpi_html}</div>' if kpi_html else ''}
  </div>
</div>""", unsafe_allow_html=True)

# Audit log à la connexion
db_audit(st.session_state.get("user_email",""), "session_active",
         f"GNPI={gnpi:,.0f} MAD", st.session_state.get("db_session_id"))

# ── Analyse actuarielle assistée sur demande uniquement (évite les appels automatiques coûteux) ──
if "accueil_ia_msg" in st.session_state:
    with st.expander(" Dernière analyse IA", expanded=False):
        st.markdown(st.session_state["accueil_ia_msg"])

if api_key:
    col_ia1, col_ia2 = st.columns([3, 1])
    with col_ia2:
        if st.button(" Analyser ma session", key="btn_accueil_ia", use_container_width=True,
                     help="Appel API payant — utiliser avec parcimonie"):
            etapes_faites_2     = [n for n, k in [("Programme","df_prog"),("Triangle","df_liq"),
                                  ("Burning Cost","resultats_bc"),("Simulation","resultats_sim"),
                                  ("Courbe de référence marché","resultats_mkt")] if k in st.session_state]
            etapes_manquantes_2 = [n for n, k in [("Programme","df_prog"),("Triangle","df_liq"),
                                  ("Burning Cost","resultats_bc"),("Simulation","resultats_sim"),
                                  ("Courbe de référence marché","resultats_mkt")] if k not in st.session_state]
            prompt_accueil = build_prompt(
                role="Assistant actuariel expert en reassurance non-proportionnelle automobile.",
                task="Genere un message d'accueil intelligent : 1. Etat de la session 2. Prochaine action recommandee 3. Point d'attention si anomalie. Maximum 8 lignes.",
                data=f"Etapes completes : {etapes_faites_2}\nEtapes restantes : {etapes_manquantes_2}\nGNPI : {gnpi:,} MAD",
                contexte_global=st.session_state.get("instructions_globales",""),
                contraintes="- Maximum 8 lignes\n- Concis\n- Ne pas inventer")
            with st.spinner(" Analyse en cours..."):
                client_acc = __import__('anthropic').Anthropic(api_key=api_key)
                try:
                    msg = client_acc.messages.create(
                        model="claude-haiku-4-5-20251001",
                        max_tokens=400,
                        messages=[{"role":"user","content":prompt_accueil}])
                    txt = msg.content[0].text
                    st.session_state["accueil_ia_msg"] = txt
                    st.rerun()
                except Exception as e_acc:
                    st.error(f"Erreur : {e_acc}")

# ════════════════════════════════════════════

def _hill_estimates(sorted_desc, k_max=None):
    n = len(sorted_desc)
    if k_max is None: k_max = min(n-1, 200)
    hills, ks = [], []
    for k in range(1, k_max+1):
        log_ratios = np.log(sorted_desc[:k] / sorted_desc[k])
        h = k / np.sum(log_ratios) if np.sum(log_ratios) > 0 else np.nan
        hills.append(h); ks.append(k)
    return np.array(ks), np.array(hills)


def _mean_excess(data, n_points=40):
    data_s = np.sort(data)
    u_min, u_max = np.percentile(data_s, 50), np.percentile(data_s, 95)
    thresholds = np.linspace(u_min, u_max, n_points)
    mef = []
    for u in thresholds:
        exc = data_s[data_s > u] - u
        mef.append(np.mean(exc) if len(exc) >= 5 else np.nan)
    return thresholds, np.array(mef)


def _gertensgarbe_k(ks, hills):
    valid = ~np.isnan(hills)
    h = hills[valid]; k = ks[valid]
    if len(h) < 10: return k[len(k)//2]
    n = len(h)
    s_prog = np.zeros(n); s_reg = np.zeros(n)
    for i in range(1, n):
        s_prog[i] = s_prog[i-1] + sum(1 for j in range(i) if h[j] < h[i])
    h_rev = h[::-1]
    for i in range(1, n):
        s_reg[i] = s_reg[i-1] + sum(1 for j in range(i) if h_rev[j] < h_rev[i])
    s_reg = s_reg[::-1]
    crossings = np.where(np.diff(np.sign(s_prog - s_reg)))[0]
    idx = crossings[0] if len(crossings) > 0 else np.argmin(np.abs(hills - np.nanmedian(hills)))
    return int(k[min(idx, len(k)-1)])


def _fit_severity(exceedances, threshold):
    from scipy import stats
    results = {}
    x = exceedances
    if len(x) < 10: return results
    try:
        alpha_h = len(x) / np.sum(np.log(x / threshold))
        ks_p, pval_p = stats.kstest(x, lambda v: 1-(v/threshold)**(-alpha_h))
        results["Pareto"] = {"alpha": alpha_h, "xm": threshold, "ks": ks_p, "pval": pval_p}
    except: pass
    try:
        log_x = np.log(x); mu_ln, sigma_ln = np.mean(log_x), np.std(log_x)
        ks_ln, pval_ln = stats.kstest(x, lambda v: stats.lognorm.cdf(v, s=sigma_ln, scale=np.exp(mu_ln)))
        results["Log-Normale"] = {"mu": mu_ln, "sigma": sigma_ln, "ks": ks_ln, "pval": pval_ln}
    except: pass
    try:
        y = x - threshold
        xi, loc, beta = stats.genpareto.fit(y, floc=0)
        ks_gp, pval_gp = stats.kstest(y, lambda v: stats.genpareto.cdf(v, xi, loc=0, scale=beta))
        results["GPD"] = {"xi": xi, "beta": beta, "ks": ks_gp, "pval": pval_gp, "threshold": threshold}
    except: pass
    return results


def _fit_frequency(counts):
    from scipy import stats
    results = {}
    if len(counts) < 3: return results
    mu = np.mean(counts); var = np.var(counts)
    try:
        ks_po, pval_po = stats.kstest(counts, lambda v: stats.poisson.cdf(v, mu))
        results["Poisson"] = {"lambda": mu, "ks": ks_po, "pval": pval_po}
    except: pass
    try:
        if var > mu:
            r_nb = mu**2 / (var - mu); p_nb = r_nb / (r_nb + mu)
            ks_nb, pval_nb = stats.kstest(counts, lambda v: stats.nbinom.cdf(v, r_nb, p_nb))
            results["BN"] = {"r": r_nb, "p": p_nb, "ks": ks_nb, "pval": pval_nb}
        else:
            results["BN"] = {"note": "var <= mean — BN non applicable"}
    except: pass
    return results


def _threshold_table(data, thresholds_pct):
    from scipy import stats
    rows = []
    for pct in thresholds_pct:
        u = np.percentile(data, pct)
        exc = data[data > u]; n_exc = len(exc)
        if n_exc < 5:
            rows.append({"Seuil %": f"p{pct}", "Seuil MAD": f"{u:,.0f}", "N exc.": n_exc,
                         "Alpha Hill": "—", "KS stat": "—", "p-val KS": "—", "AD stat": "—", "Qualite": "Insuf."})
            continue
        alpha_h = n_exc / np.sum(np.log(exc / u))
        ks_s, pval_ks = stats.kstest(exc, lambda v: 1-(v/u)**(-alpha_h))
        try:
            cdf_v = np.sort(1-(np.sort(exc)/u)**(-alpha_h))
            nn = len(cdf_v); i_a = np.arange(1, nn+1)
            ad_stat = -nn - np.mean((2*i_a-1)*(np.log(np.clip(cdf_v,1e-10,1-1e-10))+
                                               np.log(np.clip(1-cdf_v[::-1],1e-10,1-1e-10))))
        except: ad_stat = np.nan
        qual = "Bon" if pval_ks>0.05 and not np.isnan(ad_stat) and ad_stat<2.5 else                "Acceptable" if pval_ks>0.01 else "Rejeté"
        rows.append({"Seuil %": f"p{pct}", "Seuil MAD": f"{u:,.0f}", "N exc.": n_exc,
                     "Alpha Hill": f"{alpha_h:.4f}", "KS stat": f"{ks_s:.4f}",
                     "p-val KS": f"{pval_ks:.4f}",
                     "AD stat": f"{ad_stat:.4f}" if not np.isnan(ad_stat) else "—", "Qualite": qual})
    return rows


def section_analyse_distributions():
    import matplotlib.pyplot as plt
    from scipy import stats as sp_stats

    if "df_proj" not in st.session_state or "alpha_est" not in st.session_state:
        st.info("Transformez d\'abord le triangle.")
        return

    df_proj  = st.session_state["df_proj"]
    seuil_0  = float(st.session_state["seuil_est"])
    alpha_0  = float(st.session_state["alpha_est"])
    lambda_0 = float(st.session_state["lambda_est"])

    all_sev  = df_proj["Sprime_ultime"].values; all_sev = all_sev[all_sev > 0]
    sev_data = all_sev[all_sev > seuil_0]
    freq_data = df_proj.groupby("annee_surv").size().values

    if len(sev_data) < 10:
        st.warning(f"Seulement {len(sev_data)} sinistres au-dessus du seuil — augmentez le triangle ou réduisez le seuil.")
        return

    tabs_d = st.tabs(["Sélection du seuil", "Sévérité — Fits & CDF", "Fréquence", "Paramètres manuels"])

    # ── Onglet A : seuil ──
    with tabs_d[0]:
        sorted_desc = np.sort(all_sev)[::-1]
        ks_arr, hills_arr = _hill_estimates(sorted_desc, k_max=min(len(sorted_desc)-1, 150))
        k_gert = _gertensgarbe_k(ks_arr, hills_arr)
        alpha_gert = float(hills_arr[k_gert-1]) if k_gert <= len(hills_arr) else alpha_0

        col_h, col_m = st.columns(2)
        with col_h:
            fig_h, ax_h = plt.subplots(figsize=(6,3))
            ax_h.plot(ks_arr, hills_arr, color="#1a1a1a", lw=1.5)
            ax_h.axvline(k_gert, color="#ef4444", ls="--", lw=1.5,
                         label=f"Gertensgarbe k={k_gert} → α={alpha_gert:.3f}")
            ax_h.axhline(alpha_0, color="#2d8a4e", ls=":", lw=1.2, label=f"α actuel={alpha_0:.3f}")
            ax_h.set_xlabel("k"); ax_h.set_ylabel("α(k)"); ax_h.set_title("Hill Plot")
            ax_h.legend(fontsize=8); ax_h.grid(alpha=0.3)
            st.pyplot(fig_h); plt.close()
        with col_m:
            u_mef, e_mef = _mean_excess(all_sev)
            fig_m, ax_m = plt.subplots(figsize=(6,3))
            ax_m.plot(u_mef, e_mef, color="#2d8a4e", lw=2)
            ax_m.axvline(seuil_0, color="#ef4444", ls="--", lw=1.5, label=f"Seuil={seuil_0:,.0f}")
            ax_m.set_xlabel("u"); ax_m.set_ylabel("e(u)"); ax_m.set_title("Mean Excess Function")
            ax_m.legend(fontsize=8); ax_m.grid(alpha=0.3)
            st.pyplot(fig_m); plt.close()

        pcts = [50, 60, 70, 75, 80, 85, 90, 95]
        rows_s = _threshold_table(all_sev, pcts)
        df_s = pd.DataFrame(rows_s)
        st.dataframe(df_s, use_container_width=True)
        st.caption("Bon = KS p-val > 5% et AD < 2.5 | Acceptable = KS p-val > 1%")

        best_row = next((r for r in rows_s if r["Qualite"] == "Bon"), None)
        if best_row:
            st.success(f"Recommandé : {best_row['Seuil %']} = {best_row['Seuil MAD']} MAD — α={best_row['Alpha Hill']}")
            if st.button("Appliquer", key="btn_apply_seuil"):
                st.session_state["seuil_est"] = float(best_row["Seuil MAD"].replace(",","").replace(" ",""))
                st.session_state["alpha_est"] = float(best_row["Alpha Hill"])
                st.rerun()

    # ── Onglet B : sévérité ──
    with tabs_d[1]:
        fits_sev = _fit_severity(sev_data, seuil_0)
        if fits_sev:
            st.dataframe(pd.DataFrame([{
                "Distribution": n,
                "Paramètres": (f"α={f['alpha']:.4f}" if n=="Pareto" else
                               f"μ={f['mu']:.3f} σ={f['sigma']:.3f}" if n=="Log-Normale" else
                               f"ξ={f['xi']:.4f} β={f['beta']:.0f}"),
                "KS": f"{f['ks']:.4f}", "p-val": f"{f['pval']:.4f}",
                "Adéquation": "Bon" if f["pval"]>0.05 else "Acceptable" if f["pval"]>0.01 else "Rejeté"
            } for n, f in fits_sev.items()]), use_container_width=True)

        fig_c, axes_c = plt.subplots(1, 2, figsize=(12,4))
        x_s = np.sort(sev_data)
        axes_c[0].plot(x_s, np.arange(1,len(x_s)+1)/len(x_s), "k-", lw=2.5, label="Empirique")
        colors_d = {"Pareto":"#ef4444","Log-Normale":"#3b82f6","GPD":"#2d8a4e"}
        for nom, f in fits_sev.items():
            try:
                col = colors_d.get(nom,"#888")
                if nom=="Pareto": y = np.clip(1-(x_s/f["xm"])**(-f["alpha"]),0,1)
                elif nom=="Log-Normale": y = sp_stats.lognorm.cdf(x_s, s=f["sigma"], scale=np.exp(f["mu"]))
                elif nom=="GPD": y = sp_stats.genpareto.cdf(x_s-seuil_0, f["xi"], loc=0, scale=f["beta"])
                else: continue
                axes_c[0].plot(x_s, y, "--", color=col, lw=1.8, label=f"{nom} p={f['pval']:.3f}")
            except: pass
        axes_c[0].set_xlabel("MAD"); axes_c[0].set_ylabel("F(x)")
        axes_c[0].set_title("CDF Sévérité"); axes_c[0].legend(fontsize=8); axes_c[0].grid(alpha=0.3)
        # QQ-Plot
        log_x = np.log(np.sort(sev_data)/seuil_0); n_q = len(log_x)
        th_q = -np.log(1-(np.arange(1,n_q+1)/(n_q+1)))
        axes_c[1].scatter(th_q, log_x, color="#2d8a4e", s=15, alpha=0.7)
        mn_q = min(th_q.min(), log_x.min()); mx_q = max(th_q.max(), log_x.max())
        axes_c[1].plot([mn_q,mx_q],[mn_q,mx_q],"r--",lw=1.5)
        axes_c[1].set_xlabel("Quantiles Exp(1)"); axes_c[1].set_ylabel("log(X/seuil)")
        axes_c[1].set_title("QQ-Plot Pareto"); axes_c[1].grid(alpha=0.3)
        st.pyplot(fig_c); plt.close()

    # ── Onglet C : fréquence ──
    with tabs_d[2]:
        fits_freq = _fit_frequency(freq_data)
        if fits_freq:
            rows_fr = []
            for nom, f in fits_freq.items():
                if "note" in f: rows_fr.append({"Distribution":nom,"Paramètres":f["note"],"KS":"—","p-val":"—","Adéquation":"—"})
                else: rows_fr.append({"Distribution":nom,
                    "Paramètres": f"λ={f['lambda']:.3f}" if nom=="Poisson" else f"r={f['r']:.3f} p={f['p']:.4f}",
                    "KS": f"{f['ks']:.4f}", "p-val": f"{f['pval']:.4f}",
                    "Adéquation": "Bon" if f["pval"]>0.05 else "Acceptable" if f["pval"]>0.01 else "Rejeté"})
            st.dataframe(pd.DataFrame(rows_fr), use_container_width=True)

        fig_fr, ax_fr = plt.subplots(figsize=(8,4))
        v, c = np.unique(freq_data, return_counts=True)
        ax_fr.bar(v, c/len(freq_data), color="#2d8a4e", alpha=0.7, label="Observée", zorder=3)
        x_r = np.arange(0, max(freq_data)+2)
        if "Poisson" in fits_freq and "pval" in fits_freq["Poisson"]:
            ax_fr.plot(x_r, sp_stats.poisson.pmf(x_r, fits_freq["Poisson"]["lambda"]),
                       "r--o", ms=5, lw=1.5, label=f"Poisson(λ={fits_freq['Poisson']['lambda']:.2f})")
        if "BN" in fits_freq and "r" in fits_freq["BN"]:
            f_nb = fits_freq["BN"]
            ax_fr.plot(x_r, sp_stats.nbinom.pmf(x_r, f_nb["r"], f_nb["p"]),
                       "b--s", ms=5, lw=1.5, label=f"BN(r={f_nb['r']:.2f})")
        ax_fr.set_xlabel("Sinistres/an"); ax_fr.set_title("Fréquence annuelle")
        ax_fr.legend(); ax_fr.grid(alpha=0.3)
        st.pyplot(fig_fr); plt.close()
        disp_ratio = float(np.var(freq_data)/max(np.mean(freq_data),0.01))
        st.info(f"Indice de dispersion = {disp_ratio:.2f} ({'surdispersion → BN pertinente' if disp_ratio>1.2 else 'équidispersion → Poisson adapté'})")

    # ── Onglet D : manuel ──
    with tabs_d[3]:
        c1,c2,c3 = st.columns(3)
        with c1: alpha_m  = st.slider("Alpha",  0.5, 5.0,  float(alpha_0),  0.05, key="alpha_manual")
        with c2: lambda_m = st.slider("Lambda", 0.5, 30.0, float(lambda_0), 0.5,  key="lambda_manual")
        with c3:
            p40 = int(np.percentile(all_sev, 40)); p92 = int(np.percentile(all_sev, 92))
            seuil_m = st.slider("Seuil MAD", p40, p92, int(seuil_0), 50000, key="seuil_manual")

        exc_m = all_sev[all_sev > seuil_m]
        if len(exc_m) >= 5:
            fig_mn, ax_mn = plt.subplots(figsize=(8,3))
            xs_m = np.sort(exc_m)
            ax_mn.plot(xs_m, np.arange(1,len(xs_m)+1)/len(xs_m), "k-", lw=2, label="Empirique")
            ax_mn.plot(xs_m, np.clip(1-(xs_m/seuil_m)**(-alpha_m),0,1), "r--", lw=1.8,
                       label=f"Pareto(α={alpha_m:.2f})")
            ax_mn.set_xlabel("MAD"); ax_mn.set_title("CDF Sévérité — paramètres manuels")
            ax_mn.legend(); ax_mn.grid(alpha=0.3)
            st.pyplot(fig_mn); plt.close()
        if st.button("Appliquer ces paramètres", type="primary", key="apply_manual"):
            st.session_state["alpha_est"]  = alpha_m
            st.session_state["lambda_est"] = lambda_m
            st.session_state["seuil_est"]  = float(seuil_m)
            st.success(f"Paramètres mis à jour : α={alpha_m:.4f}, λ={lambda_m:.4f}, seuil={seuil_m:,.0f}")
            st.rerun()

    # Stocker pour l\'agent LLM
    try:
        fits_sev_stored = _fit_severity(sev_data, seuil_0)
        fits_freq_stored = _fit_frequency(freq_data)
        st.session_state["dist_fit_results"] = {
            "severity": {k: {kk: float(vv) if isinstance(vv,(int,float,np.floating)) else vv
                             for kk,vv in v.items() if kk != "threshold"}
                         for k,v in fits_sev_stored.items()},
            "frequency": {k: {kk: float(vv) if isinstance(vv,(int,float,np.floating)) else vv
                               for kk,vv in v.items()}
                          for k,v in fits_freq_stored.items()},
            "n_exceedances": int(len(sev_data)),
            "overdispersion_ratio": float(np.var(freq_data)/max(np.mean(freq_data),0.01)),
            "alpha_gert": alpha_gert,
        }
    except: pass


# ════════════════════════════════════════════
# TAB AGENT — AGENT PYTHON PUR (HORS LIGNE)
# ════════════════════════════════════════════


def _labo_display_section():
    """Module d’optimisation actuarielle — affiché dans tab_agent."""
    import matplotlib.pyplot as plt

    st.markdown("---")
    st.markdown("#### Module d’optimisation actuarielle")
    st.caption(
        "120 scénarios/tranche · BC + Simulation + Courbe de référence marché · RF/DT/XGB · "
        "Optimisation Dichotomie (actuarielle) + De Finetti · Programme multi-tranches"
    )

    if "df_proj" not in st.session_state or "alpha_est" not in st.session_state:
        st.info("Transformez d'abord le triangle (Tab 2).")
        return

    def _make_labo():
        return AgentLaboTarification(
            tranches_base      = tranches_input,
            gnpi               = gnpi,
            df_proj            = st.session_state["df_proj"],
            coeffs             = st.session_state.get("coeffs", np.array([1.0])),
            alpha              = st.session_state.get("alpha_est", 1.5),
            lambda_            = st.session_state.get("lambda_est", 5.0),
            seuil              = st.session_state.get("seuil_est", 1_600_000),
            chargement_majeurs = st.session_state.get("chargement_majeurs", 0.0),
            df_mkt             = st.session_state.get("df_mkt_clean"),
            is_long            = st.session_state.get("is_long_tail", True),
        )

    def _restore_labo(labo):
        """Restaure un labo depuis session_state après un rerun."""
        if "labo_modeles"  in st.session_state: labo.modeles_entraines = st.session_state["labo_modeles"]
        if "labo_features" in st.session_state: labo._features_used    = st.session_state["labo_features"]
        if "labo_best"     in st.session_state: labo._best_model_name  = st.session_state["labo_best"]
        if "labo_df_ml"    in st.session_state: labo.df_ml             = st.session_state["labo_df_ml"]
        return labo

    # ═══════════════════════════════════════════════════════════
    # ÉTAPE 1 — GRILLE
    # ═══════════════════════════════════════════════════════════
    with st.expander("Étape 1 — Grille de conditions (120 scénarios/tranche, modifiable)", expanded=True):
        c1, c2 = st.columns([3, 1])
        with c1:
            n_max = st.slider("Scénarios max par tranche", 30, 150, 120, 10, key="labo_n_max")
        with c2:
            st.markdown("<div style='height:28px'></div>", unsafe_allow_html=True)
            if st.button("Générer la grille", key="btn_labo_gen", use_container_width=True):
                labo = _make_labo()
                grille = labo.generer_grille_auto(n_max_par_tranche=n_max)
                st.session_state["labo_grille"] = grille
                st.rerun()

        if "labo_grille" in st.session_state:
            grille = st.session_state["labo_grille"]
            st.caption(f"{len(grille)} scénarios générés — modifiez directement ci-dessous avant de lancer le batch")

            df_g = pd.DataFrame([{
                "Tranche":    s["tranche_base"],
                "Type":       s["type"],
                "Priorite":   s["priorite"],
                "Portee":     s["portee"],
                "AAD":        s.get("AAD") or 0.0,
                "AAL":        s.get("AAL") or 0.0,
                "Reconst.":   s["nb_reconstitutions"],
                "Rec1 %":     s.get("taux_recon_1", 100.0),
                "Rec2 %":     s.get("taux_recon_2", 0.0),
                "Stab %":     s.get("seuil_stab", 0.0) * 100,
                "Marge":      s["marge"],
                "Frais":      s["frais"],
                "Brokage":    s["brokage"],
                "Retro.":     s["retrocession"],
                "k_sec":      s["k_securite"],
                "Alpha":      s["alpha"],
                "Lambda":     s["lambda_"],
            } for s in grille])

            df_edited = st.data_editor(
                df_g, use_container_width=True, height=300, key="labo_editor",
                column_config={
                    "Priorite": st.column_config.NumberColumn(format="%,.0f"),
                    "Portee":   st.column_config.NumberColumn(format="%,.0f"),
                    "AAD":      st.column_config.NumberColumn(format="%,.0f"),
                    "AAL":      st.column_config.NumberColumn(format="%,.0f"),
                    "Reconst.": st.column_config.NumberColumn(min_value=0, max_value=4, step=1),
                    "Rec1 %":   st.column_config.NumberColumn(min_value=50.0, max_value=100.0, step=25.0,
                                    help="Taux 1ère reconstitution (50-100%)"),
                    "Rec2 %":   st.column_config.NumberColumn(min_value=0.0, max_value=100.0, step=25.0,
                                    help="Taux 2ème reconstitution (0 si pas de 2ème)"),
                    "Stab %":   st.column_config.NumberColumn(min_value=0.0, max_value=20.0, step=1.0,
                                    help="Seuil stabilisation % (0=sans, 5/6/7/8/9/10/20)"),
                    "Marge":    st.column_config.NumberColumn(format="%.3f", min_value=0.0, max_value=0.30, step=0.01),
                    "k_sec":    st.column_config.NumberColumn(format="%.2f", min_value=0.05, max_value=0.50, step=0.05),
                    "Type":     st.column_config.SelectboxColumn(options=["travaillante","cat","non_travaillante"]),
                }
            )

            # Merge edits back into grille
            grille_modif = []
            for i, row in df_edited.iterrows():
                s = dict(grille[i]) if i < len(grille) else dict(grille[-1])
                n_rec = int(row["Reconst."])
                tr1   = float(row["Rec1 %"])
                tr2   = float(row["Rec2 %"])
                tr_list = []
                if n_rec >= 1: tr_list.append(tr1)
                if n_rec >= 2: tr_list.append(tr2 if tr2 > 0 else 100.0)
                if n_rec >= 3: tr_list.extend([100.0] * (n_rec - 2))
                s.update({
                    "tranche_base":        row["Tranche"],
                    "type":                row["Type"],
                    "priorite":            float(row["Priorite"]),
                    "portee":              float(row["Portee"]),
                    "AAD":                 float(row["AAD"]) if row["AAD"] else None,
                    "AAL":                 float(row["AAL"]) if row["AAL"] else None,
                    "nb_reconstitutions":  n_rec,
                    "taux_reconstitution": tr1,
                    "taux_reconstitutions":tr_list,
                    "taux_recon_1":        tr1,
                    "taux_recon_2":        tr2,
                    "taux_recon_moy":      float(np.mean(tr_list)) if tr_list else 100.0,
                    "seuil_stab":          float(row["Stab %"]) / 100.0,
                    "marge":               float(row["Marge"]),
                    "frais":               float(row["Frais"]),
                    "brokage":             float(row["Brokage"]),
                    "retrocession":        float(row["Retro."]),
                    "k_securite":          float(row["k_sec"]),
                    "alpha":               float(row["Alpha"]),
                    "lambda_":             float(row["Lambda"]),
                })
                grille_modif.append(s)
            st.session_state["labo_grille"] = grille_modif

    # ═══════════════════════════════════════════════════════════
    # ÉTAPE 2 — BATCH BC + SIM + MKT
    # ═══════════════════════════════════════════════════════════
    if "labo_grille" in st.session_state:
        with st.expander("Étape 2 — Tarification batch (BC + Simulation + Courbe de référence marché)", expanded=True):
            c1, c2 = st.columns([3, 1])
            with c1:
                n_sim_labo = st.number_input("Simulations par scénario", value=5000,
                    step=1000, min_value=1000, key="labo_nsim")
            with c2:
                st.markdown("<div style='height:28px'></div>", unsafe_allow_html=True)
                if st.button("Lancer le batch", type="primary",
                             key="btn_labo_batch", use_container_width=True):
                    labo = _make_labo()
                    labo.grille = st.session_state["labo_grille"]
                    total = len(labo.grille)
                    bar   = st.progress(0, f"0/{total} scénarios...")
                    def _cb(i, n):
                        bar.progress(int((i+1)/n*100), f"{i+1}/{n} scénarios...")
                    res   = labo.executer_batch(n_sim=int(n_sim_labo), progress_cb=_cb)
                    df_ml = labo.construire_dataset()
                    bar.progress(100, "Terminé ✓")
                    st.session_state["labo_resultats"] = res
                    st.session_state["labo_df_ml"]     = df_ml
                    st.rerun()

            if "labo_resultats" in st.session_state:
                res = st.session_state["labo_resultats"]
                n_valides = sum(1 for r in res if r.get("taux_retenu", 0) > 0)
                st.success(f"{len(res)} scénarios tarifés — {n_valides} valides (BC ≥ 3 années non nulles)")

                df_show = pd.DataFrame([{
                    "Tranche":    r["tranche_base"],
                    "Type":       r["type"],
                    "D":          f"{r['priorite']:,.0f}",
                    "C":          f"{r['portee']:,.0f}",
                    "AAD":        f"{(r.get('AAD') or 0):,.0f}",
                    "Rec.":       r["nb_reconstitutions"],
                    "Rec1%":      f"{r.get('taux_recon_1',100):.0f}",
                    "Rec2%":      f"{r.get('taux_recon_2',0):.0f}",
                    "Stab%":      f"{r.get('seuil_stab',0)*100:.0f}",
                    "τ BC":       f"{r.get('taux_technique_bc',0):.4%}",
                    "τ Sim":      f"{r.get('taux_technique_sim',0):.4%}",
                    "τ Mkt":      f"{r.get('taux_technique_mkt',0):.4%}" if r.get("valide_mkt") else "—",
                    "τ Retenu":   f"{r.get('taux_retenu',0):.4%}",
                    "Prime (MAD)":f"{r.get('prime_MAD',0):,.0f}",
                    "Méthode":    r.get("methode_retenue",""),
                } for r in res])
                st.dataframe(df_show, use_container_width=True, height=280)

                try:
                    import io as _io_labo
                    buf = _io_labo.BytesIO()
                    st.session_state["labo_df_ml"].to_excel(buf, index=False, engine="openpyxl")
                    st.download_button(" Télécharger le dataset ML (Excel)",
                        data=buf.getvalue(), file_name="labo_dataset_ml.xlsx",
                        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                        key="btn_dl_labo")
                except: pass

    # ═══════════════════════════════════════════════════════════
    # ÉTAPE 3 — ML
    # ═══════════════════════════════════════════════════════════
    if "labo_df_ml" in st.session_state:
        with st.expander("Étape 3 — Entraînement ML (RF / DT / XGB)", expanded=True):
            df_ml = st.session_state["labo_df_ml"]
            n_feat = len(AgentLaboTarification.FEATURES)
            st.caption(
                f"Dataset : {len(df_ml)} lignes · {n_feat} features "
                f"(conditions + taux_recon + seuil_stab + α/λ) · "
                f"Target : τ technique"
            )
            c1, c2 = st.columns([2,1])
            with c1:
                target_choice = st.radio(
                    "Variable cible",
                    ["taux_retenu","taux_technique_bc","taux_technique_sim","taux_technique_mkt"],
                    horizontal=True, key="labo_target")
            with c2:
                st.markdown("<div style='height:28px'></div>", unsafe_allow_html=True)
                if st.button("Entraîner les modèles", type="primary", key="btn_labo_train"):
                    labo = _make_labo(); labo.df_ml = df_ml
                    with st.spinner("Entraînement RF / DT / XGB..."):
                        labo.entrainer_modeles(target=target_choice)
                    st.session_state["labo_modeles"]    = labo.modeles_entraines
                    st.session_state["labo_metriques"]  = labo.metriques_ml
                    st.session_state["labo_importance"] = labo.importance_vars
                    st.session_state["labo_features"]   = labo._features_used
                    st.session_state["labo_best"]       = labo._best_model_name
                    st.rerun()

            if "labo_metriques" in st.session_state:
                best = st.session_state.get("labo_best","")
                tableau_resultats([{
                    "Modèle":     nom,
                    "MAE (pts)":  f"{v.get('MAE',0)*100:.4f}" if "MAE" in v else "—",
                    "RMSE (pts)": f"{v.get('RMSE',0)*100:.4f}" if "RMSE" in v else "—",
                    "R²":         f"{v.get('R2',0):.4f}" if "R2" in v else "—",
                    "N train":    v.get("n_train","—"),
                    "✓ Meilleur": "" if nom == best else "",
                } for nom, v in st.session_state["labo_metriques"].items()])

                imp_dict = st.session_state.get("labo_importance", {})
                if imp_dict:
                    best_nom, imp = list(imp_dict.items())[0]
                    fig_imp, ax_imp = plt.subplots(figsize=(8, 4))
                    imp.head(12).plot.barh(ax=ax_imp, color="#2d8a4e", edgecolor="white")
                    ax_imp.set_xlabel("Importance relative")
                    ax_imp.set_title(f"Variables importantes — {best_nom}")
                    ax_imp.invert_yaxis(); ax_imp.grid(alpha=0.2)
                    ax_imp.spines[["top","right"]].set_visible(False)
                    st.pyplot(fig_imp); plt.close()
                    st.caption(
                        "**priorite / portee dominant** → la géométrie de la tranche "
                        "est le premier déterminant du taux.  "
                        "**k_securite / sigma dominant** → la volatilité historique est prépondérante.  "
                        "**seuil_stab dominant** → la stabilisation a un fort impact (branche longue)."
                    )

    # ═══════════════════════════════════════════════════════════
    # ÉTAPE 4 — OPTIMISATION ACTUARIELLE
    # ═══════════════════════════════════════════════════════════
    if "labo_modeles" in st.session_state:
        with st.expander(" Recherche de programmes alternatifs comparables (ML)", expanded=False):
            st.caption(
                "Le modèle ML prédit le taux pour n'importe quelle combinaison de conditions. "
                "Entrez un taux cible et l'outil trouve les conditions qui s'en approchent."
            )
            col_rco1, col_rco2, col_rco3 = st.columns(3)
            with col_rco1:
                t_target_reco = st.number_input("Taux cible (%)", value=3.0, step=0.1,
                    min_value=0.01, key="reco_taux_cible") / 100
                typ_reco = st.selectbox("Type de tranche",
                    ["travaillante","cat","non_travaillante"], key="reco_type")
            with col_rco2:
                t_tol = st.number_input("Tolérance ±(%)", value=0.5, step=0.1,
                    min_value=0.05, key="reco_tolerance") / 100
                n_reco = st.slider("Nb résultats max", 5, 30, 15, key="reco_n")
            with col_rco3:
                st.markdown("<div style='height:28px'></div>", unsafe_allow_html=True)
                if st.button("🔍 Trouver les conditions optimales", type="primary",
                             key="btn_reco_conditions", use_container_width=True):
                    labo_reco = AgentLaboTarification(
                        tranches_base=tranches_input, gnpi=gnpi,
                        df_proj=st.session_state["df_proj"],
                        coeffs=st.session_state.get("coeffs", np.array([1.0])),
                        alpha=st.session_state.get("alpha_est",1.5),
                        lambda_=st.session_state.get("lambda_est",5.0),
                        seuil=st.session_state.get("seuil_est",1_600_000))
                    labo_reco.modeles_entraines  = st.session_state.get("labo_modeles",{})
                    labo_reco._features_used     = st.session_state.get("labo_features",[])
                    labo_reco._best_model_name   = st.session_state.get("labo_best","")
                    results_reco, info_reco = labo_reco.optimiser_via_ml(
                        tranche_type=typ_reco,
                        taux_min=t_target_reco - t_tol,
                        taux_max=t_target_reco + t_tol,
                        n_candidats=3000)
                    st.session_state["reco_results"] = results_reco
                    st.session_state["reco_info"]    = info_reco

            if "reco_results" in st.session_state and st.session_state["reco_results"]:
                info_r = st.session_state.get("reco_info", {})
                if info_r.get("hors_plage"):
                    st.warning(info_r.get("message","Taux cible hors plage — résultats les plus proches affichés"))
                else:
                    st.success(f" {len(st.session_state['reco_results'])} combinaison(s) trouvée(s) près de {t_target_reco:.4%}")
                    st.caption(f"Plage observée : [{info_r.get('pred_min',0):.4%} — {info_r.get('pred_max',0):.4%}]")
                tableau_resultats(st.session_state["reco_results"][:n_reco],
                    "Conditions optimales recommandées par le modèle ML")
                st.caption(
                    "Note : ces conditions sont des prédictions ML — recalculer le BC et la simulation "
                    "avec les paramètres retenus pour valider le taux technique réel."
                )

    # ═══════════════════════════════════════════════════════════════════
    if "labo_modeles" in st.session_state:
        with st.expander(
            "Étape 4 — Optimisation actuarielle (Dichotomie + De Finetti/Borch)", expanded=True
        ):
            st.markdown(
                """
**Méthodes disponibles :**
- **Dichotomie (De Wylder, 1979 / méthode actuarielle)** : τ est monotone décroissant en D → bisection sur [D_min, D_max], convergence en ~50 itérations vers D* tel que τ(D*) = τ_cible. Méthode recommandée par les traités actuariels (Daykin, Pentikäinen & Pesonen, 1994).
- **Frontière De Finetti–Borch (1940/1969)** : minimise Var(perte retenue) pour un budget de prime donné. Borch (1969) prouve que le stop-loss (XL) est optimal pour ce critère. Retourne la courbe Pareto-efficiente et le programme optimal.
- **Programme multi-tranches** : combine les résultats des deux méthodes sur l'ensemble des tranches pour proposer le programme global.
                """
            )

            methode_opt = st.radio(
                "Méthode d'optimisation",
                ["Dichotomie actuarielle", "Frontière De Finetti–Borch", "Programme multi-tranches complet"],
                horizontal=True, key="labo_methode_opt"
            )

            c1, c2, c3 = st.columns(3)
            with c1:
                tranche_opt_idx = st.selectbox(
                    "Tranche de référence",
                    options=list(range(len(tranches_input))),
                    format_func=lambda i: tranches_input[i]["nom"],
                    key="labo_tranche_idx"
                ) if tranches_input else 0
            with c2:
                taux_cible_opt = st.number_input(
                    "Taux cible (%)", value=3.0, step=0.1, min_value=0.1,
                    key="labo_taux_cible") / 100
            with c3:
                budget_pct = st.number_input(
                    "Budget prime max (% GNPI)", value=4.0, step=0.1, min_value=0.1,
                    key="labo_budget_pct") / 100

            if st.button("Lancer l'optimisation", type="primary", key="btn_labo_opt2"):
                labo = _restore_labo(_make_labo())

                if methode_opt == "Dichotomie actuarielle":
                    if not tranches_input:
                        st.error("Aucune tranche définie.")
                    else:
                        t_base = tranches_input[tranche_opt_idx]
                        with st.spinner(f"Dichotomie sur la priorité de '{t_base['nom']}'..."):
                            res_dich = labo.optimiser_dichotomie(t_base, taux_cible_opt)
                        st.session_state["labo_opt_res"] = ("dichotomie", res_dich, t_base)

                elif methode_opt == "Frontière De Finetti–Borch":
                    if not tranches_input:
                        st.error("Aucune tranche définie.")
                    else:
                        t_base = tranches_input[tranche_opt_idx]
                        with st.spinner(f"Calcul frontière efficiente De Finetti pour '{t_base['nom']}'..."):
                            res_finetti = labo.frontiere_de_finetti(
                                t_base, budget_prime_pct=budget_pct, n_points=50)
                        st.session_state["labo_opt_res"] = ("finetti", res_finetti, t_base)

                else:  # multi-tranches
                    with st.spinner("Optimisation du programme complet (toutes tranches)..."):
                        resultats_mt = []
                        for i, t in enumerate(tranches_input):
                            r_d = labo.optimiser_dichotomie(t, taux_cible_opt)
                            r_f = labo.frontiere_de_finetti(t, budget_prime_pct=budget_pct, n_points=30)
                            resultats_mt.append({"tranche":t,"dichotomie":r_d,"finetti":r_f})
                    st.session_state["labo_opt_res"] = ("multi", resultats_mt, None)
                st.rerun()

            # ── Affichage des résultats d'optimisation ──
            if "labo_opt_res" in st.session_state:
                methode_r, res_r, t_r = st.session_state["labo_opt_res"]

                if methode_r == "dichotomie":
                    st.markdown(f"##### Résultat dichotomie — {t_r['nom']}")
                    if res_r is None:
                        st.error("Modèle non entraîné — lancez d'abord l'étape 3.")
                    elif not res_r.get("converge", True) or "message" in res_r:
                        msg = res_r.get("message","Cible hors plage atteignable.")
                        tau_lo = res_r.get("tau_lo",0); tau_hi = res_r.get("tau_hi",0)
                        st.warning(msg)
                        st.info(
                            f"Plage atteignable : [{min(tau_lo,tau_hi):.4%} — {max(tau_lo,tau_hi):.4%}]. "
                            f"Ajustez le taux cible dans cet intervalle."
                        )
                    else:
                        D_star = res_r["D_star"]; tau_star = res_r["tau_star"]
                        nb = res_r.get("nb_iter",0)
                        st.success(
                            f"**D\\* = {D_star:,.0f} MAD** → τ\\* = {tau_star:.4%} "
                            f"(convergé en {nb} itérations)"
                        )
                        tableau_resultats([{
                            "Priorité optimale D*": f"{D_star:,.0f}",
                            "Portée C":             f"{t_r['portee']:,.0f}",
                            "Taux obtenu τ*":       f"{tau_star:.4%}",
                            "Taux cible":           f"{taux_cible_opt:.4%}",
                            "Écart":                f"{abs(tau_star-taux_cible_opt)*100:.4f} pts",
                            "Itérations":           nb,
                            "Prime estimée (MAD)":  f"{gnpi*tau_star:,.0f}",
                        }])
                        # Tracer la convergence
                        iters = res_r.get("iterations",[])
                        if len(iters) > 2:
                            fig_d, ax_d = plt.subplots(figsize=(7,3))
                            ax_d.plot([it["D"] for it in iters],
                                      [it["tau"]*100 for it in iters],
                                      "o-", color="#2d8a4e", ms=4)
                            ax_d.axhline(taux_cible_opt*100, color="red",
                                         ls="--", label=f"Cible {taux_cible_opt:.2%}")
                            ax_d.set_xlabel("Priorité D (MAD)")
                            ax_d.set_ylabel("τ technique (%)")
                            ax_d.set_title("Convergence dichotomie")
                            ax_d.legend(); ax_d.grid(alpha=0.2)
                            st.pyplot(fig_d); plt.close()
                        st.caption(
                            "**Principe (De Wylder / Daykin–Pentikäinen–Pesonen)** : "
                            "τ est monotone décroissant en D (une priorité plus haute → "
                            "moins de sinistres touchent la tranche). "
                            "La bisection converge en O(log((D_max−D_min)/ε)) ≈ 50 itérations."
                        )

                elif methode_r == "finetti":
                    st.markdown(f"##### Frontière De Finetti–Borch — {t_r['nom']}")
                    if not res_r or not res_r.get("frontier"):
                        st.warning("Frontière vide. Vérifiez que le modèle ML est entraîné (étape 3).")
                    else:
                        frontier = res_r["frontier"]
                        optimal  = res_r.get("optimal")
                        fig_f, ax_f = plt.subplots(figsize=(7, 4))
                        xs = [p["prime_pct"]*100 for p in frontier]
                        ys = [p["var_retenue"]*1e4 for p in frontier]
                        ax_f.plot(xs, ys, "o-", color="#2d8a4e", ms=5, label="Frontière efficiente")
                        if optimal:
                            ax_f.scatter([optimal["prime_pct"]*100],
                                         [optimal.get("var_retenue",0)*1e4],
                                         color="red", s=120, zorder=5, label="Programme optimal")
                        ax_f.set_xlabel("Prime cédée (% GNPI)")
                        ax_f.set_ylabel("Variance retenue (×10⁻⁴)")
                        ax_f.set_title(
                            "Frontière efficiente De Finetti–Borch\n"
                            "min Var(retenu) s.c. E[cession] = budget"
                        )
                        ax_f.legend(); ax_f.grid(alpha=0.2)
                        st.pyplot(fig_f); plt.close()

                        if optimal:
                            st.success(
                                f"**Programme De Finetti optimal** : "
                                f"D\\* = {optimal.get('D',0):,.0f} · "
                                f"C = {optimal.get('C',0):,.0f} · "
                                f"τ\\* = {optimal.get('tau_pred',0):.4%}"
                            )
                            tableau_resultats([{
                                "Priorité D*":     f"{optimal.get('D',0):,.0f}",
                                "Portée C":        f"{optimal.get('C',0):,.0f}",
                                "Taux prédit":     f"{optimal.get('tau_pred',0):.4%}",
                                "Prime cédée":     f"{optimal.get('prime_pct',0):.4%}",
                                "Var retenue":     f"{optimal.get('var_retenue',0):.6f}",
                                "Score De Finetti":f"{optimal.get('score_finetti',0):.4f}",
                                "Prime (MAD)":     f"{gnpi*optimal.get('tau_pred',0):,.0f}",
                            }])
                        st.caption(
                            "**Borch (1969)** : pour une prime nette fixée, le stop-loss (XL) "
                            "minimise la variance de la perte retenue. "
                            "Le score De Finetti = Δvariance / prime mesure l'efficacité marginale "
                            "de chaque euro de prime cédée."
                        )

                elif methode_r == "multi":
                    st.markdown("##### Programme multi-tranches — Résultats consolidés")
                    st.caption(
                        "Un programme optimal est composé d'au moins 2 tranches. "
                        "Résultats dichotomie + De Finetti par tranche, puis consolidation."
                    )
                    rows_mt = []
                    prime_totale = 0.0
                    for item in res_r:
                        t = item["tranche"]
                        rd = item.get("dichotomie") or {}
                        rf = item.get("finetti") or {}
                        opt_f = rf.get("optimal") or {}
                        tau_d = rd.get("tau_star", 0) if rd.get("converge", False) else None
                        tau_f = opt_f.get("tau_pred", 0)
                        tau_retenu = tau_d or tau_f
                        prime_totale += gnpi * (tau_retenu or 0)
                        rows_mt.append({
                            "Tranche":          t["nom"],
                            "Type":             t["type"],
                            "D* Dich.":         f"{rd.get('D_star',0):,.0f}" if rd.get("converge") else "—",
                            "τ* Dich.":         f"{tau_d:.4%}" if tau_d else "—",
                            "D* De Finetti":    f"{opt_f.get('D',0):,.0f}" if opt_f else "—",
                            "τ* De Finetti":    f"{tau_f:.4%}" if tau_f else "—",
                            "τ Retenu":         f"{tau_retenu:.4%}" if tau_retenu else "—",
                            "Prime (MAD)":      f"{gnpi*(tau_retenu or 0):,.0f}",
                        })
                    tableau_resultats(rows_mt)
                    st.metric("Prime totale programme", f"{prime_totale:,.0f} MAD",
                              f"{prime_totale/gnpi:.4%} du GNPI")
                    st.caption(
                        "Le programme multi-tranches consolide la protection : "
                        "T1 travaillante (max BC/Sim) + T2/T3 cat (max Sim/Mkt). "
                        "La protection globale = somme des portées × (1 + reconstitutions)."
                    )

    # ═══════════════════════════════════════════════════════════
    # ÉTAPE 5 — NSGA-II  (Deb, Pratap, Agarwal & Meyarivan, 2002)
    # ═══════════════════════════════════════════════════════════
    if "labo_modeles" in st.session_state:
        with st.expander(
            "Étape 5 — NSGA-II : Optimisation multi-objectif (Front de Pareto)",
            expanded=False
        ):
            st.markdown(
                """
**NSGA-II** (*Non-dominated Sorting Genetic Algorithm II*, Deb et al. 2002)  
Algorithme évolutionnaire qui explore simultanément les **3 objectifs actuariels** :

| Objectif | Sens | Signification |
|---|---|---|
| **O1** τ_technique | Minimiser | Coût du programme (prime/GNPI) |
| **O2** Var(retenu) | Minimiser | Risque résiduel ≈ (τ_pur × k)² |
| **O3** Protection | Maximiser | Portée × (1+Rec) / GNPI |

**Opérateurs :** SBX crossover (η=20) + Mutation polynomiale (η=20) — Echchelh et al. (2019) confirme 98% de l'hypervolume Pareto en 20 générations pour des traités XL.
                """
            )
            c1, c2, c3, c4 = st.columns(4)
            with c1:
                nsga_pop  = st.number_input("Taille population", value=80, step=20,
                    min_value=20, max_value=200, key="nsga_pop")
            with c2:
                nsga_gen  = st.number_input("Générations", value=40, step=10,
                    min_value=10, max_value=200, key="nsga_gen")
            with c3:
                nsga_eta_c = st.number_input("η croisement (SBX)", value=20, step=5,
                    min_value=5, max_value=50, key="nsga_eta_c")
            with c4:
                nsga_multi = st.checkbox("Multi-tranches", value=True, key="nsga_multi",
                    help="Optimise toutes les tranches simultanément (chromosome global)")

            if st.button("Lancer NSGA-II", type="primary", key="btn_nsga2"):
                labo = _restore_labo(_make_labo())
                bar_nsga = st.progress(0, "Initialisation population...")
                def _nsga_cb(gen, n):
                    bar_nsga.progress(
                        int(gen/n*100),
                        f"Génération {gen}/{n} — convergence en cours..."
                    )
                with st.spinner("NSGA-II en cours..."):
                    result = labo.optimiser_nsga2(
                        pop_size    = int(nsga_pop),
                        n_gen       = int(nsga_gen),
                        eta_c       = int(nsga_eta_c),
                        eta_m       = int(nsga_eta_c),
                        multi_tranche = nsga_multi,
                        progress_cb = _nsga_cb,
                    )
                bar_nsga.progress(100, "Terminé ✓")
                st.session_state["nsga_result"] = result

            if "nsga_result" in st.session_state:
                result = st.session_state["nsga_result"]

                if "erreur" in result:
                    st.error(result["erreur"])
                else:
                    pareto = result["pareto"]
                    logp   = result["log"]
                    n_t    = result["n_tranches"]

                    st.success(
                        f"**{len(pareto)} solutions Pareto** trouvées en "
                        f"{result['n_gen']} générations · "
                        f"{result['pop_size']} individus · "
                        f"{n_t} tranche(s)"
                    )

                    # ── Graphiques 3D Pareto ──
                    col_a, col_b = st.columns(2)
                    import matplotlib.pyplot as plt

                    with col_a:
                        # O1 vs O2
                        fig1, ax1 = plt.subplots(figsize=(5, 4))
                        o1 = [p["O1_tau"]*100 for p in pareto]
                        o2 = [p["O2_var"]*1e4  for p in pareto]
                        sc = ax1.scatter(o1, o2, c=o1, cmap="RdYlGn_r", s=60, edgecolors="k", lw=0.4)
                        plt.colorbar(sc, ax=ax1, label="τ (%)")
                        ax1.set_xlabel("O1 : τ_technique (%)")
                        ax1.set_ylabel("O2 : Variance retenue (×10⁻⁴)")
                        ax1.set_title("Front de Pareto — Coût vs Risque")
                        ax1.grid(alpha=0.2)
                        st.pyplot(fig1); plt.close()

                    with col_b:
                        # O1 vs O3
                        fig2, ax2 = plt.subplots(figsize=(5, 4))
                        o3 = [p["O3_prot"]*100 for p in pareto]
                        sc2 = ax2.scatter(o1, o3, c=o3, cmap="Blues", s=60, edgecolors="k", lw=0.4)
                        plt.colorbar(sc2, ax=ax2, label="Protection (%)")
                        ax2.set_xlabel("O1 : τ_technique (%)")
                        ax2.set_ylabel("O3 : Protection nette (% GNPI)")
                        ax2.set_title("Front de Pareto — Coût vs Protection")
                        ax2.grid(alpha=0.2)
                        st.pyplot(fig2); plt.close()

                    # ── Convergence ──
                    if logp:
                        fig3, axes = plt.subplots(1, 3, figsize=(12, 3))
                        gens = [l["gen"] for l in logp]
                        for ax3, key, label, color in zip(
                            axes,
                            ["tau_min", "var_min", "prot_max"],
                            ["τ min (%)", "Var min (×10⁻⁴)", "Protection max (%)"],
                            ["#e74c3c", "#3498db", "#2ecc71"]
                        ):
                            vals = [l[key] * (100 if "tau" in key or "prot" in key else 1e4)
                                    for l in logp]
                            ax3.plot(gens, vals, color=color, lw=2)
                            ax3.set_xlabel("Génération")
                            ax3.set_ylabel(label)
                            ax3.set_title(label)
                            ax3.grid(alpha=0.2)
                        fig3.tight_layout()
                        st.pyplot(fig3); plt.close()

                    # ── Tableau du front de Pareto ──
                    st.markdown("##### Solutions Pareto — détail par tranche")
                    # Construire les colonnes dynamiquement selon n_tranches
                    rows_p = []
                    for sol in sorted(pareto, key=lambda p: p["O1_tau"]):
                        row = {
                            "τ total":  f"{sol['O1_tau']:.4%}",
                            "Var":      f"{sol['O2_var']:.2e}",
                            "Prot %":   f"{sol['O3_prot']*100:.1f}",
                            "Prime (MAD)": f"{gnpi*sol['O1_tau']:,.0f}",
                        }
                        for ti in range(n_t):
                            p = f"T{ti+1}"
                            row[f"{p} D"]     = f"{sol.get(p+'_D',0):,.0f}"
                            row[f"{p} C"]     = f"{sol.get(p+'_C',0):,.0f}"
                            row[f"{p} Rec"]   = sol.get(p+"_rec", 0)
                            row[f"{p} Marge"] = f"{sol.get(p+'_marge',0):.2%}"
                        rows_p.append(row)
                    if rows_p:
                        tableau_resultats(rows_p[:30])

                    # ── Solution compromis (TOPSIS simplifié) ──
                    # Normalise les 3 objectifs et choisit le point le plus proche de l'idéal
                    if len(pareto) >= 2:
                        O = np.array([[p["O1_tau"], p["O2_var"], -p["O3_prot"]] for p in pareto])
                        O_norm = (O - O.min(0)) / (O.max(0) - O.min(0) + 1e-12)
                        ideal  = np.zeros(3)   # objectifs normalisés minimaux
                        dists  = np.linalg.norm(O_norm - ideal, axis=1)
                        best   = pareto[int(np.argmin(dists))]
                        st.markdown("##### Solution compromis (TOPSIS — équilibre coût/risque/protection)")
                        comp_rows = [{
                            "τ total":     f"{best['O1_tau']:.4%}",
                            "Var retenue": f"{best['O2_var']:.2e}",
                            "Protection":  f"{best['O3_prot']*100:.1f}%",
                            "Prime (MAD)": f"{gnpi*best['O1_tau']:,.0f}",
                        }]
                        for ti in range(n_t):
                            p = f"T{ti+1}"
                            comp_rows[0][f"{p} D*"]    = f"{best.get(p+'_D',0):,.0f}"
                            comp_rows[0][f"{p} C"]     = f"{best.get(p+'_C',0):,.0f}"
                            comp_rows[0][f"{p} AAD"]   = f"{best.get(p+'_aad',0):,.0f}"
                            comp_rows[0][f"{p} Rec"]   = best.get(p+"_rec", 0)
                            comp_rows[0][f"{p} Rec1%"] = best.get(p+"_tr1", 100)
                            comp_rows[0][f"{p} k"]     = best.get(p+"_k", 0.20)
                            comp_rows[0][f"{p} Stab"]  = f"{best.get(p+'_stab',0):.0%}"
                            comp_rows[0][f"{p} Marge"] = f"{best.get(p+'_marge',0):.2%}"
                        tableau_resultats(comp_rows)
                        st.caption(
                            "**TOPSIS** (Hwang & Yoon, 1981) : solution la plus proche du point "
                            "idéal normalisé (τ=0, Var=0, Protection=max). "
                            "Représente le meilleur compromis coût/risque/protection du front de Pareto."
                        )
# ════════════════════════════════════════════

tab1, tab2, tab3, tab4, tab5, tab6, tab_agent, tab_full, tab_hist, tab_admin = st.tabs([
    " Programme", "📂 Données & Triangle",
    " Burning Cost", " Simulation",
    " Courbe de référence marché", " Rapport Final",
    " Agent Python", " Agent LLM", "📜 Historique", "🔐 Admin"
])

etapes_progress = [
    ("Programme",    "df_prog"       in st.session_state),
    ("Triangle",     "df_liq"        in st.session_state),
    ("Burning Cost", "resultats_bc"  in st.session_state),
    ("Simulation",   "resultats_sim" in st.session_state),
    ("Courbe de référence marché", "resultats_mkt" in st.session_state),
]
progress_steps(etapes_progress, current=0)

# ════════════════════════════════════════════
# TAB 1 — PROGRAMME
# ════════════════════════════════════════════

with tab1:
    st.header("Programme de Réassurance")
    st.caption("Définissez les tranches, conditions et paramètres de chargement")
    nb_tranches = st.number_input("Nombre de tranches", min_value=1, max_value=10, value=3)
    tranches_input = []
    defaults = {
        0: {"type": "travaillante", "priorite": 2_000_000,  "portee": 13_000_000},
        1: {"type": "cat",          "priorite": 15_000_000, "portee": 10_000_000},
        2: {"type": "cat",          "priorite": 25_000_000, "portee": 15_000_000},
    }
    for i in range(nb_tranches):
        d = defaults.get(i, {"type": "travaillante", "priorite": 2_000_000, "portee": 13_000_000})
        with st.expander(f"🔷 Tranche {i+1}", expanded=(i==0)):
            c1, c2, c3 = st.columns(3)
            with c1:
                st.markdown("**Identification**")
                nom      = st.text_input("Nom", value=f"Tranche {i+1}", key=f"nom_{i}")
                type_idx = ["travaillante","non_travaillante","cat"].index(d["type"])
                type_t   = st.selectbox("Type", ["travaillante","non_travaillante","cat"], index=type_idx, key=f"type_{i}")
                priorite = st.number_input("Priorité (MAD)", value=float(d["priorite"]), step=500_000.0,
                                           format="%.0f", key=f"prio_{i}")
                portee   = st.number_input("Portée (MAD)",   value=float(d["portee"]),   step=500_000.0,
                                           format="%.0f", key=f"port_{i}")
            with c2:
                st.markdown("**Conditions contractuelles**")
                has_aal  = st.checkbox("AAL", key=f"aal_{i}")
                aal_val  = st.number_input("Montant AAL (MAD)", value=0.0, step=100_000.0,
                                           format="%.2f", key=f"aal_v_{i}", disabled=not has_aal)
                has_aad  = st.checkbox("AAD", key=f"aad_{i}")
                aad_val  = st.number_input("Montant AAD (MAD)", value=0.0, step=100_000.0,
                                           format="%.2f", key=f"aad_v_{i}", disabled=not has_aad)
                has_indices = st.checkbox("Clause d'indexation", key=f"idx_{i}")
            with c3:
                st.markdown("**Frais & Charges**")
                brokage      = st.number_input("Brokage %",       value=10.0, min_value=0.0, max_value=30.0,
                                               step=0.01, format="%.2f", key=f"brok_{i}")
                frais        = st.number_input("Frais généraux %", value=5.0,  min_value=0.0, max_value=20.0,
                                               step=0.01, format="%.2f", key=f"frais_{i}")
                marge        = st.number_input("Marge %",          value=10.0, min_value=0.0, max_value=30.0,
                                               step=0.01, format="%.2f", key=f"marge_{i}")
                retrocession = st.number_input("Rétrocession %",   value=0.0,  min_value=0.0, max_value=50.0,
                                               step=0.01, format="%.2f", key=f"retro_{i}")

            # ── Reconstitutions : nb + taux individuel par reconstitution ──
            st.markdown("**Reconstitutions**")
            nb_recon = st.number_input("Nombre de reconstitutions", value=1, min_value=0, max_value=5,
                                       step=1, key=f"recon_{i}")
            taux_recons = []
            if nb_recon > 0:
                cols_rec = st.columns(min(nb_recon, 5))
                for r_idx in range(nb_recon):
                    with cols_rec[r_idx]:
                        t_r = st.number_input(
                            f"Reconst. {r_idx+1} %",
                            value=100.0, min_value=0.0, max_value=200.0,
                            step=0.5, format="%.1f",
                            key=f"txrecon_{i}_{r_idx}",
                            help=f"Taux de la {r_idx+1}ᵉ reconstitution")
                        taux_recons.append(t_r)
            if taux_recons:
                st.caption(f"Reconstitutions : {' | '.join([f'{r_idx+1}ᵉ→{t:.1f}%' for r_idx,t in enumerate(taux_recons)])}")

        tranches_input.append({
            "numero": i+1, "nom": nom, "type": type_t,
            "priorite": float(priorite), "portee": float(portee),
            "AAL": float(aal_val) if has_aal else None,
            "AAD": float(aad_val) if has_aad else None,
            "nb_reconstitutions": int(nb_recon),
            "taux_reconstitution": taux_recons[0] if taux_recons else 100.0,  # compat. ancienne formule
            "taux_reconstitutions": taux_recons,   # ← liste individuelle
            "indices": has_indices,
            "brokage": brokage/100, "frais": frais/100,
            "marge": marge/100, "retrocession": retrocession/100
        })
    if st.button(" Valider le programme", type="primary"):
        st.session_state["tranches_input"] = tranches_input
        st.session_state["gnpi"] = gnpi
        st.session_state["df_prog"] = pd.DataFrame([{
            "Tranche": t["nom"], "Type": t["type"],
            "Priorité": f"{t['priorite']:,.0f}", "Portée": f"{t['portee']:,.0f}",
            "AAL": f"{t['AAL']:,.0f}" if t["AAL"] else "—",
            "AAD": f"{t['AAD']:,.0f}" if t["AAD"] else "—",
            "Reconst.": " | ".join([f"{r_idx+1}→{tr:.0f}%" for r_idx,tr in enumerate(t['taux_reconstitutions'])]) if t.get("taux_reconstitutions") else f"{t['nb_reconstitutions']}x{t['taux_reconstitution']:.0f}%",
            "Indices": "" if t["indices"] else "—",
            "Brokage": f"{t['brokage']:.2%}", "Frais": f"{t['frais']:.2%}",
            "Marge": f"{t['marge']:.2%}", "Rétro": f"{t['retrocession']:.2%}",
        } for t in tranches_input])
        st.success(" Programme validé !")
    if "df_prog" in st.session_state:
        st.dataframe(st.session_state["df_prog"], use_container_width=True)
        c1, c2, c3 = st.columns(3)
        c1.metric("Travaillantes", sum(1 for t in tranches_input if t["type"]=="travaillante"))
        c2.metric("Cat",           sum(1 for t in tranches_input if t["type"]=="cat"))
        c3.metric("Non-trav.",     sum(1 for t in tranches_input if t["type"]=="non_travaillante"))

# ════════════════════════════════════════════
# TAB 2 — DONNÉES & TRIANGLE
# ════════════════════════════════════════════

with tab2:
    st.header("Données de base & Transformation triangle")
    type_branche = st.radio("Type de branche",
        ["Développement long (As-If + Stabilisation + Projection CL)",
         "Développement court (As-If uniquement, pas de projection)"],
        key="type_branche", horizontal=True)
    is_long = "long" in type_branche
    c1, c2, c3 = st.columns(3)
    with c1: f_triangle = st.file_uploader(" Triangle développement", type=["xlsx","csv"], key="f_tri")
    with c2: f_gnpis    = st.file_uploader(" Base GNPIs",             type=["xlsx","csv"], key="f_gnp")
    with c3: f_indices  = st.file_uploader(" Table indices",          type=["xlsx","csv"], key="f_idx")

    annee_cotation = st.number_input("Année de cotation (n)", value=2026, step=1)
    seuil_stabilisation = st.number_input(
        "Seuil stabilisation (% inflation, 0 = toujours)",
        value=0.0, min_value=0.0, max_value=50.0, step=5.0) / 100
    pct_seuil = st.number_input(
        "Percentile seuil Pareto (p80 par défaut)",
        value=0.80, min_value=0.50, max_value=0.99, step=0.05, format="%.2f")

    if st.button(" Transformer le triangle", type="primary") and f_triangle and f_gnpis and f_indices:
        with st.spinner("🔄 Transformation en cours..."):
            progress = st.progress(0, text="Lecture des fichiers...")
            df_gnpis_df = pd.read_excel(f_gnpis)  if f_gnpis.name.endswith('xlsx') else pd.read_csv(f_gnpis)
            df_idx_df   = pd.read_excel(f_indices) if f_indices.name.endswith('xlsx') else pd.read_csv(f_indices)
            df_gnpis_df.columns = [str(c).strip() for c in df_gnpis_df.columns]
            df_idx_df.columns   = [str(c).strip() for c in df_idx_df.columns]

            progress.progress(10, text="Nettoyage indices...")
            
            df_idx_df['Annee'] = pd.to_numeric(
                df_idx_df['Annee'].astype(str).str.strip().str.replace('.0', '', regex=False),
                errors='coerce'
            )
            
            df_idx_df['Coefficients'] = pd.to_numeric(
                df_idx_df['Coefficients']
                .astype(str)
                .str.strip()
                .str.replace(',', '.', regex=False)
                .str.replace(' ', '', regex=False),
                errors='coerce'
            )
            
            df_idx_df = df_idx_df.dropna(subset=['Annee', 'Coefficients'])
            df_idx_df['Annee'] = df_idx_df['Annee'].astype(int)
            df_idx_df = df_idx_df.sort_values('Annee')
            
            # ─────────────────────────────────────────────
            # Projection future des indices
            # ─────────────────────────────────────────────
            inflation_future = st.number_input(
                "Inflation future annuelle des indices (%)",
                value=3.0,
                min_value=0.0,
                max_value=30.0,
                step=0.5,
                help=(
                    "Taux utilisé pour projeter les indices futurs. "
                    "Exemple : si le dernier indice connu est 2025, "
                    "l'outil projette 2026, 2027, ..., 2035."
                )
            ) / 100
            
            horizon_projection_indices = 10
            
            df_idx_set = df_idx_df.set_index('Annee')['Coefficients']
            
            annee_min_indice = int(df_idx_set.index.min())
            annee_max_connue = int(df_idx_set.index.max())
            
            indices_proj = {
                int(a): float(v)
                for a, v in df_idx_set.items()
            }
            
            for annee in range(annee_max_connue + 1, annee_max_connue + horizon_projection_indices + 1):
                indices_proj[annee] = indices_proj[annee - 1] * (1 + inflation_future)
            
            annees_indices_proj = np.array(sorted(indices_proj.keys()), dtype=int)
            valeurs_indices_proj = np.array([indices_proj[a] for a in annees_indices_proj], dtype=float)
            
            def get_indice(annee):
                annee = int(annee)
            
                if annee in indices_proj:
                    return float(indices_proj[annee])
            
                if annee < annee_min_indice:
                    annees_hist = df_idx_set.index.values.astype(int)
                    valeurs_hist = df_idx_set.values.astype(float)
            
                    if len(annees_hist) >= 2:
                        return float(
                            valeurs_hist[0]
                            - (valeurs_hist[1] - valeurs_hist[0])
                            * (annees_hist[0] - annee)
                        )
            
                    return float(valeurs_hist[0])
            
                return np.nan
            
            I_cotation_val = get_indice(annee_cotation)
            
            if pd.isna(I_cotation_val):
                st.error(
                    f"L'indice de l'année de cotation {annee_cotation} est indisponible. "
                    f"Dernière année projetée : {annee_max_connue + horizon_projection_indices}."
                )
                st.stop()
            
            st.info(
                f" I_cotation({annee_cotation}) = {I_cotation_val:.4f} | "
                f"Dernière année connue : {annee_max_connue} | "
                f"Projection jusqu'à : {annee_max_connue + horizon_projection_indices} | "
                f"Inflation future : {inflation_future:.2%}"
            )


            progress.progress(20, text="Parsing triangle...")
            df_raw = pd.read_excel(f_triangle, header=None)

            # ══════════════════════════════════════════════════════════
            # PARSER ROBUSTE — Format : UW Year | PAID OS TOTAL par an
            # ══════════════════════════════════════════════════════════

            # ── ÉTAPE 1 : Trouver la ligne des années de règlement ──
            # C'est la ligne qui contient le plus de valeurs numériques 2000-2050
            header_year_row = 0
            best_year_count = 0
            for row_idx in range(min(8, len(df_raw))):
                row_vals = df_raw.iloc[row_idx].tolist()
                cnt = 0
                for v in row_vals:
                    try:
                        vi = int(float(str(v).strip()))
                        if 1990 <= vi <= 2060: cnt += 1
                    except: pass
                if cnt > best_year_count:
                    best_year_count = cnt
                    header_year_row = row_idx
            header_type_row = header_year_row + 1
            data_start_row  = header_type_row + 1

            st.info(f" En-têtes : ligne {header_year_row+1} (années) | ligne {header_type_row+1} (PAID/OS/TOTAL) | Données à partir de la ligne {data_start_row+1}")

            # ── ÉTAPE 2 : Construire col_info — (annee_regl, type) par colonne ──
            ligne_annees = df_raw.iloc[header_year_row].tolist()
            ligne_types  = df_raw.iloc[header_type_row].tolist()
            annee_courante = None
            col_info = []  # liste de (annee_regl, type_normalise) pour chaque colonne
            for i, (ann, typ) in enumerate(zip(ligne_annees, ligne_types)):
                if i == 0:
                    col_info.append(('UW_YEAR', 'UW_YEAR'))
                    continue
                # Mise à jour de l'année courante si on trouve une année valide
                try:
                    a = int(float(str(ann).strip()))
                    if 1990 <= a <= 2060:
                        annee_courante = a
                except: pass
                # Normalisation du type de colonne
                typ_str = str(typ).strip().upper() if pd.notna(typ) and str(typ).strip() not in ('nan','NaN','') else ''
                # Mapping vers types normalisés
                if   typ_str in ('TOTAL', 'TOT', 'CUMUL', 'AMOUNT', 'MONTANT', 'INCURRED'):
                    typ_norm = 'TOTAL'
                elif typ_str in ('PAID', 'PAY', 'PAID LOSS', 'PAYE', 'PAYÉ', 'REGLEMENT', 'RÈGLEMENT'):
                    typ_norm = 'PAID'
                elif typ_str in ('OS', 'O/S', 'OUTSTANDING', 'RESERVE', 'RÉSERVE', 'SUSPENS', 'IBNR'):
                    typ_norm = 'OS'
                else:
                    typ_norm = typ_str  # garder tel quel
                col_info.append((annee_courante, typ_norm))

            # Résumé des colonnes détectées
            cols_total = [(i, a) for i,(a,t) in enumerate(col_info) if t=='TOTAL']
            cols_paid  = [(i, a) for i,(a,t) in enumerate(col_info) if t=='PAID']
            cols_os    = [(i, a) for i,(a,t) in enumerate(col_info) if t=='OS']
            annees_reg_detectees = sorted(set(a for a,t in col_info if t=='TOTAL' and a is not None))
            st.success(f" Colonnes détectées — TOTAL : {len(cols_total)} | PAID : {len(cols_paid)} | OS : {len(cols_os)} | Années règlement : {annees_reg_detectees[0] if annees_reg_detectees else '?'} → {annees_reg_detectees[-1] if annees_reg_detectees else '?'}")

            if len(cols_total) == 0:
                st.error(" Aucune colonne TOTAL trouvée. Vérifiez que la ligne des types contient bien 'TOTAL'.")
                st.dataframe(df_raw.iloc[:data_start_row], use_container_width=True)
                st.stop()

            # ── ÉTAPE 3 : Extraire les données — 1 ligne = 1 sinistre ──
            df_data = df_raw.iloc[data_start_row:].reset_index(drop=True)
            # Propagation de l'année de survenance (cellules fusionnées → ffill)
            df_data.iloc[:, 0] = df_data.iloc[:, 0].ffill()

            progress.progress(30, text="Extraction sinistres...")
            records = []
            sinistre_counter = {}  # {annee_surv: compteur} pour numéroter les sinistres
            for idx_row, row in df_data.iterrows():
                # Lire l'année de survenance (colonne A)
                try:
                    raw_uw = str(row.iloc[0]).strip().replace('.0','')
                    annee_surv = int(float(raw_uw))
                    if not (1990 <= annee_surv <= 2060): continue
                except: continue

                # Numéroter chaque sinistre dans l'année de survenance
                sinistre_counter[annee_surv] = sinistre_counter.get(annee_surv, 0) + 1
                sin_num = sinistre_counter[annee_surv]
                sinistre_id = f"{annee_surv}_S{sin_num:04d}"

                # Lire les colonnes TOTAL pour chaque année de règlement
                for col_idx, (annee_reg, typ) in enumerate(col_info):
                    if typ != 'TOTAL' or annee_reg is None: continue
                    val = row.iloc[col_idx]
                    try:
                        if pd.isna(val): continue
                        if isinstance(val, str):
                            val = val.strip().replace(',','.').replace(' ','').replace('\xa0','')
                            if not val or any(c.isalpha() for c in val) or '#' in val: continue
                        val = float(val)
                        if val <= 0 or np.isnan(val) or np.isinf(val): continue
                    except: continue
                    dev = annee_reg - annee_surv
                    if dev < 0 or dev > 15: continue  # max 15 ans de dev (flexible)
                    records.append({
                        'sinistre_id': sinistre_id,
                        'annee_surv':  annee_surv,
                        'annee_reg':   annee_reg,
                        'dev':         dev,
                        'total':       val
                    })

            if not records:
                st.error(" Aucune donnée extraite. Vérifiez le format du fichier.")
                st.markdown("**5 premières lignes du fichier brut :**")
                st.dataframe(df_raw.head(5), use_container_width=True)
                st.stop()

            # Résumé du parsing
            annees_surv_uniq = sorted(set(r['annee_surv'] for r in records))
            st.success(f" Extraction OK — {len(records):,} observations | {len(annees_surv_uniq)} années de survenance ({annees_surv_uniq[0]}→{annees_surv_uniq[-1]}) | {sum(sinistre_counter.values()):,} sinistres")

            df_liq = pd.DataFrame(records)
            # ── Trier par sinistre et développement croissant (obligatoire pour le décumul) ──
            df_liq = df_liq.sort_values(['sinistre_id', 'dev']).reset_index(drop=True)

            progress.progress(48, text="Indices...")
            
            df_liq['I_reg'] = df_liq['annee_reg'].apply(get_indice)
            df_liq['I_surv'] = df_liq['annee_surv'].apply(get_indice)
            
            # Délai historique de règlement :
            # exemple : survenance 2016, règlement 2018 → délai = 2 ans
            df_liq['delai_reglement'] = df_liq['annee_reg'] - df_liq['annee_surv']
            
            # Année de règlement projetée dans le scénario AS-IF :
            # exemple : année AS-IF 2026 + délai 2 = règlement projeté 2028
            df_liq['annee_reg_asif'] = annee_cotation + df_liq['delai_reglement']
            
            # Indice futur correspondant à l'année de règlement projetée
            df_liq['I_reg_asif'] = df_liq['annee_reg_asif'].apply(get_indice)
            
            # Indice de survenance dans le scénario AS-IF
            df_liq['I_surv_asif'] = I_cotation_val
            
            # I_ultime gardé pour affichage / compatibilité
            df_liq['annee_ultime'] = df_liq['annee_surv'] + 9
            df_liq['I_ultime'] = df_liq['annee_ultime'].apply(get_indice)
            
            if df_liq[['I_reg', 'I_surv', 'I_reg_asif']].isna().any().any():
                annees_manquantes = sorted(
                    set(
                        df_liq.loc[df_liq['I_reg'].isna(), 'annee_reg'].dropna().astype(int).tolist()
                        + df_liq.loc[df_liq['I_surv'].isna(), 'annee_surv'].dropna().astype(int).tolist()
                        + df_liq.loc[df_liq['I_reg_asif'].isna(), 'annee_reg_asif'].dropna().astype(int).tolist()
                    )
                )
            
                st.error(
                    "Indices manquants pour certaines années : "
                    f"{annees_manquantes}. "
                    "Augmentez l'horizon de projection ou vérifiez la table des indices."
                )
                st.stop()
            
            progress.progress(50, text="Décumul → As-If sur incréments...")
            
            # ── ÉTAPE 1 : DÉCUMULER ──
            df_liq['prev_total'] = (
                df_liq
                .groupby('sinistre_id')['total']
                .shift(1)
                .fillna(0)
            )
            
            df_liq['increment'] = (
                df_liq['total'] - df_liq['prev_total']
            ).clip(lower=0)
            
            # ── ÉTAPE 2 : AS-IF SUR L'INCRÉMENT AVEC DÉLAI DE RÈGLEMENT ──
            # Formule :
            # inc_asif = increment × I_(année_cotation + délai_règlement) / I_règlement_historique
            #
            # Exemple :
            # Survenance 2016, règlement 2018, année AS-IF 2026
            # délai = 2018 - 2016 = 2
            # année de règlement AS-IF = 2026 + 2 = 2028
            # inc_asif = increment × I_2028 / I_2018
            
            df_liq['inc_asif'] = df_liq['increment'] * (
                df_liq['I_reg_asif'] / df_liq['I_reg']
            )
            
            progress.progress(55, text="Stabilisation sur incréments...")
            
            # ── ÉTAPE 3 : STABILISATION SUR L'INCRÉMENT ──
            # La stabilisation doit maintenant être testée dans le scénario AS-IF :
            # ratio = I_règlement_ASIF / I_survenance_ASIF
            #
            # Comme la survenance AS-IF est l'année de cotation :
            # I_survenance_ASIF = I_cotation
            
            df_liq['ratio_check'] = df_liq['I_reg_asif'] / df_liq['I_surv_asif']
            
            mask_stab = df_liq['ratio_check'] >= (1.0 + seuil_stabilisation)
            
            df_liq['inc_stab'] = np.where(
                mask_stab,
                df_liq['inc_asif'] * (df_liq['I_surv_asif'] / df_liq['I_reg_asif']),
                df_liq['inc_asif']
            )
            
            n_stab = int(mask_stab.sum())
            
            annees_reg_stab = sorted(
                df_liq.loc[mask_stab, 'annee_reg_asif']
                .dropna()
                .astype(int)
                .unique()
                .tolist()
            )
            
            st.info(
                f" Décumul + Stab | "
                f"Seuil : {seuil_stabilisation*100:.0f}% | "
                f"Incréments stab. : {n_stab} | "
                f"Années règlement AS-IF : {annees_reg_stab}"
            )
            
            # ── ÉTAPE 4 : RECUMULER ──
            df_liq['Sk'] = (
                df_liq
                .groupby('sinistre_id')['inc_asif']
                .cumsum()
            )
            
            df_liq['S_prime_k'] = (
                df_liq
                .groupby('sinistre_id')['inc_stab']
                .cumsum()
            )
            
            df_liq['coeff_stab'] = np.where(
                df_liq['S_prime_k'] > 0,
                df_liq['Sk'] / df_liq['S_prime_k'],
                1.0
            )

            # Vérification : n sinistres avec incrément négatif (réductions de réserves)
            n_neg = (df_liq['increment'] < 0).sum()
            if n_neg > 0:
                st.warning(f" {n_neg} incréments négatifs détectés (réductions de réserves) → mis à 0 pour la modélisation")


            if is_long:
                progress.progress(65, text="Chain Ladder...")
                facteurs = {k: [] for k in range(9)}
                for sin_id, grp in df_liq.groupby('sinistre_id'):
                    grp = grp.sort_values('dev').set_index('dev')
                    for k in range(9):
                        if k in grp.index and (k+1) in grp.index:
                            t_k = grp.loc[k, 'S_prime_k']; t_k1 = grp.loc[k+1, 'S_prime_k']
                            if t_k > 0:
                                f = t_k1 / t_k
                                if 0.9 <= f <= 2.5: facteurs[k].append(f)
                f_moyens = {k: np.mean(facteurs[k]) if facteurs[k] else 1.0 for k in range(9)}

                progress.progress(75, text="Projection...")
                projections = []
                for sin_id, grp in df_liq.groupby('sinistre_id'):
                    grp = grp.sort_values('dev').set_index('dev')
                    annee_surv_p = grp['annee_surv'].iloc[0]
                    dev_max = grp.index.max()
                    Sprime_ultime = grp.loc[dev_max, 'S_prime_k']
                    coeff_sin = grp.loc[dev_max, 'coeff_stab']
                    for k in range(dev_max, 9): Sprime_ultime *= f_moyens[k]
                    projections.append({'sinistre_id': sin_id, 'annee_surv': annee_surv_p,
                                        'dev_max': dev_max, 'Sprime_ultime': Sprime_ultime,
                                        'Sk_ultime': Sprime_ultime * coeff_sin, 'coeff_stab': coeff_sin})
                df_facteurs_df = pd.DataFrame({
                    'Dev.': [f"{k}→{k+1}" for k in range(9)],
                    'Facteur moyen': [round(f_moyens[k], 4) for k in range(9)],
                    'Nb observations': [len(facteurs[k]) for k in range(9)]})
            else:
                progress.progress(65, text="Branche courte...")
                df_liq['S_prime_k']  = df_liq['Sk']
                df_liq['coeff_stab'] = 1.0
                f_moyens = {k: 1.0 for k in range(9)}
                projections = []
                for sin_id, grp in df_liq.groupby('sinistre_id'):
                    grp = grp.sort_values('dev').set_index('dev')
                    annee_surv_p = grp['annee_surv'].iloc[0]
                    dev_max = grp.index.max()
                    Sk_actuel = grp.loc[dev_max, 'Sk']
                    projections.append({'sinistre_id': sin_id, 'annee_surv': annee_surv_p,
                                        'dev_max': dev_max, 'Sprime_ultime': Sk_actuel,
                                        'Sk_ultime': Sk_actuel, 'coeff_stab': 1.0})
                df_facteurs_df = pd.DataFrame({'Info': ['Branche courte']})

            df_proj = pd.DataFrame(projections)
            progress.progress(85, text="Alpha & Lambda...")
            D_trav = next((t['priorite'] for t in tranches_input if t['type'] == 'travaillante'), 2_000_000)
            seuil_model = pct_seuil * D_trav
            X_all = df_proj['Sprime_ultime'].values; X_all = X_all[X_all > 0]
            Pm_proxy = np.percentile(X_all, 99.5)
            X_model = X_all[(X_all >= seuil_model) & (X_all < Pm_proxy)]
            if len(X_model) < 5: X_model = X_all[X_all >= seuil_model]
            t_min = np.min(X_model); n_model = len(X_model)
            alpha_est = n_model / np.sum(np.log(X_model / t_min))
            df_gnpis_idx = df_gnpis_df.set_index(df_gnpis_df.columns[0])
            gnpi_col = df_gnpis_df.columns[1]
            df_proj_model = df_proj[(df_proj['Sprime_ultime'] >= seuil_model) & (df_proj['Sprime_ultime'] < Pm_proxy)]
            N_obs = df_proj_model.groupby('annee_surv').size()
            N_asif_vals = []
            for ann, cnt in N_obs.items():
                try:
                    gnpi_ann = float(df_gnpis_idx.loc[ann, gnpi_col])
                    N_asif_vals.append(cnt * gnpi / gnpi_ann)
                except: N_asif_vals.append(cnt)
            lambda_est = float(np.mean(N_asif_vals)) if N_asif_vals else 5.0
            coeffs_raw = df_proj['coeff_stab'].values
            coeffs = coeffs_raw[(coeffs_raw > 0) & np.isfinite(coeffs_raw)]

            C_trav = next((t['portee'] for t in tranches_input if t['type'] == 'travaillante'), 13_000_000)
            # ── Identification sinistres majeurs par TVE GPD (toutes tranches) ──
            res_maj = identifier_sinistres_majeurs_gpd(
                df_proj=df_proj, gnpi=gnpi, tranches_input=tranches_input,
                nb_annees_obs=df_proj['annee_surv'].nunique(),
                retour_ans=20, pct_seuil=pct_seuil)
            df_seuils, _ = selectionner_seuil_pareto(X=df_proj['Sprime_ultime'].values, D=D_trav)

            # Chargements par tranche → stockés pour Tab3 et agents
            chargements_par_tranche = res_maj.get("chargements_par_tranche", {})

            progress.progress(100, text="Terminé !")
            st.session_state.update({
                "df_liq": df_liq, "df_proj": df_proj, "f_moyens": f_moyens,
                "alpha_est": float(alpha_est), "lambda_est": float(lambda_est),
                "seuil_est": float(seuil_model), "Pm_proxy": float(Pm_proxy),
                "coeffs": coeffs, "is_long": is_long,
                "I_cotation": I_cotation_val, "annee_cotation": annee_cotation,
                "seuil_stabilisation": seuil_stabilisation,
                "df_gnpis_df": df_gnpis_df, "df_facteurs": df_facteurs_df,
                "res_majeurs": res_maj, "df_seuils_pareto": df_seuils,
                "chargement_majeurs":          res_maj["chargement"],
                "chargements_par_tranche":     chargements_par_tranche,
            })
            st.success("Transformation terminée !")

    if "df_liq" in st.session_state:
        # ── DIAGNOSTIC — ce que le parser a réellement lu ──
        with st.expander("🔎 Diagnostic parsing — Vérifiez que le triangle est bien lu", expanded=True):
            df_liq_diag = st.session_state["df_liq"]
            annees_surv  = sorted(df_liq_diag["annee_surv"].unique().tolist())
            annees_regl  = sorted(df_liq_diag["annee_reg"].unique().tolist())
            devs         = sorted(df_liq_diag["dev"].unique().tolist())
            st.markdown(f"""<div style="display:flex;gap:16px;flex-wrap:wrap;margin-bottom:12px">
                <div style="background:#f0fff4;border:1px solid #2d8a4e;border-radius:8px;padding:10px 16px">
                    <b style="color:#2d8a4e">Années de survenance (UW Year)</b><br>
                    <span style="font-size:13px">{annees_surv[0]} → {annees_surv[-1]} | {len(annees_surv)} années</span>
                </div>
                <div style="background:#f0fff4;border:1px solid #2d8a4e;border-radius:8px;padding:10px 16px">
                    <b style="color:#2d8a4e">Années de règlement (colonnes)</b><br>
                    <span style="font-size:13px">{annees_regl[0]} → {annees_regl[-1]} | {len(annees_regl)} années</span>
                </div>
                <div style="background:#f0fff4;border:1px solid #2d8a4e;border-radius:8px;padding:10px 16px">
                    <b style="color:#2d8a4e">Développements trouvés</b><br>
                    <span style="font-size:13px">{devs}</span>
                </div>
                <div style="background:#f0fff4;border:1px solid #2d8a4e;border-radius:8px;padding:10px 16px">
                    <b style="color:#2d8a4e">Total observations</b><br>
                    <span style="font-size:13px">{len(df_liq_diag):,} lignes | {df_liq_diag['sinistre_id'].nunique():,} sinistres</span>
                </div></div>""", unsafe_allow_html=True)

            # Tableau récapitulatif par année de survenance
            recap = df_liq_diag.groupby("annee_surv").agg(
                nb_sinistres=("sinistre_id","nunique"),
                dev_max=("dev","max"),
                total_brut=("total","sum"),
                S_prime_moy=("S_prime_k","mean")
            ).reset_index()
            recap.columns = ["UW Year","Nb sinistres","Dev max obs.","Total brut (MAD)","S'k moyen (MAD)"]
            recap["Total brut (MAD)"] = recap["Total brut (MAD)"].apply(lambda x: f"{x:,.0f}")
            recap["S'k moyen (MAD)"]  = recap["S'k moyen (MAD)"].apply(lambda x: f"{x:,.0f}")
            st.markdown("**Résumé par année de survenance — si les années ne correspondent pas à votre fichier, vérifiez ci-dessous :**")
            st.dataframe(recap, use_container_width=True)

            # Afficher les 5 premières lignes brutes pour déboguer
            with st.expander(" Données brutes parsées (5 premières lignes)", expanded=False):
                st.dataframe(df_liq_diag.head(10), use_container_width=True)
                st.caption("Si les années de survenance ou les montants sont faux → votre fichier a probablement une ligne de titre supplémentaire en haut, ou les colonnes TOTAL sont nommées différemment.")

        c1b, c2b, c3b = st.columns(3)
        c1b.metric("Observations", len(st.session_state['df_liq']))
        c2b.metric("Sinistres",    st.session_state['df_liq']['sinistre_id'].nunique())
        c3b.metric("Années",       st.session_state['df_liq']['annee_surv'].nunique())
        branch_label = "Longue" if st.session_state.get("is_long") else "Courte"
        st.info(f"🌿 Branche : **{branch_label}** | I_cotation({st.session_state.get('annee_cotation')}) = {st.session_state.get('I_cotation',1):.4f}")
        st.info(f"Seuil modélisation : {st.session_state.get('seuil_est',0):,.0f} MAD | Alpha : {st.session_state.get('alpha_est',0):.4f} | Lambda : {st.session_state.get('lambda_est',0):.4f}")

        if "df_proj" in st.session_state:
            import matplotlib.pyplot as plt
            from scipy import stats as _sp_gpd

            charges_all = st.session_state["df_proj"]["Sprime_ultime"].values
            charges_all = charges_all[charges_all > 0]
            charges_sorted_desc = np.sort(charges_all)[::-1]
            n_all = len(charges_all)

            st.markdown("---")
            st.markdown("#### Identification des sinistres majeurs — Choix du seuil u (TVE/GPD)")
            st.caption(
                "u est le seuil au-dessus duquel on ajuste une GPD pour calculer le niveau de retour Pm. "
                "Il est distinct du seuil de modélisation (utilisé pour alpha/lambda). "
                "Analysez les graphiques ci-dessous pour le choisir manuellement."
            )

            # ════════════════════════════════════════════════
            # ÉTAPE 1 — Graphiques diagnostiques (Hill, MEF, Gertensgarbe)
            # ════════════════════════════════════════════════
            with st.expander("Étape 1 — Hill · MEF · Gertensgarbe", expanded=True):

                import matplotlib.pyplot as plt
                import matplotlib.ticker as mticker

                k_max = min(len(charges_sorted_desc) - 1, 200)
                ks    = np.arange(1, k_max + 1)

                # ── Hill estimates α(k) = k / Σ log(X_(i)/X_(k+1)) ──
                hills = np.array([
                    k / np.sum(np.log(charges_sorted_desc[:k] / charges_sorted_desc[k]))
                    if charges_sorted_desc[k] > 0 and
                       np.sum(np.log(charges_sorted_desc[:k] / charges_sorted_desc[k])) > 0
                    else np.nan
                    for k in ks
                ])
                # IC 95 % : α ± 1.96 × α/√k
                with np.errstate(invalid='ignore'):
                    ci_up  = hills + 1.96 * hills / np.sqrt(ks)
                    ci_low = np.maximum(hills - 1.96 * hills / np.sqrt(ks), 0)

                # ── Gertensgarbe — Mann-Kendall progressif / régressif sur α(k) ──
                ok   = ~np.isnan(hills)
                h_ok = hills[ok]; k_ok = ks[ok]; nk = len(h_ok)

                u_fwd = np.zeros(nk)
                for i in range(2, nk):
                    s = sum(1 for j in range(i) if h_ok[j] < h_ok[i])
                    e_s = i * (i - 1) / 4
                    v_s = i * (i - 1) * (2 * i + 5) / 72
                    u_fwd[i] = (s - e_s) / np.sqrt(v_s)

                h_rev  = h_ok[::-1]
                u_bwd_rev = np.zeros(nk)
                for i in range(2, nk):
                    s = sum(1 for j in range(i) if h_rev[j] < h_rev[i])
                    e_s = i * (i - 1) / 4
                    v_s = i * (i - 1) * (2 * i + 5) / 72
                    u_bwd_rev[i] = (s - e_s) / np.sqrt(v_s)
                u_bwd = u_bwd_rev[::-1]

                diff_gb   = u_fwd - u_bwd
                cross_idx = np.where(np.diff(np.sign(diff_gb)))[0]
                k_gert    = int(k_ok[cross_idx[0]]) if len(cross_idx) > 0 else int(k_ok[nk // 2])
                u_gert    = float(charges_sorted_desc[k_gert - 1]) if k_gert <= len(charges_sorted_desc) else float(np.percentile(charges_all, 80))
                alpha_gert = float(hills[k_gert - 1]) if k_gert - 1 < len(hills) else 1.5

                # ── MEF — cercles ouverts sur chaque valeur triée (style meplot R) ──
                # On prend toutes les valeurs uniques triées sauf la dernière
                u_sorted = np.sort(np.unique(charges_all))
                # Limiter à ~80 points pour la lisibilité
                step  = max(1, len(u_sorted) // 80)
                u_mef = u_sorted[::step][:-1]
                mef   = np.array([
                    float(np.mean(charges_all[charges_all > u] - u))
                    if np.sum(charges_all > u) >= 2 else np.nan
                    for u in u_mef
                ])
                valid_mef = ~np.isnan(mef)
                # Seuil MeanExc : valeur médiane de la zone de linéarité
                s_mef = float(st.session_state.get("seuil_est", float(np.percentile(charges_all, 60))))

                # ════════════════════════════════
                fig, axes = plt.subplots(1, 3, figsize=(16, 5))
                for ax in axes:
                    ax.set_facecolor("white")
                    ax.spines[['top', 'right']].set_visible(False)
                fig.patch.set_facecolor("white")

                # ── (1) Hill plot ──
                ax1 = axes[0]
                ax1.plot(k_ok, h_ok, color="black", lw=1.2)
                ax1.fill_between(ks[ok], ci_low[ok], ci_up[ok],
                                 color="steelblue", alpha=0.25, label="IC 95 %")
                ax1.axvline(k_gert, color="red", ls="--", lw=2,
                            label=f"k = {k_gert}")
                ax1.set_xlabel("Order Statistics")
                ax1.set_ylabel("Tail Index")
                ax1.set_title("Hill Plot")
                ax1.legend(fontsize=8)
                ax1.grid(alpha=0.2, linestyle="--")

                # ── (2) MEF — cercles ouverts, style meplot(X) ──
                ax2 = axes[1]
                ax2.scatter(u_mef[valid_mef], mef[valid_mef],
                            s=30, facecolors="none", edgecolors="black",
                            linewidths=0.8)
                ax2.axvline(s_mef, color="red", ls="--", lw=2,
                            label=f"s = {s_mef:,.0f}")
                ax2.set_xlabel("Threshold")
                ax2.set_ylabel("Mean Excess")
                ax2.set_title("Mean Excess Function")
                ax2.xaxis.set_major_formatter(mticker.ScalarFormatter(useMathText=True))
                ax2.yaxis.set_major_formatter(mticker.ScalarFormatter(useMathText=True))
                ax2.ticklabel_format(axis='both', style='sci', scilimits=(0, 0))
                ax2.legend(fontsize=8)
                ax2.grid(alpha=0.2, linestyle="--")

                # ── (3) Gertensgarbe — deux courbes croisées ──
                ax3 = axes[2]
                ax3.plot(k_ok, u_fwd, color="black", lw=1.5, label="U progressif")
                ax3.plot(k_ok, u_bwd, color="black", lw=1.5, ls="--",
                         label="U régressif")
                ax3.axhline(0, color="black", lw=0.6, alpha=0.4)
                ax3.axvline(k_gert, color="red", ls="--", lw=2,
                            label=f"k* = {k_gert}  (u ≈ {u_gert:,.0f})")
                ax3.set_xlabel("Order Statistics")
                ax3.set_ylabel("Statistique U(k)")
                ax3.set_title("Gertensgarbe-Werner")
                ax3.legend(fontsize=8)
                ax3.grid(alpha=0.2, linestyle="--")

                plt.tight_layout()
                st.pyplot(fig); plt.close()

                st.info(
                    f"Gertensgarbe → k* = {k_gert}  |  u suggéré = {u_gert:,.0f} MAD  |  "
                    f"α = {alpha_gert:.4f}  |  "
                    "Cherchez la zone stable du Hill et la linéarité du MEF pour confirmer u."
                )

            # ════════════════════════════════════════════════
            # ÉTAPE 2 — Saisie manuelle de u
            # ════════════════════════════════════════════════
            with st.expander("Étape 2 — Saisie du seuil u retenu", expanded=True):
                st.caption(
                    "u ≠ seuil de modélisation. "
                    "u est choisi sur toute la base pour le fit GPD et le calcul de Pm. "
                    "u2 (seuil de modélisation) est sur les données courants pour alpha/lambda."
                )
                col_u1, col_u2, col_u3 = st.columns(3)
                with col_u1:
                    u_default = st.session_state.get("u_gpd_retenu", round(u_gert / 10000) * 10000)
                    u_choisi = st.number_input(
                        "u retenu (MAD)",
                        value=float(u_default),
                        min_value=float(np.percentile(charges_all, 10)),
                        max_value=float(np.percentile(charges_all, 99)),
                        step=50_000.0, format="%.0f",
                        key="u_gpd_input",
                        help="Seuil choisi après analyse Hill + MEF + Gertensgarbe"
                    )
                with col_u2:
                    retour_gpd = st.number_input("Période de retour (ans)", value=20, min_value=5, max_value=100, step=5, key="retour_gpd")
                with col_u3:
                    nb_ann_gpd = st.number_input("Nb années observation", value=int(st.session_state["df_proj"]["annee_surv"].nunique()), min_value=1, max_value=50, key="nb_ann_gpd")

                # Preview instantané du fit GPD avec le u choisi
                excesses_preview = charges_all[charges_all >= u_choisi] - u_choisi
                n_exc_prev = len(excesses_preview)
                st.caption(f"Avec u = {u_choisi:,.0f} MAD → {n_exc_prev} excédances ({n_exc_prev/n_all:.1%} des sinistres)")
                if n_exc_prev < 5:
                    st.warning("Moins de 5 excédances — relevez u ou réduisez-le.")
                else:
                    xi_prev, _, sig_prev = _sp_gpd.genpareto.fit(excesses_preview, floc=0)
                    survie_prev = n_exc_prev / n_all
                    m_prev = retour_gpd * (n_all / nb_ann_gpd)
                    ms_prev = m_prev * survie_prev
                    if abs(xi_prev) > 1e-10:
                        Pm_prev = u_choisi + (sig_prev / xi_prev) * (ms_prev**xi_prev - 1)
                    else:
                        Pm_prev = u_choisi + sig_prev * np.log(ms_prev)
                    Pm_prev = max(Pm_prev, float(np.percentile(charges_all, 95)))
                    st.markdown(
                        f"**Aperçu GPD** : xi = {xi_prev:.4f} | sigma = {sig_prev:,.0f} MAD | "
                        f"P(X>u) = {survie_prev:.4f} | **Pm = {Pm_prev:,.0f} MAD** "
                        f"({sum(charges_all >= Pm_prev)} sinistres au-dessus)"
                    )

                if st.button("Valider ce seuil u et calculer Pm", type="primary", key="btn_valider_u"):
                    if n_exc_prev >= 5:
                        with st.spinner("Fit GPD et identification des sinistres majeurs..."):
                            res_new = identifier_sinistres_majeurs_gpd(
                                df_proj        = st.session_state["df_proj"],
                                gnpi           = gnpi,
                                tranches_input = tranches_input,
                                nb_annees_obs  = int(nb_ann_gpd),
                                retour_ans     = int(retour_gpd),
                                u              = float(u_choisi),
                            )
                        st.session_state["res_majeurs"]             = res_new
                        st.session_state["chargement_majeurs"]      = res_new["chargement"]
                        st.session_state["chargements_par_tranche"] = res_new.get("chargements_par_tranche", {})
                        st.session_state["u_gpd_retenu"]            = float(u_choisi)
                        st.rerun()
                    else:
                        st.error("Augmentez ou réduisez u pour avoir au moins 5 excédances.")

            # ════════════════════════════════════════════════
            # ÉTAPE 3 — Résultats GPD + PP/QQ plots
            # ════════════════════════════════════════════════
            if "res_majeurs" in st.session_state:
                res  = st.session_state["res_majeurs"]
                diag = res.get("gpd_diag", {})

                if diag and diag.get("u", 0) > 0:
                    with st.expander("Étape 3 — Résultats GPD et diagnostics", expanded=True):
                        c1,c2,c3,c4 = st.columns(4)
                        c1.metric("Pm (niveau de retour)", f"{res['Pm']:,.0f} MAD")
                        c2.metric("xi (forme GPD)",        f"{diag['xi']:.4f}")
                        c3.metric("sigma (échelle)",       f"{diag['sigma_gpd']:,.0f} MAD")
                        c4.metric("N excédances",          diag['n_excesses'])

                        tableau_resultats([{"Indicateur": k, "Valeur": v} for k,v in {
                            "Seuil u retenu (MAD)":  f"{diag['u']:,.0f}",
                            "xi (forme GPD)":        f"{diag['xi']:.4f}",
                            "sigma (échelle, MAD)":  f"{diag['sigma_gpd']:.2f}",
                            "P(X > u)":              f"{diag['survie_P_X_gt_u']:.6f}",
                            "Observations > u":      diag['n_excesses'],
                            "Fréquence annuelle":    f"{diag['freq_annuelle']:.4f} sin/an",
                            "m":                     f"{diag['m']:.2f}",
                            "Pm retour 20 ans":      f"{diag['Pm']:,.0f} MAD",
                            "Nb sinistres majeurs":  res["n_majeurs"],
                            "Nb sinistres courants": res["n_courants"],
                        }.items()])

                        # PP-plot et QQ-plot
                        excesses_gpd = np.array(diag.get("excesses", []))
                        if len(excesses_gpd) >= 5:
                            xi_v = float(diag["xi"]); sig_v = float(diag["sigma_gpd"])
                            pp_g = np.arange(1, len(excesses_gpd)+1) / (len(excesses_gpd)+1)
                            exc_s = np.sort(excesses_gpd)
                            fig_g, ax_g = plt.subplots(1, 2, figsize=(10, 4))
                            fig_g.patch.set_facecolor('#f5f5f5')
                            # PP
                            cdf_g = _sp_gpd.genpareto.cdf(exc_s, xi_v, loc=0, scale=sig_v)
                            ax_g[0].scatter(pp_g, cdf_g, color="#2d8a4e", s=20, alpha=0.7)
                            ax_g[0].plot([0,1],[0,1],"r--",lw=1.5)
                            ax_g[0].set_xlabel("Probabilités empiriques")
                            ax_g[0].set_ylabel("Probabilités GPD théoriques")
                            ax_g[0].set_title("PP-plot GPD"); ax_g[0].grid(alpha=0.3)
                            # QQ
                            q_g = _sp_gpd.genpareto.ppf(pp_g, xi_v, loc=0, scale=sig_v)
                            ax_g[1].scatter(q_g, exc_s, color="#2d8a4e", s=20, alpha=0.7)
                            mn_g = min(q_g.min(), exc_s.min()); mx_g = max(q_g.max(), exc_s.max())
                            ax_g[1].plot([mn_g,mx_g],[mn_g,mx_g],"r--",lw=1.5)
                            ax_g[1].set_xlabel("Quantiles GPD théoriques (MAD)")
                            ax_g[1].set_ylabel("Quantiles empiriques (MAD)")
                            ax_g[1].set_title("QQ-plot GPD"); ax_g[1].grid(alpha=0.3)
                            plt.tight_layout(); st.pyplot(fig_g); plt.close()
                            st.caption("Alignement diagonal = bon ajustement. Déviation en queue haute = sous-estimation des extrêmes → relever u.")

                    # Chargements par tranche
                    charg_par_t = res.get("chargements_par_tranche", {})
                    if charg_par_t:
                        with st.expander("Chargements par tranche (data_extremes)", expanded=True):
                            st.caption("Chargement = sum((1/T) × min(max(Xj − D, 0), C)) / GNPI | T = période de retour")
                            tableau_resultats([{
                                "Tranche":    n,  "Type": ct["type"],
                                "D (MAD)":    f"{ct['D']:,.0f}",
                                "C (MAD)":    f"{ct['C']:,.0f}",
                                "Pm (MAD)":   f"{res['Pm']:,.0f}",
                                "N majeurs":  res["n_majeurs"],
                                "Chargement": f"{ct['chargement']:.6f}",
                                "Charg. %":   f"{ct['chargement']:.4%}",
                            } for n,ct in charg_par_t.items()])

                    with st.expander("Détail sinistres majeurs (data_extremes)"):
                        df_ch = res.get("df_chargements", pd.DataFrame())
                        if len(df_ch) > 0:
                            st.dataframe(df_ch, use_container_width=True)
                        else:
                            st.info("Aucun sinistre au-dessus de Pm.")

            if "df_seuils_pareto" in st.session_state:
                with st.expander("Tableau seuils Pareto (KS)"):
                    st.dataframe(st.session_state["df_seuils_pareto"], use_container_width=True)

        # ── DÉTECTEUR D'ANOMALIES DU TRIANGLE ──────────────────────────────
        with st.expander(" Détecteur d'anomalies du triangle (avant tout calcul)", expanded=True):
            df_liq_check = st.session_state["df_liq"]
            anomalies_tri = []
            # 1. Incréments négatifs (réductions de réserves anormales)
            neg_inc = df_liq_check[df_liq_check["increment"] < 0] if "increment" in df_liq_check.columns else pd.DataFrame()
            if len(neg_inc) > 0:
                anomalies_tri.append({
                    "Type": " Incréments négatifs",
                    "N": len(neg_inc),
                    "Impact": "Réductions de réserves → mis à 0 pour la modélisation",
                    "Sévérité": "Modérée"})
            # 2. Sinistres avec un seul développement observé
            dev_counts = df_liq_check.groupby("sinistre_id")["dev"].count()
            n_single_dev = (dev_counts == 1).sum()
            if n_single_dev > len(dev_counts) * 0.30:
                anomalies_tri.append({
                    "Type": " Sinistres à 1 seul développement",
                    "N": int(n_single_dev),
                    "Impact": f"{n_single_dev/len(dev_counts):.0%} des sinistres — Triangle potentiellement incomplet",
                    "Sévérité": "Haute"})
            # 3. Années de survenance avec très peu de sinistres
            ann_counts = df_liq_check.groupby("annee_surv")["sinistre_id"].nunique()
            low_years  = ann_counts[ann_counts < 3]
            if len(low_years) > 0:
                anomalies_tri.append({
                    "Type": " Années avec < 3 sinistres",
                    "N": len(low_years),
                    "Impact": f"Années : {list(low_years.index)} → BC peu fiable ces années",
                    "Sévérité": "Haute"})
            # 4. Montants extrêmes (> 50× médiane)
            med_tot = df_liq_check["total"].median()
            extreme = df_liq_check[df_liq_check["total"] > 50 * med_tot] if med_tot > 0 else pd.DataFrame()
            if len(extreme) > 0:
                anomalies_tri.append({
                    "Type": " Montants extrêmes (> 50× médiane)",
                    "N": len(extreme),
                    "Impact": f"Max = {df_liq_check['total'].max():,.0f} MAD — Vérifier si erreur de saisie",
                    "Sévérité": "Critique"})
            # 5. Trous dans le développement (années de règlement manquantes)
            devs_obs = sorted(df_liq_check["dev"].unique())
            devs_exp = list(range(min(devs_obs), max(devs_obs)+1)) if devs_obs else []
            devs_manquants = [d for d in devs_exp if d not in devs_obs]
            if devs_manquants:
                anomalies_tri.append({
                    "Type": " Développements manquants",
                    "N": len(devs_manquants),
                    "Impact": f"Développements absents : {devs_manquants} — Facteurs CL non calculables",
                    "Sévérité": "Haute"})

            if anomalies_tri:
                tableau_resultats(anomalies_tri, "Anomalies détectées dans le triangle")
                n_crit = sum(1 for a in anomalies_tri if a["Sévérité"] == "Critique")
                if n_crit > 0:
                    st.error(f" {n_crit} anomalie(s) critique(s) — vérifiez les données avant de tarifer.")
                else:
                    st.warning(f" {len(anomalies_tri)} anomalie(s) — à analyser avant tarification.")
            else:
                st.success(" Aucune anomalie détectée dans le triangle.")

        with st.expander("Triangle — vérification stabilisation"):
            cols_show = ['sinistre_id','annee_surv','annee_reg','dev','total','I_surv','I_reg','ratio_check','Sk','S_prime_k','coeff_stab']
            st.dataframe(st.session_state["df_liq"][[c for c in cols_show if c in st.session_state["df_liq"].columns]].head(50), use_container_width=True)
        if "df_facteurs" in st.session_state:
            with st.expander("Facteurs Chain Ladder"):
                st.dataframe(st.session_state["df_facteurs"], use_container_width=True)
        if "df_proj" in st.session_state:
            with st.expander("Projections"):
                st.dataframe(st.session_state["df_proj"].head(20), use_container_width=True)

    # ═══════════════════════════════════════════════════════════════════
    # MODÈLE ACTUARIEL COMPLET — Méthode QBE Re (étapes A→I)
    # Basé sur : "Modélisation sinistres corporels — Excédent de Sinistres"
    # Auteur original : QBE Re / EGS — Adapté Atlantic Re IA
    # ═══════════════════════════════════════════════════════════════════
    if "df_proj" in st.session_state:
        st.markdown("---")
        st.markdown("""
        <div style="background:linear-gradient(135deg,#0d2b3e,#1e3a52);
            padding:18px 24px;border-bottom:3px solid #00b5a5;margin-bottom:16px">
          <div style="font-size:16px;font-weight:800;color:white;font-family:Montserrat,sans-serif">
            🎓 Modèle Actuariel Complet — Méthode QBE Re (Étapes A→I)
          </div>
          <div style="font-size:12px;color:rgba(255,255,255,0.7);margin-top:4px">
            Modélisation sinistres corporels longs · Triangle IBNR+IBNER · Cadences · Prime pure
          </div>
        </div>""", unsafe_allow_html=True)

        st.markdown("""
        <div style="background:#e8f7f4;border-left:4px solid #00b5a5;padding:12px 16px;margin-bottom:16px;font-size:13px">
        <b>Référence méthodologique :</b> "Modélisation des sinistres corporels pour la tarification d'un traité de
        Réassurance Automobile en Excédent de Sinistres" — QBE Re<br>
        <b>Séquence :</b> A. Analyse → B. Revalorisation → C. Seuils → D. IBNR+IBNER →
        E. Exposition → F. Fréquence → G. Sévérité → H. Cadences → I. Prime pure
        </div>""", unsafe_allow_html=True)

        df_proj    = st.session_state["df_proj"]
        df_liq_m   = st.session_state.get("df_liq", pd.DataFrame())

        # ── D. IBNR — Nombre de sinistres IBNR par Chain Ladder ──────────────
        with st.expander("D.1 — IBNR : Nombre de sinistres non encore déclarés (Chain Ladder sur effectifs)", expanded=False):
            st.caption("D.1 — Estimation du nombre de sinistres survenus mais non déclarés (IBNR count) par Chain Ladder sur les effectifs annuels")
            if not df_liq_m.empty and "annee_surv" in df_liq_m.columns:
                # Compter les sinistres distincts par (annee_surv, dev)
                counts = (df_liq_m.drop_duplicates(subset=["sinistre_id","dev"])
                          .groupby(["annee_surv","dev"])["sinistre_id"].count()
                          .reset_index(columns=["annee_surv","dev","nb"]) if False
                          else df_liq_m.drop_duplicates(["sinistre_id","dev"])
                               .groupby(["annee_surv","dev"]).size().reset_index(name="nb"))
                annees_s = sorted(counts["annee_surv"].unique())
                devs_s   = sorted(counts["dev"].unique())

                # Triangle des effectifs
                tri_counts = pd.DataFrame(index=annees_s, columns=devs_s, dtype=float)
                for _, row in counts.iterrows():
                    tri_counts.loc[row["annee_surv"], row["dev"]] = row["nb"]

                # Facteurs Chain Ladder sur effectifs cumulés
                tri_cum = tri_counts.cumsum(axis=1)
                facteurs_n = {}
                for k in range(len(devs_s)-1):
                    d1, d2 = devs_s[k], devs_s[k+1]
                    num = tri_cum[d2].dropna(); den = tri_cum[d1].dropna()
                    common = num.index.intersection(den.index)
                    if len(common) >= 2 and den[common].sum() > 0:
                        facteurs_n[f"{d1}→{d2}"] = float(num[common].sum() / den[common].sum())
                    else:
                        facteurs_n[f"{d1}→{d2}"] = 1.0

                st.markdown("**Facteurs de développement sur effectifs (Chain Ladder count)**")
                tableau_resultats([{"Développement": k, "Facteur": f"{v:.4f}"}
                                   for k, v in facteurs_n.items()])

                # Projection IBNR
                ibnr_rows = []
                for ann in annees_s:
                    dev_max = df_liq_m[df_liq_m["annee_surv"]==ann]["dev"].max() if not df_liq_m.empty else max(devs_s)
                    nb_obs  = df_liq_m[(df_liq_m["annee_surv"]==ann)]["sinistre_id"].nunique()
                    nb_ult  = float(nb_obs)
                    for k in devs_s:
                        if k > dev_max and f"{dev_max}→{k}" in facteurs_n:
                            nb_ult *= facteurs_n.get(f"{dev_max}→{k}", 1.0)
                            dev_max = k
                        elif k > dev_max:
                            for fk, fv in facteurs_n.items():
                                if int(fk.split("→")[0]) == dev_max:
                                    nb_ult *= fv; dev_max = int(fk.split("→")[1]); break
                    ibnr_rows.append({
                        "Année surv.": ann,
                        "N observé":   nb_obs,
                        "N ultime (proj.)": round(nb_ult, 1),
                        "IBNR count": round(max(nb_ult - nb_obs, 0), 1),
                    })

                if ibnr_rows:
                    tableau_resultats(ibnr_rows, "Estimation IBNR (effectifs)")
                    total_ibnr = sum(r["IBNR count"] for r in ibnr_rows)
                    st.metric("Total IBNR (sinistres non déclarés estimés)", f"{total_ibnr:.1f}")
                    st.session_state["ibnr_count_total"] = total_ibnr
                    st.caption(
                        "Ces sinistres IBNR seront échantillonnés depuis la distribution de sévérité "
                        "observée lors du calcul de la prime pure (étape I)."
                    )

        # ── D.2 IBNER — Développement par sinistre ───────────────────────────
        with st.expander("D.2 — IBNER : Développement des montants par sinistre (Chain Ladder sur montants)", expanded=False):
            st.caption("D.2 — Sinistres IBNER : survenus mais sous-réservés. Chain Ladder sur les montants cumulés par sinistre.")
            df_p = df_proj.copy()

            # Facteurs Chain Ladder sur montants : déjà calculés via df_facteurs (f_moyens)
            f_moyens = st.session_state.get("f_moyens", {})
            if f_moyens:
                st.markdown("**Facteurs IBNER (identiques aux facteurs CL du triangle des montants)**")
                tableau_resultats([{
                    "Développement": f"{k}→{k+1}",
                    "Facteur IBNER": f"{v:.4f}",
                    "Interprétation": (
                        "Sous-réservage" if v > 1.05 else
                        "Sur-réservage"  if v < 0.95 else
                        "Estimation correcte"
                    )
                } for k, v in f_moyens.items()])

            # Sinistres en situation ultime
            if not df_p.empty and "dev_max" in df_p.columns:
                dist_devmax = df_p.groupby("dev_max")["sinistre_id"].count().reset_index()
                dist_devmax.columns = ["Dev max observé", "Nb sinistres"]
                st.markdown("**Distribution des sinistres par développement maximum observé**")
                tableau_resultats(dist_devmax.to_dict("records"))

                avg_ibner = df_p["Sprime_ultime"].mean() if "Sprime_ultime" in df_p.columns else 0
                avg_sk    = df_p["Sk_ultime"].mean()     if "Sk_ultime"    in df_p.columns else 0
                ratio_ibner = avg_ibner / avg_sk if avg_sk > 0 else 1.0
                st.info(
                    f"Ratio IBNER moyen : Sprime_ultime / Sk_ultime = {ratio_ibner:.4f}  "
                    f"({'Sous-réservage moyen' if ratio_ibner > 1.02 else 'Sur-réservage moyen' if ratio_ibner < 0.98 else 'Estimation correcte'})"
                )
                st.caption(
                    "Méthode QBE Re : chaque sinistre est projeté individuellement à l'ultime (sinistre par sinistre). "
                    "Le ratio IBNER quantifie la tendance systématique de la cédante à sous/sur-estimer ses réserves."
                )

        # ── E. Exposition ─────────────────────────────────────────────────────
        with st.expander("E — Exposition au risque : Nombre de véhicules-années", expanded=False):
            st.caption("E — La meilleure mesure d'exposition est le nombre de véhicules-années, corrigé vers l'année de cotation.")
            st.markdown("""
            <div style="background:#f2f8f7;border-left:3px solid #00b5a5;padding:12px 16px;font-size:12px">
            <b>Méthode QBE Re :</b> Le GNPI est utilisé comme proxy de l'exposition ici (corrigé par l'inflation tarifaire).
            Si le nombre de véhicules-années est disponible, il est préféré.
            Correction = GNPI_ann / GNPI_cotation × N_véhicules_cotation.
            </div>""", unsafe_allow_html=True)
            col_e1, col_e2 = st.columns(2)
            with col_e1:
                gnpi_annot = st.number_input("GNPI année de cotation (MAD)", value=float(gnpi),
                    step=1_000_000.0, key="gnpi_expo_annot")
            with col_e2:
                nb_vehicules = st.number_input("Nb véhicules-années (si connu)", value=0, step=1000, key="nb_veh")

            if not df_liq_m.empty and "annee_surv" in df_liq_m.columns and "I_reg" in df_liq_m.columns:
                annees_expo = sorted(df_liq_m["annee_surv"].unique())
                # Reconstruction de l'exposition relative via GNPI indexé
                df_gnpis_df = st.session_state.get("df_gnpis_df", pd.DataFrame())
                rows_expo = []
                for ann in annees_expo:
                    try:
                        gnpi_col = df_gnpis_df.columns[1] if not df_gnpis_df.empty else None
                        gnpi_ann = float(df_gnpis_df.set_index(df_gnpis_df.columns[0]).loc[ann, gnpi_col]) if gnpi_col else gnpi_annot
                    except: gnpi_ann = gnpi_annot
                    I_ann = df_liq_m[df_liq_m["annee_surv"]==ann]["I_surv"].mean() if "I_surv" in df_liq_m.columns else 1.0
                    I_cot = st.session_state.get("I_cotation", 1.0)
                    expo_corrigee = gnpi_ann * (I_cot / max(I_ann, 1e-6))
                    rows_expo.append({
                        "Année": ann,
                        "GNPI observé (MAD)": f"{gnpi_ann:,.0f}",
                        "GNPI corrigé cotation": f"{expo_corrigee:,.0f}",
                        "Ratio exposition": f"{expo_corrigee/gnpi_annot:.4f}",
                    })
                if rows_expo:
                    tableau_resultats(rows_expo, "Exposition annuelle corrigée vers l'année de cotation")
                    st.session_state["expo_rows"] = rows_expo

        # ── F. Modélisation fréquence ─────────────────────────────────────────
        with st.expander("F — Fréquence : Loi de Poisson par année de développement", expanded=False):
            st.caption("F — Estimation du lambda Poisson par année, tenant compte de l'exposition. Une loi de Poisson par année de développement.")
            df_p = df_proj.copy()
            if not df_p.empty and "annee_surv" in df_p.columns:
                Amin = float(st.session_state.get("seuil_est", 0)) * 0.5   # seuil 50% priorité = seuil données
                lambda_est = float(st.session_state.get("lambda_est", 5.0))

                annees_f = sorted(df_p["annee_surv"].unique())
                rows_freq = []
                for ann in annees_f:
                    nb = df_p[df_p["annee_surv"]==ann]["sinistre_id"].nunique()
                    rows_freq.append({
                        "Année surv.": ann,
                        "N sinistres > Amin": nb,
                        "λ Poisson estimé": f"{nb:.3f}",
                    })
                tableau_resultats(rows_freq)
                lambdas = [r["N sinistres > Amin"] for r in rows_freq]
                lambda_moyen = float(np.mean(lambdas)) if lambdas else lambda_est
                st.metric("λ moyen (fréquence annuelle sinistres > Amin)", f"{lambda_moyen:.4f}")
                st.caption(
                    f"λ = {lambda_moyen:.4f} sinistres/an au-dessus du seuil Amin ≈ {Amin:,.0f} MAD. "
                    "Une loi de Poisson(λ) est ajustée pour chaque année de développement. "
                    "Méthode QBE Re : Σ_k P(N_k=n) × cadence(k) permet la décomposition temporelle."
                )

                import matplotlib.pyplot as plt
                fig_f, ax_f = plt.subplots(figsize=(8, 3))
                ax_f.bar(annees_f, lambdas, color="#00b5a5", alpha=0.8, edgecolor="#0d2b3e")
                ax_f.axhline(lambda_moyen, color="#ff6b35", ls="--", lw=2, label=f"λ moyen = {lambda_moyen:.2f}")
                ax_f.set_xlabel("Année de survenance")
                ax_f.set_ylabel("N sinistres > Amin")
                ax_f.set_title("Fréquence annuelle — distribution Poisson")
                ax_f.legend(); ax_f.grid(alpha=0.2)
                st.pyplot(fig_f); plt.close()

        # ── G. Modélisation sévérité ──────────────────────────────────────────
        with st.expander("G — Sévérité : Distribution Pareto / Empirique / Marché", expanded=False):
            st.caption("G — Ajustement de la distribution de sévérité sur les sinistres en situation ultime (après IBNER).")
            df_p = df_proj.copy()
            if "Sprime_ultime" in df_p.columns:
                seuil_mod = float(st.session_state.get("seuil_est", 0))
                alpha_est = float(st.session_state.get("alpha_est", 1.5))
                X_all     = df_p["Sprime_ultime"].values; X_all = X_all[X_all > 0]

                st.markdown("**G.1 — Distribution empirique vs Pareto**")
                import matplotlib.pyplot as plt
                from scipy import stats as _sp

                X_above = X_all[X_all >= seuil_mod]
                n_above = len(X_above)

                # Pareto MLE
                alpha_hat = n_above / np.sum(np.log(X_above / seuil_mod))
                x_range   = np.linspace(seuil_mod, np.percentile(X_all, 98), 200)
                cdf_emp   = np.array([np.mean(X_above <= x) for x in x_range])
                cdf_par   = 1 - (seuil_mod / x_range) ** alpha_hat

                fig_g, (ax_g1, ax_g2) = plt.subplots(1, 2, figsize=(12, 4))
                # CDF
                ax_g1.plot(x_range, cdf_emp, "k-", lw=2, label="Empirique")
                ax_g1.plot(x_range, cdf_par, "--", color="#00b5a5", lw=2,
                           label=f"Pareto(α={alpha_hat:.3f})")
                ax_g1.set_xlabel("Montant sinistre (MAD)"); ax_g1.set_ylabel("F(x)")
                ax_g1.set_title("CDF Sévérité au-dessus du seuil")
                ax_g1.legend(); ax_g1.grid(alpha=0.2)
                # QQ-Plot
                log_x = np.log(np.sort(X_above)/seuil_mod); n_q = len(log_x)
                th_q  = -np.log(1 - np.arange(1,n_q+1)/(n_q+1))
                ax_g2.scatter(th_q, log_x, color="#0d2b3e", s=15, alpha=0.6)
                mn_q = min(th_q.min(), log_x.min()); mx_q = max(th_q.max(), log_x.max())
                ax_g2.plot([mn_q,mx_q],[mn_q,mx_q],"--", color="#ff6b35", lw=1.5)
                ax_g2.set_xlabel("Quantiles Exp(1)"); ax_g2.set_ylabel("log(X/seuil)")
                ax_g2.set_title("QQ-Plot Pareto"); ax_g2.grid(alpha=0.2)
                st.pyplot(fig_g); plt.close()

                # Formule analytique E[f(X)] pour Pareto
                st.markdown("**G.2 — Calcul analytique E[f(X)] = E[min(C, max(0, X-P))] par Pareto**")
                st.latex(r"""
E[f(X)] = \left(\frac{x_m}{P}\right)^\alpha \cdot \frac{P}{\alpha-1}
\cdot \left[1 - \left(\frac{P}{P+C}\right)^{\alpha-1}\right]
- C \cdot \left(\frac{x_m}{P+C}\right)^\alpha
""")
                st.caption("Formule exacte pour X ~ Pareto(α, x_m) — Daykin-Pentikäinen-Pesonen (1994), Section 5.3")

                for t in tranches_input:
                    D = t["priorite"]; C = t["portee"]
                    if alpha_hat > 1:
                        p_above_D = (seuil_mod / D) ** alpha_hat if D > seuil_mod else 1.0
                        p_above_DC= (seuil_mod / (D+C)) ** alpha_hat
                        e_fx = (p_above_D * D / (alpha_hat-1) *
                                (1 - (D/(D+C))**(alpha_hat-1)) - C * p_above_DC)
                        e_fx = max(e_fx, 0)
                    else:
                        e_fx = 0.0
                    lambda_m = float(st.session_state.get("lambda_est", 5.0))
                    prime_pure_pareto = lambda_m * e_fx
                    tableau_resultats([{
                        "Tranche": t["nom"],
                        "D (priorité)": f"{D:,.0f}",
                        "C (portée)": f"{C:,.0f}",
                        "P(X>D)": f"{(seuil_mod/D)**alpha_hat:.4%}" if D>seuil_mod else "100%",
                        "E[f(X)] Pareto": f"{e_fx:,.0f} MAD",
                        "Prime pure (λ×E[f])": f"{prime_pure_pareto:,.0f} MAD",
                        "Taux Pareto": f"{prime_pure_pareto/gnpi:.4%}",
                    }])
                st.session_state["alpha_pareto_g"] = alpha_hat

        # ── H. Cadences de règlement ──────────────────────────────────────────
        with st.expander("H — Cadences de règlement et de réservation", expanded=False):
            st.caption("H — Estimation de la cadence de règlement (proportion payée par développement k) et de réservation (tendance sous/sur-estimation).")
            st.markdown("""
            <div style="background:#f2f8f7;border-left:3px solid #00b5a5;padding:12px 16px;font-size:12px">
            <b>Méthode QBE Re :</b><br>
            • <b>Cadence règlement</b> = Triangle des paiements non développés / Sinistres en situation ultime<br>
            • <b>Cadence réservation</b> = Déduite des coefficients IBNER (tendance sous-estimation)<br>
            • Ces cadences sont appliquées à l'étape I pour pondérer les sinistres par probabilité de paiement.
            </div>""", unsafe_allow_html=True)

            df_liq_h = st.session_state.get("df_liq", pd.DataFrame())
            df_proj_h = df_proj.copy()

            if not df_liq_h.empty and "dev" in df_liq_h.columns and not df_proj_h.empty:
                # Construire la cadence : par développement k, proportion des sinistres payés
                devs_h = sorted(df_liq_h["dev"].unique())
                rows_cadence = []
                total_ult_mad = df_proj_h["Sprime_ultime"].sum() if "Sprime_ultime" in df_proj_h.columns else 1.0

                cumul_paye = 0.0
                for dev in devs_h:
                    # Paiements du développement k (incréments)
                    if "inc_asif" in df_liq_h.columns:
                        paye_k = df_liq_h[df_liq_h["dev"]==dev]["inc_asif"].sum()
                    elif "increment" in df_liq_h.columns:
                        paye_k = df_liq_h[df_liq_h["dev"]==dev]["increment"].sum()
                    else:
                        paye_k = 0.0
                    cumul_paye += paye_k
                    cadence_k = cumul_paye / max(total_ult_mad, 1.0)
                    rows_cadence.append({
                        "Développement k": dev,
                        "Paiements As-If (MAD)": f"{paye_k:,.0f}",
                        "Cumul paiements": f"{cumul_paye:,.0f}",
                        "Cadence (% ultime)": f"{cadence_k:.2%}",
                        "En attente": f"{1-cadence_k:.2%}",
                    })
                cadence_list = [r["Cadence (% ultime)"] for r in rows_cadence]
                tableau_resultats(rows_cadence, "Cadences de règlement par développement")
                st.session_state["cadence_rows"] = rows_cadence

                import matplotlib.pyplot as plt
                fig_h, ax_h = plt.subplots(figsize=(8, 3))
                dev_vals = [r["Développement k"] for r in rows_cadence]
                cad_vals = [float(r["Cadence (% ultime)"].replace("%",""))/100 for r in rows_cadence]
                ax_h.plot(dev_vals, cad_vals, "o-", color="#00b5a5", lw=2, ms=8)
                ax_h.fill_between(dev_vals, cad_vals, alpha=0.15, color="#00b5a5")
                ax_h.set_xlabel("Développement"); ax_h.set_ylabel("Proportion cumulée payée")
                ax_h.set_title("Cadence de règlement cumulée (% du montant ultime)")
                ax_h.yaxis.set_major_formatter(plt.FuncFormatter(lambda y,_: f"{y:.0%}"))
                ax_h.grid(alpha=0.2)
                st.pyplot(fig_h); plt.close()

                st.markdown("**Cadence de réservation (coefficients IBNER)**")
                f_moyens_h = st.session_state.get("f_moyens", {})
                if f_moyens_h:
                    reserv_rows = []
                    for k, fv in f_moyens_h.items():
                        reserv_rows.append({
                            "Dev": f"{k}→{k+1}",
                            "Facteur IBNER": f"{fv:.4f}",
                            "Sous-réservage": f"{(fv-1)*100:+.1f}%",
                            "Diagnostic": "Sous-réservage" if fv > 1.02 else
                                          "Sur-réservage"  if fv < 0.98 else
                                          "Estimation correcte"
                        })
                    tableau_resultats(reserv_rows)

        # ── I. Prime pure complète ────────────────────────────────────────────
        with st.expander("I — Prime pure (sinistralité annuelle attendue) — Formule QBE Re", expanded=True):
            st.caption("I — Application du programme de réassurance sur chaque sinistre, pondéré par la cadence de règlement.")
            st.markdown("""
            <div style="background:#f2f8f7;border-left:3px solid #00b5a5;padding:12px 16px;font-size:12px">
            <b>Formule QBE Re :</b><br>
            <code>SR(k) = Exposition × Σ_i [cadence(k,i) × min(C, max(0, X_i_ultime − P))]</code><br>
            <code>Prime pure = SR(k→ultime) / GNPI</code><br>
            <b>Inclut :</b> sinistres observés + IBNR estimés (échantillonnés depuis la distribution sévérité)
            </div>""", unsafe_allow_html=True)

            df_proj_i = df_proj.copy()
            if "Sprime_ultime" in df_proj_i.columns and tranches_input:
                ibnr_n = float(st.session_state.get("ibnr_count_total", 0))
                alpha_i = float(st.session_state.get("alpha_pareto_g",
                                st.session_state.get("alpha_est", 1.5)))
                seuil_i = float(st.session_state.get("seuil_est", 1_600_000))

                # Ajouter les sinistres IBNR simulés
                if ibnr_n > 0 and alpha_i > 1:
                    np.random.seed(42)
                    n_ibnr_int = int(round(ibnr_n))
                    u_ibnr = np.random.uniform(size=n_ibnr_int)
                    x_ibnr = seuil_i * (u_ibnr ** (-1.0/alpha_i))  # Pareto
                    # Année de survenance : extrapolation linéaire
                    ann_max = df_proj_i["annee_surv"].max()
                    df_ibnr = pd.DataFrame({
                        "sinistre_id":    [f"IBNR_{j}" for j in range(n_ibnr_int)],
                        "annee_surv":     [ann_max + 1] * n_ibnr_int,
                        "dev_max":        [0] * n_ibnr_int,
                        "Sprime_ultime":  x_ibnr,
                        "Sk_ultime":      x_ibnr,
                        "coeff_stab":     [1.0] * n_ibnr_int,
                    })
                    df_complet = pd.concat([df_proj_i, df_ibnr], ignore_index=True)
                    st.info(f"Ajout de {n_ibnr_int} sinistres IBNR simulés (Pareto α={alpha_i:.3f})")
                else:
                    df_complet = df_proj_i.copy()

                # Calcul par tranche
                rows_prime_pure = []
                for t in tranches_input:
                    D = t["priorite"]; C = t["portee"]
                    n_rec = t["nb_reconstitutions"]
                    aal = t.get("AAL"); aad = t.get("AAD")
                    cap = (n_rec + 1) * C

                    # Sinistralité par sinistre
                    def f_xl(x):
                        return min(max(x - D, 0), C) * t.get("coeff_stab", 1.0)
                    df_complet["f_xi"] = df_complet["Sprime_ultime"].apply(
                        lambda x: min(max(x - D, 0), C))

                    # Agrégation annuelle
                    charges_ann = df_complet.groupby("annee_surv")["f_xi"].sum()
                    charges_finales = []
                    for ann, ch in charges_ann.items():
                        if aad: ch = max(ch - aad, 0)
                        if aal: ch = min(ch, aal)
                        charges_finales.append(min(ch, cap))

                    n_ann = len(charges_finales)
                    if n_ann == 0:
                        rows_prime_pure.append({"Tranche":t["nom"],"τ pure QBE":"—","Prime (MAD)":"—"})
                        continue
                    charge_moy = np.mean(charges_finales)
                    sigma       = np.std([c for c in charges_finales if c > 0]) if any(c>0 for c in charges_finales) else 0.0
                    tau_pur     = charge_moy / gnpi
                    tau_risque  = tau_pur + 0.20 * (sigma / gnpi)  # R1
                    denom       = max(1 - t["brokage"] - t["frais"] - t["marge"] - t.get("retrocession",0), 0.01)
                    tau_tech    = tau_risque / denom
                    prime       = gnpi * tau_tech

                    rows_prime_pure.append({
                        "Tranche":          t["nom"],
                        "Type":             t["type"],
                        "N sinistres (obs+IBNR)": len(df_complet),
                        "Charge annuelle moy.":  f"{charge_moy:,.0f}",
                        "σ annuelle":            f"{sigma:,.0f}",
                        "τ pur QBE":             f"{tau_pur:.4%}",
                        "τ risque (R1)":         f"{tau_risque:.4%}",
                        "τ technique":           f"{tau_tech:.4%}",
                        "Prime pure (MAD)":      f"{prime:,.0f}",
                    })

                tableau_resultats(rows_prime_pure, "Prime pure — Méthode QBE Re complète (IBNR inclus)")

                prime_totale_qbe = sum(
                    gnpi * float(r["τ technique"].replace("%",""))/100
                    for r in rows_prime_pure
                    if r.get("τ technique","—") != "—"
                )
                col_q1, col_q2, col_q3 = st.columns(3)
                with col_q1: card("Prime totale QBE", f"{prime_totale_qbe:,.0f} MAD", icone="🎓")
                with col_q2: card("Taux global QBE",  f"{prime_totale_qbe/gnpi:.4%}", couleur="#0d2b3e", icone="")
                with col_q3: card("Sinistres IBNR", f"{int(round(ibnr_n))}", couleur="#00b5a5", icone="")

                st.markdown("""
                <div style="background:#e8f7f4;border-left:4px solid #00b5a5;padding:12px 16px;font-size:12px;margin-top:12px">
                <b>Pour obtenir la prime de réassurance finale (chargée) :</b><br>
                τ_final = τ_technique + GSM (Grands Sinistres Matériels) + Frais fixes gestion + Courtage + Rémunération capital<br>
                <i>Source : QBE Re — Conclusion de la présentation</i>
                </div>""", unsafe_allow_html=True)

                st.caption("""
                **Références bibliographiques :**
                Daykin, Pentikäinen & Pesonen (1994) — *Practical Risk Theory for Actuaries*
                | Finger (2006) — *Property-Casualty Insurance Pricing* (CAS)
                | Pickands (1975), Balkema & de Haan (1974) — *GPD pour les excédances*
                | QBE Re EGS — *Modélisation sinistres corporels RC Auto*
                """)

# ════════════════════════════════════════════
# TAB 3 — BURNING COST
# ════════════════════════════════════════════

with tab3:
    section_header("Burning Cost", "Charges historiques réassurance par tranche", "")
    st.caption("Ck = min(max(S’k_ultime − D, 0), L) × coeff_stab")
    st.markdown("""<div style="background:rgba(45,138,78,0.08);border-left:4px solid #2d8a4e;
        border-radius:0 8px 8px 0;padding:10px 16px;margin-bottom:12px;font-size:12px">
        <b>R1</b> — τ_risque = τ_pur + σ_hist × 20% (écart-type BC annuels non nuls × chargement sécurité) —
        <b>R2</b> — Si années non nulles < 3 → τ_BC = 0 (données insuffisantes)
        </div>""", unsafe_allow_html=True)

    if "df_proj" not in st.session_state:
        st.warning(" Transformez d'abord le triangle")
    else:
        # ── DÉTECTEUR ANNÉES ATYPIQUES ─────────────────────────────────────
        with st.expander("🔍 Analyse préalable — Détection des années atypiques (obligatoire)", expanded=True):
            st.caption("AVANT le calcul BC: identifier les années atypiques. Causes [A]=Isolement [B]=Nature CAT [C]=GNPI faible [D]=Sinistre unique [E]=Périmètre")
            df_proj_bc = st.session_state["df_proj"].copy()
            t_ref = next((t for t in tranches_input if t["type"]=="travaillante"), tranches_input[0] if tranches_input else None)
            if t_ref:
                D_ref = t_ref["priorite"]; L_ref = t_ref["portee"]
                df_proj_bc["Ck_ref"] = df_proj_bc.apply(
                    lambda r: min(max(r["Sprime_ultime"] - D_ref, 0), L_ref) * r["coeff_stab"], axis=1)
                ch_ann = df_proj_bc.groupby("annee_surv")["Ck_ref"].sum().reset_index()
                ch_ann.columns = ["Annee","Charge_XL"]
                gnpi_bc = {}
                df_gref = st.session_state.get("df_gnpis_df", pd.DataFrame())
                if not df_gref.empty:
                    try:
                        gi = df_gref.set_index(df_gref.columns[0]); gc = df_gref.columns[1]
                        for ann2 in ch_ann["Annee"]:
                            try: gnpi_bc[int(ann2)] = float(gi.loc[ann2, gc])
                            except: gnpi_bc[int(ann2)] = gnpi
                    except: pass
                ch_ann["GNPI"] = ch_ann["Annee"].apply(lambda a: gnpi_bc.get(int(a), gnpi))
                ch_ann["TxBC"] = ch_ann["Charge_XL"] / ch_ann["GNPI"].clip(lower=1)
                med_t = ch_ann["TxBC"].median(); med_g = ch_ann["GNPI"].median()
                anom = {}
                ta = ch_ann["TxBC"].values; ga = ch_ann["GNPI"].values; aa = ch_ann["Annee"].values
                for i2, (an2, tau2, gnpi2) in enumerate(zip(aa, ta, ga)):
                    c2 = []
                    vois = [ta[j] for j in [i2-1, i2+1] if 0 <= j < len(ta)]
                    if vois and tau2 > 0 and med_t > 0:
                        rv = tau2 / max(float(np.mean(vois)), 1e-10)
                        if rv > 3.0 and tau2 > med_t * 2: c2.append(f"[A] Isolement: {tau2:.2%} >> voisines ({np.mean(vois):.2%}) ratio={rv:.1f}x")
                    if gnpi2 < med_g * 0.5 and med_g > 0: c2.append(f"[C] GNPI faible: {gnpi2:,.0f} vs médiane {med_g:,.0f}")
                    if c2: anom[int(an2)] = c2
                rows_at = [{"Année":int(r["Annee"]),"Charge XL":f"{r['Charge_XL']:,.0f}","GNPI":f"{r['GNPI']:,.0f}",
                    "τ BC":f"{r['TxBC']:.4%}","vs Médiane":f"{r['TxBC']/med_t:.1f}×" if med_t>0 else "—",
                    "Anomalie":" | ".join(anom.get(int(r["Annee"]),[])) or " Normale"}
                    for _,r in ch_ann.iterrows()]
                tableau_resultats(rows_at, f"Analyse années atypiques — {t_ref['nom']}")
                if anom: st.warning(f" Années atypiques détectées : {sorted(anom.keys())}")
                col_e1, col_e2 = st.columns([3,1])
                with col_e1:
                    exc_ann = st.multiselect("Années à exclure du BC",
                        options=sorted([int(a) for a in aa]), default=sorted(anom.keys()),
                        key="bc_annees_exclues", help="[A]=Isolement [B]=Nature CAT [C]=GNPI faible [D]=Sinistre unique [E]=Périmètre")
                with col_e2:
                    cause_exc = st.selectbox("Cause",["[A] Isolement","[B] Nature CAT","[C] GNPI faible","[D] Sinistre unique","[E] Périmètre","Autre"],key="bc_cause_excl")
                if exc_ann:
                    t_av = ch_ann["TxBC"].mean(); t_ss = ch_ann[~ch_ann["Annee"].isin(exc_ann)]["TxBC"].mean()
                    c1e,c2e,c3e = st.columns(3)
                    with c1e: card("τ BC avec atypiques",f"{t_av:.4%}",couleur="#e74c3c",icone="")
                    with c2e: card("τ BC sans atypiques",f"{t_ss:.4%}",couleur="#00b5a5",icone="")
                    with c3e: card("Écart",f"{abs(t_av-t_ss)*100:.4f} pts",couleur="#0d2b3e",icone="")
                    st.session_state["bc_annees_exclues_set"] = set(exc_ann)
                    st.caption(f"Cause documentée : {cause_exc}")
                else: st.session_state["bc_annees_exclues_set"] = set()
        if st.button(" Calculer le Burning Cost", type="primary"):
            with st.spinner("Calcul en cours..."):
                df_proj = st.session_state["df_proj"]
                resultats_bc = []
                for t_info in tranches_input:
                    D = t_info["priorite"]; L = t_info["portee"]
                    aal = t_info["AAL"]; aad = t_info["AAD"]
                    n_rec = t_info["nb_reconstitutions"]; t_r = t_info["taux_reconstitution"] / 100
                    cap = (n_rec + 1) * L
                    df_proj["Ck"] = df_proj.apply(
                        lambda row: min(max(row["Sprime_ultime"] - D, 0), L) * row["coeff_stab"], axis=1)
                    charges_ann = df_proj.groupby("annee_surv")["Ck"].sum()
                    charges_finales = []
                    for ann, ch in charges_ann.items():
                        if aad: ch = max(ch - aad, 0)
                        if aal: ch = min(ch, aal)
                        ch = min(ch, cap)
                        charges_finales.append({"annee": ann, "charge": ch})
                    df_ch = pd.DataFrame(charges_finales); N = len(df_ch)
                    # Reconstitutions avec taux individuels par reconstitution
                    taux_rec_list = t_info.get("taux_reconstitutions", [t_info.get("taux_reconstitution", 100)] * n_rec)
                    Pr_Rec = 0.0
                    for C_n in df_ch["charge"].values:
                        for r_idx, t_r_i in enumerate(taux_rec_list):
                            Pr_Rec += (t_r_i / 100) * min(L, max(C_n - r_idx * L, 0))
                    Pr_Rec /= L if L > 0 else 1
                    Rec = Pr_Rec / (Pr_Rec + N) if (Pr_Rec + N) > 0 else 0.0
                    charge_moy  = df_ch["charge"].mean()
                    charges_nonzero = [c for c in df_ch["charge"].values if c > 0]
                    n_ann_nonzero   = len(charges_nonzero)
                    charg_maj = st.session_state.get(
                        "chargements_par_tranche", {}).get(
                        t_info["nom"], {}).get(
                        "chargement",
                        st.session_state.get("chargement_majeurs", 0.0))
                    # R2 — Moins de 3 années non nulles → BC = 0 (données insuffisantes)
                    if n_ann_nonzero < 3:
                        taux_pur = taux_risque = taux_technique = 0.0
                        sigma_hist = 0.0
                    else:
                        taux_pur   = charge_moy / gnpi
                        sigma_hist = float(np.std(charges_nonzero)) / gnpi
                        # R1 — τ_risque = τ_pur + σ_hist × 20% (chargement sécurité)
                        taux_risque    = taux_pur + sigma_hist * 0.20
                        taux_technique = (taux_risque * (1 - Rec)) / (
                            1 - t_info["brokage"] - t_info["frais"] - t_info["marge"] - t_info["retrocession"])
                    resultats_bc.append({
                        "tranche": t_info["nom"], "type": t_info["type"],
                        "charge_moy": charge_moy, "Pr_Rec": Pr_Rec, "Rec": Rec,
                        "n_ann_nonzero": n_ann_nonzero, "sigma_hist": sigma_hist if n_ann_nonzero >= 3 else 0.0,
                        "taux_pur": taux_pur, "taux_risque": taux_risque,
                        "taux_technique": taux_technique,
                        "chargement_majeurs": charg_maj,
                        "detail_annuel": df_ch.to_dict("records")
                    })
                st.session_state["resultats_bc"] = resultats_bc
                # ── Auto-save ──
                try:
                    db_save_session(st.session_state.get("user_email",""), gnpi, tranches_input)
                    db_save_etape("bc", [{k:v for k,v in r.items() if k!="detail_annuel"} for r in resultats_bc])
                    st.toast(" BC sauvegardé")
                except Exception as _e:
                    st.toast(f" Sauvegarde DB : {_e}")

    if "resultats_bc" in st.session_state:
        tableau_resultats([{
            "Tranche": r["tranche"], "Type": r["type"],
            "Ans non-nuls": f"{r.get('n_ann_nonzero',0)} {'' if r.get('n_ann_nonzero',0)<3 else ''}",
            "Charge moy.": f"{r.get('charge_moy', r.get('charge_moy_MAD', 0)):,.0f} MAD",
            "σ hist.": f"{r.get('sigma_hist',0):.4%}",
            "Rec": f"{r['Rec']:.4%}",
            "Taux pur": f"{r['taux_pur']:.4%}", "Taux risque": f"{r['taux_risque']:.4%}",
            "Taux technique": f"{r['taux_technique']:.4%}",
            "Charg. majeurs": f"{r.get('chargement_majeurs', 0):.4%}",
        } for r in st.session_state["resultats_bc"]], titre=" Résultats Burning Cost")

        # ── Triangle individuel + traçabilité ──
        with st.expander(" Triangle individuel — 1 ligne = 1 sinistre", expanded=False):
            if "df_liq" in st.session_state:
                df_liq_bc = st.session_state["df_liq"].copy()
                st.markdown("""<div style="background:#f0fff4;border-left:4px solid #2d8a4e;
                    border-radius:0 8px 8px 0;padding:10px 14px;margin-bottom:12px;font-size:12px">
                    <b>Logique :</b> 1️⃣ Chaque sinistre est projeté individuellement à l'ultime →
                    2️⃣ Charge XL individuelle : <code>Ck = min(max(S'ultime − D, 0), L)</code> →
                    3️⃣ Agrégation par UW Year = BC annuel
                    </div>""", unsafe_allow_html=True)

                etape_view = st.radio(
                    "Montants à afficher :",
                    ["1 Bruts Excel (TOTAL=PAID+OS)",
                     "2 As-If Sk",
                     "3 Stabilises Sprimek"],
                    key="tri_etape_view", horizontal=True)

                col_val = "total" if etape_view.startswith("1") else ("Sk" if etape_view.startswith("2") else "S_prime_k")

                # Triangle individuel : 1 ligne = 1 sinistre, colonnes = années règlement
                pivot_ind = df_liq_bc.pivot_table(
                    index=["annee_surv", "sinistre_id"],
                    columns="annee_reg",
                    values=col_val,
                    aggfunc="last"
                )
                pivot_ind.index.names = ["UW Year", "ID Sinistre"]
                pivot_ind.columns = [str(int(c)) for c in pivot_ind.columns]
                fmt_fn = getattr(pivot_ind, "map", getattr(pivot_ind, "applymap", None))
                st.markdown(f"**{len(pivot_ind)} sinistres × {len(pivot_ind.columns)} années de règlement**")
                st.dataframe(fmt_fn(lambda x: f"{x:,.0f}" if pd.notna(x) else "—"),
                             use_container_width=True, height=400)

                if etape_view.startswith("1"):
                    st.markdown("**Lignes brutes (30 premières) — comparez avec votre Excel :**")
                    df_chk = df_liq_bc[["sinistre_id","annee_surv","annee_reg","dev","total"]].head(30).copy()
                    df_chk["total"] = df_chk["total"].apply(lambda x: f"{x:,.0f}")
                    df_chk.columns = ["ID Sinistre","UW Year","Année règlement","Dev","TOTAL brut"]
                    st.dataframe(df_chk, use_container_width=True)

            if "df_proj" in st.session_state:
                st.divider()
                st.markdown("**S'prime_ultime individuel — projection de chaque sinistre à l'ultime :**")
                df_proj_show = st.session_state["df_proj"][
                    ["sinistre_id","annee_surv","dev_max","Sprime_ultime","coeff_stab"]].copy()
                df_proj_show["Sprime_ultime"] = df_proj_show["Sprime_ultime"].apply(lambda x: f"{x:,.0f}")
                df_proj_show["coeff_stab"]    = df_proj_show["coeff_stab"].apply(lambda x: f"{x:.4f}")
                df_proj_show.columns = ["ID Sinistre","UW Year","Dev max","S'prime ultime","Coeff stab."]
                st.dataframe(df_proj_show, use_container_width=True, height=300)
                st.caption(f"{len(df_proj_show)} sinistres individuels projetés")

            st.divider()
            st.markdown("**BC agrégé par UW Year (somme des Ck individuels) :**")
            for r in st.session_state["resultats_bc"]:
                detail = r.get("detail_annuel", [])
                if detail:
                    df_det = pd.DataFrame(detail)
                    df_det["charge"] = df_det["charge"].apply(lambda x: f"{x:,.0f}")
                    df_det.columns   = ["UW Year","Charge XL nette (MAD)"]
                    with st.expander(f"  {r['tranche']} | {r['type']} | tau_pur={r['taux_pur']:.4%}", expanded=False):
                        st.dataframe(df_det, use_container_width=True)




        # ── CRÉDIBILITÉ BÜHLMANN-STRAUB ──────────────────────────────────────
        with st.expander("Crédibilité Bühlmann-Straub", expanded=False):
            st.markdown("""<div style="background:#f2f8f7;border-left:4px solid #00b5a5;padding:12px 16px;font-size:12px">
            <b>Bühlmann-Straub (1967) :</b> τ_crédible = Z × τ_BC + (1-Z) × μ_a_priori | Z = n / (n + k) | k = σ²_intra / σ²_inter
            </div>""", unsafe_allow_html=True)
            a_priori_bs = st.number_input("μ a priori global (% GNPI)", value=3.0, step=0.1, min_value=0.0,
                key="bs_apriori", help="Taux de marché ou expérience groupe") / 100
            cred_res = buehlmann_straub_credibility(st.session_state["resultats_bc"], a_priori_pct=a_priori_bs, gnpi_val=gnpi)
            tableau_resultats([{"Tranche":n,"Z":f"{r['Z']:.3f}","τ BC":f"{r.get('tau_bc',0):.4%}",
                "μ a priori":f"{r.get('mu_a_priori',a_priori_bs):.4%}","τ Bühlmann":f"{r['tau_credible']:.4%}",
                "Interprétation":r["interpretation"]} for n,r in cred_res.items()],
                "Crédibilité Bühlmann-Straub par tranche")

        # ── BOOTSTRAP IC ──────────────────────────────────────────────────────
        with st.expander("IC Bootstrap (Efron & Tibshirani, 1993)", expanded=False):
            st.caption("Rééchantillonnage avec remise sur les années. Quantifie l'incertitude liée au faible historique.")
            n_boot_v = st.slider("Rééchantillons", 500, 5000, 2000, 500, key="n_boot_ci")
            alpha_ci_pct = st.select_slider("Niveau confiance %", options=[90,95,99], value=95, key="alpha_ci")
            if st.button("Calculer les IC Bootstrap", key="btn_bootstrap_ci"):
                rows_ic = []
                for t_bc in tranches_input:
                    ic = bootstrap_ci_bc(st.session_state["df_proj"].copy(), t_bc, gnpi,
                                         n_boot=n_boot_v, alpha_ci=1-alpha_ci_pct/100)
                    if ic:
                        tau_r = next((r["taux_technique"] for r in st.session_state["resultats_bc"]
                                      if r["tranche"]==t_bc["nom"]),0)
                        rows_ic.append({"Tranche":t_bc["nom"],
                            "τ BC central":f"{tau_r:.4%}",
                            f"IC {alpha_ci_pct}% bas":f"{ic['ic_lo']:.4%}",
                            f"IC {alpha_ci_pct}% haut":f"{ic['ic_hi']:.4%}",
                            "Amplitude":f"{(ic['ic_hi']-ic['ic_lo'])*100:.4f} pts"})
                    else:
                        rows_ic.append({"Tranche":t_bc["nom"],"Note":"< 4 années — impossible"})
                if rows_ic:
                    st.session_state["ic_bootstrap"] = rows_ic
                    tableau_resultats(rows_ic, f"IC {alpha_ci_pct}% Bootstrap ({n_boot_v} rééchantillons)")
            elif "ic_bootstrap" in st.session_state:
                tableau_resultats(st.session_state["ic_bootstrap"])


        st.divider()
        guide_prompt("Burning Cost",
            ["Comparer avec taux marché attendu 2-4%", "Signaler si BC < simulation de plus de 30%", "Identifier les années atypiques"],
            ["Taux BC N-1 : R&C=2.5%, CatL1=0%", "Objectif prime totale < 12M MAD", "Taux Partner Re 2025 : R&C=2.30%"],
            ["Tableau par tranche avec verdict //", "Recommandation unique par tranche", "Maximum 1 page"])

        st.markdown("###  Analyse Claude — Burning Cost")
        ctx_bc, inst_bc, inp_bc, out_bc = prompt_inputs(
            key_prefix="bc",
            placeholder_contexte="Ex: Sinistralité exceptionnelle 2020...",
            placeholder_instructions="Ex: Comparer avec taux marché 3-4%...",
            placeholder_input="Ex: Taux BC N-1 : R&C=2.5%",
            placeholder_output="Ex: Tableau par tranche + verdict OK/ALERTE/RÉVISER")

        if api_key and st.button(" Recommandations Claude — BC"):
            prompt = build_prompt(
                role="Expert actuaire senior en reassurance non-proportionnelle automobile, 15 ans d'experience XL et cat.",
                task="1. Evalue le niveau du taux vs normes marche\n2. Verifie coherence inter-tranches\n3. Analyse impact Rec\n4. Verdict : OK | A verifier | Probleme",
                data=f"BC : {json.dumps([{k:v for k,v in r.items() if k!='detail_annuel'} for r in st.session_state['resultats_bc']], indent=2)}\nProgramme : {json.dumps(tranches_input, indent=2)}\nGNPI : {gnpi:,} MAD",
                contexte=ctx_bc, instructions=inst_bc, input_data=inp_bc, output_instructions=out_bc,
                contexte_global=st.session_state.get("instructions_globales",""),
                contraintes="- tau_tech < tau_risque (Rec reduit - NORMAL)\n- BC=0 tranche cat NORMAL\n- Ne pas inventer comparatifs marche")
            claude_stream(api_key, prompt, max_tokens=2000, session_key="analyse_bc")

        if "analyse_bc" in st.session_state:
            st.markdown(st.session_state["analyse_bc"])

# ════════════════════════════════════════════
# TAB 4 — SIMULATION
# ════════════════════════════════════════════

with tab4:
    st.header("Simulation Pareto / Poisson")
    st.caption("Simule S'0 sur la loi choisie — applique coeff Sk/S'k pour charge réassurance")

    if "alpha_est" not in st.session_state:
        st.warning(" Transformez d'abord le triangle")
    else:
        # ══ Section 0 : Analyse distributions (Hill, MEF, CDF, fits) ══
        with st.expander("Analyse des distributions — Seuil · Hill · MEF · Gertensgarbe · Fits · CDF", expanded=False):
            section_analyse_distributions()

        # ══ Section A : Détection automatique du seuil TVE ══════════════
        with st.expander(" Détection automatique du seuil TVE (Hill + MEF + Gertensgarbe)", expanded=True):
            st.caption("Les 3 méthodes détectent le seuil optimal. Une droite rouge indique le seuil recommandé. Choisissez ensuite votre seuil.")

            if st.button("🔍 Détecter le seuil optimal automatiquement", key="btn_detect_seuil"):
                data_sim_tve = st.session_state.get("df_proj", None)
                if data_sim_tve is not None:
                    with st.spinner("Analyse TVE en cours..."):
                        X_tve = data_sim_tve["Sprime_ultime"].dropna().values
                        X_tve = X_tve[X_tve > 0]
                        seuil_opt, fig_tve, diag_tve = detecter_seuil_optimal_tve(X_tve, "Sinistres projetés")
                        if fig_tve:
                            st.pyplot(fig_tve, use_container_width=True)
                            plt.close(fig_tve)
                            st.session_state["seuil_tve_detecte"] = seuil_opt
                            st.session_state["diag_tve"] = diag_tve
                else:
                    st.warning("Données non disponibles — transformez d'abord le triangle")

            if "diag_tve" in st.session_state:
                diag = st.session_state["diag_tve"]
                cols_diag = st.columns(4)
                cols_diag[0].metric("Hill (stabilité CV)",
                                    f"{diag.get('seuil_hill',0):,.0f} MAD",
                                    delta=f"α={diag.get('alpha_hill',0):.4f} · k={diag.get('k_hill',0)}")
                cols_diag[1].metric("MEF (linéarité R²)",
                                    f"{diag.get('seuil_mef',0):,.0f} MAD",
                                    delta=f"R²={diag.get('mef_r2',0):.3f}")
                cols_diag[2].metric("Gertensgarbe-Werner",
                                    f"{diag.get('seuil_gert',0):,.0f} MAD",
                                    delta=f"α={diag.get('alpha_gert',0):.4f} · k*={diag.get('k_gert',0)}")
                cols_diag[3].metric("Consensus (médiane)",
                                    f"{diag.get('seuil_optimal',0):,.0f} MAD",
                                    delta=" Recommandé")

                st.info(
                    f"Gertensgarbe k*={diag.get('k_gert',0)} · "
                    f"Hill stabilité k={diag.get('k_hill',0)} · "
                    f"MEF linéarité R²={diag.get('mef_r2',0):.3f} · "
                    "Cherchez la zone stable du Hill et la linéarité du MEF pour confirmer u."
                )

            # ── Slider interactif pour positionner la droite verticale ────────
            st.markdown("**🎚️ Positionnement interactif du seuil**")
            data_pctiles = st.session_state.get("df_proj", None)
            if data_pctiles is not None:
                X_ch = data_pctiles["Sprime_ultime"].dropna().values
                X_ch = X_ch[X_ch > 0]
                s_min = float(np.percentile(X_ch, 50))
                s_max = float(np.percentile(X_ch, 99))
                seuil_slider = st.slider(
                    "Glissez pour positionner le seuil (droite rouge verticale)",
                    min_value=int(s_min), max_value=int(s_max),
                    value=int(st.session_state.get("seuil_est", np.percentile(X_ch, 80))),
                    step=max(1, int((s_max - s_min) / 200)),
                    format="%d MAD",
                    key="seuil_slider_interactif"
                )
                n_exc_slider = int(np.sum(X_ch > seuil_slider))

                # Graphiques avec droite verticale interactive
                import matplotlib.pyplot as plt
                import matplotlib.ticker as mticker
                sorted_desc_sl = np.sort(X_ch)[::-1]
                u_sorted_sl    = np.sort(np.unique(X_ch))
                step_sl = max(1, len(u_sorted_sl) // 80)
                u_mef_sl = u_sorted_sl[::step_sl][:-1]
                mef_sl   = np.array([
                    float(np.mean(X_ch[X_ch > u] - u)) if np.sum(X_ch > u) >= 2 else np.nan
                    for u in u_mef_sl
                ])
                valid_sl = ~np.isnan(mef_sl)

                fig_sl, axes_sl = plt.subplots(1, 3, figsize=(16, 5))
                for ax in axes_sl:
                    ax.set_facecolor("white")
                    ax.spines[["top","right"]].set_visible(False)
                fig_sl.patch.set_facecolor("white")
                ax_sl1, ax_sl2, ax_sl3 = axes_sl

                # Hill interactif
                k_max_sl = min(len(sorted_desc_sl)-2, 150)
                ks_sl = np.arange(1, k_max_sl+1)
                hills_sl = np.array([
                    k / np.sum(np.log(sorted_desc_sl[:k]/sorted_desc_sl[k]))
                    if sorted_desc_sl[k]>0 and np.sum(np.log(sorted_desc_sl[:k]/sorted_desc_sl[k]))>0
                    else np.nan for k in ks_sl
                ])
                ok_sl = ~np.isnan(hills_sl)
                with np.errstate(invalid='ignore'):
                    ci_up_sl  = hills_sl + 1.96*hills_sl/np.sqrt(ks_sl)
                    ci_low_sl = np.maximum(hills_sl - 1.96*hills_sl/np.sqrt(ks_sl), 0)
                k_slider = int(np.sum(sorted_desc_sl > seuil_slider))
                k_slider = max(1, min(k_slider, k_max_sl))

                # (1) Hill
                ax_sl1.plot(ks_sl[ok_sl], hills_sl[ok_sl], color="black", lw=1.2)
                ax_sl1.fill_between(ks_sl[ok_sl], ci_low_sl[ok_sl], ci_up_sl[ok_sl],
                                    color="steelblue", alpha=0.25, label="IC 95 %")
                ax_sl1.axvline(k_slider, color="red", ls="--", lw=2,
                               label=f"k={k_slider} → α={hills_sl[min(k_slider-1,len(hills_sl)-1)]:.4f}")
                ax_sl1.set_xlabel("Order Statistics")
                ax_sl1.set_ylabel("Tail Index α(k)")
                ax_sl1.set_title(f"Hill Plot — seuil {seuil_slider:,.0f} MAD")
                ax_sl1.legend(fontsize=8)
                ax_sl1.grid(alpha=0.2, linestyle="--")

                # (2) MEF — cercles ouverts style meplot R
                ax_sl2.scatter(u_mef_sl[valid_sl], mef_sl[valid_sl],
                               s=30, facecolors="none", edgecolors="black", linewidths=0.8)
                ax_sl2.axvline(seuil_slider, color="red", ls="--", lw=2,
                               label=f"Seuil = {seuil_slider:,.0f}")
                ax_sl2.set_xlabel("Threshold")
                ax_sl2.set_ylabel("Mean Excess")
                ax_sl2.set_title("Mean Excess Function")
                ax_sl2.xaxis.set_major_formatter(mticker.ScalarFormatter(useMathText=True))
                ax_sl2.yaxis.set_major_formatter(mticker.ScalarFormatter(useMathText=True))
                ax_sl2.ticklabel_format(axis="both", style="sci", scilimits=(0,0))
                ax_sl2.legend(fontsize=8)
                ax_sl2.grid(alpha=0.2, linestyle="--")

                # (3) Gertensgarbe — U progressif / régressif
                h_ok_sl = hills_sl[ok_sl]; k_ok_sl = ks_sl[ok_sl]; nk_sl = len(h_ok_sl)
                u_fwd_sl = np.zeros(nk_sl); u_bwd_rev_sl = np.zeros(nk_sl)
                for i in range(2, nk_sl):
                    s_f = sum(1 for j in range(i) if h_ok_sl[j] < h_ok_sl[i])
                    e_f = i*(i-1)/4; v_f = i*(i-1)*(2*i+5)/72
                    u_fwd_sl[i] = (s_f-e_f)/np.sqrt(max(v_f,1e-10))
                h_rev_sl = h_ok_sl[::-1]
                for i in range(2, nk_sl):
                    s_b = sum(1 for j in range(i) if h_rev_sl[j] < h_rev_sl[i])
                    e_b = i*(i-1)/4; v_b = i*(i-1)*(2*i+5)/72
                    u_bwd_rev_sl[i] = (s_b-e_b)/np.sqrt(max(v_b,1e-10))
                u_bwd_sl = u_bwd_rev_sl[::-1]
                cross_sl = np.where(np.diff(np.sign(u_fwd_sl - u_bwd_sl)))[0]
                k_gert_sl = int(k_ok_sl[cross_sl[0]]) if len(cross_sl)>0 else int(k_ok_sl[nk_sl//2])

                ax_sl3.plot(k_ok_sl, u_fwd_sl, color="black", lw=1.5, label="U progressif")
                ax_sl3.plot(k_ok_sl, u_bwd_sl, color="black", lw=1.5, ls="--", label="U régressif")
                ax_sl3.axhline(0, color="black", lw=0.6, alpha=0.4)
                ax_sl3.axvline(k_slider, color="red", ls="--", lw=2,
                               label=f"k={k_slider}  (u≈{seuil_slider:,.0f})")
                ax_sl3.axvline(k_gert_sl, color="orange", ls=":", lw=1.5,
                               label=f"Gertensgarbe k*={k_gert_sl}")
                ax_sl3.set_xlabel("Order Statistics")
                ax_sl3.set_ylabel("Statistique U(k)")
                ax_sl3.set_title("Gertensgarbe-Werner")
                ax_sl3.legend(fontsize=8)
                ax_sl3.grid(alpha=0.2, linestyle="--")

                plt.tight_layout()
                st.pyplot(fig_sl); plt.close(fig_sl)

                col_a, col_b = st.columns(2)
                col_a.metric("Excédances au-dessus du seuil", f"{n_exc_slider}",
                             delta=f"{n_exc_slider/len(X_ch)*100:.1f}% des sinistres")
                alpha_at_slider = float(hills_sl[min(k_slider-1, len(hills_sl)-1)]) if not np.isnan(hills_sl[min(k_slider-1,len(hills_sl)-1)]) else 1.5
                col_b.metric("α Hill estimé à ce seuil", f"{alpha_at_slider:.4f}")

                if st.button(" Appliquer ce seuil", key="btn_apply_slider_seuil", type="primary"):
                    st.session_state["seuil_est"] = float(seuil_slider)
                    st.session_state["alpha_est"] = alpha_at_slider
                    lambda_new = float(n_exc_slider / len(
                        data_pctiles["annee_surv"].unique()))
                    st.session_state["lambda_est"] = lambda_new
                    st.success(f" Seuil = {seuil_slider:,.0f} MAD | α = {alpha_at_slider:.4f} | λ = {lambda_new:.4f}")
                    st.rerun()

            # Seuil de modélisation — choix par liste
            st.markdown("**Ou choisir parmi les seuils proposés :**")
            seuil_default = st.session_state.get("seuil_tve_detecte", st.session_state["seuil_est"])
            if data_pctiles is not None:
                seuil_options = {}
                if "diag_tve" in st.session_state:
                    d = st.session_state["diag_tve"]
                    seuil_options[f" Hill (k={d.get('k_hill',0)}) = {d.get('seuil_hill',0):,.0f} MAD"] = float(d.get('seuil_hill', seuil_default))
                    seuil_options[f" MEF (R²={d.get('mef_r2',0):.2f}) = {d.get('seuil_mef',0):,.0f} MAD"] = float(d.get('seuil_mef', seuil_default))
                    seuil_options[f" Gertensgarbe (k*={d.get('k_gert',0)}) = {d.get('seuil_gert',0):,.0f} MAD"] = float(d.get('seuil_gert', seuil_default))
                    seuil_options[f" Consensus TVE = {d.get('seuil_optimal',0):,.0f} MAD"] = float(d.get('seuil_optimal', seuil_default))
                for p in [0.60, 0.65, 0.70, 0.75, 0.80, 0.85, 0.90, 0.95]:
                    seuil_options[f"Q{int(p*100)} = {np.quantile(X_ch, p):,.0f} MAD"] = float(np.quantile(X_ch, p))
                seuil_options[" Saisie manuelle"] = -1.0
                seuil_label  = st.selectbox("Seuil de modélisation", list(seuil_options.keys()), key="seuil_select_label")
                seuil_choisi = seuil_options[seuil_label]
                if seuil_choisi < 0:
                    seuil_choisi = st.number_input("Seuil manuel (MAD)", value=float(seuil_default),
                                                   step=50_000.0, format="%.0f", key="seuil_manuel_input")
                if st.button(" Appliquer ce seuil (liste)", key="btn_apply_list_seuil"):
                    st.session_state["seuil_est"] = seuil_choisi
                    n_exc_new = int(np.sum(X_ch > seuil_choisi))
                    if n_exc_new > 1:
                        exc_new = X_ch[X_ch > seuil_choisi]
                        st.session_state["alpha_est"] = float(n_exc_new / np.sum(np.log(exc_new / seuil_choisi)))
                        st.session_state["lambda_est"] = float(n_exc_new / len(
                            data_pctiles["annee_surv"].unique()))
                    st.success(f" Seuil = {seuil_choisi:,.0f} MAD | Excédances : {n_exc_new}")
                    st.rerun()

        # ══ Section B : Choix de la loi de sévérité ══════════════════════
        with st.expander(" Sélection de la loi de sévérité (Pareto / Lognormale / GPD)", expanded=True):
            if st.session_state.get("df_proj") is not None:
                X_fit = st.session_state["df_proj"]["Sprime_ultime"].dropna().values
                X_fit = X_fit[X_fit > 0]
                seuil_fit = st.session_state.get("seuil_est", st.session_state["seuil_est"])

                if st.button(" Comparer les lois et choisir", key="btn_comparer_lois"):
                    with st.spinner("Ajustement des 3 lois..."):
                        res_lois, err_lois = comparer_lois_ajustement(X_fit, seuil_fit)
                    if err_lois:
                        st.warning(err_lois)
                    else:
                        st.session_state["comparaison_lois"] = res_lois

                if "comparaison_lois" in st.session_state:
                    cols_aff = ["Loi","Params","KS stat","p-value KS","AIC","BIC","Recommandée"]
                    tableau_resultats(
                        [{k: r.get(k,"") for k in cols_aff}
                         for r in st.session_state["comparaison_lois"]],
                        "Comparaison des lois d'ajustement")
                    st.markdown("""<div style="background:#f2f8f7;border-left:4px solid #00b5a5;
                        padding:10px 14px;font-size:12px">
                        <b>Guide :</b> p-value KS > 0.05 = bonne adéquation · AIC minimal = meilleur fit ·
                        ξ GPD > 0 = queue lourde (Fréchet) · ξ ≈ 0 = Gumbel · ξ < 0 = Weibull bornée
                        </div>""", unsafe_allow_html=True)

                loi_retenue = st.selectbox(
                    " Loi retenue pour la simulation",
                    options=["pareto", "lognormale", "gpd"],
                    format_func=lambda x: {
                        "pareto": "Pareto — Extrapolation classique XL",
                        "lognormale": "Lognormale — Sinistres moyens / branche mixte",
                        "gpd": "GPD — Extreme Value Theory (TVE recommandée cat)"
                    }[x],
                    key="loi_simulation_choisie",
                    help="Choisissez selon les indicateurs AIC/KS ci-dessus"
                )
                st.session_state["loi_sim"] = loi_retenue

                # Mise à jour dynamique des paramètres selon la loi
                if "comparaison_lois" in st.session_state:
                    loi_data = next((r for r in st.session_state["comparaison_lois"]
                                     if r["Loi"].lower() == loi_retenue), None)
                    if loi_data:
                        params_str = loi_data.get("Params", "")
                        st.markdown(f"**Paramètres {loi_retenue.upper()} :** `{params_str}`")
                        # Extraire et stocker les paramètres pour la simulation
                        import re as _re
                        if loi_retenue == "pareto":
                            m = _re.search(r"α=([\d.]+)", params_str)
                            if m: st.session_state["alpha_est"] = float(m.group(1))
                        elif loi_retenue == "lognormale":
                            m_mu = _re.search(r"μ=([-\d.]+)", params_str)
                            m_si = _re.search(r"σ=([\d.]+)", params_str)
                            if m_mu: st.session_state["loi_mu"]    = float(m_mu.group(1))
                            if m_si: st.session_state["loi_sigma"] = float(m_si.group(1))
                        elif loi_retenue == "gpd":
                            m_xi   = _re.search(r"ξ=([-\d.]+)", params_str)
                            m_beta = _re.search(r"β=([\d.,]+)", params_str)
                            if m_xi:   st.session_state["gpd_xi"]   = float(m_xi.group(1))
                            if m_beta: st.session_state["gpd_beta"] = float(m_beta.group(1).replace(",",""))

                # Afficher les paramètres actifs selon la loi
                if loi_retenue == "pareto":
                    st.info(f" **Pareto** | α = {st.session_state.get('alpha_est',1.5):.4f} | "
                            f"λ = {st.session_state.get('lambda_est',5.0):.4f} | "
                            f"Seuil = {st.session_state.get('seuil_est',0):,.0f} MAD")
                elif loi_retenue == "lognormale":
                    st.info(f" **Lognormale** | μ = {st.session_state.get('loi_mu', 0):.4f} | "
                            f"σ = {st.session_state.get('loi_sigma', 0):.4f} | "
                            f"λ = {st.session_state.get('lambda_est',5.0):.4f} | "
                            f"Seuil = {st.session_state.get('seuil_est',0):,.0f} MAD")
                elif loi_retenue == "gpd":
                    st.info(f" **GPD** | ξ = {st.session_state.get('gpd_xi', 0):.4f} | "
                            f"β = {st.session_state.get('gpd_beta', 0):,.0f} | "
                            f"λ = {st.session_state.get('lambda_est',5.0):.4f} | "
                            f"Seuil = {st.session_state.get('seuil_est',0):,.0f} MAD")

        is_long_sim = st.session_state.get("is_long", True)
        loi_active  = st.session_state.get("loi_sim", "pareto")

        # ── Paramètres dynamiques selon la loi ───────────────────────────────
        st.markdown("####  Paramètres de simulation")
        c1, c2, c3, c4 = st.columns(4)
        with c4: n_sim_v = st.number_input("Nb simulations", value=10000, step=1000, key="nsim_input")

        if loi_active == "pareto":
            st.info(f"🌿 Branche {'longue' if is_long_sim else 'courte'} | **Pareto** | "
                    f"Seuil={st.session_state['seuil_est']:,.0f} | α={st.session_state['alpha_est']:.4f} | λ={st.session_state['lambda_est']:.4f}")
            with c1: st.number_input("α (Alpha Pareto)",  value=float(st.session_state["alpha_est"]),  step=0.01,     format="%.4f", key="alpha_input")
            with c2: st.number_input("λ (Lambda Poisson)", value=float(st.session_state["lambda_est"]), step=0.1,      format="%.4f", key="lambda_input")
            with c3: st.number_input("Seuil (MAD)",        value=float(st.session_state["seuil_est"]),  step=50_000.0, format="%.0f", key="seuil_input")
            # Alias pour la simulation
            xi_v = None; beta_v = None
            mu_ln_v = None; sigma_ln_v = None

        elif loi_active == "lognormale":
            mu_default    = float(st.session_state.get("loi_mu",    np.log(max(st.session_state.get("seuil_est",1e6), 1))))
            sigma_default = float(st.session_state.get("loi_sigma", 1.0))
            st.info(f"🌿 Branche {'longue' if is_long_sim else 'courte'} | **Lognormale** | "
                    f"Seuil={st.session_state['seuil_est']:,.0f} | μ={mu_default:.4f} | σ={sigma_default:.4f} | λ={st.session_state['lambda_est']:.4f}")
            with c1: st.number_input("μ (mu log-space)",   value=mu_default,    step=0.05, format="%.4f", key="mu_ln_input")
            with c2: st.number_input("σ (sigma log-space)", value=sigma_default, step=0.05, format="%.4f", key="sigma_ln_input")
            with c3: st.number_input("λ (Lambda Poisson)",  value=float(st.session_state["lambda_est"]), step=0.1, format="%.4f", key="lambda_input")
            # Alias
            alpha_v = None; xi_v = None; beta_v = None
            mu_ln_v = None; sigma_ln_v = None

        elif loi_active == "gpd":
            xi_default   = float(st.session_state.get("gpd_xi",   0.3))
            beta_default = float(st.session_state.get("gpd_beta",  max(st.session_state.get("seuil_est",1e6)*0.5, 1)))
            st.info(f"🌿 Branche {'longue' if is_long_sim else 'courte'} | **GPD** | "
                    f"Seuil={st.session_state['seuil_est']:,.0f} | ξ={xi_default:.4f} | β={beta_default:,.0f} | λ={st.session_state['lambda_est']:.4f}")
            with c1: st.number_input("ξ (xi — indice de queue)", value=xi_default,   step=0.01, format="%.4f", key="gpd_xi_input")
            with c2: st.number_input("β (beta — échelle GPD)",   value=beta_default, step=10_000.0, format="%.0f", key="gpd_beta_input")
            with c3: st.number_input("λ (Lambda Poisson)",       value=float(st.session_state["lambda_est"]), step=0.1, format="%.4f", key="lambda_input")
            xi_v = None; beta_v = None; mu_ln_v = None; sigma_ln_v = None

        if st.button(" Lancer la simulation", type="primary"):
            with st.spinner(" Simulation en cours..."):
                progress_sim = st.progress(0, text="Initialisation...")
                loi_sim  = st.session_state.get("loi_sim", "pareto")
                seuil_f  = float(st.session_state.get("seuil_input", st.session_state["seuil_est"]))
                lambda_f = float(st.session_state.get("lambda_input", st.session_state["lambda_est"]))
                n_s      = int(st.session_state.get("nsim_input", 10000))
                coeffs   = st.session_state["coeffs"]

                # Paramètres spécifiques à la loi
                if loi_sim == "pareto":
                    alpha_f = float(st.session_state.get("alpha_input", st.session_state["alpha_est"]))
                elif loi_sim == "lognormale":
                    mu_f    = float(st.session_state.get("mu_ln_input",    st.session_state.get("loi_mu", 13.0)))
                    sigma_f = float(st.session_state.get("sigma_ln_input", st.session_state.get("loi_sigma", 1.0)))
                elif loi_sim == "gpd":
                    xi_f   = float(st.session_state.get("gpd_xi_input",   st.session_state.get("gpd_xi",   0.3)))
                    beta_f = float(st.session_state.get("gpd_beta_input",  st.session_state.get("gpd_beta", 500_000.0)))

                np.random.seed(42)
                resultats_sim = []
                for idx_t, t_info in enumerate(tranches_input):
                    progress_sim.progress(int((idx_t/len(tranches_input))*100), text=f"Simulation {t_info['nom']}...")
                    D = t_info["priorite"]; P = t_info["portee"]
                    r = t_info["nb_reconstitutions"]; aal = t_info["AAL"]; aad = t_info["AAD"]
                    cap = (r + 1) * P

                    def simuler(avec_aal, avec_aad, avec_rec):
                        charges = []
                        for _ in range(n_s):
                            N = np.random.poisson(lambda_f); S_total = 0
                            if N > 0:
                                # ── Génération selon la loi choisie ──────────
                                if loi_sim == "pareto":
                                    U = np.random.uniform(size=N)
                                    Sprime_sim = seuil_f * (U ** (-1/alpha_f))
                                elif loi_sim == "lognormale":
                                    Sprime_sim = np.random.lognormal(mu_f, sigma_f, size=N)
                                    Sprime_sim = np.maximum(Sprime_sim, seuil_f)
                                elif loi_sim == "gpd":
                                    U = np.random.uniform(size=N)
                                    if xi_f != 0:
                                        Sprime_sim = seuil_f + beta_f / xi_f * ((1 - U) ** (-xi_f) - 1)
                                    else:
                                        Sprime_sim = seuil_f - beta_f * np.log(U)
                                else:
                                    U = np.random.uniform(size=N)
                                    Sprime_sim = seuil_f * (U ** (-1/1.5))

                                idx_c = np.random.choice(len(coeffs), size=N, replace=True)
                                for i in range(N):
                                    S_prime = Sprime_sim[i]; c = coeffs[idx_c[i]]
                                    if S_prime <= D: S_i = 0
                                    elif S_prime <= D + P: S_i = c * (S_prime - D)
                                    else: S_i = c * P
                                    S_total += S_i
                            ch = S_total
                            if avec_aad and aad: ch = max(ch - aad, 0)
                            if avec_aal and aal: ch = min(ch, aal)
                            charges.append(min(ch, cap) if avec_rec else ch)
                        return np.array(charges)

                    def calc_taux(ch):
                        P0 = np.mean(ch); sig = np.std(ch)
                        tp = P0 / gnpi; tr = (P0 + 0.2 * sig) / gnpi
                        tt = tr / (1 - t_info["brokage"] - t_info["frais"] - t_info["marge"] - t_info["retrocession"])
                        return tp, tr, tt

                    c_base = simuler(True, True, True); c_sans_aal = simuler(False, True, True)
                    c_sans_aad = simuler(True, False, True); c_sans_rec = simuler(True, True, False)
                    tp, tr, tt = calc_taux(c_base)
                    tp2, tr2, tt2 = calc_taux(c_sans_aal)
                    tp3, tr3, tt3 = calc_taux(c_sans_aad)
                    tp4, tr4, tt4 = calc_taux(c_sans_rec)
                    resultats_sim.append({
                        "tranche": t_info["nom"], "type": t_info["type"],
                        "taux_pur": tp, "taux_risque": tr, "taux_technique": tt,
                        "chargement_majeurs": st.session_state.get("chargement_majeurs", 0.0),
                        "sans_aal": tt2, "sans_aad": tt3, "sans_rec": tt4,
                        "impact_aal": round(tt2 - tt, 6), "impact_aad": round(tt3 - tt, 6), "impact_rec": round(tt4 - tt, 6),
                    })
                progress_sim.progress(100, text="Terminé !")
                st.session_state["resultats_sim"] = resultats_sim
                # ── Auto-save ──
                try:
                    db_save_session(st.session_state.get("user_email",""), gnpi, tranches_input)
                    db_save_etape("sim", resultats_sim)
                    st.toast(" Simulation sauvegardée")
                except Exception as _e:
                    st.toast(f" Sauvegarde DB : {_e}")

    if "resultats_sim" in st.session_state:
        tableau_resultats([{
            "Tranche": r["tranche"], "Taux pur": f"{r['taux_pur']:.4%}",
            "Taux risque": f"{r['taux_risque']:.4%}", "Taux technique": f"{r['taux_technique']:.4%}",
            "Charg. majeurs": f"{r.get('chargement_majeurs', 0):.4%}",
            "Sans AAL": f"{r['sans_aal']:.4%}", "Sans AAD": f"{r['sans_aad']:.4%}",
            "Sans reconst.": f"{r['sans_rec']:.4%}",
        } for r in st.session_state["resultats_sim"]], titre=" Résultats Simulation")

        st.divider()
        guide_prompt("Simulation Pareto/Poisson",
            ["Alpha calibré sur données 2016-2025", "Lambda estimé sur portefeuille 183M MAD", "Seuil TVE retenu : p80 x D"],
            ["Analyser impact AAL sur tranche cat", "Comparer BC vs Simulation par tranche", "Recommander montant optimal des conditions"],
            ["Alpha R=1.45, Lambda R=3.2", "Résultats simulation N-1 : R&C=3.1%", "Période de retour majeurs : 20 ans"],
            ["Impact par condition en points de taux", "Classement NECESSAIRE/A AJUSTER/INUTILE", "Recommandation chiffrée par condition"])

        st.markdown("###  Analyse Claude — Simulation & Conditions")
        ctx_sim, inst_sim, inp_sim, out_sim = prompt_inputs(
            key_prefix="sim",
            placeholder_contexte="Ex: Nouveau modèle cat, lambda revu à la hausse...",
            placeholder_instructions="Ex: Seuil d'alerte écart = 20%...",
            placeholder_input="Ex: Résultats simulation N-1...",
            placeholder_output="Ex: Verdict par condition + impact en points de taux")

        if api_key and st.button(" Recommandations Claude — Simulation"):
            prompt = build_prompt(
                role="Expert en modelisation catastrophe et simulation stochastique reassurance.",
                task="1. Impact par condition en points de taux\n2. Classe NECESSAIRE/A AJUSTER/INUTILE\n3. Montant optimal\n4. Compare BC vs Simulation",
                data=f"Simulation : {json.dumps(st.session_state['resultats_sim'], indent=2)}\nProgramme : {json.dumps(tranches_input, indent=2)}",
                contexte=ctx_sim, instructions=inst_sim, input_data=inp_sim, output_instructions=out_sim,
                contexte_global=st.session_state.get("instructions_globales",""),
                contraintes="- Ne pas supprimer AAL sur cat\n- AAD trop eleve = tranche inutile\n- Ecart BC/Sim>50% = anomalie majeure")
            claude_stream(api_key, prompt, max_tokens=2000, session_key="analyse_sim")

        if "analyse_sim" in st.session_state:
            st.markdown(st.session_state["analyse_sim"])

# ════════════════════════════════════════════
# TAB 5 — MARKET CURVE
# ════════════════════════════════════════════

with tab5:
    st.header("Courbe de référence marché")
    st.caption("ROL = a x x^(-b)  |  x = (D + C/2) / GNPI  |  tau_pur = ROL x C / GNPI")
    st.markdown("""
    <div style="background:linear-gradient(135deg,#0d2b3e,#004d40);
        padding:14px 20px;border-left:4px solid #00b5a5;margin-bottom:12px;font-size:13px;color:white">
      <b style="color:#00b5a5">Regles Courbe de référence marché :</b><br>
      Utiliser UNIQUEMENT des donnees representant les tranches a tarifer.<br>
      Si ROL cible ~ 10% : filtrer donnees ROL entre 0% et 15% uniquement.<br>
      Ne jamais melanger donnees a fort ROL avec tranches a faible ROL.<br>
      R2 >= 0.40, N >= 15 points, hierarchie ROL respectee (priorite haute = ROL bas).<br>
      <span style="color:#aaa;font-size:11px">
      R4 -- Courbe de référence marché applicable aux tranches cat et non-travaillantes.
      </span>
    </div>""", unsafe_allow_html=True)

    f_mkt = st.file_uploader("Donnees marche", type=["xlsx","csv"], key="f_mkt")

    # Filtres ROL par tranche
    with st.expander("Parametres ROL par tranche (recommande)", expanded=True):
        st.caption(
            "Definissez la plage de ROL pour chaque tranche. "
            "Ex: T2 ROL ~ 2% -> utiliser donnees ROL entre 0.5% et 4% uniquement.")
        rol_par_tranche = {}
        cat_tranches_mkt = [t for t in tranches_input if t["type"] != "travaillante"]
        if cat_tranches_mkt:
            cols_tr_mkt = st.columns(min(len(cat_tranches_mkt), 3))
            for i_t, t_mkt in enumerate(cat_tranches_mkt):
                with cols_tr_mkt[i_t % min(len(cat_tranches_mkt), 3)]:
                    st.markdown(f"**{t_mkt['nom']}** ({t_mkt['type']})")
                    r_mn = st.number_input(f"ROL min %", value=0.5, step=0.5,
                        min_value=0.0, max_value=50.0, key=f"rol_min_t{i_t}")
                    r_mx = st.number_input(f"ROL max %", value=5.0, step=0.5,
                        min_value=0.0, max_value=100.0, key=f"rol_max_t{i_t}")
                    rol_par_tranche[t_mkt["nom"]] = (r_mn/100, r_mx/100)
        if rol_par_tranche:
            st.session_state["rol_par_tranche"] = rol_par_tranche
            st.info("Plages ROL par tranche enregistrees. Le fit sera realise avec les donnees filtrees par tranche si disponibles.")

    with st.expander("Parametres de filtrage global", expanded=False):
        c1, c2, c3 = st.columns(3)
        with c1:
            rol_min = st.number_input("ROL minimum (%)",  value=0.5,   step=0.5)  / 100
            rol_max = st.number_input("ROL maximum (%)",  value=100.0, step=10.0) / 100
        with c2:
            tolerance = st.number_input("Tolerance proximite ROL Midpoint (%)", value=50.0, step=5.0) / 100
            r2_min    = st.number_input("R2 minimum accepte (%)", value=40.0, step=5.0) / 100
        with c3:
            filtre_branche = st.text_input("Filtre branche (INT_BUSINESS)", value="EVENEMENT")
            st.caption("Laisser vide = pas de filtre")


        if f_mkt is None:
            st.info("⬆️ Uploadez un fichier de données marché pour construire la Courbe de référence marché.")
            st.stop()

        if st.button("🔨 Construire la Courbe de référence marché", type="primary",
                     key="btn_construire_mkt_main", use_container_width=False):
            with st.spinner(" Construction en cours..."):
                df_mkt = pd.read_excel(f_mkt) if f_mkt.name.endswith('xlsx') else pd.read_csv(f_mkt)
                df_mkt.columns = [c.strip() for c in df_mkt.columns]
                for col in ['ROLs', 'midpoints', 'Garantie en MAD', 'Priorité en MAD']:
                    if col in df_mkt.columns and df_mkt[col].dtype == object:
                        df_mkt[col] = (df_mkt[col].astype(str).str.replace('%','').str.replace(' ','').str.replace(',','.')
                                       .apply(lambda x: float(x)/100 if x not in ['nan',''] and float(x) > 1.5
                                              else (float(x) if x not in ['nan',''] else np.nan)))
                df_mkt = df_mkt.dropna(subset=['ROLs', 'midpoints'])
                n_avant = len(df_mkt)
                if filtre_branche.strip():
                    col_business = next((c for c in df_mkt.columns if 'BUSINESS' in c.upper()), None)
                    if col_business:
                        df_mkt = df_mkt[df_mkt[col_business].astype(str).str.strip().str.upper()
                                        .str.contains(filtre_branche.strip().upper(), regex=False, na=False)]
                n_filtre = n_avant - len(df_mkt)
                mask_rol = (df_mkt['ROLs'] >= rol_min) & (df_mkt['ROLs'] <= rol_max)
                df_excl_rol = df_mkt[~mask_rol].copy(); df_mkt = df_mkt[mask_rol].copy(); n_rol = len(df_excl_rol)
                df_mkt['diff_rel'] = np.where(df_mkt['midpoints'] != 0,
                    np.abs(df_mkt['ROLs'] - df_mkt['midpoints']) / np.abs(df_mkt['midpoints']), 1.0)
                df_excl_prox = df_mkt[df_mkt['diff_rel'] < tolerance].copy()
                df_mkt = df_mkt[df_mkt['diff_rel'] >= tolerance].copy(); n_prox = len(df_excl_prox)
                df_mkt = df_mkt[df_mkt['midpoints'] > 0].copy()
                st.markdown(f"""<div style="background:#f0fff4;border-left:4px solid #2d8a4e;border-radius:0 8px 8px 0;padding:12px 16px;margin:8px 0">
                     <b>{len(df_mkt)} points retenus</b> sur {n_avant} | Filtre branche : {n_filtre} | ROL hors bornes : {n_rol} | ROL≈Midpoint : {n_prox}
                    </div>""", unsafe_allow_html=True)
                if len(df_mkt) < 5:
                    st.error(" Moins de 5 points retenus."); st.stop()

                def fit_power(x, y):
                    log_x = np.log(x); log_y = np.log(y)
                    coeffs = np.polyfit(log_x, log_y, 1)
                    a = np.exp(coeffs[1]); b = -coeffs[0]
                    log_y_pred = np.polyval(coeffs, log_x)
                    r2 = 1 - np.sum((log_y-log_y_pred)**2) / np.sum((log_y-log_y.mean())**2)
                    return a, b, r2

                def predict_rol(x_norm, a, b): return a * (x_norm ** (-b))

                def calc_taux_tranche(t, a, b):
                    x_norm = (t['priorite'] + t['portee'] / 2) / gnpi
                    rol = predict_rol(x_norm, a, b)
                    taux_pur = rol * (t['portee'] / gnpi)
                    taux_risque = taux_pur * 1.002
                    taux_tech = taux_risque / (1 - t['brokage'] - t['frais'] - t['marge'] - t['retrocession'])
                    n_rec = t['nb_reconstitutions']; t_r = t['taux_reconstitution'] / 100; L = t['portee']
                    C_rep = taux_pur * gnpi
                    Pr_Rec = sum(t_r * min(L, max(C_rep - (r-1)*L, 0)) for r in range(1, n_rec+1))
                    Pr_Rec /= L if L > 0 else 1
                    Rec = Pr_Rec / (Pr_Rec + 10) if (Pr_Rec + 10) > 0 else 0
                    charg_maj_mkt = st.session_state.get("chargement_majeurs", 0.0)
                    return {"tranche": t["nom"], "type": t["type"], "x_norm": x_norm,
                            "rol": rol, "taux_pur": taux_pur, "taux_tech": taux_tech,
                            "chargement_majeurs": charg_maj_mkt, "taux": taux_tech}

                resultats_mkt = []
                for q in [0.10, 0.20, 0.30, 0.40, 0.50, 0.60, 0.70, 0.80, 0.90, 1.0]:
                    mid_max = np.quantile(df_mkt['midpoints'], q)
                    port_max = np.quantile(df_mkt['Garantie en MAD'], q) if 'Garantie en MAD' in df_mkt.columns else np.inf
                    df_q = df_mkt[(df_mkt['midpoints'] <= mid_max) &
                                   (df_mkt['Garantie en MAD'] <= port_max if 'Garantie en MAD' in df_mkt.columns else True)]
                    if len(df_q) < 5: continue
                    try:
                        a, b, r2 = fit_power(df_q['midpoints'].values, df_q['ROLs'].values)
                        if b <= 0: continue
                        taux_tranches = []; taux_nuls = 0
                        for t in tranches_input:
                            tt = calc_taux_tranche(t, a, b)
                            if tt['taux'] <= 0 or np.isnan(tt['taux']) or np.isinf(tt['taux']): taux_nuls += 1
                            taux_tranches.append(tt)
                        if taux_nuls > 0: continue
                        taux_vals = [tt["taux"] for tt in taux_tranches]
                        median_taux = np.median(taux_vals)
                        cv_taux = np.std(taux_vals) / median_taux if median_taux > 0 else 99
                        resultats_mkt.append({"quantile": q, "n_points": len(df_q), "a": a, "b": b,
                                              "r2": r2, "cv_taux": cv_taux, "taux_tranches": taux_tranches,
                                              "r2_ok": r2 >= r2_min})
                    except: continue

                if not resultats_mkt:
                    st.warning(" Relâchement contrainte.")
                    for q in [0.10, 0.20, 0.30, 0.40, 0.50, 0.60, 0.70, 0.80, 0.90, 1.0]:
                        mid_max = np.quantile(df_mkt['midpoints'], q)
                        df_q = df_mkt[df_mkt['midpoints'] <= mid_max]
                        if len(df_q) < 5: continue
                        try:
                            a, b, r2 = fit_power(df_q['midpoints'].values, df_q['ROLs'].values)
                            if b <= 0: continue
                            taux_tranches = [calc_taux_tranche(t, a, b) for t in tranches_input]
                            taux_vals = [tt["taux"] for tt in taux_tranches]
                            median_taux = np.median(taux_vals)
                            cv_taux = np.std(taux_vals) / median_taux if median_taux > 0 else 99
                            resultats_mkt.append({"quantile": q, "n_points": len(df_q), "a": a, "b": b,
                                                  "r2": r2, "cv_taux": cv_taux, "taux_tranches": taux_tranches,
                                                  "r2_ok": r2 >= r2_min})
                        except: continue

                if not resultats_mkt:
                    st.error(" Impossible d'ajuster la courbe."); st.stop()

                all_t = [tt["taux"] for r in resultats_mkt for tt in r.get("taux_tranches",[])]
                med_g = np.median([t for t in all_t if t > 0]) if any(t > 0 for t in all_t) else 1
                r2v = [r["r2"] for r in resultats_mkt]; r2min_v, r2max_v = min(r2v), max(r2v)
                for r in resultats_mkt:
                    tm = np.mean([tt["taux"] for tt in r.get("taux_tranches",[])])
                    r2_norm = (r["r2"] - r2min_v) / (r2max_v - r2min_v + 1e-10)
                    ecart_med = abs(tm - med_g) / (med_g + 1e-10)
                    taux_nuls = sum(1 for tt in r.get("taux_tranches",[]) if tt.get("taux",0) <= 0)
                    r["score"] = 0.5*r2_norm - 0.3*ecart_med - 0.2*r["cv_taux"] - taux_nuls*10.0 + (0.5 if r["r2_ok"] else 0)
                resultats_mkt = sorted(resultats_mkt, key=lambda x: x['score'], reverse=True)
                st.session_state["resultats_mkt"] = resultats_mkt
                st.session_state["df_mkt_clean"]  = df_mkt
                # ── Auto-save ──
                try:
                    db_save_etape("mkt", {"resultats_mkt": [{k:v for k,v in r.items() if k!="taux_tranches"} for r in resultats_mkt],
                                          "taux_mkt_final": resultats_mkt[0]["taux_tranches"] if resultats_mkt else []})
                    st.toast(" Courbe de référence marché sauvegardée")
                except Exception as _e:
                    st.toast(f" Sauvegarde DB : {_e}")

    if "resultats_mkt" in st.session_state and "df_mkt_clean" in st.session_state:
        rmt = st.session_state.get("resultats_mkt", [])
        # Vérification du format : resultats_mkt doit contenir des dicts avec clé "quantile"
        # (pas taux_mkt_final qui a un format différent)
        if rmt and not isinstance(rmt[0], dict):
            rmt = []
        if rmt and "quantile" not in rmt[0]:
            rmt = []
        dmc = st.session_state.get("df_mkt_clean")
        def predict_rol(x_norm, a, b): return a * (x_norm ** (-b))
        if not rmt or dmc is None:
            st.info("Courbe de référence marché non disponible pour cette session. Lancez le calcul dans l'onglet Courbe de référence marché.")
        else:
            rows_recap = []
            for r in rmt:
                row = {"Q": f"Q{int(r['quantile']*100)}", "N": r["n_points"],
                       "a": f"{r['a']:.5f}", "b": f"{r['b']:.4f}",
                       "R2": f"{r['r2']:.4f}", "R2ok": "OK" if r["r2_ok"] else "faible",
                       "Score": f"{r['score']:.4f}"}
                for tt in r.get("taux_tranches",[]):
                    row[tt["tranche"]] = f"{tt['taux']:.4%}" if tt["taux"] > 0 else "NUL"
                rows_recap.append(row)
            st.subheader("Comparaison ajustements — ROL = a x x^(-b)  |  x = (D+C/2)/GNPI")
            tableau_resultats(rows_recap)
            best = rmt[0]
            st.success(f"Meilleur : Q{int(best['quantile']*100)} — a={best['a']:.5f}, b={best['b']:.4f} | R2={best['r2']:.4f} | Score={best['score']:.4f}")

            choix_q = st.selectbox("Choisir la combinaison",
                options=[f"Q{int(r['quantile']*100)} — a={r['a']:.5f} b={r['b']:.4f} R2={r['r2']:.4f} Score={r['score']:.4f}" for r in rmt], index=0)
            idx_choix = [f"Q{int(r['quantile']*100)} — a={r['a']:.5f} b={r['b']:.4f} R2={r['r2']:.4f} Score={r['score']:.4f}" for r in rmt].index(choix_q)
            choix = rmt[idx_choix]

            x_all = dmc['midpoints'].values; y_all = dmc['ROLs'].values
            x_range = np.linspace(min(x_all), max(x_all), 300)
            y_fit = predict_rol(x_range, choix['a'], choix['b'])
            fig, ax = plt.subplots(figsize=(10, 5))
            fig.patch.set_facecolor('#f5f5f5'); ax.set_facecolor('#fafafa')
            ax.scatter(x_all, y_all, color='#2d8a4e', s=60, zorder=5, alpha=0.7, label='Données marché')
            ax.plot(x_range, y_fit, color='#1a1a1a', lw=2.5,
                    label=f"ROL = {choix['a']:.5f} x x^(-{choix['b']:.4f}) | R2={choix['r2']:.4f}")
            ax.set_xlabel('Midpoint normalisé x = (D+C/2)/GNPI'); ax.set_ylabel('ROL')
            ax.set_title('Courbe de référence marché — ROL = a x x^(-b)', fontweight='bold', color='#1a1a1a')
            ax.legend(); ax.grid(alpha=0.3, linestyle='--')
            st.pyplot(fig)

            st.subheader("Taux marché retenus")
            tableau_resultats([{
                "Tranche": tt["tranche"], "Type": tt["type"],
                "x=(D+C/2)/GNPI": f"{tt['x_norm']:.5f}",
                "ROL estimé": f"{tt['rol']:.4%}", "Taux pur": f"{tt['taux_pur']:.4%}",
                "Taux tech.": f"{tt['taux_tech']:.4%}",
                "Taux final": f"{tt['taux']:.4%}" if tt["taux"] > 0 else "NUL"
            } for tt in choix.get("taux_tranches",[])])
            st.session_state["taux_mkt_final"] = choix.get("taux_tranches",[])

        st.divider()
        guide_prompt("Courbe de référence marché",
            ["Marché 2025, 40 cotations XL événement", "Marché en durcissement +10-15%", "Modèle puissance ROL = a x x^(-b)"],
            ["Privilégier R2 >= 45% avec taux non nuls", "Signaler taux marché > 3x simulation", "Recommander UN seul ajustement"],
            ["Taux référence Cat L1=1.5%", "a=0.0487, b=0.605 (rapport FST)", "R2 acceptable > 40%"],
            ["Justification R2 + robustesse N", "Comparaison avec simulation", "Ajustement retenu avec a, b, R2"])

        st.markdown("###  Analyse Claude — Courbe de référence marché")
        ctx_mkt, inst_mkt, inp_mkt, out_mkt = prompt_inputs(
            key_prefix="mkt",
            placeholder_contexte="Ex: Marché en durcissement, hausse 15%...",
            placeholder_instructions="Ex: Privilégier N > 20 points...",
            placeholder_input="Ex: Taux référence Cat L1=1.5%",
            placeholder_output="Ex: Recommandation unique avec justification R2")

        if api_key and st.button(" Recommandations Claude — Courbe de référence marché"):
            prompt = build_prompt(
                role="Expert en reassurance catastrophe et market curve, specialiste marches emergents.",
                task=f"Analyse ajustements market curve. Critere : R2>={r2_min*100:.0f}% avec taux non nuls prime. Recommande UN seul ajustement justifie.",
                data=f"Ajustements : {json.dumps(rows_recap, indent=2)}\nProgramme : {json.dumps(tranches_input, indent=2)}\nGNPI : {gnpi:,} MAD",
                contexte=ctx_mkt, instructions=inst_mkt, input_data=inp_mkt, output_instructions=out_mkt,
                contexte_global=st.session_state.get("instructions_globales", ""),
                contraintes=f"- b>0 obligatoire\n- R2>={r2_min*100:.0f}% avec taux non nuls preferable\n- N<10 faible robustesse\n- Taux>3x simulation=suspect")
            claude_stream(api_key, prompt, max_tokens=1500, session_key="analyse_mkt")

        if "analyse_mkt" in st.session_state:
            st.markdown(st.session_state["analyse_mkt"])

# ════════════════════════════════════════════
# TAB 6 — RAPPORT FINAL
# ════════════════════════════════════════════

with tab6:
    st.header("Rapport Final de Tarification")
    st.markdown("""<div style="background:rgba(45,138,78,0.08);border-left:4px solid #2d8a4e;
        border-radius:0 8px 8px 0;padding:10px 16px;margin-bottom:12px;font-size:12px">
        <b>Règles de sélection finale</b> —
        T1 (travaillante) : max(τ_BC, τ_Sim) |
        T2, T3 (cat) : max(τ_Sim, τ_Marché) —
        Courbe de référence marché appliquée <b>uniquement aux tranches cat</b>.
        </div>""", unsafe_allow_html=True)
    manquants = [n for n, k in [("BC","resultats_bc"),("Simulation","resultats_sim"),("Courbe de référence marché","taux_mkt_final")]
                 if k not in st.session_state]
    if manquants:
        st.warning(f" Complétez d'abord : {', '.join(manquants)}")
    else:
        _bc_list  = st.session_state["resultats_bc"]
        _sim_list = st.session_state["resultats_sim"]
        _mkt_list = st.session_state["taux_mkt_final"]
        rows_rapport = []; prime_totale = 0
        for idx_t, t in enumerate(tranches_input):
            nom = t["nom"]
            bc_tt  = _lookup_taux(_bc_list,  nom, idx_t, "taux_technique")
            sim_tt = _lookup_taux(_sim_list, nom, idx_t, "taux_technique")
            # Courbe de référence marché uniquement pour tranches cat
            mkt = _lookup_taux(_mkt_list, nom, idx_t, "taux") if t["type"] != "travaillante" else 0.0
            if t["type"] == "travaillante":
                # T1 : max(BC, Sim) — méthode la plus conservative
                taux_retenu = max(bc_tt, sim_tt)
                methode_base = "BC" if bc_tt >= sim_tt else "Simulation"
                ecart = abs(bc_tt-sim_tt)/max(bc_tt,sim_tt)*100 if max(bc_tt,sim_tt)>0 else 0
                methode = f"max(BC,Sim)→{methode_base} | écart {ecart:.0f}% {'' if ecart>25 else ''}"
            else:
                # T2, T3 cat : max(Sim, Marché) — toujours côté sécurité
                taux_retenu = max(sim_tt, mkt)
                methode = f"max(Sim,Mkt)→{'Marché' if mkt >= sim_tt else 'Simulation'}"
            prime = gnpi * taux_retenu; prime_totale += prime
            rows_rapport.append({
                "Tranche": nom, "Type": t["type"],
                "Taux BC": f"{bc_tt:.4%}", "Taux Sim.": f"{sim_tt:.4%}",
                "Taux Marché": f"{mkt:.4%}", "Taux retenu": f"{taux_retenu:.4%}",
                "Prime (MAD)": f"{prime:,.0f}", "Méthode": methode
            })
        st.session_state["df_rapport"]   = pd.DataFrame(rows_rapport)
        st.session_state["prime_totale"] = prime_totale
        # ── Auto-save rapport ──
        try:
            db_save_session(st.session_state.get("user_email",""), gnpi, tranches_input)
            db_save_etape("rapport", {"rows": rows_rapport, "prime_totale": prime_totale})
            st.toast(" Rapport sauvegardé")
        except Exception as _e:
            st.toast(f" Sauvegarde DB : {_e}")
        st.subheader(" Synthèse de tarification")
        st.dataframe(st.session_state["df_rapport"], use_container_width=True)
        c1, c2, c3 = st.columns(3)
        with c1: card("Prime totale", f"{prime_totale:,.0f} MAD", couleur="#2d8a4e", icone="")
        with c2: card("Taux global",  f"{prime_totale/gnpi:.4%}", couleur="#1a1a1a",  icone="")
        with c3: card("Tranches",     str(len(tranches_input)),   couleur="#2d8a4e",  icone="")

        # ── EXPORT PDF + EXCEL + PPTX ──
        st.markdown("###  Exports")

        # ── Comparaison de scénarios ──────────────────────────────────────────
        with st.expander("🔀 Comparaison de scénarios (côte à côte)", expanded=False):
            st.caption(
                "Comparez jusqu'à 3 jeux de paramètres pour la négociation. "
                "Renseignez les taux retenus manuellement ou chargez depuis les résultats."
            )
            n_scenarios_cmp = st.radio("Nombre de scénarios", [2, 3], horizontal=True, key="n_scen_cmp")
            cols_cmp = st.columns(n_scenarios_cmp)
            scenarios_cmp = []
            defaults_cmp = [
                ("Scénario Base (tarif technique)",   "Programme actuel"),
                ("Scénario B (concession −10%)",      "Réduction de 10% sur taux retenus"),
                ("Scénario C (marché cédant +5%)",    "Hausse de 5% côté cédante"),
            ]
            for i in range(n_scenarios_cmp):
                with cols_cmp[i]:
                    label = st.text_input(f"Nom scénario {i+1}", value=defaults_cmp[i][0], key=f"scen_name_{i}")
                    desc  = st.text_input(f"Description", value=defaults_cmp[i][1], key=f"scen_desc_{i}")
                    taux_scen = {}
                    for t in tranches_input:
                        taux_ref = next(
                            (r.get("taux_retenu", r.get("Taux retenu", 0))
                             for r in (st.session_state.get("df_rapport", pd.DataFrame()).to_dict("records")
                                       if st.session_state.get("df_rapport") is not None else [])
                             if str(r.get("Tranche","") or r.get("tranche","")) == t["nom"]), 0)
                        try: taux_ref_f = float(str(taux_ref).replace("%",""))
                        except: taux_ref_f = 0.0
                        mult = 1.0 if i == 0 else (0.90 if i == 1 else 1.05)
                        taux_scen[t["nom"]] = st.number_input(
                            f"τ {t['nom'][:12]} (%)", value=round(taux_ref_f * mult, 4),
                            step=0.01, format="%.4f", key=f"scen_t{i}_{hash(t['nom'])%9999}")
                    prime_scen = sum(gnpi * t_v / 100 for t_v in taux_scen.values())
                    st.markdown(f"""<div class="comp-card {'highlight' if i==0 else ''}">
                      <b>{label}</b><br>
                      <span style="font-size:11px;color:#5a7a8a">{desc}</span><br>
                      <div style="font-size:18px;font-weight:800;color:#0d2b3e;margin-top:8px">{prime_scen:,.0f} MAD</div>
                      <div style="font-size:12px;color:#00b5a5">{prime_scen/gnpi:.4%}</div>
                    </div>""", unsafe_allow_html=True)
                    scenarios_cmp.append({"label": label, "taux": taux_scen, "prime": prime_scen})

            if len(scenarios_cmp) >= 2:
                st.markdown("**Tableau comparatif :**")
                rows_comp_scen = []
                for t in tranches_input:
                    row_c = {"Tranche": t["nom"]}
                    for sc in scenarios_cmp:
                        row_c[sc["label"][:20]] = f"{sc['taux'].get(t['nom'],0):.4f}%"
                    rows_comp_scen.append(row_c)
                rows_comp_scen.append({"Tranche": "TOTAL PRIME",
                    **{sc["label"][:20]: f"{sc['prime']:,.0f} MAD" for sc in scenarios_cmp}})
                tableau_resultats(rows_comp_scen, "Comparaison des scénarios")

        col_pdf, col_xls, col_pptx, col_name = st.columns([1, 1, 1, 1.5])
        with col_pdf:
            if st.button(" PDF", type="primary", use_container_width=True):
                try:
                    with st.spinner("Génération PDF..."):
                        pdf_bytes = generer_pdf_rapport(
                            user_email=st.session_state.get("user_email",""),
                            gnpi_val=gnpi,
                            tranches=tranches_input,
                            resultats_bc=st.session_state.get("resultats_bc",[]),
                            resultats_sim=st.session_state.get("resultats_sim",[]),
                            taux_mkt_final=st.session_state.get("taux_mkt_final",[]),
                            df_rapport=st.session_state.get("df_rapport"),
                            prime_totale=prime_totale,
                            analyse_claude=st.session_state.get("reco_finale",""),
                            annee=2026
                        )
                    st.download_button(
                        "⬇️ Cliquer pour télécharger",
                        data=pdf_bytes,
                        file_name=f"atlantic_re_rapport_{datetime.now().strftime('%Y%m%d_%H%M')}.pdf",
                        mime="application/pdf",
                        use_container_width=True
                    )
                    st.success(" PDF prêt !")
                except Exception as e_pdf:
                    st.error(f"Erreur PDF : {e_pdf}")
        with col_xls:
            if st.button(" Excel", use_container_width=True):
                try:
                    import io as _io_xls
                    xls_buf = _io_xls.BytesIO()
                    with pd.ExcelWriter(xls_buf, engine='openpyxl') as writer:
                        st.session_state["df_rapport"].to_excel(writer, sheet_name="Rapport", index=False)
                        if st.session_state.get("resultats_bc"):
                            pd.DataFrame([{k:v for k,v in r.items() if k!="detail_annuel"}
                                           for r in st.session_state["resultats_bc"]]).to_excel(
                                writer, sheet_name="Burning Cost", index=False)
                        if st.session_state.get("resultats_sim"):
                            pd.DataFrame(st.session_state["resultats_sim"]).to_excel(
                                writer, sheet_name="Simulation", index=False)
                    st.download_button(
                        "⬇️ Télécharger .xlsx",
                        data=xls_buf.getvalue(),
                        file_name=f"atlantic_re_{datetime.now().strftime('%Y%m%d_%H%M')}.xlsx",
                        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                        use_container_width=True
                    )
                    st.success(" Excel prêt !")
                except Exception as e_xls:
                    st.error(f"Erreur Excel : {e_xls}")

        with col_pptx:
            if st.button("📑 PowerPoint", use_container_width=True):
                try:
                    with st.spinner("Génération PPTX (PptxGenJS)..."):
                        pptx_bytes = generer_pptx_rapport(
                            gnpi_val=gnpi, tranches=tranches_input,
                            resultats_bc=st.session_state.get("resultats_bc",[]),
                            resultats_sim=st.session_state.get("resultats_sim",[]),
                            taux_mkt_final=st.session_state.get("taux_mkt_final",[]),
                            df_rapport=st.session_state.get("df_rapport"),
                            prime_totale=prime_totale, annee=2026)
                    if pptx_bytes:
                        st.download_button(
                            "⬇️ Télécharger .pptx",
                            data=pptx_bytes,
                            file_name=f"atlantic_re_rapport_{datetime.now().strftime('%Y%m%d_%H%M')}.pptx",
                            mime="application/vnd.openxmlformats-officedocument.presentationml.presentation",
                            use_container_width=True)
                        st.success(" PPTX prêt — 6 slides")
                    else:
                        st.warning("PPTX non disponible (Node.js/pptxgenjs requis sur ce serveur)")
                except Exception as e_pptx:
                    st.warning(f"PPTX : {e_pptx}")

        with col_name:
            nom_session_input = st.text_input(" Nommer cette session",
                placeholder="Ex: Atlantic Re 2026 — Version finale",
                key="nom_session_input")
            if st.button("Enregistrer le nom", key="btn_save_nom"):
                try:
                    db_save_session(st.session_state.get("user_email",""), gnpi,
                                    tranches_input, nom=nom_session_input)
                    db_audit(st.session_state.get("user_email",""), "session_named",
                             nom_session_input, st.session_state.get("db_session_id"))
                    st.success(f" Session nommée : {nom_session_input}")
                except Exception as _e: st.error(str(_e))

        # ── Envoi rapport par email ───────────────────────────────────────────
        with st.expander(" Envoyer le rapport PDF par email", expanded=False):
            col_em1, col_em2 = st.columns([2, 1])
            with col_em1:
                dest_rapport_email = st.text_input(
                    "Destinataire(s)",
                    placeholder="client@compagnie.ma, manager@atlanticre.ma",
                    key="rapport_email_destinataires_tab6")
                msg_rapport_email = st.text_area("Message (optionnel)", height=68,
                    key="rapport_email_message_tab6",
                    placeholder="Bonjour, veuillez trouver ci-joint le rapport de tarification.")
            with col_em2:
                st.markdown("<div style='height:28px'></div>", unsafe_allow_html=True)
                if st.button("📨 Envoyer PDF", use_container_width=True, key="btn_email_rapport_tab6"):
                    emails_ok = _normaliser_destinataires_email(dest_rapport_email)
                    if not emails_ok:
                        st.error("Email invalide")
                    else:
                        with st.spinner("Envoi..."):
                            ok_m, msg_m = envoyer_rapport_pdf_email(
                                destinataires=emails_ok, gnpi_val=gnpi,
                                tranches=tranches_input, prime_totale_val=prime_totale,
                                message_html=f"<p>{msg_rapport_email}</p>" if msg_rapport_email.strip() else "")
                        if ok_m: st.success(f" {msg_m}")
                        else: st.error(f" {msg_m}")
                # Webhook Slack/Teams
                wh_res = st.session_state.get("webhook_rapport_sent")
                if st.button("📢 Notifier Slack/Teams", use_container_width=True, key="btn_wh_rapport"):
                    wh_results = envoyer_webhook_notification(
                        f"Rapport finalisé — {st.session_state.get('user_email','')}",
                        f"Prime : {prime_totale:,.0f} MAD | Taux : {prime_totale/gnpi:.4%} | GNPI : {gnpi:,.0f} MAD",
                        niveau="rapport_final")
                    if wh_results:
                        for svc, ok_w, msg_w in wh_results:
                            (st.success if ok_w else st.error)(f"{svc} : {msg_w}")
                    else:
                        st.info("Configurez SLACK_WEBHOOK_URL ou TEAMS_WEBHOOK_URL dans les Secrets")
                    st.session_state["webhook_rapport_sent"] = True

        st.divider()
        guide_prompt("Rapport Final",
            ["Négociation avec Partner Re / Munich Re", "Comité de tarification 15 janvier 2026", "Objectif prime < 14M MAD"],
            ["Justifier chaque taux retenu vs alternatives", "Comparer avec taux N-1 fournis", "Conclure sur positionnement vs marché"],
            ["Taux N-1 : R&C=3.1%, CatL1=1.2%, CatL2=0.8%", "Cotation Partner Re : R&C=2.30%", "Chargement majeurs = 0.05%"],
            ["Synthèse exécutive 5 lignes max", "Tableau récapitulatif final obligatoire", "Verdict : ACCEPTER / NEGOCIER / REFUSER"])

        st.markdown("###  Rapport Claude — Analyse finale")
        ctx_r, inst_r, inp_r, out_r = prompt_inputs(
            key_prefix="rapport",
            placeholder_contexte="Ex: Négociation réassureur XYZ, objectif prime < 14M MAD...",
            placeholder_instructions="Ex: Justifier chaque taux, comparer avec N-1...",
            placeholder_input="Ex: Taux N-1 : R&C=3.1%, CatL1=1.2%, CatL2=0.8%",
            placeholder_output="Ex: Rapport 1 page max, tableau synthèse obligatoire")

        if api_key and st.button(" Générer le rapport Claude", type="primary"):
            prompt = build_prompt(
                role="Expert senior tarification reassurance non-proportionnelle, specialiste automobile marches emergents.",
                task="1. SYNTHESE EXECUTIVE (5 lignes max)\n2. ANALYSE PAR TRANCHE (BC/Sim/Marche -> Verdict)\n3. COHERENCE INTER-METHODES\n4. ANOMALIES\n5. TABLEAU FINAL\n6. RECOMMANDATION GLOBALE",
                data=f"Rapport : {json.dumps(rows_rapport, indent=2)}\nBC : {json.dumps([{k:v for k,v in r.items() if k!='detail_annuel'} for r in st.session_state['resultats_bc']], indent=2)}\nSim : {json.dumps(st.session_state['resultats_sim'], indent=2)}\nGNPI : {gnpi:,} MAD | Prime : {prime_totale:,.0f} MAD | Taux global : {prime_totale/gnpi:.4%}",
                contexte=ctx_r, instructions=inst_r, input_data=inp_r, output_instructions=out_r,
                contexte_global=st.session_state.get("instructions_globales",""),
                contraintes="- Ne jamais recommander taux < taux pur\n- BC=0 cat = normal\n- Mentionner incertitudes et limites")
            claude_stream(api_key, prompt, max_tokens=2500, session_key="reco_finale")

    if "reco_finale" in st.session_state:
        st.divider()
        st.subheader(" Rapport Claude")
        st.markdown(st.session_state["reco_finale"])

    # ── Optimisation A/B/C ──
    if (st.session_state.get("resultats_sim") and
        st.session_state.get("resultats_bc")  and
        st.session_state.get("df_rapport") is not None):
        if st.button(" Générer les variantes de programme optimal (A/B/C)", type="primary", key="btn_optim"):
            with st.spinner("Optimisation en cours..."):
                variantes = optimiser_programme_variantes(
                    tranches_input, gnpi,
                    st.session_state["resultats_sim"],
                    st.session_state["resultats_bc"],
                    st.session_state.get("taux_mkt_final", []))
                st.session_state["variantes_optimisation"] = variantes
        if "variantes_optimisation" in st.session_state:
            afficher_variantes_optimisation(
                st.session_state["variantes_optimisation"],
                gnpi, tranches_input)

    # ── Panneau Audit Managers ──
    if (st.session_state.get("resultats_bc") and
        st.session_state.get("resultats_sim") and
        st.session_state.get("df_rapport") is not None):
        afficher_panneau_audit(
            tranches_input,
            st.session_state["resultats_bc"],
            st.session_state["resultats_sim"],
            st.session_state.get("taux_mkt_final", []),
            st.session_state["df_rapport"],
            st.session_state.get("prime_totale", 0),
            gnpi)



# ═══════════════════════════════════════════════════════════════════════════════
# TAB AGENT + TAB FULL + TAB HIST + TAB ADMIN
# ═══════════════════════════════════════════════════════════════════════════════
with tab_agent:
    section_header("Agent de Tarification Autonome", "Calcul actuariel complet — BC · Simulation · Courbe de référence marché · Optimisation du programme", "")

    st.markdown("""<div style="background:linear-gradient(135deg,#0d2b1a,#1a1a1a);border-radius:12px;
        padding:18px 24px;margin-bottom:16px;border:1px solid rgba(45,138,78,0.4)">
        <div style="color:#2d8a4e;font-weight:700;font-size:15px;margin-bottom:8px">
            Séquence de tarification
        </div>
        <div style="color:#ccc;font-size:13px;line-height:1.9">
            Validation des paramètres &rarr;
            Burning Cost (formule &sigma;) &rarr;
            Simulation Pareto/Poisson &rarr;
            Contrôles de cohérence &rarr;
            Courbe de référence marché (tranches cat) &rarr;
            Rapport de tarification &rarr;
            Optimisation du programme (5 variantes)
        </div></div>""", unsafe_allow_html=True)

    # Prérequis
    prereqs = {
        "Programme"  : True,
        "Triangle"   : "df_proj" in st.session_state,
        "Paramètres" : "alpha_est" in st.session_state,
    }
    c1, c2, c3 = st.columns(3)
    for col, (nom_p, ok) in zip([c1,c2,c3], prereqs.items()):
        col.markdown(f"""<div style="background:{'rgba(45,138,78,0.12)' if ok else 'rgba(239,68,68,0.08)'};
            border:1px solid {'#2d8a4e' if ok else '#ef4444'};border-radius:10px;
            padding:12px;text-align:center">
            <div style="font-size:14px;font-weight:700;color:{'#2d8a4e' if ok else '#ef4444'}">
                {'Prêt' if ok else 'Requis'}</div>
            <div style="font-size:11px;color:#aaa;margin-top:2px">{nom_p}</div>
            </div>""", unsafe_allow_html=True)

    st.markdown("")
    c_left, c_right = st.columns([2, 1])
    with c_left:
        n_sim_py = st.number_input("Nombre de simulations", value=10000, step=5000, min_value=1000, key="nsim_py")
    with c_right:
        st.markdown("<div style='height:28px'></div>", unsafe_allow_html=True)
        lancer_py = st.button("Lancer la tarification", type="primary", use_container_width=True,
                              disabled="df_proj" not in st.session_state)

    if "df_proj" not in st.session_state:
        st.info("Transformez d'abord le triangle dans l'onglet Données & Triangle")

    elif lancer_py:
        # Notification email de début
        notifier_consultation(
            st.session_state.get("user_email",""),
            "Agent Python — Tarification lancée",
            f"GNPI={gnpi:,.0f} MAD · {len(tranches_input)} tranches")
        with st.spinner(" Pipeline en cours..."):
            prog_bar = st.progress(0, text="Initialisation...")

            agent = AgentActuarielPython(
                tranches           = tranches_input,
                gnpi               = gnpi,
                df_proj            = st.session_state["df_proj"],
                coeffs             = st.session_state.get("coeffs", np.array([1.0])),
                alpha_est          = st.session_state.get("alpha_est", 1.5),
                lambda_est         = st.session_state.get("lambda_est", 5.0),
                seuil_est          = st.session_state.get("seuil_est", 1_600_000),
                Pm_proxy           = st.session_state.get("Pm_proxy", 0),
                chargement_majeurs = st.session_state.get("chargement_majeurs", 0.0),
                df_mkt_clean       = st.session_state.get("df_mkt_clean"),
            )

            prog_bar.progress(10, "Validation paramètres...")
            agent.etape_0_validation()
            prog_bar.progress(25, "Burning Cost...")
            agent.etape_1_burning_cost()
            prog_bar.progress(50, "Simulation...")
            agent.etape_2_simulation(int(n_sim_py))
            prog_bar.progress(65, "Contrôles...")
            agent.etape_3_controles()
            prog_bar.progress(75, "Courbe de référence marché...")
            agent.etape_4_market_curve()
            prog_bar.progress(90, "Rapport...")
            agent.etape_5_rapport()
            prog_bar.progress(95, "Optimisation du programme...")
            agent.variantes = agent.etape_6_optimisation()
            rapport_txt = agent.generer_rapport_texte()
            prog_bar.progress(100, "Terminé.")

            # ── Moteurs agentiques V2 ──
            contexte_ag = {
                "has_triangle": "df_proj" in st.session_state,
                "has_market":   st.session_state.get("df_mkt_clean") is not None,
                "n_rows":       len(agent.df_proj) if agent.df_proj is not None else 0,
            }
            plan_ag     = AgentRaisonnement().planifier(contexte_ag)
            critique_ag = AgentCritique().auditer(agent.tranches, agent.gnpi,
                              agent.resultats_bc, agent.resultats_sim,
                              agent.resultats_mkt, agent.rapport_rows)
            # Remonter les alertes critique dans l'agent
            for a in critique_ag.get("alertes",[]):
                agent._alerte(a.get("niveau","INFO"), f"{a.get('tranche','')}: {a.get('message','')}")
            ml_ag       = AgentML().entrainer_depuis_df_proj(agent.df_proj)
            memoire_ag  = AgentMemoireMetier().benchmark(
                              user_email=st.session_state.get("user_email",""),
                              tranches=agent.tranches, rapport_rows=agent.rapport_rows,
                              gnpi=agent.gnpi,
                              current_session_id=st.session_state.get("db_session_id"))
            challenge_ag = AgentChallenger().challenger(
                              agent.tranches, agent.resultats_bc, agent.resultats_sim,
                              agent.resultats_mkt, agent.rapport_rows)
            opt_ag       = AgentOptimisationProgramme(agent.gnpi).explorer(
                              agent.tranches, agent.resultats_bc, agent.resultats_sim,
                              agent.resultats_mkt, objectif="equilibre", top_n=8)

            # Stocker dans session_state
            st.session_state["resultats_bc"]        = agent.resultats_bc
            st.session_state["resultats_sim"]        = agent.resultats_sim
            st.session_state["taux_mkt_final"]       = agent.resultats_mkt
            st.session_state["df_rapport"]           = pd.DataFrame(agent.rapport_rows)
            st.session_state["prime_totale"]         = agent.prime_totale
            st.session_state["agent_py_log"]         = agent.log
            st.session_state["agent_py_anomalies"]   = agent.anomalies
            st.session_state["agent_py_rapport"]     = rapport_txt
            st.session_state["agent_py_variantes"]          = agent.variantes
            st.session_state["agent_plan_agentique"]         = plan_ag
            st.session_state["agent_critique"]               = critique_ag
            st.session_state["agent_ml"]                     = ml_ag
            st.session_state["agent_memoire_metier"]         = memoire_ag
            st.session_state["agent_challenger"]             = challenge_ag
            st.session_state["agent_optimisation_avancee"]   = opt_ag
            st.session_state["agent_py_done"]                = True

            # Auto-save
            try:
                db_save_session(st.session_state.get("user_email",""), gnpi, tranches_input)
                db_save_etape("bc",  [{k:v for k,v in r.items() if k!="detail_annuel"} for r in agent.resultats_bc])
                db_save_etape("sim", agent.resultats_sim)
                if agent.resultats_mkt:
                    db_save_etape("mkt", {"resultats_mkt":[], "taux_mkt_final": agent.resultats_mkt})
                db_save_etape("rapport", {"rows": agent.rapport_rows, "prime_totale": agent.prime_totale})
            except: pass

    # ── Affichage des résultats ──
    if st.session_state.get("agent_py_done"):

        # ── Moteurs agentiques V2 ──
        if any(st.session_state.get(k) for k in ["agent_plan_agentique","agent_critique","agent_ml","agent_memoire_metier","agent_challenger","agent_optimisation_avancee"]):
            with st.expander("Raisonnement · Critique · Mémoire · Challenger · ML · Optimisation avancée", expanded=True):
                afficher_plan_agentique(st.session_state.get("agent_plan_agentique"))
                afficher_critique_agentique(st.session_state.get("agent_critique"))
                afficher_memoire_metier(st.session_state.get("agent_memoire_metier"))
                afficher_challenger(st.session_state.get("agent_challenger"))
                afficher_ml_agentique(st.session_state.get("agent_ml"))
                afficher_optimisation_avancee(st.session_state.get("agent_optimisation_avancee"))

        # ── Alertes
        anomalies = st.session_state.get("agent_py_anomalies", [])
        if anomalies:
            st.markdown("#### Points d'attention")
            for a in anomalies:
                color = {"CRITIQUE":"#ef4444","WARN":"#f59e0b","INFO":"#3b82f6"}.get(a["niveau"],"#888")
                st.markdown(f"""<div style="border-left:3px solid {color};padding:8px 14px;
                    margin:3px 0;font-size:13px;background:rgba(0,0,0,0.03)">
                    [{a['niveau']}] {a['message']}</div>""", unsafe_allow_html=True)

        # ── Taux par méthode ──
        if st.session_state.get("resultats_bc"):
            c_bc, c_sim = st.columns(2)
            with c_bc:
                st.markdown("#### Burning Cost")
                tableau_resultats([{
                    "Tranche": r["tranche"],
                    "Années non nulles": r.get("n_ann_nonzero",0),
                    "Taux pur": f"{r['taux_pur']:.4%}",
                    "Ecart-type": f"{r.get('sigma_hist',0):.4%}",
                    "Taux technique": f"{r['taux_technique']:.4%}",
                } for r in st.session_state["resultats_bc"]])
            with c_sim:
                st.markdown("#### Simulation")
                tableau_resultats([{
                    "Tranche": r["tranche"],
                    "Taux pur": f"{r['taux_pur']:.4%}",
                    "Taux technique": f"{r['taux_technique']:.4%}",
                    "Impact rec.": f"{r.get('impact_rec',0):.4%}",
                } for r in st.session_state["resultats_sim"]])

        # ── Rapport de tarification ──
        if st.session_state.get("df_rapport") is not None:
            st.markdown("#### Tarification retenue")
            def _g(row, *keys):
                for k in keys:
                    if k in row: return row[k]
                return ""
            tableau_resultats([{
                "Tranche": _g(row,"tranche","Tranche"),
                "BC": f"{float(_g(row,'taux_bc',0) or 0):.4%}",
                "Simulation": f"{float(_g(row,'taux_sim',0) or 0):.4%}",
                "Marché": f"{float(_g(row,'taux_mkt',0) or 0):.4%}",
                "Taux retenu": f"{float(_g(row,'taux_retenu',0) or 0):.4%}",
                "Prime (MAD)": f"{float(_g(row,'prime_MAD',0) or 0):,.0f}",
                "Sélection": _g(row,"methode","Méthode"),
            } for row in st.session_state["df_rapport"].to_dict("records")])
            pt = st.session_state.get("prime_totale",0)
            c1,c2 = st.columns(2)
            with c1: card("Prime totale", f"{pt:,.0f} MAD", icone="")
            with c2: card("Taux global",  f"{pt/gnpi:.4%}", couleur="#1a1a1a", icone="")

        # ── 5 VARIANTES DE PROGRAMME OPTIMAL ──
        variantes = st.session_state.get("agent_py_variantes", {})
        if variantes:
            st.markdown("---")
            st.markdown("#### Optimisation du programme — 5 variantes (perspective leader)")
            st.caption("En tant que leader, ces variantes structurent la proposition de tarification et la marge de négociation.")

            cols = st.columns(len(variantes))
            colors_v = ["#1a1a1a","#2d8a4e","#3b82f6","#f59e0b","#7c3aed"]
            for col, (key, v), color in zip(cols, variantes.items(), colors_v):
                delta = v["ecart_ref_pts"]
                delta_str = f"{delta:+.2f} pts" if key != "ref" else "référence"
                with col:
                    st.markdown(f"""<div style="border-top:3px solid {color};background:white;
                        border-radius:0 0 8px 8px;padding:14px 12px;
                        box-shadow:0 2px 8px rgba(0,0,0,0.06);margin-bottom:8px">
                        <div style="font-size:13px;font-weight:700;color:{color}">{v['label']}</div>
                        <div style="font-size:11px;color:#555;margin:4px 0">{v['angle']}</div>
                        <div style="font-size:18px;font-weight:700;color:#1a1a1a;margin:8px 0">
                            {v['taux_global']:.4%}</div>
                        <div style="font-size:11px;color:#888">{v['prime']:,.0f} MAD</div>
                        <div style="font-size:11px;color:{color};font-weight:600;margin-top:4px">
                            {delta_str}</div>
                        </div>""", unsafe_allow_html=True)

            # Tableau comparatif détaillé
            with st.expander("Détail des 5 variantes — paramètres et justifications", expanded=False):
                rows_v = []
                for key, v in variantes.items():
                    for t in v["tranches"]:
                        rows_v.append({
                            "Variante": v["label"],
                            "Tranche": t["nom"],
                            "Priorité (MAD)": f"{t['priorite']:,.0f}",
                            "Portée (MAD)": f"{t['portee']:,.0f}",
                            "Reconst.": t.get("nb_reconstitutions","—"),
                            "AAL": f"{t['AAL']:,.0f}" if t.get("AAL") else "—",
                            "AAD": f"{t['AAD']:,.0f}" if t.get("AAD") else "—",
                            "Taux": f"{t.get('_taux',0):.4%}",
                        })
                tableau_resultats(rows_v)

                st.markdown("**Justifications actuarielles :**")
                for key, v in variantes.items():
                    st.markdown(f"**{v['label']}** — {v['description']}")

        # ── Journal des décisions ──
        with st.expander("Journal des décisions actuarielles", expanded=False):
            log_data = [{"Etape": e["etape"], "Décision": e["decision"],
                         "Détail": e["detail"]} for e in st.session_state.get("agent_py_log",[])]
            if log_data: tableau_resultats(log_data)

        # ── Rapport texte ──
        with st.expander("Rapport complet (format texte)", expanded=False):
            st.code(st.session_state.get("agent_py_rapport",""), language="text")

        st.markdown("")
        if st.button("Nouvelle tarification", key="relancer_py"):
            for k in ["agent_py_done","agent_py_log","agent_py_anomalies",
                      "agent_py_rapport","agent_py_variantes"]:
                st.session_state.pop(k, None)
            st.rerun()

    # ── Laboratoire ML (toujours accessible si df_proj disponible) ──
    _labo_display_section()

    # ── Ressources actuarielles ──
    with st.expander("🌐 Ressources actuarielles — Sites web & publications", expanded=False):
        afficher_ressources_actuarielles()

    # ── Intégration R ──
    with st.expander(" Intégration R Studio — Scripts de tarification", expanded=False):
        afficher_integration_r()

    # ── Notification email manuelle ──
    st.markdown("---")
    c_notif1, c_notif2 = st.columns([3, 1])
    with c_notif1:
        notif_msg = st.text_input("Message à envoyer à hervepagnangde@gmail.com", key="notif_msg",
            placeholder="Ex: Session terminée — taux global 3.24%, prime 5.9M MAD")
    with c_notif2:
        st.markdown("<div style='height:28px'></div>", unsafe_allow_html=True)
        if st.button(" Envoyer notification", key="btn_notif", use_container_width=True):
            if notif_msg.strip():
                user = st.session_state.get("user_email","Agent")
                ok, msg = envoyer_notification_email(
                    f"Message de {user} — Atlantic Re IA",
                    f"<p><b>De :</b> {user}</p><p><b>Message :</b> {notif_msg}</p>",
                    "hervepagnangde@gmail.com")
                if ok: st.success(" Email envoyé")
                else:   st.warning(f" {msg}")


with tab_full:
    section_header("Agent Complet LLM", "Fichiers bruts → Rapport final — Raisonnement LLM Claude (API requise)", "")

    st.markdown("""
    <div style="background:linear-gradient(135deg,#0d0d1a,#1a1a1a);border-radius:12px;
        padding:20px 24px;margin-bottom:24px;border:1px solid rgba(59,130,246,0.4)">
        <div style="color:#3b82f6;font-weight:700;font-size:15px;margin-bottom:10px">
             Agent Complet — LLM Claude (API Anthropic requise)
        </div>
        <div style="display:flex;gap:32px;flex-wrap:wrap">
            <div style="color:#ccc;font-size:13px;line-height:2">
                 Uploade les fichiers bruts ici<br>
                 Claude parse le triangle seul<br>
                 Claude décide branche longue/courte<br>
                 Claude calibre alpha et lambda
            </div>
            <div style="color:#ccc;font-size:13px;line-height:2">
                 Claude lance BC + Simulation + Courbe de référence marché<br>
                 Claude détecte et corrige les anomalies<br>
                 Claude choisit la méthode par tranche<br>
                 Claude produit le rapport final
            </div>
        </div>
        <div style="color:#888;font-size:12px;margin-top:10px">
            Seul un <b style="color:#f59e0b">seuil d'alerte critique</b> interrompt l'agent pour validation humaine.
        </div>
    </div>
    """, unsafe_allow_html=True)

    # ── Uploads directs ──
    st.markdown("###  Fichiers sources")
    c1, c2, c3, c4 = st.columns(4)
    with c1: f3_tri = st.file_uploader("Triangle développement", type=["xlsx","csv"], key="f3_tri")
    with c2: f3_gnp = st.file_uploader("Base GNPIs",             type=["xlsx","csv"], key="f3_gnp")
    with c3: f3_idx = st.file_uploader("Table indices",          type=["xlsx","csv"], key="f3_idx")
    with c4: f3_mkt = st.file_uploader("Données marché",         type=["xlsx","csv"], key="f3_mkt")

    # ── Config minimale ──
    st.markdown("###  Configuration minimale")
    c1, c2, c3 = st.columns(3)
    with c1: gnpi3      = st.number_input("GNPI (MAD)", value=183_000_000, step=1_000_000, key="gnpi3")
    with c2: annee3     = st.number_input("Année de cotation", value=2026, step=1, key="annee3")
    with c3: retour3    = st.number_input("Période de retour sinistres majeurs (ans)", value=20, step=5, key="retour3")

    # ── Contexte pour l'agent ──
    contexte3 = st.text_area(" Contexte pour l'agent (optionnel)",
        placeholder="Ex: Portefeuille automobile Maroc 2026, GNPI en hausse +8%, 3 tranches : Risk&Cat 13M xs 2M, Cat L1 10M xs 15M, Cat L2 15M xs 25M. Objectif prime < 14M MAD. Réassureur cible : Partner Re.",
        height=90, key="contexte3")

    seuil_alerte = st.slider(
        " Seuil d'alerte critique (interrompt l'agent)",
        min_value=10, max_value=60, value=35, step=5,
        help="Si écart BC/Simulation > ce seuil sur tranche travaillante → agent demande validation avant de continuer",
        key="seuil_alerte3")

    fichiers_ok = all([f3_tri, f3_gnp, f3_idx, f3_mkt, api_key])

    if not api_key:
        st.warning(" Clé API requise dans la sidebar")
    elif not fichiers_ok:
        manquants3 = [n for n, f in [("Triangle",f3_tri),("GNPIs",f3_gnp),("Indices",f3_idx),("Marché",f3_mkt)] if not f]
        st.warning(f" Fichiers manquants : {', '.join(manquants3)}")

    lancer3 = st.button(" Lancer l'Agent Complet", type="primary",
                        use_container_width=True, disabled=not fichiers_ok,
                        key="lancer3")

    # ════════════════════════════════
    # OUTILS PHASE 3 (étend phase 2)
    # ════════════════════════════════

    TOOLS_FULL = [
        {
            "name": "analyser_et_transformer_triangle",
            "description": """Parse et transforme le triangle de liquidation brut.
Détecte automatiquement le type de branche (long/court), applique As-If, stabilisation, Chain Ladder.
Estime alpha (MLE Hill), lambda Poisson, seuil p80×D, Pm proxy.
Retourne les statistiques clés et les paramètres calibrés.""",
            "input_schema": {
                "type": "object",
                "properties": {
                    "type_branche": {
                        "type": "string",
                        "enum": ["long", "court"],
                        "description": "Branche longue (As-If+Stab+CL) ou courte (As-If seul)"
                    },
                    "seuil_stabilisation": {
                        "type": "number",
                        "description": "Seuil de déclenchement clause stabilisation (0.0 = toujours, 0.1 = 10%)"
                    },
                    "pct_seuil_pareto": {
                        "type": "number",
                        "description": "Percentile pour le seuil Pareto (0.80 = p80 × D)"
                    },
                    "justification": {"type": "string"}
                },
                "required": ["type_branche", "seuil_stabilisation", "pct_seuil_pareto", "justification"]
            }
        },
        {
            "name": "definir_programme_tranches",
            "description": """Définit ou ajuste le programme de réassurance (tranches, conditions, frais).
Claude peut proposer les tranches basées sur le contexte fourni ou ajuster les valeurs par défaut.""",
            "input_schema": {
                "type": "object",
                "properties": {
                    "tranches": {
                        "type": "array",
                        "description": "Liste des tranches avec leurs paramètres",
                        "items": {
                            "type": "object",
                            "properties": {
                                "nom"              : {"type": "string"},
                                "type"             : {"type": "string", "enum": ["travaillante","cat","non_travaillante"]},
                                "priorite"         : {"type": "number"},
                                "portee"           : {"type": "number"},
                                "nb_reconstitutions": {"type": "integer"},
                                "taux_reconstitution": {"type": "number"},
                                "brokage_pct"      : {"type": "number"},
                                "frais_pct"        : {"type": "number"},
                                "marge_pct"        : {"type": "number"}
                            }
                        }
                    },
                    "justification": {"type": "string"}
                },
                "required": ["tranches", "justification"]
            }
        },
        {
            "name": "calculer_burning_cost_complet",
            "description": "Calcule le BC sur les données transformées. Identique à l'outil Phase 2.",
            "input_schema": {
                "type": "object",
                "properties": {"justification": {"type": "string"}},
                "required": ["justification"]
            }
        },
        {
            "name": "lancer_simulation_complete",
            "description": "Lance la simulation avec les paramètres calibrés automatiquement.",
            "input_schema": {
                "type": "object",
                "properties": {
                    "alpha"         : {"type": "number"},
                    "lambda_"       : {"type": "number"},
                    "seuil"         : {"type": "number"},
                    "n_sim"         : {"type": "integer"},
                    "justification" : {"type": "string"}
                },
                "required": ["alpha", "lambda_", "seuil", "n_sim", "justification"]
            }
        },
        {
            "name": "construire_market_curve_complete",
            "description": "Construit la market curve sur les données uploadées.",
            "input_schema": {
                "type": "object",
                "properties": {
                    "rol_min"       : {"type": "number"},
                    "rol_max"       : {"type": "number"},
                    "r2_min"        : {"type": "number"},
                    "tolerance"     : {"type": "number"},
                    "filtre_branche": {"type": "string", "description": "Mot-clé colonne INT_BUSINESS (ex: EVENEMENT)"},
                    "justification" : {"type": "string"}
                },
                "required": ["rol_min", "rol_max", "r2_min", "tolerance", "filtre_branche", "justification"]
            }
        },
        {
            "name": "demander_validation_humaine",
            "description": """Interrompt l'agent pour demander une validation humaine sur un point critique.
À utiliser UNIQUEMENT si : anomalie grave, écart très élevé, paramètre hors norme, données suspectes.""",
            "input_schema": {
                "type": "object",
                "properties": {
                    "niveau"   : {"type": "string", "enum": ["avertissement", "critique", "bloquant"]},
                    "message"  : {"type": "string", "description": "Message clair pour l'humain"},
                    "question" : {"type": "string", "description": "Question précise à poser à l'humain"},
                    "choix"    : {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Options proposées à l'humain"
                    }
                },
                "required": ["niveau", "message", "question", "choix"]
            }
        },
        {
            "name": "generer_rapport_final_complet",
            "description": "Génère le rapport final complet avec recommandations.",
            "input_schema": {
                "type": "object",
                "properties": {
                    "methode_travaillante": {"type": "string", "enum": ["bc","simulation","moyenne_bc_sim"]},
                    "methode_cat"         : {"type": "string", "enum": ["simulation","market_curve","max_sim_mkt"]},
                    "justification"       : {"type": "string"}
                },
                "required": ["methode_travaillante", "methode_cat", "justification"]
            }
        },
        {
            "name": "evaluer_pertinence_methodes",
            "description": """Analyse la pertinence statistique de chaque méthode de tarification
(BC, Simulation Pareto, Courbe de référence marché) pour chaque tranche du programme.
Utilise les résultats des tests KS/AD, la qualité du fit des distributions,
la suffisance des données historiques, et la cohérence entre méthodes.
Retourne un diagnostic structuré avec recommandation par tranche.
A appeler AVANT de générer le rapport final pour fonder le choix de méthode
sur des critères statistiques objectifs, pas seulement des règles fixes.""",
            "input_schema": {
                "type": "object",
                "properties": {
                    "inclure_tests_ks_ad":    {"type": "boolean", "description": "Inclure les résultats KS/AD"},
                    "inclure_stabilite_hill": {"type": "boolean", "description": "Inclure l'analyse Hill"},
                    "justification":          {"type": "string"}
                },
                "required": ["justification"]
            }
        },
        {
            "name": "rechercher_web_actuariel",
            "description": """Recherche des informations actuarielles sur le web.
Utiliser pour : taux de marché de référence, publications CAS/ASTIN récentes,
données de sinistralité automobile Maroc/Afrique, normes réglementaires DAPS,
benchmarks de tarification réassurance non-proportionnelle.
Sites prioritaires : swissre.com, munichre.com, casact.org, astin.org, actuaries.org.""",
            "input_schema": {
                "type": "object",
                "properties": {
                    "requete"      : {"type": "string", "description": "Termes de recherche (en français ou anglais)"},
                    "type_recherche": {
                        "type": "string",
                        "enum": ["taux_marche", "publication_actuarielle", "reglementation", "sinistralite", "methode"],
                        "description": "Type d'information recherchée"
                    },
                    "justification": {"type": "string"}
                },
                "required": ["requete", "type_recherche", "justification"]
            }
        },
        {
            "name": "envoyer_notification_agent",
            "description": """Envoie une notification email à hervepagnangde@gmail.com.
Utiliser : à la fin de chaque session de tarification complète, ou en cas d'anomalie critique.
Format : résumé des résultats clés (prime totale, taux global, anomalies détectées).""",
            "input_schema": {
                "type": "object",
                "properties": {
                    "sujet"       : {"type": "string", "description": "Objet de l'email"},
                    "contenu"     : {"type": "string", "description": "Corps du message (HTML autorisé)"},
                    "niveau"      : {
                        "type": "string",
                        "enum": ["info", "alerte", "rapport_final"],
                        "description": "Niveau de la notification"
                    },
                    "justification": {"type": "string"}
                },
                "required": ["sujet", "contenu", "niveau", "justification"]
            }
        },
        {
            "name": "consulter_ressource_actuarielle",
            "description": """Référence et cite une ressource actuarielle de la bibliothèque interne.
Retourne la liste des sites/publications disponibles par catégorie.
Catégories : réassurance, actuariat, cours, finance, Maroc.""",
            "input_schema": {
                "type": "object",
                "properties": {
                    "categorie"   : {
                        "type": "string",
                        "enum": ["Réassurance & Marché", "Actuariat & Standards", "Cours & Formations", "Finance & Économie"],
                        "description": "Catégorie de ressource"
                    },
                    "justification": {"type": "string"}
                },
                "required": ["categorie", "justification"]
            }
        },
    ]

    # ── Exécuteur evaluer_pertinence_methodes ──
    def _executer_evaluer_methodes(inclure_ks_ad=True, inclure_hill=True):
        """Analyse statistique de la pertinence de chaque méthode par tranche."""
        from scipy import stats as _sp_stats
        diag = {}
        has_bc   = "resultats_bc"  in st.session_state
        has_sim  = "resultats_sim" in st.session_state
        has_mkt  = bool(st.session_state.get("taux_mkt_final"))
        has_dist = "dist_fit_results" in st.session_state
        diag["disponibilite"] = {"bc":has_bc,"simulation":has_sim,"market_curve":has_mkt,"dist_fit":has_dist}
        dist_fit = st.session_state.get("dist_fit_results", {})
        sev_fits = dist_fit.get("severity", {})
        best_sev = None; best_pval = 0
        diag["distribution_fit"] = {}
        for nom_d, f in sev_fits.items():
            pval = f.get("pval",0)
            diag["distribution_fit"][nom_d] = {"ks":round(f.get("ks",1),4),"pval":round(pval,4),
                "adequation":"bon" if pval>0.05 else "acceptable" if pval>0.01 else "rejete"}
            if pval > best_pval: best_pval=pval; best_sev=nom_d
        diag["distribution_recommandee"] = best_sev or "Pareto"
        diag["n_exceedances"]  = dist_fit.get("n_exceedances",0)
        diag["overdispersion"] = dist_fit.get("overdispersion_ratio",1.0)
        bc_list  = st.session_state.get("resultats_bc", [])
        sim_list = st.session_state.get("resultats_sim",[])
        mkt_list = st.session_state.get("taux_mkt_final",[])
        tranches_analyse = []
        for t in tranches_input:
            nom_t = t["nom"]
            bc_r  = next((r for r in bc_list  if r["tranche"]==nom_t),{})
            sim_r = next((r for r in sim_list if r["tranche"]==nom_t),{})
            mkt_r = next((r for r in mkt_list if r["tranche"]==nom_t),{})
            bc_tt=bc_r.get("taux_technique",0); sim_tt=sim_r.get("taux_technique",0)
            mkt_tt=mkt_r.get("taux",0) if t["type"]!="travaillante" else 0
            n_nz=bc_r.get("n_ann_nonzero",0)
            ecart=abs(bc_tt-sim_tt)/bc_tt*100 if bc_tt>0 else 999
            bc_ok=n_nz>=5 and bc_tt>0; sim_ok=best_pval>0.01 and sim_tt>0
            mkt_ok=has_mkt and mkt_tt>0 and t["type"]!="travaillante"
            if t["type"]=="travaillante":
                if bc_ok and sim_ok and ecart<30: rec="max(BC,Simulation)"; raison=f"Coherent BC/Sim ({ecart:.0f}%)"
                elif bc_ok and sim_ok:            rec="Simulation (ecart eleve)"; raison=f"Ecart={ecart:.0f}%>30% — Sim prioritaire"
                elif bc_ok:                       rec="Burning Cost"; raison=f"{n_nz} ans — dist. faible"
                elif sim_ok:                      rec="Simulation"; raison=f"BC<5 ans non nuls"
                else:                             rec="Jugement expert"; raison="Donnees insuffisantes"
            else:
                if mkt_ok and sim_ok:  rec="max(Simulation,MarketCurve)"; raison="Cat: deux methodes disponibles"
                elif sim_ok:           rec="Simulation"; raison="Courbe de référence marché absente/faible"
                elif mkt_ok:           rec="Courbe de référence marché"; raison="Historique cat limite"
                else:                  rec="Jugement expert"; raison="Donnees insuffisantes"
            tranches_analyse.append({"tranche":nom_t,"type":t["type"],"n_ann_bc":n_nz,
                "bc_fiable":bc_ok,"sim_fiable":sim_ok,"mkt_fiable":mkt_ok,
                "taux_bc":round(bc_tt,6),"taux_sim":round(sim_tt,6),"taux_mkt":round(mkt_tt,6),
                "ecart_bc_sim_pct":round(ecart,1),"methode_recommandee":rec,"raison":raison})
        diag["analyse_par_tranche"] = tranches_analyse
        diag["synthese"] = {
            "distribution_severite": best_sev or "Pareto",
            "adequation": "bonne" if best_pval>0.05 else "acceptable" if best_pval>0.01 else "faible",
            "frequence_modele": "BN" if diag["overdispersion"]>1.2 else "Poisson",
            "nb_bc_fiable":  sum(1 for t in tranches_analyse if t["bc_fiable"]),
            "nb_sim_fiable": sum(1 for t in tranches_analyse if t["sim_fiable"]),
            "nb_mkt_fiable": sum(1 for t in tranches_analyse if t["mkt_fiable"]),
        }
        return _json_safe(diag)

    # ── Exécuteur triangle complet ──
    def _executer_transformer_triangle_complet(type_branche, seuil_stab, pct_seuil_p,
                                                f_tri, f_gnp, f_idx, gnpi_val, annee_cot):
        try:
            import io as _io
            is_long_p3 = (type_branche == "long")
            # ── Seek & read files (Streamlit UploadedFile needs seek before each read) ──
            f_gnp.seek(0)
            df_gnpis_p3 = pd.read_excel(_io.BytesIO(f_gnp.read())) if f_gnp.name.endswith('xlsx') else pd.read_csv(f_gnp)
            f_idx.seek(0)
            df_idx_p3   = pd.read_excel(_io.BytesIO(f_idx.read())) if f_idx.name.endswith('xlsx') else pd.read_csv(f_idx)
            df_gnpis_p3.columns = [str(c).strip() for c in df_gnpis_p3.columns]
            df_idx_p3.columns   = [str(c).strip() for c in df_idx_p3.columns]

            df_idx_p3['Annee'] = pd.to_numeric(
                df_idx_p3['Annee'].astype(str).str.strip().str.replace('.0','',regex=False), errors='coerce')
            df_idx_p3['Coefficients'] = pd.to_numeric(
                df_idx_p3['Coefficients'].astype(str).str.replace(',','.',regex=False).str.replace(' ','',regex=False), errors='coerce')
            df_idx_p3 = df_idx_p3.dropna(subset=['Annee','Coefficients'])
            df_idx_p3['Annee'] = df_idx_p3['Annee'].astype(int)
            df_idx_p3 = df_idx_p3.sort_values('Annee')
            df_idx_set_p3 = df_idx_p3.set_index('Annee')['Coefficients']

            def get_idx(annee):
                annee = int(annee)
                ann = df_idx_set_p3.index.values.astype(int)
                val = df_idx_set_p3.values.astype(float)
                if annee in ann: return float(df_idx_set_p3.loc[annee])
                if annee < ann[0]:  return float(val[0] - (val[1]-val[0])*(ann[0]-annee))
                if annee > ann[-1]: return float(val[-1] + (val[-1]-val[-2])*(annee-ann[-1]))
                return float(np.interp(annee, ann, val))

            I_cot = get_idx(annee_cot)

            f_tri.seek(0)
            tri_bytes = f_tri.read()
            if f_tri.name.endswith('xlsx'):
                df_raw_p3 = pd.read_excel(_io.BytesIO(tri_bytes), header=None)
            else:
                df_raw_p3 = pd.read_csv(_io.BytesIO(tri_bytes), header=None)
            ligne_ann = df_raw_p3.iloc[0].tolist(); ligne_typ = df_raw_p3.iloc[1].tolist()
            annee_cur = None; col_info_p3 = []
            for i, (a, t) in enumerate(zip(ligne_ann, ligne_typ)):
                if i == 0: col_info_p3.append(('UW_YEAR','')); continue
                try:
                    av = int(float(str(a).strip().replace('.0','')))
                    if 2010 <= av <= 2050: annee_cur = av
                except: pass
                col_info_p3.append((annee_cur, str(t).strip().upper() if pd.notna(t) else ''))

            df_data_p3 = df_raw_p3.iloc[2:].reset_index(drop=True)
            df_data_p3.iloc[:, 0] = df_data_p3.iloc[:, 0].ffill()

            recs = []
            for idx_r, row in df_data_p3.iterrows():
                try:
                    as_ = int(float(str(row.iloc[0]).strip().replace('.0','')))
                    if not (2010 <= as_ <= 2050): continue
                except: continue
                sid = f"{as_}_{idx_r}"
                for ci, (ar, ty) in enumerate(col_info_p3):
                    if ty != 'TOTAL' or ar is None: continue
                    v = row.iloc[ci]
                    try:
                        if isinstance(v, str):
                            v = v.strip().replace(',','.').replace(' ','')
                            if any(c.isalpha() for c in v) or '#' in v: continue
                        v = float(v)
                        if v <= 0 or np.isnan(v): continue
                    except: continue
                    dv = ar - as_
                    if dv < 0 or dv > 9: continue
                    recs.append({'sinistre_id':sid,'annee_surv':as_,'annee_reg':ar,'dev':dv,'total':v})

            df_liq_p3 = pd.DataFrame(recs)
            df_liq_p3['annee_ultime'] = df_liq_p3['annee_surv'] + 9
            df_liq_p3 = df_liq_p3.sort_values(['sinistre_id', 'dev']).reset_index(drop=True)
            df_liq_p3['annee_ultime'] = df_liq_p3['annee_surv'] + 9
            df_liq_p3['I_ultime'] = df_liq_p3['annee_ultime'].apply(get_idx)
            df_liq_p3['I_reg']    = df_liq_p3['annee_reg'].apply(get_idx)
            df_liq_p3['I_surv']   = df_liq_p3['annee_surv'].apply(get_idx)

            # ── Décumul → As-If sur incréments → Recumul ──
            df_liq_p3['prev_total']  = df_liq_p3.groupby('sinistre_id')['total'].shift(1).fillna(0)
            df_liq_p3['increment']   = (df_liq_p3['total'] - df_liq_p3['prev_total']).clip(lower=0)
            df_liq_p3['inc_asif']    = df_liq_p3['increment'] * (I_cot / df_liq_p3['I_reg'])
            df_liq_p3['ratio_check'] = df_liq_p3['I_reg'] / df_liq_p3['I_surv']
            mask_s = df_liq_p3['ratio_check'] >= (1.0 + seuil_stab)
            df_liq_p3['inc_stab']   = np.where(mask_s,
                df_liq_p3['inc_asif'] * (df_liq_p3['I_surv'] / df_liq_p3['I_reg']),
                df_liq_p3['inc_asif'])
            df_liq_p3['Sk']        = df_liq_p3.groupby('sinistre_id')['inc_asif'].cumsum()
            df_liq_p3['S_prime_k'] = df_liq_p3.groupby('sinistre_id')['inc_stab'].cumsum()
            df_liq_p3['coeff_stab'] = np.where(df_liq_p3['S_prime_k']>0, df_liq_p3['Sk']/df_liq_p3['S_prime_k'], 1.0)

            if is_long_p3:
                facteurs_p3 = {k: [] for k in range(9)}
                for sid, grp in df_liq_p3.groupby('sinistre_id'):
                    grp = grp.sort_values('dev').set_index('dev')
                    for k in range(9):
                        if k in grp.index and (k+1) in grp.index:
                            tk = grp.loc[k,'S_prime_k']; tk1 = grp.loc[k+1,'S_prime_k']
                            if tk > 0:
                                f = tk1/tk
                                if 0.9 <= f <= 2.5: facteurs_p3[k].append(f)
                f_moy_p3 = {k: np.mean(facteurs_p3[k]) if facteurs_p3[k] else 1.0 for k in range(9)}
                projs = []
                for sid, grp in df_liq_p3.groupby('sinistre_id'):
                    grp = grp.sort_values('dev').set_index('dev')
                    as_p = grp['annee_surv'].iloc[0]; dm = grp.index.max()
                    sp = grp.loc[dm,'S_prime_k']; cs = grp.loc[dm,'coeff_stab']
                    for k in range(dm,9): sp *= f_moy_p3[k]
                    projs.append({'sinistre_id':sid,'annee_surv':as_p,'dev_max':dm,
                                  'Sprime_ultime':sp,'Sk_ultime':sp*cs,'coeff_stab':cs})
            else:
                f_moy_p3 = {k:1.0 for k in range(9)}
                projs = []
                for sid, grp in df_liq_p3.groupby('sinistre_id'):
                    grp = grp.sort_values('dev').set_index('dev')
                    as_p = grp['annee_surv'].iloc[0]; dm = grp.index.max()
                    sk_ = grp.loc[dm,'Sk']
                    projs.append({'sinistre_id':sid,'annee_surv':as_p,'dev_max':dm,
                                  'Sprime_ultime':sk_,'Sk_ultime':sk_,'coeff_stab':1.0})

            df_proj_p3 = pd.DataFrame(projs)
            D_trav_p3  = next((t['priorite'] for t in st.session_state.get("tranches_p3", tranches_input) if t['type']=='travaillante'), 2_000_000)
            sm_p3      = pct_seuil_p * D_trav_p3
            X_p3       = df_proj_p3['Sprime_ultime'].values; X_p3 = X_p3[X_p3>0]
            Pm_p3      = np.percentile(X_p3, 99.5)
            Xm_p3      = X_p3[(X_p3>=sm_p3)&(X_p3<Pm_p3)]
            if len(Xm_p3)<5: Xm_p3 = X_p3[X_p3>=sm_p3]
            alpha_p3   = len(Xm_p3) / np.sum(np.log(Xm_p3/np.min(Xm_p3)))

            df_gi      = df_gnpis_p3.set_index(df_gnpis_p3.columns[0])
            gc_p3      = df_gnpis_p3.columns[1]
            dpm        = df_proj_p3[(df_proj_p3['Sprime_ultime']>=sm_p3)&(df_proj_p3['Sprime_ultime']<Pm_p3)]
            N_obs_p3   = dpm.groupby('annee_surv').size()
            lv = []
            for an, cn in N_obs_p3.items():
                try: lv.append(cn * gnpi_val / float(df_gi.loc[an, gc_p3]))
                except: lv.append(cn)
            lambda_p3  = float(np.mean(lv)) if lv else 5.0
            coeffs_p3  = df_proj_p3['coeff_stab'].values
            coeffs_p3  = coeffs_p3[(coeffs_p3>0)&np.isfinite(coeffs_p3)]

            # Stocker dans session
            st.session_state.update({
                "df_liq": df_liq_p3, "df_proj": df_proj_p3, "f_moyens": f_moy_p3,
                "alpha_est": float(alpha_p3), "lambda_est": float(lambda_p3),
                "seuil_est": float(sm_p3), "Pm_proxy": float(Pm_p3),
                "coeffs": coeffs_p3, "is_long": is_long_p3,
                "I_cotation": I_cot, "annee_cotation": annee_cot,
                "seuil_stabilisation": seuil_stab, "df_gnpis_df": df_gnpis_p3,
            })

            n_sins = df_proj_p3['sinistre_id'].nunique()
            n_ann  = df_proj_p3['annee_surv'].nunique()
            return {
                "status": "ok",
                "type_branche": type_branche,
                "nb_sinistres": int(n_sins), "nb_annees": int(n_ann),
                "nb_observations": len(df_liq_p3),
                "alpha_estime": round(float(alpha_p3), 4),
                "lambda_estime": round(float(lambda_p3), 4),
                "seuil_pareto_MAD": round(float(sm_p3), 0),
                "Pm_proxy_MAD": round(float(Pm_p3), 0),
                "I_cotation": round(float(I_cot), 4),
                "nb_obs_stabilisees": int(mask_s.sum()),
                "observations": f"{n_sins} sinistres sur {n_ann} années",
                "recommandation_alpha": "Cohérent" if 1.0 < alpha_p3 < 3.0 else "Vérifier — hors norme [1.0, 3.0]"
            }
        except Exception as e:
            return {"erreur": str(e)}


    def _executer_definir_programme(tranches_def):
        """Définit le programme depuis la décision de l'agent"""
        prog = []
        for t in tranches_def:
            prog.append({
                "numero": len(prog)+1,
                "nom": t.get("nom", f"Tranche {len(prog)+1}"),
                "type": t.get("type", "travaillante"),
                "priorite": float(t.get("priorite", 2_000_000)),
                "portee":   float(t.get("portee",   13_000_000)),
                "AAL": None, "AAD": None,
                "nb_reconstitutions":  int(t.get("nb_reconstitutions", 1)),
                "taux_reconstitution": float(t.get("taux_reconstitution", 100)),
                "indices": False,
                "brokage":      float(t.get("brokage_pct", 10)) / 100,
                "frais":        float(t.get("frais_pct",    5)) / 100,
                "marge":        float(t.get("marge_pct",   10)) / 100,
                "retrocession": 0.0
            })
        st.session_state["tranches_p3"] = prog
        return {"status": "ok", "programme": [{
            "nom": t["nom"], "type": t["type"],
            "priorite_MAD": t["priorite"], "portee_MAD": t["portee"],
            "reconstitutions": f"{t['nb_reconstitutions']} x {t['taux_reconstitution']}%",
            "charges": f"Brokage {t['brokage']:.0%} | Frais {t['frais']:.0%} | Marge {t['marge']:.0%}"
        } for t in prog]}


    def _executer_market_curve_p3(rol_min, rol_max, r2_min, tolerance, filtre, f_mkt_file, gnpi_val):
        """Courbe de référence marché sur fichier uploadé directement"""
        try:
            import io as _io
            f_mkt_file.seek(0)
            df_mkt_p3 = pd.read_excel(_io.BytesIO(f_mkt_file.read())) if f_mkt_file.name.endswith('xlsx') else pd.read_csv(f_mkt_file)
            df_mkt_p3.columns = [c.strip() for c in df_mkt_p3.columns]
            for col in ['ROLs','midpoints','Garantie en MAD']:
                if col in df_mkt_p3.columns and df_mkt_p3[col].dtype == object:
                    df_mkt_p3[col] = (df_mkt_p3[col].astype(str).str.replace('%','').str.replace(' ','').str.replace(',','.')
                        .apply(lambda x: float(x)/100 if x not in ['nan',''] and float(x)>1.5
                               else (float(x) if x not in ['nan',''] else np.nan)))
            df_mkt_p3 = df_mkt_p3.dropna(subset=['ROLs','midpoints'])
            if filtre.strip():
                col_b = next((c for c in df_mkt_p3.columns if 'BUSINESS' in c.upper()), None)
                if col_b:
                    df_mkt_p3 = df_mkt_p3[df_mkt_p3[col_b].astype(str).str.upper()
                                           .str.contains(filtre.upper(), regex=False, na=False)]
            mask_r = (df_mkt_p3['ROLs'] >= rol_min) & (df_mkt_p3['ROLs'] <= rol_max)
            df_mkt_p3 = df_mkt_p3[mask_r].copy()
            df_mkt_p3['diff_rel'] = np.where(df_mkt_p3['midpoints']!=0,
                np.abs(df_mkt_p3['ROLs']-df_mkt_p3['midpoints'])/np.abs(df_mkt_p3['midpoints']),1.0)
            df_mkt_p3 = df_mkt_p3[df_mkt_p3['diff_rel']>=tolerance].copy()
            df_mkt_p3 = df_mkt_p3[df_mkt_p3['midpoints']>0].copy()
            if len(df_mkt_p3) < 5: return {"erreur": f"Seulement {len(df_mkt_p3)} points — filtres trop restrictifs"}

            st.session_state["df_mkt_clean"] = df_mkt_p3
            prog_p3 = st.session_state.get("tranches_p3", tranches_input)

            def fit_p(x, y):
                lx=np.log(x); ly=np.log(y); c=np.polyfit(lx,ly,1)
                a=np.exp(c[1]); b=-c[0]; lyp=np.polyval(c,lx)
                r2=1-np.sum((ly-lyp)**2)/np.sum((ly-ly.mean())**2+1e-10)
                return a,b,r2

            def ctt(t, a, b):
                x=(t['priorite']+t['portee']/2)/gnpi_val
                rol=a*(x**(-b)); tp=rol*t['portee']/gnpi_val
                tr=tp*1.002; tt=tr/(1-t['brokage']-t['frais']-0.0021)
                L=t['portee']; t_r=t['taux_reconstitution']/100; n_r=t['nb_reconstitutions']
                Pr=sum(t_r*min(L,max(tp*gnpi_val-(r-1)*L,0)) for r in range(1,n_r+1))/(L or 1)
                Rec=Pr/(Pr+10)
                return {"tranche":t["nom"],"type":t["type"],"x_norm":round(x,6),
                        "rol":round(rol,6),"taux_pur":round(tp,6),"taux_tech":round(tt,6),
                        "chargement_majeurs":round(st.session_state.get("chargement_majeurs",0.0),6),"taux":round(tt,6)}

            resultats_p3_mkt = []
            for q in [0.20,0.40,0.60,0.80,1.0]:
                mq = np.quantile(df_mkt_p3['midpoints'],q)
                dq = df_mkt_p3[df_mkt_p3['midpoints']<=mq]
                if len(dq)<5: continue
                try:
                    a,b,r2=fit_p(dq['midpoints'].values,dq['ROLs'].values)
                    if b<=0: continue
                    tts=[ctt(t,a,b) for t in prog_p3]
                    if any(tt['taux']<=0 for tt in tts): continue
                    resultats_p3_mkt.append({"quantile":q,"n_points":len(dq),"a":round(a,6),
                        "b":round(b,4),"r2":round(r2,4),"r2_ok":r2>=r2_min,
                        "taux_tranches":tts,"score":r2-(0 if r2>=r2_min else 0.5)})
                except: continue

            if not resultats_p3_mkt: return {"erreur": "Aucun ajustement valide"}
            best = max(resultats_p3_mkt, key=lambda x: x["score"])
            st.session_state["resultats_mkt"]  = resultats_p3_mkt
            st.session_state["taux_mkt_final"] = best["taux_tranches"]
            return _json_safe({"status":"ok","a":best["a"],"b":best["b"],"r2":best["r2"],
                    "r2_ok":best["r2_ok"],"n_points":best["n_points"],
                    "taux_par_tranche":best["taux_tranches"],
                    "interpretation": "R² satisfaisant" if best["r2_ok"] else "R² faible — interpréter avec prudence"})
        except Exception as e:
            return {"erreur": str(e)}


    def executer_outil_full(nom, inputs, f_tri_f, f_gnp_f, f_idx_f, f_mkt_f, gnpi_v, annee_v):
        """Dispatcher Phase 3 — inclut les outils de parsing fichiers"""
        if nom == "analyser_et_transformer_triangle":
            return _executer_transformer_triangle_complet(
                inputs.get("type_branche", "long"), inputs.get("seuil_stabilisation", 0.0),
                inputs.get("pct_seuil_pareto", 0.80), f_tri_f, f_gnp_f, f_idx_f, gnpi_v, annee_v)
        elif nom == "definir_programme_tranches":
            return _executer_definir_programme(inputs.get("tranches", []))
        elif nom == "calculer_burning_cost_complet":
            prog = st.session_state.get("tranches_p3", tranches_input)
            return _executer_burning_cost_p3(prog, gnpi_v)
        elif nom == "lancer_simulation_complete":
            prog = st.session_state.get("tranches_p3", tranches_input)
            return _executer_simulation(inputs.get("alpha", st.session_state.get("alpha_est",1.5)), inputs.get("lambda_", st.session_state.get("lambda_est",5.0)), inputs.get("seuil", st.session_state.get("seuil_est",1_600_000)), int(inputs.get("n_sim", 10000)))
        elif nom == "construire_market_curve_complete":
            return _executer_market_curve_p3(
                inputs.get("rol_min", 0.05), inputs.get("rol_max", 1.0), inputs.get("r2_min", 0.30),
                inputs.get("tolerance", 0.50), inputs.get("filtre_branche", "EVENEMENT"), f_mkt_f, gnpi_v)
        elif nom == "demander_validation_humaine":
            return {"status": "validation_requise",
                    "niveau": inputs.get("niveau","avertissement"), "message": inputs.get("message",""),
                    "question": inputs.get("question",""), "choix": inputs.get("choix", ["Continuer", "Arrêter"])}
        elif nom == "generer_rapport_final_complet":
            prog = st.session_state.get("tranches_p3", tranches_input)
            return _executer_rapport_p3(inputs.get("methode_travaillante","simulation"), inputs.get("methode_cat","max_sim_mkt"), prog, gnpi_v)
        elif nom == "evaluer_pertinence_methodes":
            return _executer_evaluer_methodes(
                inclure_ks_ad=inputs.get("inclure_tests_ks_ad", True),
                inclure_hill=inputs.get("inclure_stabilite_hill", True))
        elif nom == "rechercher_web_actuariel":
            return _executer_recherche_web(
                inputs.get("requete",""), inputs.get("type_recherche","methode"))
        elif nom == "envoyer_notification_agent":
            return _executer_notification_email(
                inputs.get("sujet","Notification Atlantic Re IA"),
                inputs.get("contenu",""),
                inputs.get("niveau","info"),
                st.session_state.get("user_email",""))
        elif nom == "consulter_ressource_actuarielle":
            cat = inputs.get("categorie","Actuariat & Standards")
            return {"status":"ok","categorie":cat,
                    "ressources": RESSOURCES_ACTUARIELLES.get(cat,[])}
        else:
            return {"erreur": f"Outil inconnu : {nom}"}


    def _executer_recherche_web(requete, type_recherche):
        """Recherche web actuarielle via l'API web_search d'Anthropic."""
        try:
            client_s = __import__('anthropic').Anthropic(api_key=api_key)
            prompt_s = f"""Recherche actuarielle : {requete}
Type d'information : {type_recherche}
Contexte : Tarification réassurance non-proportionnelle XL automobile Maroc.
Fournir : chiffres clés, sources, applicabilité au contexte Maroc.
Répondre de façon concise et structurée (max 300 mots)."""
            resp = client_s.messages.create(
                model="claude-haiku-4-5-20251001",
                max_tokens=500,
                tools=[{"type":"web_search_20250305","name":"web_search"}],
                messages=[{"role":"user","content":prompt_s}])
            text = " ".join(b.text for b in resp.content if hasattr(b,"text") and b.text)
            return {"status":"ok","requete":requete,"type":type_recherche,
                    "resultat":text or "Recherche effectuée — résultats dans le contexte."}
        except Exception as e:
            return {"status":"fallback","requete":requete,
                    "resultat": f"Recherche web non disponible : {e}. "
                                f"Consulter manuellement : casact.org, swissre.com, astin.org"}


    def _executer_notification_email(sujet, contenu, niveau, user_email):
        """Envoie notification email de fin de session."""
        from datetime import datetime
        if not contenu:
            # Construire automatiquement depuis session_state
            pt = st.session_state.get("prime_totale", 0)
            tg = pt / gnpi3 if gnpi3 else 0
            anomalies_count = len([a for a in st.session_state.get("agent_py_anomalies",[])
                                   if a.get("niveau") == "CRITIQUE"])
            contenu = f"""
<p><b>Session terminée par :</b> {user_email}</p>
<p><b>Date :</b> {datetime.now().strftime('%d/%m/%Y à %H:%M')}</p>
<p><b>GNPI :</b> {gnpi3:,.0f} MAD</p>
<p><b>Prime totale calculée :</b> {pt:,.0f} MAD</p>
<p><b>Taux global :</b> {tg:.4%}</p>
<p><b>Anomalies critiques :</b> {anomalies_count}</p>
<p><b>Modules complétés :</b> BC, Simulation, Courbe de référence marché, Rapport Final</p>
"""
        icone = {"info":"","alerte":"","rapport_final":""}.get(niveau,"")
        ok, msg = envoyer_notification_email(
            f"{icone} {sujet}",
            contenu,
            "hervepagnangde@gmail.com")
        return {"status": "ok" if ok else "non_configure",
                "message": msg if ok else f"Email non envoyé ({msg}) — configurez SMTP_USER/SMTP_PASS dans Secrets Streamlit"}


    def _executer_burning_cost_p3(prog, gnpi_v):
        if "df_proj" not in st.session_state: return {"erreur": "df_proj manquant"}
        df_proj = st.session_state["df_proj"].copy()
        resultats = []
        for t_info in prog:
            D=t_info["priorite"]; L=t_info["portee"]
            aal=t_info["AAL"]; aad=t_info["AAD"]
            n_rec=t_info["nb_reconstitutions"]; t_r=t_info["taux_reconstitution"]/100
            cap=(n_rec+1)*L
            df_proj["Ck"] = df_proj.apply(
                lambda row: min(max(row["Sprime_ultime"]-D,0),L)*row["coeff_stab"], axis=1)
            charges_ann = df_proj.groupby("annee_surv")["Ck"].sum()
            cfs = []
            for an, ch in charges_ann.items():
                if aad: ch=max(ch-aad,0)
                if aal: ch=min(ch,aal)
                cfs.append({"annee":int(an),"charge":round(float(min(ch,cap)),2)})
            df_ch=pd.DataFrame(cfs); N=len(df_ch)
            Pr=0.0
            for Cn in df_ch["charge"].values:
                for r in range(1,n_rec+1): Pr+=t_r*min(L,max(Cn-(r-1)*L,0))
            Pr/=L if L>0 else 1
            Rec=Pr/(Pr+N) if (Pr+N)>0 else 0.0
            cm = df_ch["charge"].mean()
            charges_nz = [c for c in df_ch["charge"].values if c > 0]
            n_nz = len(charges_nz)
            charg_maj_p3 = st.session_state.get("chargement_majeurs", 0.0)
            if n_nz < 3:
                tp = tr = tt = 0.0; sig_p3 = 0.0
            else:
                tp = cm / gnpi_v
                sig_p3 = float(np.std(charges_nz)) / gnpi_v
                tr = tp + sig_p3 * 0.20
                tt = (tr*(1-Rec))/(1-t_info["brokage"]-t_info["frais"]-t_info["marge"]-t_info["retrocession"])
            resultats.append({"tranche":t_info["nom"],"type":t_info["type"],
                "charge_moy":round(cm,2),"n_ann_nonzero":n_nz,"sigma_hist":round(sig_p3 if n_nz>=3 else 0.0,6),
                "Pr_Rec":round(Pr,6),"Rec":round(Rec,6),
                "taux_pur":round(tp,6),"taux_risque":round(tr,6),
                "taux_technique":round(tt,6),
                "chargement_majeurs":round(charg_maj_p3,6),
                "detail_annuel":cfs})
        st.session_state["resultats_bc"] = resultats
        return {"status":"ok","resultats":[{k:v for k,v in r.items() if k!="detail_annuel"} for r in resultats]}


    def _executer_rapport_p3(meth_trav, meth_cat, prog, gnpi_v):
        if not all(k in st.session_state for k in ["resultats_bc","resultats_sim","taux_mkt_final"]):
            return {"erreur": "Résultats intermédiaires manquants"}
        _bc_l = st.session_state["resultats_bc"]
        _si_l = st.session_state["resultats_sim"]
        _mk_l = st.session_state["taux_mkt_final"]
        rows=[]; pt=0
        for idx_t, t in enumerate(prog):
            n=t["nom"]
            bt  = _lookup_taux(_bc_l, n, idx_t, "taux_technique")
            st_ = _lookup_taux(_si_l, n, idx_t, "taux_technique")
            mk  = _lookup_taux(_mk_l, n, idx_t, "taux")
            if t["type"]=="travaillante":
                if meth_trav=="bc": tx=bt; me="BC"
                elif meth_trav=="moyenne_bc_sim": tx=(bt+st_)/2; me="Moy BC+Sim"
                else: tx=st_; me="Simulation"
            else:
                if meth_cat=="market_curve": tx=mk; me="Marché"
                elif meth_cat=="max_sim_mkt": tx=max(st_,mk); me="Max(Sim,Marché)"
                else: tx=st_; me="Simulation"
            pr=gnpi_v*tx; pt+=pr
            ec=abs(bt-st_)/bt*100 if bt>0 else 0
            rows.append({"tranche":n,"type":t["type"],
                "taux_bc":round(bt,6),"taux_sim":round(st_,6),"taux_mkt":round(mk,6),
                "taux_retenu":round(tx,6),"methode":me,"prime_MAD":round(pr,2),
                "ecart_bc_sim_pct":round(ec,1)})
        st.session_state["df_rapport"]=pd.DataFrame(rows); st.session_state["prime_totale"]=pt
        return {"status":"ok","synthese":rows,"prime_totale_MAD":round(pt,2),"taux_global":round(pt/gnpi_v,6)}


    # ════════════════════════════════
    # BOUCLE AGENTIQUE PHASE 3
    # ════════════════════════════════

    def run_agent_full(api_key, f_tri_f, f_gnp_f, f_idx_f, f_mkt_f,
                       gnpi_v, annee_v, contexte_v, seuil_al,
                       log_cont, result_cont, alert_cont):
        client = anthropic.Anthropic(api_key=api_key)

        system_p3 = f"""Tu es un agent actuariel autonome de niveau expert senior.
Spécialiste : Réassurance Non-Proportionnelle XL, automobile, marchés émergents (Maroc/Afrique).
Références : Daykin-Pentikäinen-Pesonen (1994), CAS ratemaking guidelines, ASTIN Bulletin, IAA standards.

═══ CONTEXTE MISSION ═════════════════════════════════════════
{contexte_v if contexte_v else f"Portefeuille automobile Maroc 2026 | GNPI {gnpi_v:,.0f} MAD | Cotation {annee_v}"}

GNPI : {gnpi_v:,.0f} MAD | Année cotation : {annee_v} | Période retour majeurs : {retour3} ans
Seuil alerte critique (écart BC/Sim) : {seuil_al}%

═══ RÈGLE FONDAMENTALE : PRIMAUTÉ DU BURNING COST ═══════════
Le Burning Cost est LA méthode de référence en réassurance XL.
Il reflète l'expérience RÉELLE de la cédante.
TOUJOURS commencer par le BC, même quand il donne zéro.
La simulation est un outil de validation du BC — pas une alternative par défaut.

EXCEPTION MAJEURE :
• Branches non-travaillantes / partiellement travaillantes → BC non crédible → Simulation prioritaire
• Tranches cat → BC souvent nul (normal) → Simulation + Courbe de référence marché prioritaires
Dans ces cas : TRÈS GRANDE ATTENTION aux paramètres de simulation (α, λ, seuil).

═══ DÉTECTION ANNÉES ATYPIQUES (OBLIGATOIRE avant tarification) ════
AVANT de calculer le BC final, l'agent DOIT analyser chaque année.
Causes d'écartement légitimes :
  [A] ISOLEMENT  : τ année > 3× médiane de ses voisines (N-1, N+1)
  [B] NATURE     : Sinistres CAT dans une tranche Risk uniquement
  [C] GNPI FAIBLE: GNPI année < 50% de la médiane historique
  [D] SINISTRE UNIQUE : Un seul sinistre exceptionnel (traiter via EVT/GPD)
  [E] CHANGEMENT PÉRIMÈTRE : Modification majeure du portefeuille assuré
Si écartement → présenter BC avec ET sans année atypique + justification documentée.

═══ CADRE MÉTHODOLOGIQUE ════════════════════════════════════
R1 : τ_risque = τ_pur + σ_hist × 20%
R2 : BC = 0 si années non-nulles < 3 (NORMAL pour cat)
R3 : Sinistres majeurs par EVT/GPD (Pickands-Balkema-de Haan, 1974)
R4 : Courbe de référence marché = tranches CAT / non-travaillantes (ROL = a × x^-b)
R5 : As-If sur incréments (Finger 2006) — PAS sur cumulatifs
R6 : Stabilisation si I_règl/I_surv ≥ 1 + seuil

Sélection finale :
• TRAVAILLANTE   → max(BC, Sim) — BC prioritaire si crédible
• NON-TRAV./CAT  → max(Sim, Marché) — jamais BC seul

═══ RÈGLES SIMULATION ═══════════════════════════════════════
Pour les branches travaillantes :
• Objectif = faire coïncider la distribution simulée avec l'empirique, SURTOUT EN QUEUE
• Si simulation ≠ BC malgré ajustement optimal → signal de problème structurel
• Ajuster α (queue) et λ (fréquence) jusqu'à convergence visuelle

Pour les branches non-travaillantes / cat :
• Paramètres α et λ doivent être calibrés avec EXTRÊME soin
• Comparer avec taux marché comme contre-vérification
• Si simulation donne un résultat très différent du marché → investiguer

═══ RÈGLES MARKET CURVE ═════════════════════════════════════
• Filtrer les données de marché par plage de ROL pertinente pour chaque tranche
  Ex: Tranche avec ROL cible ~ 10% → utiliser données ROL ∈ [0%, 15%] uniquement
  Ex: Tranche avec ROL cible ~ 2% → utiliser données ROL ∈ [0%, 4%] uniquement
• Ne jamais mélanger données de ROL élevé avec tranches à faible ROL
• Vérifier la hiérarchie : priorité plus haute = ROL plus bas (si non respecté → signal d'erreur)
• R² minimum : 0.40 avec N ≥ 15 points

═══ SÉQUENCE OBLIGATOIRE ════════════════════════════════════
1. DÉFINIR le programme (tranches, priorités, portées, frais)
2. ANALYSER le triangle (choix branche longue/courte)
3. DÉTECTER les années atypiques (causes A→E)
4. BURNING COST (As-If → Stab → CL → agrégation, avec/sans atypiques)
5. SIMULATION (calibrage α/λ pour coller à l'empirique)
6. Si écart BC/Sim > {seuil_al}% ET tranche travaillante → DEMANDER_VALIDATION_HUMAINE
7. MARKET CURVE (filtre ROL par tranche, R² ≥ 0.40)
8. ÉVALUER pertinence statistique (KS, AD, Hill)
9. RAPPORT FINAL + NOTIFIER

═══ CHARTE QUALITÉ ══════════════════════════════════════════
• Chain-of-thought : [Observation] → [Calcul] → [Conclusion chiffrée]
• Toujours quantifier : τ_pur, σ, τ_risque, τ_technique, prime (MAD)
• Signaler explicitement : années écartées + raison, crédibilité BC
• Cohérence inter-tranches : hiérarchie ROL, taux décroissants avec la priorité

Agis de façon professionnelle, autonome et rigoureuse."""

        messages = [{"role": "user", "content":
            f"Lance la tarification complète Atlantic Re 2026. GNPI={gnpi_v:,} MAD. Contexte : {contexte_v if contexte_v else 'Standard automobile Maroc'}. Go."}]

        tour=0; max_t=15; validation_en_attente=None

        while tour < max_t:
            tour+=1
            with log_cont:
                st.markdown(f"""<div style="background:#1a1a1a;border-radius:6px;padding:6px 12px;
                    margin:4px 0;font-size:11px;color:#888">Tour {tour}/{max_t}</div>""",
                    unsafe_allow_html=True)

            resp = client.messages.create(
                model="claude-opus-4-5", max_tokens=4096,
                system=system_p3, tools=TOOLS_FULL, messages=messages)

            for block in resp.content:
                if hasattr(block,'text') and block.text:
                    with log_cont:
                        st.markdown(f"""<div style="background:rgba(45,138,78,0.07);
                            border-left:3px solid #2d8a4e;border-radius:0 8px 8px 0;
                            padding:12px 16px;margin:6px 0;font-size:13px;line-height:1.6">
                             {block.text}</div>""", unsafe_allow_html=True)

                if block.type == "tool_use":
                    with log_cont:
                        just = block.input.get("justification","")
                        params_display = {k:v for k,v in block.input.items() if k not in ["justification","tranches"]}
                        st.markdown(f"""<div style="background:rgba(59,130,246,0.07);
                            border-left:3px solid #3b82f6;border-radius:0 8px 8px 0;
                            padding:12px 16px;margin:6px 0;font-size:13px">
                             <b style="color:#3b82f6">{block.name}</b><br>
                            <span style="color:#666;font-size:11px">{just}</span><br>
                            <code style="font-size:11px">{json.dumps(params_display,ensure_ascii=False)[:200]}</code>
                            </div>""", unsafe_allow_html=True)

            if resp.stop_reason == "end_turn": break

            if resp.stop_reason == "tool_use":
                tool_results = []
                for block in resp.content:
                    if block.type != "tool_use": continue

                    with log_cont:
                        with st.spinner(f" {block.name}..."):
                            result = executer_outil_full(
                                block.name, block.input,
                                f_tri_f, f_gnp_f, f_idx_f, f_mkt_f,
                                gnpi_v, annee_v)

                    # Gestion validation humaine
                    if result.get("status") == "validation_requise":
                        # ── Validation non-bloquante : affiche l'alerte et continue ──
                        niveau = result.get("niveau","avertissement")
                        color_map = {"avertissement":"#f59e0b","critique":"#ef4444","bloquant":"#7c3aed"}
                        col_a = color_map.get(niveau, "#f59e0b")
                        with alert_cont:
                            choix_defaut = result.get("choix", ["Continuer"])[0]
                            st.markdown(f"""<div style="background:rgba(245,158,11,0.08);
                                border:2px solid {col_a};border-radius:12px;
                                padding:16px 20px;margin:8px 0">
                                <div style="color:{col_a};font-weight:700;font-size:14px;margin-bottom:6px">
                                     {niveau.upper()} — {result.get('message','')}
                                </div>
                                <div style="color:#555;font-size:13px">
                                    {result.get('question','')}
                                </div>
                                <div style="color:#2d8a4e;font-size:12px;margin-top:8px">
                                     L'agent continue automatiquement avec : <b>{choix_defaut}</b>
                                </div></div>""", unsafe_allow_html=True)
                        result = {"status": "validation_confirmee",
                                  "choix_humain": choix_defaut,
                                  "message": f"Auto-continué : {choix_defaut}"}

                    erreur = result.get("erreur","")
                    with log_cont:
                        if erreur:
                            st.markdown(f"""<div style="background:rgba(239,68,68,0.08);
                                border-left:3px solid #ef4444;border-radius:0 8px 8px 0;
                                padding:10px 14px;margin:4px 0;font-size:12px">
                                 <b>{block.name}</b> : {erreur}</div>""", unsafe_allow_html=True)
                        else:
                            status_txt = result.get("status","ok")
                            st.markdown(f"""<div style="background:rgba(45,138,78,0.06);
                                border-left:3px solid #2d8a4e;border-radius:0 8px 8px 0;
                                padding:10px 14px;margin:4px 0;font-size:12px">
                                 <b>{block.name}</b> — {status_txt}</div>""", unsafe_allow_html=True)

                    tool_results.append({
                        "type": "tool_result", "tool_use_id": block.id,
                        "content": json.dumps(_json_safe(result), ensure_ascii=False)})

                messages.append({"role":"assistant","content":resp.content})
                messages.append({"role":"user","content":tool_results})
            else:
                break

        # Résultats finaux
        with result_cont:
            st.markdown("---")
            st.markdown("##  Résultats Agent Complet")

            if "tranches_p3" in st.session_state:
                st.markdown("###  Programme défini par l'agent")
                tableau_resultats([{
                    "Tranche": t["nom"], "Type": t["type"],
                    "Priorité": f"{t['priorite']:,.0f} MAD",
                    "Portée": f"{t['portee']:,.0f} MAD",
                    "Reconst.": f"{t['nb_reconstitutions']} x {t['taux_reconstitution']}%",
                    "Charges": f"Brok {t['brokage']:.0%} | Frais {t['frais']:.0%} | Marge {t['marge']:.0%}"
                } for t in st.session_state["tranches_p3"]])

            if "df_proj" in st.session_state:
                c1,c2,c3,c4 = st.columns(4)
                c1.metric("Sinistres",  st.session_state["df_proj"]["sinistre_id"].nunique())
                c2.metric("Alpha",      f"{st.session_state.get('alpha_est',0):.4f}")
                c3.metric("Lambda",     f"{st.session_state.get('lambda_est',0):.4f}")
                c4.metric("Seuil MAD",  f"{st.session_state.get('seuil_est',0):,.0f}")

            if "resultats_bc" in st.session_state and "resultats_sim" in st.session_state:
                col_a, col_b = st.columns(2)
                with col_a:
                    st.markdown("###  Burning Cost")
                    tableau_resultats([{
                        "Tranche": r["tranche"],
                        "Rec": f"{r['Rec']:.4%}",
                        "Taux pur": f"{r['taux_pur']:.4%}",
                        "Taux tech.": f"{r['taux_technique']:.4%}",
                    } for r in st.session_state["resultats_bc"]])
                with col_b:
                    st.markdown("###  Simulation")
                    tableau_resultats([{
                        "Tranche": r["tranche"],
                        "Taux pur": f"{r['taux_pur']:.4%}",
                        "Taux tech.": f"{r['taux_technique']:.4%}",
                        "Impact rec.": f"{r.get('impact_rec', 0):.4%}",
                    } for r in st.session_state["resultats_sim"]])

            if "taux_mkt_final" in st.session_state:
                st.markdown("###  Courbe de référence marché")
                tableau_resultats([{
                    "Tranche": tt["tranche"],
                    "ROL": f"{tt['rol']:.4%}",
                    "Taux tech.": f"{tt['taux_tech']:.4%}",
                    "Taux final": f"{tt['taux']:.4%}",
                } for tt in st.session_state["taux_mkt_final"]])

            if "df_rapport" in st.session_state:
                st.markdown("###  Rapport Final")
                tableau_resultats([{
                    "Tranche": row["tranche"], "Type": row["type"],
                    "Taux BC": f"{row['taux_bc']:.4%}",
                    "Taux Sim.": f"{row['taux_sim']:.4%}",
                    "Taux Marché": f"{row['taux_mkt']:.4%}",
                    " Retenu": f"{row['taux_retenu']:.4%}",
                    "Prime (MAD)": f"{row['prime_MAD']:,.0f}",
                    "Méthode": row["methode"],
                    "Écart BC/Sim": f"{row['ecart_bc_sim_pct']:.0f}%",
                } for row in st.session_state["df_rapport"].to_dict("records")])

                pt = st.session_state.get("prime_totale", 0)
                c1,c2,c3 = st.columns(3)
                with c1: card("Prime totale", f"{pt:,.0f} MAD", icone="")
                with c2: card("Taux global",  f"{pt/gnpi_v:.4%}", couleur="#1a1a1a", icone="")
                with c3: card("Agent",        "Complet ", couleur="#3b82f6", icone="")


    # ── Lancement Phase 3 ──
    if lancer3:
        st.markdown("---")
        st.markdown("###  Exécution Agent Complet")
        alert_cont  = st.container()
        log_cont    = st.container()
        result_cont = st.container()

        with log_cont:
            st.markdown("""<div style="background:linear-gradient(135deg,#0d0d1a,#1a1a1a);
                border-radius:10px;padding:14px 18px;margin-bottom:12px;
                border:1px solid rgba(59,130,246,0.4)">
                <span style="color:#3b82f6;font-weight:700"> Agent Complet démarré</span>
                <span style="color:#888;font-size:12px;margin-left:8px">
                Traitement en cours ...</span>
                </div>""", unsafe_allow_html=True)
        try:
            run_agent_full(api_key, f3_tri, f3_gnp, f3_idx, f3_mkt,
                           gnpi3, annee3, contexte3, seuil_alerte,
                           log_cont, result_cont, alert_cont)
            with log_cont:
                st.success(" Agent Complet terminé — rapport disponible ci-dessus et dans tous les onglets")
        except Exception as e:
            st.error(f" Erreur agent complet : {e}")

    elif not lancer3 and "df_rapport" in st.session_state:
        st.info(" Résultats de la dernière exécution disponibles dans les onglets.")
        if st.button("🔄 Relancer l'Agent Complet", key="relancer3"):
            for k in ["tranches_p3","df_proj","df_liq","resultats_bc","resultats_sim",
                      "resultats_mkt","taux_mkt_final","df_rapport"]:
                st.session_state.pop(k, None)
            st.rerun()



# ════════════════════════════════════════════
# TAB HISTORIQUE
# ════════════════════════════════════════════

with tab_hist:
    section_header("Historique des Sessions", "Consultez et rechargez vos tarifications passées", "📜")

    user_email_hist = st.session_state.get("user_email", "")
    if not user_email_hist:
        st.warning(" Connectez-vous pour accéder à l'historique")
    else:
        try:
            sessions = db_list_sessions(user_email_hist)
        except Exception as _e:
            sessions = []
            st.error(f"Erreur DB : {_e}")

        if not sessions:
            st.info("📭 Aucune session sauvegardée.")
            st.markdown("""
            <div style="background:rgba(45,138,78,0.08);border-left:4px solid #2d8a4e;
                border-radius:0 8px 8px 0;padding:14px 18px;margin:8px 0;font-size:13px">
                <b>Comment créer une session ?</b><br>
                1. Définissez votre programme dans l'onglet  Programme<br>
                2. Lancez au moins un calcul (BC, Simulation ou Courbe de référence marché)<br>
                3. Cliquez <b> Sauvegarder maintenant</b> dans la sidebar<br>
                4. La session apparaîtra ici automatiquement
            </div>""", unsafe_allow_html=True)
        else:
            st.markdown(f"**{len(sessions)} session(s) trouvée(s)** pour {user_email_hist}")

            # Tableau des sessions
            sess_data = []
            for sid, nom, gnpi_s, created, updated in sessions:
                is_current = (sid == st.session_state.get("db_session_id"))
                sess_data.append({
                    "ID": sid,
                    "Session": f"{' ' if is_current else ''}{nom or f'Session #{sid}'}",
                    "GNPI": f"{gnpi_s:,.0f} MAD" if gnpi_s else "—",
                    "Créée": created or "—",
                    "Modifiée": updated or "—",
                })
            tableau_resultats(sess_data)

            st.divider()
            st.markdown("### 🔄 Charger une session")
            c1, c2 = st.columns([3, 1])
            with c1:
                sess_options = {f"#{sid} — {nom or 'Sans nom'} ({updated})": sid
                                for sid, nom, _, _, updated in sessions}
                choix_sess = st.selectbox("Choisir une session à charger",
                    options=list(sess_options.keys()), key="hist_select")
            with c2:
                st.markdown("<div style='height:28px'></div>", unsafe_allow_html=True)
                if st.button("📂 Charger", type="primary", use_container_width=True):
                    sid_choix = sess_options[choix_sess]
                    try:
                        nom_load = db_load_session(sid_choix)
                        # Résumé de ce qui a été chargé
                        chargé = []
                        if "resultats_bc"  in st.session_state: chargé.append(" Burning Cost")
                        if "resultats_sim" in st.session_state: chargé.append(" Simulation")
                        if "taux_mkt_final" in st.session_state and st.session_state["taux_mkt_final"]: chargé.append(" Courbe de référence marché")
                        if "df_rapport"    in st.session_state: chargé.append(" Rapport Final")
                        st.success(f" Session restaurée : **{nom_load}**")
                        if chargé:
                            st.markdown(f"""<div style="background:rgba(45,138,78,0.08);
                                border-left:4px solid #2d8a4e;border-radius:0 8px 8px 0;
                                padding:14px 18px;margin:8px 0;font-size:13px">
                                <b>Données disponibles dans :</b><br>
                                {"  ·  ".join(chargé)}<br><br>
                                👉 Naviguez vers l'onglet souhaité pour consulter les résultats.<br>
                                👉 Allez dans <b> Rapport Final</b> pour voir la synthèse complète.
                                </div>""", unsafe_allow_html=True)
                        st.rerun()
                    except Exception as _e:
                        st.error(f"Erreur chargement : {_e}")

            # Comparaison N-1
            st.divider()
            st.markdown("###  Comparaison N-1")
            current_sid = st.session_state.get("db_session_id")
            if current_sid and st.session_state.get("df_rapport") is not None:
                try:
                    prev_rows = db_get_previous_session(user_email_hist, current_sid)
                    if prev_rows and st.session_state.get("df_rapport") is not None:
                        curr_rows = st.session_state["df_rapport"].to_dict("records")
                        prev_map = {r.get("Tranche","") or r.get("tranche",""): r for r in prev_rows}
                        comp = []
                        for r in curr_rows:
                            nom_t = r.get("Tranche","") or r.get("tranche","")
                            prev_r = prev_map.get(nom_t, {})
                            taux_curr = r.get("Taux retenu","") or r.get("taux_retenu","")
                            taux_prev = prev_r.get("Taux retenu","") or prev_r.get("taux_retenu","")
                            try:
                                tc = float(str(taux_curr).replace("%",""))
                                tp = float(str(taux_prev).replace("%",""))
                                delta = tc - tp
                                delta_str = f"{'▲' if delta>0 else '▼'} {abs(delta):.4f}%"
                            except:
                                delta_str = "—"
                            comp.append({
                                "Tranche": nom_t,
                                "Taux N (actuel)": taux_curr,
                                "Taux N-1": taux_prev or "—",
                                "Évolution": delta_str,
                            })
                        if comp:
                            st.caption("Comparaison entre la session courante et la précédente")
                            tableau_resultats(comp)
                    else:
                        st.info("Exécutez une tarification complète pour voir la comparaison N-1.")
                except Exception as _e:
                    st.info(f"Comparaison N-1 non disponible : {_e}")
            else:
                st.info("Chargez une session et complétez une tarification pour comparer.")

            # Suppression
            st.divider()
            st.markdown("### 🗑️ Supprimer une session")
            with st.expander("Supprimer (irréversible)", expanded=False):
                del_options = {f"#{sid} — {nom or 'Sans nom'}": sid
                               for sid, nom, _, _, _ in sessions}
                del_choix = st.selectbox("Session à supprimer", list(del_options.keys()),
                                          key="hist_del_select")
                if st.button("🗑️ Confirmer la suppression", key="hist_del_btn"):
                    try:
                        sid_del = del_options[del_choix]
                        db_delete_session(sid_del)
                        if st.session_state.get("db_session_id") == sid_del:
                            st.session_state.pop("db_session_id", None)
                        st.success(" Session supprimée")
                        st.rerun()
                    except Exception as _e:
                        st.error(str(_e))

# ════════════════════════════════════════════
# TAB ADMIN
# ════════════════════════════════════════════

with tab_admin:
    st.header("🔐 Interface Administrateur")
    admin_pwd = st.text_input("Mot de passe admin", type="password", key="admin_pwd")
    if admin_pwd == get_admin_password():
        st.success(" Accès accordé")
        users = get_users()
        st.markdown("#### 👥 Utilisateurs autorisés")
        st.dataframe(pd.DataFrame([{"Email": e, "Code": c, "Statut": "Actif"}
                                    for e, c in users.items()]), use_container_width=True)
        st.divider()
        st.markdown("####  Gérer les utilisateurs")
        st.info("Allez sur Streamlit Cloud -> Settings -> Secrets et ajoutez :\nadmin_password = 'VotreMDP'\n[users]\n'email@ex.com' = 'CODE'")
        st.divider()
        st.markdown("####  Générateur de code")
        col1, col2 = st.columns(2)
        with col1:
            email_new = st.text_input("Email du nouvel utilisateur", key="new_email")
        with col2:
            if st.button("Générer un code"):
                st.session_state["generated_code"] = secrets_lib.token_hex(4).upper()
        if "generated_code" in st.session_state:
            st.success(f"Code généré : **{st.session_state['generated_code']}**")
            if email_new:
                st.code(f'"{email_new}" = "{st.session_state["generated_code"]}"')
        st.divider()
        st.markdown("####  Journal d'audit (50 dernières actions)")
        try:
            con_adm, _ = _get_conn(); cur_adm = con_adm.cursor()
            cur_adm.execute("SELECT user_email,action,details,ip_hash,created_at FROM audit_log ORDER BY id DESC LIMIT 50")
            audit_rows = cur_adm.fetchall(); con_adm.close()
            if audit_rows:
                tableau_resultats([{
                    "Utilisateur": r[0][:30], "Action": r[1],
                    "Détails": (r[2] or "")[:60], "IP hash": r[3] or "—",
                    "Date": str(r[4])[:16]
                } for r in audit_rows])
            else:
                st.info("Aucune action enregistrée.")
        except Exception as _ea:
            st.caption(f"Journal non disponible (table peut nécessiter une migration) : {_ea}")

    elif admin_pwd:
        st.error(" Mot de passe incorrect")
