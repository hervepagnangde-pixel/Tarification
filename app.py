import streamlit as st
import anthropic
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import json
import secrets as secrets_lib
from PIL import Image

# ════════════════════════════════════════════
# ACCESS CONTROL
# ════════════════════════════════════════════

def get_admin_password():
    try: return st.secrets["admin_password"]
    except: return "Admin@HerveIA2026"

def get_users():
    try: return dict(st.secrets["users"])
    except: return {"demo@herve.ia": "DEMO2026"}

def check_access(email, code):
    return get_users().get(email.lower().strip()) == code.strip()

if "authenticated" not in st.session_state:
    st.session_state["authenticated"] = False

if not st.session_state["authenticated"]:
    try:
        icon = Image.open("icon.png")
        st.set_page_config(page_title="Herve IA", layout="centered", page_icon=icon)
    except:
        st.set_page_config(page_title="Herve IA", layout="centered", page_icon="🎯")

    st.markdown("""
    <style>
    .stApp { background: linear-gradient(135deg, #1a1a1a 0%, #2d8a4e 100%); }
    .stButton > button {
        background-color: #1a1a1a; color: white;
        border: 2px solid #2d8a4e; border-radius: 8px;
        padding: 8px 20px; font-weight: 600;
    }
    .stButton > button:hover { background-color: #2d8a4e; }
    </style>
    """, unsafe_allow_html=True)

    col1, col2, col3 = st.columns([1,2,1])
    with col2:
        st.markdown("<div style='text-align:center; padding:40px 0 20px 0'>", unsafe_allow_html=True)
        st.markdown("# 🎯")
        st.markdown("### Herve IA")
        st.caption("Tarification Réassurance Non-Proportionnelle")
        st.markdown("</div>", unsafe_allow_html=True)
        st.divider()
        email = st.text_input("📧 Adresse email", placeholder="votre@email.com", key="login_email")
        code  = st.text_input("🔑 Code d'accès", type="password", placeholder="CODE123", key="login_code")
        if st.button("Se connecter", type="primary", use_container_width=True):
            if check_access(email, code):
                st.session_state["authenticated"] = True
                st.session_state["user_email"]    = email
                st.rerun()
            else:
                st.error("❌ Email ou code d'accès incorrect")
        st.caption("Accès réservé. Contactez l'administrateur.")
    st.stop()

# ════════════════════════════════════════════
# APP CONFIG
# ════════════════════════════════════════════
try:
    icon = Image.open("icon.png")
    st.set_page_config(page_title="Atlantic Re", layout="wide", page_icon=icon)
except:
    st.set_page_config(page_title="Atlantic Re", layout="wide", page_icon="🎯")

st.markdown("""
<style>
/* ── BASE ── */
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700&display=swap');

* { font-family: 'Inter', sans-serif; }
.stApp { background-color: #f4f6f4; }

/* ── SCROLLBAR ── */
::-webkit-scrollbar { width: 6px; height: 6px; }
::-webkit-scrollbar-track { background: #f1f1f1; }
::-webkit-scrollbar-thumb { background: #2d8a4e; border-radius: 3px; }

/* ── TITRES ── */
h1 { color: #1a1a1a; font-weight: 700; letter-spacing: -0.5px; }
h2 { color: #1a1a1a; border-bottom: 3px solid #2d8a4e;
     padding-bottom: 10px; margin-bottom: 20px; font-weight: 600; }
h3 { color: #2d8a4e; font-weight: 600; }

/* ── BOUTONS ── */
.stButton > button {
    background: linear-gradient(135deg, #1a1a1a 0%, #2d2d2d 100%);
    color: white; border: none; border-radius: 8px;
    padding: 10px 24px; font-weight: 600; font-size: 14px;
    letter-spacing: 0.3px; transition: all 0.25s ease;
    box-shadow: 0 2px 8px rgba(0,0,0,0.15);
}
.stButton > button:hover {
    background: linear-gradient(135deg, #2d8a4e 0%, #25a85e 100%);
    transform: translateY(-2px);
    box-shadow: 0 6px 16px rgba(45,138,78,0.35);
}
.stButton > button:active { transform: translateY(0px); }

/* Bouton primary (type="primary") */
.stButton > button[kind="primary"] {
    background: linear-gradient(135deg, #2d8a4e 0%, #25a85e 100%);
    box-shadow: 0 2px 8px rgba(45,138,78,0.3);
}
.stButton > button[kind="primary"]:hover {
    background: linear-gradient(135deg, #1a1a1a 0%, #2d2d2d 100%);
    box-shadow: 0 6px 16px rgba(0,0,0,0.25);
}

/* ── TABS ── */
.stTabs [data-baseweb="tab-list"] {
    background: #1a1a1a; border-radius: 12px;
    padding: 6px; gap: 4px;
    box-shadow: 0 4px 12px rgba(0,0,0,0.2);
}
.stTabs [data-baseweb="tab"] {
    color: #888; font-weight: 500; font-size: 13px;
    border-radius: 8px; padding: 8px 16px;
    transition: all 0.2s ease;
}
.stTabs [data-baseweb="tab"]:hover { color: white; background: rgba(255,255,255,0.1); }
.stTabs [aria-selected="true"] {
    background: linear-gradient(135deg, #2d8a4e, #25a85e) !important;
    color: white !important; border-radius: 8px;
    box-shadow: 0 2px 8px rgba(45,138,78,0.4);
}

/* ── SIDEBAR ── */
[data-testid="stSidebar"] {
    background: linear-gradient(180deg, #1a1a1a 0%, #2a2a2a 100%);
    border-right: 1px solid #2d8a4e;
}
[data-testid="stSidebar"] * { color: #e0e0e0 !important; }
[data-testid="stSidebar"] h1,
[data-testid="stSidebar"] h2,
[data-testid="stSidebar"] h3 {
    color: #2d8a4e !important;
    border-bottom: 1px solid #333 !important;
}
[data-testid="stSidebar"] .stTextInput input,
[data-testid="stSidebar"] .stNumberInput input {
    background: #2a2a2a; border: 1px solid #444;
    color: white !important; border-radius: 6px;
}
[data-testid="stSidebar"] .stTextInput input:focus,
[data-testid="stSidebar"] .stNumberInput input:focus {
    border-color: #2d8a4e;
    box-shadow: 0 0 0 2px rgba(45,138,78,0.3);
}

/* ── METRICS ── */
[data-testid="stMetric"] {
    background: white; border-radius: 12px;
    padding: 16px 20px; border: 1px solid #e8e8e8;
    box-shadow: 0 2px 8px rgba(0,0,0,0.06);
    border-left: 4px solid #2d8a4e;
    transition: transform 0.2s ease;
}
[data-testid="stMetric"]:hover { transform: translateY(-2px); box-shadow: 0 6px 16px rgba(0,0,0,0.1); }
[data-testid="stMetricLabel"] { color: #666 !important; font-size: 13px !important; font-weight: 500 !important; }
[data-testid="stMetricValue"] { color: #1a1a1a !important; font-weight: 700 !important; }

/* ── DATAFRAMES ── */
[data-testid="stDataFrame"] {
    border-radius: 12px; overflow: hidden;
    box-shadow: 0 2px 12px rgba(0,0,0,0.08);
    border: 1px solid #e8e8e8;
}

/* ── INPUTS ── */
.stTextInput input, .stNumberInput input, .stTextArea textarea {
    border: 1.5px solid #e0e0e0; border-radius: 8px;
    padding: 10px 14px; font-size: 14px;
    transition: all 0.2s ease; background: white;
}
.stTextInput input:focus, .stNumberInput input:focus, .stTextArea textarea:focus {
    border-color: #2d8a4e;
    box-shadow: 0 0 0 3px rgba(45,138,78,0.15);
    outline: none;
}

/* ── SELECTBOX ── */
.stSelectbox > div > div {
    border: 1.5px solid #e0e0e0; border-radius: 8px;
    transition: border-color 0.2s;
}
.stSelectbox > div > div:hover { border-color: #2d8a4e; }

/* ── EXPANDER ── */
.streamlit-expanderHeader {
    background: white; border-radius: 10px;
    border: 1px solid #e8e8e8; font-weight: 500;
    color: #1a1a1a; padding: 12px 16px;
    box-shadow: 0 1px 4px rgba(0,0,0,0.06);
    transition: all 0.2s ease;
}
.streamlit-expanderHeader:hover { border-color: #2d8a4e; color: #2d8a4e; }
.streamlit-expanderContent {
    border: 1px solid #e8e8e8; border-top: none;
    border-radius: 0 0 10px 10px;
    background: #fafafa; padding: 16px;
}

/* ── ALERTS ── */
.stSuccess { background: #f0fff4; border-left: 4px solid #2d8a4e; border-radius: 8px; }
.stWarning { background: #fffbf0; border-left: 4px solid #f59e0b; border-radius: 8px; }
.stError   { background: #fff0f0; border-left: 4px solid #ef4444; border-radius: 8px; }
.stInfo    { background: #f0f8ff; border-left: 4px solid #3b82f6; border-radius: 8px; }

/* ── DIVIDER ── */
hr { border: none; border-top: 2px solid #e8e8e8; margin: 20px 0; }

/* ── PROGRESS BAR ── */
.stProgress > div > div { background: linear-gradient(90deg, #2d8a4e, #25a85e); border-radius: 4px; }
.stProgress > div { background: #e8e8e8; border-radius: 4px; }

/* ── CHECKBOX & RADIO ── */
.stCheckbox label, .stRadio label { font-weight: 500; color: #333; }
</style>
""", unsafe_allow_html=True)

