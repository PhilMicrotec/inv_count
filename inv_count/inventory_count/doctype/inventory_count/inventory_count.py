# Copyright (c) 2025, Microtec and contributors
# For license information, please see license.txt

# import frappe
from frappe.model.document import Document


class InventoryCount(Document):
	pass


import frappe
import pandas as pd
import os # Pour gérer le chemin du fichier CSV

# --- Configuration ---
# Remplacez ces valeurs par les vôtres
PARENT_DOCTYPE = "MonDocumentParent"
PARENT_DOC_NAME = "MON-PARENT-001"  # Le nom/ID du document parent existant auquel vous voulez ajouter les données
CHILD_TABLE_FIELDNAME = "mes_elements" # Le nom du champ de la table enfant dans le Doctype parent
CHILD_DOCTYPE = "MonElementEnfant" # Le nom du Doctype de la table enfant
CSV_FILE_PATH = os.path.join(frappe.get_site_path(), "private", "files", "data.csv") # Chemin où votre CSV est stocké sur le serveur Frappe

# --- Fonction d'importation ---
@frappe.whitelist()
def import_csv_to_child_table():
    try:
        # 1. Vérifier si le fichier CSV existe
        if not os.path.exists(CSV_FILE_PATH):
            frappe.throw(f"Le fichier CSV est introuvable à l'emplacement : {CSV_FILE_PATH}")

        # 2. Lire le CSV avec Pandas
        df = pd.read_csv(CSV_FILE_PATH)

        # 3. Récupérer le document parent
        parent_doc = frappe.get_doc(PARENT_DOCTYPE, PARENT_DOC_NAME)

        # Assurez-vous que la liste des éléments de la table enfant est vide ou initialisée si vous voulez remplacer
        # Si vous voulez ajouter de nouvelles lignes sans supprimer les existantes, commentez la ligne suivante.
        # Si vous voulez vider et ajouter, décommentez.
        # parent_doc.set(CHILD_TABLE_FIELDNAME, []) # Vider la table enfant existante si nécessaire

        # 4. Parcourir les lignes du DataFrame et ajouter à la table enfant
        for index, row in df.iterrows():
            # Créez un dictionnaire pour chaque ligne, en mappant les noms de colonnes du CSV aux noms de champs du Doctype enfant
            child_row_data = {
                "item_code": row["item_code"],
                "item_name": row["item_name"],
                "quantity": row["quantity"],
                "rate": row["rate"],
                # Ajoutez d'autres champs de votre Doctype enfant si nécessaire
            }
            parent_doc.append(CHILD_TABLE_FIELDNAME, child_row_data)

        # 5. Sauvegarder le document parent
        parent_doc.save()
        frappe.db.commit() # Important pour persister les changements

        frappe.msgprint("Données importées avec succès dans la table enfant !")

    except Exception as e:
        frappe.log_error(frappe.get_traceback(), "Erreur lors de l'importation CSV")
        frappe.throw(f"Erreur lors de l'importation des données : {e}")

# --- Comment exécuter ce code ---
# Vous pouvez exécuter cette fonction de différentes manières :
# 1. Depuis la console Frappe (pour des tests rapides) :
#    frappe.get_doc('VotreDoctype', 'votre-nom-de-doc-ici').import_csv_to_child_table() # Si la fonction est une méthode du Doctype
#    ou
#    frappe.get_doc('VotreDoctype', 'votre-nom-de-doc-ici').run_method('import_csv_to_child_table')
#    ou
#    frappe.call("your_app.your_module.your_file.import_csv_to_child_table") # Si c'est une fonction autonome

# 2. En l'attachant à un bouton dans un Doctype personnalisé via une méthode de Doctype ou un script client.
# 3. Via un cron job si l'importation est régulière.