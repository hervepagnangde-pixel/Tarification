"""
IA TARIF — Agent Python pur
AgentActuarielPython : pipeline complet BC -> Simulation -> Market Curve -> Rapport -> Variantes.

Module sans LLM, utilisable hors ligne.
Correction intégrée : initialisation robuste de df_ml et calibration prudente des élasticités.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
import pandas as pd

from modules.optimization import _lookup_taux, _lookup_result, _json_safe


class AgentActuarielPython:
    """
    Agent de tarification 100 % Python.

    Le moteur applique des règles actuarielles explicites :
      1. validation des paramètres ;
      2. Burning Cost ;
      3. simulation fréquence-sévérité ;
      4. contrôles de cohérence ;
      5. courbe de marché ;
      6. rapport de tarification ;
      7. variantes comparables de programme.
    """

    def __init__(
        self,
        tranches,
        gnpi,
        df_proj,
        coeffs,
        alpha_est,
        lambda_est,
        seuil_est,
        Pm_proxy,
        chargement_majeurs,
        df_mkt_clean=None,
        df_ml=None,
        loi_sim="pareto",
        mu_ln=None,
        sigma_ln=None,
        gpd_xi=None,
        gpd_beta=None,
    ):
        self.tranches = tranches or []
        self.gnpi = float(gnpi or 0.0)
        self.df_proj = df_proj if df_proj is not None else pd.DataFrame()
        self.coeffs = np.asarray(coeffs if coeffs is not None else [1.0], dtype=float)
        self.alpha = float(alpha_est or 1.5)
        self.lambda_ = float(lambda_est or 0.0)
        self.seuil = float(seuil_est or 0.0)
        self.Pm_proxy = float(Pm_proxy or 0.0)
        self.chargement_majeurs = float(chargement_majeurs or 0.0)
        self.df_mkt = df_mkt_clean

        # IMPORTANT : certains workflows lancent l'agent avant le module labo/ML.
        # L'attribut doit donc toujours exister, même si aucun dataset ML n'est disponible.
        self.df_ml = df_ml
        self.loi_sim = str(loi_sim or "pareto").lower()
        self.mu_ln = None if mu_ln is None else float(mu_ln)
        self.sigma_ln = None if sigma_ln is None else float(sigma_ln)
        self.gpd_xi = None if gpd_xi is None else float(gpd_xi)
        self.gpd_beta = None if gpd_beta is None else float(gpd_beta)

        self.log = []
        self.anomalies = []
        self.resultats_bc = []
        self.resultats_sim = []
        self.resultats_mkt = []
        self.rapport_rows = []
        self.variantes = {}
        self.prime_totale = 0.0

    # ------------------------------------------------------------------
    # UTILITAIRES
    # ------------------------------------------------------------------
    def _log(self, etape, decision, detail=""):
        self.log.append({"etape": etape, "decision": decision, "detail": detail})

    def _alerte(self, niveau, message):
        """niveau : INFO / WARN / CRITIQUE."""
        self.anomalies.append({"niveau": niveau, "message": message})

    @staticmethod
    def _num(x, default=0.0):
        try:
            if x is None or x == "":
                return default
            if isinstance(x, str):
                s = x.replace("%", "").replace(" ", "").replace(",", ".")
                val = float(s)
                return val / 100.0 if "%" in x or val > 1.5 else val
            return float(x)
        except Exception:
            return default

    @staticmethod
    def _arrondir_mad(x, pas=500_000, minimum=0.0):
        try:
            return max(round(float(x) / pas) * pas, minimum)
        except Exception:
            return minimum

    def _get_taux_rec_list(self, t_info):
        n_rec = int(t_info.get("nb_reconstitutions", 0) or 0)
        if "taux_reconstitutions" in t_info and t_info.get("taux_reconstitutions"):
            vals = list(t_info.get("taux_reconstitutions") or [])
        else:
            vals = [float(t_info.get("taux_reconstitution", 100.0) or 100.0)] * n_rec
        return [float(v or 0.0) for v in vals[:n_rec]]

    # ------------------------------------------------------------------
    # CALIBRATION DES ÉLASTICITÉS
    # ------------------------------------------------------------------
    def _calibrer_elasticites(self):
        """
        Calibre les élasticités log-log depuis le dataset de scénarios ML si disponible.

        Si df_ml n'existe pas ou est insuffisant, retourne des valeurs prudentes
        par défaut. Cela évite le plantage observé :
        AttributeError: 'AgentActuarielPython' object has no attribute 'df_ml'.
        """
        valeurs_defaut = {
            "e_portee": 0.60,
            "e_priorite": 0.35,
            "e_recon": 0.08,
            "calibre": False,
            "source": "valeurs_par_defaut",
        }

        df_ml = getattr(self, "df_ml", None)
        if df_ml is None or not isinstance(df_ml, pd.DataFrame) or len(df_ml) < 10:
            return valeurs_defaut

        df = df_ml.copy().replace([np.inf, -np.inf], np.nan)
        colonnes = ["taux_retenu", "priorite", "portee", "nb_reconstitutions"]
        if not all(c in df.columns for c in colonnes):
            return valeurs_defaut

        for c in colonnes:
            df[c] = pd.to_numeric(df[c], errors="coerce")

        df = df.dropna(subset=colonnes)
        df = df[
            (df["taux_retenu"] > 0)
            & (df["priorite"] > 0)
            & (df["portee"] > 0)
            & (df["nb_reconstitutions"] >= 0)
        ].copy()

        if len(df) < 10:
            return valeurs_defaut

        try:
            from sklearn.linear_model import LinearRegression

            X = pd.DataFrame(
                {
                    "log_portee": np.log(df["portee"]),
                    "log_priorite": np.log(df["priorite"]),
                    "log_recon": np.log1p(df["nb_reconstitutions"]),
                }
            )
            y = np.log(df["taux_retenu"])

            reg = LinearRegression()
            reg.fit(X, y)
            coef = dict(zip(X.columns, reg.coef_))

            e_portee = float(coef.get("log_portee", valeurs_defaut["e_portee"]))
            e_priorite = float(-coef.get("log_priorite", valeurs_defaut["e_priorite"]))
            e_recon = float(coef.get("log_recon", valeurs_defaut["e_recon"]))

            # Encadrement prudent : on évite des sensibilités absurdes.
            e_portee = min(max(e_portee, 0.10), 1.50)
            e_priorite = min(max(e_priorite, 0.05), 1.50)
            e_recon = min(max(e_recon, 0.00), 0.50)

            return {
                "e_portee": e_portee,
                "e_priorite": e_priorite,
                "e_recon": e_recon,
                "calibre": True,
                "source": "dataset_scenarios_ml",
                "n_obs": int(len(df)),
            }

        except Exception as exc:
            self._alerte("INFO", f"Calibration des élasticités non utilisée : {exc}")
            return valeurs_defaut

    # ------------------------------------------------------------------
    # ÉTAPE 0 — VALIDATION
    # ------------------------------------------------------------------
    def etape_0_validation(self):
        self._log("Validation", "Vérification des paramètres actuariels")

        if self.df_proj is None or self.df_proj.empty:
            self._alerte("CRITIQUE", "Aucune donnée projetée disponible pour le calcul.")

        if self.gnpi <= 0:
            self._alerte("CRITIQUE", "GNPI nul ou négatif.")

        if self.alpha < 0.8:
            self._alerte("CRITIQUE", f"Alpha = {self.alpha:.4f} < 0.8 : queue très lourde, résultats sensibles.")
        elif self.alpha > 4.0:
            self._alerte("WARN", f"Alpha = {self.alpha:.4f} > 4.0 : vérifier la pertinence de la loi de sévérité.")
        else:
            self._log("Alpha", f"Paramètre alpha cohérent : {self.alpha:.4f}")

        if self.lambda_ < 0.0:
            self._alerte("CRITIQUE", f"Lambda = {self.lambda_:.4f} négatif.")
        elif self.lambda_ < 0.5:
            self._alerte("WARN", f"Lambda = {self.lambda_:.4f} faible : fréquence quasi nulle au-dessus du seuil.")
        elif self.lambda_ > 50:
            self._alerte("WARN", f"Lambda = {self.lambda_:.4f} élevé : vérifier le seuil de modélisation.")
        else:
            self._log("Lambda", f"Fréquence moyenne cohérente : {self.lambda_:.4f}")

        trav = [t for t in self.tranches if t.get("type") == "travaillante"]
        cat = [t for t in self.tranches if t.get("type") == "cat"]
        if not trav:
            self._alerte("WARN", "Aucune tranche travaillante dans le programme.")
        if not cat:
            self._alerte("INFO", "Aucune tranche cat : courbe de marché potentiellement non applicable.")
        self._log("Programme", f"{len(trav)} tranche(s) travaillante(s), {len(cat)} tranche(s) cat.")

    # ------------------------------------------------------------------
    # ÉTAPE 1 — BURNING COST
    # ------------------------------------------------------------------
    def etape_1_burning_cost(self):
        self._log("Burning Cost", "Calcul BC individuel par sinistre et agrégation annuelle.")
        resultats = []

        if self.df_proj is None or self.df_proj.empty:
            self.resultats_bc = []
            self._alerte("CRITIQUE", "Burning Cost impossible : df_proj vide.")
            return []

        for t_info in self.tranches:
            nom = t_info.get("nom", "Tranche")
            D = float(t_info.get("priorite", 0.0) or 0.0)
            L = float(t_info.get("portee", 0.0) or 0.0)
            aal = t_info.get("AAL")
            aad = t_info.get("AAD")
            n_rec = int(t_info.get("nb_reconstitutions", 0) or 0)
            taux_rec_list = self._get_taux_rec_list(t_info)
            cap = (n_rec + 1) * L

            df_p = self.df_proj.copy()
            if "Sprime_ultime" not in df_p.columns or "annee_surv" not in df_p.columns:
                self._alerte("CRITIQUE", f"{nom} : colonnes df_proj insuffisantes pour le BC.")
                continue
            if "coeff_stab" not in df_p.columns:
                df_p["coeff_stab"] = 1.0

            df_p["Ck"] = df_p.apply(
                lambda row: min(max(float(row.get("Sprime_ultime", 0.0)) - D, 0.0), L)
                * float(row.get("coeff_stab", 1.0) or 1.0),
                axis=1,
            )

            charges_ann = df_p.groupby("annee_surv")["Ck"].sum()
            charges_finales = []
            for ann, ch in charges_ann.items():
                ch = float(ch)
                if aad:
                    ch = max(ch - float(aad), 0.0)
                if aal:
                    ch = min(ch, float(aal))
                charges_finales.append({"annee": int(ann), "charge": float(min(ch, cap))})

            df_ch = pd.DataFrame(charges_finales)
            N = len(df_ch)
            charges_nonzero = [c["charge"] for c in charges_finales if c["charge"] > 0]
            n_nz = len(charges_nonzero)

            Pr_Rec = 0.0
            if N > 0 and L > 0:
                for C_n in df_ch["charge"].values:
                    for r_idx, t_r_i in enumerate(taux_rec_list):
                        Pr_Rec += (float(t_r_i) / 100.0) * min(L, max(float(C_n) - r_idx * L, 0.0))
                Pr_Rec /= L
            Rec = Pr_Rec / (Pr_Rec + N) if (Pr_Rec + N) > 0 else 0.0

            if n_nz < 3:
                tp = tr = tt = sigma = 0.0
                charge_moy = 0.0
                Pr_Rec = 0.0
                Rec = 0.0
                chargement_majeurs_bc = 0.0
                self._alerte("WARN", f"{nom} : BC non crédible, seulement {n_nz} année(s) non nulle(s).")
            else:
                charge_moy = float(df_ch["charge"].mean())
                chargement_majeurs_bc = self.chargement_majeurs
                tp = charge_moy / max(self.gnpi, 1.0)
                sigma = float(np.std(charges_nonzero)) / max(self.gnpi, 1.0)
                tr = tp + sigma * 0.20
                denom = max(
                    1
                    - float(t_info.get("brokage", 0.0) or 0.0)
                    - float(t_info.get("frais", 0.0) or 0.0)
                    - float(t_info.get("marge", 0.0) or 0.0)
                    - float(t_info.get("retrocession", 0.0) or 0.0),
                    0.01,
                )
                tt = (tr * (1 - Rec)) / denom

            resultats.append(
                {
                    "tranche": nom,
                    "type": t_info.get("type", ""),
                    "charge_moy": round(charge_moy, 2),
                    "n_ann_nonzero": int(n_nz),
                    "sigma_hist": round(sigma if n_nz >= 3 else 0.0, 6),
                    "Pr_Rec": round(Pr_Rec, 6),
                    "Rec": round(Rec, 6),
                    "taux_pur": round(tp, 6),
                    "taux_risque": round(tr, 6),
                    "taux_technique": round(tt, 6),
                    "chargement_majeurs": round(chargement_majeurs_bc, 6),
                    "detail_annuel": charges_finales,
                }
            )
            self._log("BC", f"{nom}: taux pur={tp:.4%}, taux technique={tt:.4%}, années non nulles={n_nz}.")

        self.resultats_bc = resultats
        return resultats

    # ------------------------------------------------------------------
    # ÉTAPE 2 — SIMULATION
    # ------------------------------------------------------------------
    def etape_2_simulation(self, n_sim=10000, seed=42):
        """
        Simulation fréquence-sévérité.
        La loi de sévérité utilisée est celle retenue dans l'interface :
        Pareto, Lognormale ou GPD. Le LLM ne choisit pas la loi à la place
        de l'utilisateur ; il exploite les paramètres déjà validés.
        """
        loi = str(getattr(self, "loi_sim", "pareto") or "pareto").lower()
        self._log(
            "Simulation",
            f"Simulation fréquence-sévérité : loi={loi}, lambda={self.lambda_:.4f}, seuil={self.seuil:,.0f}, n={n_sim:,}.",
        )
        rng = np.random.default_rng(seed)
        resultats = []

        if self.lambda_ <= 0 or self.seuil <= 0:
            self._alerte("CRITIQUE", "Simulation impossible : lambda ou seuil invalide.")
            self.resultats_sim = []
            return []
        if loi == "pareto" and self.alpha <= 0:
            self._alerte("CRITIQUE", "Simulation Pareto impossible : alpha invalide.")
            self.resultats_sim = []
            return []
        if loi == "lognormale":
            if self.mu_ln is None:
                self.mu_ln = float(np.log(max(self.seuil, 1.0)))
            if self.sigma_ln is None or self.sigma_ln <= 0:
                self._alerte("CRITIQUE", "Simulation lognormale impossible : sigma invalide.")
                self.resultats_sim = []
                return []
        if loi == "gpd":
            if self.gpd_xi is None:
                self.gpd_xi = 0.0
            if self.gpd_beta is None or self.gpd_beta <= 0:
                self._alerte("CRITIQUE", "Simulation GPD impossible : beta invalide.")
                self.resultats_sim = []
                return []

        coeffs = self.coeffs[np.isfinite(self.coeffs)]
        if len(coeffs) == 0:
            coeffs = np.array([1.0])

        def generer_sinistres(n_sin):
            if n_sin <= 0:
                return np.array([], dtype=float)
            if loi == "pareto":
                u = rng.uniform(size=n_sin)
                return self.seuil * (u ** (-1.0 / self.alpha))
            if loi == "lognormale":
                sp = rng.lognormal(float(self.mu_ln), float(self.sigma_ln), size=n_sin)
                return np.maximum(sp, self.seuil)
            if loi == "gpd":
                u = rng.uniform(size=n_sin)
                xi = float(self.gpd_xi)
                beta = float(self.gpd_beta)
                if abs(xi) < 1e-10:
                    return self.seuil - beta * np.log(np.clip(u, 1e-12, 1.0))
                return self.seuil + beta / xi * ((1.0 - np.clip(u, 1e-12, 1-1e-12)) ** (-xi) - 1.0)
            # Garde-fou : loi inconnue, on bloque plutôt que de revenir silencieusement à Pareto.
            raise ValueError(f"Loi de sévérité inconnue : {loi}")

        for t_info in self.tranches:
            nom = t_info.get("nom", "Tranche")
            D = float(t_info.get("priorite", 0.0) or 0.0)
            P = float(t_info.get("portee", 0.0) or 0.0)
            r = int(t_info.get("nb_reconstitutions", 0) or 0)
            aal = t_info.get("AAL")
            aad = t_info.get("AAD")
            cap = (r + 1) * P

            def simuler(avec_aal=True, avec_aad=True, avec_rec=True):
                charges = []
                for _ in range(int(n_sim)):
                    n_sin = rng.poisson(self.lambda_)
                    s_tot = 0.0
                    if n_sin > 0:
                        sp = generer_sinistres(int(n_sin))
                        ic = rng.choice(len(coeffs), size=int(n_sin), replace=True)
                        for k in range(int(n_sin)):
                            s = float(sp[k])
                            c = float(coeffs[ic[k]])
                            if s <= D:
                                s_i = 0.0
                            elif s <= D + P:
                                s_i = c * (s - D)
                            else:
                                s_i = c * P
                            s_tot += s_i
                    ch = s_tot
                    if avec_aad and aad:
                        ch = max(ch - float(aad), 0.0)
                    if avec_aal and aal:
                        ch = min(ch, float(aal))
                    charges.append(min(ch, cap) if avec_rec else ch)
                return np.array(charges, dtype=float)

            def calc(ch):
                p0 = float(np.mean(ch))
                sig = float(np.std(ch))
                tp = p0 / max(self.gnpi, 1.0)
                tr = (p0 + 0.2 * sig) / max(self.gnpi, 1.0)
                denom = max(
                    1
                    - float(t_info.get("brokage", 0.0) or 0.0)
                    - float(t_info.get("frais", 0.0) or 0.0)
                    - float(t_info.get("marge", 0.0) or 0.0)
                    - float(t_info.get("retrocession", 0.0) or 0.0),
                    0.01,
                )
                tt = tr / denom
                return round(tp, 6), round(tr, 6), round(tt, 6), round(sig / max(self.gnpi, 1.0), 6)

            c_base = simuler(True, True, True)
            c_saal = simuler(False, True, True)
            c_saad = simuler(True, False, True)
            c_srec = simuler(True, True, False)

            tp, tr, tt, sigma_sim = calc(c_base)
            _, _, tt_aal, _ = calc(c_saal)
            _, _, tt_aad, _ = calc(c_saad)
            _, _, tt_rec, _ = calc(c_srec)

            parametres = {
                "loi": loi,
                "lambda": round(self.lambda_, 6),
                "seuil": round(self.seuil, 2),
                "n_sim": int(n_sim),
                "seed": int(seed),
            }
            if loi == "pareto":
                parametres["alpha"] = round(self.alpha, 6)
            elif loi == "lognormale":
                parametres["mu"] = round(float(self.mu_ln), 6)
                parametres["sigma"] = round(float(self.sigma_ln), 6)
            elif loi == "gpd":
                parametres["xi"] = round(float(self.gpd_xi), 6)
                parametres["beta"] = round(float(self.gpd_beta), 2)

            resultats.append(
                {
                    "tranche": nom,
                    "type": t_info.get("type", ""),
                    "taux_pur": tp,
                    "taux_risque": tr,
                    "taux_technique": tt,
                    "sigma_sim": sigma_sim,
                    "chargement_majeurs": round(self.chargement_majeurs, 6),
                    "sans_aal": tt_aal,
                    "sans_aad": tt_aad,
                    "sans_rec": tt_rec,
                    "impact_aal": round(tt_aal - tt, 6),
                    "impact_aad": round(tt_aad - tt, 6),
                    "impact_rec": round(tt_rec - tt, 6),
                    "parametres_simulation": parametres,
                    "loi_severite": loi,
                    "param_lambda": round(self.lambda_, 6),
                    "param_seuil": round(self.seuil, 2),
                    "n_sim": int(n_sim),
                    "seed": int(seed),
                }
            )
            self._log("Simulation", f"{nom}: loi={loi}, taux pur={tp:.4%}, taux technique={tt:.4%}.")

        self.resultats_sim = resultats
        return resultats

    # ------------------------------------------------------------------
    # ÉTAPE 3 — CONTRÔLES BC / SIMULATION
    # ------------------------------------------------------------------
    def etape_3_controles(self):
        self._log("Contrôles", "Vérification de la cohérence BC / Simulation.")
        bc_map = {r.get("tranche"): r for r in self.resultats_bc}
        sim_map = {r.get("tranche"): r for r in self.resultats_sim}

        for t in self.tranches:
            nom = t.get("nom", "")
            bc_tt = float(bc_map.get(nom, {}).get("taux_technique", 0.0) or 0.0)
            si_tt = float(sim_map.get(nom, {}).get("taux_technique", 0.0) or 0.0)

            if t.get("type") == "travaillante" and bc_tt > 0 and si_tt > 0:
                ecart = abs(bc_tt - si_tt) / max(bc_tt, 1e-12)
                if ecart > 0.50:
                    self._alerte("CRITIQUE", f"{nom}: écart BC/Simulation = {ecart:.0%}, analyse complémentaire requise.")
                elif ecart > 0.30:
                    self._alerte("WARN", f"{nom}: écart BC/Simulation = {ecart:.0%}, justification nécessaire.")
                else:
                    self._log("Contrôle BC/Simulation", f"{nom}: écart={ecart:.0%}, convergence acceptable.")

            if t.get("type") == "cat" and bc_tt == 0:
                self._log("Contrôle Cat", f"{nom}: BC nul cohérent pour une tranche cat non touchée historiquement.")

    # ------------------------------------------------------------------
    # ÉTAPE 4 — MARKET CURVE
    # ------------------------------------------------------------------
    def etape_4_market_curve(self, r2_min=0.40):
        cat_tranches = [t for t in self.tranches if t.get("type") != "travaillante"]
        if not cat_tranches:
            self._log("Courbe de marché", "Aucune tranche non travaillante/cat : courbe de marché non appliquée.")
            self.resultats_mkt = []
            return []
        if self.df_mkt is None or len(self.df_mkt) == 0:
            self._alerte("INFO", "Données marché non fournies : courbe de marché ignorée.")
            self.resultats_mkt = []
            return []

        df_mkt = self.df_mkt.copy().replace([np.inf, -np.inf], np.nan)
        if not {"midpoints", "ROLs"}.issubset(df_mkt.columns):
            self._alerte("CRITIQUE", "Données marché insuffisantes : colonnes midpoints et ROLs requises.")
            self.resultats_mkt = []
            return []

        df_mkt["midpoints"] = pd.to_numeric(df_mkt["midpoints"], errors="coerce")
        df_mkt["ROLs"] = pd.to_numeric(df_mkt["ROLs"], errors="coerce")
        df_mkt = df_mkt[(df_mkt["midpoints"] > 0) & (df_mkt["ROLs"] > 0)].dropna()

        if len(df_mkt) < 8:
            self._alerte("WARN", f"Courbe de marché peu exploitable : seulement {len(df_mkt)} point(s).")
            self.resultats_mkt = []
            return []

        self._log("Courbe de marché", f"Ajustement ROL = a x^(-b) sur {len(df_mkt)} point(s).")

        def fit_power(x, y):
            lx = np.log(x)
            ly = np.log(y)
            c = np.polyfit(lx, ly, 1)
            a = float(np.exp(c[1]))
            b = float(-c[0])
            ly_pred = np.polyval(c, lx)
            r2 = 1 - np.sum((ly - ly_pred) ** 2) / (np.sum((ly - ly.mean()) ** 2) + 1e-10)
            return a, b, float(r2)

        def calc_taux_cat(t, a, b):
            x = (float(t.get("priorite", 0.0)) + float(t.get("portee", 0.0)) / 2.0) / max(self.gnpi, 1.0)
            rol = a * (x ** (-b))
            tp = rol * float(t.get("portee", 0.0)) / max(self.gnpi, 1.0)
            tr = tp * 1.002
            denom = max(
                1
                - float(t.get("brokage", 0.0) or 0.0)
                - float(t.get("frais", 0.0) or 0.0)
                - float(t.get("marge", 0.0) or 0.0)
                - float(t.get("retrocession", 0.0) or 0.0),
                0.01,
            )
            tt = tr / denom
            return {
                "tranche": t.get("nom", ""),
                "type": t.get("type", ""),
                "x_norm": round(x, 6),
                "rol": round(rol, 6),
                "taux_pur": round(tp, 6),
                "taux_tech": round(tt, 6),
                "taux": round(tt, 6),
                "chargement_majeurs": round(self.chargement_majeurs, 6),
            }

        best = None
        for q in [0.40, 0.60, 0.80, 1.00, 0.20]:
            try:
                mq = np.quantile(df_mkt["midpoints"], q)
                df_q = df_mkt[df_mkt["midpoints"] <= mq]
                if len(df_q) < 8:
                    continue
                a, b, r2 = fit_power(df_q["midpoints"].values, df_q["ROLs"].values)
                if b <= 0:
                    continue
                taux_tranches = [calc_taux_cat(t, a, b) for t in cat_tranches]
                if any(tt.get("taux", 0) <= 0 for tt in taux_tranches):
                    continue
                score = r2 + (0.3 if r2 >= r2_min else 0.0) + 0.01 * len(df_q)
                if best is None or score > best["score"]:
                    best = {
                        "a": a,
                        "b": b,
                        "r2": r2,
                        "n": len(df_q),
                        "quantile": q,
                        "taux_tranches": taux_tranches,
                        "score": score,
                    }
            except Exception:
                continue

        if best is None:
            self._alerte("CRITIQUE", "Aucun ajustement valide de courbe de marché.")
            self.resultats_mkt = []
            return []

        if best["r2"] < r2_min:
            self._alerte("WARN", f"Courbe de marché de faible qualité : R2={best['r2']:.3f}.")
        else:
            self._log("Courbe de marché", f"R2={best['r2']:.3f}, N={best['n']}, a={best['a']:.5f}, b={best['b']:.4f}.")

        all_tts = []
        cat_map = {tt["tranche"]: tt for tt in best["taux_tranches"]}
        for t in self.tranches:
            nom = t.get("nom", "")
            if nom in cat_map:
                all_tts.append(cat_map[nom])
            else:
                all_tts.append(
                    {
                        "tranche": nom,
                        "type": t.get("type", ""),
                        "x_norm": 0,
                        "rol": 0,
                        "taux_pur": 0,
                        "taux_tech": 0,
                        "taux": 0,
                        "chargement_majeurs": 0,
                    }
                )
        self.resultats_mkt = all_tts
        return all_tts

    # ------------------------------------------------------------------
    # ÉTAPE 5 — RAPPORT
    # ------------------------------------------------------------------
    def etape_5_rapport(self):
        self._log("Rapport", "Sélection : max(BC, Simulation) pour travaillante ; max(Simulation, Marché) sinon.")
        mkt_map = {r.get("tranche"): r.get("taux", 0.0) for r in self.resultats_mkt}
        rows = []
        pt = 0.0

        for idx_t, t in enumerate(self.tranches):
            nom = t.get("nom", f"Tranche {idx_t + 1}")
            bc_tt = _lookup_taux(self.resultats_bc, nom, idx_t, "taux_technique")
            si_tt = _lookup_taux(self.resultats_sim, nom, idx_t, "taux_technique")
            mkt = float(mkt_map.get(nom, 0.0) or 0.0) if t.get("type") != "travaillante" else 0.0

            if t.get("type") == "travaillante":
                taux = max(bc_tt, si_tt)
                meth = f"max(BC={bc_tt:.4%}, Simulation={si_tt:.4%})"
            else:
                taux = max(si_tt, mkt)
                meth = f"max(Simulation={si_tt:.4%}, Marché={mkt:.4%})"

            prime = self.gnpi * taux
            pt += prime
            ecart = abs(bc_tt - si_tt) / max(bc_tt, 1e-12) * 100 if bc_tt > 0 else 0.0
            rows.append(
                {
                    "tranche": nom,
                    "type": t.get("type", ""),
                    "taux_bc": round(bc_tt, 6),
                    "taux_sim": round(si_tt, 6),
                    "taux_mkt": round(mkt, 6),
                    "taux_retenu": round(taux, 6),
                    "methode": meth,
                    "prime_MAD": round(prime, 2),
                    "ecart_bc_sim_pct": round(ecart, 1),
                }
            )
            self._log("Sélection", f"{nom}: {meth}, prime={prime:,.0f} MAD.")

        self.rapport_rows = rows
        self.prime_totale = pt
        return rows, pt

    # ------------------------------------------------------------------
    # ÉTAPE 6 — VARIANTES COMPARABLES / LOGIQUE DE FINETTI
    # ------------------------------------------------------------------
    def etape_6_optimisation(self):
        """
        Génère des variantes comparables du programme initial.

        Logique :
        - ne pas produire des programmes explicitement « avantage cédante/réassureur » ;
        - rester proche du programme initial ;
        - privilégier la stabilité et la convergence des méthodes ;
        - utiliser les élasticités calibrées si le dataset ML existe, sinon valeurs par défaut.
        """
        self._log("Optimisation", "Recherche de programmes alternatifs comparables.")

        elasticites = self._calibrer_elasticites()
        e_portee = elasticites["e_portee"]
        e_priorite = elasticites["e_priorite"]
        e_recon = elasticites["e_recon"]

        sim_map = {r.get("tranche"): r for r in self.resultats_sim}
        bc_map = {r.get("tranche"): r for r in self.resultats_bc}
        mkt_map = {r.get("tranche"): r for r in self.resultats_mkt}

        def taux_base(t):
            nom = t.get("nom", "")
            bc = float(bc_map.get(nom, {}).get("taux_technique", 0.0) or 0.0)
            sim = float(sim_map.get(nom, {}).get("taux_technique", 0.0) or 0.0)
            mkt = float(mkt_map.get(nom, {}).get("taux", 0.0) or 0.0)
            if t.get("type") == "travaillante":
                return max(bc, sim)
            return max(sim, mkt)

        def sigma_ref(t):
            nom = t.get("nom", "")
            s_sim = float(sim_map.get(nom, {}).get("sigma_sim", 0.0) or 0.0)
            s_bc = float(bc_map.get(nom, {}).get("sigma_hist", 0.0) or 0.0)
            return max(s_sim, s_bc, 0.0)

        def convergence_ref(t):
            nom = t.get("nom", "")
            vals = []
            for v in [
                bc_map.get(nom, {}).get("taux_technique", 0.0),
                sim_map.get(nom, {}).get("taux_technique", 0.0),
                mkt_map.get(nom, {}).get("taux", 0.0),
            ]:
                v = float(v or 0.0)
                if v > 0:
                    vals.append(v)
            if len(vals) <= 1:
                return 0.0
            return float(np.std(vals) / max(np.mean(vals), 1e-12))

        def evaluer_programme(label, mult_D=1.0, mult_C=1.0, delta_rec=0):
            tranches_alt = []
            prime = 0.0
            protection = 0.0
            variance_proxy = 0.0
            convergence = 0.0
            ecart_structure = 0.0

            for t in self.tranches:
                t_alt = dict(t)
                D0 = float(t.get("priorite", 0.0) or 0.0)
                C0 = float(t.get("portee", 0.0) or 0.0)
                rec0 = int(t.get("nb_reconstitutions", 0) or 0)

                D1 = self._arrondir_mad(D0 * mult_D, minimum=500_000)
                C1 = self._arrondir_mad(C0 * mult_C, minimum=500_000)
                rec1 = int(max(0, min(5, rec0 + delta_rec)))

                t_alt["priorite"] = D1
                t_alt["portee"] = C1
                t_alt["nb_reconstitutions"] = rec1

                base = taux_base(t)
                if base <= 0:
                    base = float(sim_map.get(t.get("nom", ""), {}).get("taux_technique", 0.0) or 0.0)

                adj_portee = (C1 / max(C0, 1.0)) ** e_portee
                adj_priorite = (D0 / max(D1, 1.0)) ** e_priorite
                adj_recon = ((rec1 + 1) / max(rec0 + 1, 1)) ** e_recon
                taux = max(base * adj_portee * adj_priorite * adj_recon, 0.0)

                prime_t = self.gnpi * taux
                prime += prime_t
                protection_t = C1 * (rec1 + 1)
                protection += protection_t

                sig = sigma_ref(t)
                variance_proxy += (sig * self.gnpi) ** 2 * (C1 / max(C0, 1.0)) ** 2
                convergence += convergence_ref(t)
                ecart_structure += abs(D1 / max(D0, 1.0) - 1.0) + abs(C1 / max(C0, 1.0) - 1.0) + 0.25 * abs(rec1 - rec0)

                t_alt["_taux"] = taux
                t_alt["_prime"] = prime_t
                tranches_alt.append(t_alt)

            n = max(len(self.tranches), 1)
            taux_global = prime / max(self.gnpi, 1.0)
            variance_moyenne = variance_proxy / n
            convergence_moyenne = convergence / n
            ecart_structure_moyen = ecart_structure / n

            # Score De Finetti simplifié : priorité à la variance faible,
            # puis à la convergence des méthodes et à la proximité du programme initial.
            score = (
                -np.log1p(max(variance_moyenne, 0.0))
                -2.0 * convergence_moyenne
                -1.5 * ecart_structure_moyen
            )

            return {
                "label": label,
                "description": "Structure alternative comparable au programme initial.",
                "tranches": tranches_alt,
                "prime": round(prime, 2),
                "taux_global": round(taux_global, 6),
                "protection_theorique": round(protection, 2),
                "variance_proxy": round(float(variance_moyenne), 2),
                "indice_convergence_methodes": round(float(max(0.0, 1.0 - convergence_moyenne)) * 100, 2),
                "indice_comparabilite": round(float(max(0.0, 1.0 - ecart_structure_moyen)) * 100, 2),
                "score_de_finetti": round(float(score), 6),
                "elasticites": elasticites,
            }

        variantes = {
            "programme_initial": evaluer_programme("Programme initial", 1.00, 1.00, 0),
            "structure_comparable_1": evaluer_programme("Structure comparable 1", 1.05, 1.00, 0),
            "structure_comparable_2": evaluer_programme("Structure comparable 2", 1.00, 0.95, 0),
            "structure_comparable_3": evaluer_programme("Structure comparable 3", 1.10, 1.00, -1),
            "structure_comparable_4": evaluer_programme("Structure comparable 4", 0.95, 1.05, 0),
        }

        initial_prime = variantes["programme_initial"]["prime"]
        for key, v in variantes.items():
            v["ecart_prime_vs_initial"] = round((v["prime"] - initial_prime) / max(initial_prime, 1.0), 6)
            if key == "programme_initial":
                v["diagnostic"] = "Programme proposé par la cédante, utilisé comme base de comparaison."
            elif abs(v["ecart_prime_vs_initial"]) <= 0.15 and v["indice_comparabilite"] >= 70:
                v["diagnostic"] = "Programme alternatif comparable, techniquement discutable avec la cédante."
            else:
                v["diagnostic"] = "Programme indicatif : écart au programme initial à documenter."

        candidats = {k: v for k, v in variantes.items() if k != "programme_initial"}
        programme_recommande_key = max(candidats, key=lambda k: candidats[k]["score_de_finetti"]) if candidats else "programme_initial"
        variantes["programme_recommande"] = variantes[programme_recommande_key]
        variantes["programme_recommande"]["cle_source"] = programme_recommande_key

        self._log(
            "Optimisation",
            f"Variantes comparables générées. Élasticités : source={elasticites.get('source')}, calibré={elasticites.get('calibre')}.",
        )
        return variantes

    # ------------------------------------------------------------------
    # RAPPORT TEXTE
    # ------------------------------------------------------------------
    def generer_rapport_texte(self):
        taux_global = self.prime_totale / max(self.gnpi, 1.0)
        lignes = [
            "=" * 60,
            "RAPPORT DE TARIFICATION — AGENT PYTHON AUTONOME",
            "=" * 60,
            f"GNPI         : {self.gnpi:,.0f} MAD",
            f"Prime totale : {self.prime_totale:,.0f} MAD",
            f"Taux global  : {taux_global:.4%}",
            f"Tranches     : {len(self.tranches)}",
            "=" * 60,
            "",
            "PARAMÈTRES",
            f"Alpha        : {self.alpha:.4f}",
            f"Lambda       : {self.lambda_:.4f}",
            f"Seuil        : {self.seuil:,.0f} MAD",
            f"Pm proxy     : {self.Pm_proxy:,.0f} MAD",
            f"Charg. majeurs : {self.chargement_majeurs:.4%}",
            "",
            "RÉSULTATS PAR TRANCHE",
        ]

        for r in self.rapport_rows:
            statut = "DIVERGENCE" if r.get("ecart_bc_sim_pct", 0) > 30 else "COHÉRENT"
            lignes += [
                "",
                f"[{str(r.get('type','')).upper()}] {r.get('tranche','')}",
                f"BC={r.get('taux_bc',0):.4%} | Simulation={r.get('taux_sim',0):.4%} | Marché={r.get('taux_mkt',0):.4%}",
                f"Retenu : {r.get('taux_retenu',0):.4%} ({r.get('methode','')})",
                f"Prime  : {r.get('prime_MAD',0):,.0f} MAD | Statut : {statut} | Ecart BC/Sim : {r.get('ecart_bc_sim_pct',0):.0f}%",
            ]

        if self.anomalies:
            lignes += ["", "ALERTES"]
            for a in self.anomalies:
                lignes.append(f"[{a.get('niveau','')}] {a.get('message','')}")

        lignes += ["", "JOURNAL DES DÉCISIONS"]
        for entry in self.log:
            lignes.append(
                f"[{entry.get('etape','')}] {entry.get('decision','')}"
                + (f" — {entry.get('detail','')}" if entry.get("detail") else "")
            )
        lignes += ["", "=" * 60]
        return "\n".join(lignes)

    # ------------------------------------------------------------------
    # PIPELINE COMPLET
    # ------------------------------------------------------------------
    def run(self, n_sim=10000):
        self.etape_0_validation()
        self.etape_1_burning_cost()
        self.etape_2_simulation(n_sim)
        self.etape_3_controles()
        self.etape_4_market_curve()
        self.etape_5_rapport()
        self.variantes = self.etape_6_optimisation()
        return self.generer_rapport_texte()
