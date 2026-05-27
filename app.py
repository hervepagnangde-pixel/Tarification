import streamlit as st
import anthropic
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import json
import secrets as secrets_lib
from PIL import Image

# ════════════════════════════════════════════
# SET PAGE CONFIG — UNE SEULE FOIS EN HAUT
# ════════════════════════════════════════════
try:
    icon = Image.open("icon.png")
    st.set_page_config(page_title="AtlanticRe IA", layout="wide", page_icon=icon)
except:
    st.set_page_config(page_title="AtlanticRe IA", layout="wide", page_icon="🎯")

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
# LANDING PAGE
# ════════════════════════════════════════════

if "page" not in st.session_state:
    st.session_state["page"] = "landing"

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
            Herve <span style="color:#2d8a4e">IA</span>
        </h1>
        <p style="color:#aaa;font-size:16px;margin:0 0 8px 0">Agent de tarification · Réassurance Non-Proportionnelle</p>
        <p style="color:#666;font-size:13px;margin:0 0 40px 0">Atlantic Re · Automobile · Maroc</p>
        <div style="display:flex;gap:16px;margin-bottom:48px;flex-wrap:wrap;justify-content:center">
            <div style="background:rgba(45,138,78,0.1);border:1px solid rgba(45,138,78,0.3);border-radius:12px;padding:16px 20px;min-width:140px">
                <div style="font-size:24px;margin-bottom:6px">🔥</div>
                <div style="color:white;font-size:13px;font-weight:600">Burning Cost</div>
                <div style="color:#888;font-size:11px">As-If · Stabilisation · CL</div>
            </div>
            <div style="background:rgba(45,138,78,0.1);border:1px solid rgba(45,138,78,0.3);border-radius:12px;padding:16px 20px;min-width:140px">
                <div style="font-size:24px;margin-bottom:6px">🎲</div>
                <div style="color:white;font-size:13px;font-weight:600">Simulation</div>
                <div style="color:#888;font-size:11px">Pareto · Poisson · TVE</div>
            </div>
            <div style="background:rgba(45,138,78,0.1);border:1px solid rgba(45,138,78,0.3);border-radius:12px;padding:16px 20px;min-width:140px">
                <div style="font-size:24px;margin-bottom:6px">📈</div>
                <div style="color:white;font-size:13px;font-weight:600">Market Curve</div>
                <div style="color:#888;font-size:11px">Modèle puissance log-log</div>
            </div>
            <div style="background:rgba(45,138,78,0.1);border:1px solid rgba(45,138,78,0.3);border-radius:12px;padding:16px 20px;min-width:140px">
                <div style="font-size:24px;margin-bottom:6px">🤖</div>
                <div style="color:white;font-size:13px;font-weight:600">Agent Claude</div>
                <div style="color:#888;font-size:11px">Analyse · Recommandations</div>
            </div>
        </div>
    </div>
    """, unsafe_allow_html=True)

    col1, col2, col3 = st.columns([1, 2, 1])
    with col2:
        if st.button("🚀  Lancer l'outil de tarification", type="primary", use_container_width=True):
            st.session_state["page"] = "app"
            st.rerun()
        st.markdown(f"<p style='text-align:center;color:#555;font-size:12px;margin-top:12px'>Connecté : {st.session_state.get('user_email','')}</p>", unsafe_allow_html=True)
    st.stop()

# ════════════════════════════════════════════
# APP CONFIG CSS
# ════════════════════════════════════════════
st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700&display=swap');
* { font-family: 'Inter', sans-serif; }
.stApp { background-color: #f4f6f4; }
::-webkit-scrollbar { width: 6px; height: 6px; }
::-webkit-scrollbar-track { background: #f1f1f1; }
::-webkit-scrollbar-thumb { background: #2d8a4e; border-radius: 3px; }
h1 { color: #1a1a1a; font-weight: 700; letter-spacing: -0.5px; }
h2 { color: #1a1a1a; border-bottom: 3px solid #2d8a4e; padding-bottom: 10px; margin-bottom: 20px; font-weight: 600; }
h3 { color: #2d8a4e; font-weight: 600; }
.stButton > button { background: linear-gradient(135deg, #1a1a1a 0%, #2d2d2d 100%); color: white; border: none; border-radius: 8px; padding: 10px 24px; font-weight: 600; font-size: 14px; transition: all 0.25s ease; box-shadow: 0 2px 8px rgba(0,0,0,0.15); }
.stButton > button:hover { background: linear-gradient(135deg, #2d8a4e 0%, #25a85e 100%); transform: translateY(-2px); box-shadow: 0 6px 16px rgba(45,138,78,0.35); }
.stButton > button[kind="primary"] { background: linear-gradient(135deg, #2d8a4e 0%, #25a85e 100%); }
.stButton > button[kind="primary"]:hover { background: linear-gradient(135deg, #1a1a1a 0%, #2d2d2d 100%); }
.stTabs [data-baseweb="tab-list"] { background: #1a1a1a; border-radius: 12px; padding: 6px; gap: 4px; box-shadow: 0 4px 12px rgba(0,0,0,0.2); }
.stTabs [data-baseweb="tab"] { color: #888; font-weight: 500; font-size: 13px; border-radius: 8px; padding: 8px 16px; transition: all 0.2s ease; }
.stTabs [data-baseweb="tab"]:hover { color: white; background: rgba(255,255,255,0.1); }
.stTabs [aria-selected="true"] { background: linear-gradient(135deg, #2d8a4e, #25a85e) !important; color: white !important; border-radius: 8px; box-shadow: 0 2px 8px rgba(45,138,78,0.4); }
[data-testid="stSidebar"] { background: linear-gradient(180deg, #1a1a1a 0%, #2a2a2a 100%); border-right: 1px solid #2d8a4e; }
[data-testid="stSidebar"] * { color: #e0e0e0 !important; }
[data-testid="stSidebar"] h1, [data-testid="stSidebar"] h2, [data-testid="stSidebar"] h3 { color: #2d8a4e !important; border-bottom: 1px solid #333 !important; }
[data-testid="stSidebar"] .stTextInput input, [data-testid="stSidebar"] .stNumberInput input { background: #2a2a2a; border: 1px solid #444; color: white !important; border-radius: 6px; }
[data-testid="stMetric"] { background: white; border-radius: 12px; padding: 16px 20px; border: 1px solid #e8e8e8; box-shadow: 0 2px 8px rgba(0,0,0,0.06); border-left: 4px solid #2d8a4e; transition: transform 0.2s ease; }
[data-testid="stMetric"]:hover { transform: translateY(-2px); }
[data-testid="stMetricLabel"] { color: #666 !important; font-size: 13px !important; font-weight: 500 !important; }
[data-testid="stMetricValue"] { color: #1a1a1a !important; font-weight: 700 !important; }
[data-testid="stDataFrame"] { border-radius: 12px; overflow: hidden; box-shadow: 0 2px 12px rgba(0,0,0,0.08); border: 1px solid #e8e8e8; }
.stTextInput input, .stNumberInput input, .stTextArea textarea { border: 1.5px solid #e0e0e0; border-radius: 8px; padding: 10px 14px; font-size: 14px; transition: all 0.2s ease; background: white; }
.stTextInput input:focus, .stNumberInput input:focus, .stTextArea textarea:focus { border-color: #2d8a4e; box-shadow: 0 0 0 3px rgba(45,138,78,0.15); outline: none; }
.stSelectbox > div > div { border: 1.5px solid #e0e0e0; border-radius: 8px; }
.stSelectbox > div > div:hover { border-color: #2d8a4e; }
.streamlit-expanderHeader { background: white; border-radius: 10px; border: 1px solid #e8e8e8; font-weight: 500; color: #1a1a1a; padding: 12px 16px; transition: all 0.2s ease; }
.streamlit-expanderHeader:hover { border-color: #2d8a4e; color: #2d8a4e; }
.streamlit-expanderContent { border: 1px solid #e8e8e8; border-top: none; border-radius: 0 0 10px 10px; background: #fafafa; padding: 16px; }
hr { border: none; border-top: 2px solid #e8e8e8; margin: 20px 0; }
.stProgress > div > div { background: linear-gradient(90deg, #2d8a4e, #25a85e); border-radius: 4px; }
.stProgress > div { background: #e8e8e8; border-radius: 4px; }
</style>
""", unsafe_allow_html=True)


