"""
Atlantic Re IA — Notifications module
Email Gmail SMTP + webhooks Slack/Teams + envoi rapport PDF.
"""
import streamlit as st
import json, urllib.request, urllib.error
from datetime import datetime
from modules.pdf_gen import generer_pdf_rapport, generer_pptx_rapport


# ════════════════════════════════════════════
# HELPERS
# ════════════════════════════════════════════

def _normaliser_destinataires_email(destinataire):
    """Accepte une chaîne séparée par virgule/point-virgule ou une liste d'emails."""
    if destinataire is None:
        return []
    if isinstance(destinataire, (list, tuple, set)):
        items = list(destinataire)
    else:
        items = str(destinataire).replace(";", ",").split(",")
    emails = []
    for e in items:
        e = str(e).strip()
        if e and "@" in e and "." in e.split("@")[-1]:
            emails.append(e)
    return emails


def get_destinataires_notifications_agent():
    """Retourne les destinataires configurés pour les notifications IA."""
    candidats = [
        st.session_state.get("email_notifications_agent", ""),
        st.session_state.get("notif_destinataires", ""),
        st.session_state.get("rapport_email_destinataires", ""),
        st.session_state.get("user_email", ""),
    ]
    for candidat in candidats:
        emails = _normaliser_destinataires_email(candidat)
        if emails:
            return emails
    return []


# ════════════════════════════════════════════
# EMAIL SMTP
# ════════════════════════════════════════════

def envoyer_notification_email(sujet, corps, destinataire="hervepagnangde@gmail.com",
                                pieces_jointes=None):
    """
    Envoie via Gmail SMTP.
    SMTP_USER et SMTP_PASS doivent être dans les Secrets Streamlit (niveau racine).
    Pour Gmail : SMTP_PASS = App Password 16 caractères.
    """
    destinataires = _normaliser_destinataires_email(destinataire)
    if not destinataires:
        return False, "Aucun destinataire valide."

    # Lecture secrets
    smtp_user = ""
    smtp_pass = ""
    try:
        smtp_user = st.secrets["SMTP_USER"]
        smtp_pass = st.secrets["SMTP_PASS"]
    except Exception:
        try:
            smtp_user = st.secrets.get("SMTP_USER", "")
            smtp_pass = st.secrets.get("SMTP_PASS", "")
        except Exception:
            pass

    if not smtp_user or not smtp_pass:
        for section in ["roles", "smtp", "email", "config"]:
            try:
                sec = st.secrets.get(section, {})
                if hasattr(sec, "get"):
                    u = sec.get("SMTP_USER", "") or sec.get("smtp_user", "")
                    p = sec.get("SMTP_PASS", "") or sec.get("smtp_pass", "")
                    if u and p:
                        smtp_user = u; smtp_pass = p; break
            except Exception:
                pass

    if not smtp_user or not smtp_pass:
        return False, (
            "SMTP non configuré. Ajoutez SMTP_USER et SMTP_PASS dans les Secrets Streamlit. "
            "Pour Gmail, SMTP_PASS doit être un App Password de 16 caractères."
        )

    import smtplib
    from email.mime.text import MIMEText
    from email.mime.multipart import MIMEMultipart
    from email.mime.base import MIMEBase
    from email import encoders

    msg = MIMEMultipart("mixed")
    msg["Subject"] = f"[Atlantic Re IA] {sujet}"
    msg["From"]    = smtp_user
    msg["To"]      = ", ".join(destinataires)

    alt = MIMEMultipart("alternative")
    html_body = f"""
    <html><body style="font-family:Arial,sans-serif;color:#0d2b3e">
    <div style="border-top:4px solid #00b5a5;padding:20px;max-width:680px">
      <h2 style="color:#0d2b3e">&#x1F916; Atlantic Re IA</h2>
      <div style="background:#f2f8f7;padding:16px;border-left:4px solid #00b5a5">
        {corps}
      </div>
      <p style="color:#5a7a8a;font-size:12px;margin-top:20px">
        Atlantic Re IA &middot; Réassurance Non-Proportionnelle &middot; Maroc
      </p>
    </div></body></html>"""
    alt.attach(MIMEText(html_body, "html"))
    msg.attach(alt)

    for pj in (pieces_jointes or []):
        try:
            data = pj.get("data", b"")
            filename = pj.get("filename", "piece_jointe")
            mime_type = pj.get("mime_type", "application/octet-stream")
            maintype, subtype = mime_type.split("/", 1) if "/" in mime_type else ("application", "octet-stream")
            part = MIMEBase(maintype, subtype)
            part.set_payload(data)
            encoders.encode_base64(part)
            part.add_header("Content-Disposition", f'attachment; filename="{filename}"')
            msg.attach(part)
        except Exception:
            continue

    # SSL 465
    try:
        with smtplib.SMTP_SSL("smtp.gmail.com", 465, timeout=15) as server:
            server.login(smtp_user, smtp_pass)
            server.sendmail(smtp_user, destinataires, msg.as_string())
        return True, f"Email envoyé à {len(destinataires)} destinataire(s) (SSL 465)"
    except smtplib.SMTPAuthenticationError:
        return False, (
            "Authentification Gmail échouée. Créez un App Password Gmail : "
            "myaccount.google.com → Sécurité → Validation 2 étapes → Mots de passe des applications."
        )
    except Exception as e1:
        # STARTTLS 587
        try:
            with smtplib.SMTP("smtp.gmail.com", 587, timeout=15) as server:
                server.ehlo(); server.starttls(); server.ehlo()
                server.login(smtp_user, smtp_pass)
                server.sendmail(smtp_user, destinataires, msg.as_string())
            return True, f"Email envoyé à {len(destinataires)} destinataire(s) (STARTTLS 587)"
        except smtplib.SMTPAuthenticationError:
            return False, "Authentification Gmail échouée (port 587). App Password Gmail requis."
        except Exception as e2:
            return False, f"Erreur SMTP (SSL: {e1} | TLS: {e2})"


