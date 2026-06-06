"""
Atlantic Re IA — Programme optimization & utilities
Variantes A/B/C, panneau audit, lookup helpers, JSON safe.
"""
import numpy as np
import pandas as pd
import streamlit as st
from datetime import datetime
from modules.ui import tableau_resultats, card, section_header

# ════════════════════════════════════════════
# MODULE OPTIMISATION PROGRAMME — 3 VARIANTES
# ════════════════════════════════════════════

def optimiser_programme_variantes(tranches, gnpi_val, resultats_sim, resultats_bc, taux_mkt_final):
    """Génère 3 variantes de programme optimal (A=cédante, B=réassureur, C=équilibre)."""
    from scipy.optimize import minimize
    import numpy as np

    def taux_sim_pour_tranche(idx, portee_new, priorite_new, aal_new, aad_new, nb_recon_new):
        """Estime le taux technique pour des paramètres modifiés (interpolation linéaire)."""
        if idx >= len(resultats_sim): return 0.0
        r = resultats_sim[idx]
        base = r.get("taux_technique", 0)
        # Sensibilités approximatives
        t_orig = tranches[idx]
        ratio_portee   = portee_new   / max(t_orig["portee"],   1)
        ratio_priorite = priorite_new / max(t_orig["priorite"], 1)
        # Taux varie ~ sqrt(portee) et ~ 1/priorite^0.5 (approximation log-log)
        adj = (ratio_portee ** 0.5) / (ratio_priorite ** 0.3)
        # Chargement AAL / reconstitutions
        r_sans_aal = r.get("sans_aal", base); r_sans_rec = r.get("sans_rec", base)
        adj_aal = 0.0 if aal_new > 0 else (r_sans_aal - base)
        adj_rec = (nb_recon_new / max(t_orig["nb_reconstitutions"], 1) - 1) * (r_sans_rec - base) * 0.5
        return max(base * adj + adj_aal + adj_rec, 0)

    base_tranches = [dict(t) for t in tranches]
    resultats_variantes = {}

    for perspective in ["cedante", "reassureur", "equilibre"]:
        variante_tranches = []
        for i, t in enumerate(base_tranches):
            t_var = dict(t)
            if perspective == "cedante":
                # Maximiser protection : élargir portée, baisser priorité, plus de reconstitutions
                t_var["portee"]             = round(t["portee"] * 1.15 / 500_000) * 500_000
                t_var["priorite"]           = round(t["priorite"] * 0.90 / 500_000) * 500_000
                t_var["nb_reconstitutions"] = min(t["nb_reconstitutions"] + 1, 3)
                if t["type"] == "travaillante":
                    t_var["AAL"]            = round(t_var["portee"] * 2.0 / 100_000) * 100_000
                    t_var["AAD"]            = round(t.get("AAD", 0) * 0.80 / 100_000) * 100_000 if t.get("AAD") else None
            elif perspective == "reassureur":
                # Maximiser rendement : réduire portée, augmenter priorité, moins de reconstitutions
                t_var["portee"]             = round(t["portee"] * 0.85 / 500_000) * 500_000
                t_var["priorite"]           = round(t["priorite"] * 1.10 / 500_000) * 500_000
                t_var["nb_reconstitutions"] = max(t["nb_reconstitutions"] - 1, 1)
                if t["type"] == "travaillante":
                    t_var["AAL"]            = round(t_var["portee"] * 1.5 / 100_000) * 100_000
                    t_var["AAD"]            = round((t.get("AAD", 0) or t["portee"]*0.3) * 1.20 / 100_000) * 100_000
            else:  # equilibre
                # Compromis : légère optimisation des deux côtés
                t_var["portee"]             = t["portee"]
                t_var["priorite"]           = t["priorite"]
                t_var["nb_reconstitutions"] = t["nb_reconstitutions"]
                if t["type"] == "travaillante" and t.get("AAL"):
                    t_var["AAL"] = round(t["AAL"] * 1.05 / 100_000) * 100_000

            # Garantir valeurs minimales
            t_var["portee"]   = max(t_var["portee"],   1_000_000)
            t_var["priorite"] = max(t_var["priorite"], 500_000)
            variante_tranches.append(t_var)

        # Calculer prime estimée pour cette variante
        prime_v = 0.0
        taux_v  = []
        for i, t_var in enumerate(variante_tranches):
            tt = taux_sim_pour_tranche(i,
                t_var["portee"], t_var["priorite"],
                t_var.get("AAL", 0) or 0,
                t_var.get("AAD", 0) or 0,
                t_var["nb_reconstitutions"])
            prime_v += gnpi_val * tt
            taux_v.append(tt)

        resultats_variantes[perspective] = {
            "tranches":    variante_tranches,
            "taux":        taux_v,
            "prime":       prime_v,
            "taux_global": prime_v / gnpi_val if gnpi_val else 0,
        }

    return resultats_variantes