def card(titre, valeur, couleur="#2d8a4e", icone="📊"):
    st.markdown(f"""<div style="background:white;border-radius:12px;padding:20px 24px;border:1px solid #e8e8e8;
        border-left:5px solid {couleur};box-shadow:0 2px 8px rgba(0,0,0,0.06);margin-bottom:12px;">
        <div style="font-size:12px;color:#888;font-weight:500;text-transform:uppercase;letter-spacing:0.5px;margin-bottom:6px">{icone} {titre}</div>
        <div style="font-size:24px;font-weight:700;color:#1a1a1a">{valeur}</div></div>""", unsafe_allow_html=True)


def section_header(titre, sous_titre="", icone=""):
    st.markdown(f"""<div style="background:linear-gradient(135deg,#1a1a1a 0%,#2d2d2d 100%);border-radius:12px;
        padding:20px 24px;margin-bottom:20px;box-shadow:0 4px 12px rgba(0,0,0,0.15);">
        <div style="font-size:20px;font-weight:700;color:white">{icone} {titre}</div>
        {f'<div style="font-size:13px;color:#aaa;margin-top:4px">{sous_titre}</div>' if sous_titre else ''}
        </div>""", unsafe_allow_html=True)


def tableau_resultats(donnees, titre=""):
    if not donnees: return
    if titre:
        st.markdown(f"<h4 style='color:#1a1a1a;margin-bottom:12px'>{titre}</h4>", unsafe_allow_html=True)
    colonnes = list(donnees[0].keys())
    html = """<div style="overflow-x:auto;border-radius:12px;box-shadow:0 2px 12px rgba(0,0,0,0.08);">
    <table style="width:100%;border-collapse:collapse;font-size:13px;">
    <thead><tr style="background:linear-gradient(135deg,#1a1a1a,#2d2d2d)">"""
    for col in colonnes:
        html += f'<th style="padding:12px 16px;text-align:left;color:white;font-weight:600">{col}</th>'
    html += "</tr></thead><tbody>"
    for i, row in enumerate(donnees):
        bg = "white" if i % 2 == 0 else "#f9fafb"
        html += f'<tr style="background:{bg}" onmouseover="this.style.background=\'#f0fff4\'" onmouseout="this.style.background=\'{bg}\'">'
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
            html += f'<td style="padding:11px 16px;border-bottom:1px solid #f0f0f0;color:{color};font-weight:500">{val}</td>'
        html += "</tr>"
    html += "</tbody></table></div>"
    st.markdown(html, unsafe_allow_html=True)


def progress_steps(steps, current):
    html = '<div style="display:flex;align-items:center;gap:0;margin:16px 0;overflow-x:auto">'
    for i, (label, done) in enumerate(steps):
        if done:         bg, fg, border = "#2d8a4e", "white", "#2d8a4e"
        elif i==current: bg, fg, border = "#1a1a1a", "white", "#1a1a1a"
        else:            bg, fg, border = "white", "#999", "#ddd"
        check     = "✓ " if done else ""
        connector = '<div style="height:2px;background:#ddd;flex:1;min-width:8px"></div>' if i < len(steps)-1 else ""
        html += '<div style="display:flex;align-items:center;flex:1;min-width:80px">'
        html += f'<div style="background:{bg};color:{fg};border:2px solid {border};border-radius:20px;padding:6px 12px;font-size:11px;font-weight:600;white-space:nowrap;text-align:center;width:100%">{check}{label}</div>'
        html += connector + '</div>'
    html += '</div>'
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
            contexte = st.text_area("📌 Contexte",
                placeholder=placeholder_contexte or "Ex: Portefeuille automobile Maroc 2026...",
                height=80, key=f"{key_prefix}_contexte")
            instructions = st.text_area("📋 Instructions spécifiques",
                placeholder=placeholder_instructions or "Ex: Être attentif à la tranche Cat L1...",
                height=80, key=f"{key_prefix}_instructions")
        with c2:
            input_data = st.text_area("📥 Données supplémentaires",
                placeholder=placeholder_input or "Ex: Taux marché de référence : 3.2%...",
                height=80, key=f"{key_prefix}_input")
            output_instructions = st.text_area("📤 Format de sortie souhaité",
                placeholder=placeholder_output or "Ex: Tableau structuré + recommandation chiffrée...",
                height=80, key=f"{key_prefix}_output")
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
RÈGLES ABSOLUES
════════════════════════════════════════════
1. ANTI-HALLUCINATION : Ne jamais inventer. Si incertain → "Information insuffisante."
2. RAISONNEMENT : [Observation] → [Analyse] → [Conclusion] avec chiffres.
3. CONTRAINTES MÉTIER :
{contraintes if contraintes else "   - Taux techniques positifs et < 50%\n   - Ecart BC/Sim > 25% signalé\n   - BC=0 tranche cat NORMAL"}
4. VÉRIFICATION : chiffres présents ? cohérence ? hiérarchie taux_pur < taux_risque < taux_tech ?
5. EXEMPLES :
{exemples if exemples else '   BON : "Taux BC 2.94%, simulation 3.98%, ecart 35% -> retenir simulation."\n   MAUVAIS : "Le taux est acceptable."'}