def notifier_consultation(user_email, module, details=""):
    """Notifie automatiquement lors d'une consultation de l'agent."""
    sujet = f"Consultation par {user_email} — {module}"
    corps = f"""
    <p><b>Utilisateur :</b> {user_email}</p>
    <p><b>Module consulté :</b> {module}</p>
    <p><b>Date/Heure :</b> {datetime.now().strftime('%d/%m/%Y à %H:%M:%S')}</p>
    {f'<p><b>Détails :</b> {details}</p>' if details else ''}
    """
    destinataires = get_destinataires_notifications_agent()
    if not destinataires:
        return False
    ok, _ = envoyer_notification_email(sujet, corps, destinataire=destinataires)
    return ok


# ════════════════════════════════════════════
# RAPPORT PDF PAR EMAIL
# ════════════════════════════════════════════

def generer_pdf_rapport_courant(gnpi_val, tranches, prime_totale_val, annee=2026):
    """Génère le PDF du rapport courant depuis session_state."""
    return generer_pdf_rapport(
        user_email=st.session_state.get("user_email", ""),
        gnpi_val=gnpi_val,
        tranches=tranches,
        resultats_bc=st.session_state.get("resultats_bc", []),
        resultats_sim=st.session_state.get("resultats_sim", []),
        taux_mkt_final=st.session_state.get("taux_mkt_final", []),
        df_rapport=st.session_state.get("df_rapport"),
        prime_totale=prime_totale_val,
        analyse_claude=st.session_state.get("reco_finale", ""),
        annee=annee
    )


def envoyer_rapport_pdf_email(destinataires, gnpi_val, tranches, prime_totale_val,
                               message_html="", annee=2026):
    """Génère et envoie le rapport PDF courant."""
    pdf_bytes = generer_pdf_rapport_courant(gnpi_val, tranches, prime_totale_val, annee=annee)
    nom_fichier = f"atlantic_re_rapport_{datetime.now().strftime('%Y%m%d_%H%M')}.pdf"
    taux_global = prime_totale_val / gnpi_val if gnpi_val else 0
    corps = f"""
    <p>Bonjour,</p>
    <p>Veuillez trouver ci-joint le rapport de tarification généré par <b>Atlantic Re IA</b>.</p>
    <ul>
      <li><b>Utilisateur :</b> {st.session_state.get('user_email','')}</li>
      <li><b>GNPI :</b> {gnpi_val:,.0f} MAD</li>
      <li><b>Prime totale :</b> {prime_totale_val:,.0f} MAD</li>
      <li><b>Taux global :</b> {taux_global:.4%}</li>
      <li><b>Date :</b> {datetime.now().strftime('%d/%m/%Y à %H:%M')}</li>
    </ul>
    {message_html if message_html else ""}
    <p>Cordialement,<br>Atlantic Re IA</p>
    """
    return envoyer_notification_email(
        "Rapport de tarification XL",
        corps,
        destinataire=destinataires,
        pieces_jointes=[{
            "filename": nom_fichier,
            "data": pdf_bytes,
            "mime_type": "application/pdf",
        }]
    )
