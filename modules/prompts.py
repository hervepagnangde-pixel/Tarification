"""
Atlantic Re IA — Prompt engineering module
Fonctions compatibles avec app.py :
- prompt_inputs
- _charger_few_shot_dynamiques
- build_prompt
- claude_stream
- guide_prompt

Objectif : utiliser le LLM comme couche d'analyse, de contrôle et de recommandation,
jamais comme moteur principal de tarification.
"""

import json
import streamlit as st
import anthropic
from modules.db import _get_conn, _ph


def prompt_inputs(key_prefix, placeholder_contexte="", placeholder_instructions="",
                  placeholder_input="", placeholder_output=""):
    """
    Zone standard de personnalisation du prompt LLM.
    Ajoute aussi une zone dédiée aux résultats de tarification manuelle externe
    afin de comparer les calculs internes avec les références obtenues sous R,
    Excel, SAS ou tout autre outil.
    """
    with st.expander("Personnalisation de l'analyse LLM", expanded=False):
        st.markdown("##### Instructions complémentaires")
        c1, c2 = st.columns(2)
        with c1:
            contexte = st.text_area(
                "Contexte",
                placeholder=placeholder_contexte or "Exemple : Portefeuille automobile, renouvellement 2026, traité XL non proportionnel.",
                height=90,
                key=f"{key_prefix}_contexte",
            )
            instructions = st.text_area(
                "Instructions spécifiques",
                placeholder=placeholder_instructions or "Exemple : comparer les résultats internes aux taux manuels et signaler les écarts.",
                height=90,
                key=f"{key_prefix}_instructions",
            )
        with c2:
            input_data = st.text_area(
                "Données supplémentaires",
                placeholder=placeholder_input or "Exemple : remarques sur la qualité du triangle, exclusions, jugement expert.",
                height=90,
                key=f"{key_prefix}_input",
            )
            output_instructions = st.text_area(
                "Format de sortie souhaité",
                placeholder=placeholder_output or "Exemple : synthèse structurée, écarts, points de vigilance, proposition de programmes comparables.",
                height=90,
                key=f"{key_prefix}_output",
            )

        st.markdown("##### Références de tarification manuelle externe")
        st.caption(
            "Cette zone sert à renseigner les résultats obtenus hors de l'application "
            "sous R, Excel, SAS ou tout autre outil. Ces informations servent de référence comparaison."
        )
        manuel = st.text_area(
            "Résultats manuels externes",
            placeholder=(
                "Exemple :\n"
                "- T1 : taux BC manuel = 3.20 %, taux simulation = 3.45 %, taux retenu = 3.45 %\n"
                "- Loi fréquence : Poisson, lambda = 2.10\n"
                "- Loi sévérité : GPD, seuil = 1 500 000, xi = 0.42, beta = 850 000\n"
                "- Sinistres majeurs : 2019 = 12.5M, 2023 = 9.8M, chargement spécifique = 0.18 %\n"
                "- Commentaire : année 2019 exclue du BC principal mais conservée en stress test."
            ),
            height=140,
            key=f"{key_prefix}_tarification_manuelle_externe",
        )

    if manuel.strip():
        input_data = (input_data or "").strip()
        bloc = "\n\nREFERENCES MANUELLES EXTERNES FOURNIES PAR L'UTILISATEUR :\n" + manuel.strip()
        input_data = (input_data + bloc).strip()

    return contexte, instructions, input_data, output_instructions


def _charger_few_shot_dynamiques(user_email, n_max=3):
    """Charge des exemples de sessions historiques validées depuis la base."""
    try:
        con, db = _get_conn()
        cur = con.cursor()
        p = _ph()
        cur.execute(
            f"""
            SELECT s.nom_session, s.gnpi, r.data_json
            FROM sessions s
            JOIN resultats r ON r.session_id = s.id
            WHERE s.user_email = {p} AND r.etape = 'rapport'
            ORDER BY s.updated_at DESC
            LIMIT {int(n_max)}
            """,
            (user_email,),
        )
        rows = cur.fetchall()
        con.close()
    except Exception:
        return ""

    exemples = []
    for nom, gnpi_h, data_json in rows:
        try:
            d = json.loads(data_json)
            rapport_rows = d.get("rows", [])
            prime_totale = d.get("prime_totale", 0)
            if not rapport_rows:
                continue
            lines = [
                f"SESSION : {nom or 'Sans nom'} | GNPI {(gnpi_h or 0):,.0f} MAD | Prime {prime_totale:,.0f} MAD"
            ]
            for r in rapport_rows[:4]:
                nom_t = r.get("tranche", "") or r.get("Tranche", "")
                typ_t = r.get("type", "") or r.get("Type", "")
                tau = r.get("taux_retenu", "") or r.get("Taux retenu", "")
                meth = r.get("methode", "") or r.get("Méthode", "")
                lines.append(f"  {nom_t} ({typ_t}) -> Retenu {tau} via {meth}")
            exemples.append("\n".join(lines))
        except Exception:
            continue

    if not exemples:
        return ""
    return "\n\n".join([f"CAS HISTORIQUE {i+1} :\n{ex}" for i, ex in enumerate(exemples)])


