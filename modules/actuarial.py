"""
Atlantic Re IA — Actuarial computations module
Tooltips, glossaire, Hill/MEF/GPD, Bühlmann-Straub, Bootstrap CI,
selectionner_seuil_pareto, identifier_sinistres_majeurs, 
section_analyse_distributions.
"""
import streamlit as st
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
from scipy import stats as _sp_stats
from modules.db import _get_conn, _ph, db_init
from modules.ui import tableau_resultats, card

def tooltip(terme, definition):
    """Retourne un terme avec tooltip HTML inline."""
    safe_def = definition.replace('"', '&quot;')
    return f'<span class="ar-tooltip" data-tip="{safe_def}">{terme}</span>'


GLOSSAIRE_ACTUARIEL = {
    "τ_pur":        "Taux pur = Charge moyenne / GNPI. Coût moyen annuel avant chargements.",
    "τ_risque":     "R1 : τ_risque = τ_pur + σ × 20%. Intègre un chargement de sécurité proportionnel à la volatilité.",
    "τ_technique":  "Taux technique = τ_risque × (1−Rec) / (1−Brokage−Frais−Marge−Rétro). Prix de revient du réassureur.",
    "σ":            "Écart-type des charges annuelles non nulles divisé par le GNPI. Mesure la volatilité historique.",
    "Rec":          "Facteur de reconstitution = Pr_Rec / (Pr_Rec + N). Réduction du taux liée aux primes de reconstitution.",
    "BC":           "Burning Cost = Σ charges XL nettes / Σ GNPI. Méthode de référence basée sur l'expérience réelle.",
    "ROL":          "Rate On Line = Prime XL / Portée. Indicateur standard de niveau de taux en réassurance cat.",
    "AAL":          "Annual Aggregate Limit. Plafond de la charge annuelle totale à la charge du réassureur.",
    "AAD":          "Annual Aggregate Deductible. Franchise annuelle agrégée : le réassuré conserve les premiers sinistres.",
    "Alpha (α)":    "Indice de queue Pareto. α faible = queue lourde (grands sinistres fréquents). Plage normale [0.8 ; 4.0].",
    "Lambda (λ)":   "Fréquence Poisson. Nombre moyen de sinistres/an au-dessus du seuil de modélisation.",
    "IBNR":         "Incurred But Not Reported. Sinistres survenus mais non encore déclarés. Estimés par Chain Ladder.",
    "IBNER":        "Incurred But Not Enough Reserved. Sinistres déclarés mais sous-réservés. Facteurs CL sur montants.",
    "GPD":          "Generalized Pareto Distribution. Utilisée pour modéliser les excédances au-dessus d'un seuil u (TVE).",
    "As-If":        "Revalorisation des sinistres historiques au niveau de coût de l'année de cotation. Sur incréments.",
    "Pm":           "Niveau de retour T ans. Calculé par GPD : Pm = u + (σ/ξ) × ((m×P(X>u))^ξ − 1).",
    "Credibility":  "Bühlmann-Straub : τ = Z × BC + (1−Z) × μ_priori. Z = n/(n+k), k = σ²_entre/σ²_intra.",
    "NSGA-II":      "Non-dominated Sorting Genetic Algorithm II (Deb 2002). Optimisation multi-objectif : τ min, Var min, Protection max.",
    "TOPSIS":       "Technique for Order Preference by Similarity to Ideal Solution. Compromise entre objectifs normalisés.",
    "Reconst.":     "Reconstitution : prime payée pour rétablir la capacité après sinistre. Taux variable par reconstitution.",
}


def html_glossaire_inline(texte):
    """Remplace automatiquement les termes du glossaire par des tooltips dans un texte HTML."""
    for terme, definition in GLOSSAIRE_ACTUARIEL.items():
        texte = texte.replace(terme, tooltip(terme, definition), 1)
    return texte


def buehlmann_straub_credibility(resultats_bc_list, a_priori_pct=None, gnpi_val=1.0):
    """
    Formule de Bühlmann-Straub (1967) — Crédibilité actuarielle.

    Z = n / (n + k)        où k = σ²_intra / σ²_inter
    τ_crédible = Z × τ_BC + (1 − Z) × μ_a_priori

    Avec σ²_intra = variance interne (fluctuation aléatoire) ≈ σ²_hist
         σ²_inter = variance entre portefeuilles (hétérogénéité structurelle)
         k         = ratio de crédibilité

    Retourne un dict par tranche avec Z, τ_crédible, interprétation.
    """
    resultats = {}
    for r in resultats_bc_list:
        nom       = r.get("tranche", "")
        tau_bc    = r.get("taux_technique", 0.0)
        sigma_h   = r.get("sigma_hist", 0.0)     # σ individuelle (intra)
        n_nz      = int(r.get("n_ann_nonzero", 0))

        # μ a priori : fourni manuellement ou calculé comme moyenne inter-portefeuilles
        mu = float(a_priori_pct or tau_bc or 0.03)

        if n_nz < 1 or sigma_h == 0:
            resultats[nom] = {
                "Z": 0.0, "tau_credible": mu,
                "interpretation": "Aucune donnée — a priori retenu",
                "formule": f"Z=0, τ={mu:.4%}"
            }
            continue

        # k estimé à partir du ratio de Bühlmann (hypothèse simplifiée)
        # σ²_inter estimée comme (variance entre la moyenne BC et l'a priori)
        sigma2_intra = sigma_h ** 2
        sigma2_inter = max((tau_bc - mu) ** 2, sigma2_intra * 0.1)  # garde-fou
        k = sigma2_intra / max(sigma2_inter, 1e-10)

        Z = n_nz / (n_nz + k)
        tau_credible = Z * tau_bc + (1 - Z) * mu

        if Z >= 0.80:
            interp = "Haute crédibilité — BC quasi-seul retenu"
        elif Z >= 0.50:
            interp = "Crédibilité moyenne — mélange BC et a priori"
        else:
            interp = "Faible crédibilité — a priori dominant"

        resultats[nom] = {
            "Z":              round(Z, 4),
            "tau_bc":         round(tau_bc, 6),
            "mu_a_priori":    round(mu, 6),
            "tau_credible":   round(tau_credible, 6),
            "k":              round(k, 4),
            "sigma_intra":    round(sigma_h, 6),
            "n_annees":       n_nz,
            "interpretation": interp,
            "formule":        f"Z={Z:.3f}, τ_BC={tau_bc:.4%}, μ={mu:.4%} → τ_cred={tau_credible:.4%}",
        }
    return resultats


