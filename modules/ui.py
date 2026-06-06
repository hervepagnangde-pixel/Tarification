"""
Atlantic Re IA — UI Components
CSS design system Atlantic Re/Orange BF.
Inject with: st.markdown(f"<style>{CSS_ATLANTICRE}</style>", unsafe_allow_html=True)

Composants: card, section_header, tableau_resultats, progress_steps,
            tooltip, html_glossaire_inline, GLOSSAIRE_ACTUARIEL.
"""
import streamlit as st

CSS_ATLANTICRE = """
@import url('https://fonts.googleapis.com/css2?family=Montserrat:wght@300;400;500;600;700;800;900&family=Inter:wght@300;400;500;600;700&display=swap');

/* ── Variables de couleur Atlantic Re ── */
:root {
  --ar-primary:   #0d2b3e;
  --ar-teal:      #00b5a5;
  --ar-green:     #1a7a5a;
  --ar-green2:    #00c896;
  --ar-black:     #080d14;
  --ar-dark:      #111820;
  --ar-mid:       #1e3a52;
  --ar-light:     #e8f7f4;
  --ar-offwhite:  #f2f8f7;
  --ar-text:      #0a1628;
  --ar-muted:     #5a7a8a;
  --ar-border:    #d0e8e2;
  --ar-shadow:    rgba(0,181,165,0.18);
  --ar-orange:    #ff6b35;
}

/* ── Base ── */
* { font-family: 'Inter', 'Montserrat', sans-serif; box-sizing: border-box; }
.stApp { background: var(--ar-offwhite) !important; }

/* ── Scrollbar ── */
::-webkit-scrollbar { width: 5px; height: 5px; }
::-webkit-scrollbar-track { background: var(--ar-light); }
::-webkit-scrollbar-thumb { background: var(--ar-teal); border-radius: 10px; }

/* ── Titres ── */
h1 { color: var(--ar-primary); font-family: 'Montserrat', sans-serif; font-weight: 800;
     letter-spacing: -0.5px; }
h2 { color: var(--ar-primary); font-weight: 700;
     border-bottom: 3px solid var(--ar-teal); padding-bottom: 12px; margin-bottom: 20px; }
h3 { color: var(--ar-green); font-weight: 600; }

/* ── Boutons — style Orange BF large ── */
.stButton > button {
  background: linear-gradient(135deg, var(--ar-primary) 0%, var(--ar-mid) 100%);
  color: white; border: none; border-radius: 4px; padding: 12px 28px;
  font-weight: 700; font-size: 14px; font-family: 'Montserrat', sans-serif;
  text-transform: uppercase; letter-spacing: 0.5px;
  transition: all 0.3s ease; box-shadow: 0 4px 16px rgba(13,43,62,0.3);
  min-height: 44px;
}
.stButton > button:hover {
  background: linear-gradient(135deg, var(--ar-teal) 0%, var(--ar-green2) 100%);
  transform: translateY(-3px); box-shadow: 0 8px 24px var(--ar-shadow);
}
.stButton > button[kind="primary"] {
  background: linear-gradient(135deg, var(--ar-teal) 0%, var(--ar-green) 100%);
  box-shadow: 0 4px 16px var(--ar-shadow);
}
.stButton > button[kind="primary"]:hover {
  background: linear-gradient(135deg, var(--ar-primary) 0%, var(--ar-mid) 100%);
  box-shadow: 0 8px 24px rgba(13,43,62,0.4);
}
.stButton > button[kind="secondary"] {
  background: transparent; color: var(--ar-teal);
  border: 2px solid var(--ar-teal); border-radius: 4px;
}
.stButton > button[kind="secondary"]:hover {
  background: var(--ar-teal); color: white;
}

/* ── Onglets — style barre navigation Orange BF ── */
.stTabs [data-baseweb="tab-list"] {
  background: var(--ar-black);
  border-radius: 0; padding: 0 8px; gap: 2px;
  box-shadow: 0 4px 20px rgba(0,0,0,0.4);
  border-bottom: 3px solid var(--ar-teal);
}
.stTabs [data-baseweb="tab"] {
  color: #9ab5c5; font-weight: 600; font-size: 12px;
  font-family: 'Montserrat', sans-serif;
  border-radius: 0; padding: 14px 18px;
  text-transform: uppercase; letter-spacing: 0.5px;
  transition: all 0.25s ease; border-bottom: 3px solid transparent;
  margin-bottom: -3px;
}
.stTabs [data-baseweb="tab"]:hover {
  color: var(--ar-teal); background: rgba(0,181,165,0.08);
}
.stTabs [aria-selected="true"] {
  background: transparent !important; color: var(--ar-teal) !important;
  border-bottom: 3px solid var(--ar-teal) !important;
  box-shadow: none !important;
}

/* ── Sidebar — panel latéral sombre ── */
[data-testid="stSidebar"] {
  background: linear-gradient(180deg, var(--ar-black) 0%, var(--ar-primary) 100%) !important;
  border-right: none;
  box-shadow: 4px 0 24px rgba(0,0,0,0.3);
}
[data-testid="stSidebar"] * { color: #c8dce6 !important; }
[data-testid="stSidebar"] h1, [data-testid="stSidebar"] h2,
[data-testid="stSidebar"] h3 {
  color: var(--ar-teal) !important; border-bottom: 1px solid #1e3a52 !important;
  font-family: 'Montserrat', sans-serif !important; letter-spacing: 0.5px;
}
[data-testid="stSidebar"] .stTextInput input,
[data-testid="stSidebar"] .stNumberInput input {
  background: #0d2040; border: 1px solid #1e4060; color: white !important;
  border-radius: 4px;
}
[data-testid="stSidebar"] .stButton > button {
  background: linear-gradient(135deg, var(--ar-teal), var(--ar-green)) !important;
  border-radius: 4px; font-size: 12px; padding: 8px 16px;
}
[data-testid="stSidebar"] .stSelectbox [data-baseweb="select"] > div {
  background: #0d2040 !important; border-color: #1e4060 !important;
}

/* ── Métriques — cartes chiffrées ── */
[data-testid="stMetric"] {
  background: white; border-radius: 0;
  padding: 20px 24px; border: none;
  box-shadow: 0 2px 12px rgba(0,0,0,0.06);
  border-top: 4px solid var(--ar-teal);
  border-left: none;
  transition: all 0.3s ease;
  position: relative; overflow: hidden;
}
[data-testid="stMetric"]::before {
  content: ''; position: absolute; top:0; right:0;
  width: 60px; height: 100%;
  background: linear-gradient(135deg, transparent, rgba(0,181,165,0.06));
}
[data-testid="stMetric"]:hover {
  transform: translateY(-4px); box-shadow: 0 12px 30px var(--ar-shadow);
  border-top-color: var(--ar-green2);
}
[data-testid="stMetricLabel"] {
  color: var(--ar-muted) !important; font-size: 11px !important;
  font-weight: 700 !important; text-transform: uppercase; letter-spacing: 1px;
}
[data-testid="stMetricValue"] {
  color: var(--ar-primary) !important; font-weight: 800 !important;
  font-family: 'Montserrat', sans-serif !important; font-size: 24px !important;
}

/* ── DataFrames ── */
[data-testid="stDataFrame"] {
  border-radius: 0; overflow: hidden;
  box-shadow: 0 4px 20px rgba(0,0,0,0.08); border: none;
  border-top: 3px solid var(--ar-teal);
}

/* ── Inputs ── */
.stTextInput input, .stNumberInput input, .stTextArea textarea {
  border: 1.5px solid var(--ar-border); border-radius: 4px;
  padding: 12px 16px; font-size: 14px;
  transition: all 0.2s ease; background: white; color: var(--ar-text);
}
.stTextInput input:focus, .stNumberInput input:focus, .stTextArea textarea:focus {
  border-color: var(--ar-teal); box-shadow: 0 0 0 3px rgba(0,181,165,0.12); outline: none;
}
.stSelectbox > div > div { border: 1.5px solid var(--ar-border); border-radius: 4px; }
.stSelectbox > div > div:hover { border-color: var(--ar-teal); }

/* ── Expanders ── */
.streamlit-expanderHeader {
  background: white; border-radius: 0;
  border: none; border-left: 4px solid var(--ar-teal);
  font-weight: 600; color: var(--ar-primary); padding: 14px 18px;
  transition: all 0.2s ease; font-family: 'Montserrat', sans-serif;
  box-shadow: 0 2px 8px rgba(0,0,0,0.05);
}
.streamlit-expanderHeader:hover {
  border-left-color: var(--ar-green2); color: var(--ar-teal);
  background: var(--ar-light);
}
.streamlit-expanderContent {
  border: none; border-left: 4px solid var(--ar-light);
  background: white; padding: 16px 20px;
  box-shadow: 0 4px 12px rgba(0,0,0,0.04);
}

/* ── Progress bars ── */
.stProgress > div > div {
  background: linear-gradient(90deg, var(--ar-teal), var(--ar-green2));
  border-radius: 0;
}
.stProgress > div { background: var(--ar-light); border-radius: 0; }

/* ── Tooltips actuariels ── */
.ar-tooltip {
  position: relative; cursor: help;
  border-bottom: 1px dashed var(--ar-teal); color: var(--ar-teal);
  font-weight: 600;
}
.ar-tooltip::after {
  content: attr(data-tip);
  position: absolute; bottom: 125%; left: 50%; transform: translateX(-50%);
  background: var(--ar-primary); color: white;
  padding: 6px 10px; border-radius: 6px; font-size: 12px; font-weight: 400;
  white-space: nowrap; z-index: 1000; pointer-events: none;
  opacity: 0; transition: opacity 0.2s; max-width: 320px; white-space: normal;
  border: 1px solid var(--ar-teal);
}
.ar-tooltip:hover::after { opacity: 1; }

/* ── Scénario comparison cards ── */
.comp-card {
  background: white; border-top: 4px solid var(--ar-teal);
  padding: 16px; box-shadow: 0 2px 8px rgba(0,0,0,0.06);
}
.comp-card.highlight { border-top-color: #00c896; background: #f2fff9; }

/* ── Executive dashboard ── */
.exec-kpi { display:flex;gap:12px;flex-wrap:wrap;margin-bottom:12px; }
.exec-kpi-item {
  flex:1;min-width:140px;background:white;padding:14px 18px;
  border-top:3px solid var(--ar-teal);box-shadow:0 2px 8px rgba(0,0,0,0.06);
}


/* ── Success / Warning / Error — style Orange BF ── */
.stSuccess, div[data-baseweb="notification"][kind="positive"] {
  background: linear-gradient(135deg, #00c896, #1a7a5a) !important;
  color: white !important; border-radius: 4px; border: none !important;
  font-weight: 600;
}
.stWarning { border-left: 4px solid var(--ar-orange) !important; }
.stError   { border-left: 4px solid #e74c3c !important; }

/* ── Checkboxes et radios ── */
.stCheckbox label { color: var(--ar-text) !important; font-weight: 500; }
.stRadio label { color: var(--ar-text) !important; }

/* ── Sliders ── */
.stSlider div[data-baseweb="slider"] div[role="slider"] {
  background: var(--ar-teal) !important;
}

/* ── Header app top bar ── */
header[data-testid="stHeader"] {
  background: var(--ar-black) !important;
  border-bottom: 3px solid var(--ar-teal) !important;
}
"""