def card(titre, valeur, couleur="#2d8a4e", icone="📊"):
    st.markdown(f"""
    <div style="
        background: white; border-radius: 12px;
        padding: 20px 24px; border: 1px solid #e8e8e8;
        border-left: 5px solid {couleur};
        box-shadow: 0 2px 8px rgba(0,0,0,0.06);
        margin-bottom: 12px;
    ">
        <div style="font-size:12px; color:#888; font-weight:500; text-transform:uppercase; letter-spacing:0.5px; margin-bottom:6px">
            {icone} {titre}
        </div>
        <div style="font-size:24px; font-weight:700; color:#1a1a1a">{valeur}</div>
    </div>
    """, unsafe_allow_html=True)


def badge(texte, couleur="green"):
    couleurs = {
        "green" : ("rgba(45,138,78,0.12)",  "#2d8a4e"),
        "black" : ("rgba(26,26,26,0.08)",   "#1a1a1a"),
        "orange": ("rgba(245,158,11,0.12)", "#f59e0b"),
        "red"   : ("rgba(239,68,68,0.12)",  "#ef4444"),
        "blue"  : ("rgba(59,130,246,0.12)", "#3b82f6"),
    }
    bg, fg = couleurs.get(couleur, couleurs["green"])
    st.markdown(f"""
    <span style="
        background:{bg}; color:{fg};
        padding: 4px 12px; border-radius: 20px;
        font-size: 12px; font-weight: 600;
        display: inline-block; margin: 2px;
    ">{texte}</span>
    """, unsafe_allow_html=True)


def section_header(titre, sous_titre="", icone=""):
    st.markdown(f"""
    <div style="
        background: linear-gradient(135deg, #1a1a1a 0%, #2d2d2d 100%);
        border-radius: 12px; padding: 20px 24px;
        margin-bottom: 20px;
        box-shadow: 0 4px 12px rgba(0,0,0,0.15);
    ">
        <div style="font-size:20px; font-weight:700; color:white">
            {icone} {titre}
        </div>
        {f'<div style="font-size:13px; color:#aaa; margin-top:4px">{sous_titre}</div>' if sous_titre else ''}
    </div>
    """, unsafe_allow_html=True)


def alerte_box(message, type_alerte="info"):
    configs = {
        "info"   : ("ℹ️", "#3b82f6", "rgba(59,130,246,0.08)"),
        "success": ("✅", "#2d8a4e", "rgba(45,138,78,0.08)"),
        "warning": ("⚠️", "#f59e0b", "rgba(245,158,11,0.08)"),
        "error"  : ("❌", "#ef4444", "rgba(239,68,68,0.08)"),
    }
    icon, color, bg = configs.get(type_alerte, configs["info"])
    st.markdown(f"""
    <div style="
        background:{bg}; border-left: 4px solid {color};
        border-radius: 0 8px 8px 0; padding: 14px 18px;
        margin: 8px 0; font-size: 14px; color: #333;
    ">
        {icon} {message}
    </div>
    """, unsafe_allow_html=True)


def tableau_resultats(donnees, titre=""):
    """Affiche un tableau HTML stylisé"""
    if not donnees: return
    if titre:
        st.markdown(f"<h4 style='color:#1a1a1a; margin-bottom:12px'>{titre}</h4>", unsafe_allow_html=True)
    colonnes = list(donnees[0].keys())
    html = """
    <div style="overflow-x:auto; border-radius:12px; box-shadow:0 2px 12px rgba(0,0,0,0.08);">
    <table style="width:100%; border-collapse:collapse; font-size:13px;">
    <thead>
    <tr style="background:linear-gradient(135deg,#1a1a1a,#2d2d2d)">
    """
    for col in colonnes:
        html += f'<th style="padding:12px 16px; text-align:left; color:white; font-weight:600; letter-spacing:0.3px">{col}</th>'
    html += "</tr></thead><tbody>"
    for i, row in enumerate(donnees):
        bg = "white" if i % 2 == 0 else "#f9fafb"
        html += f'<tr style="background:{bg}; transition:background 0.15s" onmouseover="this.style.background=\'#f0fff4\'" onmouseout="this.style.background=\'{bg}\'">'
        for col in colonnes:
            val = row.get(col, "")
            color = "#1a1a1a"
            if "%" in str(val) and any(c.isdigit() for c in str(val)):
                try:
                    num = float(str(val).replace("%",""))
                    if num > 5: color = "#ef4444"
                    elif num > 2: color = "#f59e0b"
                    else: color = "#2d8a4e"
                except: pass
            if "✅" in str(val): color = "#2d8a4e"
            if "⚠️" in str(val): color = "#f59e0b"
            html += f'<td style="padding:11px 16px; border-bottom:1px solid #f0f0f0; color:{color}; font-weight:500">{val}</td>'
        html += "</tr>"
    html += "</tbody></table></div>"
    st.markdown(html, unsafe_allow_html=True)


def progress_steps(steps, current):
    """Barre de progression par étapes"""
    html = '<div style="display:flex; align-items:center; gap:0; margin:16px 0; overflow-x:auto">'
    for i, (label, done) in enumerate(steps):
        is_current = (i == current)
        if done:
            bg, fg, border = "#2d8a4e", "white", "#2d8a4e"
        elif is_current:
            bg, fg, border = "#1a1a1a", "white", "#1a1a1a"
        else:
            bg, fg, border = "white", "#999", "#ddd"
        html += f"""
        <div style="display:flex; align-items:center; flex:1; min-width:80px">
            <div style="
                background:{bg}; color:{fg}; border: 2px solid {border};
                border-radius:20px; padding:6px 12px;
                font-size:11px; font-weight:600; white-space:nowrap;
                text-align:center; width:100%;
            ">{'✓ ' if done else ''}{label}</div>
            {'<div style="height:2px; background:#ddd; flex:1; min-width:8px"></div>' if i < len(steps)-1 else ''}
        </div>
        """
    html += "</div>"
    st.markdown(html, unsafe_allow_html=True)

# ════════════════════════════════════════════
# PROMPT ENGINEERING
# ════════════════════════════════════════════

def prompt_inputs(key_prefix, placeholder_contexte="", placeholder_instructions="",
                  placeholder_input="", placeholder_output=""):
    with st.expander("✏️ Personnaliser le prompt Claude", expanded=False):
        st.markdown("##### 🎯 Prompt Engineering")
        c1, c2 = st.columns(2)
        with c1:
            contexte = st.text_area(
                "📌 Contexte",
                placeholder=placeholder_contexte or "Ex: Portefeuille automobile Maroc 2026...",
                height=80, key=f"{key_prefix}_contexte",
                help="Informations de contexte sur le portefeuille, le marché, l'historique"
            )
            instructions = st.text_area(
                "📋 Instructions spécifiques",
                placeholder=placeholder_instructions or "Ex: Être attentif à la tranche Cat L1...",
                height=80, key=f"{key_prefix}_instructions",
                help="Directives spécifiques pour cette analyse"
            )
        with c2:
            input_data = st.text_area(
                "📥 Données supplémentaires",
                placeholder=placeholder_input or "Ex: Taux marché de référence : 3.2%...",
                height=80, key=f"{key_prefix}_input",
                help="Données additionnelles non présentes dans les fichiers"
            )
            output_instructions = st.text_area(
                "📤 Format de sortie souhaité",
                placeholder=placeholder_output or "Ex: Tableau structuré + recommandation chiffrée...",
                height=80, key=f"{key_prefix}_output",
                help="Comment structurer la réponse de Claude"
            )
    return contexte, instructions, input_data, output_instructions


