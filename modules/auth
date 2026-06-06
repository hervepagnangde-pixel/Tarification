"""
Atlantic Re IA — Authentication & access control
"""
import streamlit as st

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
        st.markdown("# 🎯")
        st.markdown("### Atlantic Re IA")
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