def card(titre, valeur, couleur="#00b5a5", icone="📊", sous_titre=""):
    """Carte chiffrée style Orange BF / Atlantic Re."""
    st.markdown(f"""
    <div style="background:white;border-top:4px solid {couleur};
        padding:20px 24px;box-shadow:0 4px 20px rgba(0,0,0,0.08);
        margin-bottom:12px;position:relative;overflow:hidden;transition:all 0.3s ease"
        onmouseover="this.style.boxShadow='0 8px 32px rgba(0,181,165,0.2)';this.style.transform='translateY(-3px)'"
        onmouseout="this.style.boxShadow='0 4px 20px rgba(0,0,0,0.08)';this.style.transform='translateY(0)'">
      <div style="position:absolute;top:0;right:0;width:80px;height:100%;
          background:linear-gradient(135deg,transparent,rgba(0,181,165,0.05))"></div>
      <div style="font-size:11px;color:#5a7a8a;font-weight:700;text-transform:uppercase;
          letter-spacing:1px;margin-bottom:8px">{icone} {titre}</div>
      <div style="font-size:26px;font-weight:800;color:#0d2b3e;
          font-family:'Montserrat',sans-serif;line-height:1.1">{valeur}</div>
      {f'<div style="font-size:11px;color:#5a7a8a;margin-top:4px">{sous_titre}</div>' if sous_titre else ''}
    </div>""", unsafe_allow_html=True)


