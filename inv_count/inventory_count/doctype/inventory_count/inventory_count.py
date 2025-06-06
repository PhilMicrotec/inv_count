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
    Compares 'inv_physical_items' and 'inv_virtual_items' child tables
    of an 'Inventory Count' document and populates/updates the 'inv_difference' child table
    with any discrepancies. It will update existing rows if the item_code matches,
    or create new ones if not found.

    Args:
        doc_name (str): The name of the 'Inventory Count' document.

    Returns:
        str: A message indicating the success or failure of the operation.
    """
    try:
        doc = frappe.get_doc("Inventory Count", doc_name)

        physical_items = doc.get("inv_physical_items")
        virtual_items = doc.get("inv_virtual_items")

        physical_items_map = {
            row.get("code"): int(row.get("qty") or 0)
            for row in physical_items
        }
        virtual_items_map = {
            row.get("item_id"): int(row.get("qoh") or 0)
            for row in virtual_items
        }
        description_virtual_item_map = {
            row.get("item_id"): row.get("shortdescription")
            for row in virtual_items
        }
        description_physical_item_map = {
            row.get("code"): row.get("description")
            for row in physical_items
        }

        # Keep track of item_codes that were updated/created in inv_difference
        processed_difference_items = set()

        # --- Upsert logic for discrepancies based on Physical Items ---
        for item_code, physical_qty_int in physical_items_map.items():
            if item_code is None:
                continue

            # Default description if not found in virtual items (e.g., new item)
            description_physical = description_physical_item_map.get(item_code, "")
            virtual_qty_int = virtual_items_map.get(item_code, 0) # Get virtual qty, default to 0 if not found

            difference = physical_qty_int - virtual_qty_int
            
            # Only add to difference table if there's an actual difference
            if difference != 0:
                # Try to find an existing row in inv_difference for this item_code
                existing_row = None
                for row in doc.get("inv_difference"):
                    if row.item_code == item_code:
                        existing_row = row
                        break

                if existing_row:
                    # Update existing row
                    existing_row.description = description_physical
                    existing_row.physical_qty = physical_qty_int
                    existing_row.virtual_qty = virtual_qty_int
                    existing_row.difference_qty = difference
                    existing_row.difference_reason = "Quantité différente" if item_code in virtual_items_map else "Article non trouvé dans l'inventaire virtuel"
                    # Preserve 'confirmed' status if you have it
                    # existing_row.confirmed = existing_row.confirmed or 0
                else:
                    # Create new row
                    new_diff_item = doc.append("inv_difference", {})
                    new_diff_item.item_code = item_code
                    new_diff_item.description = description_physical
                    new_diff_item.physical_qty = physical_qty_int
                    new_diff_item.virtual_qty = virtual_qty_int
                    new_diff_item.difference_qty = difference
                    new_diff_item.difference_reason = "Quantité différente" if item_code in virtual_items_map else "Article non trouvé dans l'inventaire virtuel"
                    new_diff_item.confirmed = 0 # Default to unchecked for new differences

                processed_difference_items.add(item_code)

        # --- Upsert logic for items only in Virtual Items (not in Physical) ---
        for item_code, virtual_qty_int in virtual_items_map.items():
            if item_code is None or item_code in physical_items_map:
                # Skip if already processed or exists in physical items
                continue

            description_virtual = description_virtual_item_map.get(item_code, "")
            difference = 0 - virtual_qty_int # Item found in virtual but not in physical

            # Try to find an existing row in inv_difference for this item_code
            existing_row = None
            for row in doc.get("inv_difference"):
                if row.item_code == item_code:
                    existing_row = row
                    break

            if existing_row:
                # Update existing row
                existing_row.description = description_virtual
                existing_row.physical_qty = 0
                existing_row.virtual_qty = virtual_qty_int
                existing_row.difference_qty = difference
                existing_row.difference_reason = "Article non trouvé dans l'inventaire physique"
            else:
                # Create new row
                new_diff_item = doc.append("inv_difference", {})
                new_diff_item.item_code = item_code
                new_diff_item.description = description_virtual
                new_diff_item.physical_qty = 0
                new_diff_item.virtual_qty = virtual_qty_int
                new_diff_item.difference_qty = difference
                new_diff_item.difference_reason = "Article non trouvé dans l'inventaire physique"
                new_diff_item.confirmed = 0 # Default to unchecked for new differences

            processed_difference_items.add(item_code)


        # --- Remove rows from inv_difference that are no longer discrepancies ---
        # Iterate backwards to safely remove items while iterating
        items_to_remove = []
        for i in range(len(doc.get("inv_difference")) - 1, -1, -1):
            row = doc.get("inv_difference")[i]
            if row.item_code not in processed_difference_items:
                # If an item_code in inv_difference was not processed, it means
                # its difference has been resolved (physical_qty == virtual_qty)
                # or it no longer exists as a discrepancy.
                items_to_remove.append(row)
        
        for row_to_remove in items_to_remove:
            doc.remove(row_to_remove)

        doc.save()
        frappe.db.commit()


    except Exception as e:
        frappe.log_error(frappe.get_traceback(), "Error in compare_child_tables")
        return f"Une erreur est survenue lors de la comparaison des tables : {e}"