def build_prompt(role, task, data, contexte="", instructions="",
                 input_data="", output_instructions="",
                 contexte_global="", exemples="", contraintes=""):
    """
    Construit un prompt LLM renforcé anti-hallucination.
    Le LLM intervient comme couche d'interprétation, contrôle, comparaison
    et recommandation de structures comparables. Il ne remplace pas les calculs.
    """
    prompt = f"""
IA TARIF — ASSISTANT D'INTERPRETATION ACTUARIELLE
Réassurance non-proportionnelle XL · Automobile · Marchés émergents

IDENTITE ET ROLE
{role}

POSITIONNEMENT OBLIGATOIRE
Le LLM n'est pas le moteur de tarification. Il ne doit pas calculer un tarif à la place
du moteur actuariel, ni remplacer les travaux manuels réalisés sous R, Excel, SAS ou
un autre outil. Son rôle est de :
1. lire les résultats fournis ;
2. contrôler leur cohérence ;
3. comparer les résultats internes aux références manuelles externes ;
4. identifier les écarts et points de vigilance ;
5. proposer des structures de programmes comparables pour enrichir la négociation ;
6. formuler une recommandation actuarielle argumentée.

REGLES STRICTES ANTI-HALLUCINATION
1. Ne jamais inventer de taux, prime, GNPI, ROL, p-value, R2, alpha, lambda, xi, beta,
   seuil, sinistre majeur ou année exclue.
2. Tout chiffre utilisé doit provenir explicitement des données fournies dans ce prompt.
3. Si une donnée est absente, écrire : "donnée non fournie" ou "données insuffisantes".
4. Ne pas reconstituer de triangle dans la réponse.
5. Ne pas afficher de calcul détaillé non traçable.
6. Ne pas présenter une proposition comme optimale absolue ; parler de structure comparable,
   techniquement cohérente et à valider actuariellement.
7. Ne pas opposer les intérêts de la cédante et du réassureur. L’objectif est, pour le réassureur, de proposer une offre techniquement solide, compétitive et crédible afin de maximiser ses chances d’être retenu comme leader de l’affaire. La formulation doit rester
   professionnelle : proposition alternative comparable, stabilité accrue, lisibilité,
   cohérence marché, enrichissement de négociation.
8. Les références manuelles externes fournies par l'utilisateur sont prioritaires comme
   base de comparaison. Ne pas les modifier.
9. Si les résultats internes divergent fortement des références manuelles, signaler l'écart
   et demander une revue actuarielle, sans trancher arbitrairement.
10. En cas d'incertitude, conclure avec réserve et proposer des perspectives.

CADRE ACTUARIEL
- Burning Cost : référence historique lorsque l'expérience est crédible.
- Simulation fréquence-sévérité : validation stochastique et lecture de queue.
- Courbe de référence marché : benchmark externe, surtout pour les couches hautes/cat.
- Sinistres majeurs : doivent être explicitement identifiés, isolés et commentés. Leur traitement doit être conforme à la méthode retenue : exclusion du Burning Cost courant, chargement spécifique, analyse de sensibilité ou prise en compte dans la simulation de queue lorsque cela est justifié.
- Optimisation : recherche de programmes alternatifs comparables, proches du programme initial,
  avec attention à la variance, à la convergence des méthodes et à la cohérence marché. Doit faire varier priorité, portée, AAD, AAL, reconstitution et seuil de stabilisation ( appliquer seuil atteint).

REGLES DE COHERENCE
- Si les méthodes BC, Simulation et Marché convergent vers des taux proches, le programme
  initial peut être considéré comme techniquement stable, sous réserve de qualité des données.
- Si les méthodes divergent fortement, l'objectif n'est pas d'imposer un taux mais d'identifier
  les sources de divergence : données, sinistres majeurs, fréquence, sévérité, marché, structure.
- La minimisation de la variance doit être comprise comme un critère de stabilité, pas comme
  une optimisation commerciale agressive.

CONTRAINTES METIER SPECIFIQUES
{contraintes if contraintes else "Aucune contrainte spécifique supplémentaire fournie."}

CONTEXTE GLOBAL
{contexte_global if contexte_global else "Non fourni."}

CONTEXTE SPECIFIQUE
{contexte if contexte else "Non fourni."}

TACHE
{task}

DONNEES D'ANALYSE FOURNIES
{data}

DONNEES SUPPLEMENTAIRES ET REFERENCES MANUELLES EVENTUELLES
{input_data if input_data else "Non fourni."}

INSTRUCTIONS COMPLEMENTAIRES
{instructions if instructions else "Produire une analyse actuarielle structurée, prudente et traçable."}

EXEMPLES DE REFERENCE
{exemples if exemples else "Aucun exemple historique fourni."}

FORMAT DE SORTIE REQUIS
{output_instructions if output_instructions else '''
1. Synthèse des données disponibles et limites
2. Comparaison résultats internes vs références manuelles externes, si fournies
3. Analyse de convergence des méthodes BC / Simulation / Marché
4. Lecture des sinistres majeurs et de leur impact potentiel
5. Appréciation de la stabilité du programme initial
6. Programmes alternatifs comparables, uniquement si justifiés par les données
7. Points de vigilance pour la négociation en position de réassureur leader
8. Conclusion prudente : exploitable / exploitable avec réserves / à revoir
'''}

La précision et la traçabilité priment sur l'exhaustivité.
"""
prompt = build_prompt(
    role="Actuaire réassurance XL automobile.",
    task="Analyser les résultats et proposer des programmes alternatifs comparables.",
    data=donnees_resultats,
    contexte=contexte_utilisateur,
    instructions=instructions_utilisateur,
    input_data=references_manuelles,
    output_instructions=format_sortie,
    contexte_global=st.session_state.get("instructions_globales", ""),
    contraintes=contraintes_metier
)
    return prompt.strip()