def section_header(titre, sous_titre="", icone="", couleur="#0d2b3e"):
    """En-tête de section style Orange BF — bande pleine largeur."""
    st.markdown(f"""
    <div style="background:linear-gradient(135deg,{couleur} 0%,#1e3a52 60%,#004d40 100%);
        padding:24px 32px;margin-bottom:24px;
        box-shadow:0 6px 24px rgba(0,0,0,0.2);
        border-bottom:4px solid #00b5a5;position:relative;overflow:hidden">
      <div style="position:absolute;right:20px;top:50%;transform:translateY(-50%);
          opacity:0.08;font-size:80px">{icone}</div>
      <div style="font-size:22px;font-weight:800;color:white;
          font-family:'Montserrat',sans-serif;letter-spacing:-0.3px">{icone} {titre}</div>
      {f'<div style="font-size:13px;color:rgba(255,255,255,0.75);margin-top:6px;font-weight:400">{sous_titre}</div>' if sous_titre else ''}
    </div>""", unsafe_allow_html=True)


def tableau_resultats(donnees, titre=""):
    """Tableau de données style Atlantic Re / Orange BF."""
    if not donnees: return
    if titre:
        st.markdown(f"""<div style="font-size:15px;font-weight:700;color:#0d2b3e;
            margin-bottom:12px;padding-bottom:8px;
            border-bottom:2px solid #00b5a5;font-family:'Montserrat',sans-serif">
            {titre}</div>""", unsafe_allow_html=True)
    colonnes = list(donnees[0].keys())
    html = """<div style="overflow-x:auto;box-shadow:0 4px 20px rgba(0,0,0,0.08);border-top:3px solid #00b5a5">
    <table style="width:100%;border-collapse:collapse;font-size:13px;background:white">
    <thead><tr style="background:linear-gradient(135deg,#0d2b3e,#1e3a52)">"""
    for col in colonnes:
        html += f'<th style="padding:13px 18px;text-align:left;color:#00b5a5;font-weight:700;font-family:Montserrat,sans-serif;font-size:11px;text-transform:uppercase;letter-spacing:0.8px;white-space:nowrap">{col}</th>'
    html += "</tr></thead><tbody>"
    for i, row in enumerate(donnees):
        bg = "white" if i % 2 == 0 else "#f2f8f7"
        html += f'<tr style="background:{bg};transition:background 0.15s" onmouseover="this.style.background=\'#e4f7f2\'" onmouseout="this.style.background=\'{bg}\'">'
        for col in colonnes:
            val = row.get(col, "")
            color = "#0a1628"
            fw = "500"
            if "%" in str(val) and any(c.isdigit() for c in str(val)):
                try:
                    num = float(str(val).replace("%","").replace(",",".").strip())
                    if num > 5:   color = "#c0392b"; fw = "700"
                    elif num > 2: color = "#e67e22"; fw = "600"
                    elif num > 0: color = "#1a7a5a"; fw = "600"
                except: pass
            if "✅" in str(val): color = "#1a7a5a"; fw = "700"
            if "⚠️" in str(val): color = "#e67e22"; fw = "600"
            if "🚨" in str(val) or "❌" in str(val): color = "#c0392b"; fw = "700"
            html += f'<td style="padding:12px 18px;border-bottom:1px solid #e8f7f4;color:{color};font-weight:{fw};font-size:13px">{val}</td>'
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
