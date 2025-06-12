# Copyright (c) 2025, Microtec and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document
import pandas as pd
import os
import pymysql
import traceback # Import for more detailed error traceback

class InventoryCount(Document):
    pass

@frappe.whitelist()
def import_data_with_pandas(inventory_count_name):
    """
    Imports data into the 'inv_virtual_items' childtable of a specific 'Inventory Count' DocType
    based on the import source type (CSV or SQL Database) configured in the 'Inventory Count Settings' DocType.

    Args:
        inventory_count_name (str): The name/ID of the Inventory Count document to update.
    """
    parent_doctype = "Inventory Count"
    settings_doctype = "Inventory Count Settings"
    child_table_field_name = "inv_virtual_items"
    
    # 1. Get the Inventory Count document (the one being worked on)
    if not inventory_count_name or not frappe.db.exists(parent_doctype, inventory_count_name):
        frappe.throw(f"Document '{parent_doctype}' with name '{inventory_count_name}' not found.", title="Document Missing")
        return {"status": "error", "message": f"Document '{parent_doctype}' not found."}

    inventory_count_doc = frappe.get_doc(parent_doctype, inventory_count_name)
    frappe.msgprint(f"Importing virtual inventory for '{inventory_count_doc.name}'...", title="Import Status", indicator='blue')

    # 2. Get the Inventory Count Settings document
    try:
        settings_doc = frappe.get_doc(settings_doctype)
    except Exception:
        frappe.throw(f"'{settings_doctype}' document not found. Please configure your import settings first.", title="Settings Missing")

    try:
        df = pd.DataFrame() # Initialize an empty DataFrame
        
        # Determine import source type from settings
        import_source_type = settings_doc.import_source_type

        if import_source_type == "CSV":
            csv_file_path_relative = settings_doc.csv_file_path
            if not csv_file_path_relative:
                frappe.throw("CSV File Path is not specified in 'Inventory Count Settings'.", title="CSV Path Missing")

            # Resolve full path: assuming relative path is from app's root folder
            current_app_path = frappe.get_app_path('inv_count') # Assuming 'inv_count' is your app name
            csv_full_path = os.path.join(current_app_path, csv_file_path_relative)

            if not os.path.exists(csv_full_path):
                frappe.log_error(f"CSV file not found: {csv_full_path}", "Inventory Count Import Error")
                frappe.throw(f"Error: CSV file '{csv_file_path_relative}' not found at '{csv_full_path}'. Please check 'Inventory Count Settings'.", title="File Not Found")
            
            df = pd.read_csv(csv_full_path, encoding='iso-8859-1')
            frappe.msgprint(f"Successfully loaded data from CSV: {csv_full_path}", title="CSV Load Success", indicator='green')

        elif import_source_type == "SQL Database":
            # Retrieve SQL connection details from the Settings DocType
            sql_host = settings_doc.sql_host
            sql_port = settings_doc.sql_port
            sql_database = settings_doc.sql_database
            sql_username = settings_doc.sql_username
            sql_password = settings_doc.sql_password
            sql_query = settings_doc.sql_query

            # These are marked as required in the DocType, but a quick check here is good too
            if not all([sql_host, sql_database, sql_username, sql_query]):
                frappe.throw("Missing SQL connection details (Host, Database, Username, or Query) in 'Inventory Count Settings'.", title="SQL Details Missing")

            try:
                conn = pymysql.connect(
                    host=sql_host,
                    port=int(sql_port) if sql_port else 3306,
                    user=sql_username,
                    password=sql_password,
                    database=sql_database
                )
                frappe.msgprint(f"Successfully connected to SQL database: {sql_database} on {sql_host}:{sql_port}", title="SQL Connect Success", indicator='green')
                df = pd.read_sql(sql_query, conn)
                conn.close()
                frappe.msgprint("Successfully loaded data from SQL query.", title="SQL Load Success", indicator='green')

            except pymysql.Error as e:
                frappe.log_error(f"SQL Database connection/query error: {e}", "Inventory Count SQL Import Error")
                frappe.throw(f"SQL Database Error: {e}. Check your connection details and query in 'Inventory Count Settings'.", title="SQL Error")
            except Exception as e:
                frappe.log_error(f"General error during SQL import: {e}", "Inventory Count SQL Import Error")
                frappe.throw(f"An unexpected error occurred during SQL import: {e}", title="SQL Import Failed")

        else:
            frappe.throw("Invalid import source type selected in 'Inventory Count Settings'. Please choose 'CSV' or 'SQL Database'.", title="Invalid Source Type")

        # --- Common logic after DataFrame is loaded ---
        df = df.fillna(0)
        
        # Clear the childtable before adding new entries
        inventory_count_doc.set(child_table_field_name, [])

        # Iterate through each row of the DataFrame and add to the childtable
        for index, row in df.iterrows():
            child_item = inventory_count_doc.append(child_table_field_name, {})
            
            # Mappage des colonnes du DataFrame aux champs de la childtable 'inv_virtual_items'
            # Ensure column names from your CSV/SQL query match these
            try:
                child_item.location = row.get('Location', '')
                child_item.iv_item_recid = row.get('IV_Item_RecID', '')
                child_item.item_id = row.get('Item_ID', '')
                child_item.shortdescription = row.get('ShortDescription', '')
                child_item.category = row.get('Category', '')
                child_item.vendor_recid = row.get('Vendor_RecID', '')
                child_item.vendor_name = row.get('Vendor_Name', '')
                child_item.warehouse_recid = row.get('Warehouse_RecID', '')
                child_item.warehouse = row.get('Warehouse', '')
                child_item.warehouse_bin_recid = row.get('Warehouse_Bin_RecID', '')
                child_item.bin = row.get('Bin', '')
                child_item.qoh = row.get('QOH', 0)
                child_item.lasttransactiondate = row.get('LastTransactionDate', None)
                child_item.iv_audit_recid = row.get('IV_Audit_RecID', '')
                child_item.pickednotshipped = row.get('PickedNotShipped', 0)
                child_item.pickednotshippedcost = row.get('PickedNotShippedCost', 0.0)
                child_item.pickednotinvoiced = row.get('PickedNotInvoiced', 0)
                child_item.pickednotinvoicedcost = row.get('PickedNotInvoicedCost', 0.0)
                child_item.selectedcost = row.get('SelectedCost', 0.0)
                child_item.extendedcost = row.get('ExtendedCost', 0.0)
                child_item.snlist = row.get('SNList', '')
                # Add or adjust these mappings as per your actual data columns and child DocType fields

            except Exception as e:
                frappe.log_error(f"Error mapping data row: {row}. Error: {e}", "Inventory Count Data Mapping Error")
                frappe.throw(f"Error mapping data row to child table: {e}. Check your CSV/SQL column names and data types.", title="Data Mapping Error")


        inventory_count_doc.save()
        frappe.db.commit() # Ensure changes are persisted in the database

        frappe.msgprint(f"Importation terminée pour le document Inventory Count '{inventory_count_doc.name}'.", title="Importation réussie", indicator='green')
        return {"status": "success", "doc_name": inventory_count_doc.name}

    except Exception as e:
        frappe.db.rollback() # Rollback changes in case of error
        frappe.log_error(frappe.get_traceback(), "Erreur lors de l'importation de l'Inventory Count")
        traceback.print_exc() # For more detailed error trace in console
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
        return {"status": "success", "message": "Comparaison des inventaires terminée avec succès."}


    except Exception as e:
        frappe.log_error(frappe.get_traceback(), "Error in compare_child_tables")
        return {"status": "error", "message": f"Une erreur est survenue lors de la comparaison des tables : {e}"}