def build_prompt(role, task, data, contexte="", instructions="",
                 input_data="", output_instructions="",
                 contexte_global="", exemples="", contraintes=""):
    prompt = f"""
════════════════════════════════════════════
RÔLE
════════════════════════════════════════════
{role}

════════════════════════════════════════════
RÈGLES ABSOLUES — RESPECTER IMPÉRATIVEMENT
════════════════════════════════════════════
1. ANTI-HALLUCINATION :
   Ne jamais inventer de chiffres, de faits ou de références.
   Si une information est manquante ou incertaine, écrire EXPLICITEMENT :
   "Information insuffisante pour conclure sur ce point."
   Ne jamais extrapoler au-delà des données fournies.

2. RAISONNEMENT STRUCTURÉ :
   Avant chaque conclusion, montrer le raisonnement étape par étape.
   Format obligatoire : [Observation] → [Analyse] → [Conclusion]
   Ne jamais donner une conclusion sans la justifier par des chiffres.

3. CONTRAINTES MÉTIER :
{contraintes if contraintes else """   - Les taux techniques doivent être positifs et inférieurs à 50%
   - Un écart BC/Simulation > 25% est systématiquement signalé ⚠️
   - Ne pas recommander un taux inférieur au taux pur calculé
   - Pour les tranches cat : la market curve prime sur le BC historique
   - BC = 0 pour tranche cat est NORMAL, ne pas le signaler comme anomalie
   - Signaler tout résultat qui semble mathématiquement incohérent"""}

4. ITÉRATION ET VÉRIFICATION :
   Avant de finaliser la réponse, vérifier :
   ✓ Les chiffres cités sont-ils présents dans les données fournies ?
   ✓ Les recommandations sont-elles cohérentes entre tranches ?
   ✓ Y a-t-il des contradictions dans l'analyse ?
   ✓ Les taux respectent-ils la hiérarchie : taux_pur < taux_risque < taux_technique ?
   Si non, corriger avant de répondre.

5. ANCRAGE PAR EXEMPLES :
{exemples if exemples else """   Exemple de BONNE recommandation :
   "La tranche Risk & Cat affiche un taux BC de 2.94% et simulation de 3.98%.
    L'écart de 35% [Observation] suggère que le BC sous-estime le risque actuel,
    probablement dû à l'inflation sinistres non capturée [Analyse].
    → Retenir le taux simulation de 3.98% avec mention au comité [Conclusion]."

   Exemple de MAUVAISE recommandation (à éviter) :
   "Le taux est acceptable." ← pas de raisonnement, pas de chiffres."""}

════════════════════════════════════════════
CONTEXTE GÉNÉRAL DU PORTEFEUILLE
════════════════════════════════════════════
{contexte_global if contexte_global else "Non fourni — raisonner uniquement sur les données."}

════════════════════════════════════════════
CONTEXTE SPÉCIFIQUE
════════════════════════════════════════════
{contexte if contexte else "Aucun contexte spécifique fourni."}

════════════════════════════════════════════
TÂCHE
════════════════════════════════════════════
{task}

════════════════════════════════════════════
DONNÉES D'ENTRÉE
════════════════════════════════════════════
{data}
{f"""
DONNÉES SUPPLÉMENTAIRES :
{input_data}""" if input_data else ""}

════════════════════════════════════════════
INSTRUCTIONS SPÉCIFIQUES
════════════════════════════════════════════
{instructions if instructions else "Suivre la tâche telle que décrite ci-dessus."}

════════════════════════════════════════════
FORMAT DE SORTIE ATTENDU
════════════════════════════════════════════
{output_instructions if output_instructions else """
Structure ta réponse ainsi :
1. SYNTHÈSE (2-3 phrases max)
2. ANALYSE PAR TRANCHE
   - Observations factuelles (chiffres)
   - Raisonnement [→]
   - Recommandation chiffrée
3. POINTS D'ATTENTION (anomalies, incertitudes)
4. CONCLUSION (verdict final avec taux retenus)"""}

Rappel final : La précision prime sur l'exhaustivité.
Si incertain → le dire plutôt qu'inventer.
════════════════════════════════════════════
"""
    return prompt.strip()


# ════════════════════════════════════════════
# HEADER + SIDEBAR
# ════════════════════════════════════════════

st.title("Atlantic Re")
st.caption(f"Connecté : {st.session_state.get('user_email','')} | Burning cost · Simulation · Market curve · IA")

with st.sidebar:
    if st.button("🚪 Déconnexion"):
        st.session_state["authenticated"] = False
        st.rerun()
    st.markdown("### ⚙️ Configuration")
    api_key = st.text_input("🔑 Clé API Claude", type="password", placeholder="sk-ant-...")
    gnpi    = st.number_input("💰 GNPI (MAD)", value=183_000_000, step=1_000_000)
    st.divider()
    st.markdown("### 📊 Statut des étapes")
    for nom, key in [("Programme","df_prog"),("Données","df_liq"),
                     ("Burning cost","resultats_bc"),("Simulation","resultats_sim"),
                     ("Market curve","resultats_mkt")]:
        st.markdown(f"{'✅' if key in st.session_state else '⬜'} {nom}")
    st.divider()
    st.markdown("### 🌍 Contexte global")
    instructions_globales = st.text_area(
        "Contexte portefeuille",
        placeholder="Ex: Portefeuille automobile Maroc, forte croissance 2023...",
        height=120, key="instructions_globales",
        help="Inclus dans TOUS les prompts Claude"
    )

# ════════════════════════════════════════════
# TABS
# ════════════════════════════════════════════

tab1, tab2, tab3, tab4, tab5, tab6, tab_admin = st.tabs([
    "📋 Programme", "📂 Données & Triangle",
    "🔥 Burning Cost", "🎲 Simulation",
    "📈 Market Curve", "📋 Rapport Final", "🔐 Admin"
])

etapes_progress = [
    ("Programme",    "df_prog"       in st.session_state),
    ("Triangle",     "df_liq"        in st.session_state),
    ("Burning Cost", "resultats_bc"  in st.session_state),
    ("Simulation",   "resultats_sim" in st.session_state),
    ("Market Curve", "resultats_mkt" in st.session_state),
]
progress_steps(etapes_progress, current=0)  # 0=Programme, 1=Triangle, etc.

# ════════════════════════════════════════════
# TAB 1 — PROGRAMME
# ════════════════════════════════════════════

