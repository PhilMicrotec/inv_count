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
        df = pd.read_csv(csv_file_path, encoding='iso-8859-1')
        
        df = df.fillna(0)
        
        # Obtenir ou créer le document parent Inventory Count
        inventory_count_doc = None
        if inventory_count_name and frappe.db.exists(parent_doctype, inventory_count_name):
            inventory_count_doc = frappe.get_doc(parent_doctype, inventory_count_name)
            print(f"Document Inventory Count '{inventory_count_name}' trouvé.")
        else:
            print(f"Document not found")


        # Vider la childtable avant d'ajouter de nouvelles entrées (optionnel)
        inventory_count_doc.set(child_table_field_name, [])

        # Parcourir chaque ligne du DataFrame et l'ajouter à la childtable
        for index, row in df.iterrows():
            child_item = inventory_count_doc.append(child_table_field_name, {})
            
            # Mappage des colonnes du CSV aux champs de la childtable 'inv_virtual_items'
            try:
                child_item.location = row['Location']
                child_item.iv_item_recid = row['IV_Item_RecID']
                child_item.item_id = row['Item_ID']
                child_item.shortdescription = row['ShortDescription']
                child_item.category = row['Category']
                child_item.vendor_recid = row['Vendor_RecID']
                child_item.vendor_name = row['Vendor_Name']
                child_item.warehouse_recid = row['Warehouse_RecID']
                child_item.warehouse = row['Warehouse']
                child_item.warehouse_bin_recid = row['Warehouse_Bin_RecID']
                child_item.bin = row['Bin']
                child_item.qoh = row['QOH']
                child_item.lasttransactiondate = row['LastTransactionDate']
                child_item.iv_audit_recid = row['Warehouse_Bin_RecID']
                child_item.pickednotshipped = row['PickedNotShipped']
                child_item.pickednotshippedcost = row['PickedNotShippedCost']
                child_item.pickednotinvoiced = row['PickedNotInvoiced']
                child_item.pickednotinvoicedcost = row['PickedNotInvoicedCost']
                child_item.selectedcost = row['SelectedCost']
                child_item.extendedcost = row['ExtendedCost']
                child_item.snlist = row['SNList']
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

@frappe.whitelist()
def compare_child_tables(doc_name):
    """
    Compare 'inv_physical_items' and 'inv_virtual_items' child tables
    of an 'Inventory Count' document and populate the 'inv_difference' child table
    with any discrepancies, converting quantities to integers for comparison.

    Args:
        doc_name (str): The name of the 'Inventory Count' document.

    Returns:
        str: A message indicating the success or failure of the operation.
    """
    try:
        # Get the parent Inventory Count document
        doc = frappe.get_doc("Inventory Count", doc_name)

        # Get data from the two source child tables
        physical_items = doc.get("inv_physical_items")
        virtual_items = doc.get("inv_virtual_items")

        # Prepare dictionaries for easier lookup, converting quantities to int
        # Use int() with a default of 0 if the value is None or cannot be converted
        physical_items_map = {
            row.get("code"): int(row.get("qty") or 0)
            for row in physical_items
        }
        virtual_items_map = {
            row.get("item_id"): int(row.get("qoh") or 0)
            for row in virtual_items
        }
        description_item_map = {
            row.get("item_id"): row.get("shortdescription")
            for row in virtual_items
        }

        # Clear existing rows in inv_difference before adding new ones
        doc.set("inv_difference", [])

        # --- Compare Physical Items against Virtual Items ---
        for item_code, physical_qty_int in physical_items_map.items():
            if item_code is None:
                continue

            description = description_item_map[item_code]
            if item_code not in virtual_items_map:
                # Item found in physical but not in virtual
                doc.append("inv_difference", {
                    "item_code": item_code,
                    "description": description,
                    "physical_qty": physical_qty_int,
                    "virtual_qty": 0,
                    "difference_qty": physical_qty_int, # physical - 0
                    "difference_reason": "Article non trouvé dans l'inventaire virtuel"
                })
            else:
                virtual_qty_int = virtual_items_map[item_code]
                
                # Direct integer comparison
                if virtual_qty_int != physical_qty_int:
                    # Item found in both, but quantities mismatch
                    difference = physical_qty_int - virtual_qty_int
                    doc.append("inv_difference", {
                        "item_code": item_code,
                        "description": description,
                        "physical_qty": physical_qty_int,
                        "virtual_qty": virtual_qty_int,
                        "difference_qty": difference,
                        "difference_reason": "Quantité différente"
                    })

        # --- Compare Virtual Items against Physical Items (to find items only in virtual) ---
        for item_code, virtual_qty_int in virtual_items_map.items():
            if item_code is None:
                continue

            description = description_item_map[item_code]
            if item_code not in physical_items_map:
                # Item found in virtual but not in physical
                difference = 0 - virtual_qty_int # 0 - virtual
                doc.append("inv_difference", {
                    "item_code": item_code,
                    "description": description,
                    "physical_qty": 0,
                    "virtual_qty": virtual_qty_int,
                    "difference_qty": difference,
                    "difference_reason": "Article non trouvé dans l'inventaire physique"
                })

        # Save the parent document to persist changes in inv_difference
        doc.save()
        frappe.db.commit()


    except Exception as e:
        frappe.log_error(frappe.get_traceback(), "Error in compare_child_tables")
        return f"Une erreur est survenue lors de la comparaison des tables : {e}"
