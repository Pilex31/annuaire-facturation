"""
ANNUAIRE ROMAND — Agent de facturation v1
──────────────────────────────────────────
Génère les factures annuelles d'abonnement.

Deux modes :
  1. Mode CRON (automatique) : génère les factures pour tous les
     clients dont l'abonnement doit être renouvelé aujourd'hui.
  2. Mode MANUEL : génère une facture pour un client précis.

Les PDF sont déposés dans le dossier /factures.
Chaque facture est enregistrée dans la table 'factures' de Supabase.

Variables d'environnement requises :
  SUPABASE_URL, SUPABASE_KEY
  OQOO_NOM, OQOO_RUE, OQOO_NUMERO, OQOO_NPA, OQOO_VILLE
  OQOO_QR_IBAN, OQOO_TVA, OQOO_EMAIL, OQOO_TELEPHONE
"""

import os
import sys
import re
import unicodedata
from datetime import datetime, date, timedelta
from supabase import create_client, Client

from generateur_factures import generer_facture


# ═══════════════════════════════════════════════════════
# CONFIGURATION
# ═══════════════════════════════════════════════════════

SUPABASE_URL = os.environ.get("SUPABASE_URL")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY")

# Tarif de l'abonnement
PRIX_HT = 39.95
TAUX_TVA = 8.10
DELAI_PAIEMENT_JOURS = 30

# Limite : nombre de PREMIÈRES factures (nouveaux clients) par jour.
# Les renouvellements (date anniversaire) ne sont PAS limités.
MAX_PREMIERES_FACTURES_PAR_JOUR = 5

# Bucket Supabase Storage où sont déposés les PDF
BUCKET_FACTURES = "factures"


def get_emetteur() -> dict:
    """Coordonnées d'OQOO, lues depuis les variables d'environnement."""
    return {
        "nom": os.environ.get("OQOO_NOM", "OQOO"),
        "rue": os.environ.get("OQOO_RUE", ""),
        "numero": os.environ.get("OQOO_NUMERO", ""),
        "npa": os.environ.get("OQOO_NPA", ""),
        "ville": os.environ.get("OQOO_VILLE", ""),
        "qr_iban": os.environ.get("OQOO_QR_IBAN", ""),
        "tva": os.environ.get("OQOO_TVA", ""),
        "email": os.environ.get("OQOO_EMAIL", ""),
        "telephone": os.environ.get("OQOO_TELEPHONE", ""),
    }


def log(msg: str):
    print(f"[{datetime.now().strftime('%H:%M:%S')}] {msg}", flush=True)


def nettoyer_nom_fichier(texte: str) -> str:
    """
    Nettoie une chaîne pour qu'elle soit un nom de fichier valide
    pour Supabase Storage : pas d'accents, pas d'espaces, pas de
    caractères spéciaux. Garde lettres, chiffres, tirets, underscores.
    """
    # Décomposer les accents (é -> e + accent) puis retirer les accents
    sans_accents = unicodedata.normalize("NFKD", texte)
    sans_accents = sans_accents.encode("ascii", "ignore").decode("ascii")
    # Remplacer tout ce qui n'est pas alphanumérique par un underscore
    propre = re.sub(r"[^A-Za-z0-9]+", "_", sans_accents)
    # Retirer les underscores en début/fin
    return propre.strip("_")


def get_supabase() -> Client:
    return create_client(SUPABASE_URL, SUPABASE_KEY)


# ═══════════════════════════════════════════════════════
# CALCULS
# ═══════════════════════════════════════════════════════

def calculer_montants(prix_ht: float = PRIX_HT, taux: float = TAUX_TVA) -> dict:
    """Calcule HT, TVA et TTC."""
    montant_tva = round(prix_ht * taux / 100, 2)
    montant_ttc = round(prix_ht + montant_tva, 2)
    return {
        "montant_ht": round(prix_ht, 2),
        "taux_tva": taux,
        "montant_tva": montant_tva,
        "montant_ttc": montant_ttc,
    }