with tab1:
    st.header("Programme de Réassurance")
    st.caption("Définissez les tranches, conditions et paramètres de chargement")
    nb_tranches = st.number_input("Nombre de tranches", min_value=1, max_value=10, value=3)
    tranches_input = []

    for i in range(nb_tranches):
        with st.expander(f"🔷 Tranche {i+1}", expanded=(i==0)):
            c1, c2, c3 = st.columns(3)
            with c1:
                st.markdown("**Identification**")
                nom      = st.text_input("Nom",             value=f"Tranche {i+1}", key=f"nom_{i}")
                type_t   = st.selectbox("Type",             ["travaillante","non_travaillante","cat"], key=f"type_{i}")
                priorite = st.number_input("Priorité (MAD)",value=2_000_000,  step=500_000, key=f"prio_{i}", format="%d")
                portee   = st.number_input("Portée (MAD)",  value=13_000_000, step=500_000, key=f"port_{i}", format="%d")
            with c2:
                st.markdown("**Conditions contractuelles**")
                has_aal     = st.checkbox("AAL", key=f"aal_{i}")
                aal_val     = st.number_input("Montant AAL", value=0, step=100_000, key=f"aal_v_{i}", disabled=not has_aal)
                has_aad     = st.checkbox("AAD", key=f"aad_{i}")
                aad_val     = st.number_input("Montant AAD", value=0, step=100_000, key=f"aad_v_{i}", disabled=not has_aad)
                has_indices = st.checkbox("Clause d'indexation", key=f"idx_{i}")
            with c3:
                st.markdown("**Frais & Reconstitutions**")
                nb_recon     = st.number_input("Nb reconstitutions",    value=1,   min_value=0, max_value=5,   key=f"recon_{i}")
                tx_recon     = st.number_input("Taux reconstitution %", value=100, min_value=0, max_value=200, key=f"txrecon_{i}")
                brokage      = st.number_input("Brokage %",             value=10,  min_value=0, max_value=30,  key=f"brok_{i}")
                frais        = st.number_input("Frais généraux %",      value=5,   min_value=0, max_value=20,  key=f"frais_{i}")
                marge        = st.number_input("Marge %",               value=10,  min_value=0, max_value=30,  key=f"marge_{i}")
                retrocession = st.number_input("Rétrocession %",        value=0,   min_value=0, max_value=50,  key=f"retro_{i}")

        tranches_input.append({
            "numero": i+1, "nom": nom, "type": type_t,
            "priorite": priorite, "portee": portee,
            "AAL": aal_val if has_aal else None,
            "AAD": aad_val if has_aad else None,
            "nb_reconstitutions": nb_recon, "taux_reconstitution": tx_recon,
            "indices": has_indices,
            "brokage": brokage/100, "frais": frais/100,
            "marge": marge/100, "retrocession": retrocession/100
        })

    if st.button("💾 Valider le programme", type="primary"):
        st.session_state["tranches_input"] = tranches_input
        st.session_state["df_prog"] = pd.DataFrame([{
            "Tranche"  : t["nom"], "Type"    : t["type"],
            "Priorité" : f"{t['priorite']:,}", "Portée": f"{t['portee']:,}",
            "AAL"      : f"{t['AAL']:,}" if t["AAL"] else "—",
            "AAD"      : f"{t['AAD']:,}" if t["AAD"] else "—",
            "Reconst." : f"{t['nb_reconstitutions']} x {t['taux_reconstitution']}%",
            "Indices"  : "✅" if t["indices"] else "—",
            "Brokage"  : f"{t['brokage']:.0%}", "Marge": f"{t['marge']:.0%}",
        } for t in tranches_input])
        st.success("✅ Programme validé !")

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

    type_branche = st.radio(
        "Type de branche",
        ["Développement long (As-If + Stabilisation + Projection CL)",
         "Développement court (As-If uniquement, pas de projection)"],
        key="type_branche", horizontal=True
    )
    is_long = "long" in type_branche

    c1, c2, c3 = st.columns(3)
    with c1: f_triangle = st.file_uploader("📁 Triangle développement", type=["xlsx","csv"], key="f_tri")
    with c2: f_gnpis    = st.file_uploader("📁 Base GNPIs",             type=["xlsx","csv"], key="f_gnp")
    with c3: f_indices  = st.file_uploader("📁 Table indices",          type=["xlsx","csv"], key="f_idx")

    annee_cotation = st.number_input("Année de cotation (n)", value=2026, step=1,
                                      help="I_cotation fixe pour la stabilisation")

    if st.button("▶ Transformer le triangle", type="primary") and f_triangle and f_gnpis and f_indices:
        with st.spinner("🔄 Transformation en cours..."):
            progress = st.progress(0, text="Lecture des fichiers...")

            df_gnpis_df = pd.read_excel(f_gnpis)  if f_gnpis.name.endswith('xlsx')   else pd.read_csv(f_gnpis)
            df_idx_df   = pd.read_excel(f_indices) if f_indices.name.endswith('xlsx') else pd.read_csv(f_indices)
            df_gnpis_df.columns = [c.strip() for c in df_gnpis_df.columns]
            df_idx_df.columns   = [c.strip() for c in df_idx_df.columns]

            progress.progress(15, text="Parsing du triangle...")
            df_raw       = pd.read_excel(f_triangle, header=None)
            ligne_annees = df_raw.iloc[0].tolist()
            ligne_types  = df_raw.iloc[1].tolist()

            annee_courante = None
            col_info = []
            for i, (ann, typ) in enumerate(zip(ligne_annees, ligne_types)):
                if i == 0: col_info.append(('UW_YEAR', '')); continue
                try:
                    a = int(float(str(ann)))
                    if 2010 <= a <= 2035: annee_courante = a
                except: pass
                typ_clean = str(typ).strip().upper() if pd.notna(typ) else ''
                col_info.append((annee_courante, typ_clean))

            df_data = df_raw.iloc[2:].reset_index(drop=True)
            df_data.iloc[:, 0] = df_data.iloc[:, 0].ffill()

            progress.progress(30, text="Extraction des TOTAL...")
            records = []
            for idx_row, row in df_data.iterrows():
                try:
                    annee_surv = int(float(str(row.iloc[0])))
                    if not (2010 <= annee_surv <= 2035): continue
                except: continue
                sinistre_id = f"{annee_surv}_{idx_row}"
                for col_idx, (annee_reg, typ) in enumerate(col_info):
                    if typ != 'TOTAL' or annee_reg is None: continue
                    val = row.iloc[col_idx]
                    try:
                        if isinstance(val, str):
                            val = val.strip().replace(',','.').replace(' ','')
                            if any(c.isalpha() for c in val) or '#' in val: continue
                        val = float(val)
                        if val <= 0 or np.isnan(val): continue
                    except: continue
                    dev = annee_reg - annee_surv
                    if dev < 0 or dev > 9: continue
                    records.append({'sinistre_id': sinistre_id, 'annee_surv': annee_surv,
                                    'annee_reg': annee_reg, 'dev': dev, 'total': val})

            df_liq = pd.DataFrame(records)

            progress.progress(45, text="Calcul As-If...")
            df_idx_set     = df_idx_df.set_index('Annee')['Coefficients']
            I_cotation_val = float(df_idx_set.get(annee_cotation, 1.0))

            def get_indice(annee):
                try: return float(df_idx_set[annee])
                except: return 1.0

            # As-If : Sk = total × (I_ultime / I_reg)
            df_liq['annee_ultime'] = df_liq['annee_surv'] + 9
            df_liq['I_ultime']     = df_liq['annee_ultime'].apply(get_indice)
            df_liq['I_reg']        = df_liq['annee_reg'].apply(get_indice)
            df_liq['I_surv']       = df_liq['annee_surv'].apply(get_indice)
            df_liq['Sk']           = df_liq['total'] * (df_liq['I_ultime'] / df_liq['I_reg'])

            if is_long:
                progress.progress(50, text="Stabilisation...")
                # S'k = Sk × (I_surv / I_cotation) si (I_cotation/I_surv - 1) > 10%
                df_liq['ratio_check'] = I_cotation_val / df_liq['I_surv']
                df_liq['S_prime_k']   = np.where(
                    (df_liq['ratio_check'] - 1) > 0.10,
                    df_liq['Sk'] * (df_liq['I_surv'] / I_cotation_val),
                    df_liq['Sk']
                )
                df_liq['coeff_stab'] = np.where(
                    df_liq['S_prime_k'] > 0,
                    df_liq['Sk'] / df_liq['S_prime_k'],
                    1.0
                )

                progress.progress(60, text="Chain Ladder individuel sur S'k...")
                facteurs = {k: [] for k in range(9)}
                for sin_id, grp in df_liq.groupby('sinistre_id'):
                    grp = grp.sort_values('dev').set_index('dev')
                    for k in range(9):
                        if k in grp.index and (k+1) in grp.index:
                            t_k  = grp.loc[k,   'S_prime_k']
                            t_k1 = grp.loc[k+1, 'S_prime_k']
                            if t_k > 0:
                                f = t_k1 / t_k
                                if 0.9 <= f <= 2.5: facteurs[k].append(f)

                f_moyens = {k: np.mean(facteurs[k]) if facteurs[k] else 1.0 for k in range(9)}

                progress.progress(75, text="Projection S'k à l'ultime...")
                projections = []
                for sin_id, grp in df_liq.groupby('sinistre_id'):
                    grp = grp.sort_values('dev').set_index('dev')
                    annee_surv_p   = grp['annee_surv'].iloc[0]
                    dev_max        = grp.index.max()
                    Sprime_actuel  = grp.loc[dev_max, 'S_prime_k']
                    coeff_sin      = grp.loc[dev_max, 'coeff_stab']
                    Sprime_ultime  = Sprime_actuel
                    for k in range(dev_max, 9):
                        Sprime_ultime *= f_moyens[k]
                    Sk_ultime = Sprime_ultime * coeff_sin
                    projections.append({
                        'sinistre_id'  : sin_id,
                        'annee_surv'   : annee_surv_p,
                        'dev_max'      : dev_max,
                        'Sprime_ultime': Sprime_ultime,
                        'Sk_ultime'    : Sk_ultime,
                        'coeff_stab'   : coeff_sin
                    })
                df_facteurs_df = pd.DataFrame({
                    'Dev.'           : [f"{k}→{k+1}" for k in range(9)],
                    'Facteur moyen'  : [round(f_moyens[k], 4) for k in range(9)],
                    'Nb observations': [len(facteurs[k]) for k in range(9)]
                })

            else:
                progress.progress(60, text="Branche courte — As-If direct...")
                df_liq['S_prime_k']  = df_liq['Sk']
                df_liq['coeff_stab'] = 1.0
                f_moyens = {k: 1.0 for k in range(9)}
                projections = []
                for sin_id, grp in df_liq.groupby('sinistre_id'):
                    grp = grp.sort_values('dev').set_index('dev')
                    annee_surv_p = grp['annee_surv'].iloc[0]
                    dev_max      = grp.index.max()
                    Sk_actuel    = grp.loc[dev_max, 'Sk']
                    projections.append({
                        'sinistre_id'  : sin_id,
                        'annee_surv'   : annee_surv_p,
                        'dev_max'      : dev_max,
                        'Sprime_ultime': Sk_actuel,
                        'Sk_ultime'    : Sk_actuel,
                        'coeff_stab'   : 1.0
                    })
                df_facteurs_df = pd.DataFrame({'Info': ['Branche courte — pas de projection CL']})

            df_proj = pd.DataFrame(projections)

            progress.progress(88, text="Estimation alpha & lambda...")
            X       = df_proj['Sprime_ultime'].values
            X       = X[X > 0]
            seuil   = np.percentile(X, 85)
            X_above = X[X >= seuil]
            t_min   = np.min(X_above)
            n_above = len(X_above)
            alpha_est = n_above / np.sum(np.log(X_above / t_min))

            df_gnpis_idx = df_gnpis_df.set_index(df_gnpis_df.columns[0])
            gnpi_col     = df_gnpis_df.columns[1]
            N_obs        = df_proj[df_proj['Sprime_ultime'] >= seuil].groupby('annee_surv').size()
            N_asif_vals  = []
            for ann, cnt in N_obs.items():
                try:
                    gnpi_ann = float(df_gnpis_idx.loc[ann, gnpi_col])
                    N_asif_vals.append(cnt * gnpi / gnpi_ann)
                except: N_asif_vals.append(cnt)
            lambda_est = float(np.mean(N_asif_vals)) if N_asif_vals else 5.0

            coeffs_raw = df_proj['coeff_stab'].values
            coeffs     = coeffs_raw[(coeffs_raw > 0) & np.isfinite(coeffs_raw)]

            progress.progress(100, text="Terminé !")

            st.session_state.update({
                "df_liq"        : df_liq,
                "df_proj"       : df_proj,
                "f_moyens"      : f_moyens,
                "alpha_est"     : float(alpha_est),
                "lambda_est"    : float(lambda_est),
                "seuil_est"     : float(seuil),
                "coeffs"        : coeffs,
                "is_long"       : is_long,
                "I_cotation"    : I_cotation_val,
                "annee_cotation": annee_cotation,
                "df_gnpis_df"   : df_gnpis_df,
                "df_facteurs"   : df_facteurs_df
            })

    if "df_liq" in st.session_state:
        c1, c2, c3 = st.columns(3)
        c1.metric("Observations", len(st.session_state['df_liq']))
        c2.metric("Sinistres",    st.session_state['df_liq']['sinistre_id'].nunique())
        c3.metric("Années",       st.session_state['df_liq']['annee_surv'].nunique())

        branch_label = "Longue (As-If + Stab + CL)" if st.session_state.get("is_long") else "Courte (As-If uniquement)"
        st.info(f"🌿 Branche : **{branch_label}** | I_cotation({st.session_state.get('annee_cotation')}) = {st.session_state.get('I_cotation',1):.4f}")
        st.info(f"🔢 Seuil P85: {st.session_state['seuil_est']:,.0f} | Alpha: {st.session_state['alpha_est']:.4f} | Lambda: {st.session_state['lambda_est']:.4f}")

        with st.expander("📊 Triangle de liquidation (Sk & S'k)"):
            cols_show = ['sinistre_id','annee_surv','annee_reg','dev','total','Sk','S_prime_k','coeff_stab']
            st.dataframe(st.session_state["df_liq"][[c for c in cols_show if c in st.session_state["df_liq"].columns]].head(30), use_container_width=True)
        with st.expander("📊 Facteurs Chain Ladder"):
            st.dataframe(st.session_state["df_facteurs"], use_container_width=True)
        with st.expander("📊 Projections"):
            st.dataframe(st.session_state["df_proj"].head(20), use_container_width=True)

