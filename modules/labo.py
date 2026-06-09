"""
Atlantic Re IA — Laboratoire de tarification ML
AgentLaboTarification : grille 120 scénarios, batch BC+Sim+Mkt,
RF/XGB/CatBoost, dichotomie, De Finetti-Borch, NSGA-II multi-objectif.
"""
import streamlit as st
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
import json, random
from modules.ui import tableau_resultats, card, section_header
from datetime import datetime

# ════════════════════════════════════════════
# LABORATOIRE DE TARIFICATION ML
# ════════════════════════════════════════════

class AgentLaboTarification:
    """
    Expérience par machine learning.
    Workflow :
      1. Grille 120 scenarios/tranche (auto, modifiable)
      2. Batch BC + Simulation + Market Curve
      3. Dataset ML (conditions + params -> taux)
      4. RF / DT / XGB
      5. Optimisation : dichotomie actuarielle + De Finetti
      6. Programme multi-tranches optimal
    """

    # ── Grille de variation ──────────────────────────────────────────
    MULT_PRIORITE    = [0.50, 0.60, 0.70, 0.80, 0.90, 1.00, 1.10, 1.20, 1.30, 1.50]
    MULT_PORTEE      = [0.70, 0.80, 0.90, 1.00, 1.15, 1.30]
    AAD_PCT          = [0.00, 0.05, 0.10, 0.15, 0.20]     # % de la portée
    NB_RECON         = [0, 1, 2, 3]
    TAUX_RECON_LIST  = [50.0, 75.0, 100.0]                 # % par reconstitution
    K_SECURITE       = [0.10, 0.15, 0.20, 0.25, 0.30]
    SEUIL_STAB       = [0.00, 0.05, 0.06, 0.07, 0.08, 0.09, 0.10, 0.20]

    FEATURES = [
        "priorite","portee","AAD_val","AAL_val",
        "nb_reconstitutions","taux_recon_1","taux_recon_2","taux_recon_moy",
        "brokage","frais","marge","retrocession","k_securite",
        "seuil_stab",
        "alpha","lambda_","seuil_modelisation",
        "type_travaillante","type_cat","type_non_trav",
        "ratio_D_GNPI","ratio_C_GNPI","ratio_aad_C","ratio_aal_C",
        "levier_frais","cap_sur_GNPI",
    ]
    TARGET = "taux_retenu"

    def __init__(self, tranches_base, gnpi, df_proj, coeffs,
                 alpha, lambda_, seuil, chargement_majeurs=0.0, df_mkt=None,
                 is_long=True):
        self.tranches_base      = tranches_base
        self.gnpi               = gnpi
        self.df_proj            = df_proj
        self.coeffs             = coeffs
        self.alpha              = alpha
        self.lambda_            = lambda_
        self.seuil              = seuil
        self.chargement_majeurs = chargement_majeurs
        self.df_mkt             = df_mkt
        self.is_long            = is_long
        self.grille             = []
        self.resultats          = []
        self.df_ml              = None
        self.modeles_entraines  = {}
        self.metriques_ml       = {}
        self.importance_vars    = {}
        self._features_used     = list(self.FEATURES)
        self._best_model_name   = None

    # ── 1. GÉNÉRATION GRILLE ────────────────────────────────────────

    def generer_grille_auto(self, n_max_par_tranche=120):
        import random, itertools
        random.seed(42)
        scenarios = []

        for t in self.tranches_base:
            D0 = t["priorite"]; C0 = t["portee"]
            pool = []
            for mD, mC, aad_p, n_rec, k_sec, t_rec, seuil_s in itertools.product(
                self.MULT_PRIORITE, self.MULT_PORTEE,
                self.AAD_PCT, self.NB_RECON,
                self.K_SECURITE, self.TAUX_RECON_LIST,
                self.SEUIL_STAB
            ):
                D   = max(round(D0 * mD / 500_000) * 500_000, 500_000)
                C   = max(round(C0 * mC / 500_000) * 500_000, 500_000)
                aad = round(C * aad_p / 100_000) * 100_000 if aad_p > 0 else None
                # reconstitution rates list
                if n_rec == 0:
                    taux_rec_list = []
                elif n_rec == 1:
                    taux_rec_list = [t_rec]
                elif n_rec == 2:
                    taux_rec_list = [min(t_rec, 75.0), 100.0]
                else:
                    taux_rec_list = [min(t_rec, 75.0), 100.0, 100.0]
                pool.append(self._make_scenario(
                    t, D, C, aad, None, n_rec, taux_rec_list, k_sec, seuil_s))

            # Échantillonnage aléatoire stratifié
            sampled = random.sample(pool, min(n_max_par_tranche, len(pool)))
            scenarios.extend(sampled)

            # Variantes AAL (travaillante)
            if t["type"] == "travaillante":
                for aal_m in [1.5, 2.0, 3.0]:
                    scenarios.append(self._make_scenario(
                        t, D0, C0, None, C0 * aal_m, 1, [100.0], 0.20, 0.00))

        self.grille = scenarios
        return scenarios

    def _make_scenario(self, t, D, C, aad, aal, n_rec, taux_rec_list, k_sec, seuil_s):
        tr1 = taux_rec_list[0] if len(taux_rec_list) > 0 else 0.0
        tr2 = taux_rec_list[1] if len(taux_rec_list) > 1 else 0.0
        tr_moy = float(np.mean(taux_rec_list)) if taux_rec_list else 0.0
        return {
            "tranche_base":        t["nom"],
            "type":                t["type"],
            "priorite":            float(D),
            "portee":              float(C),
            "AAD":                 float(aad) if aad else None,
            "AAL":                 float(aal) if aal else None,
            "nb_reconstitutions":  int(n_rec),
            "taux_reconstitution": float(taux_rec_list[0]) if taux_rec_list else 100.0,
            "taux_reconstitutions":taux_rec_list,
            "taux_recon_1":        tr1,
            "taux_recon_2":        tr2,
            "taux_recon_moy":      tr_moy,
            "brokage":             t["brokage"],
            "frais":               t["frais"],
            "marge":               t["marge"],
            "retrocession":        t["retrocession"],
            "alpha":               float(self.alpha),
            "lambda_":             float(self.lambda_),
            "seuil_modelisation":  float(self.seuil),
            "k_securite":          float(k_sec),
            "seuil_stab":          float(seuil_s),
        }

    # ── 2. BC ────────────────────────────────────────────────────────

    def _bc_scenario(self, s):
        D = s["priorite"]; L = s["portee"]
        aad = s.get("AAD"); aal = s.get("AAL")
        n_rec = int(s.get("nb_reconstitutions", 1))
        taux_rec_list = s.get("taux_reconstitutions", [100.0] * n_rec) or [100.0]
        k   = float(s.get("k_securite", 0.20))
        bk  = s["brokage"]; fg = s["frais"]; mg = s["marge"]; rt = s["retrocession"]
        cap = (n_rec + 1) * L

        # Appliquer seuil de stabilisation si branche longue
        seuil_s = float(s.get("seuil_stab", 0.0))
        df = self.df_proj.copy()
        if seuil_s > 0 and self.is_long and "I_reg" in df.columns and "I_surv" in df.columns:
            ratio = df["I_reg"] / df["I_surv"].clip(lower=1e-6)
            mask  = ratio >= (1.0 + seuil_s)
            df["Sprime_ultime_s"] = np.where(mask,
                df["Sprime_ultime"] * df["I_surv"] / df["I_reg"].clip(lower=1e-6),
                df["Sprime_ultime"])
            col = "Sprime_ultime_s"
        else:
            col = "Sprime_ultime"

        df["Ck"] = df.apply(lambda r: min(max(r[col] - D, 0), L) * r["coeff_stab"], axis=1)
        cfs = []
        for _, ch in df.groupby("annee_surv")["Ck"].sum().items():
            if aad: ch = max(ch - aad, 0)
            if aal: ch = min(ch, aal)
            cfs.append(float(min(ch, cap)))

        N   = len(cfs); nz = [c for c in cfs if c > 0]; n_nz = len(nz)
        Pr  = 0.0
        for C_n in cfs:
            for ri, t_r in enumerate(taux_rec_list):
                Pr += (t_r / 100) * min(L, max(C_n - ri * L, 0))
        Pr /= L if L > 0 else 1
        Rec = Pr / (Pr + N) if (Pr + N) > 0 else 0.0

        if n_nz < 3:
            return {"taux_pur_bc":0.0,"taux_technique_bc":0.0,
                    "n_ann_nonzero":n_nz,"rec_bc":Rec,"valide_bc":False}
        tp    = np.mean(cfs) / self.gnpi
        sigma = float(np.std(nz)) / self.gnpi
        tr    = tp + k * sigma
        tt    = (tr * (1 - Rec)) / max(1 - bk - fg - mg - rt, 0.01)
        return {"taux_pur_bc":round(tp,6),"taux_technique_bc":round(tt,6),
                "n_ann_nonzero":n_nz,"rec_bc":round(Rec,6),
                "sigma_bc":round(sigma,6),"valide_bc":True}

    # ── 3. SIMULATION ────────────────────────────────────────────────

    def _sim_scenario(self, s, n_sim=5000):
        D = s["priorite"]; P = s["portee"]
        aad = s.get("AAD"); aal = s.get("AAL")
        n_rec = int(s.get("nb_reconstitutions", 1))
        taux_rec_list = s.get("taux_reconstitutions", [100.0] * n_rec) or [100.0]
        cap   = (n_rec + 1) * P
        alp   = float(s.get("alpha", self.alpha))
        lam   = float(s.get("lambda_", self.lambda_))
        seu   = float(s.get("seuil_modelisation", self.seuil))
        k     = float(s.get("k_securite", 0.20))
        bk    = s["brokage"]; fg = s["frais"]; mg = s["marge"]; rt = s["retrocession"]

        np.random.seed(42)
        charges = []
        for _ in range(n_sim):
            N_sin = np.random.poisson(lam); S = 0.0
            if N_sin > 0:
                U = np.random.uniform(size=N_sin); Sp = seu * (U ** (-1.0/alp))
                ic = np.random.choice(len(self.coeffs), size=N_sin, replace=True)
                for j in range(N_sin):
                    sp = Sp[j]; c = self.coeffs[ic[j]]
                    if sp <= D: si = 0
                    elif sp <= D+P: si = c*(sp-D)
                    else: si = c*P
                    S += si
            ch = S
            if aad: ch = max(ch - aad, 0)
            if aal: ch = min(ch, aal)
            charges.append(min(ch, cap))

        arr = np.array(charges); P0 = np.mean(arr); sig = np.std(arr)
        tp  = P0 / self.gnpi
        tr  = tp + k * (sig / self.gnpi)
        tt  = tr / max(1 - bk - fg - mg - rt, 0.01)
        return {"taux_pur_sim":round(tp,6),"taux_technique_sim":round(tt,6),
                "sigma_sim":round(sig/self.gnpi,6),"valide_sim":True}

    # ── 4. MARKET CURVE ─────────────────────────────────────────────

    def _mkt_scenario(self, s):
        if self.df_mkt is None:
            return {"taux_technique_mkt":0.0,"valide_mkt":False}
        D = s["priorite"]; P = s["portee"]
        bk = s["brokage"]; fg = s["frais"]; mg = s["marge"]; rt = s["retrocession"]
        # Fit power curve ROL = a * x^(-b) sur les données marché disponibles
        try:
            log_x = np.log(self.df_mkt["midpoints"].values)
            log_y = np.log(self.df_mkt["ROLs"].values)
            c = np.polyfit(log_x, log_y, 1)
            a = np.exp(c[1]); b = -c[0]
            if b <= 0:
                return {"taux_technique_mkt":0.0,"valide_mkt":False}
            x_norm = (D + P/2) / self.gnpi
            rol = a * (x_norm ** (-b))
            tp  = rol * P / self.gnpi
            tr  = tp * 1.002
            tt  = tr / max(1 - bk - fg - mg - rt, 0.01)
            return {"taux_technique_mkt":round(tt,6),"valide_mkt":True,
                    "rol":round(rol,6),"a_mkt":round(a,6),"b_mkt":round(b,4)}
        except:
            return {"taux_technique_mkt":0.0,"valide_mkt":False}

    # ── 5. BATCH ────────────────────────────────────────────────────

    def executer_batch(self, n_sim=5000, progress_cb=None):
        self.resultats = []; n = len(self.grille)
        for i, s in enumerate(self.grille):
            if progress_cb: progress_cb(i, n)
            bc  = self._bc_scenario(s)
            sim = self._sim_scenario(s, n_sim)
            mkt = self._mkt_scenario(s)
            row = {**s, **bc, **sim, **mkt}
            # Sélection méthode
            if s["type"] == "travaillante":
                row["taux_retenu"]     = max(bc["taux_technique_bc"], sim["taux_technique_sim"])
                row["methode_retenue"] = "BC" if bc["taux_technique_bc"] >= sim["taux_technique_sim"] else "Sim"
            else:
                mkt_t = mkt["taux_technique_mkt"] if mkt["valide_mkt"] else 0.0
                row["taux_retenu"]     = max(sim["taux_technique_sim"], mkt_t)
                row["methode_retenue"] = "Mkt" if mkt_t >= sim["taux_technique_sim"] and mkt_t > 0 else "Sim"
            row["prime_MAD"] = self.gnpi * row["taux_retenu"]
            self.resultats.append(row)
        return self.resultats

    # ── 6. DATASET ML ───────────────────────────────────────────────

    def construire_dataset(self):
        if not self.resultats: return None
        rows = []
        for r in self.resultats:
            if r.get("taux_retenu", 0) <= 0: continue
            D = r["priorite"]; C = r["portee"]
            aad_v = r.get("AAD") or 0.0; aal_v = r.get("AAL") or 0.0
            bk = r["brokage"]; fg = r["frais"]; mg = r["marge"]; rt = r["retrocession"]
            n_rec = r.get("nb_reconstitutions", 1)
            rows.append({
                "priorite":D,"portee":C,"AAD_val":aad_v,"AAL_val":aal_v,
                "nb_reconstitutions":n_rec,
                "taux_recon_1":r.get("taux_recon_1",100.0),
                "taux_recon_2":r.get("taux_recon_2",0.0),
                "taux_recon_moy":r.get("taux_recon_moy",100.0),
                "brokage":bk,"frais":fg,"marge":mg,"retrocession":rt,
                "k_securite":r.get("k_securite",0.20),
                "seuil_stab":r.get("seuil_stab",0.0),
                "alpha":r.get("alpha",self.alpha),
                "lambda_":r.get("lambda_",self.lambda_),
                "seuil_modelisation":r.get("seuil_modelisation",self.seuil),
                "type_travaillante":1 if r["type"]=="travaillante" else 0,
                "type_cat":1 if r["type"]=="cat" else 0,
                "type_non_trav":1 if r["type"]=="non_travaillante" else 0,
                "ratio_D_GNPI":D/max(self.gnpi,1),
                "ratio_C_GNPI":C/max(self.gnpi,1),
                "ratio_aad_C":aad_v/max(C,1),
                "ratio_aal_C":aal_v/max(C,1),
                "levier_frais":1-bk-fg-mg-rt,
                "cap_sur_GNPI":(n_rec+1)*C/max(self.gnpi,1),
                "taux_pur_bc":r.get("taux_pur_bc",0),
                "taux_technique_bc":r.get("taux_technique_bc",0),
                "taux_pur_sim":r.get("taux_pur_sim",0),
                "taux_technique_sim":r.get("taux_technique_sim",0),
                "taux_technique_mkt":r.get("taux_technique_mkt",0),
                "taux_retenu":r.get("taux_retenu",0),
                "prime_MAD":r.get("prime_MAD",0),
                "tranche_base":r.get("tranche_base",""),
                "type":r["type"],
                "methode_retenue":r.get("methode_retenue",""),
            })
        self.df_ml = pd.DataFrame(rows)
        return self.df_ml

    # ── 7. ENTRAÎNEMENT ML ──────────────────────────────────────────

    def entrainer_modeles(self, target=None):
        target = target or self.TARGET

        if self.df_ml is None or len(self.df_ml) < 10:
            return {"erreur": "Dataset insuffisant (min 10 lignes)"}

        if target not in self.df_ml.columns:
            return {"erreur": f"Variable cible introuvable : {target}"}

        try:
            from sklearn.model_selection import train_test_split
            from sklearn.metrics import mean_absolute_error, mean_squared_error, r2_score
            from sklearn.tree import DecisionTreeRegressor
            from sklearn.ensemble import RandomForestRegressor
        except Exception as e:
            return {"erreur": f"scikit-learn manquant : {e}"}

        # IMPORTANT :
        # Les colonnes de taux sont des résultats actuariels calculés.
        # Elles ne doivent jamais être utilisées comme variables explicatives,
        # sinon le modèle "prédit" un taux à partir d'autres taux déjà calculés.
        # On conserve les taux uniquement comme variables cibles possibles.
        colonnes_exclues = {
            "taux_pur_bc",
            "taux_technique_bc",
            "taux_pur_sim",
            "taux_technique_sim",
            "taux_technique_mkt",
            "taux_retenu",
        }

        feats = [
            f for f in self.FEATURES
            if f in self.df_ml.columns
            and f != target
            and f not in colonnes_exclues
            and "taux" not in f.lower()
        ]

        if not feats:
            return {"erreur": "Aucune variable explicative disponible après exclusion des taux."}

        X = self.df_ml[feats].fillna(0)
        y = self.df_ml[target]

        mask = (y > 0) & np.isfinite(y)
        X = X[mask]
        y = y[mask]

        if len(X) < 10:
            return {"erreur": "Trop peu de scenarios valides"}

        X_tr, X_te, y_tr, y_te = train_test_split(
            X, y, test_size=0.25, random_state=42
        )

        models = {
            "Arbre de decision": DecisionTreeRegressor(
                max_depth=6,
                min_samples_leaf=3,
                random_state=42,
            ),
            "Random Forest": RandomForestRegressor(
                n_estimators=300,
                max_depth=10,
                min_samples_leaf=2,
                random_state=42,
                n_jobs=-1,
            ),
        }

        try:
            from xgboost import XGBRegressor
            models["XGBoost"] = XGBRegressor(
                n_estimators=300,
                max_depth=4,
                learning_rate=0.05,
                subsample=0.85,
                colsample_bytree=0.85,
                objective="reg:squarederror",
                random_state=42,
            )
        except Exception as e:
            self.metriques_ml["XGBoost"] = {"erreur": f"XGBoost indisponible : {e}"}

        try:
            from catboost import CatBoostRegressor
            models["CatBoost"] = CatBoostRegressor(
                iterations=300,
                depth=5,
                learning_rate=0.05,
                loss_function="RMSE",
                random_seed=42,
                verbose=False,
            )
        except Exception as e:
            self.metriques_ml["CatBoost"] = {"erreur": f"CatBoost indisponible : {e}"}

        resultats = dict(self.metriques_ml) if isinstance(self.metriques_ml, dict) else {}
        best_name = None
        best_mae = None

        for nom, model in models.items():
            try:
                model.fit(X_tr, y_tr)
                pred = model.predict(X_te)

                mae = float(mean_absolute_error(y_te, pred))
                rmse = float(np.sqrt(mean_squared_error(y_te, pred)))
                r2 = float(r2_score(y_te, pred))

                resultats[nom] = {
                    "MAE": mae,
                    "RMSE": rmse,
                    "R2": r2,
                    "n_train": len(X_tr),
                    "n_test": len(X_te),
                    "features": len(feats),
                    "taux_en_features": "Non",
                }

                self.modeles_entraines[nom] = model

                if best_mae is None or mae < best_mae:
                    best_mae = mae
                    best_name = nom

            except Exception as e:
                resultats[nom] = {"erreur": str(e)}

        self.metriques_ml = resultats
        self._features_used = feats
        self._best_model_name = best_name

        if best_name and hasattr(self.modeles_entraines.get(best_name), "feature_importances_"):
            imp = pd.Series(
                self.modeles_entraines[best_name].feature_importances_,
                index=feats
            )
            self.importance_vars[best_name] = imp.sort_values(ascending=False)

        return resultats

    # ── 8. PRÉDICTION ───────────────────────────────────────────────

    def predire_taux(self, conditions):
        model = self.modeles_entraines.get(self._best_model_name)
        if model is None: return None
        D = conditions.get("priorite",2e6); C = conditions.get("portee",13e6)
        aad_v = conditions.get("AAD") or 0.0; aal_v = conditions.get("AAL") or 0.0
        bk=conditions.get("brokage",0.10); fg=conditions.get("frais",0.05)
        mg=conditions.get("marge",0.10);  rt=conditions.get("retrocession",0.0)
        t  = conditions.get("type","travaillante")
        n_rec = conditions.get("nb_reconstitutions",1)
        tr1 = conditions.get("taux_recon_1",100.0)
        tr2 = conditions.get("taux_recon_2",0.0)
        row = {
            "priorite":D,"portee":C,"AAD_val":aad_v,"AAL_val":aal_v,
            "nb_reconstitutions":n_rec,"taux_recon_1":tr1,"taux_recon_2":tr2,
            "taux_recon_moy":(tr1+tr2)/2 if n_rec>1 else tr1,
            "brokage":bk,"frais":fg,"marge":mg,"retrocession":rt,
            "k_securite":conditions.get("k_securite",0.20),
            "seuil_stab":conditions.get("seuil_stab",0.0),
            "alpha":conditions.get("alpha",self.alpha),
            "lambda_":conditions.get("lambda_",self.lambda_),
            "seuil_modelisation":conditions.get("seuil_modelisation",self.seuil),
            "type_travaillante":1 if t=="travaillante" else 0,
            "type_cat":1 if t=="cat" else 0,
            "type_non_trav":1 if t=="non_travaillante" else 0,
            "ratio_D_GNPI":D/max(self.gnpi,1),"ratio_C_GNPI":C/max(self.gnpi,1),
            "ratio_aad_C":aad_v/max(C,1),"ratio_aal_C":aal_v/max(C,1),
            "levier_frais":1-bk-fg-mg-rt,
            "cap_sur_GNPI":(n_rec+1)*C/max(self.gnpi,1),
        }
        X = pd.DataFrame([{f: row.get(f,0) for f in self._features_used}])
        return float(model.predict(X)[0])

    # ── 9. OPTIMISATION — DICHOTOMIE ACTUARIELLE ────────────────────
    # Propriété : taux_retenu est monotone décroissant en D (priorité)
    # → bisection sur [D_min, D_max] jusqu'à convergence vers tau_cible

    def optimiser_dichotomie(self, t_base, taux_cible, tolerance=1e-5,
                              max_iter=60, conditions_fixees=None):
        """
        Trouve D* tel que tau(D*) ≈ taux_cible par bisection.
        Basé sur la monotonie : tau decroit quand D augmente.
        """
        if not self.modeles_entraines: return None
        cond = {
            "type":              t_base["type"],
            "portee":            t_base["portee"],
            "AAD":               None,
            "nb_reconstitutions":t_base.get("nb_reconstitutions",1),
            "taux_recon_1":      100.0,"taux_recon_2":0.0,
            "brokage":           t_base["brokage"],
            "frais":             t_base["frais"],
            "marge":             t_base["marge"],
            "retrocession":      t_base["retrocession"],
            "k_securite":        0.20,
            "seuil_stab":        0.0,
            "alpha":             self.alpha,"lambda_":self.lambda_,
            "seuil_modelisation":self.seuil,
        }
        if conditions_fixees: cond.update(conditions_fixees)

        D_min = t_base["priorite"] * 0.3
        D_max = t_base["priorite"] * 4.0

        # Vérifier la monotonie : tau(D_min) > tau(D_max)
        cond["priorite"] = D_min
        tau_lo = self.predire_taux(cond) or 0
        cond["priorite"] = D_max
        tau_hi = self.predire_taux(cond) or 0

        if tau_lo is None or tau_hi is None:
            return None

        # Ajuster les bornes si la cible est hors plage
        if not (min(tau_lo,tau_hi) <= taux_cible <= max(tau_lo,tau_hi)):
            return {"converge":False,"D_star":None,"tau_star":None,
                    "tau_lo":tau_lo,"tau_hi":tau_hi,
                    "message":f"Cible {taux_cible:.4%} hors plage [{min(tau_lo,tau_hi):.4%}, {max(tau_lo,tau_hi):.4%}]"}

        iterations = []
        for _ in range(max_iter):
            D_mid = (D_min + D_max) / 2
            D_mid = round(D_mid / 100_000) * 100_000
            cond["priorite"] = D_mid
            tau_mid = self.predire_taux(cond) or 0
            iterations.append({"D":D_mid,"tau":tau_mid})
            if abs(tau_mid - taux_cible) < tolerance: break
            # tau décroit avec D → si tau_mid > cible, augmenter D_min
            if tau_mid > taux_cible: D_min = D_mid
            else:                    D_max = D_mid

        return {"converge":True,"D_star":D_mid,"tau_star":tau_mid,
                "iterations":iterations,"nb_iter":len(iterations)}

    # ── 10. OPTIMISATION — DE FINETTI / FRONTIÈRE EFFICIENTE ────────
    # De Finetti (1940) : min Var(perte retenue) sous contrainte E[prime]=budget
    # Borch (1960) : optimal XL est celui minimisant la variance résiduelle
    # Approche : balayer (D,C) et calculer Var(perte retenue) vs prime cédée
    # La frontière efficiente = courbe Pareto-optimale dans l'espace (prime, variance)

    def frontiere_de_finetti(self, t_base, budget_prime_pct=None, n_points=40):
        """
        Calcule la frontière efficiente De Finetti pour une tranche.
        Retourne les couples (prime_cedee_pct, variance_retenue_normalisee)
        et identifie le programme optimal selon le critère de De Finetti.

        Le programme optimal minimise Var(retenu) pour un niveau de prime donné.
        Équivalent à : maximiser l'utilité quadratique E[R] - lambda*Var(R).
        """
        if not self.modeles_entraines or self.df_ml is None:
            return []

        D0 = t_base["priorite"]; C0 = t_base["portee"]
        # Grille de (D,C) à évaluer
        D_vals = np.linspace(D0 * 0.4, D0 * 2.5, n_points)
        C_vals = [C0 * m for m in [0.7, 1.0, 1.3]]

        # Calcul de la prime et de la variance pour chaque (D,C)
        # On utilise les simulations disponibles dans df_ml
        results = []
        model = self.modeles_entraines.get(self._best_model_name)
        if model is None: return []

        for C in C_vals:
            for D in D_vals:
                cond = {
                    "type":t_base["type"],"priorite":D,"portee":C,
                    "AAD":None,"nb_reconstitutions":1,
                    "taux_recon_1":100.0,"taux_recon_2":0.0,"taux_recon_moy":100.0,
                    "brokage":t_base["brokage"],"frais":t_base["frais"],
                    "marge":t_base["marge"],"retrocession":t_base["retrocession"],
                    "k_securite":0.20,"seuil_stab":0.0,
                    "alpha":self.alpha,"lambda_":self.lambda_,
                    "seuil_modelisation":self.seuil,
                }
                tau_pred = self.predire_taux(cond)
                if tau_pred is None or tau_pred <= 0: continue

                # Variance retenue approchée (var(X) - 2*Cov(X, ceded) + var(ceded))
                # Simplification : var_retenu ~ var_total * (1 - tau_pred/tau_total)^2
                # tau_total = tau sans aucune rétrocession
                cond_libre = dict(cond); cond_libre["marge"] = 0.0; cond_libre["brokage"] = 0.0
                tau_libre = self.predire_taux(cond_libre) or tau_pred

                prime_pct = tau_pred
                # Approx variance normalisée basée sur le chargement de sécurité
                k_sec = cond["k_securite"]
                sigma_approx = tau_libre / (1 + k_sec) * k_sec  # sigma ≈ tau_pur * k
                var_retenue = max(0, sigma_approx * (1 - prime_pct) ** 2)

                results.append({
                    "D":D,"C":C,"prime_pct":prime_pct,
                    "var_retenue":var_retenue,"tau_pred":tau_pred
                })

        if not results: return []

        # Frontière efficiente : pour chaque niveau de prime, garder le min variance
        df_r = pd.DataFrame(results).sort_values("prime_pct")
        # Pareto frontier
        frontier = []
        min_var = float("inf")
        for _, row in df_r.sort_values("prime_pct", ascending=True).iterrows():
            if row["var_retenue"] < min_var:
                min_var = row["var_retenue"]
                frontier.append(row.to_dict())

        # Programme optimal = meilleur ratio amélioration_variance / prime
        if len(frontier) > 1:
            frontier_df = pd.DataFrame(frontier)
            frontier_df["score_finetti"] = (
                frontier_df["var_retenue"].max() - frontier_df["var_retenue"]
            ) / (frontier_df["prime_pct"] + 1e-10)
            best_idx = frontier_df["score_finetti"].idxmax()
            best     = frontier_df.iloc[best_idx]
        else:
            best = pd.Series(frontier[0]) if frontier else None

        return {
            "frontier": frontier,
            "optimal":  best.to_dict() if best is not None else None,
            "n_points": len(results),
        }

    # ── 11. OPTIMISATION ML AMÉLIORÉE ───────────────────────────────
    # Génère des candidats, prédit, retourne toujours des résultats
    # (soit dans la plage, soit les N plus proches de la cible)

    def optimiser_via_ml(self, tranche_type, taux_min, taux_max, n_candidats=2000):
        model = self.modeles_entraines.get(self._best_model_name)
        if model is None or self.df_ml is None:
            return [], {"erreur":"Modele non entraîné"}

        # Bornes tirées des données observées (+ extrapolation ±40%)
        D_min = float(self.df_ml["priorite"].min()) * 0.6
        D_max = float(self.df_ml["priorite"].max()) * 1.5
        C_min = float(self.df_ml["portee"].min()) * 0.6
        C_max = float(self.df_ml["portee"].max()) * 1.5

        np.random.seed(0)
        D_arr   = np.random.uniform(D_min, D_max, n_candidats)
        C_arr   = np.random.uniform(C_min, C_max, n_candidats)
        aad_arr = np.random.uniform(0, C_arr * 0.20)
        rec_arr = np.random.randint(0, 4, n_candidats)
        tr1_arr = np.random.choice([50.,75.,100.], n_candidats)
        k_arr   = np.random.uniform(0.10, 0.30, n_candidats)
        mg_arr  = np.random.uniform(0.06, 0.16, n_candidats)
        stab_arr = np.random.choice([0.,0.05,0.10,0.20], n_candidats)

        rows = []
        for i in range(n_candidats):
            D = round(D_arr[i]/500_000)*500_000; C = round(C_arr[i]/500_000)*500_000
            aad = round(aad_arr[i]/100_000)*100_000
            n_rec = int(rec_arr[i]); tr1 = float(tr1_arr[i])
            tr2 = 100.0 if n_rec >= 2 else 0.0
            bk=0.10; fg=0.05; mg=float(mg_arr[i]); rt=0.0
            rows.append({
                "priorite":D,"portee":C,"AAD_val":aad,"AAL_val":0,
                "nb_reconstitutions":n_rec,"taux_recon_1":tr1,"taux_recon_2":tr2,
                "taux_recon_moy":(tr1+tr2)/2 if n_rec>1 else tr1,
                "brokage":bk,"frais":fg,"marge":mg,"retrocession":rt,
                "k_securite":float(k_arr[i]),"seuil_stab":float(stab_arr[i]),
                "alpha":self.alpha,"lambda_":self.lambda_,
                "seuil_modelisation":self.seuil,
                "type_travaillante":1 if tranche_type=="travaillante" else 0,
                "type_cat":1 if tranche_type=="cat" else 0,
                "type_non_trav":1 if tranche_type=="non_travaillante" else 0,
                "ratio_D_GNPI":D/max(self.gnpi,1),"ratio_C_GNPI":C/max(self.gnpi,1),
                "ratio_aad_C":aad/max(C,1),"ratio_aal_C":0,
                "levier_frais":1-bk-fg-mg-rt,"cap_sur_GNPI":(n_rec+1)*C/max(self.gnpi,1),
            })

        X     = pd.DataFrame([{f:r.get(f,0) for f in self._features_used} for r in rows])
        preds = model.predict(X)
        info  = {"pred_min":float(np.min(preds)),"pred_max":float(np.max(preds)),
                 "pred_median":float(np.median(preds))}

        # Résultats dans la plage cible
        in_range = [(i,p) for i,p in enumerate(preds) if taux_min <= p <= taux_max]

        if not in_range:
            # Retourner les 15 plus proches de la cible (centre de la plage)
            cible_centre = (taux_min + taux_max) / 2
            closest = sorted(enumerate(preds), key=lambda x: abs(x[1]-cible_centre))[:15]
            in_range = closest
            info["hors_plage"] = True
            info["message"] = (f"Plage cible [{taux_min:.4%},{taux_max:.4%}] absente — "
                               f"plage observée [{info['pred_min']:.4%},{info['pred_max']:.4%}]. "
                               f"Affichage des 15 conditions les plus proches de "
                               f"{cible_centre:.4%}.")

        results = []
        for i, pred in in_range[:20]:
            r = rows[i]
            results.append({
                "Priorite":   f"{r['priorite']:,.0f}",
                "Portee":     f"{r['portee']:,.0f}",
                "AAD":        f"{r['AAD_val']:,.0f}",
                "Reconst.":   int(r["nb_reconstitutions"]),
                "Rec1 %":     f"{r['taux_recon_1']:.0f}%",
                "Rec2 %":     f"{r['taux_recon_2']:.0f}%",
                "Marge":      f"{r['marge']:.2%}",
                "k sec.":     f"{r['k_securite']:.2f}",
                "Stabilit.":  f"{r['seuil_stab']:.0%}",
                "Taux predit":f"{pred:.4%}",
                "Prime":      f"{self.gnpi*pred:,.0f}",
            })
        return results, info

    # ── 12. NSGA-II  ────────────────────────────────────────────────
    # Deb, Pratap, Agarwal & Meyarivan (2002) — IEEE Trans. Evol. Comp.
    # Appliqué à la réassurance XL : Echchelh et al. (2019)
    # Chromosome (par tranche) : [D, C, aad_pct, nb_rec, tr1, k_sec, stab_idx, marge]
    # Objectifs : O1=τ_min, O2=Var(retenu)_min, O3=Protection_max (→ -protection)

    def optimiser_nsga2(self, pop_size=80, n_gen=50,
                        eta_c=20, eta_m=20, multi_tranche=True,
                        progress_cb=None):
        """
        NSGA-II pour l'optimisation multi-objectif du programme XL.
        Retourne : front de Pareto, population finale, log par génération.
        """
        import random
        random.seed(42)
        np.random.seed(42)

        model = self.modeles_entraines.get(self._best_model_name)
        if model is None:
            return {"erreur": "Modèle ML non entraîné (étape 3 requise)"}

        # ── Bornes du problème ────────────────────────────────────────
        tranches = self.tranches_base if multi_tranche else self.tranches_base[:1]
        n_t      = len(tranches)

        STAB_VALS = [0.00, 0.05, 0.06, 0.07, 0.08, 0.09, 0.10, 0.20]
        n_stab    = len(STAB_VALS)

        # Bornes par tranche (8 variables chacune)
        bounds = []
        for t in tranches:
            D0 = t["priorite"]; C0 = t["portee"]
            bounds += [
                (D0 * 0.40, D0 * 2.50),   # D
                (C0 * 0.60, C0 * 2.00),   # C
                (0.00, 0.20),              # aad_pct
                (0, 3),                    # nb_rec (arrondi à l'entier)
                (50.0, 100.0),             # taux_recon_1
                (0.10, 0.30),              # k_securite
                (0, n_stab - 1),           # stab_idx (discret)
                (0.06, 0.15),              # marge
            ]
        n_var = len(bounds)  # 8 × n_tranches

        # ── Évaluation des objectifs ─────────────────────────────────
        def decode(x, t_idx):
            """Décode les 8 variables d'une tranche en dict conditions."""
            base = t_idx * 8
            t    = tranches[t_idx]
            D    = np.clip(x[base],   *bounds[base])
            C    = np.clip(x[base+1], *bounds[base+1])
            aad  = np.clip(x[base+2], *bounds[base+2])
            n_rec= int(round(np.clip(x[base+3], 0, 3)))
            tr1  = np.clip(x[base+4], 50, 100)
            k    = np.clip(x[base+5], *bounds[base+5])
            si   = int(round(np.clip(x[base+6], 0, n_stab-1)))
            mg   = np.clip(x[base+7], *bounds[base+7])
            return {
                "type": t["type"], "priorite": D, "portee": C,
                "AAD": C * aad if aad > 0 else None, "AAL": None,
                "nb_reconstitutions": n_rec,
                "taux_recon_1": tr1,
                "taux_recon_2": 100.0 if n_rec >= 2 else 0.0,
                "taux_recon_moy": tr1 if n_rec <= 1 else (tr1 + 100.0) / 2,
                "brokage": t["brokage"], "frais": t["frais"],
                "marge": mg, "retrocession": t["retrocession"],
                "k_securite": k, "seuil_stab": STAB_VALS[si],
                "alpha": self.alpha, "lambda_": self.lambda_,
                "seuil_modelisation": self.seuil,
            }

        def evaluate(x):
            """Retourne (O1_τ, O2_var, O3_-protection) pour un chromosome."""
            tau_tot = 0.0; var_tot = 0.0; prot_tot = 0.0
            for ti in range(n_t):
                cond = decode(x, ti)
                tau  = self.predire_taux(cond) or 0.0
                tau_tot += tau
                # Var approx : (τ_pur × k)^2 où τ_pur ≈ τ / (1 + k)
                k   = cond["k_securite"]
                tau_pur = tau / (1.0 + k) if (1 + k) > 0 else tau
                var_tot += (tau_pur * k) ** 2
                # Protection = portée × (1 + nb_rec) normalisée
                prot_tot += cond["portee"] * (1 + cond["nb_reconstitutions"]) / max(self.gnpi, 1)
            return np.array([tau_tot, var_tot, -prot_tot])

        # ── Opérateurs génétiques ────────────────────────────────────
        def sbx_crossover(p1, p2):
            """SBX (Simulated Binary Crossover), Deb & Agrawal 1995."""
            c1 = p1.copy(); c2 = p2.copy()
            for i in range(n_var):
                if random.random() > 0.5: continue
                if abs(p1[i] - p2[i]) < 1e-14: continue
                lo, hi = bounds[i]
                u = random.random()
                beta = (2*u)**(1/(eta_c+1)) if u < 0.5 else (1/(2-2*u))**(1/(eta_c+1))
                c1[i] = 0.5*((1+beta)*p1[i] + (1-beta)*p2[i])
                c2[i] = 0.5*((1-beta)*p1[i] + (1+beta)*p2[i])
                c1[i] = np.clip(c1[i], lo, hi)
                c2[i] = np.clip(c2[i], lo, hi)
            return c1, c2

        def poly_mutation(x):
            """Polynomial mutation, Deb 1996."""
            xm = x.copy()
            for i in range(n_var):
                if random.random() > 1.0/n_var: continue
                lo, hi = bounds[i]; rng = hi - lo
                if rng < 1e-14: continue
                u = random.random()
                if u < 0.5:
                    delta = (2*u)**(1/(eta_m+1)) - 1.0
                else:
                    delta = 1.0 - (2-2*u)**(1/(eta_m+1))
                xm[i] = np.clip(x[i] + delta * rng, lo, hi)
            return xm

        # ── Tri non-dominé ───────────────────────────────────────────
        def non_dominated_sort(F):
            """
            Tri non-dominé rapide (Deb et al. 2002).
            F : array (N, M) des valeurs d'objectifs.
            Retourne liste de fronts (indices).
            """
            N = len(F)
            n_dom  = np.zeros(N, dtype=int)   # nb solutions dominant p
            S      = [[] for _ in range(N)]    # solutions dominées par p
            rank   = np.zeros(N, dtype=int)
            fronts = [[]]
            for p in range(N):
                for q in range(N):
                    if p == q: continue
                    if all(F[p] <= F[q]) and any(F[p] < F[q]):
                        S[p].append(q)         # p domine q
                    elif all(F[q] <= F[p]) and any(F[q] < F[p]):
                        n_dom[p] += 1          # q domine p
                if n_dom[p] == 0:
                    rank[p] = 0
                    fronts[0].append(p)
            i = 0
            while fronts[i]:
                nxt = []
                for p in fronts[i]:
                    for q in S[p]:
                        n_dom[q] -= 1
                        if n_dom[q] == 0:
                            rank[q] = i + 1
                            nxt.append(q)
                fronts.append(nxt)
                i += 1
            return fronts[:-1], rank

        def crowding_distance(F, front):
            """Distance de crowding pour un front."""
            n  = len(front)
            cd = np.zeros(n)
            if n <= 2: return np.full(n, np.inf)
            for m in range(F.shape[1]):
                idx_sorted = np.argsort(F[front, m])
                cd[idx_sorted[0]]  = np.inf
                cd[idx_sorted[-1]] = np.inf
                rng = F[front[idx_sorted[-1]], m] - F[front[idx_sorted[0]], m]
                if rng < 1e-14: continue
                for k in range(1, n-1):
                    cd[idx_sorted[k]] += (F[front[idx_sorted[k+1]], m] -
                                          F[front[idx_sorted[k-1]], m]) / rng
            return cd

        def tournament(pop, rank, cd, k=2):
            """Sélection par tournoi binaire (rang + crowding)."""
            candidates = random.sample(range(len(pop)), k)
            best = candidates[0]
            for c in candidates[1:]:
                if (rank[c] < rank[best] or
                   (rank[c] == rank[best] and cd[c] > cd[best])):
                    best = c
            return pop[best].copy()

        def random_individual():
            x = np.zeros(n_var)
            for i, (lo, hi) in enumerate(bounds):
                x[i] = random.uniform(lo, hi)
            return x

        # ── Boucle principale NSGA-II ────────────────────────────────
        pop  = np.array([random_individual() for _ in range(pop_size)])
        Fval = np.array([evaluate(x) for x in pop])

        log_pareto = []  # évolution du front de Pareto

        for gen in range(n_gen):
            if progress_cb: progress_cb(gen, n_gen)

            # Tri + crowding sur population courante
            fronts, rank = non_dominated_sort(Fval)
            cd = np.zeros(len(pop))
            for front in fronts:
                if not front: continue
                cdf = crowding_distance(Fval, front)
                for k2, idx in enumerate(front):
                    cd[idx] = cdf[k2]

            # Génération des enfants (taille pop_size)
            offspring   = []
            offspring_F = []
            while len(offspring) < pop_size:
                p1 = tournament(pop, rank, cd)
                p2 = tournament(pop, rank, cd)
                c1, c2 = sbx_crossover(p1, p2)
                c1 = poly_mutation(c1)
                c2 = poly_mutation(c2)
                for c in [c1, c2]:
                    if len(offspring) < pop_size:
                        offspring.append(c)
                        offspring_F.append(evaluate(c))

            # R = P ∪ Q
            R  = np.vstack([pop, offspring])
            RF = np.vstack([Fval, np.array(offspring_F)])

            # Tri non-dominé sur R, sélectionner les meilleurs pop_size
            fronts_r, rank_r = non_dominated_sort(RF)
            cd_r = np.zeros(len(R))
            for front in fronts_r:
                if not front: continue
                cdf = crowding_distance(RF, front)
                for k2, idx in enumerate(front):
                    cd_r[idx] = cdf[k2]

            next_indices = []
            for front in fronts_r:
                if len(next_indices) + len(front) <= pop_size:
                    next_indices.extend(front)
                else:
                    remaining = pop_size - len(next_indices)
                    sorted_f  = sorted(front, key=lambda i: -cd_r[i])
                    next_indices.extend(sorted_f[:remaining])
                    break

            pop  = R[next_indices]
            Fval = RF[next_indices]

            # Log front de Pareto (rang 0)
            fronts_new, _ = non_dominated_sort(Fval)
            if fronts_new:
                pf = fronts_new[0]
                log_pareto.append({
                    "gen": gen+1,
                    "n_pareto": len(pf),
                    "tau_min":  float(Fval[pf, 0].min()),
                    "var_min":  float(Fval[pf, 1].min()),
                    "prot_max": float(-Fval[pf, 2].max()),
                })

        if progress_cb: progress_cb(n_gen, n_gen)

        # ── Extraction du front de Pareto final ──────────────────────
        fronts_fin, rank_fin = non_dominated_sort(Fval)
        pareto_idx = fronts_fin[0] if fronts_fin else []
        pareto = []
        for idx in pareto_idx:
            x    = pop[idx]
            objs = Fval[idx]
            sol  = {"O1_tau": float(objs[0]),
                    "O2_var": float(objs[1]),
                    "O3_prot":float(-objs[2])}
            for ti, t in enumerate(tranches):
                cond = decode(x, ti)
                sol[f"T{ti+1}_nom"]   = t["nom"]
                sol[f"T{ti+1}_D"]     = round(cond["priorite"])
                sol[f"T{ti+1}_C"]     = round(cond["portee"])
                sol[f"T{ti+1}_aad"]   = round(cond["AAD"]) if cond["AAD"] else 0
                sol[f"T{ti+1}_rec"]   = cond["nb_reconstitutions"]
                sol[f"T{ti+1}_tr1"]   = round(cond["taux_recon_1"])
                sol[f"T{ti+1}_k"]     = round(cond["k_securite"], 2)
                sol[f"T{ti+1}_stab"]  = round(cond["seuil_stab"], 2)
                sol[f"T{ti+1}_marge"] = round(cond["marge"], 3)
            pareto.append(sol)

        return {
            "pareto":    pareto,
            "log":       log_pareto,
            "n_gen":     n_gen,
            "pop_size":  pop_size,
            "n_tranches":n_t,
        }



