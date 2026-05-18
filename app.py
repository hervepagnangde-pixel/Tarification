import streamlit as st
import anthropic
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
from scipy.optimize import curve_fit 
from scipy.stats import pareto
import json

st.set_page_config(page_title="Agent Tarification Réassurance", layout="wide")
st.title("🎯 Agent Tarification Réassurance Non-Proportionnelle")

# ─── SIDEBAR ───
st.sidebar.header("⚙️ Configuration")
api_key = st.sidebar.text_input("Clé API Claude", type="password")
gnpi = st.sidebar.number_input("GNPI (MAD)", value=183_000_000, step=1_000_000)

# ─── FORMULAIRE PROGRAMME ───
st.header("📋 Programme de Réassurance")
st.subheader("Définir les tranches")

nb_tranches = st.number_input("Nombre de tranches", min_value=1, max_value=10, value=3)

tranches_input = []
for i in range(nb_tranches):
    st.markdown(f"**Tranche {i+1}**")
    col1, col2, col3 = st.columns(3)
    with col1:
        nom = st.text_input(f"Nom", value=f"Tranche {i+1}", key=f"nom_{i}")
        type_t = st.selectbox(f"Type", ["travaillante", "non_travaillante", "cat"], key=f"type_{i}")
        priorite = st.number_input(f"Priorité (MAD)", value=2_000_000, step=500_000, key=f"prio_{i}")
        portee = st.number_input(f"Portée/Limite (MAD)", value=13_000_000, step=500_000, key=f"port_{i}")
    with col2:
        st.markdown("**Conditions**")
        has_aal = st.checkbox(f"AAL", key=f"aal_{i}")
        aal_val = st.number_input(f"Montant AAL (MAD)", value=0, step=100_000, key=f"aal_v_{i}", disabled=not has_aal)
        has_aad = st.checkbox(f"AAD", key=f"aad_{i}")
        aad_val = st.number_input(f"Montant AAD (MAD)", value=0, step=100_000, key=f"aad_v_{i}", disabled=not has_aad)
    with col3:
        st.markdown("**Reconstitutions & Frais**")
        nb_recon = st.number_input(f"Nb reconstitutions", value=1, min_value=0, max_value=5, key=f"recon_{i}")
        tx_recon = st.number_input(f"Taux reconstitution (%)", value=100, min_value=0, max_value=200, key=f"txrecon_{i}")
        has_indices = st.checkbox(f"Indices", key=f"idx_{i}")
        brokage = st.number_input(f"Brokage (%)", value=10, min_value=0, max_value=30, key=f"brok_{i}")
        frais = st.number_input(f"Frais généraux (%)", value=5, min_value=0, max_value=20, key=f"frais_{i}")
        marge = st.number_input(f"Marge (%)", value=10, min_value=0, max_value=30, key=f"marge_{i}")
        retrocession = st.number_input(f"Rétrocession (%)", value=0, min_value=0, max_value=50, key=f"retro_{i}")

    tranches_input.append({
        "numero": i+1, "nom": nom, "type": type_t,
        "priorite": priorite, "portee": portee,
        "AAL": aal_val if has_aal else None,
        "AAD": aad_val if has_aad else None,
        "nb_reconstitutions": nb_recon,
        "taux_reconstitution": tx_recon,
        "indices": has_indices,
        "brokage": brokage/100,
        "frais": frais/100,
        "marge": marge/100,
        "retrocession": retrocession/100
    })
    st.divider()



# ─── SIMULATION ───
st.header("🎲 Simulation")

# ── Upload fichiers ──
st.subheader("📂 Données de base")
col1, col2, col3 = st.columns(3)
with col1:
    f_triangle = st.file_uploader("Triangle de développement", type=["xlsx","csv"])
with col2:
    f_gnpis = st.file_uploader("Base GNPIs (Annee, GNPI)", type=["xlsx","csv"])
with col3:
    f_indices = st.file_uploader("Table indices (Annee, Coefficients)", type=["xlsx","csv"])

annee_cotation = st.number_input("Année de cotation", value=2026, step=1)