# ════════════════════════════════════════════
# TAB 3 — BURNING COST
# ════════════════════════════════════════════

with tab3:
    section_header("Burning Cost", "Charges historiques réassurance par tranche", "🔥")
    st.caption("Ck = min(max(S'k_ultime − D, 0), L) × (Sk/S'k)")

    if "df_proj" not in st.session_state:
        st.warning("⚠️ Transformez d'abord le triangle")
    else:
        if st.button("▶ Calculer le Burning Cost", type="primary"):
            with st.spinner("Calcul en cours..."):
                df_proj      = st.session_state["df_proj"]
                resultats_bc = []

                for t_info in tranches_input:
                    D   = t_info["priorite"]
                    P   = t_info["portee"]
                    aal = t_info["AAL"]
                    aad = t_info["AAD"]
                    r   = t_info["nb_reconstitutions"]
                    cap = (r + 1) * P

                    df_proj['Ck'] = df_proj.apply(
                        lambda row: min(max(row['Sprime_ultime'] - D, 0), P) * row['coeff_stab'],
                        axis=1
                    )

                    charges_ann     = df_proj.groupby('annee_surv')['Ck'].sum()
                    charges_finales = []
                    for ann, ch in charges_ann.items():
                        if aad: ch = max(ch - aad, 0)
                        if aal: ch = min(ch, aal)
                        ch = min(ch, cap)
                        charges_finales.append({'annee': ann, 'charge': ch})

                    df_ch          = pd.DataFrame(charges_finales)
                    charge_moy     = df_ch['charge'].mean()
                    taux_pur       = charge_moy / gnpi
                    taux_risque    = taux_pur * 1.20
                    taux_technique = taux_risque / (1 - t_info["brokage"] - t_info["frais"] - 0.0021)
                    taux_final     = taux_technique * (1 + t_info["marge"] + t_info["retrocession"])

                    resultats_bc.append({
                        "tranche"       : t_info["nom"], "type": t_info["type"],
                        "charge_moy"    : charge_moy,
                        "taux_pur"      : taux_pur,
                        "taux_risque"   : taux_risque,
                        "taux_technique": taux_technique,
                        "taux_final"    : taux_final,
                        "detail_annuel" : df_ch.to_dict('records')
                    })
                st.session_state["resultats_bc"] = resultats_bc

    if "resultats_bc" in st.session_state:
    tableau_resultats([{
        "Tranche"       : r["tranche"],
        "Type"          : r["type"],
        "Charge moy."   : f"{r['charge_moy']:,.0f} MAD",
        "Taux pur"      : f"{r['taux_pur']:.4%}",
        "Taux risque"   : f"{r['taux_risque']:.4%}",
        "Taux technique": f"{r['taux_technique']:.4%}",
        "Taux final"    : f"{r['taux_final']:.4%}",
    } for r in st.session_state["resultats_bc"]], titre="📊 Résultats Burning Cost")

        st.divider()
        st.markdown("### 🤖 Analyse Claude — Burning Cost")
        ctx_bc, inst_bc, inp_bc, out_bc = prompt_inputs(
            key_prefix="bc",
            placeholder_contexte="Ex: Sinistralité exceptionnelle 2020, portefeuille en croissance...",
            placeholder_instructions="Ex: Comparer avec taux marché de référence 3-4%...",
            placeholder_input="Ex: Taux BC année précédente : R&C=2.5%",
            placeholder_output="Ex: Tableau par tranche + verdict OK/ALERTE/RÉVISER"
        )

        if api_key and st.button("🤖 Recommandations Claude — BC"):
            with st.spinner("Claude analyse..."):
                prompt = build_prompt(
                    role="Expert actuaire senior en réassurance non-proportionnelle automobile, 15 ans d'expérience en tarification XL et cat.",
                    task="""Analyse les résultats de Burning Cost par tranche.
Pour chaque tranche :
1. Évalue le niveau du taux (élevé/normal/faible vs normes marché)
2. Vérifie la cohérence entre tranches (progression logique priorité/taux)
3. Identifie les anomalies ou données suspectes
4. Donne un verdict : ✅ Cohérent | ⚠️ À vérifier | ❌ Problème""",
                    data=f"""Résultats BC :
{json.dumps([{k:v for k,v in r.items() if k!='detail_annuel'} for r in st.session_state['resultats_bc']], indent=2)}
Programme : {json.dumps(tranches_input, indent=2)}
GNPI : {gnpi:,} MAD
Formule : Ck = min(max(S'k_ultime−D,0),L) × (Sk/S'k)""",
                    contexte=ctx_bc, instructions=inst_bc,
                    input_data=inp_bc, output_instructions=out_bc,
                    contexte_global=st.session_state.get("instructions_globales",""),
                    contraintes="""- Taux pur BC négatif = erreur de calcul à signaler
- BC = 0 pour tranche cat est NORMAL
- Vérifier hiérarchie : taux_pur < taux_risque < taux_technique < taux_final
- Ne jamais inventer de comparatifs marché non fournis"""
                )
                client  = anthropic.Anthropic(api_key=api_key)
                analyse = client.messages.create(model="claude-opus-4-5", max_tokens=2000,
                    messages=[{"role":"user","content":prompt}])
                st.session_state["analyse_bc"] = analyse.content[0].text

        if "analyse_bc" in st.session_state:
            st.markdown(st.session_state["analyse_bc"])