def _labo_display_section():
    """Laboratoire de tarification ML — affiché dans tab_agent."""
    import matplotlib.pyplot as plt

    st.markdown("---")
    st.markdown("#### Laboratoire de tarification ML")
    st.caption(
        "120 scénarios/tranche · BC + Simulation + Market Curve · RF/DT/XGB · "
        "Optimisation Dichotomie (actuarielle) + De Finetti · Programme multi-tranches"
    )

    if "df_proj" not in st.session_state or "alpha_est" not in st.session_state:
        st.info("Transformez d'abord le triangle (Tab 2).")
        return

    def _make_labo():
        return AgentLaboTarification(
            tranches_base      = tranches_input,
            gnpi               = gnpi,
            df_proj            = st.session_state["df_proj"],
            coeffs             = st.session_state.get("coeffs", np.array([1.0])),
            alpha              = st.session_state.get("alpha_est", 1.5),
            lambda_            = st.session_state.get("lambda_est", 5.0),
            seuil              = st.session_state.get("seuil_est", 1_600_000),
            chargement_majeurs = st.session_state.get("chargement_majeurs", 0.0),
            df_mkt             = st.session_state.get("df_mkt_clean"),
            is_long            = st.session_state.get("is_long_tail", True),
        )

    def _restore_labo(labo):
        """Restaure un labo depuis session_state après un rerun."""
        if "labo_modeles"  in st.session_state: labo.modeles_entraines = st.session_state["labo_modeles"]
        if "labo_features" in st.session_state: labo._features_used    = st.session_state["labo_features"]
        if "labo_best"     in st.session_state: labo._best_model_name  = st.session_state["labo_best"]
        if "labo_df_ml"    in st.session_state: labo.df_ml             = st.session_state["labo_df_ml"]
        return labo

    # ═══════════════════════════════════════════════════════════
    # ÉTAPE 1 — GRILLE
    # ═══════════════════════════════════════════════════════════
    with st.expander("Étape 1 — Grille de conditions (120 scénarios/tranche, modifiable)", expanded=True):
        c1, c2 = st.columns([3, 1])
        with c1:
            n_max = st.slider("Scénarios max par tranche", 30, 150, 120, 10, key="labo_n_max")
        with c2:
            st.markdown("<div style='height:28px'></div>", unsafe_allow_html=True)
            if st.button("Générer la grille", key="btn_labo_gen", use_container_width=True):
                labo = _make_labo()
                grille = labo.generer_grille_auto(n_max_par_tranche=n_max)
                st.session_state["labo_grille"] = grille
                st.rerun()

        if "labo_grille" in st.session_state:
            grille = st.session_state["labo_grille"]
            st.caption(f"{len(grille)} scénarios générés — modifiez directement ci-dessous avant de lancer le batch")

            df_g = pd.DataFrame([{
                "Tranche":    s["tranche_base"],
                "Type":       s["type"],
                "Priorite":   s["priorite"],
                "Portee":     s["portee"],
                "AAD":        s.get("AAD") or 0.0,
                "AAL":        s.get("AAL") or 0.0,
                "Reconst.":   s["nb_reconstitutions"],
                "Rec1 %":     s.get("taux_recon_1", 100.0),
                "Rec2 %":     s.get("taux_recon_2", 0.0),
                "Stab %":     s.get("seuil_stab", 0.0) * 100,
                "Marge":      s["marge"],
                "Frais":      s["frais"],
                "Brokage":    s["brokage"],
                "Retro.":     s["retrocession"],
                "k_sec":      s["k_securite"],
                "Alpha":      s["alpha"],
                "Lambda":     s["lambda_"],
            } for s in grille])

            df_edited = st.data_editor(
                df_g, use_container_width=True, height=300, key="labo_editor",
                column_config={
                    "Priorite": st.column_config.NumberColumn(format="%,.0f"),
                    "Portee":   st.column_config.NumberColumn(format="%,.0f"),
                    "AAD":      st.column_config.NumberColumn(format="%,.0f"),
                    "AAL":      st.column_config.NumberColumn(format="%,.0f"),
                    "Reconst.": st.column_config.NumberColumn(min_value=0, max_value=4, step=1),
                    "Rec1 %":   st.column_config.NumberColumn(min_value=50.0, max_value=100.0, step=25.0,
                                    help="Taux 1ère reconstitution (50-100%)"),
                    "Rec2 %":   st.column_config.NumberColumn(min_value=0.0, max_value=100.0, step=25.0,
                                    help="Taux 2ème reconstitution (0 si pas de 2ème)"),
                    "Stab %":   st.column_config.NumberColumn(min_value=0.0, max_value=20.0, step=1.0,
                                    help="Seuil stabilisation % (0=sans, 5/6/7/8/9/10/20)"),
                    "Marge":    st.column_config.NumberColumn(format="%.3f", min_value=0.0, max_value=0.30, step=0.01),
                    "k_sec":    st.column_config.NumberColumn(format="%.2f", min_value=0.05, max_value=0.50, step=0.05),
                    "Type":     st.column_config.SelectboxColumn(options=["travaillante","cat","non_travaillante"]),
                }
            )

            # Merge edits back into grille
            grille_modif = []
            for i, row in df_edited.iterrows():
                s = dict(grille[i]) if i < len(grille) else dict(grille[-1])
                n_rec = int(row["Reconst."])
                tr1   = float(row["Rec1 %"])
                tr2   = float(row["Rec2 %"])
                tr_list = []
                if n_rec >= 1: tr_list.append(tr1)
                if n_rec >= 2: tr_list.append(tr2 if tr2 > 0 else 100.0)
                if n_rec >= 3: tr_list.extend([100.0] * (n_rec - 2))
                s.update({
                    "tranche_base":        row["Tranche"],
                    "type":                row["Type"],
                    "priorite":            float(row["Priorite"]),
                    "portee":              float(row["Portee"]),
                    "AAD":                 float(row["AAD"]) if row["AAD"] else None,
                    "AAL":                 float(row["AAL"]) if row["AAL"] else None,
                    "nb_reconstitutions":  n_rec,
                    "taux_reconstitution": tr1,
                    "taux_reconstitutions":tr_list,
                    "taux_recon_1":        tr1,
                    "taux_recon_2":        tr2,
                    "taux_recon_moy":      float(np.mean(tr_list)) if tr_list else 100.0,
                    "seuil_stab":          float(row["Stab %"]) / 100.0,
                    "marge":               float(row["Marge"]),
                    "frais":               float(row["Frais"]),
                    "brokage":             float(row["Brokage"]),
                    "retrocession":        float(row["Retro."]),
                    "k_securite":          float(row["k_sec"]),
                    "alpha":               float(row["Alpha"]),
                    "lambda_":             float(row["Lambda"]),
                })
                grille_modif.append(s)
            st.session_state["labo_grille"] = grille_modif

    # ═══════════════════════════════════════════════════════════
    # ÉTAPE 2 — BATCH BC + SIM + MKT
    # ═══════════════════════════════════════════════════════════
    if "labo_grille" in st.session_state:
        with st.expander("Étape 2 — Tarification batch (BC + Simulation + Market Curve)", expanded=True):
            c1, c2 = st.columns([3, 1])
            with c1:
                n_sim_labo = st.number_input("Simulations par scénario", value=5000,
                    step=1000, min_value=1000, key="labo_nsim")
            with c2:
                st.markdown("<div style='height:28px'></div>", unsafe_allow_html=True)
                if st.button("Lancer le batch", type="primary",
                             key="btn_labo_batch", use_container_width=True):
                    labo = _make_labo()
                    labo.grille = st.session_state["labo_grille"]
                    total = len(labo.grille)
                    bar   = st.progress(0, f"0/{total} scénarios...")
                    def _cb(i, n):
                        bar.progress(int((i+1)/n*100), f"{i+1}/{n} scénarios...")
                    res   = labo.executer_batch(n_sim=int(n_sim_labo), progress_cb=_cb)
                    df_ml = labo.construire_dataset()
                    bar.progress(100, "Terminé ✓")
                    st.session_state["labo_resultats"] = res
                    st.session_state["labo_df_ml"]     = df_ml
                    st.rerun()

            if "labo_resultats" in st.session_state:
                res = st.session_state["labo_resultats"]
                n_valides = sum(1 for r in res if r.get("taux_retenu", 0) > 0)
                st.success(f"{len(res)} scénarios tarifés — {n_valides} valides (BC ≥ 3 années non nulles)")

                df_show = pd.DataFrame([{
                    "Tranche":    r["tranche_base"],
                    "Type":       r["type"],
                    "D":          f"{r['priorite']:,.0f}",
                    "C":          f"{r['portee']:,.0f}",
                    "AAD":        f"{(r.get('AAD') or 0):,.0f}",
                    "Rec.":       r["nb_reconstitutions"],
                    "Rec1%":      f"{r.get('taux_recon_1',100):.0f}",
                    "Rec2%":      f"{r.get('taux_recon_2',0):.0f}",
                    "Stab%":      f"{r.get('seuil_stab',0)*100:.0f}",
                    "τ BC":       f"{r.get('taux_technique_bc',0):.4%}",
                    "τ Sim":      f"{r.get('taux_technique_sim',0):.4%}",
                    "τ Mkt":      f"{r.get('taux_technique_mkt',0):.4%}" if r.get("valide_mkt") else "—",
                    "τ Retenu":   f"{r.get('taux_retenu',0):.4%}",
                    "Prime (MAD)":f"{r.get('prime_MAD',0):,.0f}",
                    "Méthode":    r.get("methode_retenue",""),
                } for r in res])
                st.dataframe(df_show, use_container_width=True, height=280)

                try:
                    import io as _io_labo
                    buf = _io_labo.BytesIO()
                    st.session_state["labo_df_ml"].to_excel(buf, index=False, engine="openpyxl")
                    st.download_button("📥 Télécharger le dataset ML (Excel)",
                        data=buf.getvalue(), file_name="labo_dataset_ml.xlsx",
                        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                        key="btn_dl_labo")
                except: pass

    # ═══════════════════════════════════════════════════════════
    # ÉTAPE 3 — ML
    # ═══════════════════════════════════════════════════════════
    if "labo_df_ml" in st.session_state:
        with st.expander("Étape 3 — Entraînement ML (RF / DT / XGB)", expanded=True):
            df_ml = st.session_state["labo_df_ml"]
            n_feat = len(AgentLaboTarification.FEATURES)
            st.caption(
                f"Dataset : {len(df_ml)} lignes · {n_feat} features "
                f"(conditions + taux_recon + seuil_stab + α/λ) · "
                f"Target : τ technique"
            )
            c1, c2 = st.columns([2,1])
            with c1:
                target_choice = st.radio(
                    "Variable cible",
                    ["taux_retenu","taux_technique_bc","taux_technique_sim","taux_technique_mkt"],
                    horizontal=True, key="labo_target")
            with c2:
                st.markdown("<div style='height:28px'></div>", unsafe_allow_html=True)
                if st.button("Entraîner les modèles", type="primary", key="btn_labo_train"):
                    labo = _make_labo(); labo.df_ml = df_ml
                    with st.spinner("Entraînement RF / DT / XGB..."):
                        labo.entrainer_modeles(target=target_choice)
                    st.session_state["labo_modeles"]    = labo.modeles_entraines
                    st.session_state["labo_metriques"]  = labo.metriques_ml
                    st.session_state["labo_importance"] = labo.importance_vars
                    st.session_state["labo_features"]   = labo._features_used
                    st.session_state["labo_best"]       = labo._best_model_name
                    st.rerun()

            if "labo_metriques" in st.session_state:
                best = st.session_state.get("labo_best","")
                tableau_resultats([{
                    "Modèle":     nom,
                    "MAE (pts)":  f"{v.get('MAE',0)*100:.4f}" if "MAE" in v else "—",
                    "RMSE (pts)": f"{v.get('RMSE',0)*100:.4f}" if "RMSE" in v else "—",
                    "R²":         f"{v.get('R2',0):.4f}" if "R2" in v else "—",
                    "N train":    v.get("n_train","—"),
                    "✓ Meilleur": "✅" if nom == best else "",
                } for nom, v in st.session_state["labo_metriques"].items()])

                imp_dict = st.session_state.get("labo_importance", {})
                if imp_dict:
                    best_nom, imp = list(imp_dict.items())[0]
                    fig_imp, ax_imp = plt.subplots(figsize=(8, 4))
                    imp.head(12).plot.barh(ax=ax_imp, color="#2d8a4e", edgecolor="white")
                    ax_imp.set_xlabel("Importance relative")
                    ax_imp.set_title(f"Variables importantes — {best_nom}")
                    ax_imp.invert_yaxis(); ax_imp.grid(alpha=0.2)
                    ax_imp.spines[["top","right"]].set_visible(False)
                    st.pyplot(fig_imp); plt.close()
                    st.caption(
                        "**priorite / portee dominant** → la géométrie de la tranche "
                        "est le premier déterminant du taux.  "
                        "**k_securite / sigma dominant** → la volatilité historique est prépondérante.  "
                        "**seuil_stab dominant** → la stabilisation a un fort impact (branche longue)."
                    )

    # ═══════════════════════════════════════════════════════════
    # ÉTAPE 4 — OPTIMISATION ACTUARIELLE
    # ═══════════════════════════════════════════════════════════
    if "labo_modeles" in st.session_state:
        with st.expander("🎯 Recommandeur de conditions optimales (ML)", expanded=False):
            st.caption(
                "Le modèle ML prédit le taux pour n'importe quelle combinaison de conditions. "
                "Entrez un taux cible et l'outil trouve les conditions qui s'en approchent."
            )
            col_rco1, col_rco2, col_rco3 = st.columns(3)
            with col_rco1:
                t_target_reco = st.number_input("Taux cible (%)", value=3.0, step=0.1,
                    min_value=0.01, key="reco_taux_cible") / 100
                typ_reco = st.selectbox("Type de tranche",
                    ["travaillante","cat","non_travaillante"], key="reco_type")
            with col_rco2:
                t_tol = st.number_input("Tolérance ±(%)", value=0.5, step=0.1,
                    min_value=0.05, key="reco_tolerance") / 100
                n_reco = st.slider("Nb résultats max", 5, 30, 15, key="reco_n")
            with col_rco3:
                st.markdown("<div style='height:28px'></div>", unsafe_allow_html=True)
                if st.button("🔍 Trouver les conditions optimales", type="primary",
                             key="btn_reco_conditions", use_container_width=True):
                    labo_reco = AgentLaboTarification(
                        tranches_base=tranches_input, gnpi=gnpi,
                        df_proj=st.session_state["df_proj"],
                        coeffs=st.session_state.get("coeffs", np.array([1.0])),
                        alpha=st.session_state.get("alpha_est",1.5),
                        lambda_=st.session_state.get("lambda_est",5.0),
                        seuil=st.session_state.get("seuil_est",1_600_000))
                    labo_reco.modeles_entraines  = st.session_state.get("labo_modeles",{})
                    labo_reco._features_used     = st.session_state.get("labo_features",[])
                    labo_reco._best_model_name   = st.session_state.get("labo_best","")
                    results_reco, info_reco = labo_reco.optimiser_via_ml(
                        tranche_type=typ_reco,
                        taux_min=t_target_reco - t_tol,
                        taux_max=t_target_reco + t_tol,
                        n_candidats=3000)
                    st.session_state["reco_results"] = results_reco
                    st.session_state["reco_info"]    = info_reco

            if "reco_results" in st.session_state and st.session_state["reco_results"]:
                info_r = st.session_state.get("reco_info", {})
                if info_r.get("hors_plage"):
                    st.warning(info_r.get("message","Taux cible hors plage — résultats les plus proches affichés"))
                else:
                    st.success(f"✅ {len(st.session_state['reco_results'])} combinaison(s) trouvée(s) près de {t_target_reco:.4%}")
                    st.caption(f"Plage observée : [{info_r.get('pred_min',0):.4%} — {info_r.get('pred_max',0):.4%}]")
                tableau_resultats(st.session_state["reco_results"][:n_reco],
                    "Conditions optimales recommandées par le modèle ML")
                st.caption(
                    "Note : ces conditions sont des prédictions ML — recalculer le BC et la simulation "
                    "avec les paramètres retenus pour valider le taux technique réel."
                )

    # ═══════════════════════════════════════════════════════════════════
    if "labo_modeles" in st.session_state:
        with st.expander(
            "Étape 4 — Optimisation actuarielle (Dichotomie + De Finetti/Borch)", expanded=True
        ):
            st.markdown(
                """
**Méthodes disponibles :**
- **Dichotomie (De Wylder, 1979 / méthode actuarielle)** : τ est monotone décroissant en D → bisection sur [D_min, D_max], convergence en ~50 itérations vers D* tel que τ(D*) = τ_cible. Méthode recommandée par les traités actuariels (Daykin, Pentikäinen & Pesonen, 1994).
- **Frontière De Finetti–Borch (1940/1969)** : minimise Var(perte retenue) pour un budget de prime donné. Borch (1969) prouve que le stop-loss (XL) est optimal pour ce critère. Retourne la courbe Pareto-efficiente et le programme optimal.
- **Programme multi-tranches** : combine les résultats des deux méthodes sur l'ensemble des tranches pour proposer le programme global.
                """
            )

            methode_opt = st.radio(
                "Méthode d'optimisation",
                ["Dichotomie actuarielle", "Frontière De Finetti–Borch", "Programme multi-tranches complet"],
                horizontal=True, key="labo_methode_opt"
            )

            c1, c2, c3 = st.columns(3)
            with c1:
                tranche_opt_idx = st.selectbox(
                    "Tranche de référence",
                    options=list(range(len(tranches_input))),
                    format_func=lambda i: tranches_input[i]["nom"],
                    key="labo_tranche_idx"
                ) if tranches_input else 0
            with c2:
                taux_cible_opt = st.number_input(
                    "Taux cible (%)", value=3.0, step=0.1, min_value=0.1,
                    key="labo_taux_cible") / 100
            with c3:
                budget_pct = st.number_input(
                    "Budget prime max (% GNPI)", value=4.0, step=0.1, min_value=0.1,
                    key="labo_budget_pct") / 100

            if st.button("Lancer l'optimisation", type="primary", key="btn_labo_opt2"):
                labo = _restore_labo(_make_labo())

                if methode_opt == "Dichotomie actuarielle":
                    if not tranches_input:
                        st.error("Aucune tranche définie.")
                    else:
                        t_base = tranches_input[tranche_opt_idx]
                        with st.spinner(f"Dichotomie sur la priorité de '{t_base['nom']}'..."):
                            res_dich = labo.optimiser_dichotomie(t_base, taux_cible_opt)
                        st.session_state["labo_opt_res"] = ("dichotomie", res_dich, t_base)

                elif methode_opt == "Frontière De Finetti–Borch":
                    if not tranches_input:
                        st.error("Aucune tranche définie.")
                    else:
                        t_base = tranches_input[tranche_opt_idx]
                        with st.spinner(f"Calcul frontière efficiente De Finetti pour '{t_base['nom']}'..."):
                            res_finetti = labo.frontiere_de_finetti(
                                t_base, budget_prime_pct=budget_pct, n_points=50)
                        st.session_state["labo_opt_res"] = ("finetti", res_finetti, t_base)

                else:  # multi-tranches
                    with st.spinner("Optimisation du programme complet (toutes tranches)..."):
                        resultats_mt = []
                        for i, t in enumerate(tranches_input):
                            r_d = labo.optimiser_dichotomie(t, taux_cible_opt)
                            r_f = labo.frontiere_de_finetti(t, budget_prime_pct=budget_pct, n_points=30)
                            resultats_mt.append({"tranche":t,"dichotomie":r_d,"finetti":r_f})
                    st.session_state["labo_opt_res"] = ("multi", resultats_mt, None)
                st.rerun()

            # ── Affichage des résultats d'optimisation ──
            if "labo_opt_res" in st.session_state:
                methode_r, res_r, t_r = st.session_state["labo_opt_res"]

                if methode_r == "dichotomie":
                    st.markdown(f"##### Résultat dichotomie — {t_r['nom']}")
                    if res_r is None:
                        st.error("Modèle non entraîné — lancez d'abord l'étape 3.")
                    elif not res_r.get("converge", True) or "message" in res_r:
                        msg = res_r.get("message","Cible hors plage atteignable.")
                        tau_lo = res_r.get("tau_lo",0); tau_hi = res_r.get("tau_hi",0)
                        st.warning(msg)
                        st.info(
                            f"Plage atteignable : [{min(tau_lo,tau_hi):.4%} — {max(tau_lo,tau_hi):.4%}]. "
                            f"Ajustez le taux cible dans cet intervalle."
                        )
                    else:
                        D_star = res_r["D_star"]; tau_star = res_r["tau_star"]
                        nb = res_r.get("nb_iter",0)
                        st.success(
                            f"**D\\* = {D_star:,.0f} MAD** → τ\\* = {tau_star:.4%} "
                            f"(convergé en {nb} itérations)"
                        )
                        tableau_resultats([{
                            "Priorité optimale D*": f"{D_star:,.0f}",
                            "Portée C":             f"{t_r['portee']:,.0f}",
                            "Taux obtenu τ*":       f"{tau_star:.4%}",
                            "Taux cible":           f"{taux_cible_opt:.4%}",
                            "Écart":                f"{abs(tau_star-taux_cible_opt)*100:.4f} pts",
                            "Itérations":           nb,
                            "Prime estimée (MAD)":  f"{gnpi*tau_star:,.0f}",
                        }])
                        # Tracer la convergence
                        iters = res_r.get("iterations",[])
                        if len(iters) > 2:
                            fig_d, ax_d = plt.subplots(figsize=(7,3))
                            ax_d.plot([it["D"] for it in iters],
                                      [it["tau"]*100 for it in iters],
                                      "o-", color="#2d8a4e", ms=4)
                            ax_d.axhline(taux_cible_opt*100, color="red",
                                         ls="--", label=f"Cible {taux_cible_opt:.2%}")
                            ax_d.set_xlabel("Priorité D (MAD)")
                            ax_d.set_ylabel("τ technique (%)")
                            ax_d.set_title("Convergence dichotomie")
                            ax_d.legend(); ax_d.grid(alpha=0.2)
                            st.pyplot(fig_d); plt.close()
                        st.caption(
                            "**Principe (De Wylder / Daykin–Pentikäinen–Pesonen)** : "
                            "τ est monotone décroissant en D (une priorité plus haute → "
                            "moins de sinistres touchent la tranche). "
                            "La bisection converge en O(log((D_max−D_min)/ε)) ≈ 50 itérations."
                        )

                elif methode_r == "finetti":
                    st.markdown(f"##### Frontière De Finetti–Borch — {t_r['nom']}")
                    if not res_r or not res_r.get("frontier"):
                        st.warning("Frontière vide. Vérifiez que le modèle ML est entraîné (étape 3).")
                    else:
                        frontier = res_r["frontier"]
                        optimal  = res_r.get("optimal")
                        fig_f, ax_f = plt.subplots(figsize=(7, 4))
                        xs = [p["prime_pct"]*100 for p in frontier]
                        ys = [p["var_retenue"]*1e4 for p in frontier]
                        ax_f.plot(xs, ys, "o-", color="#2d8a4e", ms=5, label="Frontière efficiente")
                        if optimal:
                            ax_f.scatter([optimal["prime_pct"]*100],
                                         [optimal.get("var_retenue",0)*1e4],
                                         color="red", s=120, zorder=5, label="Programme optimal")
                        ax_f.set_xlabel("Prime cédée (% GNPI)")
                        ax_f.set_ylabel("Variance retenue (×10⁻⁴)")
                        ax_f.set_title(
                            "Frontière efficiente De Finetti–Borch\n"
                            "min Var(retenu) s.c. E[cession] = budget"
                        )
                        ax_f.legend(); ax_f.grid(alpha=0.2)
                        st.pyplot(fig_f); plt.close()

                        if optimal:
                            st.success(
                                f"**Programme De Finetti optimal** : "
                                f"D\\* = {optimal.get('D',0):,.0f} · "
                                f"C = {optimal.get('C',0):,.0f} · "
                                f"τ\\* = {optimal.get('tau_pred',0):.4%}"
                            )
                            tableau_resultats([{
                                "Priorité D*":     f"{optimal.get('D',0):,.0f}",
                                "Portée C":        f"{optimal.get('C',0):,.0f}",
                                "Taux prédit":     f"{optimal.get('tau_pred',0):.4%}",
                                "Prime cédée":     f"{optimal.get('prime_pct',0):.4%}",
                                "Var retenue":     f"{optimal.get('var_retenue',0):.6f}",
                                "Score De Finetti":f"{optimal.get('score_finetti',0):.4f}",
                                "Prime (MAD)":     f"{gnpi*optimal.get('tau_pred',0):,.0f}",
                            }])
                        st.caption(
                            "**Borch (1969)** : pour une prime nette fixée, le stop-loss (XL) "
                            "minimise la variance de la perte retenue. "
                            "Le score De Finetti = Δvariance / prime mesure l'efficacité marginale "
                            "de chaque euro de prime cédée."
                        )

                elif methode_r == "multi":
                    st.markdown("##### Programme multi-tranches — Résultats consolidés")
                    st.caption(
                        "Un programme optimal est composé d'au moins 2 tranches. "
                        "Résultats dichotomie + De Finetti par tranche, puis consolidation."
                    )
                    rows_mt = []
                    prime_totale = 0.0
                    for item in res_r:
                        t = item["tranche"]
                        rd = item.get("dichotomie") or {}
                        rf = item.get("finetti") or {}
                        opt_f = rf.get("optimal") or {}
                        tau_d = rd.get("tau_star", 0) if rd.get("converge", False) else None
                        tau_f = opt_f.get("tau_pred", 0)
                        tau_retenu = tau_d or tau_f
                        prime_totale += gnpi * (tau_retenu or 0)
                        rows_mt.append({
                            "Tranche":          t["nom"],
                            "Type":             t["type"],
                            "D* Dich.":         f"{rd.get('D_star',0):,.0f}" if rd.get("converge") else "—",
                            "τ* Dich.":         f"{tau_d:.4%}" if tau_d else "—",
                            "D* De Finetti":    f"{opt_f.get('D',0):,.0f}" if opt_f else "—",
                            "τ* De Finetti":    f"{tau_f:.4%}" if tau_f else "—",
                            "τ Retenu":         f"{tau_retenu:.4%}" if tau_retenu else "—",
                            "Prime (MAD)":      f"{gnpi*(tau_retenu or 0):,.0f}",
                        })
                    tableau_resultats(rows_mt)
                    st.metric("Prime totale programme", f"{prime_totale:,.0f} MAD",
                              f"{prime_totale/gnpi:.4%} du GNPI")
                    st.caption(
                        "Le programme multi-tranches consolide la protection : "
                        "T1 travaillante (max BC/Sim) + T2/T3 cat (max Sim/Mkt). "
                        "La protection globale = somme des portées × (1 + reconstitutions)."
                    )

    # ═══════════════════════════════════════════════════════════
    # ÉTAPE 5 — NSGA-II  (Deb, Pratap, Agarwal & Meyarivan, 2002)
    # ═══════════════════════════════════════════════════════════
    if "labo_modeles" in st.session_state:
        with st.expander(
            "Étape 5 — NSGA-II : Optimisation multi-objectif (Front de Pareto)",
            expanded=False
        ):
            st.markdown(
                """
**NSGA-II** (*Non-dominated Sorting Genetic Algorithm II*, Deb et al. 2002)  
Algorithme évolutionnaire qui explore simultanément les **3 objectifs actuariels** :

| Objectif | Sens | Signification |
|---|---|---|
| **O1** τ_technique | Minimiser | Coût du programme (prime/GNPI) |
| **O2** Var(retenu) | Minimiser | Risque résiduel ≈ (τ_pur × k)² |
| **O3** Protection | Maximiser | Portée × (1+Rec) / GNPI |

**Opérateurs :** SBX crossover (η=20) + Mutation polynomiale (η=20) — Echchelh et al. (2019) confirme 98% de l'hypervolume Pareto en 20 générations pour des traités XL.
                """
            )
            c1, c2, c3, c4 = st.columns(4)
            with c1:
                nsga_pop  = st.number_input("Taille population", value=80, step=20,
                    min_value=20, max_value=200, key="nsga_pop")
            with c2:
                nsga_gen  = st.number_input("Générations", value=40, step=10,
                    min_value=10, max_value=200, key="nsga_gen")
            with c3:
                nsga_eta_c = st.number_input("η croisement (SBX)", value=20, step=5,
                    min_value=5, max_value=50, key="nsga_eta_c")
            with c4:
                nsga_multi = st.checkbox("Multi-tranches", value=True, key="nsga_multi",
                    help="Optimise toutes les tranches simultanément (chromosome global)")

            if st.button("Lancer NSGA-II", type="primary", key="btn_nsga2"):
                labo = _restore_labo(_make_labo())
                bar_nsga = st.progress(0, "Initialisation population...")
                def _nsga_cb(gen, n):
                    bar_nsga.progress(
                        int(gen/n*100),
                        f"Génération {gen}/{n} — convergence en cours..."
                    )
                with st.spinner("NSGA-II en cours..."):
                    result = labo.optimiser_nsga2(
                        pop_size    = int(nsga_pop),
                        n_gen       = int(nsga_gen),
                        eta_c       = int(nsga_eta_c),
                        eta_m       = int(nsga_eta_c),
                        multi_tranche = nsga_multi,
                        progress_cb = _nsga_cb,
                    )
                bar_nsga.progress(100, "Terminé ✓")
                st.session_state["nsga_result"] = result

            if "nsga_result" in st.session_state:
                result = st.session_state["nsga_result"]

                if "erreur" in result:
                    st.error(result["erreur"])
                else:
                    pareto = result["pareto"]
                    logp   = result["log"]
                    n_t    = result["n_tranches"]

                    st.success(
                        f"**{len(pareto)} solutions Pareto** trouvées en "
                        f"{result['n_gen']} générations · "
                        f"{result['pop_size']} individus · "
                        f"{n_t} tranche(s)"
                    )

                    # ── Graphiques 3D Pareto ──
                    col_a, col_b = st.columns(2)
                    import matplotlib.pyplot as plt

                    with col_a:
                        # O1 vs O2
                        fig1, ax1 = plt.subplots(figsize=(5, 4))
                        o1 = [p["O1_tau"]*100 for p in pareto]
                        o2 = [p["O2_var"]*1e4  for p in pareto]
                        sc = ax1.scatter(o1, o2, c=o1, cmap="RdYlGn_r", s=60, edgecolors="k", lw=0.4)
                        plt.colorbar(sc, ax=ax1, label="τ (%)")
                        ax1.set_xlabel("O1 : τ_technique (%)")
                        ax1.set_ylabel("O2 : Variance retenue (×10⁻⁴)")
                        ax1.set_title("Front de Pareto — Coût vs Risque")
                        ax1.grid(alpha=0.2)
                        st.pyplot(fig1); plt.close()

                    with col_b:
                        # O1 vs O3
                        fig2, ax2 = plt.subplots(figsize=(5, 4))
                        o3 = [p["O3_prot"]*100 for p in pareto]
                        sc2 = ax2.scatter(o1, o3, c=o3, cmap="Blues", s=60, edgecolors="k", lw=0.4)
                        plt.colorbar(sc2, ax=ax2, label="Protection (%)")
                        ax2.set_xlabel("O1 : τ_technique (%)")
                        ax2.set_ylabel("O3 : Protection nette (% GNPI)")
                        ax2.set_title("Front de Pareto — Coût vs Protection")
                        ax2.grid(alpha=0.2)
                        st.pyplot(fig2); plt.close()

                    # ── Convergence ──
                    if logp:
                        fig3, axes = plt.subplots(1, 3, figsize=(12, 3))
                        gens = [l["gen"] for l in logp]
                        for ax3, key, label, color in zip(
                            axes,
                            ["tau_min", "var_min", "prot_max"],
                            ["τ min (%)", "Var min (×10⁻⁴)", "Protection max (%)"],
                            ["#e74c3c", "#3498db", "#2ecc71"]
                        ):
                            vals = [l[key] * (100 if "tau" in key or "prot" in key else 1e4)
                                    for l in logp]
                            ax3.plot(gens, vals, color=color, lw=2)
                            ax3.set_xlabel("Génération")
                            ax3.set_ylabel(label)
                            ax3.set_title(label)
                            ax3.grid(alpha=0.2)
                        fig3.tight_layout()
                        st.pyplot(fig3); plt.close()

                    # ── Tableau du front de Pareto ──
                    st.markdown("##### Solutions Pareto — détail par tranche")
                    # Construire les colonnes dynamiquement selon n_tranches
                    rows_p = []
                    for sol in sorted(pareto, key=lambda p: p["O1_tau"]):
                        row = {
                            "τ total":  f"{sol['O1_tau']:.4%}",
                            "Var":      f"{sol['O2_var']:.2e}",
                            "Prot %":   f"{sol['O3_prot']*100:.1f}",
                            "Prime (MAD)": f"{gnpi*sol['O1_tau']:,.0f}",
                        }
                        for ti in range(n_t):
                            p = f"T{ti+1}"
                            row[f"{p} D"]     = f"{sol.get(p+'_D',0):,.0f}"
                            row[f"{p} C"]     = f"{sol.get(p+'_C',0):,.0f}"
                            row[f"{p} Rec"]   = sol.get(p+"_rec", 0)
                            row[f"{p} Marge"] = f"{sol.get(p+'_marge',0):.2%}"
                        rows_p.append(row)
                    if rows_p:
                        tableau_resultats(rows_p[:30])

                    # ── Solution compromis (TOPSIS simplifié) ──
                    # Normalise les 3 objectifs et choisit le point le plus proche de l'idéal
                    if len(pareto) >= 2:
                        O = np.array([[p["O1_tau"], p["O2_var"], -p["O3_prot"]] for p in pareto])
                        O_norm = (O - O.min(0)) / (O.max(0) - O.min(0) + 1e-12)
                        ideal  = np.zeros(3)   # objectifs normalisés minimaux
                        dists  = np.linalg.norm(O_norm - ideal, axis=1)
                        best   = pareto[int(np.argmin(dists))]
                        st.markdown("##### Solution compromis (TOPSIS — équilibre coût/risque/protection)")
                        comp_rows = [{
                            "τ total":     f"{best['O1_tau']:.4%}",
                            "Var retenue": f"{best['O2_var']:.2e}",
                            "Protection":  f"{best['O3_prot']*100:.1f}%",
                            "Prime (MAD)": f"{gnpi*best['O1_tau']:,.0f}",
                        }]
                        for ti in range(n_t):
                            p = f"T{ti+1}"
                            comp_rows[0][f"{p} D*"]    = f"{best.get(p+'_D',0):,.0f}"
                            comp_rows[0][f"{p} C"]     = f"{best.get(p+'_C',0):,.0f}"
                            comp_rows[0][f"{p} AAD"]   = f"{best.get(p+'_aad',0):,.0f}"
                            comp_rows[0][f"{p} Rec"]   = best.get(p+"_rec", 0)
                            comp_rows[0][f"{p} Rec1%"] = best.get(p+"_tr1", 100)
                            comp_rows[0][f"{p} k"]     = best.get(p+"_k", 0.20)
                            comp_rows[0][f"{p} Stab"]  = f"{best.get(p+'_stab',0):.0%}"
                            comp_rows[0][f"{p} Marge"] = f"{best.get(p+'_marge',0):.2%}"
                        tableau_resultats(comp_rows)
                        st.caption(
                            "**TOPSIS** (Hwang & Yoon, 1981) : solution la plus proche du point "
                            "idéal normalisé (τ=0, Var=0, Protection=max). "
                            "Représente le meilleur compromis coût/risque/protection du front de Pareto."
                        )