# --- NEW WHITELISTED WRAPPER FUNCTIONS FOR ENQUEUEING ---

@frappe.whitelist()
def enqueue_import_data(inventory_count_name):
    """
    Whitelisted wrapper to enqueue the import_data_with_pandas function.
    This function can be called from client-side JavaScript.
    """
    # Optional: Add a permission check here to ensure the user has rights
    # to trigger this action. For example:
    # if not frappe.has_permission('Inventory Count', 'write'):
    #     frappe.throw(frappe._("You do not have permission to trigger this import."), frappe.PermissionError)

    job = frappe.enqueue( # Store the Job object in a variable 'job'
        method='inv_count.inventory_count.doctype.inventory_count.inventory_count.import_data_with_pandas',
        queue='short',       # Use 'long' queue for potentially long-running imports
        timeout=300,      # Set a generous timeout (e.g., 15000 seconds = ~4 hours)
        is_async=True,
        # Arguments to pass to the actual `import_data_with_pandas` function
        inventory_count_name=inventory_count_name
    )
    # IMPORTANT: Return a dictionary containing the job's ID (which is a string, hence JSON serializable)
    return {'job_id': job.id}


@frappe.whitelist()
def enqueue_compare_tables(doc_name):
    frappe.log_error(f"Attempting to enqueue compare_tables for doc: {doc_name}", "Enqueue Debug")

    # Optional: Add a permission check here
    if not frappe.has_permission('Inventory Count', 'write'):
        frappe.throw(frappe._("You do not have permission to trigger this comparison."), frappe.PermissionError)

    try:
        job = frappe.enqueue(
            method='inv_count.inventory_count.doctype.inventory_count.inventory_count.compare_child_tables',
            queue='default',
            timeout=300,
            is_async=True,
            doc_name=doc_name
        )
        frappe.log_error(f"Job enqueued successfully: {job.id}", "Enqueue Debug")
        return {'job_id': job.id}
    except Exception as e:
        frappe.log_error(f"Error enqueuing job: {e}", "Enqueue Error")
        # Re-raise or return a specific error to the client if enqueueing fails
        frappe.throw(f"Failed to enqueue comparison job: {e}")