def bootstrap_ci_bc(df_proj, tranche_info, gnpi_val, n_boot=2000, alpha_ci=0.05):
    """
    Intervalle de confiance Bootstrap sur le taux BC (Efron & Tibshirani, 1993).
    Rééchantillonne les années de sinistralité avec remise, recalcule le BC.
    Retourne IC [α/2, 1−α/2] sur le taux technique.
    """
    D   = tranche_info["priorite"];  L = tranche_info["portee"]
    aal = tranche_info.get("AAL");   aad = tranche_info.get("AAD")
    n_rec = tranche_info.get("nb_reconstitutions", 1)
    t_r   = tranche_info.get("taux_reconstitution", 100) / 100
    bk    = tranche_info["brokage"]; fg = tranche_info["frais"]
    mg    = tranche_info["marge"];   rt = tranche_info.get("retrocession", 0)
    cap   = (n_rec + 1) * L

    df_proj = df_proj.copy()
    df_proj["Ck"] = df_proj.apply(
        lambda row: min(max(row["Sprime_ultime"] - D, 0), L) * row["coeff_stab"], axis=1)
    charges_par_ann = df_proj.groupby("annee_surv")["Ck"].sum()
    charges_list    = []
    for ann, ch in charges_par_ann.items():
        if aad: ch = max(ch - aad, 0)
        if aal: ch = min(ch, aal)
        charges_list.append(float(min(ch, cap)))

    if len(charges_list) < 4:
        return None  # Pas assez de données pour bootstrap

    np.random.seed(42)
    boot_taux = []
    for _ in range(n_boot):
        sample    = np.random.choice(charges_list, size=len(charges_list), replace=True)
        nz        = [c for c in sample if c > 0]
        if len(nz) < 1: continue
        tp        = np.mean(sample) / gnpi_val
        sigma     = np.std(nz) / gnpi_val if len(nz) >= 2 else 0
        tr        = tp + sigma * 0.20
        tt        = (tr * (1 - 0.0)) / max(1 - bk - fg - mg - rt, 0.01)
        boot_taux.append(tt)

    if len(boot_taux) < 10:
        return None

    lo = float(np.percentile(boot_taux, 100 * alpha_ci / 2))
    hi = float(np.percentile(boot_taux, 100 * (1 - alpha_ci / 2)))
    med = float(np.median(boot_taux))
    return {"ic_lo": lo, "ic_hi": hi, "mediane_boot": med,
            "n_boot": n_boot, "alpha": alpha_ci,
            "label": f"IC {int((1-alpha_ci)*100)}% : [{lo:.4%}, {hi:.4%}]"}


