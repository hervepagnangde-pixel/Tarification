with tab5:
    st.header("Market Curve")
    st.caption("ROL = a × midpoints^(−b)  ↔  log(ROL) = log(a) − b×log(midpoints)")

    f_mkt = st.file_uploader("📁 Données marché", type=["xlsx","csv"], key="f_mkt")

    # ── Paramètres de filtrage (inspirés du VBA) ──
    with st.expander("⚙️ Paramètres de filtrage", expanded=False):
        c1, c2, c3 = st.columns(3)
        with c1:
            rol_min   = st.number_input("ROL minimum (%)", value=5.0,  step=1.0) / 100
            rol_max   = st.number_input("ROL maximum (%)", value=150.0, step=10.0) / 100
        with c2:
            tolerance = st.number_input("Tolérance proximité ROL≈Midpoint (%)", value=20.0, step=5.0) / 100
            r2_min    = st.number_input("R² minimum accepté (%)", value=45.0, step=5.0) / 100
        with c3:
            filtre_branche = st.text_input("Filtre branche (colonne INT_BUSINESS)", value="EVENEMENT",
                                            help="Garde uniquement les lignes contenant ce mot")
            st.caption("Laisser vide = pas de filtre branche")

    if f_mkt and st.button("▶ Construire la market curve", type="primary"):
        with st.spinner("📈 Construction en cours..."):
            df_mkt = pd.read_excel(f_mkt) if f_mkt.name.endswith('xlsx') else pd.read_csv(f_mkt)

            # Nettoyage colonnes numériques
            for col in ['ROLs','midpoints','Garantie en MAD','Priorité en MAD']:
                if col in df_mkt.columns and df_mkt[col].dtype == object:
                    df_mkt[col] = (df_mkt[col].astype(str)
                                   .str.replace('%','')
                                   .str.replace(' ','')
                                   .str.replace(',','.')
                                   .apply(lambda x: float(x)/100 if float(x) > 1.5 else float(x)
                                          if x not in ['nan',''] else np.nan))

            df_mkt = df_mkt.dropna(subset=['ROLs','midpoints'])

            # ── Filtre 1 : branche ──
            n_avant = len(df_mkt)
            if filtre_branche.strip():
                col_business = next((c for c in df_mkt.columns if 'BUSINESS' in c.upper() or 'BRANCHE' in c.upper()), None)
                if col_business:
                    df_mkt = df_mkt[df_mkt[col_business].astype(str).str.upper().str.contains(filtre_branche.upper())]
            n_filtre = n_avant - len(df_mkt)

            # ── Filtre 2 : bornes ROL ──
            mask_rol  = (df_mkt['ROLs'] >= rol_min) & (df_mkt['ROLs'] <= rol_max)
            df_excl_rol = df_mkt[~mask_rol].copy()
            df_mkt    = df_mkt[mask_rol].copy()
            n_rol     = len(df_excl_rol)

            # ── Filtre 3 : ROL ≈ Midpoint (trop proche = point suspect) ──
            df_mkt['diff_rel'] = np.where(
                df_mkt['midpoints'] != 0,
                np.abs(df_mkt['ROLs'] - df_mkt['midpoints']) / np.abs(df_mkt['midpoints']),
                1.0
            )
            df_excl_prox = df_mkt[df_mkt['diff_rel'] < tolerance].copy()
            df_mkt       = df_mkt[df_mkt['diff_rel'] >= tolerance].copy()
            n_prox       = len(df_excl_prox)

            # ── Filtre 4 : midpoints > 0 ──
            df_mkt = df_mkt[df_mkt['midpoints'] > 0].copy()

            # Résumé filtrage
            st.markdown(f"""
            <div style="background:#f0fff4; border-left:4px solid #2d8a4e; border-radius:0 8px 8px 0; padding:12px 16px; margin:8px 0">
                ✅ <b>{len(df_mkt)} points retenus</b> sur {n_avant} &nbsp;|&nbsp;
                Exclus filtre branche : {n_filtre} &nbsp;|&nbsp;
                Exclus ROL hors [{rol_min*100:.0f}%–{rol_max*100:.0f}%] : {n_rol} &nbsp;|&nbsp;
                Exclus ROL≈Midpoint : {n_prox}
            </div>
            """, unsafe_allow_html=True)

            if len(df_mkt) < 5:
                st.error("❌ Moins de 5 points retenus — impossible d'ajuster la courbe.")
                st.stop()

            # ── Fonctions ajustement ──
            def fit_power(x, y):
                """
                ROL = a × mid^(-b)
                log(ROL) = log(a) - b×log(mid)
                Régression : slope=-b, intercept=log(a)
                """
                log_x     = np.log(x)
                log_y     = np.log(y)
                coeffs    = np.polyfit(log_x, log_y, 1)
                slope     = coeffs[0]        # = -b
                intercept = coeffs[1]        # = log(a)
                a         = np.exp(intercept)
                b         = -slope           # doit être > 0
                log_y_pred = np.polyval(coeffs, log_x)
                ss_res    = np.sum((log_y - log_y_pred)**2)
                ss_tot    = np.sum((log_y - log_y.mean())**2)
                r2        = 1 - ss_res / ss_tot if ss_tot > 0 else 0
                return a, b, r2

            def predict_rol(mid, a, b):
                return a * (mid ** (-b))

            # ── 10 combinaisons de quantiles ──
            resultats_mkt = []
            for q in [0.10,0.20,0.30,0.40,0.50,0.60,0.70,0.80,0.90,1.0]:
                mid_max  = np.quantile(df_mkt['midpoints'],       q)
                port_max = np.quantile(df_mkt['Garantie en MAD'], q) if 'Garantie en MAD' in df_mkt.columns else np.inf
                df_q     = df_mkt[
                    (df_mkt['midpoints'] <= mid_max) &
                    (df_mkt['Garantie en MAD'] <= port_max if 'Garantie en MAD' in df_mkt.columns else True)
                ]
                if len(df_q) < 5: continue
                try:
                    a, b, r2 = fit_power(df_q['midpoints'].values, df_q['ROLs'].values)

                    # b doit être positif (ROL décroit avec priorité)
                    if b <= 0: continue

                    # Calcul des taux par tranche
                    taux_tranches = []
                    taux_nuls     = 0
                    for t in tranches_input:
                        mid_t = t['priorite'] + t['portee'] / 2
                        rol   = predict_rol(mid_t, a, b)
                        taux  = rol * (t['portee'] / gnpi)
                        if taux <= 0 or np.isnan(taux) or np.isinf(taux):
                            taux_nuls += 1
                        taux_tranches.append({
                            "tranche": t["nom"],
                            "type"   : t["type"],
                            "rol"    : rol,
                            "taux"   : taux
                        })

                    # ── Critère de sélection ──
                    # Préférer R²≥45% avec taux non nuls
                    # à R²>45% avec taux nuls
                    if taux_nuls > 0:
                        continue  # Rejeter si taux nuls

                    taux_vals   = [tt["taux"] for tt in taux_tranches]
                    median_taux = np.median(taux_vals)
                    cv_taux     = np.std(taux_vals) / median_taux if median_taux > 0 else 99

                    resultats_mkt.append({
                        "quantile"     : q,
                        "n_points"     : len(df_q),
                        "a"            : a,
                        "b"            : b,
                        "r2"           : r2,
                        "cv_taux"      : cv_taux,
                        "taux_tranches": taux_tranches,
                        "r2_ok"        : r2 >= r2_min
                    })
                except: continue

            # Si aucun résultat avec taux non nuls, on relâche la contrainte
            if not resultats_mkt:
                st.warning(f"⚠️ Aucun ajustement avec taux non nuls — relâchement de la contrainte.")
                for q in [0.10,0.20,0.30,0.40,0.50,0.60,0.70,0.80,0.90,1.0]:
                    mid_max  = np.quantile(df_mkt['midpoints'], q)
                    df_q     = df_mkt[df_mkt['midpoints'] <= mid_max]
                    if len(df_q) < 5: continue
                    try:
                        a, b, r2 = fit_power(df_q['midpoints'].values, df_q['ROLs'].values)
                        if b <= 0: continue
                        taux_tranches = [{"tranche":t["nom"],"type":t["type"],
                            "rol": predict_rol(t['priorite']+t['portee']/2, a, b),
                            "taux": predict_rol(t['priorite']+t['portee']/2, a, b)*(t['portee']/gnpi)}
                            for t in tranches_input]
                        taux_vals   = [tt["taux"] for tt in taux_tranches]
                        median_taux = np.median(taux_vals)
                        cv_taux     = np.std(taux_vals)/median_taux if median_taux > 0 else 99
                        resultats_mkt.append({
                            "quantile":q,"n_points":len(df_q),"a":a,"b":b,
                            "r2":r2,"cv_taux":cv_taux,"taux_tranches":taux_tranches,"r2_ok":r2>=r2_min
                        })
                    except: continue

            if not resultats_mkt:
                st.error("❌ Impossible d'ajuster la courbe. Vérifiez les données.")
                st.stop()

            # ── Score : R²≥45% avec taux non nuls prime sur tout ──
            all_t  = [tt["taux"] for r in resultats_mkt for tt in r["taux_tranches"]]
            med_g  = np.median([t for t in all_t if t > 0]) if any(t > 0 for t in all_t) else 1
            r2v    = [r["r2"] for r in resultats_mkt]
            r2min_v, r2max_v = min(r2v), max(r2v)

            for r in resultats_mkt:
                tm        = np.mean([tt["taux"] for tt in r["taux_tranches"]])
                r2_norm   = (r["r2"] - r2min_v) / (r2max_v - r2min_v + 1e-10)
                ecart_med = abs(tm - med_g) / (med_g + 1e-10)
                taux_nuls = sum(1 for tt in r["taux_tranches"] if tt["taux"] <= 0)

                # Pénalité forte si taux nuls
                penalite_nuls = taux_nuls * 10.0

                # Score final : R²≥45% + taux cohérents + pas nuls
                r["score"] = (
                    0.5 * r2_norm
                    - 0.3 * ecart_med
                    - 0.2 * r["cv_taux"]
                    - penalite_nuls
                    + (0.5 if r["r2_ok"] else 0)  # bonus si R²≥seuil
                )

            resultats_mkt = sorted(resultats_mkt, key=lambda x: x['score'], reverse=True)
            st.session_state["resultats_mkt"] = resultats_mkt
            st.session_state["df_mkt_clean"]  = df_mkt

    if "resultats_mkt" in st.session_state:
        rmt = st.session_state["resultats_mkt"]
        dmc = st.session_state["df_mkt_clean"]

        def predict_rol(mid, a, b):
            return a * (mid ** (-b))

        rows_recap = []
        for r in rmt:
            row = {
                "Q"     : f"Q{int(r['quantile']*100)}",
                "N"     : r["n_points"],
                "a"     : f"{r['a']:.5f}",
                "b"     : f"{r['b']:.4f}",
                "R²"    : f"{r['r2']:.4f}",
                "R²≥seuil": "✅" if r["r2_ok"] else "⚠️",
                "Score" : f"{r['score']:.4f}",
            }
            for tt in r["taux_tranches"]:
                taux = tt["taux"]
                row[tt["tranche"]] = f"{taux:.4%}" if taux > 0 else "❌ NUL"
            rows_recap.append(row)

        st.subheader("📊 Comparaison des ajustements — ROL = a × mid^(−b)")
        tableau_resultats(rows_recap)

        best = rmt[0]
        st.success(
            f"✅ Meilleur : Q{int(best['quantile']*100)} — "
            f"ROL = {best['a']:.5f} × mid^(−{best['b']:.4f}) | "
            f"R²={best['r2']:.4f} {'✅' if best['r2_ok'] else '⚠️'} | "
            f"Score={best['score']:.4f}"
        )

        choix_q = st.selectbox(
            "Choisir la combinaison",
            options=[
                f"Q{int(r['quantile']*100)} — a={r['a']:.5f} b={r['b']:.4f} "
                f"R²={r['r2']:.4f}{'✅' if r['r2_ok'] else '⚠️'} Score={r['score']:.4f}"
                for r in rmt
            ],
            index=0
        )
        idx_choix = [
            f"Q{int(r['quantile']*100)} — a={r['a']:.5f} b={r['b']:.4f} "
            f"R²={r['r2']:.4f}{'✅' if r['r2_ok'] else '⚠️'} Score={r['score']:.4f}"
            for r in rmt
        ].index(choix_q)
        choix = rmt[idx_choix]

        # ── Graphique ──
        x_all   = dmc['midpoints'].values
        y_all   = dmc['ROLs'].values
        x_range = np.linspace(min(x_all), max(x_all), 300)
        y_fit   = predict_rol(x_range, choix['a'], choix['b'])

        fig, ax = plt.subplots(figsize=(10,5))
        fig.patch.set_facecolor('#f5f5f5')
        ax.set_facecolor('#fafafa')
        ax.scatter(x_all, y_all, color='#2d8a4e', s=60, zorder=5, alpha=0.7, label='Données marché (retenus)')
        ax.plot(x_range, y_fit, color='#1a1a1a', lw=2.5,
                label=f"ROL = {choix['a']:.5f} × mid^(−{choix['b']:.4f}) | R²={choix['r2']:.4f}")
        ax.set_xlabel('Midpoints'); ax.set_ylabel('ROL')
        ax.set_title('Market Curve — ROL = a × midpoints^(−b)', fontweight='bold', color='#1a1a1a')
        ax.legend(); ax.grid(alpha=0.3, linestyle='--')
        st.pyplot(fig)

        # ── Taux retenus ──
        st.subheader("📊 Taux marché retenus")
        df_taux = pd.DataFrame([{
            "Tranche"    : tt["tranche"],
            "Type"       : tt["type"],
            "ROL estimé" : f"{tt['rol']:.4%}",
            "Taux marché": f"{tt['taux']:.4%}" if tt["taux"] > 0 else "❌ NUL"
        } for tt in choix["taux_tranches"]])
        st.dataframe(df_taux, use_container_width=True)

        st.session_state["taux_mkt_final"] = choix["taux_tranches"]

        st.divider()
        st.markdown("### 🤖 Analyse Claude — Market Curve")
        ctx_mkt, inst_mkt, inp_mkt, out_mkt = prompt_inputs(
            key_prefix="mkt",
            placeholder_contexte="Ex: Marché en durcissement, hausse 15% vs année précédente...",
            placeholder_instructions="Ex: Privilégier les ajustements avec N > 20 points...",
            placeholder_input="Ex: Taux marché de référence secteur : Cat L1=1.5%",
            placeholder_output="Ex: Recommandation unique avec justification R² et cohérence"
        )

        if api_key and st.button("🤖 Recommandations Claude — Market Curve"):
            with st.spinner("Claude analyse..."):
                prompt = build_prompt(
                    role="Expert en réassurance catastrophe et market curve, spécialiste marchés émergents.",
                    task=f"""Analyse les ajustements de market curve et recommande le meilleur.
Modèle : ROL = a × midpoints^(-b), b > 0 (ROL décroit avec la priorité)
Critère prioritaire : R²≥{r2_min*100:.0f}% avec taux non nuls > R² plus élevé avec taux nuls.
Pour chaque ajustement :
1. Évalue R² et sa significativité (seuil {r2_min*100:.0f}%)
2. Vérifie que tous les taux sont positifs et cohérents
3. Tiens compte du N (robustesse statistique)
4. Signale les taux nuls ou aberrants
Recommande UN seul ajustement avec justification.""",
                    data=f"""Ajustements :
{json.dumps(rows_recap, indent=2)}
Programme : {json.dumps(tranches_input, indent=2)}
GNPI : {gnpi:,} MAD
Filtres appliqués : ROL∈[{rol_min*100:.0f}%,{rol_max*100:.0f}%], tolérance proximité {tolerance*100:.0f}%""",
                    contexte=ctx_mkt, instructions=inst_mkt,
                    input_data=inp_mkt, output_instructions=out_mkt,
                    contexte_global=st.session_state.get("instructions_globales",""),
                    contraintes=f"""- b > 0 obligatoire (ROL décroit avec priorité)
- R²≥{r2_min*100:.0f}% avec taux non nuls = préférable à R² plus élevé avec taux nuls
- Taux nul = rejet immédiat de l'ajustement
- N < 10 = faible robustesse à signaler
- Taux marché > 3× simulation = suspect"""
                )
                client = anthropic.Anthropic(api_key=api_key)
                reco   = client.messages.create(
                    model="claude-opus-4-5", max_tokens=1500,
                    messages=[{"role":"user","content":prompt}]
                )
                st.session_state["analyse_mkt"] = reco.content[0].text

        if "analyse_mkt" in st.session_state:
            st.markdown(st.session_state["analyse_mkt"])
