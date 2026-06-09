""" 
Atlantic Re IA — Agent Python pur
AgentActuarielPython : pipeline complet BC→Sim→Mkt→Rapport→Variantes,
100%% Python sans LLM, fonctionne hors ligne.
"""
import numpy as np
import pandas as pd
from datetime import datetime
from modules.optimization import _lookup_taux, _lookup_result, _json_safe

# ════════════════════════════════════════════
# AGENT PYTHON PUR — LOGIQUE ACTUARIELLE CODÉE
# ════════════════════════════════════════════

class AgentActuarielPython:
    """
    Agent de tarification 100% Python — aucun LLM, aucune API.
    Logique actuarielle codée explicitement. Fonctionne hors ligne.
    """

    def __init__(self, tranches, gnpi, df_proj, coeffs,
                 alpha_est, lambda_est, seuil_est, Pm_proxy,
                 chargement_majeurs, df_mkt_clean=None):
        self.tranches           = tranches
        self.gnpi               = gnpi
        self.df_proj            = df_proj
        self.coeffs             = coeffs
        self.alpha              = alpha_est
        self.lambda_            = lambda_est
        self.seuil              = seuil_est
        self.Pm_proxy           = Pm_proxy
        self.chargement_majeurs = chargement_majeurs
        self.df_mkt             = df_mkt_clean
        self.log                = []   # journal des décisions
        self.anomalies          = []   # alertes détectées
        self.resultats_bc       = []
        self.resultats_sim      = []
        self.resultats_mkt      = []
        self.rapport_rows       = []
        self.prime_totale       = 0.0

    # ────────────────────────────────────────────
    def _log(self, etape, decision, detail=""):
        self.log.append({"etape": etape, "decision": decision, "detail": detail})

    def _alerte(self, niveau, message):
        """niveau: INFO / WARN / CRITIQUE"""
        icone = {"INFO": "ℹ️", "WARN": "⚠️", "CRITIQUE": "🚨"}.get(niveau, "ℹ️")
        self.anomalies.append({"niveau": niveau, "icone": icone, "message": message})

    # ────────────────────────────────────────────
    # ÉTAPE 1 — VALIDATION DES PARAMÈTRES
    # ────────────────────────────────────────────
    def etape_0_validation(self):
        self._log("Validation", "Vérification des paramètres actuariels")

        # Alpha
        if self.alpha < 0.8:
            self._alerte("CRITIQUE", f"Alpha = {self.alpha:.4f} < 0.8 — queue trop lourde, résultats suspects")
        elif self.alpha > 4.0:
            self._alerte("WARN", f"Alpha = {self.alpha:.4f} > 4.0 — distribution proche normale, vérifier la modélisation")
        else:
            self._log("Alpha", f"OK — {self.alpha:.4f} dans la plage [0.8, 4.0]")

        # Lambda
        if self.lambda_ < 0.5:
            self._alerte("WARN", f"Lambda = {self.lambda_:.4f} très faible — fréquence quasi nulle au-dessus du seuil")
        elif self.lambda_ > 50:
            self._alerte("WARN", f"Lambda = {self.lambda_:.4f} très élevé — vérifier le seuil de modélisation")
        else:
            self._log("Lambda", f"OK — {self.lambda_:.4f} sinistres/an au-dessus du seuil")

        # Programme
        trav = [t for t in self.tranches if t["type"] == "travaillante"]
        cat  = [t for t in self.tranches if t["type"] == "cat"]
        if not trav:
            self._alerte("WARN", "Aucune tranche travaillante dans le programme")
        if not cat:
            self._alerte("INFO", "Aucune tranche cat — market curve non applicable")
        self._log("Programme", f"{len(trav)} travaillante(s), {len(cat)} cat")

    # ────────────────────────────────────────────
    # ÉTAPE 2 — BURNING COST
    # ────────────────────────────────────────────
    def etape_1_burning_cost(self):
        self._log("Burning Cost", "Calcul BC individuel par sinistre, agrégation annuelle")
        resultats = []
        for t_info in self.tranches:
            D   = t_info["priorite"];  L  = t_info["portee"]
            aal = t_info["AAL"];       aad = t_info["AAD"]
            n_rec = t_info["nb_reconstitutions"]
            taux_rec_list = t_info.get("taux_reconstitutions",
                            [t_info.get("taux_reconstitution", 100)] * n_rec)
            cap = (n_rec + 1) * L

            # Charge annuelle
            df_p = self.df_proj.copy()
            df_p["Ck"] = df_p.apply(
                lambda row: min(max(row["Sprime_ultime"] - D, 0), L) * row["coeff_stab"], axis=1)
            charges_ann = df_p.groupby("annee_surv")["Ck"].sum()
            charges_finales = []
            for ann, ch in charges_ann.items():
                if aad: ch = max(ch - aad, 0)
                if aal: ch = min(ch, aal)
                charges_finales.append({"annee": int(ann), "charge": float(min(ch, cap))})

            df_ch = pd.DataFrame(charges_finales); N = len(df_ch)
            charges_nonzero = [c["charge"] for c in charges_finales if c["charge"] > 0]
            n_nz = len(charges_nonzero)

            # Reconstitutions individuelles
            Pr_Rec = 0.0
            for C_n in df_ch["charge"].values:
                for r_idx, t_r_i in enumerate(taux_rec_list):
                    Pr_Rec += (t_r_i / 100) * min(L, max(C_n - r_idx * L, 0))
            Pr_Rec /= L if L > 0 else 1
            Rec = Pr_Rec / (Pr_Rec + N) if (Pr_Rec + N) > 0 else 0.0

            # R2 — données insuffisantes
            if n_nz < 3:
                tp = tr = tt = sigma = 0.0
                self._alerte("WARN",
                    f"{t_info['nom']} : BC = 0 — seulement {n_nz} année(s) non nulle(s) (règle R2 : min 3 requis)")
            else:
                charge_moy = df_ch["charge"].mean()
                tp    = charge_moy / self.gnpi
                sigma = float(np.std(charges_nonzero)) / self.gnpi
                tr    = tp + sigma * 0.20   # R1
                tt    = (tr * (1 - Rec)) / max(
                    1 - t_info["brokage"] - t_info["frais"] - t_info["marge"] - t_info["retrocession"],
                    0.01)

            resultats.append({
                "tranche": t_info["nom"], "type": t_info["type"],
                "charge_moy": df_ch["charge"].mean() if n_nz >= 3 else 0.0,
                "n_ann_nonzero": n_nz, "sigma_hist": round(sigma if n_nz >= 3 else 0.0, 6),
                "Pr_Rec": round(Pr_Rec, 6), "Rec": round(Rec, 6),
                "taux_pur": round(tp, 6), "taux_risque": round(tr, 6),
                "taux_technique": round(tt, 6),
                "chargement_majeurs": round(self.chargement_majeurs, 6),
                "detail_annuel": charges_finales
            })
            self._log("BC", f"{t_info['nom']}: τ_pur={tp:.4%} τ_tech={tt:.4%} Rec={Rec:.4%} ({n_nz} ans non nuls)")

        self.resultats_bc = resultats
        return resultats

    # ────────────────────────────────────────────
    # ÉTAPE 3 — SIMULATION
    # ────────────────────────────────────────────
    def etape_2_simulation(self, n_sim=10000):
        self._log("Simulation", f"Pareto(α={self.alpha:.4f}) × Poisson(λ={self.lambda_:.4f}) — {n_sim:,} simulations")
        np.random.seed(42)
        resultats = []
        for t_info in self.tranches:
            D = t_info["priorite"]; P = t_info["portee"]
            r = t_info["nb_reconstitutions"]
            aal = t_info["AAL"]; aad = t_info["AAD"]
            cap = (r + 1) * P

            def simuler(avec_aal, avec_aad, avec_rec):
                charges = []
                for _ in range(n_sim):
                    N_sin = np.random.poisson(self.lambda_)
                    S_tot = 0.0
                    if N_sin > 0:
                        U  = np.random.uniform(size=N_sin)
                        Sp = self.seuil * (U ** (-1 / self.alpha))
                        ic = np.random.choice(len(self.coeffs), size=N_sin, replace=True)
                        for k in range(N_sin):
                            s = Sp[k]; c = self.coeffs[ic[k]]
                            if   s <= D:     S_i = 0
                            elif s <= D + P: S_i = c * (s - D)
                            else:            S_i = c * P
                            S_tot += S_i
                    ch = S_tot
                    if avec_aad and aad: ch = max(ch - aad, 0)
                    if avec_aal and aal: ch = min(ch, aal)
                    charges.append(min(ch, cap) if avec_rec else ch)
                return np.array(charges)

            def calc(ch):
                P0 = np.mean(ch); sig = np.std(ch)
                tp = P0 / self.gnpi
                tr = (P0 + 0.2 * sig) / self.gnpi
                tt = tr / max(1 - t_info["brokage"] - t_info["frais"] -
                              t_info["marge"] - t_info["retrocession"], 0.01)
                return round(tp,6), round(tr,6), round(tt,6)

            c_base = simuler(True,  True,  True)
            c_saal = simuler(False, True,  True)
            c_saad = simuler(True,  False, True)
            c_srec = simuler(True,  True,  False)
            tp,tr,tt   = calc(c_base)
            _,_,tt_aal = calc(c_saal)
            _,_,tt_aad = calc(c_saad)
            _,_,tt_rec = calc(c_srec)

            resultats.append({
                "tranche": t_info["nom"], "type": t_info["type"],
                "taux_pur": tp, "taux_risque": tr, "taux_technique": tt,
                "chargement_majeurs": round(self.chargement_majeurs, 6),
                "sans_aal": tt_aal, "sans_aad": tt_aad, "sans_rec": tt_rec,
                "impact_aal": round(tt_aal - tt, 6),
                "impact_aad": round(tt_aad - tt, 6),
                "impact_rec": round(tt_rec - tt, 6),
            })
            self._log("Sim", f"{t_info['nom']}: τ_pur={tp:.4%} τ_tech={tt:.4%}")

        self.resultats_sim = resultats
        return resultats

    # ────────────────────────────────────────────
    # ÉTAPE 4 — DÉTECTION ANOMALIES BC vs SIM
    # ────────────────────────────────────────────
    def etape_3_controles(self):
        self._log("Contrôles", "Vérification cohérence BC / Simulation")
        bc_map  = {r["tranche"]: r for r in self.resultats_bc}
        sim_map = {r["tranche"]: r for r in self.resultats_sim}
        for t in self.tranches:
            nom   = t["nom"]
            bc_tt = bc_map.get(nom, {}).get("taux_technique", 0)
            si_tt = sim_map.get(nom, {}).get("taux_technique", 0)
            if t["type"] == "travaillante" and bc_tt > 0 and si_tt > 0:
                ecart = abs(bc_tt - si_tt) / bc_tt
                if ecart > 0.50:
                    self._alerte("CRITIQUE",
                        f"{nom}: écart BC/Sim = {ecart:.0%} > 50% — anomalie majeure, vérifier les données")
                elif ecart > 0.30:
                    self._alerte("WARN",
                        f"{nom}: écart BC/Sim = {ecart:.0%} > 30% — simulation retenue (méthode conservative)")
                else:
                    self._log("Contrôle BC/Sim", f"{nom}: écart = {ecart:.0%} ✅")
            if t["type"] == "cat" and bc_tt == 0:
                self._log("Cat BC=0", f"{nom}: normal — tranche cat sans sinistres historiques au-dessus de la priorité")

    # ────────────────────────────────────────────
    # ÉTAPE 5 — MARKET CURVE (cat uniquement)
    # ────────────────────────────────────────────
    def etape_4_market_curve(self, r2_min=0.40):
        cat_tranches = [t for t in self.tranches if t["type"] != "travaillante"]
        if not cat_tranches:
            self._log("Market Curve", "Aucune tranche cat — market curve non applicable")
            self.resultats_mkt = []
            return []
        if self.df_mkt is None:
            self._alerte("INFO", "Données marché non fournies — market curve ignorée")
            self.resultats_mkt = []
            return []

        self._log("Market Curve", f"Ajustement ROL = a × x^(-b) sur {len(self.df_mkt)} points — cat uniquement")

        def fit_power(x, y):
            lx = np.log(x); ly = np.log(y)
            c  = np.polyfit(lx, ly, 1)
            a  = np.exp(c[1]); b = -c[0]
            ly_pred = np.polyval(c, lx)
            r2 = 1 - np.sum((ly-ly_pred)**2) / (np.sum((ly-ly.mean())**2) + 1e-10)
            return a, b, r2

        def calc_taux_cat(t, a, b):
            x   = (t["priorite"] + t["portee"] / 2) / self.gnpi
            rol = a * (x ** (-b))
            tp  = rol * t["portee"] / self.gnpi
            tr  = tp * 1.002
            tt  = tr / max(1 - t["brokage"] - t["frais"] - t["marge"] - t["retrocession"], 0.01)
            return {"tranche": t["nom"], "type": t["type"], "x_norm": round(x,6),
                    "rol": round(rol,6), "taux_pur": round(tp,6),
                    "taux_tech": round(tt,6), "taux": round(tt,6),
                    "chargement_majeurs": round(self.chargement_majeurs,6)}

        best = None
        for q in [0.40, 0.60, 0.80, 1.0, 0.20]:
            mq   = np.quantile(self.df_mkt["midpoints"], q)
            df_q = self.df_mkt[self.df_mkt["midpoints"] <= mq]
            if len(df_q) < 8: continue
            try:
                a, b, r2 = fit_power(df_q["midpoints"].values, df_q["ROLs"].values)
                if b <= 0: continue
                tts = [calc_taux_cat(t, a, b) for t in cat_tranches]
                if any(tt["taux"] <= 0 for tt in tts): continue
                # Vérification cohérence ROL : tranche plus basse = ROL plus élevé
                if len(tts) >= 2:
                    rols = [tt["rol"] for tt in tts]
                    if rols != sorted(rols, reverse=True):
                        self._alerte("INFO", f"Q{int(q*100)}: hiérarchie ROL non respectée — ajustement écarté")
                        continue
                score = r2 + (0.3 if r2 >= r2_min else 0) + 0.01 * len(df_q)
                if best is None or score > best["score"]:
                    best = {"a": a, "b": b, "r2": r2, "n": len(df_q),
                            "quantile": q, "taux_tranches": tts, "score": score}
            except: continue

        if best is None:
            self._alerte("CRITIQUE", "Aucun ajustement market curve valide — taux marché = 0 pour les tranches cat")
            self.resultats_mkt = []
            return []

        if best["r2"] < r2_min:
            self._alerte("WARN", f"R² = {best['r2']:.3f} < {r2_min} — market curve de faible qualité, simultion prioritaire")
        else:
            self._log("Market Curve", f"R²={best['r2']:.3f} N={best['n']} a={best['a']:.5f} b={best['b']:.4f} ✅")

        # Compléter avec taux=0 pour les tranches travaillantes
        all_tts = []
        cat_map = {tt["tranche"]: tt for tt in best["taux_tranches"]}
        for t in self.tranches:
            if t["nom"] in cat_map:
                all_tts.append(cat_map[t["nom"]])
            else:
                all_tts.append({"tranche": t["nom"], "type": t["type"],
                                 "x_norm":0, "rol":0, "taux_pur":0,
                                 "taux_tech":0, "taux":0, "chargement_majeurs":0})
        self.resultats_mkt = all_tts
        return all_tts

    # ────────────────────────────────────────────
    # ÉTAPE 6 — RAPPORT FINAL + SÉLECTION MÉTHODE
    # ────────────────────────────────────────────
    def etape_5_rapport(self):
        self._log("Rapport", "Sélection méthode : max(BC,Sim) trav. | max(Sim,Mkt) cat")
        bc_map  = {r["tranche"]: r for r in self.resultats_bc}
        sim_map = {r["tranche"]: r for r in self.resultats_sim}
        mkt_map = {r["tranche"]: r["taux"] for r in self.resultats_mkt}
        rows = []; pt = 0.0
        for idx_t, t in enumerate(self.tranches):
            nom   = t["nom"]
            bc_tt = _lookup_taux(self.resultats_bc,  nom, idx_t, "taux_technique")
            si_tt = _lookup_taux(self.resultats_sim, nom, idx_t, "taux_technique")
            mkt   = mkt_map.get(nom, 0.0) if t["type"] != "travaillante" else 0.0
            if t["type"] == "travaillante":
                taux = max(bc_tt, si_tt)
                meth = f"max(BC={bc_tt:.4%}, Sim={si_tt:.4%}) → {'BC' if bc_tt >= si_tt else 'Sim'}"
            else:
                taux = max(si_tt, mkt)
                meth = f"max(Sim={si_tt:.4%}, Mkt={mkt:.4%}) → {'Mkt' if mkt >= si_tt else 'Sim'}"
            prime = self.gnpi * taux; pt += prime
            ecart = abs(bc_tt - si_tt) / bc_tt * 100 if bc_tt > 0 else 0
            rows.append({
                "tranche": nom, "type": t["type"],
                "taux_bc": round(bc_tt,6), "taux_sim": round(si_tt,6),
                "taux_mkt": round(mkt,6), "taux_retenu": round(taux,6),
                "methode": meth, "prime_MAD": round(prime,2),
                "ecart_bc_sim_pct": round(ecart,1)
            })
            self._log("Sélection", f"{nom}: {meth} | prime={prime:,.0f} MAD")
        self.rapport_rows = rows
        self.prime_totale = pt
        return rows, pt
    def _calibrer_elasticites(self):
        """
        Calibre les élasticités log-log depuis df_ml.
        Remplace les constantes arbitraires 0.6 / 0.35 / 0.3
        par des valeurs estimées sur les scénarios réels.
        """
        if self.df_ml is None or len(self.df_ml) < 10:
            return {
                "e_portee": 0.60,
                "e_priorite": 0.35,
                "e_recon": 0.30,
                "calibre": False,
            }
    
        import numpy as np
    
        df = self.df_ml.copy()
        df = df[
            (df["taux_retenu"] > 0)
            & (df["priorite"] > 0)
            & (df["portee"] > 0)
        ]
    
        if len(df) < 10:
            return {
                "e_portee": 0.60,
                "e_priorite": 0.35,
                "e_recon": 0.30,
                "calibre": False,
            }
    
        log_tau = np.log(df["taux_retenu"])
        log_C = np.log(df["portee"])
        log_D = np.log(df["priorite"])
        log_rec = np.log(df["nb_reconstitutions"] + 1)
    
        X_ols = np.column_stack([
            np.ones(len(df)),
            log_C,
            log_D,
            log_rec,
        ])
    
        try:
            beta, _, _, _ = np.linalg.lstsq(X_ols, log_tau, rcond=None)
    
            e_portee = float(beta[1])
            e_priorite = float(-beta[2])
            e_recon = float(beta[3])
    
            e_portee = np.clip(e_portee, 0.3, 1.2)
            e_priorite = np.clip(e_priorite, 0.1, 0.8)
            e_recon = np.clip(e_recon, 0.0, 0.6)
    
            return {
                "e_portee": round(e_portee, 3),
                "e_priorite": round(e_priorite, 3),
                "e_recon": round(e_recon, 3),
                "calibre": True,
            }
    
        except Exception:
            return {
                "e_portee": 0.60,
                "e_priorite": 0.35,
                "e_recon": 0.30,
                "calibre": False,
            }
    
    
    # ────────────────────────────────────────────
    # ÉTAPE 6 — 5 VARIANTES DE PROGRAMME OPTIMAL
    # ────────────────────────────────────────────
    def etape_6_optimisation(self):
        """
        Génère 5 variantes de programme basées sur :
        - Analyse technique
        - Sensibilité des conditions
        - Logique de leader
        """
    
        self._log(
            "Optimisation",
            "Génération de 5 variantes de programme — perspective leader"
        )
    
        sim_map = {r["tranche"]: r for r in self.resultats_sim}
        bc_map = {r["tranche"]: r for r in self.resultats_bc}
        mkt_map = {r["tranche"]: r for r in self.resultats_mkt}
    
        elasticites = self._calibrer_elasticites()
    
        self._log(
            "Optimisation",
            f"Élasticités {'calibrées' if elasticites['calibre'] else 'heuristiques'} — "
            f"e_portée={elasticites['e_portee']:.3f}, "
            f"e_priorité={elasticites['e_priorite']:.3f}, "
            f"e_recon={elasticites['e_recon']:.3f}"
        )
    
        def taux_technique_modifie(
            t_info,
            taux_pur_ref,
            coeff_portee=1.0,
            coeff_priorite=1.0,
            nb_recon_new=None,
            aal_ratio=None,
            elasticites=None,
        ):
            """
            Estime le taux technique pour un programme modifié.
            Élasticités calibrées depuis df_ml si disponibles,
            sinon fallback sur heuristiques marché.
            """
            e = elasticites or {
                "e_portee": 0.60,
                "e_priorite": 0.35,
                "e_recon": 0.30,
            }
    
            adj = (coeff_portee ** e["e_portee"]) / (
                coeff_priorite ** e["e_priorite"]
            )
    
            n_rec = (
                nb_recon_new
                if nb_recon_new is not None
                else t_info["nb_reconstitutions"]
            )
    
            ratio_rec = (n_rec + 1) / max(t_info["nb_reconstitutions"] + 1, 1)
            adj_rec = ratio_rec ** e["e_recon"]
    
            adj_aal = 1.0
            if aal_ratio is not None and t_info.get("AAL"):
                adj_aal = aal_ratio ** 0.2
    
            return taux_pur_ref * adj * adj_rec * adj_aal
    
        variantes = {}
    
        # ── VARIANTE 1 — Programme de référence ──
        v1 = []
    
        for t in self.tranches:
            r = sim_map.get(t["nom"], {})
            taux = r.get("taux_technique", 0)
    
            v1.append({
                **t,
                "_taux": taux,
                "_prime": self.gnpi * taux,
            })
    
        variantes["ref"] = {
            "label": "Programme de référence",
            "description": "Conditions actuelles — taux techniques issus de la simulation",
            "angle": "Base de comparaison",
            "tranches": v1,
            "prime": sum(t["_prime"] for t in v1),
        }
    
        # ── VARIANTE 2 — Optimisation priorité (+10%) ──
        v2 = []
    
        for t in self.tranches:
            t2 = dict(t)
            t2["priorite"] = round(t["priorite"] * 1.10 / 500_000) * 500_000
    
            r = sim_map.get(t["nom"], {})
            tt = taux_technique_modifie(
                t,
                r.get("taux_technique", 0),
                coeff_priorite=1.10,
                elasticites=elasticites,
            )
    
            v2.append({
                **t2,
                "_taux": tt,
                "_prime": self.gnpi * tt,
            })
    
        variantes["priorite_haute"] = {
            "label": "Priorité relevée (+10%)",
            "description": (
                f"Priorité T1 : {self.tranches[0]['priorite'] * 1.10 / 1e6:.1f}M MAD — "
                "réduit l'exposition sur sinistres courants"
            ),
            "angle": "Protège le réassureur sur la tranche travaillante",
            "tranches": v2,
            "prime": sum(t["_prime"] for t in v2),
        }
    
        # ── VARIANTE 3 — Portée réduite (−15%) ──
        v3 = []
    
        for t in self.tranches:
            t3 = dict(t)
            t3["portee"] = round(t["portee"] * 0.85 / 500_000) * 500_000
    
            r = sim_map.get(t["nom"], {})
            tt = taux_technique_modifie(
                t,
                r.get("taux_technique", 0),
                coeff_portee=0.85,
                elasticites=elasticites,
            )
    
            v3.append({
                **t3,
                "_taux": tt,
                "_prime": self.gnpi * tt,
            })
    
        variantes["portee_reduite"] = {
            "label": "Portée réduite (−15%)",
            "description": "Réduit l'engagement maximal — adapté si sinistralité catastrophique élevée",
            "angle": "Limite le MPL (Maximum Possible Loss)",
            "tranches": v3,
            "prime": sum(t["_prime"] for t in v3),
        }
    
        # ── VARIANTE 4 — Conditions restrictives ──
        v4 = []
    
        for t in self.tranches:
            t4 = dict(t)
    
            if t["type"] == "travaillante":
                aad_actuel = t.get("AAD") or 0
                t4["AAD"] = round(
                    max(aad_actuel * 1.25, t["portee"] * 0.15) / 100_000
                ) * 100_000
    
            if t["type"] == "cat":
                t4["nb_reconstitutions"] = max(t["nb_reconstitutions"] - 1, 1)
    
            r = sim_map.get(t["nom"], {})
            tt = taux_technique_modifie(
                t,
                r.get("taux_technique", 0),
                nb_recon_new=t4["nb_reconstitutions"],
                elasticites=elasticites,
            )
    
            v4.append({
                **t4,
                "_taux": tt,
                "_prime": self.gnpi * tt,
            })
    
        variantes["conditions_restrictives"] = {
            "label": "Conditions restrictives",
            "description": "AAD renforcé + reconstitutions cat limitées — réduit la fréquence de mise en jeu",
            "angle": "Meilleure rentabilité technique pour le réassureur",
            "tranches": v4,
            "prime": sum(t["_prime"] for t in v4),
        }
    
        # ── VARIANTE 5 — Programme élargi cédante ──
        v5 = []
    
        for t in self.tranches:
            t5 = dict(t)
            t5["portee"] = round(t["portee"] * 1.15 / 500_000) * 500_000
            t5["priorite"] = round(t["priorite"] * 0.90 / 500_000) * 500_000
    
            r = sim_map.get(t["nom"], {})
            tt = taux_technique_modifie(
                t,
                r.get("taux_technique", 0),
                coeff_portee=1.15,
                coeff_priorite=0.90,
                elasticites=elasticites,
            )
    
            v5.append({
                **t5,
                "_taux": tt,
                "_prime": self.gnpi * tt,
            })
    
        variantes["elargi_cedante"] = {
            "label": "Programme élargi",
            "description": "Portée +15%, priorité −10% — protection maximale pour la cédante",
            "angle": "Proposition cédante si marché favorable / négociation de renouvellement",
            "tranches": v5,
            "prime": sum(t["_prime"] for t in v5),
        }
    
        # ── Scoring des variantes ──
        taux_ref = variantes["ref"]["prime"] / self.gnpi if self.gnpi else 0
    
        for _, v in variantes.items():
            taux_v = v["prime"] / self.gnpi if self.gnpi else 0
    
            v["taux_global"] = taux_v
            v["ecart_ref_pts"] = (taux_v - taux_ref) * 100
            v["score_leader"] = taux_v - abs(taux_v - taux_ref) * 0.5
    
        self._log(
            "Optimisation",
            f"5 variantes générées | Prime ref : {variantes['ref']['prime']:,.0f} MAD"
        )
    
        return variantes

    def generer_rapport_texte(self):
        taux_global = self.prime_totale / self.gnpi if self.gnpi else 0
        lignes = [
            "=" * 60,
            "  RAPPORT DE TARIFICATION — AGENT PYTHON AUTONOME",
            "=" * 60,
            f"  GNPI        : {self.gnpi:,.0f} MAD",
            f"  Prime totale: {self.prime_totale:,.0f} MAD",
            f"  Taux global : {taux_global:.4%}",
            f"  Tranches    : {len(self.tranches)}",
            "=" * 60,
            "",
            "── PARAMÈTRES CALIBRÉS ─────────────────────────────",
            f"  Alpha Pareto (MLE-Hill) : {self.alpha:.4f}",
            f"  Lambda Poisson          : {self.lambda_:.4f}",
            f"  Seuil modélisation      : {self.seuil:,.0f} MAD",
            f"  Pm proxy (P99.5)        : {self.Pm_proxy:,.0f} MAD",
            f"  Chargement majeurs      : {self.chargement_majeurs:.4%}",
            "",
            "── RÉSULTATS PAR TRANCHE ───────────────────────────",
        ]
        for r in self.rapport_rows:
            statut = "⚠️" if r["ecart_bc_sim_pct"] > 30 else "✅"
            lignes += [
                f"",
                f"  [{r['type'].upper()}] {r['tranche']}",
                f"  BC={r['taux_bc']:.4%} | Sim={r['taux_sim']:.4%} | Mkt={r['taux_mkt']:.4%}",
                f"  → Retenu : {r['taux_retenu']:.4%} ({r['methode']})",
                f"  → Prime  : {r['prime_MAD']:,.0f} MAD {statut} (écart BC/Sim : {r['ecart_bc_sim_pct']:.0f}%)",
            ]
        if self.anomalies:
            lignes += ["", "── ALERTES ─────────────────────────────────────────"]
            for a in self.anomalies:
                lignes.append(f"  {a['icone']} [{a['niveau']}] {a['message']}")
        lignes += [
            "",
            "── JOURNAL DES DÉCISIONS ───────────────────────────",
        ]
        for entry in self.log:
            lignes.append(f"  [{entry['etape']}] {entry['decision']}" +
                          (f" — {entry['detail']}" if entry['detail'] else ""))
        lignes += ["", "=" * 60]
        return "\n".join(lignes)

    # ────────────────────────────────────────────
    # PIPELINE COMPLET
    # ────────────────────────────────────────────
    def run(self, n_sim=10000):
        self.etape_0_validation()
        self.etape_1_burning_cost()
        self.etape_2_simulation(n_sim)
        self.etape_3_controles()
        self.etape_4_market_curve()
        self.etape_5_rapport()
        self.variantes = self.etape_6_optimisation()
        return self.generer_rapport_texte()