def generer_pptx_rapport(gnpi_val, tranches, resultats_bc, resultats_sim,
                          taux_mkt_final, df_rapport, prime_totale, annee=2026):
    """
    Génère un rapport de tarification en format PPTX (6 slides).
    Palette : Ocean Executive — navy #0d2b3e + teal #00b5a5 + blanc
    """
    import io as _io_pptx
    import subprocess, os, tempfile, json as _json

    # Construire le script PptxGenJS
    taux_global = prime_totale / gnpi_val if gnpi_val else 0

    rows_rapport_js = "[]"
    if df_rapport is not None and not df_rapport.empty:
        rows_rapport_js = _json.dumps([
            {"t": str(r.get("Tranche","") or r.get("tranche","")),
             "bc": str(r.get("Taux BC","") or f"{r.get('taux_bc',0):.4%}"),
             "sim": str(r.get("Taux Sim.","") or f"{r.get('taux_sim',0):.4%}"),
             "mkt": str(r.get("Taux Marché","") or f"{r.get('taux_mkt',0):.4%}"),
             "ret": str(r.get("Taux retenu","") or f"{r.get('taux_retenu',0):.4%}"),
             "prime": str(r.get("Prime (MAD)","") or f"{r.get('prime_MAD',0):,.0f}")}
            for _, r in df_rapport.iterrows()
        ], ensure_ascii=False)

    tranches_js = _json.dumps([
        {"nom": t.get("nom",""), "type": t.get("type",""),
         "prio": f"{t.get('priorite',0)/1e6:.0f}M",
         "port": f"{t.get('portee',0)/1e6:.0f}M",
         "rec":  f"{t.get('nb_reconstitutions',1)}x{t.get('taux_reconstitution',100):.0f}%"}
        for t in tranches
    ], ensure_ascii=False)

    bc_js  = _json.dumps([{"t":r.get("tranche",""),"tt":f"{r.get('taux_technique',0):.4%}",
                            "tp":f"{r.get('taux_pur',0):.4%}","n":r.get("n_ann_nonzero",0)}
                           for r in (resultats_bc or [])], ensure_ascii=False)
    sim_js = _json.dumps([{"t":r.get("tranche",""),"tt":f"{r.get('taux_technique',0):.4%}",
                            "tp":f"{r.get('taux_pur',0):.4%}"}
                           for r in (resultats_sim or [])], ensure_ascii=False)

    script = f"""
const pptxgen = require("pptxgenjs");
const prs = new pptxgen();
prs.layout = 'LAYOUT_16x9';
prs.author = 'Atlantic Re IA';
prs.title = 'Rapport Tarification XL {annee}';

const NAV = "0d2b3e", TEAL = "00b5a5", WHITE = "FFFFFF", GRAY = "f2f8f7", MGRAY = "5a7a8a";
const tranches = {tranches_js};
const bcData   = {bc_js};
const simData  = {sim_js};
const rapport  = {rows_rapport_js};

// ── Slide 1 : Couverture ──────────────────────────────
let s1 = prs.addSlide();
s1.background = {{color: NAV}};
s1.addShape(prs.ShapeType.rect, {{x:0,y:4.5,w:10,h:1.125,fill:{{color:TEAL}}}});
s1.addText("ATLANTIC RE", {{x:0.5,y:0.8,w:9,h:1.2,fontSize:48,bold:true,color:WHITE,fontFace:"Georgia"}});
s1.addText("Rapport de Tarification {annee}", {{x:0.5,y:2.0,w:9,h:0.7,fontSize:24,color:TEAL,fontFace:"Calibri"}});
s1.addText("Réassurance Non-Proportionnelle · Automobile · Maroc", {{x:0.5,y:2.7,w:9,h:0.5,fontSize:14,color:WHITE,fontFace:"Calibri"}});
s1.addText("GNPI : {gnpi_val:,.0f} MAD  |  Prime totale : {prime_totale:,.0f} MAD  |  Taux global : {taux_global:.4%}", {{x:0.5,y:4.6,w:9,h:0.4,fontSize:12,color:NAV,fontFace:"Calibri"}});

// ── Slide 2 : Programme ───────────────────────────────
let s2 = prs.addSlide();
s2.background = {{color: GRAY}};
s2.addShape(prs.ShapeType.rect, {{x:0,y:0,w:10,h:0.9,fill:{{color:NAV}}}});
s2.addText("Programme de Réassurance", {{x:0.4,y:0,w:9,h:0.9,fontSize:22,bold:true,color:WHITE,valign:"middle"}});
const tRows = [["Tranche","Type","Priorité","Portée","Reconstitutions"].map(h=>{{text:h,options:{{bold:true,color:WHITE,fill:{{color:NAV}}}}}})]
  .concat(tranches.map(t=>[t.nom,t.type,t.prio,t.port,t.rec].map(v=>{{return{{text:v}}}})));
s2.addTable(tRows, {{x:0.4,y:1.1,w:9.2,colW:[2.5,1.5,1.8,1.8,1.6],border:{{type:'none'}},rowH:0.45,fontSize:13,fontFace:"Calibri",color:"1a1a1a",fill:{{color:WHITE}},border:{{pt:0.5,color:"d0e8e2"}}}});

// ── Slide 3 : Burning Cost ────────────────────────────
let s3 = prs.addSlide();
s3.background = {{color: GRAY}};
s3.addShape(prs.ShapeType.rect, {{x:0,y:0,w:10,h:0.9,fill:{{color:NAV}}}});
s3.addText("Burning Cost", {{x:0.4,y:0,w:9,h:0.9,fontSize:22,bold:true,color:WHITE,valign:"middle"}});
s3.addShape(prs.ShapeType.rect, {{x:0,y:0.85,w:10,h:0.06,fill:{{color:TEAL}}}});
s3.addText("Méthode de référence · As-If sur incréments · Règle R1 : τ_risque = τ_pur + σ × 20%", {{x:0.4,y:0.95,w:9.2,h:0.35,fontSize:11,color:MGRAY,italic:true}});
const bcRows = [[["Tranche","τ pur","τ technique","Années non nulles"].map(h=>{{text:h,options:{{bold:true,color:WHITE,fill:{{color:NAV}}}}}})]].flat()
  .concat ? [["Tranche","τ pur","τ technique","Années non nulles"].map(h=>{{text:h,options:{{bold:true,color:WHITE,fill:{{color:NAV}}}}}})]
  .concat(bcData.map(r=>[r.t,r.tp,r.tt,String(r.n)].map(v=>{{return{{text:v}}}}))) : [];
if(bcRows.length > 1) s3.addTable(bcRows, {{x:0.4,y:1.4,w:9.2,colW:[3,2,2.5,1.7],border:{{pt:0.5,color:"d0e8e2"}},rowH:0.5,fontSize:13,fontFace:"Calibri",color:"1a1a1a"}});

// ── Slide 4 : Simulation ──────────────────────────────
let s4 = prs.addSlide();
s4.background = {{color: GRAY}};
s4.addShape(prs.ShapeType.rect, {{x:0,y:0,w:10,h:0.9,fill:{{color:NAV}}}});
s4.addText("Simulation Pareto / Poisson", {{x:0.4,y:0,w:9,h:0.9,fontSize:22,bold:true,color:WHITE,valign:"middle"}});
s4.addShape(prs.ShapeType.rect, {{x:0,y:0.85,w:10,h:0.06,fill:{{color:TEAL}}}});
const simRows = [["Tranche","τ pur","τ technique"].map(h=>{{text:h,options:{{bold:true,color:WHITE,fill:{{color:NAV}}}}}})]
  .concat(simData.map(r=>[r.t,r.tp,r.tt].map(v=>{{return{{text:v}}}})));
if(simRows.length > 1) s4.addTable(simRows, {{x:0.4,y:1.4,w:9.2,colW:[3.5,2.5,3.2],border:{{pt:0.5,color:"d0e8e2"}},rowH:0.5,fontSize:13,fontFace:"Calibri",color:"1a1a1a"}});

// ── Slide 5 : Synthèse ────────────────────────────────
let s5 = prs.addSlide();
s5.background = {{color: GRAY}};
s5.addShape(prs.ShapeType.rect, {{x:0,y:0,w:10,h:0.9,fill:{{color:NAV}}}});
s5.addText("Synthèse de Tarification", {{x:0.4,y:0,w:9,h:0.9,fontSize:22,bold:true,color:WHITE,valign:"middle"}});
s5.addShape(prs.ShapeType.rect, {{x:0,y:0.85,w:10,h:0.06,fill:{{color:TEAL}}}});
if(rapport.length > 0) {{
  const rptRows = [["Tranche","BC","Simulation","Marché","Retenu","Prime (MAD)"].map(h=>{{text:h,options:{{bold:true,color:WHITE,fill:{{color:NAV}}}}}})]
    .concat(rapport.map(r=>[r.t,r.bc,r.sim,r.mkt,r.ret,r.prime].map(v=>{{return{{text:v}}}})));
  s5.addTable(rptRows, {{x:0.4,y:1.4,w:9.2,colW:[2.0,1.4,1.4,1.4,1.4,1.6],border:{{pt:0.5,color:"d0e8e2"}},rowH:0.45,fontSize:12,fontFace:"Calibri",color:"1a1a1a"}});
}}

// ── Slide 6 : Conclusion ──────────────────────────────
let s6 = prs.addSlide();
s6.background = {{color: NAV}};
s6.addShape(prs.ShapeType.rect, {{x:0,y:0,w:10,h:0.06,fill:{{color:TEAL}}}});
s6.addText("Conclusion & Recommandations", {{x:0.5,y:0.5,w:9,h:1,fontSize:30,bold:true,color:WHITE,fontFace:"Georgia"}});
s6.addText([
  {{text:"Prime totale\\n",   options:{{bold:true,fontSize:14,color:TEAL}}}},
  {{text:"{prime_totale:,.0f} MAD\\n\\n", options:{{fontSize:22,bold:true,color:WHITE}}}},
  {{text:"Taux global\\n",    options:{{bold:true,fontSize:14,color:TEAL}}}},
  {{text:"{taux_global:.4%}\\n\\n",       options:{{fontSize:22,bold:true,color:WHITE}}}},
  {{text:"Généré par Atlantic Re IA · {datetime.now().strftime('%d/%m/%Y %H:%M')}",
     options:{{fontSize:10,color:"9ab5c5",italic:true}}}}
], {{x:0.8,y:1.8,w:4.5,h:3.5,valign:"top"}});
s6.addText("Sélection : max(BC, Sim) travaillante\\nmax(Sim, Marché) cat / non-travaillante\\n\\nBC = méthode de référence\\nSimulation = validation & prudence\\nMarket curve = benchmark externe cat", {{x:5.5,y:2.0,w:4.0,h:3.0,fontSize:13,color:"c8dce6",fontFace:"Calibri",valign:"top"}});

await prs.writeFile({{fileName:"/tmp/atlantic_re_rapport_{annee}.pptx"}});
console.log("OK");
"""

    # Écrire et exécuter le script Node.js
    tmp_dir = tempfile.mkdtemp()
    script_path = os.path.join(tmp_dir, "make_pptx.mjs")
    with open(script_path, "w", encoding="utf-8") as f:
        f.write(script)

    try:
        result = subprocess.run(
            ["node", script_path],
            capture_output=True, text=True, timeout=30,
            env={**os.environ, "NODE_PATH": "/home/claude/.npm-global/lib/node_modules"}
        )
        pptx_path = f"/tmp/atlantic_re_rapport_{annee}.pptx"
        if os.path.exists(pptx_path):
            with open(pptx_path, "rb") as f:
                return f.read()
        return None
    except Exception:
        return None
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


