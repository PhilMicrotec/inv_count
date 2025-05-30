# Copyright (c) 2025, Microtec and contributors
# For license information, please see license.txt

# import frappe
from frappe.model.document import Document # type: ignore


class InventoryCount(Document):
	pass

import frappe
import pandas as pd
import os

@frappe.whitelist()
def import_data_with_pandas(inventory_count_name=None):
    """
    Importe les données d'un fichier CSV (test.csv) situé dans le sous-dossier 'inv_count'
    de l'application dans la childtable 'inv_virtual_items' du DocType 'Inventory Count'.

    Cette fonction est conçue pour être exécutée côté serveur (par ex. via bench execute).

    Args:
        inventory_count_name (str, optional): Le nom/ID de l'Inventory Count existant.
                                            Si None, un nouvel Inventory Count sera créé.
                                            Par défaut à None.
    """
    parent_doctype = "Inventory Count"
    child_table_field_name = "inv_virtual_items"
    
    current_script_dir = frappe.get_app_path('inv_count')
    csv_file_path = os.path.join(current_script_dir, 'test.csv')

    if not os.path.exists(csv_file_path):
        frappe.log_error(f"Fichier CSV non trouvé à l'emplacement spécifié: {csv_file_path}", "Erreur d'importation Inventory Count")
        print(f"Erreur: Le fichier CSV n'a pas été trouvé à l'emplacement: {csv_file_path}")
        frappe.msgprint(f"Erreur: Le fichier CSV 'test.csv' est introuvable dans le dossier 'inv_count'.", title="Fichier introuvable", indicator='red')
        return {"status": "error", "message": f"Fichier CSV non trouvé: {csv_file_path}"}

    try:
        df = pd.read_csv(csv_file_path, encoding='latin', sep=',')
        
        df = df.fillna(0)
        
        frappe.msgprint(f"Lu {len(df)} lignes à partir de '{os.path.basename(csv_file_path)}'.", title="CSV Lu", indicator='blue')

        # Obtenir ou créer le document parent Inventory Count
        inventory_count_doc = None
        if inventory_count_name and frappe.db.exists(parent_doctype, inventory_count_name):
            inventory_count_doc = frappe.get_doc(parent_doctype, inventory_count_name)
            print(f"Document Inventory Count '{inventory_count_name}' trouvé.")
        else:
            inventory_count_doc = frappe.new_doc(parent_doctype)
            if inventory_count_name:
                inventory_count_doc.name = inventory_count_name


        # Vider la childtable avant d'ajouter de nouvelles entrées (optionnel)
        inventory_count_doc.set(child_table_field_name, [])

        # Parcourir chaque ligne du DataFrame et l'ajouter à la childtable
        for index, row in df.iterrows():
            child_item = inventory_count_doc.append(child_table_field_name, {})
            
            # Mappage des colonnes du CSV aux champs de la childtable 'inv_virtual_items'
            # Assurez-vous que ces noms correspondent aux colonnes de votre test.csv
            try:
                child_item.location = row['Location']
                child_item.iv_item_recid = row['IV_Item_RecID']
                child_item.item_id = row['Item_ID']
                child_item.shortdescription = row['ShortDescription']
                # Ajoutez d'autres mappings si votre CSV contient plus de colonnes nécessaires
                

            except KeyError as e:
                frappe.throw(f"Colonne manquante dans le CSV: **{e.args[0]}**. Veuillez vérifier l'en-tête de votre 'test.csv'.", title="Erreur de CSV")


        inventory_count_doc.save()
        frappe.db.commit() # S'assurer que les changements sont persistés dans la base de données

        frappe.msgprint(f"Importation terminée pour le document Inventory Count '{inventory_count_doc.name}'.", title="Importation réussie", indicator='green')
        return {"status": "success", "doc_name": inventory_count_doc.name}

    except Exception as e:
        frappe.db.rollback() # Annuler les changements en cas d'erreur
        frappe.log_error(frappe.get_traceback(), "Erreur lors de l'importation CSV pour Inventory Count")
        print(f"Une erreur est survenue lors de l'importation: {e}")
        import traceback
        traceback.print_exc() # Pour obtenir plus de détails sur l'erreur
        frappe.msgprint(f"Une erreur est survenue lors de l'importation: {e}", title="Erreur d'importation", indicator='red')
        return {"status": "error", "message": str(e)}
