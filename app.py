CEDANTE & MARCHÉ
━━━━━━━━━━━━━━━
Portefeuille d'une cédante relevant du marché EMIRATES.
Leader de l'affaire : Partner Re. En tant que leader, nous fixons les conditions de référence.
Branche : Responsabilité Civile Automobile + Tous Risques — développement LONG (projection Chain-Ladder obligatoire).

PROGRAMME DE RÉASSURANCE
━━━━━━━━━━━━━━━━━━━━━━━
Tranche 1 (travaillante) : 13 000 000 xs 2 000 000
  → AAL = 26 000 000 MAD | AAD = 4 000 000 MAD
Tranche 2 (cat) : 10 000 000 xs 15 000 000
Tranche 3 (cat) : 15 000 000 xs 25 000 000

CONDITIONS COMMUNES (toutes tranches)
  Reconstitutions : 2 x 100 %
  Brokage : 7 %
  Frais généraux : 5 %
  Marge bénéficiaire : 10 %
  Rétrocession : 0,21 %

RÈGLES ACTUARIELLES OBLIGATOIRES — BURNING COST
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
R1 — Taux de risque BC : τ_risque = τ_pur + σ_hist × 20 %
     où σ_hist est l'écart-type des burning costs annuels historiques non nuls de la tranche.
R2 — Filtre données insuffisantes : si le nombre d'années avec BC historique non nul pour
     une tranche est STRICTEMENT INFÉRIEUR à 3, poser τ_BC = 0 pour cette tranche
     (données insuffisantes — ne pas extrapoler).
R3 — Pour les tranches cat avec τ_BC = 0, la tarification repose UNIQUEMENT sur la
     simulation stochastique et la market curve.

RÈGLES ACTUARIELLES — MARKET CURVE
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
La market curve (ROL = a × x^(−b)) est utilisée UNIQUEMENT pour les tranches cat (T2, T3).
Elle ne s'applique PAS à la tranche travaillante.
Critères de sélection obligatoires pour un bon ajustement :
  • R² ≥ 0,45 (préférer > 0,55 si possible)
  • b > 0 (pente décroissante — obligatoire)
  • Nombre de points N ≥ 15 (robustesse statistique)
  • Les taux marché cat doivent être cohérents avec la hiérarchie : T2 > T3 en ROL
    (tranche plus basse = ROL plus élevé — vérifier cette cohérence)
  • Écarter les ajustements où ROL cat > 3 × taux simulation correspondant
  • En cas de plusieurs ajustements valides, retenir celui avec le meilleur score
    combiné (R², robustesse N, cohérence inter-tranches cat)

RÈGLE DE SÉLECTION FINALE PAR TRANCHE
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
T1 (travaillante) : méthode = max(τ_BC, τ_simulation) — retenir la plus conservative
T2, T3 (cat)      : méthode = max(τ_simulation, τ_marché) — toujours côté sécurité

LIVRABLE FINAL OBLIGATOIRE — OPTIMISATION DU PROGRAMME
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
En tant que leader Partner Re, proposer à la fin du rapport 3 variantes de programme optimal :

VARIANTE A — Programme optimal côté CÉDANTE (minimiser la prime, maximiser la protection)
  Proposer : ajustements AAL/AAD, portées, priorités, reconstitutions
  Justifier l'impact sur la prime et le taux retenu

VARIANTE B — Programme optimal côté RÉASSUREUR (maximiser le rendement, maîtriser l'exposition)
  Proposer : conditions plus restrictives, niveaux de priorité, limitation des reconstitutions
  Justifier l'impact sur la sinistralité attendue et le ROL

VARIANTE C — Programme équilibré LEADER Partner Re (compromis acceptable pour les deux parties)
  Proposition de négociation réaliste avec fourchette de taux défendable
  Inclure la comparaison avec le taux technique calculé et le positionnement marché

Pour chaque variante : tableau récapitulatif (priorité, portée, AAL, AAD, reconst., taux retenu, prime estimée).
Conclure avec une recommandation de positionnement final chiffrée.