def claude_stream(api_key, prompt, max_tokens=2000, session_key="", use_opus=False):
    """
    Appel streaming Claude.
    use_opus=True  : modèle plus puissant pour analyses complexes.
    use_opus=False : modèle économique pour analyses standard.
    """
    model = "claude-opus-4-5" if use_opus else "claude-haiku-4-5-20251001"
    client = anthropic.Anthropic(api_key=api_key)
    placeholder = st.empty()
    full_text = ""
    label_model = "Opus" if use_opus else "Haiku"

    with st.status(f"Analyse LLM en cours ({label_model})", expanded=True) as status:
        st.write("Connexion au modèle")
        st.write("Chargement des informations actuarielles")
        try:
            with client.messages.stream(
                model=model,
                max_tokens=max_tokens,
                messages=[{"role": "user", "content": prompt}],
            ) as stream:
                st.write("Génération de l'analyse")
                for text in stream.text_stream:
                    full_text += text
                    placeholder.markdown(full_text + "▌")
            status.update(label="Analyse terminée", state="complete", expanded=False)
        except Exception as e:
            status.update(label="Erreur", state="error")
            st.error(f"Erreur API : {e}")
            return ""

    placeholder.markdown(full_text)
    if session_key:
        st.session_state[session_key] = full_text
    return full_text


def guide_prompt(etape, exemples_contexte, exemples_instructions,
                 exemples_input, exemples_output=None):
    """Affiche un guide sobre pour aider l'utilisateur à renseigner le prompt."""
    exemples_output = exemples_output or []
    with st.expander(f"Conseils de rédaction du prompt — {etape}", expanded=False):
        c1, c2 = st.columns(2)
        with c1:
            st.markdown("**Contexte à renseigner**")
            for ex in exemples_contexte:
                st.markdown(f"- {ex}")
            st.markdown("**Instructions utiles**")
            for ex in exemples_instructions:
                st.markdown(f"- {ex}")
        with c2:
            st.markdown("**Données supplémentaires**")
            for ex in exemples_input:
                st.markdown(f"- {ex}")
            if exemples_output:
                st.markdown("**Format de sortie**")
                for ex in exemples_output:
                    st.markdown(f"- {ex}")
        st.info(
            "Le LLM doit uniquement interpréter les résultats fournis, comparer les références "
            "et proposer des structures comparables. Il ne doit pas inventer de paramètres ni remplacer la tarification actuarielle."
        )
