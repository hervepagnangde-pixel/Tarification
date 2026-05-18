import streamlit as st
import anthropic
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
from scipy.optimize import curve_fit
import json

# Configuration
st.set_page_config(page_title="Agent Tarification Réassurance", layout="wide")
st.title("🎯 Agent de Tarification Réassurance Non-Proportionnelle")

# Clé API
api_key = st.sidebar.text_input("Clé API Claude", type="password")
gnpi = st.sidebar.number_input("GNPI (MAD)", value=183_000_000, step=1_000_000)

# Upload fichiers
st.sidebar.header("Fichiers")
f_prog = st.sidebar.file_uploader("Programme", type=["xlsx","csv"])
f_bc   = st.sidebar.file_uploader("Burning Cost", type=["xlsx","csv"])
f_sim  = st.sidebar.file_uploader("Simulation", type=["csv","xlsx"])
f_mkt  = st.sidebar.file_uploader("Données Marché", type=["xlsx","csv"])

if st.sidebar.button("▶ Lancer l'analyse", disabled=not all([api_key, f_prog, f_bc, f_sim])):
    client = anthropic.Anthropic(api_key=api_key)

    # ETAPE 1 - Programme
    with st.spinner("Lecture du programme..."):
        df = pd.read_excel(f_prog, header=None)
        contenu = df.to_string()
        msg = client.messages.create(
            model="claude-opus-4-5", max_tokens=1000,
            messages=[{"role":"user","content":f"Extrait les tranches en JSON uniquement, sans markdown:\n{{\"tranches\":[{{\"numero\":1,\"nom\":\"Risk & Cat\",\"type\":\"travaillante\",\"priorite\":2000000,\"limite\":13000000}}]}}\n\n{contenu}"}]
        )
        texte = msg.content[0].text.replace("```json","").replace("```","").strip()
        tranches = json.loads(texte)["tranches"]
        st.success(f"✅ {len(tranches)} tranches identifiées")

    # ETAPE 2 - Burning Cost
    with st.spinner("Burning Cost..."):
        df_bc = pd.read_excel(f_bc, header=None)
        col_ha = df_bc.iloc[:, 208].dropna()
        bc_taux = float(col_ha[col_ha.apply(lambda x: isinstance(x, float))].values[0])
        bc_rates = {tranches[0]["nom"]: bc_taux}
        for t in tranches[1:]:
            bc_rates[t["nom"]] = 0.0
        st.success("✅ Taux BC calculés")

    # ETAPE 3 - Simulation
    with st.spinner("Simulation..."):
        df_sim = pd.read_csv(f_sim)
        sim_rates = {}
        for i, t in enumerate(tranches):
            sim_rates[t["nom"]] = {
                "taux_pur": df_sim.iloc[i]["Taux_PrimePure"],
                "taux_technique": df_sim.iloc[i]["Taux_Technique"]
            }
        st.success("✅ Taux simulation extraits")

    # ETAPE 4 - Market Curve
    taux_marche = {}
    if f_mkt:
        with st.spinner("Market Curve..."):
            df_mkt = pd.read_excel(f_mkt)
            df_curve = df_mkt[['Priorité en MAD','ROLs']].dropna()
            if df_curve['ROLs'].dtype == object:
                df_curve['ROLs'] = df_curve['ROLs'].str.replace('%','').astype(float)/100
            x = df_curve['Priorité en MAD'].values
            y = df_curve['ROLs'].values
            def power_model(x, a, b):
                return a * np.power(x, -b)
            params, _ = curve_fit(power_model, x, y, p0=[1, 0.5], maxfev=5000)
            a, b = params

            for t in tranches:
                rol = power_model(t['priorite'], a, b)
                taux_marche[t["nom"]] = rol * (t["limite"] / gnpi)

            # Graphique
            fig, ax = plt.subplots(figsize=(8,4))
            ax.scatter(x, y, color='orange', s=60, zorder=5, label='Données marché')
            x_range = np.linspace(min(x), max(x), 200)
            ax.plot(x_range, power_model(x_range, a, b), color='red', linewidth=2, label=f'y={a:.4f}×x^(-{b:.4f})')
            ax.set_xlabel('Priorité (MAD)'); ax.set_ylabel('ROL')
            ax.set_title('Market Curve'); ax.legend(); ax.grid(alpha=0.3)
            st.pyplot(fig)
            st.success("✅ Market curve construite")

    # ETAPE 5 - Rapport
    st.header("📊 Rapport de Tarification")
    rows = []
    prime_totale = 0
    for t in tranches:
        nom = t["nom"]
        bc = bc_rates.get(nom, 0)
        sim = sim_rates[nom]["taux_technique"]
        mkt = taux_marche.get(nom, 0)
        taux_retenu = max(sim, mkt) if t["type"] != "travaillante" else sim
        prime = gnpi * taux_retenu
        prime_totale += prime
        ecart = (sim - bc) / bc * 100 if bc > 0 else None
        alerte = "⚠️" if ecart and abs(ecart) > 25 else "✅"
        rows.append({
            "Tranche": nom,
            "Type": t["type"],
            "BC": f"{bc:.4%}",
            "Simulation": f"{sim:.4%}",
            "Marché": f"{mkt:.4%}" if mkt else "—",
            "Taux retenu": f"{taux_retenu:.4%}",
            "Prime (MAD)": f"{prime:,.0f}",
            "Statut": alerte
        })

    st.dataframe(pd.DataFrame(rows), use_container_width=True)
    st.metric("Prime totale", f"{prime_totale:,.0f} MAD")
    st.metric("Taux global", f"{prime_totale/gnpi:.4%}")
