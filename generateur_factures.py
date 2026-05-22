"""
ANNUAIRE ROMAND — Générateur de factures PDF
─────────────────────────────────────────────
Génère une facture A4 professionnelle avec QR-facture suisse
conforme aux Swiss Implementation Guidelines (norme SIX).

Dépendances : reportlab (le QR est généré nativement)
"""

from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.lib.colors import HexColor, black, white
from reportlab.pdfgen import canvas
from reportlab.graphics.barcode import qr
from reportlab.graphics.shapes import Drawing
from reportlab.graphics import renderPDF
from datetime import date, timedelta


# ═══════════════════════════════════════════════════════
# COULEURS DE LA MARQUE
# ═══════════════════════════════════════════════════════
BLEU_NUIT = HexColor("#1a1a2e")
VIOLET    = HexColor("#534AB7")
GRIS      = HexColor("#888888")
GRIS_CLAIR = HexColor("#f5f5f7")


# ═══════════════════════════════════════════════════════
# CONSTRUCTION DU SWISS QR CODE
# ═══════════════════════════════════════════════════════

def construire_donnees_qr(facture: dict, emetteur: dict) -> str:
    """
    Construit la chaîne de données du Swiss QR Code selon la norme SIX.
    L'ordre des champs est STRICT et imposé par la norme.
    """
    debiteur = facture["client"]

    lignes = [
        "SPC",                          # QRType — toujours "SPC"
        "0200",                         # Version
        "1",                            # Codage UTF-8
        emetteur["qr_iban"].replace(" ", ""),  # IBAN du créancier

        # Créancier (adresse structurée, type "S")
        "S",
        emetteur["nom"],
        emetteur["rue"],
        emetteur["numero"],
        emetteur["npa"],
        emetteur["ville"],
        "CH",

        # Adresse ultime du créancier (vide)
        "", "", "", "", "", "", "",

        # Montant
        f"{facture['montant_ttc']:.2f}",
        "CHF",

        # Débiteur (le client, adresse structurée type "S")
        "S",
        debiteur["nom_entreprise"],
        debiteur["adresse"],
        "",                             # numéro inclus dans adresse
        debiteur["npa"],
        debiteur["ville"],
        "CH",

        # Type de référence + référence
        "QRR",                          # QRR = référence QR structurée
        facture["reference_qr"],

        # Communication libre
        f"Abonnement Annuaire Romand {facture['periode']}",

        # Trailer
        "EPD",
    ]
    return "\r\n".join(lignes)


def dessiner_qr(c: canvas.Canvas, donnees: str, x: float, y: float, taille: float):
    """Dessine le QR code à la position donnée."""
    widget = qr.QrCodeWidget(donnees, barLevel="M")
    bounds = widget.getBounds()
    largeur = bounds[2] - bounds[0]
    hauteur = bounds[3] - bounds[1]

    d = Drawing(taille, taille, transform=[taille / largeur, 0, 0, taille / hauteur, 0, 0])
    d.add(widget)
    renderPDF.draw(d, c, x, y)


# ═══════════════════════════════════════════════════════
# GÉNÉRATION DE LA FACTURE COMPLÈTE
# ═══════════════════════════════════════════════════════