def identifier_sinistres_majeurs_gpd(df_proj, gnpi, tranches_input,
                                      nb_annees_obs=10, retour_ans=20,
                                      u=None, pct_seuil=0.80):
    """
    Identification des sinistres majeurs par TVE — fit GPD (scipy).
    Traduction exacte du code R evir::gpd.
    Chargement calculé par tranche : chargement = sum((1/T) * min(max(X-D,0),C) / GNPI)

    Paramètres
    ----------
    u            : seuil TVE (si None → p80 × priorité travaillante)
    pct_seuil    : percentile pour calcul automatique du seuil
    retour_ans   : période de retour pour Pm
    nb_annees_obs: nombre d'années d'observation
    """
    from scipy import stats

    charges = df_proj['Sprime_ultime'].values
    charges = charges[charges > 0]
    n_total = len(charges)

    # ── Seuil TVE ──
    if u is None:
        D_trav = next((t['priorite'] for t in tranches_input if t['type'] == 'travaillante'),
                      charges[charges > 0].mean())
        u = pct_seuil * D_trav

    # ── Excédances au-dessus du seuil ──
    excesses = charges[charges >= u] - u
    n_excesses = len(excesses)

    if n_excesses < 5:
        # Fallback si trop peu de données : Pm = p99.5
        Pm = float(np.percentile(charges, 99.5))
        xi = 0.0; sigma_gpd = float(np.std(excesses)) if n_excesses > 0 else 1.0
        survie = n_excesses / max(n_total, 1)
        freq_annuelle = n_total / nb_annees_obs
        m = retour_ans * freq_annuelle
        fit_ok = False
    else:
        # ── Fit GPD (xi=forme, loc=0 fixé, sigma=échelle) ──
        xi, loc_gpd, sigma_gpd = stats.genpareto.fit(excesses, floc=0)
        survie       = n_excesses / n_total
        freq_annuelle = n_total / nb_annees_obs
        m             = retour_ans * freq_annuelle

        # ── Niveau de retour Pm (formule R evir) ──
        ms = m * survie
        if abs(xi) > 1e-10:
            Pm = u + (sigma_gpd / xi) * (ms**xi - 1)
        else:
            Pm = u + sigma_gpd * np.log(ms)
        fit_ok = True

    Pm = max(Pm, float(np.percentile(charges, 95)))  # garde-fou minimal

    # ── Séparation majeurs / courants ──
    mask_maj    = df_proj['Sprime_ultime'] >= Pm
    df_majeurs  = df_proj[mask_maj].copy()
    df_courants = df_proj[~mask_maj].copy()

    # ── Chargements par tranche (formule R) ──
    # chargement_tranche = sum((1/T) * min(max(X-D,0),C)) / GNPI
    chargements_par_tranche = {}
    for t in tranches_input:
        D = t['priorite']; C = t['portee']
        if len(df_majeurs) > 0:
            X_maj = df_majeurs['Sprime_ultime'].values
            charges_nettes = np.minimum(np.maximum(X_maj - D, 0), C)
            chargement_t   = float(np.sum((1.0 / retour_ans) * charges_nettes) / gnpi)
        else:
            charges_nettes = np.array([])
            chargement_t   = 0.0
        chargements_par_tranche[t['nom']] = {
            'chargement': round(chargement_t, 8),
            'type':        t['type'],
            'D':           D, 'C': C,
            'charges_nettes': charges_nettes.tolist(),
        }

    # ── Tableau détaillé sinistres majeurs ──
    rows_charg = []
    for _, row in df_majeurs.iterrows():
        x = row['Sprime_ultime']
        row_d = {"Annee": row.get('annee_surv', '—'), "Montant_stab": round(x),
                 "p_j": round(1.0/retour_ans, 4)}
        for t in tranches_input:
            D = t['priorite']; C = t['portee']
            cn  = float(min(max(x - D, 0), C))
            chg = (1.0/retour_ans) * cn / gnpi
            row_d[f"Ck {t['nom'][:8]}"]   = round(cn, 0)
            row_d[f"Charg {t['nom'][:8]}"] = round(chg, 6)
        rows_charg.append(row_d)
    df_chargements = pd.DataFrame(rows_charg)

    # Chargement de référence = tranche travaillante (compat. code existant)
    chargement_ref = next(
        (v['chargement'] for k,v in chargements_par_tranche.items() if v['type']=='travaillante'),
        sum(v['chargement'] for v in chargements_par_tranche.values()))

    # ── Diagnostics GPD ──
    gpd_diag = {
        "u": round(float(u), 0),
        "xi": round(float(xi), 4),
        "sigma_gpd": round(float(sigma_gpd), 2),
        "survie_P_X_gt_u": round(float(survie), 6),
        "n_excesses": int(n_excesses),
        "freq_annuelle": round(float(freq_annuelle), 4),
        "m": round(float(m), 2),
        "Pm": round(float(Pm), 0),
        "fit_ok": fit_ok,
        "excesses": excesses.tolist() if fit_ok else [],
    }

    return {
        "df_majeurs":              df_majeurs,
        "df_courants":             df_courants,
        "Pm":                      float(Pm),
        "chargement":              chargement_ref,
        "chargements_par_tranche": chargements_par_tranche,
        "df_chargements":          df_chargements,
        "alpha":                   float(-1/xi) if abs(xi) > 1e-4 else 1.5,
        "n_majeurs":               int(len(df_majeurs)),
        "n_courants":              int(len(df_courants)),
        "gpd_diag":                gpd_diag,
    }


