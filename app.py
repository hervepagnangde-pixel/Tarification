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