def generer_facture(facture: dict, emetteur: dict, chemin_pdf: str):
    """
    Génère une facture A4 complète.

    facture : {
        numero, date_emission, date_echeance, periode,
        montant_ht, taux_tva, montant_tva, montant_ttc,
        reference_qr,
        client: { nom_entreprise, contact_nom, adresse, npa, ville }
    }
    emetteur : {
        nom, rue, numero, npa, ville, qr_iban, tva, email, telephone
    }
    """
    c = canvas.Canvas(chemin_pdf, pagesize=A4)
    largeur, hauteur = A4
    client = facture["client"]

    # ─────────────────────────────────────────
    # PARTIE HAUTE — LA FACTURE
    # ─────────────────────────────────────────

    # En-tête : bandeau bleu nuit
    c.setFillColor(BLEU_NUIT)
    c.rect(0, hauteur - 45 * mm, largeur, 45 * mm, fill=1, stroke=0)

    c.setFillColor(white)
    c.setFont("Helvetica-Bold", 22)
    c.drawString(20 * mm, hauteur - 22 * mm, "FACTURE")

    c.setFont("Helvetica", 10)
    c.drawString(20 * mm, hauteur - 30 * mm, f"N° {facture['numero']}")
    c.drawString(20 * mm, hauteur - 35 * mm, f"Date : {facture['date_emission']}")

    # Logo / nom émetteur (en haut à droite)
    c.setFont("Helvetica-Bold", 16)
    c.drawRightString(largeur - 20 * mm, hauteur - 20 * mm, emetteur["nom"])
    c.setFont("Helvetica", 8)
    c.drawRightString(largeur - 20 * mm, hauteur - 26 * mm,
                      f"{emetteur['rue']} {emetteur['numero']}")
    c.drawRightString(largeur - 20 * mm, hauteur - 30 * mm,
                      f"{emetteur['npa']} {emetteur['ville']}")
    c.drawRightString(largeur - 20 * mm, hauteur - 34 * mm, emetteur["tva"])

    # Bloc destinataire
    y = hauteur - 65 * mm
    c.setFillColor(GRIS)
    c.setFont("Helvetica", 8)
    c.drawString(20 * mm, y + 12 * mm, "FACTURÉ À")

    c.setFillColor(black)
    c.setFont("Helvetica-Bold", 11)
    c.drawString(20 * mm, y + 6 * mm, client["nom_entreprise"])
    c.setFont("Helvetica", 10)
    ligne = y
    if client.get("contact_nom"):
        c.drawString(20 * mm, ligne, client["contact_nom"])
        ligne -= 5 * mm
    c.drawString(20 * mm, ligne, client["adresse"])
    ligne -= 5 * mm
    c.drawString(20 * mm, ligne, f"{client['npa']} {client['ville']}")

    # Période + échéance (à droite)
    c.setFillColor(GRIS)
    c.setFont("Helvetica", 8)
    c.drawRightString(largeur - 20 * mm, y + 12 * mm, "PÉRIODE D'ABONNEMENT")
    c.setFillColor(black)
    c.setFont("Helvetica", 10)
    c.drawRightString(largeur - 20 * mm, y + 6 * mm, facture["periode"])
    c.setFillColor(GRIS)
    c.setFont("Helvetica", 8)
    c.drawRightString(largeur - 20 * mm, y - 2 * mm, "ÉCHÉANCE")
    c.setFillColor(black)
    c.setFont("Helvetica", 10)
    c.drawRightString(largeur - 20 * mm, y - 8 * mm, facture["date_echeance"])

    # ─────────────────────────────────────────
    # TABLEAU DES PRESTATIONS
    # ─────────────────────────────────────────
    y_tab = hauteur - 105 * mm

    # En-tête du tableau
    c.setFillColor(BLEU_NUIT)
    c.rect(20 * mm, y_tab, largeur - 40 * mm, 9 * mm, fill=1, stroke=0)
    c.setFillColor(white)
    c.setFont("Helvetica-Bold", 9)
    c.drawString(24 * mm, y_tab + 3 * mm, "DÉSIGNATION")
    c.drawRightString(largeur - 24 * mm, y_tab + 3 * mm, "MONTANT")

    # Ligne de prestation
    c.setFillColor(black)
    c.setFont("Helvetica", 10)
    y_ligne = y_tab - 10 * mm
    c.drawString(24 * mm, y_ligne,
                 f"Abonnement annuel — Annuaire Romand ({facture['periode']})")
    c.drawRightString(largeur - 24 * mm, y_ligne,
                      f"CHF {facture['montant_ht']:.2f}")

    c.setStrokeColor(GRIS_CLAIR)
    c.line(20 * mm, y_ligne - 4 * mm, largeur - 20 * mm, y_ligne - 4 * mm)

    # Totaux
    y_tot = y_ligne - 14 * mm
    c.setFont("Helvetica", 10)
    c.drawRightString(largeur - 55 * mm, y_tot, "Sous-total HT")
    c.drawRightString(largeur - 24 * mm, y_tot, f"CHF {facture['montant_ht']:.2f}")

    y_tot -= 6 * mm
    c.drawRightString(largeur - 55 * mm, y_tot,
                      f"TVA {facture['taux_tva']:.1f}%")
    c.drawRightString(largeur - 24 * mm, y_tot, f"CHF {facture['montant_tva']:.2f}")

    y_tot -= 9 * mm
    c.setFillColor(VIOLET)
    c.rect(largeur - 95 * mm, y_tot - 3 * mm, 75 * mm, 10 * mm, fill=1, stroke=0)
    c.setFillColor(white)
    c.setFont("Helvetica-Bold", 11)
    c.drawString(largeur - 91 * mm, y_tot, "TOTAL À PAYER")
    c.drawRightString(largeur - 24 * mm, y_tot, f"CHF {facture['montant_ttc']:.2f}")

    # Conditions de paiement
    c.setFillColor(GRIS)
    c.setFont("Helvetica", 8)
    c.drawString(20 * mm, y_tot - 20 * mm,
                 f"Paiement à 30 jours. Merci de scanner le QR-code ci-dessous "
                 f"avec votre application bancaire.")
    c.drawString(20 * mm, y_tot - 25 * mm,
                 f"Référence : {facture['reference_qr']}")

    # ─────────────────────────────────────────
    # PARTIE BASSE — LA QR-FACTURE (105mm de haut)
    # ─────────────────────────────────────────
    qr_zone_h = 105 * mm

    # Ligne de séparation (ciseaux)
    c.setStrokeColor(GRIS)
    c.setDash(2, 2)
    c.line(0, qr_zone_h, largeur, qr_zone_h)
    c.setDash()
    c.setFillColor(GRIS)
    c.setFont("Helvetica", 7)
    c.drawCentredString(largeur / 2, qr_zone_h + 2 * mm,
                        "✂ Séparer avant le versement")

    # ── Section RÉCÉPISSÉ (gauche, 62mm) ──
    x_rec = 5 * mm
    c.setFillColor(black)
    c.setFont("Helvetica-Bold", 11)
    c.drawString(x_rec, qr_zone_h - 7 * mm, "Récépissé")

    c.setFont("Helvetica-Bold", 6)
    c.drawString(x_rec, qr_zone_h - 14 * mm, "Compte / Payable à")
    c.setFont("Helvetica", 8)
    c.drawString(x_rec, qr_zone_h - 18 * mm, emetteur["qr_iban"])
    c.drawString(x_rec, qr_zone_h - 22 * mm, emetteur["nom"])
    c.drawString(x_rec, qr_zone_h - 26 * mm,
                 f"{emetteur['rue']} {emetteur['numero']}")
    c.drawString(x_rec, qr_zone_h - 30 * mm,
                 f"{emetteur['npa']} {emetteur['ville']}")

    c.setFont("Helvetica-Bold", 6)
    c.drawString(x_rec, qr_zone_h - 37 * mm, "Référence")
    c.setFont("Helvetica", 8)
    c.drawString(x_rec, qr_zone_h - 41 * mm, facture["reference_qr"])

    c.setFont("Helvetica-Bold", 6)
    c.drawString(x_rec, qr_zone_h - 48 * mm, "Payable par")
    c.setFont("Helvetica", 8)
    c.drawString(x_rec, qr_zone_h - 52 * mm, client["nom_entreprise"])
    c.drawString(x_rec, qr_zone_h - 56 * mm, client["adresse"])
    c.drawString(x_rec, qr_zone_h - 60 * mm,
                 f"{client['npa']} {client['ville']}")

    c.setFont("Helvetica-Bold", 6)
    c.drawString(x_rec, qr_zone_h - 70 * mm, "Monnaie")
    c.drawString(x_rec + 20 * mm, qr_zone_h - 70 * mm, "Montant")
    c.setFont("Helvetica", 8)
    c.drawString(x_rec, qr_zone_h - 74 * mm, "CHF")
    c.drawString(x_rec + 20 * mm, qr_zone_h - 74 * mm,
                 f"{facture['montant_ttc']:.2f}")

    c.setFont("Helvetica-Bold", 6)
    c.drawString(x_rec, qr_zone_h - 84 * mm, "Point de dépôt")

    # Trait vertical de séparation récépissé / section paiement
    c.setStrokeColor(GRIS)
    c.setDash(2, 2)
    c.line(62 * mm, 0, 62 * mm, qr_zone_h)
    c.setDash()

    # ── Section PAIEMENT (centre/droite) ──
    x_pay = 67 * mm
    c.setFillColor(black)
    c.setFont("Helvetica-Bold", 11)
    c.drawString(x_pay, qr_zone_h - 7 * mm, "Section paiement")

    # Le QR code (46x46 mm, avec la croix suisse au centre)
    donnees_qr = construire_donnees_qr(facture, emetteur)
    dessiner_qr(c, donnees_qr, x_pay, qr_zone_h - 60 * mm, 46 * mm)

    # Croix suisse au centre du QR (obligatoire)
    cx, cy = x_pay + 23 * mm, qr_zone_h - 60 * mm + 23 * mm
    c.setFillColor(white)
    c.rect(cx - 3.5 * mm, cy - 3.5 * mm, 7 * mm, 7 * mm, fill=1, stroke=0)
    c.setFillColor(black)
    c.rect(cx - 3 * mm, cy - 3 * mm, 6 * mm, 6 * mm, fill=1, stroke=0)
    c.setFillColor(white)
    c.rect(cx - 1.7 * mm, cy - 0.6 * mm, 3.4 * mm, 1.2 * mm, fill=1, stroke=0)
    c.rect(cx - 0.6 * mm, cy - 1.7 * mm, 1.2 * mm, 3.4 * mm, fill=1, stroke=0)

    # Montant sous le QR
    c.setFillColor(black)
    c.setFont("Helvetica-Bold", 8)
    c.drawString(x_pay, qr_zone_h - 70 * mm, "Monnaie")
    c.drawString(x_pay + 22 * mm, qr_zone_h - 70 * mm, "Montant")
    c.setFont("Helvetica", 10)
    c.drawString(x_pay, qr_zone_h - 75 * mm, "CHF")
    c.drawString(x_pay + 22 * mm, qr_zone_h - 75 * mm,
                 f"{facture['montant_ttc']:.2f}")

    # ── Section informations (droite) ──
    x_inf = 118 * mm
    c.setFont("Helvetica-Bold", 8)
    c.drawString(x_inf, qr_zone_h - 7 * mm, "Compte / Payable à")
    c.setFont("Helvetica", 8)
    c.drawString(x_inf, qr_zone_h - 11 * mm, emetteur["qr_iban"])
    c.drawString(x_inf, qr_zone_h - 15 * mm, emetteur["nom"])
    c.drawString(x_inf, qr_zone_h - 19 * mm,
                 f"{emetteur['rue']} {emetteur['numero']}")
    c.drawString(x_inf, qr_zone_h - 23 * mm,
                 f"{emetteur['npa']} {emetteur['ville']}")

    c.setFont("Helvetica-Bold", 8)
    c.drawString(x_inf, qr_zone_h - 31 * mm, "Référence")
    c.setFont("Helvetica", 8)
    c.drawString(x_inf, qr_zone_h - 35 * mm, facture["reference_qr"])

    c.setFont("Helvetica-Bold", 8)
    c.drawString(x_inf, qr_zone_h - 43 * mm,
                 "Informations supplémentaires")
    c.setFont("Helvetica", 8)
    c.drawString(x_inf, qr_zone_h - 47 * mm,
                 f"Abonnement Annuaire Romand {facture['periode']}")

    c.setFont("Helvetica-Bold", 8)
    c.drawString(x_inf, qr_zone_h - 55 * mm, "Payable par")
    c.setFont("Helvetica", 8)
    c.drawString(x_inf, qr_zone_h - 59 * mm, client["nom_entreprise"])
    c.drawString(x_inf, qr_zone_h - 63 * mm, client["adresse"])
    c.drawString(x_inf, qr_zone_h - 67 * mm,
                 f"{client['npa']} {client['ville']}")

    c.save()
    return chemin_pdf