# Alias pour compat. code existant
def identifier_sinistres_majeurs(df_proj, gnpi, D, C_tranche,
                                  nb_annees_obs=10, retour_ans=20, percentile_seuil=99.5):
    """Wrapper de compatibilité — appelle la version GPD complète."""
    tranches_compat = [{"nom": "Tranche", "type": "travaillante",
                         "priorite": D, "portee": C_tranche}]
    return identifier_sinistres_majeurs_gpd(
        df_proj, gnpi, tranches_compat,
        nb_annees_obs=nb_annees_obs, retour_ans=retour_ans,
        pct_seuil=0.995)





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

        # KS test correct : utiliser les excédances (exc - u) vs Pareto(alpha, scale=u)
        # scipy.stats.pareto : F(x) = 1 - (b/x)^alpha pour x >= b
        # Pour excédances y = exc - u ~ Pareto(alpha, scale=u) décalée :
        # on utilise la formule analytique sur exc directement
        exc_sorted = np.sort(exc)
        empirical  = np.arange(1, n_exc + 1) / n_exc
        theoretical = 1 - (u / exc_sorted) ** alpha_h
        ks_s = float(np.max(np.abs(empirical - theoretical)))
        # p-value via distribution de Kolmogorov (approximation asymptotique)
        # Note : paramètres estimés → p-value légèrement optimiste (comme en R)
        ks_lambda = (np.sqrt(n_exc) + 0.12 + 0.11 / np.sqrt(n_exc)) * ks_s
        from scipy.special import kolmogorov as _kolmogorov
        pval_ks = float(_kolmogorov(ks_lambda))
        pval_ks = min(max(pval_ks, 0.0), 1.0)

        try:
            cdf_v = np.sort(1-(np.sort(exc)/u)**(-alpha_h))
            nn = len(cdf_v); i_a = np.arange(1, nn+1)
            ad_stat = -nn - np.mean((2*i_a-1)*(np.log(np.clip(cdf_v,1e-10,1-1e-10))+
                                               np.log(np.clip(1-cdf_v[::-1],1e-10,1-1e-10))))
        except: ad_stat = np.nan
        qual = "Bon" if pval_ks>0.05 and not np.isnan(ad_stat) and ad_stat<2.5 else \
               "Acceptable" if pval_ks>0.01 else "Rejeté"
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
        import matplotlib.ticker as mticker
        sorted_desc = np.sort(all_sev)[::-1]
        n_sd = len(sorted_desc)
        k_max_sd = min(n_sd - 2, 200)
        ks_sd = np.arange(1, k_max_sd + 1)

        # Hill estimates + IC 95%
        hills_sd = np.array([
            k / np.sum(np.log(sorted_desc[:k] / sorted_desc[k]))
            if sorted_desc[k] > 0 and np.sum(np.log(sorted_desc[:k] / sorted_desc[k])) > 0
            else np.nan for k in ks_sd
        ])
        with np.errstate(invalid='ignore'):
            ci_up_sd  = hills_sd + 1.96 * hills_sd / np.sqrt(ks_sd)
            ci_low_sd = np.maximum(hills_sd - 1.96 * hills_sd / np.sqrt(ks_sd), 0)
        ok_sd = ~np.isnan(hills_sd)

        # Gertensgarbe — U progressif / régressif (Mann-Kendall normalisé)
        h_ok_sd = hills_sd[ok_sd]; k_ok_sd = ks_sd[ok_sd]; nk_sd = len(h_ok_sd)
        u_fwd_sd = np.zeros(nk_sd)
        for i in range(2, nk_sd):
            s = sum(1 for j in range(i) if h_ok_sd[j] < h_ok_sd[i])
            e_s = i*(i-1)/4; v_s = i*(i-1)*(2*i+5)/72
            u_fwd_sd[i] = (s - e_s) / np.sqrt(max(v_s, 1e-10))
        h_rev_sd = h_ok_sd[::-1]
        u_bwd_rev_sd = np.zeros(nk_sd)
        for i in range(2, nk_sd):
            s = sum(1 for j in range(i) if h_rev_sd[j] < h_rev_sd[i])
            e_s = i*(i-1)/4; v_s = i*(i-1)*(2*i+5)/72
            u_bwd_rev_sd[i] = (s - e_s) / np.sqrt(max(v_s, 1e-10))
        u_bwd_sd = u_bwd_rev_sd[::-1]
        cross_sd = np.where(np.diff(np.sign(u_fwd_sd - u_bwd_sd)))[0]
        k_gert = int(k_ok_sd[cross_sd[0]]) if len(cross_sd) > 0 else int(k_ok_sd[nk_sd // 2])
        alpha_gert = float(hills_sd[min(k_gert-1, len(hills_sd)-1)])
        u_gert = float(sorted_desc[min(k_gert-1, n_sd-1)])

        # MEF — cercles ouverts, style meplot R
        u_sorted_sd = np.sort(np.unique(all_sev))
        step_sd = max(1, len(u_sorted_sd) // 80)
        u_mef_sd = u_sorted_sd[::step_sd][:-1]
        mef_sd = np.array([
            float(np.mean(all_sev[all_sev > u] - u)) if np.sum(all_sev > u) >= 2 else np.nan
            for u in u_mef_sd
        ])
        valid_mef_sd = ~np.isnan(mef_sd)

        # ── Figure 1×3 identique à sinistres majeurs ─────────────────────
        fig_sd, axes_sd = plt.subplots(1, 3, figsize=(16, 5))
        for ax in axes_sd:
            ax.set_facecolor("white")
            ax.spines[["top", "right"]].set_visible(False)
        fig_sd.patch.set_facecolor("white")

        # (1) Hill plot
        ax_sd1 = axes_sd[0]
        ax_sd1.plot(k_ok_sd, h_ok_sd, color="black", lw=1.2)
        ax_sd1.fill_between(ks_sd[ok_sd], ci_low_sd[ok_sd], ci_up_sd[ok_sd],
                            color="steelblue", alpha=0.25, label="IC 95 %")
        ax_sd1.axvline(k_gert, color="red", ls="--", lw=2,
                       label=f"k* = {k_gert}")
        ax_sd1.set_xlabel("Order Statistics")
        ax_sd1.set_ylabel("Tail Index α(k)")
        ax_sd1.set_title("Hill Plot")
        ax_sd1.legend(fontsize=8)
        ax_sd1.grid(alpha=0.2, linestyle="--")

        # (2) MEF — cercles ouverts
        ax_sd2 = axes_sd[1]
        ax_sd2.scatter(u_mef_sd[valid_mef_sd], mef_sd[valid_mef_sd],
                       s=30, facecolors="none", edgecolors="black", linewidths=0.8)
        ax_sd2.axvline(seuil_0, color="red", ls="--", lw=2,
                       label=f"s = {seuil_0:,.0f}")
        ax_sd2.set_xlabel("Threshold")
        ax_sd2.set_ylabel("Mean Excess")
        ax_sd2.set_title("Mean Excess Function")
        ax_sd2.xaxis.set_major_formatter(mticker.ScalarFormatter(useMathText=True))
        ax_sd2.yaxis.set_major_formatter(mticker.ScalarFormatter(useMathText=True))
        ax_sd2.ticklabel_format(axis="both", style="sci", scilimits=(0, 0))
        ax_sd2.legend(fontsize=8)
        ax_sd2.grid(alpha=0.2, linestyle="--")

        # (3) Gertensgarbe — U progressif / régressif
        ax_sd3 = axes_sd[2]
        ax_sd3.plot(k_ok_sd, u_fwd_sd, color="black", lw=1.5, label="U progressif")
        ax_sd3.plot(k_ok_sd, u_bwd_sd, color="black", lw=1.5, ls="--", label="U régressif")
        ax_sd3.axhline(0, color="black", lw=0.6, alpha=0.4)
        ax_sd3.axvline(k_gert, color="red", ls="--", lw=2,
                       label=f"k* = {k_gert}  (u ≈ {u_gert:,.0f})")
        ax_sd3.set_xlabel("Order Statistics")
        ax_sd3.set_ylabel("Statistique U(k)")
        ax_sd3.set_title("Gertensgarbe-Werner")
        ax_sd3.legend(fontsize=8)
        ax_sd3.grid(alpha=0.2, linestyle="--")

        plt.tight_layout()
        st.pyplot(fig_sd, use_container_width=True); plt.close(fig_sd)

        st.info(
            f"Gertensgarbe → k* = {k_gert}  |  u suggéré = {u_gert:,.0f} MAD  |  "
            f"α = {alpha_gert:.4f}  |  "
            "Cherchez la zone stable du Hill et la linéarité du MEF pour confirmer u."
        )

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



# ════════════════════════════════════════════════════════════════════════════
# SÉLECTION AUTOMATIQUE DU SEUIL TVE (Hill + MEF + Gertensgarbe)
# ════════════════════════════════════════════════════════════════════════════



def detecter_seuil_optimal_tve(data, label="Sinistres"):
    """
    Détecte le seuil TVE via Hill (IC 95%), MEF (style meplot R), Gertensgarbe (U progressif/régressif).
    Même style graphique que la section identification sinistres majeurs.
    Retourne : seuil_consensus, fig, dict diagnostics.
    """
    import matplotlib.pyplot as plt
    import matplotlib.ticker as mticker
    from scipy import stats as _sp

    data_pos = np.array([x for x in data if x > 0 and np.isfinite(x)])
    if len(data_pos) < 20:
        return None, None, {"erreur": "Moins de 20 observations positives"}

    sorted_desc = np.sort(data_pos)[::-1]
    n = len(sorted_desc)
    k_max = min(n - 2, 150)
    ks = np.arange(1, k_max + 1)

    # ── Hill estimates + IC 95% ────────────────────────────────────────────
    hills = np.array([
        k / np.sum(np.log(sorted_desc[:k] / sorted_desc[k]))
        if sorted_desc[k] > 0 and np.sum(np.log(sorted_desc[:k] / sorted_desc[k])) > 0
        else np.nan
        for k in ks
    ])
    with np.errstate(invalid='ignore'):
        ci_up  = hills + 1.96 * hills / np.sqrt(ks)
        ci_low = np.maximum(hills - 1.96 * hills / np.sqrt(ks), 0)

    # ── Hill stabilité (CV glissant) ──────────────────────────────────────
    ok = ~np.isnan(hills)
    h_ok = hills[ok]; k_ok = ks[ok]
    win = 15
    cv_arr = np.array([
        np.std(h_ok[max(0,i-win//2):i+win//2+1]) /
        (np.abs(np.mean(h_ok[max(0,i-win//2):i+win//2+1])) + 1e-10)
        for i in range(len(h_ok))
    ])
    k_hill_best  = int(k_ok[np.argmin(cv_arr)])
    seuil_hill   = float(sorted_desc[min(k_hill_best, n-1)])
    alpha_hill   = float(h_ok[np.argmin(cv_arr)])

    # ── Gertensgarbe — U progressif / régressif (Mann-Kendall normalisé) ──
    nk = len(h_ok)
    u_fwd = np.zeros(nk)
    for i in range(2, nk):
        s = sum(1 for j in range(i) if h_ok[j] < h_ok[i])
        e_s = i * (i - 1) / 4
        v_s = i * (i - 1) * (2 * i + 5) / 72
        u_fwd[i] = (s - e_s) / np.sqrt(max(v_s, 1e-10))

    h_rev = h_ok[::-1]
    u_bwd_rev = np.zeros(nk)
    for i in range(2, nk):
        s = sum(1 for j in range(i) if h_rev[j] < h_rev[i])
        e_s = i * (i - 1) / 4
        v_s = i * (i - 1) * (2 * i + 5) / 72
        u_bwd_rev[i] = (s - e_s) / np.sqrt(max(v_s, 1e-10))
    u_bwd = u_bwd_rev[::-1]

    diff_gb   = u_fwd - u_bwd
    cross_idx = np.where(np.diff(np.sign(diff_gb)))[0]
    k_gert    = int(k_ok[cross_idx[0]]) if len(cross_idx) > 0 else int(k_ok[nk // 2])
    seuil_gert  = float(sorted_desc[min(k_gert - 1, n-1)])
    alpha_gert  = float(hills[min(k_gert - 1, len(hills)-1)]) if not np.isnan(hills[min(k_gert-1,len(hills)-1)]) else alpha_hill

    # ── MEF — cercles ouverts, style meplot R ─────────────────────────────
    u_sorted = np.sort(np.unique(data_pos))
    step  = max(1, len(u_sorted) // 80)
    u_mef_pts = u_sorted[::step][:-1]
    mef_vals  = np.array([
        float(np.mean(data_pos[data_pos > u] - u))
        if np.sum(data_pos > u) >= 3 else np.nan
        for u in u_mef_pts
    ])
    valid_mef = ~np.isnan(mef_vals)

    # MEF — linéarité R² maximal
    seuil_mef = float(np.percentile(data_pos, 75))
    best_r2   = 0.0
    u_v = u_mef_pts[valid_mef]; e_v = mef_vals[valid_mef]
    if len(u_v) >= 6:
        from scipy.stats import linregress
        for i in range(3, len(u_v) - 2):
            slope, _, r, _, _ = linregress(u_v[i:], e_v[i:])
            if r ** 2 > best_r2 and slope > -0.1:
                best_r2   = r ** 2
                seuil_mef = float(u_v[i])

    seuil_consensus = float(np.median([seuil_hill, seuil_mef, seuil_gert]))

    # ── Graphiques — style identique à sinistres majeurs ──────────────────
    fig, axes = plt.subplots(1, 3, figsize=(16, 5))
    for ax in axes:
        ax.set_facecolor("white")
        ax.spines[["top", "right"]].set_visible(False)
    fig.patch.set_facecolor("white")

    # (1) Hill plot avec IC 95%
    ax1 = axes[0]
    ax1.plot(k_ok, h_ok, color="black", lw=1.2)
    ax1.fill_between(ks[ok], ci_low[ok], ci_up[ok],
                     color="steelblue", alpha=0.25, label="IC 95 %")
    ax1.axvline(k_gert, color="red", ls="--", lw=2,
                label=f"Gertensgarbe k={k_gert}")
    ax1.axvline(k_hill_best, color="orange", ls=":", lw=2,
                label=f"Stabilité CV k={k_hill_best}")
    ax1.set_xlabel("Order Statistics")
    ax1.set_ylabel("Tail Index α(k)")
    ax1.set_title("Hill Plot")
    ax1.legend(fontsize=8)
    ax1.grid(alpha=0.2, linestyle="--")

    # (2) MEF — cercles ouverts style meplot R
    ax2 = axes[1]
    ax2.scatter(u_mef_pts[valid_mef], mef_vals[valid_mef],
                s=30, facecolors="none", edgecolors="black", linewidths=0.8)
    ax2.axvline(seuil_mef, color="red", ls="--", lw=2,
                label=f"Linéarité = {seuil_mef:,.0f}")
    ax2.axvline(seuil_consensus, color="orange", ls=":", lw=1.5,
                label=f"Consensus = {seuil_consensus:,.0f}")
    ax2.set_xlabel("Threshold")
    ax2.set_ylabel("Mean Excess")
    ax2.set_title("Mean Excess Function")
    ax2.xaxis.set_major_formatter(mticker.ScalarFormatter(useMathText=True))
    ax2.yaxis.set_major_formatter(mticker.ScalarFormatter(useMathText=True))
    ax2.ticklabel_format(axis="both", style="sci", scilimits=(0, 0))
    ax2.legend(fontsize=8)
    ax2.grid(alpha=0.2, linestyle="--")

    # (3) Gertensgarbe — U progressif / régressif
    ax3 = axes[2]
    ax3.plot(k_ok, u_fwd, color="black", lw=1.5, label="U progressif")
    ax3.plot(k_ok, u_bwd, color="black", lw=1.5, ls="--", label="U régressif")
    ax3.axhline(0, color="black", lw=0.6, alpha=0.4)
    ax3.axvline(k_gert, color="red", ls="--", lw=2,
                label=f"k* = {k_gert}  (u ≈ {seuil_gert:,.0f})")
    ax3.set_xlabel("Order Statistics")
    ax3.set_ylabel("Statistique U(k)")
    ax3.set_title("Gertensgarbe-Werner")
    ax3.legend(fontsize=8)
    ax3.grid(alpha=0.2, linestyle="--")

    plt.tight_layout()

    diag = {
        "seuil_hill":    round(seuil_hill),
        "seuil_mef":     round(seuil_mef),
        "seuil_gert":    round(seuil_gert),
        "seuil_optimal": round(seuil_consensus),
        "k_hill":        k_hill_best,
        "k_gert":        k_gert,
        "alpha_hill":    round(alpha_hill, 4),
        "alpha_gert":    round(alpha_gert, 4),
        "mef_r2":        round(best_r2, 3),
        "n_obs":         n,
        # Pour le slider interactif
        "data_min":      round(float(np.percentile(data_pos, 50))),
        "data_max":      round(float(np.percentile(data_pos, 99))),
    }
    return seuil_consensus, fig, diag

def comparer_lois_ajustement(data, seuil, label="Sinistres"):
    """
    Ajuste Pareto, Lognormale et GPD aux excédances au-dessus du seuil.
    Retourne un DataFrame d'indicateurs (KS, AD, AIC, BIC, α/μ/σ) pour chaque loi.

    La loi avec le plus petit AIC est recommandée.
    """
    import numpy as np
    from scipy import stats
    from scipy.special import kolmogorov

    exceedances = data[data > seuil] - seuil
    exceedances = exceedances[exceedances > 0]
    n = len(exceedances)

    if n < 10:
        return None, "Moins de 10 excédances au-dessus du seuil"

    resultats = []

    # ── Pareto (GPD avec ξ > 0) ──────────────────────────────────────────
    try:
        # Estimation MLE Pareto : α = n / Σ log(1 + x/seuil)
        log_sum = np.sum(np.log(1 + exceedances / seuil)) if seuil > 0 else np.sum(np.log(exceedances))
        alpha_p = n / log_sum if log_sum > 0 else 1.5
        sigma_p = seuil / alpha_p if alpha_p > 0 else seuil

        # CDF Pareto : F(x) = 1 - (1 + x/sigma)^(-alpha)
        cdf_pareto = lambda x: 1 - (1 + x / max(sigma_p, 1e-10)) ** (-alpha_p)
        observed_sorted = np.sort(exceedances)
        theoretical_cdf = cdf_pareto(observed_sorted)
        empirical_cdf   = np.arange(1, n+1) / n

        ks_stat = np.max(np.abs(empirical_cdf - theoretical_cdf))
        ks_pval = float(stats.kstest(exceedances, lambda x: cdf_pareto(x)).pvalue)

        # Log-vraisemblance Pareto
        ll_p = n * np.log(alpha_p / max(sigma_p, 1e-10)) - (alpha_p + 1) * np.sum(np.log(1 + exceedances / max(sigma_p, 1e-10)))
        aic_p = -2 * ll_p + 2 * 2  # 2 paramètres
        bic_p = -2 * ll_p + np.log(n) * 2

        resultats.append({
            "Loi": "Pareto", "Params": f"α={alpha_p:.4f}, σ={sigma_p:,.0f}",
            "KS stat": round(ks_stat, 4), "p-value KS": round(ks_pval, 4),
            "AIC": round(aic_p, 2), "BIC": round(bic_p, 2),
            "α (Pareto)": round(alpha_p, 4), "Recommandée": "",
            "_ll": ll_p, "_aic": aic_p,
        })
    except Exception as e:
        resultats.append({"Loi": "Pareto", "Erreur": str(e)[:50],
                          "_aic": 1e10, "_ll": -1e10})

    # ── Lognormale ──────────────────────────────────────────────────────
    try:
        log_exc  = np.log(exceedances + 1e-10)
        mu_ln    = np.mean(log_exc)
        sigma_ln = np.std(log_exc, ddof=1)

        ks_res   = stats.kstest(exceedances, 'lognorm', args=(sigma_ln, 0, np.exp(mu_ln)))
        ll_ln    = np.sum(stats.lognorm.logpdf(exceedances, sigma_ln, 0, np.exp(mu_ln)))
        aic_ln   = -2 * ll_ln + 2 * 2
        bic_ln   = -2 * ll_ln + np.log(n) * 2

        resultats.append({
            "Loi": "Lognormale", "Params": f"μ={mu_ln:.4f}, σ={sigma_ln:.4f}",
            "KS stat": round(ks_res.statistic, 4), "p-value KS": round(ks_res.pvalue, 4),
            "AIC": round(aic_ln, 2), "BIC": round(bic_ln, 2),
            "α (Pareto)": "—", "Recommandée": "",
            "_ll": ll_ln, "_aic": aic_ln,
        })
    except Exception as e:
        resultats.append({"Loi": "Lognormale", "Erreur": str(e)[:50],
                          "_aic": 1e10, "_ll": -1e10})

    # ── GPD (Pickands-Balkema-de Haan) ──────────────────────────────────
    try:
        # Estimation MLE GPD
        from scipy.optimize import minimize

        def neg_ll_gpd(params):
            xi, beta = params
            if beta <= 0: return 1e10
            if xi >= 0:
                return -np.sum(stats.genpareto.logpdf(exceedances, xi, 0, beta))
            elif xi < 0:
                if np.any(exceedances > -beta/xi): return 1e10
                return -np.sum(stats.genpareto.logpdf(exceedances, xi, 0, beta))

        res = minimize(neg_ll_gpd, [0.3, np.mean(exceedances)],
                      method='Nelder-Mead', options={'maxiter': 2000, 'xatol': 1e-6})
        xi_gpd, beta_gpd = res.x

        ks_res_gpd = stats.kstest(exceedances, 'genpareto',
                                  args=(xi_gpd, 0, beta_gpd))
        ll_gpd   = -res.fun
        aic_gpd  = -2 * ll_gpd + 2 * 2
        bic_gpd  = -2 * ll_gpd + np.log(n) * 2

        resultats.append({
            "Loi": "GPD", "Params": f"ξ={xi_gpd:.4f}, β={beta_gpd:,.0f}",
            "KS stat": round(ks_res_gpd.statistic, 4), "p-value KS": round(ks_res_gpd.pvalue, 4),
            "AIC": round(aic_gpd, 2), "BIC": round(bic_gpd, 2),
            "α (Pareto)": f"1/ξ={1/xi_gpd:.3f}" if xi_gpd != 0 else "∞",
            "Recommandée": "",
            "_ll": ll_gpd, "_aic": aic_gpd,
            "_xi": xi_gpd, "_beta": beta_gpd,
        })
    except Exception as e:
        resultats.append({"Loi": "GPD", "Erreur": str(e)[:50],
                          "_aic": 1e10, "_ll": -1e10})

    # ── Recommandation : AIC minimal ──────────────────────────────────────
    valid = [r for r in resultats if "_aic" in r and r["_aic"] < 1e9]
    if valid:
        best = min(valid, key=lambda r: r["_aic"])
        best["Recommandée"] = "✅ AIC min"

    # Nettoyer les clés internes avant affichage
    for r in resultats:
        for k in ["_ll", "_aic", "_xi", "_beta"]:
            r.pop(k, None)

    return resultats, None


def afficher_selection_loi(data, seuil, key_prefix="loi"):
    """
    Affiche le comparateur de lois et retourne la loi choisie par l'utilisateur.
    Appelé depuis Tab 4 (Simulation) avant de lancer la simulation.
    """
    st.markdown("#### 📊 Sélection de la loi de sévérité")
    st.caption("Ajustement Pareto / Lognormale / GPD aux excédances. "
               "Choisissez la loi en fonction des indicateurs ci-dessous.")

    with st.spinner("Ajustement des lois..."):
        resultats_lois, err = comparer_lois_ajustement(data, seuil, "Excédances")

    if err or not resultats_lois:
        st.warning(err or "Pas assez de données")
        return "pareto"

    # Affichage tableau
    import streamlit as st
    cols_aff = ["Loi","Params","KS stat","p-value KS","AIC","BIC","Recommandée"]
    rows_aff = [{k: r.get(k,"") for k in cols_aff} for r in resultats_lois]

    # Colorier la ligne recommandée
    df_lois = __import__('pandas').DataFrame(rows_aff)
    st.dataframe(df_lois, use_container_width=True, hide_index=True)

    st.markdown("""
    <div style="background:#f2f8f7;border-left:4px solid #00b5a5;padding:10px 14px;font-size:12px">
    <b>Guide de lecture :</b><br>
    • <b>KS p-value</b> : > 0.05 = bonne adéquation | < 0.05 = loi rejetée<br>
    • <b>AIC</b> : plus petit = meilleur ajustement (pénalise la complexité)<br>
    • <b>BIC</b> : idem AIC, pénalité plus forte sur n<br>
    • <b>ξ GPD</b> : > 0 = queue lourde (Fréchet) | ξ ≈ 0 = Gumbel (légère) | ξ < 0 = Weibull (bornée)
    </div>""", unsafe_allow_html=True)

    loi_choisie = st.selectbox(
        "🔬 Loi retenue pour la simulation",
        options=["pareto", "lognormale", "gpd"],
        format_func={"pareto":"Pareto (Extrapolation classique XL)",
                     "lognormale":"Lognormale (Sinistres moyens)",
                     "gpd":"GPD (Extreme Value Theory — TVE)"}.get,
        key=f"{key_prefix}_loi_choisie",
        help="La loi avec ✅ AIC min est statistiquement recommandée, "
             "mais vous pouvez choisir selon le contexte actuariel."
    )

    st.info(f"✅ Loi retenue : **{loi_choisie.upper()}** — les simulations utiliseront cette loi.")
    return loi_choisie
