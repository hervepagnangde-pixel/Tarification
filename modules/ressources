"""
Atlantic Re IA — Resources module
Ressources actuarielles web, scripts R, intégration R Studio.
"""
import streamlit as st
import numpy as np
from modules.ui import tableau_resultats, card

def afficher_ressources_actuarielles():
    """Panneau de ressources actuarielles web pour l'agent."""
    st.markdown("---")
    st.markdown("#### 🌐 Ressources actuarielles — Sites de référence")
    tabs_res = st.tabs(list(RESSOURCES_ACTUARIELLES.keys()))
    for tab, (categorie, ressources) in zip(tabs_res, RESSOURCES_ACTUARIELLES.items()):
        with tab:
            cols = st.columns(2)
            for i, r in enumerate(ressources):
                with cols[i % 2]:
                    st.markdown(f"""
                    <a href="{r['url']}" target="_blank" style="text-decoration:none">
                    <div style="background:white;border-left:3px solid #00b5a5;
                        padding:12px 16px;margin-bottom:8px;cursor:pointer;
                        box-shadow:0 2px 8px rgba(0,0,0,0.06);transition:all 0.2s"
                        onmouseover="this.style.borderLeftColor='#0d2b3e';this.style.boxShadow='0 4px 16px rgba(0,181,165,0.2)'"
                        onmouseout="this.style.borderLeftColor='#00b5a5';this.style.boxShadow='0 2px 8px rgba(0,0,0,0.06)'">
                      <div style="font-size:13px;font-weight:700;color:#0d2b3e">{r['nom']}</div>
                      <div style="font-size:11px;color:#5a7a8a;margin-top:3px">{r['desc']}</div>
                      <div style="font-size:10px;color:#00b5a5;margin-top:4px">{r['url'][:50]}...</div>
                    </div></a>""", unsafe_allow_html=True)


# ════════════════════════════════════════════
# INTÉGRATION R — Exécution de scripts R
# ════════════════════════════════════════════

SCRIPTS_R_TARIFICATION = {
    "Hill Plot & Seuil Pareto": """
# ─── Hill plot et sélection de seuil (style evir) ───────────────────
library(evir)
# X = vecteur des montants sinistres
X <- sort(X, decreasing=TRUE)
# Hill estimates
hill_est <- function(X, k_max=NULL) {
  n <- length(X)
  if (is.null(k_max)) k_max <- min(n-1, 200)
  hills <- numeric(k_max); ks <- 1:k_max
  for (k in ks) hills[k] <- k / sum(log(X[1:k]/X[k+1]))
  list(k=ks, alpha=hills)
}
h <- hill_est(X)
plot(h$k, h$alpha, type="l", main="Hill Plot", xlab="k", ylab="alpha(k)")
# Gertensgarbe — Mann-Kendall progressif/régressif
abline(v=which.min(abs(diff(h$alpha))), col="red", lty=2)
""",
    "Fit GPD (evir)": """
# ─── Fit GPD sur excédances (paquet evir, identique à l'outil) ───────
library(evir)
u <- quantile(X, 0.80)           # seuil (à ajuster via Hill+MEF)
excesses <- X[X >= u] - u
fit_gpd <- gpd(X, threshold=u)   # xi=forme, beta=échelle
print(fit_gpd$par.ests)          # xi, sigma
# Niveau de retour T ans
T <- 20
n_obs <- length(X); n_exc <- sum(X >= u)
surv <- n_exc / n_obs
freq_an <- n_obs / nb_annees
m <- T * freq_an
if (abs(fit_gpd$par.ests["xi"]) > 1e-10) {
  Pm <- u + (fit_gpd$par.ests["sigma"] / fit_gpd$par.ests["xi"]) *
        ((m * surv)^fit_gpd$par.ests["xi"] - 1)
} else {
  Pm <- u + fit_gpd$par.ests["sigma"] * log(m * surv)
}
cat("Pm (retour", T, "ans) =", Pm, "\\n")
""",
    "Simulation XL (Pareto/Poisson)": """
# ─── Simulation Pareto-Poisson pour tarification XL ─────────────────
sim_xl <- function(alpha, lambda, seuil, D, L, n_rec=1, n_sim=10000, gnpi=183e6) {
  charges <- numeric(n_sim)
  cap <- (n_rec + 1) * L
  set.seed(42)
  for (i in seq_len(n_sim)) {
    N <- rpois(1, lambda)
    if (N == 0) { charges[i] <- 0; next }
    U <- runif(N)
    Sp <- seuil * (U ^ (-1/alpha))   # Pareto par inversion
    S <- sum(pmin(pmax(Sp - D, 0), L))
    charges[i] <- min(S, cap)
  }
  tau_pur <- mean(charges) / gnpi
  sigma   <- sd(charges) / gnpi
  tau_risque <- tau_pur + 0.20 * sigma
  list(tau_pur=tau_pur, sigma=sigma, tau_risque=tau_risque,
       tau_tech=tau_risque/(1-0.10-0.05-0.10))
}
res <- sim_xl(alpha=1.45, lambda=3.2, seuil=1.6e6, D=2e6, L=13e6)
cat("τ_pur:", res$tau_pur, "\\nτ_tech:", res$tau_tech, "\\n")
""",
    "Burning Cost As-If": """
# ─── Burning Cost As-If + Stabilisation sur incréments ───────────────
# df = data.frame(sinistre_id, annee_surv, annee_reg, total)
# Indices d'inflation
get_indice <- function(annee, df_indices) {
  approx(df_indices$annee, df_indices$indice, xout=annee)$y
}
# Décumul → As-If → Stabilisation
df <- df[order(df$sinistre_id, df$annee_reg),]
df$prev <- c(0, df$total[-nrow(df)])
df$prev[df$annee_reg == min(df$annee_reg[df$sinistre_id==df$sinistre_id[1]])] <- 0
df$increment <- pmax(df$total - df$prev, 0)
# As-If
I_cotation <- get_indice(2026, df_indices)
df$inc_asif <- df$increment * (I_cotation / df$I_reg)
# Stabilisation (seuil = 5%)
df$ratio <- df$I_reg / df$I_surv
df$inc_stab <- ifelse(df$ratio >= 1.05, df$inc_asif * (df$I_surv/df$I_reg), df$inc_asif)
# Recumul
df$Sk       <- ave(df$inc_asif, df$sinistre_id, FUN=cumsum)
df$Sprime_k <- ave(df$inc_stab, df$sinistre_id, FUN=cumsum)
df$coeff    <- df$Sk / pmax(df$Sprime_k, 1e-6)
""",
}