# ═══════════════════════════════════════════════════════
# TEST / DÉMONSTRATION
# ═══════════════════════════════════════════════════════

if __name__ == "__main__":
    emetteur_demo = {
        "nom": "OQOO",
        "rue": "Rue du Commerce",
        "numero": "12",
        "npa": "1200",
        "ville": "Genève",
        "qr_iban": "CH44 3199 9123 0008 8901 2",
        "tva": "CHE-123.456.789 TVA",
        "email": "contact@oqoo.ch",
        "telephone": "+41 22 000 00 00",
    }

    facture_demo = {
        "numero": "2026-0001",
        "date_emission": "22.05.2026",
        "date_echeance": "21.06.2026",
        "periode": "2026 – 2027",
        "montant_ht": 36.96,
        "taux_tva": 8.10,
        "montant_tva": 2.99,
        "montant_ttc": 39.95,
        "reference_qr": "21 00000 00003 13947 14300 09017",
        "client": {
            "nom_entreprise": "Boulangerie Dupont Sàrl",
            "contact_nom": "M. Jean Dupont",
            "adresse": "Avenue de la Gare 45",
            "npa": "1003",
            "ville": "Lausanne",
        },
    }

    generer_facture(facture_demo, emetteur_demo, "/tmp/facture_demo.pdf")
    print("✅ Facture de démonstration générée : /tmp/facture_demo.pdf")