def calculer_chiffre_controle(nombre: str) -> str:
    """
    Calcule le chiffre de contrôle (modulo 10 récursif) pour la
    référence QR suisse. Norme officielle ESR/QRR.
    """
    table = [0, 9, 4, 6, 8, 2, 7, 1, 3, 5]
    report = 0
    for chiffre in nombre:
        report = table[(report + int(chiffre)) % 10]
    return str((10 - report) % 10)


def generer_reference_qr(numero_facture_int: int) -> str:
    """
    Génère une référence QR de 27 chiffres.
    Les 26 premiers identifient la facture, le 27e est le chiffre
    de contrôle. Affichée par blocs de 5 (norme suisse).
    """
    base = str(numero_facture_int).zfill(26)
    controle = calculer_chiffre_controle(base)
    ref = base + controle
    # Format par blocs de 5 depuis la droite
    blocs = []
    reste = ref
    while len(reste) > 5:
        blocs.insert(0, reste[-5:])
        reste = reste[:-5]
    if reste:
        blocs.insert(0, reste)
    return " ".join(blocs)


def prochain_numero_facture(supabase: Client) -> tuple:
    """
    Détermine le prochain numéro de facture.
    Format : AAAA-NNNN (ex: 2026-0001).
    Retourne (numero_str, compteur_int).
    """
    annee = date.today().year
    res = (
        supabase.table("factures")
        .select("numero")
        .like("numero", f"{annee}-%")
        .order("numero", desc=True)
        .limit(1)
        .execute()
    )
    if res.data:
        dernier = res.data[0]["numero"]
        compteur = int(dernier.split("-")[1]) + 1
    else:
        compteur = 1
    return f"{annee}-{str(compteur).zfill(4)}", compteur


# ═══════════════════════════════════════════════════════
# GÉNÉRATION D'UNE FACTURE POUR UN CLIENT
# ═══════════════════════════════════════════════════════

def facturer_client(supabase: Client, client: dict, emetteur: dict) -> dict:
    """
    Génère une facture pour un client : calcul, PDF, enregistrement.
    Retourne un dict avec le résultat.
    """
    # Numéro de facture
    numero, compteur = prochain_numero_facture(supabase)

    # Montants
    montants = calculer_montants()

    # Dates
    aujourdhui = date.today()
    echeance = aujourdhui + timedelta(days=DELAI_PAIEMENT_JOURS)

    # Période d'abonnement : 1 an à partir d'aujourd'hui
    periode_debut = aujourdhui
    periode_fin = date(aujourdhui.year + 1, aujourdhui.month, aujourdhui.day) \
        if not (aujourdhui.month == 2 and aujourdhui.day == 29) \
        else date(aujourdhui.year + 1, 3, 1)

    # Référence QR
    reference_qr = generer_reference_qr(compteur)

    # Construction du dict facture pour le PDF
    facture_pdf = {
        "numero": numero,
        "date_emission": aujourdhui.strftime("%d.%m.%Y"),
        "date_echeance": echeance.strftime("%d.%m.%Y"),
        "periode": f"{periode_debut.strftime('%d.%m.%Y')} – {periode_fin.strftime('%d.%m.%Y')}",
        "reference_qr": reference_qr,
        **montants,
        "client": {
            "nom_entreprise": client["nom_entreprise"],
            "contact_nom": client.get("contact_nom", ""),
            "adresse": client["adresse"],
            "npa": client["npa"],
            "ville": client["ville"],
        },
    }

    # Génération du PDF dans un dossier temporaire
    import tempfile
    nom_propre = nettoyer_nom_fichier(client["nom_entreprise"][:40])
    nom_fichier = f"{numero}_{nom_propre}.pdf"
    chemin_temp = os.path.join(tempfile.gettempdir(), nom_fichier)
    generer_facture(facture_pdf, emetteur, chemin_temp)

    # Upload du PDF vers Supabase Storage (bucket "factures")
    chemin_storage = f"{date.today().year}/{nom_fichier}"
    try:
        with open(chemin_temp, "rb") as f:
            supabase.storage.from_("factures").upload(
                path=chemin_storage,
                file=f.read(),
                file_options={"content-type": "application/pdf", "upsert": "true"},
            )
    except Exception as e:
        log(f"  ⚠ Erreur upload Storage : {str(e)[:120]}")
        return {"ok": False, "numero": numero, "erreur": f"upload: {e}"}
    finally:
        # On nettoie le fichier temporaire
        if os.path.exists(chemin_temp):
            os.remove(chemin_temp)

    # Enregistrement dans Supabase
    enregistrement = {
        "client_id": client["id"],
        "numero": numero,
        "montant_ht": montants["montant_ht"],
        "taux_tva": montants["taux_tva"],
        "montant_tva": montants["montant_tva"],
        "montant_ttc": montants["montant_ttc"],
        "date_emission": aujourdhui.isoformat(),
        "date_echeance": echeance.isoformat(),
        "periode_debut": periode_debut.isoformat(),
        "periode_fin": periode_fin.isoformat(),
        "statut": "emise",
        "reference_qr": reference_qr,
    }

    try:
        supabase.table("factures").insert(enregistrement).execute()
    except Exception as e:
        log(f"  ⚠ Erreur enregistrement Supabase : {str(e)[:120]}")
        return {"ok": False, "numero": numero, "erreur": str(e)}

    return {
        "ok": True,
        "numero": numero,
        "client": client["nom_entreprise"],
        "montant_ttc": montants["montant_ttc"],
        "fichier": chemin_storage,
    }