════════════════════════════════════════════
CONTEXTE GLOBAL
════════════════════════════════════════════
{contexte_global if contexte_global else "Non fourni."}

════════════════════════════════════════════
CONTEXTE SPECIFIQUE
════════════════════════════════════════════
{contexte if contexte else "Aucun."}

════════════════════════════════════════════
TACHE
════════════════════════════════════════════
{task}

════════════════════════════════════════════
DONNEES
════════════════════════════════════════════
{data}
{("DONNEES SUPPLEMENTAIRES :\n" + input_data) if input_data else ""}

════════════════════════════════════════════
INSTRUCTIONS SPECIFIQUES
════════════════════════════════════════════
{instructions if instructions else "Suivre la tache telle que decrite."}

════════════════════════════════════════════
FORMAT DE SORTIE
════════════════════════════════════════════
{output_instructions if output_instructions else "1. SYNTHESE (2-3 phrases)\n2. ANALYSE PAR TRANCHE\n3. POINTS D'ATTENTION\n4. CONCLUSION"}

La precision prime sur l'exhaustivite.
════════════════════════════════════════════
"""
    return prompt.strip()


def claude_stream(api_key, prompt, max_tokens=2000, session_key=""):
    client = anthropic.Anthropic(api_key=api_key)
    placeholder = st.empty()
    full_text = ""
    with st.status("🤖 Agent Claude en cours...", expanded=True) as status:
        st.write("🔗 Connexion au modèle...")
        st.write("📊 Chargement des données actuarielles...")
        try:
            with client.messages.stream(
                model="claude-opus-4-5", max_tokens=max_tokens,
                messages=[{"role": "user", "content": prompt}]
            ) as stream:
                st.write("✍️ Génération de l'analyse...")
                for text in stream.text_stream:
                    full_text += text
                    placeholder.markdown(full_text + "▌")
            status.update(label="✅ Analyse terminée", state="complete", expanded=False)
        except Exception as e:
            status.update(label="❌ Erreur", state="error")
            st.error(f"Erreur API : {e}")
            return ""
    placeholder.markdown(full_text)
    if session_key:
        st.session_state[session_key] = full_text
    return full_text


def guide_prompt(etape, exemples_contexte, exemples_instructions, exemples_input, exemples_output):
    with st.expander("💡 Conseils pour bien prompter Claude sur cette étape", expanded=False):
        st.markdown(f"""<div style="background:#f0fff4;border-left:4px solid #2d8a4e;border-radius:0 8px 8px 0;
            padding:14px 18px;margin-bottom:12px"><b style="color:#2d8a4e">🎯 Meilleure analyse pour : {etape}</b></div>""",
            unsafe_allow_html=True)
        c1, c2 = st.columns(2)
        with c1:
            st.markdown("**📌 Contexte — quoi mettre**")
            for ex in exemples_contexte: st.markdown(f"- {ex}")
            st.markdown("**📋 Instructions — quoi demander**")
            for ex in exemples_instructions: st.markdown(f"- {ex}")
        with c2:
            st.markdown("**📥 Données supplémentaires**")
            for ex in exemples_input: st.markdown(f"- {ex}")
            st.markdown("**📤 Format de sortie**")
            for ex in exemples_output: st.markdown(f"- {ex}")
        st.markdown("""<div style="background:#fff8f0;border-left:4px solid #f59e0b;border-radius:0 8px 8px 0;
            padding:10px 14px;margin-top:8px;font-size:12px">
            ⚠️ <b>Règle d'or :</b> Plus vous donnez de contexte métier, plus l'analyse sera pertinente et actionnelle.
            </div>""", unsafe_allow_html=True)


# ════════════════════════════════════════════
# FONCTIONS ACTUARIELLES
# ════════════════════════════════════════════

def selectionner_seuil_pareto(X, D):
    X = np.array(X); X = X[X > 0]
    k_hill = min(59, len(X)-1); k_gerten = min(43, len(X)-1)
    X_desc = np.sort(X)[::-1]
    seuils = {"MLE": np.min(X),
               "Hill": X_desc[k_hill-1] if k_hill > 0 else np.min(X),
               "Gerten": X_desc[k_gerten-1] if k_gerten > 0 else np.min(X),
               "MeanExc": 1_800_000,
               "p50": 0.50*D, "p75": 0.75*D, "p80": 0.80*D, "p85": 0.85*D, "p90": 0.90*D}
    resultats = []
    for nom, s in seuils.items():
        Xs = X[X >= s]
        if len(Xs) < 5: continue
        t_min = np.min(Xs); n = len(Xs)
        alpha_hat = n / np.sum(np.log(Xs / t_min))
        Xs_sorted = np.sort(Xs)
        cdf_emp = np.arange(1, n+1) / n
        cdf_par = 1 - (t_min / Xs_sorted) ** alpha_hat
        ks_stat = np.max(np.abs(cdf_emp - cdf_par))
        ks_pval = np.exp(-2 * n * ks_stat**2)
        resultats.append({"Seuil": nom, "t": round(s), "n": n,
                           "alpha": round(alpha_hat, 4), "KS_pval": round(ks_pval, 4)})
    return pd.DataFrame(resultats), seuils.get("p80", 0.80*D)


def identifier_sinistres_majeurs(df_proj, gnpi, D, C_tranche,
                                  nb_annees_obs=10, retour_ans=20, percentile_seuil=99.5):
    X = df_proj['Sprime_ultime'].values; X = X[X > 0]
    Pm = np.percentile(X, percentile_seuil)
    mask_maj = df_proj['Sprime_ultime'] >= Pm
    df_majeurs = df_proj[mask_maj].copy(); df_courants = df_proj[~mask_maj].copy()
    seuil_model = 0.80 * D
    X_model = X[(X >= seuil_model) & (X < Pm)]
    if len(X_model) < 3: X_model = X[X >= seuil_model]
    t_min = np.min(X_model) if len(X_model) > 0 else seuil_model
    n_model = len(X_model)
    alpha_hat = n_model / np.sum(np.log(X_model / t_min)) if n_model > 0 else 1.5
    def charge_nette(x): return min(max(x - D, 0), C_tranche)
    rows_charg = []
    for _, row in df_majeurs.iterrows():
        x = row['Sprime_ultime']; cn = charge_nette(x); chg = (1/retour_ans) * cn / gnpi
        rows_charg.append({"Annee": row.get('annee_surv','—'), "Montant_stab": round(x),
                            "Charge_nette": round(cn), "p_j": round(1/retour_ans, 4),
                            "Chargement": round(chg, 6)})
    df_chargements = pd.DataFrame(rows_charg)
    chargement_total = df_chargements['Chargement'].sum() if len(df_chargements) > 0 else 0.0
    return {"df_majeurs": df_majeurs, "df_courants": df_courants, "Pm": Pm,
            "chargement": chargement_total, "df_chargements": df_chargements,
            "alpha": alpha_hat, "n_majeurs": len(df_majeurs), "n_courants": len(df_courants)}