def afficher_variantes_optimisation(variantes, gnpi_val, tranches_ref):
    """Affiche les 3 variantes dans Tab6."""
    st.markdown("---")
    st.markdown("""<div style="background:linear-gradient(135deg,#1a1a1a 0%,#2d2d2d 100%);
        border-radius:12px;padding:20px 24px;margin-bottom:20px">
        <div style="font-size:18px;font-weight:700;color:white">⚡ Optimisation du Programme — 3 Variantes</div>
        <div style="font-size:13px;color:#aaa;margin-top:4px">
        En tant que leader (Partner Re) : propositions structurées pour la négociation
        </div></div>""", unsafe_allow_html=True)

    cols = st.columns(3)
    configs = [
        ("cedante",    "💼 Variante A", "Avantage Cédante",    "#3b82f6", "Maximise la protection — portée +15%, priorité -10%, reconstitutions +1"),
        ("reassureur", "📈 Variante B", "Avantage Réassureur", "#ef4444", "Maximise le rendement — portée -15%, priorité +10%, AAD renforcé"),
        ("equilibre",  "⚖️ Variante C", "Programme Équilibré", "#2d8a4e", "Compromis optimal — proposition de négociation finale Partner Re"),
    ]

    for col, (key, label, subtitle, color, desc) in zip(cols, configs):
        v = variantes.get(key, {}); t_list = v.get("tranches", [])
        prime = v.get("prime", 0); taux_g = v.get("taux_global", 0)
        with col:
            st.markdown(f"""<div style="background:white;border-radius:12px;padding:16px;
                border-top:4px solid {color};box-shadow:0 2px 8px rgba(0,0,0,0.08);margin-bottom:12px">
                <div style="font-size:15px;font-weight:700;color:{color}">{label}</div>
                <div style="font-size:12px;font-weight:600;color:#333;margin:4px 0">{subtitle}</div>
                <div style="font-size:11px;color:#666;margin-bottom:12px">{desc}</div>
                <div style="font-size:20px;font-weight:700;color:#1a1a1a">{prime:,.0f} MAD</div>
                <div style="font-size:12px;color:#888">Taux global : {taux_g:.4%}</div>
                </div>""", unsafe_allow_html=True)
            if t_list:
                rows_v = []
                for i, t_v in enumerate(t_list):
                    t_ref = tranches_ref[i] if i < len(tranches_ref) else {}
                    delta_p = t_v["portee"] - t_ref.get("portee", t_v["portee"])
                    delta_d = t_v["priorite"] - t_ref.get("priorite", t_v["priorite"])
                    rows_v.append({
                        "Tranche": t_v["nom"],
                        "Portée": f"{t_v['portee']/1e6:.0f}M {'↑' if delta_p>0 else '↓' if delta_p<0 else '='}",
                        "Priorité": f"{t_v['priorite']/1e6:.0f}M {'↑' if delta_d>0 else '↓' if delta_d<0 else '='}",
                        "Reconst.": f"{t_v['nb_reconstitutions']}x100%",
                        "AAL": f"{(t_v.get('AAL') or 0)/1e6:.0f}M" if t_v.get("AAL") else "—",
                    })
                tableau_resultats(rows_v)

    # Tableau comparatif
    st.markdown("### 📊 Comparaison des 3 variantes vs Programme actuel")
    prime_base = sum(gnpi_val * v.get("taux",[0])[i] if i < len(v.get("taux",[])) else 0
                     for i in range(len(tranches_ref))
                     for kk, v in variantes.items() if kk == "equilibre") or 0
    rows_comp = []
    prime_actuelle = None
    for key, label, *_ in configs:
        v = variantes.get(key, {})
        prime_v = v.get("prime", 0)
        if prime_actuelle is None: prime_actuelle = prime_v
        rows_comp.append({
            "Variante": label.replace("💼 ","").replace("📈 ","").replace("⚖️ ",""),
            "Prime estimée": f"{prime_v:,.0f} MAD",
            "Taux global": f"{v.get('taux_global',0):.4%}",
            "Écart vs équilibre": f"{(prime_v - variantes.get('equilibre',{}).get('prime',prime_v))/gnpi_val*100:+.2f} pts",
            "Recommandation": "⬆️ Protège la cédante" if key=="cedante" else "⬇️ Protège le réassureur" if key=="reassureur" else "✅ Proposition finale"
        })
    tableau_resultats(rows_comp)
    st.info("💡 En tant que leader Partner Re : proposer la Variante C comme base de négociation, avec la Variante B comme position de repli en cas de sinistralité élevée.")