# ════════════════════════════════════════════
# TAB 4 — SIMULATION
# ════════════════════════════════════════════

with tab4:
    st.header("Simulation Pareto / Poisson")
    st.caption("Simule S'0 sur Pareto — applique coeff Sk/S'k pour charge réassurance")

    if "alpha_est" not in st.session_state:
        st.warning("⚠️ Transformez d'abord le triangle")
    else:
        is_long_sim = st.session_state.get("is_long", True)
        st.info(f"🌿 Branche {'longue' if is_long_sim else 'courte'} | Seuil P85: {st.session_state['seuil_est']:,.0f} | Alpha: {st.session_state['alpha_est']:.4f} | Lambda: {st.session_state['lambda_est']:.4f}")

        c1, c2, c3, c4 = st.columns(4)
        with c1: alpha_final  = st.number_input("Alpha",          value=st.session_state["alpha_est"],  step=0.01,     format="%.4f", key="alpha_input")
        with c2: lambda_final = st.number_input("Lambda",         value=st.session_state["lambda_est"], step=0.1,      format="%.4f", key="lambda_input")
        with c3: seuil_final  = st.number_input("Seuil (MAD)",    value=st.session_state["seuil_est"],  step=50_000.0, format="%.0f", key="seuil_input")
        with c4: n_sim        = st.number_input("Nb simulations",  value=10000, step=1000,               key="nsim_input")

        if st.button("▶ Lancer la simulation", type="primary"):
            with st.spinner("🎲 Simulation en cours..."):
                progress_sim = st.progress(0, text="Initialisation...")
                alpha_f  = st.session_state["alpha_input"]
                lambda_f = st.session_state["lambda_input"]
                seuil_f  = st.session_state["seuil_input"]
                n_s      = int(st.session_state["nsim_input"])
                coeffs   = st.session_state["coeffs"]
                np.random.seed(42)
                resultats_sim = []

                for idx_t, t_info in enumerate(tranches_input):
                    progress_sim.progress(int((idx_t/len(tranches_input))*100),
                                          text=f"Simulation {t_info['nom']}...")
                    D   = t_info["priorite"]
                    P   = t_info["portee"]
                    r   = t_info["nb_reconstitutions"]
                    aal = t_info["AAL"]
                    aad = t_info["AAD"]
                    cap = (r + 1) * P

                    def simuler(avec_aal, avec_aad, avec_rec):
                        charges = []
                        for _ in range(n_s):
                            N = np.random.poisson(lambda_f)
                            S_total = 0
                            if N > 0:
                                U          = np.random.uniform(size=N)
                                Sprime_sim = seuil_f * (U ** (-1/alpha_f))
                                idx_c      = np.random.choice(len(coeffs), size=N, replace=True)
                                for i in range(N):
                                    S_prime = Sprime_sim[i]
                                    c       = coeffs[idx_c[i]]
                                    if   S_prime <= D:       S_i = 0
                                    elif S_prime <= D + P:   S_i = c * (S_prime - D)
                                    else:                    S_i = c * P
                                    S_total += S_i
                            ch = S_total
                            if avec_aad and aad: ch = max(ch - aad, 0)
                            if avec_aal and aal: ch = min(ch, aal)
                            charges.append(min(ch, cap) if avec_rec else ch)
                        return np.array(charges)

                    def calc_taux(ch):
                        P0 = np.mean(ch); sig = np.std(ch)
                        tp = P0 / gnpi
                        tr = (P0 + 0.2 * sig) / gnpi
                        tt = tr / (1 - t_info["brokage"] - t_info["frais"] - 0.0021)
                        tf = tt * (1 + t_info["marge"] + t_info["retrocession"])
                        return tp, tr, tt, tf

                    c_base     = simuler(True,  True,  True)
                    c_sans_aal = simuler(False, True,  True)
                    c_sans_aad = simuler(True,  False, True)
                    c_sans_rec = simuler(True,  True,  False)

                    tp,  tr,  tt,  tf  = calc_taux(c_base)
                    tp2, tr2, tt2, tf2 = calc_taux(c_sans_aal)
                    tp3, tr3, tt3, tf3 = calc_taux(c_sans_aad)
                    tp4, tr4, tt4, tf4 = calc_taux(c_sans_rec)

                    resultats_sim.append({
                        "tranche"       : t_info["nom"], "type": t_info["type"],
                        "taux_pur"      : tp,  "taux_risque": tr,
                        "taux_technique": tt,  "taux_final" : tf,
                        "sans_aal"      : tt2, "sans_aad"   : tt3, "sans_rec": tt4,
                    })

                progress_sim.progress(100, text="Terminé !")
                st.session_state["resultats_sim"] = resultats_sim

    if "resultats_sim" in st.session_state:
        st.subheader("📊 Résultats")
        st.dataframe(pd.DataFrame([{
            "Tranche"       : r["tranche"],
            "Taux pur"      : f"{r['taux_pur']:.4%}",
            "Taux risque"   : f"{r['taux_risque']:.4%}",
            "Taux technique": f"{r['taux_technique']:.4%}",
            "Taux final"    : f"{r['taux_final']:.4%}",
            "Sans AAL"      : f"{r['sans_aal']:.4%}",
            "Sans AAD"      : f"{r['sans_aad']:.4%}",
            "Sans reconst." : f"{r['sans_rec']:.4%}",
        } for r in st.session_state["resultats_sim"]]), use_container_width=True)

        st.divider()
        st.markdown("### 🤖 Analyse Claude — Simulation & Conditions")
        ctx_sim, inst_sim, inp_sim, out_sim = prompt_inputs(
            key_prefix="sim",
            placeholder_contexte="Ex: Nouveau modèle cat, lambda revu à la hausse...",
            placeholder_instructions="Ex: Seuil d'alerte écart = 20% au lieu de 25%...",
            placeholder_input="Ex: Résultats simulation année précédente...",
            placeholder_output="Ex: Verdict par condition + impact en points de taux"
        )

        if api_key and st.button("🤖 Recommandations Claude — Simulation"):
            with st.spinner("Claude analyse..."):
                prompt = build_prompt(
                    role="Expert en modélisation catastrophe et simulation stochastique réassurance.",
                    task="""Analyse les résultats simulation et l'impact des conditions contractuelles.
Pour chaque tranche et chaque condition (AAL, AAD, Reconstitution) :
1. Calcule l'impact en points de taux : taux_base - taux_sans_condition
2. Classe : NÉCESSAIRE (impact >15%) | À AJUSTER (5-15%) | INUTILE (<5%)
3. Recommande le montant optimal de chaque condition présente
4. Compare BC vs Simulation — signale les écarts > 25% avec explication""",
                    data=f"""Résultats simulation :
{json.dumps(st.session_state['resultats_sim'], indent=2)}
Programme : {json.dumps(tranches_input, indent=2)}""",
                    contexte=ctx_sim, instructions=inst_sim,
                    input_data=inp_sim, output_instructions=out_sim,
                    contexte_global=st.session_state.get("instructions_globales",""),
                    contraintes="""- Ne pas recommander la suppression d'une AAL sur tranche cat
- Un AAD trop élevé peut rendre la tranche inutile — le signaler
- Reconstitution = 0 acceptable seulement si taux très bas
- Écart BC/Sim > 50% = anomalie majeure à investiguer
- Ne jamais comparer à des benchmarks non fournis"""
                )
                client  = anthropic.Anthropic(api_key=api_key)
                analyse = client.messages.create(model="claude-opus-4-5", max_tokens=2000,
                    messages=[{"role":"user","content":prompt}])
                st.session_state["analyse_sim"] = analyse.content[0].text

        if "analyse_sim" in st.session_state:
            st.markdown(st.session_state["analyse_sim"])