def afficher_integration_r():
    """Interface d'intégration R Studio — scripts téléchargeables."""
    import io as _io_r

    st.markdown("---")
    st.markdown("#### 🔬 Intégration R — Scripts de tarification")
    st.markdown("""
    <div style="background:linear-gradient(135deg,#0d2b3e,#1e3a52);
        padding:12px 18px;border-left:4px solid #00b5a5;margin-bottom:12px;font-size:12px;color:white">
      <b style="color:#00b5a5">Note :</b> Streamlit Cloud ne supporte pas R nativement.
      Téléchargez les scripts et exécutez-les dans votre <b>RStudio local</b>.<br>
      Packages requis : <code>evir</code>, <code>fitdistrplus</code>, <code>MASS</code>
    </div>""", unsafe_allow_html=True)

    col_script, col_dl = st.columns([2, 1])
    with col_script:
        script_choisi = st.selectbox(
            "Script R à afficher / télécharger",
            list(SCRIPTS_R_TARIFICATION.keys()),
            key="r_script_select")
    with col_dl:
        st.markdown("<div style='height:28px'></div>", unsafe_allow_html=True)
        nom_fichier = script_choisi.lower().replace(" ","_").replace("/","_").replace("(","").replace(")","") + ".R"
        st.download_button(
            "⬇️ Télécharger le script .R",
            data=SCRIPTS_R_TARIFICATION[script_choisi].encode("utf-8"),
            file_name=nom_fichier,
            mime="text/plain",
            key="btn_dl_r_script",
            use_container_width=True,
            help="Ouvrez ce fichier dans RStudio"
        )

    st.code(SCRIPTS_R_TARIFICATION[script_choisi], language="r")

    # Script personnalisé avec téléchargement
    st.markdown("##### Script R personnalisé")
    st.caption("Écrivez votre code R, puis téléchargez-le pour l'exécuter dans RStudio local.")
    r_custom = st.text_area(
        "Votre code R",
        height=140,
        key="r_custom_code",
        placeholder="# Écrivez votre code R ici\n# Ex: utiliser les paramètres alpha/lambda de la session\n\nalpha <- 1.45\nlambda <- 3.2\nseuil  <- 1600000\n\n# Simulation Pareto / Poisson\nset.seed(42)\nN <- rpois(10000, lambda)\n# ..."
    )
    if r_custom.strip():
        st.download_button(
            "⬇️ Télécharger mon_script.R",
            data=r_custom.encode("utf-8"),
            file_name="mon_script_tarification.R",
            mime="text/plain",
            key="btn_dl_r_custom",
            use_container_width=False,
        )

    # Paramètres courants de la session pour R
    if "alpha_est" in st.session_state:
        st.markdown("**Paramètres actuels de la session (à copier dans R) :**")
        params_r = f"""# ── Paramètres Atlantic Re IA — session courante ─────────────
alpha  <- {st.session_state.get('alpha_est',  1.5):.6f}  # Indice Pareto
lambda <- {st.session_state.get('lambda_est', 5.0):.6f}  # Fréquence Poisson
seuil  <- {st.session_state.get('seuil_est',  1_600_000):.0f}     # Seuil modélisation (MAD)
gnpi   <- {gnpi:.0f}                                # GNPI (MAD)
Pm     <- {st.session_state.get('Pm_proxy',   0):.0f}     # Pm proxy P99.5 (MAD)
# Tranches
{"".join([f"D_T{i+1} <- {t['priorite']:.0f}  # Priorité {t['nom']}\nL_T{i+1} <- {t['portee']:.0f}  # Portée {t['nom']}\n" for i,t in enumerate(tranches_input)])}
"""
        st.code(params_r, language="r")
        st.download_button(
            "⬇️ Télécharger parametres_session.R",
            data=params_r.encode("utf-8"),
            file_name="parametres_session_atlanticre.R",
            mime="text/plain",
            key="btn_dl_params_r",
        )