# ═══════════════════════════════════════════════════════
# MODE CRON — Renouvellements + premières factures
# ═══════════════════════════════════════════════════════

def a_deja_ete_facture(supabase: Client, client_id: str) -> bool:
    """Vérifie si un client a déjà reçu au moins une facture."""
    res = (
        supabase.table("factures")
        .select("id")
        .eq("client_id", client_id)
        .limit(1)
        .execute()
    )
    return bool(res.data)


def facture_existe_pour_periode(supabase: Client, client_id: str, annee: int) -> bool:
    """Vérifie qu'on n'a pas déjà facturé ce client cette année (anti-doublon)."""
    res = (
        supabase.table("factures")
        .select("id")
        .eq("client_id", client_id)
        .gte("date_emission", f"{annee}-01-01")
        .lte("date_emission", f"{annee}-12-31")
        .limit(1)
        .execute()
    )
    return bool(res.data)


def trouver_renouvellements(supabase: Client) -> list:
    """
    CAS 1 — Clients dont l'abonnement doit être renouvelé aujourd'hui
    (même jour/mois que la date de début d'abonnement, année antérieure).
    Pas de limite : un renouvellement est daté.
    """
    aujourdhui = date.today()
    res = (
        supabase.table("clients")
        .select("*")
        .eq("abo_actif", True)
        .execute()
    )

    a_facturer = []
    for client in res.data or []:
        debut = client.get("date_debut_abo")
        if not debut:
            continue
        debut_date = datetime.fromisoformat(debut).date()
        memejour = (debut_date.day == aujourdhui.day
                    and debut_date.month == aujourdhui.month)
        if memejour and debut_date.year < aujourdhui.year:
            # Anti-doublon : pas déjà facturé cette année
            if not facture_existe_pour_periode(supabase, client["id"], aujourdhui.year):
                a_facturer.append(client)

    return a_facturer


def trouver_premieres_factures(supabase: Client, limite: int) -> list:
    """
    CAS 2 — Nouveaux clients qui n'ont JAMAIS eu de facture.
    Limité à 'limite' clients par jour (les plus anciens d'abord).
    """
    res = (
        supabase.table("clients")
        .select("*")
        .eq("abo_actif", True)
        .order("cree_le")          # les plus anciennement ajoutés en premier
        .execute()
    )

    sans_facture = []
    for client in res.data or []:
        if not a_deja_ete_facture(supabase, client["id"]):
            sans_facture.append(client)
        if len(sans_facture) >= limite:
            break

    return sans_facture