# ════════════════════════════════════════════
# TAB 5 — MARKET CURVE
# ════════════════════════════════════════════

with tab5:
    st.header("Market Curve")
    st.caption("Modèle log-log : log(ROL) = a × log(midpoints) + b")

    f_mkt = st.file_uploader("📁 Données marché", type=["xlsx","csv"], key="f_mkt")

    if f_mkt and st.button("▶ Construire la market curve", type="primary"):
        with st.spinner("📈 Construction en cours..."):
            df_mkt = pd.read_excel(f_mkt) if f_mkt.name.endswith('xlsx') else pd.read_csv(f_mkt)

            for col in ['ROLs','midpoints','Garantie en MAD','Priorité en MAD']:
                if col in df_mkt.columns and df_mkt[col].dtype == object:
                    df_mkt[col] = df_mkt[col].str.replace('%','').str.replace(' ','').str.replace(',','.').astype(float)

            df_mkt = df_mkt[(df_mkt['ROLs'] > 0) & (df_mkt['ROLs'] <= 1)].copy()
            df_mkt = df_mkt[df_mkt['midpoints'] > 0].copy()

            def fit_log_log(x, y):
                log_x = np.log(x); log_y = np.log(y)
                c     = np.polyfit(log_x, log_y, 1)
                a, b  = c[0], c[1]
                r2    = 1 - np.sum((log_y - np.polyval(c,log_x))**2) / np.sum((log_y - log_y.mean())**2)
                return a, b, r2

            def predict_rol(mid, a, b):
                return np.exp(b) * (mid ** a)

            resultats_mkt = []
            for q in [0.10,0.20,0.30,0.40,0.50,0.60,0.70,0.80,0.90,1.0]:
                mid_max  = np.quantile(df_mkt['midpoints'],       q)
                port_max = np.quantile(df_mkt['Garantie en MAD'], q)
                df_q     = df_mkt[(df_mkt['midpoints'] <= mid_max) & (df_mkt['Garantie en MAD'] <= port_max)]
                if len(df_q) < 5: continue
                try:
                    a, b, r2 = fit_log_log(df_q['midpoints'].values, df_q['ROLs'].values)
                    taux_tranches = [{"tranche":t["nom"],"type":t["type"],
                        "rol": predict_rol(t['priorite']+t['portee']/2, a, b),
                        "taux": predict_rol(t['priorite']+t['portee']/2, a, b)*(t['portee']/gnpi)}
                        for t in tranches_input]
                    taux_vals   = [tt["taux"] for tt in taux_tranches]
                    median_taux = np.median(taux_vals)
                    cv_taux     = np.std(taux_vals)/median_taux if median_taux > 0 else 99
                    resultats_mkt.append({"quantile":q,"n_points":len(df_q),"a":a,"b":b,
                        "r2":r2,"cv_taux":cv_taux,"taux_tranches":taux_tranches})
                except: continue

            if resultats_mkt:
                all_t = [tt["taux"] for r in resultats_mkt for tt in r["taux_tranches"]]
                med_g = np.median(all_t)
                r2v   = [r["r2"] for r in resultats_mkt]
                r2min, r2max = min(r2v), max(r2v)
                for r in resultats_mkt:
                    tm = np.mean([tt["taux"] for tt in r["taux_tranches"]])
                    r["score"] = 0.5*(r["r2"]-r2min)/(r2max-r2min+1e-10) - 0.3*abs(tm-med_g)/(med_g+1e-10) - 0.2*r["cv_taux"]
                resultats_mkt = sorted(resultats_mkt, key=lambda x: x['score'], reverse=True)

            st.session_state["resultats_mkt"] = resultats_mkt
            st.session_state["df_mkt_clean"]  = df_mkt

    if "resultats_mkt" in st.session_state:
        rmt = st.session_state["resultats_mkt"]
        dmc = st.session_state["df_mkt_clean"]

        def predict_rol(mid, a, b): return np.exp(b) * (mid ** a)

        rows_recap = []
        for r in rmt:
            row = {"Q":f"Q{int(r['quantile']*100)}","N":r["n_points"],
                   "a":f"{r['a']:.4f}","b":f"{r['b']:.4f}","R²":f"{r['r2']:.4f}","Score":f"{r['score']:.4f}"}
            for tt in r["taux_tranches"]: row[tt["tranche"]] = f"{tt['taux']:.4%}"
            rows_recap.append(row)

        st.subheader("📊 Comparaison des ajustements")
        st.dataframe(pd.DataFrame(rows_recap), use_container_width=True)
        best = rmt[0]
        st.success(f"✅ Meilleur : Q{int(best['quantile']*100)} — R²={best['r2']:.4f} | Score={best['score']:.4f}")

        choix_q   = st.selectbox("Choisir la combinaison",
            options=[f"Q{int(r['quantile']*100)} — R²={r['r2']:.4f} | Score={r['score']:.4f}" for r in rmt], index=0)
        idx_choix = [f"Q{int(r['quantile']*100)} — R²={r['r2']:.4f} | Score={r['score']:.4f}" for r in rmt].index(choix_q)
        choix     = rmt[idx_choix]

        x_all   = dmc['midpoints'].values; y_all = dmc['ROLs'].values
        x_range = np.linspace(min(x_all), max(x_all), 300)

        fig, ax = plt.subplots(figsize=(10,5))
        fig.patch.set_facecolor('#f5f5f5'); ax.set_facecolor('#fafafa')
        ax.scatter(x_all, y_all, color='#2d8a4e', s=60, zorder=5, alpha=0.7, label='Données marché')
        ax.plot(x_range, np.exp(choix['b'])*(x_range**choix['a']), color='#1a1a1a', lw=2.5,
                label=f"log(ROL)={choix['a']:.3f}×log(mid)+{choix['b']:.3f} | R²={choix['r2']:.4f}")
        ax.set_xlabel('Midpoints'); ax.set_ylabel('ROL')
        ax.set_title('Market Curve — Modèle log-log', fontweight='bold', color='#1a1a1a')
        ax.legend(); ax.grid(alpha=0.3, linestyle='--')
        st.pyplot(fig)

        st.subheader("📊 Taux marché retenus")
        st.dataframe(pd.DataFrame([{"Tranche":tt["tranche"],"Type":tt["type"],
            "ROL estimé":f"{tt['rol']:.4%}","Taux marché":f"{tt['taux']:.4%}"}
            for tt in choix["taux_tranches"]]), use_container_width=True)
        st.session_state["taux_mkt_final"] = choix["taux_tranches"]

        st.divider()
        st.markdown("### 🤖 Analyse Claude — Market Curve")
        ctx_mkt, inst_mkt, inp_mkt, out_mkt = prompt_inputs(
            key_prefix="mkt",
            placeholder_contexte="Ex: Marché en durcissement, hausse 15% vs année précédente...",
            placeholder_instructions="Ex: Privilégier les ajustements avec N > 20 points...",
            placeholder_input="Ex: Taux marché de référence secteur : Cat L1=1.5%",
            placeholder_output="Ex: Recommandation unique avec justification R² et cohérence"
        )

        if api_key and st.button("🤖 Recommandations Claude — Market Curve"):
            with st.spinner("Claude analyse..."):
                prompt = build_prompt(
                    role="Expert en réassurance catastrophe et market curve, spécialiste marchés émergents.",
                    task="""Analyse les ajustements de market curve et recommande le meilleur.
Modèle : log(ROL) = a × log(midpoints) + b
Pour chaque ajustement :
1. Évalue la qualité du R² (log-log)
2. Vérifie la cohérence des taux obtenus vs normes marché
3. Tiens compte du nombre de points (robustesse statistique)
4. Identifie les ajustements aberrants (taux trop élevés ou trop bas)
Conclusion : recommande UN seul ajustement avec justification complète.""",
                    data=f"""Ajustements :
{json.dumps(rows_recap, indent=2)}
Programme : {json.dumps(tranches_input, indent=2)}
GNPI : {gnpi:,} MAD""",
                    contexte=ctx_mkt, instructions=inst_mkt,
                    input_data=inp_mkt, output_instructions=out_mkt,
                    contexte_global=st.session_state.get("instructions_globales",""),
                    contraintes="""- R² < 0.3 = ajustement médiocre, à éviter sauf absence d'alternative
- N < 10 points = faible robustesse, signaler
- Taux marché > 3x taux simulation = suspect, investiguer
- Ne jamais recommander un taux basé sur un seul point de données
- Le score composite (R² + cohérence) prime sur le R² seul"""
                )
                client = anthropic.Anthropic(api_key=api_key)
                reco   = client.messages.create(model="claude-opus-4-5", max_tokens=1500,
                    messages=[{"role":"user","content":prompt}])
                st.session_state["analyse_mkt"] = reco.content[0].text

        if "analyse_mkt" in st.session_state:
            st.markdown(st.session_state["analyse_mkt"])