# ════════════════════════════════════════════
# HEADER + SIDEBAR
# ════════════════════════════════════════════

st.title("Atlantic Re")
st.caption(f"Connecté : {st.session_state.get('user_email','')} | Burning cost · Simulation · Market curve · IA")

with st.sidebar:
    if st.button("🚪 Déconnexion"):
        st.session_state["authenticated"] = False; st.rerun()
    if st.button("🏠 Accueil"):
        st.session_state["page"] = "landing"; st.rerun()
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
    instructions_globales = st.text_area("Contexte portefeuille",
        placeholder="Ex: Portefeuille automobile Maroc, forte croissance 2023...",
        height=120, key="instructions_globales",
        help="Inclus dans TOUS les prompts Claude")

# ════════════════════════════════════════════
# ACCUEIL INTELLIGENT
# ════════════════════════════════════════════

if api_key and "accueil_ia_done" not in st.session_state:
    etapes_faites     = [n for n, k in [("Programme","df_prog"),("Triangle","df_liq"),
                          ("Burning Cost","resultats_bc"),("Simulation","resultats_sim"),
                          ("Market Curve","resultats_mkt")] if k in st.session_state]
    etapes_manquantes = [n for n, k in [("Programme","df_prog"),("Triangle","df_liq"),
                          ("Burning Cost","resultats_bc"),("Simulation","resultats_sim"),
                          ("Market Curve","resultats_mkt")] if k not in st.session_state]
    prompt_accueil = build_prompt(
        role="Assistant actuariel expert en reassurance non-proportionnelle automobile. Tu accueilles un utilisateur sur l'outil de tarification XL Atlantic Re.",
        task="""Genere un message d'accueil intelligent en 3 parties :
1. ACCUEIL PERSONNALISE (2 lignes max)
2. GUIDE RAPIDE (etapes numerotees) : Programme -> Triangle -> BC -> Simulation -> Market Curve -> Rapport
3. RECOMMANDATION INTELLIGENTE selon l'etat actuel
Style : professionnel, concis, encourageant. Maximum 10 lignes.""",
        data=f"Etapes completes : {etapes_faites if etapes_faites else 'Aucune'}\nEtapes restantes : {etapes_manquantes if etapes_manquantes else 'Toutes completes !'}\nGNPI : {gnpi:,} MAD | Utilisateur : {st.session_state.get('user_email', '')}",
        contexte_global=st.session_state.get("instructions_globales", ""),
        contraintes="- Concis max 10 lignes\n- Emojis\n- Ne pas inventer de donnees")
    st.markdown("""<div style="background:linear-gradient(135deg,#1a1a1a 0%,#2d8a4e 100%);
        border-radius:16px;padding:24px 28px;margin-bottom:20px;box-shadow:0 6px 20px rgba(0,0,0,0.2)">
        <div style="font-size:18px;font-weight:700;color:white;margin-bottom:8px">🤖 Herve IA — Assistant de tarification</div>
        <div style="font-size:13px;color:rgba(255,255,255,0.7)">Analyse de votre session en cours...</div>
        </div>""", unsafe_allow_html=True)
    with st.container():
        claude_stream(api_key, prompt_accueil, max_tokens=600, session_key="accueil_ia_msg")
        st.session_state["accueil_ia_done"] = True

elif "accueil_ia_msg" in st.session_state:
    st.markdown("""<div style="background:linear-gradient(135deg,#1a1a1a 0%,#2d8a4e 100%);
        border-radius:16px;padding:20px 28px;margin-bottom:20px;box-shadow:0 6px 20px rgba(0,0,0,0.2)">
        <div style="font-size:18px;font-weight:700;color:white">🤖 Herve IA — Assistant de tarification</div>
        </div>""", unsafe_allow_html=True)
    st.markdown(st.session_state["accueil_ia_msg"])

elif not api_key:
    st.markdown("""<div style="background:linear-gradient(135deg,#1a1a1a 0%,#2d8a4e 100%);
        border-radius:16px;padding:24px 28px;margin-bottom:20px;">
        <div style="font-size:18px;font-weight:700;color:white">🤖 Herve IA</div>
        <div style="color:rgba(255,255,255,0.8);margin-top:8px;font-size:14px">
            Entrez votre cle API Claude dans la sidebar pour activer l'assistant IA.<br>
            <b>Workflow :</b> Programme → Triangle → BC → Simulation → Market Curve → Rapport
        </div></div>""", unsafe_allow_html=True)

