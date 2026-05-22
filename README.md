# Annuaire Romand — Agent de facturation

Génère les factures annuelles d'abonnement (39.95 CHF HT + TVA 8.1%)
avec QR-facture suisse, au format PDF.

## Fonctionnement

- **Mode CRON** (automatique, 6h UTC) : génère les renouvellements
  du jour + jusqu'à 5 premières factures de nouveaux clients.
- **Mode MANUEL** : `python agent_facturation.py <client_id>`

## Variables d'environnement requises

| Variable | Description |
|----------|-------------|
| SUPABASE_URL | URL du projet Supabase |
| SUPABASE_KEY | Clé Supabase |
| OQOO_NOM | Raison sociale (ex: OQOO Sàrl) |
| OQOO_RUE | Rue |
| OQOO_NUMERO | Numéro de rue |
| OQOO_NPA | Code postal |
| OQOO_VILLE | Ville |
| OQOO_QR_IBAN | QR-IBAN OQOO |
| OQOO_TVA | Numéro TVA (ex: CHE-123.456.789 TVA) |
| OQOO_EMAIL | Email de contact |
| OQOO_TELEPHONE | Téléphone |