def mode_cron():
    """Mode automatique : renouvellements (illimité) + premières factures (max 5/jour)."""
    log("=" * 50)
    log("🧾 AGENT FACTURATION — Mode CRON")
    log(f"   {datetime.now().strftime('%d.%m.%Y %H:%M')}")
    log(f"   Premières factures plafonnées à {MAX_PREMIERES_FACTURES_PAR_JOUR}/jour")
    log("=" * 50)

    if not all([SUPABASE_URL, SUPABASE_KEY]):
        log("❌ SUPABASE_URL ou SUPABASE_KEY manquant")
        return

    supabase = get_supabase()
    emetteur = get_emetteur()

    if not emetteur["qr_iban"]:
        log("❌ OQOO_QR_IBAN manquant — impossible de générer les QR-factures")
        return

    # ── CAS 1 : Renouvellements (date anniversaire) ──
    renouvellements = trouver_renouvellements(supabase)
    log(f"  CAS 1 — Renouvellements du jour : {len(renouvellements)}")

    # ── CAS 2 : Premières factures (nouveaux clients) ──
    premieres = trouver_premieres_factures(supabase, MAX_PREMIERES_FACTURES_PAR_JOUR)
    log(f"  CAS 2 — Premières factures à générer : {len(premieres)} "
        f"(max {MAX_PREMIERES_FACTURES_PAR_JOUR})")

    a_traiter = renouvellements + premieres
    if not a_traiter:
        log("  ℹ Aucune facture à générer aujourd'hui")
        log("✅ Terminé")
        return

    succes = 0
    for i, client in enumerate(a_traiter):
        type_facture = "renouvellement" if i < len(renouvellements) else "première"
        log(f"  → [{type_facture}] {client['nom_entreprise']}")
        resultat = facturer_client(supabase, client, emetteur)
        if resultat["ok"]:
            succes += 1
            log(f"    ✓ {resultat['numero']} — {resultat['montant_ttc']:.2f} CHF")
            log(f"    ✓ PDF : {resultat['fichier']}")
        else:
            log(f"    ✗ Échec : {resultat.get('erreur', 'inconnu')[:80]}")

    log("=" * 50)
    log(f"📊 RAPPORT")
    log(f"   Renouvellements : {len(renouvellements)}")
    log(f"   Premières factures : {len(premieres)}")
    log(f"   Total généré : {succes}/{len(a_traiter)}")
    log("=" * 50)
    log("✅ Terminé")


# ═══════════════════════════════════════════════════════
# MODE MANUEL — Facturer un client précis
# ═══════════════════════════════════════════════════════

def mode_manuel(client_id: str):
    """Mode manuel : génère une facture pour un client donné."""
    log("=" * 50)
    log("🧾 AGENT FACTURATION — Mode MANUEL")
    log("=" * 50)

    supabase = get_supabase()
    emetteur = get_emetteur()

    res = supabase.table("clients").select("*").eq("id", client_id).single().execute()
    if not res.data:
        log(f"❌ Client {client_id} introuvable")
        return

    client = res.data
    log(f"  Client : {client['nom_entreprise']}")
    resultat = facturer_client(supabase, client, emetteur)

    if resultat["ok"]:
        log(f"  ✓ Facture {resultat['numero']} générée")
        log(f"  ✓ Montant : {resultat['montant_ttc']:.2f} CHF TTC")
        log(f"  ✓ PDF : {resultat['fichier']}")
    else:
        log(f"  ✗ Échec : {resultat.get('erreur', 'inconnu')}")


# ═══════════════════════════════════════════════════════
# MAIN
# ═══════════════════════════════════════════════════════

if __name__ == "__main__":
    # Si un client_id est passé en argument → mode manuel
    # Sinon → mode cron (renouvellements du jour)
    if len(sys.argv) > 1:
        mode_manuel(sys.argv[1])
    else:
        mode_cron()