if f_triangle and f_gnpis and f_indices:

    # ── Lecture ──
    df_tri_raw = pd.read_excel(f_triangle) if f_triangle.name.endswith('xlsx') else pd.read_csv(f_triangle)
    df_gnpis   = pd.read_excel(f_gnpis)   if f_gnpis.name.endswith('xlsx')   else pd.read_csv(f_gnpis)
    df_idx     = pd.read_excel(f_indices)  if f_indices.name.endswith('xlsx')  else pd.read_csv(f_indices)

    # Nettoyer colonnes
    df_gnpis.columns = [c.strip() for c in df_gnpis.columns]
    df_idx.columns   = [c.strip() for c in df_idx.columns]

    # Nettoyer virgules dans GNPIs
    for col in df_gnpis.columns:
        if df_gnpis[col].dtype == object:
            df_gnpis[col] = df_gnpis[col].str.replace(',','.').astype(float)

    st.success("✅ Fichiers chargés")

    with st.expander("Aperçu triangle brut"):
        st.dataframe(df_tri_raw.head(20))

    # ── Transformation triangle → liquidation ──
    st.subheader("🔄 Transformation en triangle de liquidation")

    if st.button("▶ Transformer le triangle"):
        with st.spinner("Transformation en cours..."):

            # Identifier les colonnes années (2016 à 2025)
            annees_reglement = [c for c in df_tri_raw.columns if str(c).strip().isdigit()]
            annees_reglement = sorted([int(a) for a in annees_reglement])

            # Remplir la colonne UW Year (année de survenance)
            # La colonne UW Year n'apparaît qu'une fois par groupe
            col_uwyear = df_tri_raw.columns[0]
            df_tri_raw[col_uwyear] = df_tri_raw[col_uwyear].fillna(method='ffill')

            # Pour chaque sinistre (ligne), extraire TOTAL par année règlement
            # Les colonnes TOTAL sont les colonnes de type "TOTAL" sous chaque année
            records = []
            
            # Détecter les colonnes TOTAL
            # Le triangle a structure : 2016(PAID,OS,TOTAL), 2017(PAID,OS,TOTAL)...
            cols = list(df_tri_raw.columns)
            
            for idx_row, row in df_tri_raw.iterrows():
                annee_surv = row[col_uwyear]
                
                # Essayer de convertir en entier
                try:
                    annee_surv = int(annee_surv)
                except:
                    continue
                
                # Parcourir les colonnes TOTAL par année règlement
                for i, col in enumerate(cols):
                    if 'TOTAL' in str(col).upper() or 'Total' in str(col):
                        # Trouver l'année règlement correspondante
                        # Chercher l'année dans les colonnes précédentes
                        annee_reg = None
                        for j in range(i, -1, -1):
                            try:
                                yr = int(str(cols[j]).strip())
                                if 2016 <= yr <= 2025:
                                    annee_reg = yr
                                    break
                            except:
                                continue
                        
                        if annee_reg is None:
                            continue
                        
                        val = row[col]
                        
                        # Nettoyer la valeur
                        try:
                            if isinstance(val, str):
                                val = val.replace(',','.').replace(' ','')
                                if any(c.isalpha() for c in val) or '#' in val:
                                    continue
                            val = float(val)
                            if val <= 0 or np.isnan(val):
                                continue
                        except:
                            continue
                        
                        # Calculer le développement
                        dev = annee_reg - annee_surv
                        if dev < 0 or dev > 9:
                            continue
                        
                        records.append({
                            'sinistre_id' : idx_row,
                            'annee_surv'  : annee_surv,
                            'annee_reg'   : annee_reg,
                            'dev'         : dev,
                            'total'       : val
                        })

            df_liq = pd.DataFrame(records)
            
            if df_liq.empty:
                st.error("❌ Triangle vide après transformation. Vérifiez le format.")
            else:
                st.success(f"✅ {len(df_liq)} observations extraites")
                with st.expander("Aperçu triangle de liquidation"):
                    st.dataframe(df_liq.head(30))
                st.session_state["df_liq"] = df_liq
                st.session_state["df_idx"] = df_idx
                st.session_state["df_gnpis"] = df_gnpis
                st.session_state["annee_cotation"] = annee_cotation



# ─── MARKET CURVE ───
st.header("📈 Market Curve")

f_mkt = st.file_uploader("Données marché (Excel)", type=["xlsx","csv"])