if "accueil_ia_done" in st.session_state:
    if st.button("🔄 Actualiser les recommandations IA", key="reset_accueil"):
        del st.session_state["accueil_ia_done"]
        del st.session_state["accueil_ia_msg"]
        st.rerun()

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
                priorite = st.number_input("Priorité (MAD)", value=d["priorite"], step=500_000, key=f"prio_{i}", format="%d")
                portee   = st.number_input("Portée (MAD)",   value=d["portee"],   step=500_000, key=f"port_{i}", format="%d")
            with c2:
                st.markdown("**Conditions contractuelles**")
                has_aal  = st.checkbox("AAL", key=f"aal_{i}")
                aal_val  = st.number_input("Montant AAL", value=0, step=100_000, key=f"aal_v_{i}", disabled=not has_aal)
                has_aad  = st.checkbox("AAD", key=f"aad_{i}")
                aad_val  = st.number_input("Montant AAD", value=0, step=100_000, key=f"aad_v_{i}", disabled=not has_aad)
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
            "Tranche": t["nom"], "Type": t["type"],
            "Priorité": f"{t['priorite']:,}", "Portée": f"{t['portee']:,}",
            "AAL": f"{t['AAL']:,}" if t["AAL"] else "—",
            "AAD": f"{t['AAD']:,}" if t["AAD"] else "—",
            "Reconst.": f"{t['nb_reconstitutions']} x {t['taux_reconstitution']}%",
            "Indices": "✅" if t["indices"] else "—",
            "Brokage": f"{t['brokage']:.0%}", "Marge": f"{t['marge']:.0%}",
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
    type_branche = st.radio("Type de branche",
        ["Développement long (As-If + Stabilisation + Projection CL)",
         "Développement court (As-If uniquement, pas de projection)"],
        key="type_branche", horizontal=True)
    is_long = "long" in type_branche
    c1, c2, c3 = st.columns(3)
    with c1: f_triangle = st.file_uploader("📁 Triangle développement", type=["xlsx","csv"], key="f_tri")
    with c2: f_gnpis    = st.file_uploader("📁 Base GNPIs",             type=["xlsx","csv"], key="f_gnp")
    with c3: f_indices  = st.file_uploader("📁 Table indices",          type=["xlsx","csv"], key="f_idx")

    annee_cotation = st.number_input("Année de cotation (n)", value=2026, step=1)
    seuil_stabilisation = st.number_input(
        "Seuil stabilisation (% inflation, 0 = toujours)",
        value=0.0, min_value=0.0, max_value=50.0, step=5.0) / 100
    pct_seuil = st.number_input(
        "Percentile seuil Pareto (p80 par défaut)",
        value=0.80, min_value=0.50, max_value=0.99, step=0.05, format="%.2f")

    if st.button("▶ Transformer le triangle", type="primary") and f_triangle and f_gnpis and f_indices:
        with st.spinner("🔄 Transformation en cours..."):
            progress = st.progress(0, text="Lecture des fichiers...")
            df_gnpis_df = pd.read_excel(f_gnpis)  if f_gnpis.name.endswith('xlsx') else pd.read_csv(f_gnpis)
            df_idx_df   = pd.read_excel(f_indices) if f_indices.name.endswith('xlsx') else pd.read_csv(f_indices)
            df_gnpis_df.columns = [str(c).strip() for c in df_gnpis_df.columns]
            df_idx_df.columns   = [str(c).strip() for c in df_idx_df.columns]

            progress.progress(10, text="Nettoyage indices...")
            df_idx_df['Annee'] = pd.to_numeric(
                df_idx_df['Annee'].astype(str).str.strip().str.replace('.0','',regex=False), errors='coerce')
            df_idx_df['Coefficients'] = pd.to_numeric(
                df_idx_df['Coefficients'].astype(str).str.strip()
                .str.replace(',','.',regex=False).str.replace(' ','',regex=False), errors='coerce')
            df_idx_df = df_idx_df.dropna(subset=['Annee','Coefficients'])
            df_idx_df['Annee'] = df_idx_df['Annee'].astype(int)
            df_idx_df = df_idx_df.sort_values('Annee')
            df_idx_set = df_idx_df.set_index('Annee')['Coefficients']

            def get_indice(annee):
                annee = int(annee)
                annees = df_idx_set.index.values.astype(int)
                valeurs = df_idx_set.values.astype(float)
                if annee in annees: return float(df_idx_set.loc[annee])
                if annee < annees[0]:
                    return float(valeurs[0] - (valeurs[1]-valeurs[0]) * (annees[0]-annee))
                if annee > annees[-1]:
                    return float(valeurs[-1] + (valeurs[-1]-valeurs[-2]) * (annee-annees[-1]))
                return float(np.interp(annee, annees, valeurs))

            I_cotation_val = get_indice(annee_cotation)
            st.info(f"📐 I_cotation({annee_cotation}) = {I_cotation_val:.4f}")

            progress.progress(20, text="Parsing triangle...")
            df_raw = pd.read_excel(f_triangle, header=None)
            ligne_annees = df_raw.iloc[0].tolist(); ligne_types = df_raw.iloc[1].tolist()
            annee_courante = None; col_info = []
            for i, (ann, typ) in enumerate(zip(ligne_annees, ligne_types)):
                if i == 0: col_info.append(('UW_YEAR', '')); continue
                try:
                    a = int(float(str(ann).strip().replace('.0','')))
                    if 2010 <= a <= 2050: annee_courante = a
                except: pass
                col_info.append((annee_courante, str(typ).strip().upper() if pd.notna(typ) else ''))

            df_data = df_raw.iloc[2:].reset_index(drop=True)
            df_data.iloc[:, 0] = df_data.iloc[:, 0].ffill()

            progress.progress(30, text="Extraction TOTAL...")
            records = []
            for idx_row, row in df_data.iterrows():
                try:
                    annee_surv = int(float(str(row.iloc[0]).strip().replace('.0','')))
                    if not (2010 <= annee_surv <= 2050): continue
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
            progress.progress(50, text="As-If...")
            df_liq['annee_ultime'] = df_liq['annee_surv'] + 9
            df_liq['I_ultime']     = df_liq['annee_ultime'].apply(get_indice)
            df_liq['I_reg']        = df_liq['annee_reg'].apply(get_indice)
            df_liq['I_surv']       = df_liq['annee_surv'].apply(get_indice)
            df_liq['Sk']           = df_liq['total'] * (df_liq['I_ultime'] / df_liq['I_reg'])

            progress.progress(55, text="Stabilisation...")
            df_liq['ratio_check'] = df_liq['I_reg'] / df_liq['I_surv']
            mask_stab = df_liq['ratio_check'] >= (1.0 + seuil_stabilisation)
            df_liq['S_prime_k'] = np.where(mask_stab, df_liq['Sk'] * (df_liq['I_surv'] / df_liq['I_reg']), df_liq['Sk'])
            df_liq['coeff_stab'] = np.where(df_liq['S_prime_k'] > 0, df_liq['Sk'] / df_liq['S_prime_k'], 1.0)
            n_stab = mask_stab.sum()
            annees_reg_stab = sorted(df_liq[mask_stab]['annee_reg'].unique().tolist())
            st.info(f"📊 Stabilisation | Seuil : {seuil_stabilisation*100:.0f}% | Obs. : {n_stab} | Années règlement : {annees_reg_stab}")

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
            res_maj = identifier_sinistres_majeurs(df_proj=df_proj, gnpi=gnpi, D=D_trav, C_tranche=C_trav,
                nb_annees_obs=df_proj['annee_surv'].nunique(), retour_ans=20)
            df_seuils, _ = selectionner_seuil_pareto(X=df_proj['Sprime_ultime'].values, D=D_trav)

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
                "chargement_majeurs": res_maj["chargement"],
            })
            st.success("✅ Transformation terminée !")

    if "df_liq" in st.session_state:
        c1, c2, c3 = st.columns(3)
        c1.metric("Observations", len(st.session_state['df_liq']))
        c2.metric("Sinistres",    st.session_state['df_liq']['sinistre_id'].nunique())
        c3.metric("Années",       st.session_state['df_liq']['annee_surv'].nunique())
        branch_label = "Longue" if st.session_state.get("is_long") else "Courte"
        st.info(f"🌿 Branche : **{branch_label}** | I_cotation({st.session_state.get('annee_cotation')}) = {st.session_state.get('I_cotation',1):.4f}")
        st.info(f"📐 Seuil : {st.session_state.get('seuil_est',0):,.0f} | Pm P99.5 : {st.session_state.get('Pm_proxy',0):,.0f} | Alpha : {st.session_state.get('alpha_est',0):.4f} | Lambda : {st.session_state.get('lambda_est',0):.4f}")
        if "res_majeurs" in st.session_state:
            res = st.session_state["res_majeurs"]
            c1, c2, c3, c4 = st.columns(4)
            c1.metric("Sinistres majeurs",  res["n_majeurs"])
            c2.metric("Sinistres courants", res["n_courants"])
            c3.metric("Pm (niveau retour)", f"{res['Pm']:,.0f} MAD")
            c4.metric("Chargement majeurs", f"{res['chargement']:.4%}")
            with st.expander("📊 Détail sinistres majeurs"):
                st.dataframe(res["df_chargements"], use_container_width=True)
            with st.expander("📊 Sélection seuil Pareto (TVE)"):
                st.dataframe(st.session_state["df_seuils_pareto"], use_container_width=True)
        with st.expander("📊 Triangle — vérification stabilisation"):
            cols_show = ['sinistre_id','annee_surv','annee_reg','dev','total','I_surv','I_reg','ratio_check','Sk','S_prime_k','coeff_stab']
            st.dataframe(st.session_state["df_liq"][[c for c in cols_show if c in st.session_state["df_liq"].columns]].head(50), use_container_width=True)
        with st.expander("📊 Facteurs Chain Ladder"):
            st.dataframe(st.session_state["df_facteurs"], use_container_width=True)
        with st.expander("📊 Projections"):
            st.dataframe(st.session_state["df_proj"].head(20), use_container_width=True)