def afficher_panneau_audit(tranches, resultats_bc, resultats_sim, taux_mkt_final,
                            df_rapport, prime_totale, gnpi_val):
    """Panneau de transparence pour managers — explicabilité complète."""
    st.markdown("---")
    with st.expander("🔍 Panneau Transparence & Audit — Pour la direction", expanded=False):
        st.markdown("""<div style="background:rgba(59,130,246,0.08);border-left:4px solid #3b82f6;
            border-radius:0 8px 8px 0;padding:14px 18px;margin-bottom:16px">
            <b style="color:#3b82f6">Ce panneau est destiné au comité de direction.</b><br>
            Il montre comment chaque chiffre a été calculé, quelles règles ont été appliquées,
            et où se trouvent les zones d'incertitude. L'actuaire reste décisionnaire.
            </div>""", unsafe_allow_html=True)

        st.markdown("#### 1️⃣ Règles actuarielles appliquées")
        regles = []
        for r in resultats_bc:
            n_nz = r.get("n_ann_nonzero", 0)
            sigma = r.get("sigma_hist", 0)
            regle = "R2 — BC=0 (< 3 ans non nuls)" if n_nz < 3 else f"R1 — τ_risque = τ_pur + σ ({sigma:.4%}) × 20%"
            statut = "⚠️ Données insuffisantes" if n_nz < 3 else "✅ Données suffisantes"
            regles.append({
                "Tranche": r["tranche"], "Type": r["type"],
                "Années non-nulles": f"{n_nz}",
                "σ historique": f"{sigma:.4%}",
                "Règle appliquée": regle,
                "Statut": statut,
            })
        tableau_resultats(regles)

        st.markdown("#### 2️⃣ Comparaison des 3 méthodes")
        comp_m = []
        for i, t in enumerate(tranches):
            nom = t["nom"]
            bc_t = next((r.get("taux_technique",0) for r in resultats_bc if r["tranche"]==nom), 0)
            si_t = next((r.get("taux_technique",0) for r in resultats_sim if r["tranche"]==nom), 0)
            mk_t = next((r.get("taux",0) for r in taux_mkt_final if r["tranche"]==nom), 0) if t["type"]!="travaillante" else None
            rpt  = df_rapport[df_rapport["Tranche"]==nom].iloc[0] if not df_rapport.empty and nom in df_rapport["Tranche"].values else {}
            retenu = rpt.get("Taux retenu","—") if hasattr(rpt,"get") else "—"
            comp_m.append({
                "Tranche": nom, "Type": t["type"],
                "BC": f"{bc_t:.4%}" if bc_t else "0% (R2)",
                "Simulation": f"{si_t:.4%}",
                "Market curve": f"{mk_t:.4%}" if mk_t is not None else "N/A (trav.)",
                "Taux retenu": retenu if isinstance(retenu,str) else f"{retenu:.4%}",
                "Logique": f"max(BC,Sim)" if t["type"]=="travaillante" else "max(Sim,Mkt)",
            })
        tableau_resultats(comp_m)

        st.markdown("#### 3️⃣ Piste d'audit — Décisions de l'agent")
        st.markdown(f"""<div style="background:#f9fafb;border-radius:8px;padding:14px;font-size:12px;
            font-family:monospace;border:1px solid #e0e0e0">
            📅 Date : {datetime.now().strftime("%d/%m/%Y %H:%M")} |
            GNPI : {gnpi_val:,} MAD |
            Prime totale : {prime_totale:,.0f} MAD |
            Taux global : {prime_totale/gnpi_val:.4%} |
            Tranches : {len(tranches)}<br>
            Formule τ_risque : τ_pur + σ_hist × 20% (CAS actuarial standards)<br>
            Règle R2 : BC = 0 si années non-nulles < 3<br>
            Market curve : cat uniquement (R² ≥ 0.45)<br>
            Sélection finale : max(BC, Sim) trav. | max(Sim, Mkt) cat
            </div>""", unsafe_allow_html=True)

        st.markdown("#### 4️⃣ Questions fréquentes managers")
        with st.expander("❓ Pourquoi le BC de certaines tranches cat est à 0 ?"):
            st.markdown("Parce que la règle actuarielle R2 interdit d'extrapoler à partir de moins de 3 années de sinistralité observée. Ce n'est pas une erreur — c'est une règle de prudence qui évite de construire une tarification sur des données insuffisantes.")
        with st.expander("❓ Comment vérifier les calculs ?"):
            st.markdown("Chaque calcul intermédiaire est affiché dans les onglets BC, Simulation et Market Curve. Les formules sont codées explicitement — il n'y a pas d'algorithme opaque.")
        with st.expander("❓ L'IA peut-elle se tromper ?"):
            st.markdown("Oui, comme tout outil de calcul. C'est pourquoi l'actuaire vérifie les résultats intermédiaires avant validation. L'avantage de cet outil : chaque hypothèse est documentée et traçable, contrairement à un fichier Excel.")
        with st.expander("❓ Qui est responsable du taux final ?"):
            st.markdown("L'actuaire qui valide le rapport. L'IA propose, l'actuaire décide. Le bouton 'Générer le rapport' est un acte de validation explicite.")

def _lookup_taux(results_list, nom, idx, key="taux_technique"):
    """Lookup par nom de tranche. Fallback par index si nom introuvable."""
    # Recherche par nom exact
    for r in results_list:
        if r.get("tranche","") == nom:
            return r.get(key, 0)
    # Fallback par index
    if idx < len(results_list):
        return results_list[idx].get(key, 0)
    return 0

def _lookup_result(results_list, nom, idx):
    """Retourne le dict complet par nom puis par index."""
    for r in results_list:
        if r.get("tranche","") == nom:
            return r
    if idx < len(results_list):
        return results_list[idx]
    return {}