# ════════════════════════════════════════════
# TAB 6 — RAPPORT FINAL
# ════════════════════════════════════════════


with tab6:
    st.header("Rapport Final de Tarification")

    manquants = [n for n, k in [("BC","resultats_bc"),("Simulation","resultats_sim"),("Market Curve","taux_mkt_final")]
                 if k not in st.session_state]
    if manquants:
        st.warning(f"⚠️ Complétez d'abord : {', '.join(manquants)}")
    else:
        # Calcul automatique du rapport
        bc_map  = {r["tranche"]: r for r in st.session_state["resultats_bc"]}
        sim_map = {r["tranche"]: r for r in st.session_state["resultats_sim"]}
        mkt_map = {r["tranche"]: r["taux"] for r in st.session_state["taux_mkt_final"]}

        rows_rapport = []; prime_totale = 0
        for t in tranches_input:
            nom    = t["nom"]
            bc_tt  = bc_map.get(nom,{}).get("taux_technique",0)
            sim_tt = sim_map.get(nom,{}).get("taux_technique",0)
            mkt    = mkt_map.get(nom, 0)
            if t["type"] == "travaillante":
                ecart = abs(bc_tt-sim_tt)/bc_tt*100 if bc_tt > 0 else 0
                taux_retenu = sim_tt
                methode = f"Simulation (écart BC/Sim: {ecart:.0f}%) {'⚠️' if ecart>25 else '✅'}"
            else:
                taux_retenu = max(sim_tt, mkt)
                methode = "Simulation" if sim_tt >= mkt else "Marché"
            prime = gnpi * taux_retenu; prime_totale += prime
            rows_rapport.append({
                "Tranche"    : nom, "Type": t["type"],
                "Taux BC"    : f"{bc_tt:.4%}", "Taux Sim.": f"{sim_tt:.4%}",
                "Taux Marché": f"{mkt:.4%}", "Taux retenu": f"{taux_retenu:.4%}",
                "Prime (MAD)": f"{prime:,.0f}", "Méthode": methode
            })

        st.session_state["df_rapport"]   = pd.DataFrame(rows_rapport)
        st.session_state["prime_totale"] = prime_totale

        # Affichage tableau
        st.subheader("📊 Synthèse de tarification")
        st.dataframe(st.session_state["df_rapport"], use_container_width=True)
        c1, c2, c3 = st.columns(3)
        with c1: card("Prime totale", f"{prime_totale:,.0f} MAD", couleur="#2d8a4e", icone="💰")
        with c2: card("Taux global",  f"{prime_totale/gnpi:.4%}", couleur="#1a1a1a",  icone="📊")
        with c3: card("Tranches",     str(len(tranches_input)),   couleur="#2d8a4e",  icone="📋")

        st.divider()
        st.markdown("### 🤖 Rapport Claude — Analyse finale")
        ctx_r, inst_r, inp_r, out_r = prompt_inputs(
            key_prefix="rapport",
            placeholder_contexte="Ex: Négociation avec réassureur XYZ, objectif prime < 14M MAD...",
            placeholder_instructions="Ex: Justifier chaque taux retenu, comparer avec N-1...",
            placeholder_input="Ex: Taux retenus N-1 : R&C=3.1%, CatL1=1.2%, CatL2=0.8%",
            placeholder_output="Ex: Rapport 1 page max, tableau synthèse final obligatoire"
        )

        if api_key and st.button("🤖 Générer le rapport Claude", type="primary"):
            with st.spinner("Claude rédige le rapport final..."):
                prompt = build_prompt(
                    role="""Expert senior en tarification réassurance non-proportionnelle,
spécialisé branche automobile marchés émergents (Maroc, Afrique francophone).
Rôle de consultant indépendant — objectif : fournir un avis technique rigoureux.""",
                    task="""Rédige un rapport de tarification professionnel et complet.
Structure OBLIGATOIRE :
1. SYNTHÈSE EXÉCUTIVE (5 lignes max — pour le management)
2. ANALYSE PAR TRANCHE (une section par tranche)
   - Chiffres clés BC / Simulation / Marché
   - Raisonnement [Observation → Analyse → Conclusion]
   - Verdict et taux retenu justifié
3. COHÉRENCE INTER-MÉTHODES
4. ANOMALIES ET POINTS D'ATTENTION
5. TABLEAU RÉCAPITULATIF FINAL
6. RECOMMANDATION GLOBALE""",
                    data=f"""Rapport de tarification :
{json.dumps(rows_rapport, indent=2)}

BC détaillé :
{json.dumps([{k:v for k,v in r.items() if k!='detail_annuel'} for r in st.session_state['resultats_bc']], indent=2)}

Simulation :
{json.dumps(st.session_state['resultats_sim'], indent=2)}

GNPI : {gnpi:,} MAD
Prime totale : {prime_totale:,.0f} MAD
Taux global  : {prime_totale/gnpi:.4%}""",
                    contexte=ctx_r, instructions=inst_r,
                    input_data=inp_r, output_instructions=out_r,
                    contexte_global=st.session_state.get("instructions_globales",""),
                    exemples="""Exemple de BONNE synthèse exécutive :
"Le programme 2026 de 3 tranches ressort à 14.2M MAD (7.76% du GNPI).
La tranche travaillante Risk&Cat présente un écart BC/Simulation de 35%
— vraisemblablement lié à l'inflation sinistres. Les tranches cat sont
tarifées sur la market curve, plus prudente que la simulation seule."

Exemple à ÉVITER :
"Les taux calculés semblent raisonnables." ← vague, sans chiffres.""",
                    contraintes="""- Ne jamais recommander un taux inférieur au taux pur
- Si BC = 0 sur tranche cat → c'est normal, ne pas le signaler comme problème
- Prime totale = somme des (GNPI × taux_retenu par tranche)
- Si taux marché >> simulation sur tranche cat → normal, l'expliquer
- Mentionner explicitement les incertitudes et limites de chaque méthode
- Ne pas inventer de comparatifs historiques non fournis"""
                )
                client      = anthropic.Anthropic(api_key=api_key)
                reco_finale = client.messages.create(model="claude-opus-4-5", max_tokens=2500,
                    messages=[{"role":"user","content":prompt}])
                st.session_state["reco_finale"] = reco_finale.content[0].text

    if "reco_finale" in st.session_state:
        st.divider()
        st.subheader("🤖 Rapport Claude")
        st.markdown(st.session_state["reco_finale"])

# ════════════════════════════════════════════
# TAB ADMIN
# ════════════════════════════════════════════

with tab_admin:
    st.header("🔐 Interface Administrateur")

    admin_pwd = st.text_input("Mot de passe admin", type="password", key="admin_pwd")

    if admin_pwd == get_admin_password():
        st.success("✅ Accès accordé")
        users = get_users()

        st.markdown("#### 👥 Utilisateurs autorisés")
        st.dataframe(pd.DataFrame([
            {"Email": e, "Code": c, "Statut": "✅ Actif"}
            for e, c in users.items()
        ]), use_container_width=True)

        st.divider()
        st.markdown("#### ⚙️ Comment gérer les utilisateurs")
        st.info("""**Allez sur Streamlit Cloud → votre app → Settings → Secrets** et ajoutez :

```toml
admin_password = "VotreMotDePasseAdmin"

[users]
"email@exemple.com" = "CODE_UNIQUE"
"autre@email.com"   = "AUTRE_CODE"
```

Sauvegardez — l'app se recharge automatiquement.""")

        st.divider()
        st.markdown("#### 🎲 Générateur de code")
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
                st.caption("Copiez dans vos Secrets Streamlit et communiquez le code à l'utilisateur.")

    elif admin_pwd:
        st.error("❌ Mot de passe incorrect")