if f_mkt:
    df_mkt = pd.read_excel(f_mkt)
    
    # Nettoyage
    df_curve = df_mkt[['Priorité en MAD','ROLs']].dropna()
    if df_curve['ROLs'].dtype == object:
        df_curve['ROLs'] = df_curve['ROLs'].str.replace('%','').astype(float)/100
    
    x = df_curve['Priorité en MAD'].values
    y = df_curve['ROLs'].values

    # Modèle puissance
    def power_model(x, a, b):
        return a * np.power(x, -b)

    params, _ = curve_fit(power_model, x, y, p0=[1, 0.5], maxfev=5000)
    a, b = params

    # Résidus pour percentiles
    y_pred = power_model(x, a, b)
    residus = y - y_pred

    p25 = np.percentile(residus, 25)
    p75 = np.percentile(residus, 75)

    st.write(f"Modèle ajusté : y = {a:.5f} × x^(-{b:.4f})")

    # Graphique
    fig, ax = plt.subplots(figsize=(10, 5))
    ax.scatter(x, y, color='orange', s=60, zorder=5, label='Données marché')
    x_range = np.linspace(min(x), max(x), 300)
    ax.plot(x_range, power_model(x_range, a, b), 
            color='red', linewidth=2, label='Courbe centrale')
    ax.plot(x_range, power_model(x_range, a, b) + p25, 
            color='green', linewidth=1.5, linestyle='--', label='P25 (bas)')
    ax.plot(x_range, power_model(x_range, a, b) + p75, 
            color='blue', linewidth=1.5, linestyle='--', label='P75 (haut)')
    ax.set_xlabel('Priorité (MAD)')
    ax.set_ylabel('ROL')
    ax.set_title('Market Curve — P25 / Médiane / P75')
    ax.legend()
    ax.grid(alpha=0.3)
    st.pyplot(fig)

    # Taux par tranche
    st.subheader("📊 Taux marché par tranche")
    rows_mkt = []
    for t in tranches_input:
        rol_central = power_model(t['priorite'], a, b)
        rol_bas     = max(rol_central + p25, 0)
        rol_haut    = rol_central + p75

        taux_bas     = rol_bas     * (t['portee'] / gnpi)
        taux_central = rol_central * (t['portee'] / gnpi)
        taux_haut    = rol_haut    * (t['portee'] / gnpi)

        rows_mkt.append({
            "Tranche"       : t["nom"],
            "Type"          : t["type"],
            "Taux P25 (bas)": f"{taux_bas:.4%}",
            "Taux médian"   : f"{taux_central:.4%}",
            "Taux P75 (haut)": f"{taux_haut:.4%}",
            "ROL central"   : f"{rol_central:.4%}"
        })

    df_mkt_res = pd.DataFrame(rows_mkt)
    st.dataframe(df_mkt_res, use_container_width=True)

    # Analyse Claude
    if api_key:
        with st.spinner("Claude analyse la market curve..."):
            client = anthropic.Anthropic(api_key=api_key)
            analyse_mkt = client.messages.create(
                model="claude-opus-4-5", max_tokens=1000,
                messages=[{"role": "user", "content": f"""Tu es expert en réassurance non-proportionnelle.
Voici les taux de marché estimés par la market curve pour chaque tranche.
Pour chaque tranche dis quel taux choisir (P25, médian ou P75) et pourquoi.
Tiens compte du type de tranche (travaillante vs cat) et du contexte marché.

Taux marché :
{json.dumps(rows_mkt, indent=2)}

Tranches :
{json.dumps(tranches_input, indent=2)}"""
                }]
            )
            st.subheader("🤖 Recommandation Claude sur les taux marché")
            st.markdown(analyse_mkt.content[0].text)

    st.session_state["rows_mkt"] = rows_mkt
    st.success("✅ Market curve construite !")

# Résumé programme
if st.button("📊 Voir résumé du programme"):
    df_prog = pd.DataFrame([{
        "Tranche": t["nom"], "Type": t["type"],
        "Priorité": f"{t['priorite']:,}", "Portée": f"{t['portee']:,}",
        "AAL": t["AAL"] or "—", "AAD": t["AAD"] or "—",
        "Reconst.": f"{t['nb_reconstitutions']} x {t['taux_reconstitution']}%",
        "Indices": "✅" if t["indices"] else "—",
        "Brokage": f"{t['brokage']:.0%}", "Marge": f"{t['marge']:.0%}"
    } for t in tranches_input])
    st.dataframe(df_prog, use_container_width=True)