# ════════════════════════════════════════════
# TAB 3 — BURNING COST
# ════════════════════════════════════════════

with tab3:
    section_header("Burning Cost", "Charges historiques réassurance par tranche", "🔥")
    st.caption("Ck = min(max(S'k_ultime − D, 0), L) × coeff_stab")

    if "df_proj" not in st.session_state:
        st.warning("⚠️ Transformez d'abord le triangle")
    else:
        if st.button("▶ Calculer le Burning Cost", type="primary"):
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
                    Pr_Rec = 0.0
                    for C_n in df_ch["charge"].values:
                        for r in range(1, n_rec + 1):
                            Pr_Rec += t_r * min(L, max(C_n - (r-1)*L, 0))
                    Pr_Rec /= L if L > 0 else 1
                    Rec = Pr_Rec / (Pr_Rec + N) if (Pr_Rec + N) > 0 else 0.0
                    charge_moy  = df_ch["charge"].mean()
                    taux_pur    = charge_moy / gnpi
                    taux_risque = taux_pur * 1.20
                    taux_technique = (taux_risque * (1 - Rec)) / (1 - t_info["brokage"] - t_info["frais"] - 0.0021)
                    taux_final = taux_technique * (1 + t_info["marge"] + t_info["retrocession"])
                    resultats_bc.append({
                        "tranche": t_info["nom"], "type": t_info["type"],
                        "charge_moy": charge_moy, "Pr_Rec": Pr_Rec, "Rec": Rec,
                        "taux_pur": taux_pur, "taux_risque": taux_risque,
                        "taux_technique": taux_technique, "taux_final": taux_final,
                        "detail_annuel": df_ch.to_dict("records")
                    })
                st.session_state["resultats_bc"] = resultats_bc

    if "resultats_bc" in st.session_state:
        tableau_resultats([{
            "Tranche": r["tranche"], "Type": r["type"],
            "Charge moy.": f"{r['charge_moy']:,.0f} MAD",
            "Pr_Rec": f"{r['Pr_Rec']:.4f}", "Rec": f"{r['Rec']:.4%}",
            "Taux pur": f"{r['taux_pur']:.4%}", "Taux risque": f"{r['taux_risque']:.4%}",
            "Taux technique": f"{r['taux_technique']:.4%}", "Taux final": f"{r['taux_final']:.4%}",
        } for r in st.session_state["resultats_bc"]], titre="📊 Résultats Burning Cost")

        st.divider()
        guide_prompt("Burning Cost",
            ["Sinistralité exceptionnelle 2020 (COVID)", "Portefeuille en croissance +15%/an", "Historique 10 ans, branche longue"],
            ["Comparer avec taux marché attendu 2-4%", "Signaler si BC < simulation de plus de 30%", "Identifier les années atypiques"],
            ["Taux BC N-1 : R&C=2.5%, CatL1=0%", "Objectif prime totale < 12M MAD", "Taux Partner Re 2025 : R&C=2.30%"],
            ["Tableau par tranche avec verdict ✅/⚠️/❌", "Recommandation unique par tranche", "Maximum 1 page"])

        st.markdown("### 🤖 Analyse Claude — Burning Cost")
        ctx_bc, inst_bc, inp_bc, out_bc = prompt_inputs(
            key_prefix="bc",
            placeholder_contexte="Ex: Sinistralité exceptionnelle 2020...",
            placeholder_instructions="Ex: Comparer avec taux marché 3-4%...",
            placeholder_input="Ex: Taux BC N-1 : R&C=2.5%",
            placeholder_output="Ex: Tableau par tranche + verdict OK/ALERTE/RÉVISER")

        if api_key and st.button("🤖 Recommandations Claude — BC"):
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
    st.caption("Simule S'0 sur Pareto — applique coeff Sk/S'k pour charge réassurance")

    if "alpha_est" not in st.session_state:
        st.warning("⚠️ Transformez d'abord le triangle")
    else:
        is_long_sim = st.session_state.get("is_long", True)
        st.info(f"🌿 Branche {'longue' if is_long_sim else 'courte'} | Seuil : {st.session_state['seuil_est']:,.0f} | Alpha: {st.session_state['alpha_est']:.4f} | Lambda: {st.session_state['lambda_est']:.4f}")
        c1, c2, c3, c4 = st.columns(4)
        with c1: st.number_input("Alpha",         value=st.session_state["alpha_est"],  step=0.01,     format="%.4f", key="alpha_input")
        with c2: st.number_input("Lambda",        value=st.session_state["lambda_est"], step=0.1,      format="%.4f", key="lambda_input")
        with c3: st.number_input("Seuil (MAD)",   value=st.session_state["seuil_est"],  step=50_000.0, format="%.0f", key="seuil_input")
        with c4: st.number_input("Nb simulations", value=10000, step=1000,               key="nsim_input")

        if st.button("▶ Lancer la simulation", type="primary"):
            with st.spinner("🎲 Simulation en cours..."):
                progress_sim = st.progress(0, text="Initialisation...")
                alpha_f = st.session_state["alpha_input"]; lambda_f = st.session_state["lambda_input"]
                seuil_f = st.session_state["seuil_input"]; n_s = int(st.session_state["nsim_input"])
                coeffs  = st.session_state["coeffs"]
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
                                U = np.random.uniform(size=N)
                                Sprime_sim = seuil_f * (U ** (-1/alpha_f))
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
                        tt = tr / (1 - t_info["brokage"] - t_info["frais"] - 0.0021)
                        tf = tt * (1 + t_info["marge"] + t_info["retrocession"])
                        return tp, tr, tt, tf

                    c_base = simuler(True, True, True); c_sans_aal = simuler(False, True, True)
                    c_sans_aad = simuler(True, False, True); c_sans_rec = simuler(True, True, False)
                    tp, tr, tt, tf = calc_taux(c_base)
                    tp2, tr2, tt2, tf2 = calc_taux(c_sans_aal)
                    tp3, tr3, tt3, tf3 = calc_taux(c_sans_aad)
                    tp4, tr4, tt4, tf4 = calc_taux(c_sans_rec)
                    resultats_sim.append({
                        "tranche": t_info["nom"], "type": t_info["type"],
                        "taux_pur": tp, "taux_risque": tr, "taux_technique": tt, "taux_final": tf,
                        "sans_aal": tt2, "sans_aad": tt3, "sans_rec": tt4,
                    })
                progress_sim.progress(100, text="Terminé !")
                st.session_state["resultats_sim"] = resultats_sim

    if "resultats_sim" in st.session_state:
        tableau_resultats([{
            "Tranche": r["tranche"], "Taux pur": f"{r['taux_pur']:.4%}",
            "Taux risque": f"{r['taux_risque']:.4%}", "Taux technique": f"{r['taux_technique']:.4%}",
            "Taux final": f"{r['taux_final']:.4%}", "Sans AAL": f"{r['sans_aal']:.4%}",
            "Sans AAD": f"{r['sans_aad']:.4%}", "Sans reconst.": f"{r['sans_rec']:.4%}",
        } for r in st.session_state["resultats_sim"]], titre="📊 Résultats Simulation")

        st.divider()
        guide_prompt("Simulation Pareto/Poisson",
            ["Alpha calibré sur données 2016-2025", "Lambda estimé sur portefeuille 183M MAD", "Seuil TVE retenu : p80 x D"],
            ["Analyser impact AAL sur tranche cat", "Comparer BC vs Simulation par tranche", "Recommander montant optimal des conditions"],
            ["Alpha R=1.45, Lambda R=3.2", "Résultats simulation N-1 : R&C=3.1%", "Période de retour majeurs : 20 ans"],
            ["Impact par condition en points de taux", "Classement NECESSAIRE/A AJUSTER/INUTILE", "Recommandation chiffrée par condition"])

        st.markdown("### 🤖 Analyse Claude — Simulation & Conditions")
        ctx_sim, inst_sim, inp_sim, out_sim = prompt_inputs(
            key_prefix="sim",
            placeholder_contexte="Ex: Nouveau modèle cat, lambda revu à la hausse...",
            placeholder_instructions="Ex: Seuil d'alerte écart = 20%...",
            placeholder_input="Ex: Résultats simulation N-1...",
            placeholder_output="Ex: Verdict par condition + impact en points de taux")

        if api_key and st.button("🤖 Recommandations Claude — Simulation"):
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
    st.header("Market Curve")
    st.caption("ROL = a x x^(-b)  |  x = (D + C/2) / GNPI  |  tau_pur = ROL x C / GNPI")

    f_mkt = st.file_uploader("📁 Données marché", type=["xlsx","csv"], key="f_mkt")

    with st.expander("⚙️ Paramètres de filtrage", expanded=False):
        c1, c2, c3 = st.columns(3)
        with c1:
            rol_min = st.number_input("ROL minimum (%)",  value=5.0,   step=1.0)  / 100
            rol_max = st.number_input("ROL maximum (%)",  value=100.0, step=10.0) / 100
        with c2:
            tolerance = st.number_input("Tolérance proximité ROL≈Midpoint (%)", value=50.0, step=5.0) / 100
            r2_min    = st.number_input("R² minimum accepté (%)", value=30.0, step=5.0) / 100
        with c3:
            filtre_branche = st.text_input("Filtre branche (INT_BUSINESS)", value="EVENEMENT")
            st.caption("Laisser vide = pas de filtre")

    if f_mkt and st.button("▶ Construire la market curve", type="primary"):
        with st.spinner("📈 Construction en cours..."):
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
                ✅ <b>{len(df_mkt)} points retenus</b> sur {n_avant} | Filtre branche : {n_filtre} | ROL hors bornes : {n_rol} | ROL≈Midpoint : {n_prox}
                </div>""", unsafe_allow_html=True)
            if len(df_mkt) < 5:
                st.error("❌ Moins de 5 points retenus."); st.stop()

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
                taux_tech = taux_risque / (1 - t['brokage'] - t['frais'] - 0.0021)
                n_rec = t['nb_reconstitutions']; t_r = t['taux_reconstitution'] / 100; L = t['portee']
                C_rep = taux_pur * gnpi
                Pr_Rec = sum(t_r * min(L, max(C_rep - (r-1)*L, 0)) for r in range(1, n_rec+1))
                Pr_Rec /= L if L > 0 else 1
                Rec = Pr_Rec / (Pr_Rec + 10) if (Pr_Rec + 10) > 0 else 0
                return {"tranche": t["nom"], "type": t["type"], "x_norm": x_norm,
                        "rol": rol, "taux_pur": taux_pur, "taux_tech": taux_tech, "taux": taux_tech * (1 - Rec)}

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
                st.warning("⚠️ Relâchement contrainte.")
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
                st.error("❌ Impossible d'ajuster la courbe."); st.stop()

            all_t = [tt["taux"] for r in resultats_mkt for tt in r["taux_tranches"]]
            med_g = np.median([t for t in all_t if t > 0]) if any(t > 0 for t in all_t) else 1
            r2v = [r["r2"] for r in resultats_mkt]; r2min_v, r2max_v = min(r2v), max(r2v)
            for r in resultats_mkt:
                tm = np.mean([tt["taux"] for tt in r["taux_tranches"]])
                r2_norm = (r["r2"] - r2min_v) / (r2max_v - r2min_v + 1e-10)
                ecart_med = abs(tm - med_g) / (med_g + 1e-10)
                taux_nuls = sum(1 for tt in r["taux_tranches"] if tt["taux"] <= 0)
                r["score"] = 0.5*r2_norm - 0.3*ecart_med - 0.2*r["cv_taux"] - taux_nuls*10.0 + (0.5 if r["r2_ok"] else 0)
            resultats_mkt = sorted(resultats_mkt, key=lambda x: x['score'], reverse=True)
            st.session_state["resultats_mkt"] = resultats_mkt
            st.session_state["df_mkt_clean"]  = df_mkt

    if "resultats_mkt" in st.session_state:
        rmt = st.session_state["resultats_mkt"]
        dmc = st.session_state["df_mkt_clean"]
        def predict_rol(x_norm, a, b): return a * (x_norm ** (-b))
        rows_recap = []
        for r in rmt:
            row = {"Q": f"Q{int(r['quantile']*100)}", "N": r["n_points"],
                   "a": f"{r['a']:.5f}", "b": f"{r['b']:.4f}",
                   "R2": f"{r['r2']:.4f}", "R2ok": "OK" if r["r2_ok"] else "faible",
                   "Score": f"{r['score']:.4f}"}
            for tt in r["taux_tranches"]:
                row[tt["tranche"]] = f"{tt['taux']:.4%}" if tt["taux"] > 0 else "NUL"
            rows_recap.append(row)
        st.subheader("📊 Comparaison ajustements — ROL = a x x^(-b)  |  x = (D+C/2)/GNPI")
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
        ax.set_title('Market Curve — ROL = a x x^(-b)', fontweight='bold', color='#1a1a1a')
        ax.legend(); ax.grid(alpha=0.3, linestyle='--')
        st.pyplot(fig)

        st.subheader("📊 Taux marché retenus")
        tableau_resultats([{
            "Tranche": tt["tranche"], "Type": tt["type"],
            "x=(D+C/2)/GNPI": f"{tt['x_norm']:.5f}",
            "ROL estimé": f"{tt['rol']:.4%}", "Taux pur": f"{tt['taux_pur']:.4%}",
            "Taux tech.": f"{tt['taux_tech']:.4%}",
            "Taux final": f"{tt['taux']:.4%}" if tt["taux"] > 0 else "NUL"
        } for tt in choix["taux_tranches"]])
        st.session_state["taux_mkt_final"] = choix["taux_tranches"]

        st.divider()
        guide_prompt("Market Curve",
            ["Marché 2025, 40 cotations XL événement", "Marché en durcissement +10-15%", "Modèle puissance ROL = a x x^(-b)"],
            ["Privilégier R2 >= 45% avec taux non nuls", "Signaler taux marché > 3x simulation", "Recommander UN seul ajustement"],
            ["Taux référence Cat L1=1.5%", "a=0.0487, b=0.605 (rapport FST)", "R2 acceptable > 40%"],
            ["Justification R2 + robustesse N", "Comparaison avec simulation", "Ajustement retenu avec a, b, R2"])

        st.markdown("### 🤖 Analyse Claude — Market Curve")
        ctx_mkt, inst_mkt, inp_mkt, out_mkt = prompt_inputs(
            key_prefix="mkt",
            placeholder_contexte="Ex: Marché en durcissement, hausse 15%...",
            placeholder_instructions="Ex: Privilégier N > 20 points...",
            placeholder_input="Ex: Taux référence Cat L1=1.5%",
            placeholder_output="Ex: Recommandation unique avec justification R2")

        if api_key and st.button("🤖 Recommandations Claude — Market Curve"):
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
    manquants = [n for n, k in [("BC","resultats_bc"),("Simulation","resultats_sim"),("Market Curve","taux_mkt_final")]
                 if k not in st.session_state]
    if manquants:
        st.warning(f"⚠️ Complétez d'abord : {', '.join(manquants)}")
    else:
        bc_map  = {r["tranche"]: r for r in st.session_state["resultats_bc"]}
        sim_map = {r["tranche"]: r for r in st.session_state["resultats_sim"]}
        mkt_map = {r["tranche"]: r["taux"] for r in st.session_state["taux_mkt_final"]}
        rows_rapport = []; prime_totale = 0
        for t in tranches_input:
            nom = t["nom"]
            bc_tt  = bc_map.get(nom,{}).get("taux_technique",0)
            sim_tt = sim_map.get(nom,{}).get("taux_technique",0)
            mkt    = mkt_map.get(nom, 0)
            if t["type"] == "travaillante":
                ecart = abs(bc_tt-sim_tt)/bc_tt*100 if bc_tt > 0 else 0
                taux_retenu = sim_tt
                methode = f"Simulation (ecart BC/Sim: {ecart:.0f}%) {'!' if ecart>25 else 'OK'}"
            else:
                taux_retenu = max(sim_tt, mkt)
                methode = "Simulation" if sim_tt >= mkt else "Marché"
            prime = gnpi * taux_retenu; prime_totale += prime
            rows_rapport.append({
                "Tranche": nom, "Type": t["type"],
                "Taux BC": f"{bc_tt:.4%}", "Taux Sim.": f"{sim_tt:.4%}",
                "Taux Marché": f"{mkt:.4%}", "Taux retenu": f"{taux_retenu:.4%}",
                "Prime (MAD)": f"{prime:,.0f}", "Méthode": methode
            })
        st.session_state["df_rapport"]   = pd.DataFrame(rows_rapport)
        st.session_state["prime_totale"] = prime_totale
        st.subheader("📊 Synthèse de tarification")
        st.dataframe(st.session_state["df_rapport"], use_container_width=True)
        c1, c2, c3 = st.columns(3)
        with c1: card("Prime totale", f"{prime_totale:,.0f} MAD", couleur="#2d8a4e", icone="💰")
        with c2: card("Taux global",  f"{prime_totale/gnpi:.4%}", couleur="#1a1a1a",  icone="📊")
        with c3: card("Tranches",     str(len(tranches_input)),   couleur="#2d8a4e",  icone="📋")

        st.divider()
        guide_prompt("Rapport Final",
            ["Négociation avec Partner Re / Munich Re", "Comité de tarification 15 janvier 2026", "Objectif prime < 14M MAD"],
            ["Justifier chaque taux retenu vs alternatives", "Comparer avec taux N-1 fournis", "Conclure sur positionnement vs marché"],
            ["Taux N-1 : R&C=3.1%, CatL1=1.2%, CatL2=0.8%", "Cotation Partner Re : R&C=2.30%", "Chargement majeurs = 0.05%"],
            ["Synthèse exécutive 5 lignes max", "Tableau récapitulatif final obligatoire", "Verdict : ACCEPTER / NEGOCIER / REFUSER"])

        st.markdown("### 🤖 Rapport Claude — Analyse finale")
        ctx_r, inst_r, inp_r, out_r = prompt_inputs(
            key_prefix="rapport",
            placeholder_contexte="Ex: Négociation réassureur XYZ, objectif prime < 14M MAD...",
            placeholder_instructions="Ex: Justifier chaque taux, comparer avec N-1...",
            placeholder_input="Ex: Taux N-1 : R&C=3.1%, CatL1=1.2%, CatL2=0.8%",
            placeholder_output="Ex: Rapport 1 page max, tableau synthèse obligatoire")

        if api_key and st.button("🤖 Générer le rapport Claude", type="primary"):
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
        st.dataframe(pd.DataFrame([{"Email": e, "Code": c, "Statut": "Actif"}
                                    for e, c in users.items()]), use_container_width=True)
        st.divider()
        st.markdown("#### ⚙️ Gérer les utilisateurs")
        st.info("Allez sur Streamlit Cloud -> Settings -> Secrets et ajoutez :\nadmin_password = 'VotreMDP'\n[users]\n'email@ex.com' = 'CODE'")
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
    elif admin_pwd:
        st.error("❌ Mot de passe incorrect")
