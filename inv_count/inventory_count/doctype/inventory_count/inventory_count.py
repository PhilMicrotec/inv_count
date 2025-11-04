# Copyright (c) 2025, Microtec and contributors
# For license information, please see license.txt

import frappe
from frappe import _ # Import for translation support
from frappe.model.document import Document
import pandas as pd
import os
import pyodbc
import traceback # Import for more detailed error traceback
import requests
import base64
import json
from frappe.utils import get_datetime, get_timestamp
import re

class InventoryCount(Document):
    pass

cwAPI_version="2025.8" # Define the ConnectWise API version to use throughout the code

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
        frappe.throw(_("Document '{0}' with name '{1}' not found.").format(parent_doctype, inventory_count_name), title=_("Document Missing"))
        return {"status": "error", "message": _("Document '{0}' not found.").format(parent_doctype)}

    inventory_count_doc = frappe.get_doc(parent_doctype, inventory_count_name)

    # 2. Get the Inventory Count Settings document
    try:
        settings_doc = frappe.get_doc(settings_doctype)
    except Exception:
        frappe.throw(_("'{0}' document not found. Please configure your import settings first.").format(settings_doctype), title=_("Settings Missing"))

    try:
        df = pd.DataFrame() # Initialize an empty DataFrame
        
        # Determine import source type from settings
        import_source_type = settings_doc.import_source_type

        if import_source_type == "CSV":
            csv_file_path_relative = settings_doc.csv_file_path
            if not csv_file_path_relative:
                frappe.throw(_("CSV File Path is not specified in 'Inventory Count Settings'."), title=_("CSV Path Missing"))

            # Resolve full path: assuming relative path is from app's root folder
            current_app_path = frappe.get_app_path('inv_count') # Assuming 'inv_count' is your app name
            csv_full_path = os.path.join(current_app_path, csv_file_path_relative)

            if not os.path.exists(csv_full_path):
                frappe.log_error(f"CSV file not found: {csv_full_path}", "Inventory Count Import Error") # Internal log, not for translation
                frappe.throw(_("Error: CSV file '{0}' not found at '{1}'. Please check 'Inventory Count Settings'.").format(csv_file_path_relative, csv_full_path), title=_("File Not Found"))
            
            df = pd.read_csv(csv_full_path, encoding='iso-8859-1')

        elif import_source_type == "SQL Database":

            warehouse_id_split=inventory_count_doc.warehouse.split('(')[1]
            warehouse_id = warehouse_id_split.split(')')[0]
            warehouse_bin_id_split = inventory_count_doc.warehouse_bin.split('(')[1]
            warehouse_bin_id = warehouse_bin_id_split.split(')')[0]
            valuation_date = inventory_count_doc.date.strftime('"%Y-%m-%d"')

            # Retrieve SQL connection details from the Settings DocType
            sql_host = settings_doc.sql_host
            sql_port = settings_doc.sql_port
            sql_database = settings_doc.sql_database
            sql_username = settings_doc.sql_username
            sql_password = settings_doc.get_password('sql_password')
            sql_query = settings_doc.sql_query

            sql_query = sql_query.replace("{warehouse_id}", warehouse_id).replace("{warehouse_bin_id}", warehouse_bin_id).replace("{valuation_date}", valuation_date)

            # These are marked as required in the DocType, but a quick check here is good too
            if not all([sql_host, sql_database, sql_username, sql_query]):
                frappe.throw(_("Missing SQL connection details (Host, Database, Username, or Query) in 'Inventory Count Settings'."), title=_("SQL Details Missing"))

            try:
                conn_str = f"DRIVER={{ODBC Driver 17 for SQL Server}};SERVER={sql_host},{sql_port};DATABASE={sql_database};UID={sql_username};PWD={sql_password};TrustServerCertificate=yes;Encrypt=yes"
                conn = pyodbc.connect(conn_str)
                df = pd.read_sql_query(sql_query, conn)
                conn.close()

            except pyodbc.Error as e:
                frappe.log_error(f"SQL Database connection/query error: {e}", "Inventory Count SQL Import Error") # Internal log, not for translation
                frappe.throw(_("SQL Database Error: {0}. Check your connection details and query in 'Inventory Count Settings'.").format(e), title=_("SQL Error"))
            except Exception as e:
                frappe.log_error(f"General error during SQL import: {e}", "Inventory Count SQL Import Error") # Internal log, not for translation
                frappe.throw(_("An unexpected error occurred during SQL import: {0}").format(e), title=_("SQL Import Failed"))

        else:
            frappe.throw(_("Invalid import source type selected in 'Inventory Count Settings'. Please choose 'CSV' or 'SQL Database'."), title=_("Invalid Source Type"))

        # --- Common logic after DataFrame is loaded ---
        df = df.fillna(0)
        
        # Clear the childtable before adding new entries
        inventory_count_doc.set(child_table_field_name, [])

        qoh_calculation_type = settings_doc.get('qty_calculation_type', 'QOH + Picked') 

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
                if qoh_calculation_type == 'QOH':
                    child_item.qty = row.get('QOH', 0)
                elif qoh_calculation_type == 'QOH+PickedNotShipped': 
                    child_item.qty = row.get('QOH', 0) + row.get('PickedNotShipped', 0) 
                elif qoh_calculation_type == 'QOH+PickedNotInvoiced': 
                    child_item.qty = row.get('QOH', 0) + row.get('PickedNotInvoiced', 0)
                elif qoh_calculation_type == 'QOH+PickedNotShipped+PickedNotInvoiced': 
                    child_item.qty = row.get('QOH', 0) + row.get('PickedNotShipped', 0) + row.get('PickedNotInvoiced', 0)
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
                frappe.log_error(f"Error mapping data row: {row}. Error: {e}", "Inventory Count Data Mapping Error") # Internal log, not for translation
                frappe.throw(_("Error mapping data row to child table: {0}. Check your CSV/SQL column names and data types.").format(e), title=_("Data Mapping Error"))

        inventory_count_doc.save()
        frappe.db.commit() # Ensure changes are persisted in the database

        return {"status": "success", "message": _("Import completed successfully. {0} items imported.").format(len(inventory_count_doc.get(child_table_field_name)))} # This is a translatable user-facing message

    except Exception as e:
        frappe.db.rollback() # Rollback changes in case of error
        frappe.log_error(frappe.get_traceback(), "Error during Inventory Count import") # Changed log category to English
        traceback.print_exc() # For more detailed error trace in console
        frappe.msgprint(_("An error occurred during import: {0}").format(e), title=_("Import Error"), indicator='red')
        #frappe.publish_realtime("Import Error", {"message": str(e)}) # This is an event payload, not a translatable user-facing message
        return {"status": "error", "message": str(e)}


@frappe.whitelist()
def compare_child_tables(doc_name):
    """
    Compares 'inv_physical_items' and 'inv_virtual_items' child tables
    of an 'Inventory Count' document and populates/updates the 'inv_difference' child table
    with any discrepancies. It will update existing rows if the item_code matches,
    or create new ones if not found, preserving the 'confirmed' status.

    Allows comparison to be filtered by the main 'category' field on the Inventory Count document.
    If 'category' is empty, all items are compared.

    Additionally, if a product added to 'inv_difference' has serial numbers in
    'inv_virtual_items', these serial numbers will populate/update the 'inv_difference_sn'
    child table, linking them to the 'item_code' and PRESERVING existing 'to_do' statuses.
    """
    try:
        doc = frappe.get_doc("Inventory Count", doc_name)

        main_category_filter = doc.get("category")
        
        all_physical_items = doc.get("inv_physical_items")
        all_virtual_items = doc.get("inv_virtual_items")

        existing_confirmed_status_map = {
            row.item_code: row.confirmed
            for row in doc.get("inv_difference") if row.item_code
        }

        # Map to store SNList for virtual items
        virtual_item_snlist_map = {
            row.get("item_id"): row.get("snlist")
            for row in all_virtual_items if row.get("item_id")
        }

        physical_items_to_compare = []
        virtual_items_to_compare = []

        # Decide which items to compare based on the category filter
        if main_category_filter:
            # Filter virtual items by the selected category
            virtual_items_to_compare = [
                item for item in all_virtual_items if item.category == main_category_filter
            ]
            
            # If physical items should *also* be filtered by category:
            physical_items_to_compare = [
                item for item in all_physical_items 
            ]
        else:
            physical_items_to_compare = all_physical_items
            virtual_items_to_compare = all_virtual_items

        # Build maps from the *filtered* or *all* lists
        physical_items_map = {
            row.get("code"): int(row.get("qty") or 0)
            for row in physical_items_to_compare
        }
        virtual_items_map = {
            row.get("item_id"): int(row.get("qty") or 0)
            for row in virtual_items_to_compare
        }
        description_virtual_item_map = {
            row.get("item_id"): row.get("shortdescription")
            for row in virtual_items_to_compare
        }
        description_physical_item_map = {
            row.get("code"): row.get("description")
            for row in physical_items_to_compare
        }
        virtual_item_Recid = {
            row.get("item_id"): row.get("iv_item_recid")
            for row in all_virtual_items if row.get("item_id")
        }

        # Keep track of item_codes that were updated/created in inv_difference
        processed_difference_items = set()

        # --- MODIFIED: Store existing inv_difference_sn data to preserve 'to_do' ---
        # Also, pre-populate the final list with existing rows that have a 'Remove/Add' status
        existing_sn_data_map = {} 
        preserved_sn_rows = []
        preserved_sn_keys = set() # To ensure uniqueness for preserved rows

        for sn_row in doc.get("inv_difference_sn"):
            sn_key = (sn_row.get("product"), sn_row.get("serial_number"))
            if sn_key[0] and sn_key[1]: # Ensure both product and serial_number exist
                existing_sn_data_map[sn_key] = {
                    "to_do": sn_row.get("to_do"),
                    # Add any other fields you want to preserve here
                }
                # If an existing row has 'Add/Remove' status, we want to explicitly preserve it
                if sn_row.get("to_do") == "Remove/Add":
                    preserved_sn_rows.append(sn_row)
                    preserved_sn_keys.add(sn_key) # Add to set to mark as seen

        # Initialize updated_inv_difference_sn. We will populate this with new differences.
        updated_inv_difference_sn_new_entries = []
        # --- END MODIFIED ---

        # --- Upsert logic for discrepancies based on Physical Items (from the items selected for comparison) ---
        for item_code, physical_qty_int in physical_items_map.items():
            if item_code is None:
                continue

            description_physical = description_physical_item_map.get(item_code, "")
            virtual_qty_int = virtual_items_map.get(item_code, 0) # Will be 0 if not found in virtual_items_to_compare

            difference = physical_qty_int - virtual_qty_int

            RecID_from_virtual = virtual_item_Recid.get(item_code, "")
            
            if difference != 0:
                # Try to find an existing row in inv_difference for this item_code
                existing_row_diff = None
                for row in doc.get("inv_difference"):
                    if row.item_code == item_code:
                        existing_row_diff = row
                        break

                if existing_row_diff:
                    # Update existing row
                    existing_row_diff.description = description_physical
                    existing_row_diff.physical_qty = physical_qty_int
                    existing_row_diff.virtual_qty = virtual_qty_int
                    existing_row_diff.difference_qty = difference
                    existing_row_diff.difference_reason = _("Quantité différente") if item_code in virtual_items_map else _("Article non trouvé dans l'inventaire virtuel")
                    existing_row_diff.recid = RecID_from_virtual
                else:
                    # Create new row
                    new_diff_item = doc.append("inv_difference", {})
                    new_diff_item.item_code = item_code
                    new_diff_item.description = description_physical
                    new_diff_item.physical_qty = physical_qty_int
                    new_diff_item.virtual_qty = virtual_qty_int
                    new_diff_item.difference_qty = difference
                    new_diff_item.difference_reason = _("Quantité différente") if item_code in virtual_items_map else _("Article non trouvé dans l'inventaire virtuel")
                    new_diff_item.confirmed = existing_confirmed_status_map.get(item_code, 0)
                    new_diff_item.recid = RecID_from_virtual

                processed_difference_items.add(item_code)

                # --- MODIFIED: Populate/Update inv_difference_sn for this item ---
                snlist_str = virtual_item_snlist_map.get(item_code)
                if snlist_str and snlist_str != '0':
                    serial_numbers = [sn.strip() for sn in snlist_str.split(',') if sn.strip()]
                    for sn in serial_numbers:
                        sn_key = (item_code, sn)
                        
                        # Create a new row data (will be added to the temporary list)
                        new_sn_row_data = {
                            "product": item_code,
                            "serial_number": sn
                        }
                        
                        # Preserve 'to_do' status if it existed for this serial
                        if sn_key in existing_sn_data_map:
                            new_sn_row_data["to_do"] = existing_sn_data_map[sn_key]["to_do"]
                        # else: new_sn_row_data["to_do"] will default to whatever its default value is (usually None/empty)
                        
                        updated_inv_difference_sn_new_entries.append(new_sn_row_data)
                # --- END MODIFIED ---


        # --- Upsert logic for items only in Virtual Items (from the items selected for comparison, not in Physical's selected list) ---
        for item_code, virtual_qty_int in virtual_items_map.items():
            if item_code is None or item_code in physical_items_map:
                continue # Skip if already processed or exists in physical items map

            description_virtual = description_virtual_item_map.get(item_code, "")
            difference = 0 - virtual_qty_int # Item found in virtual but not in physical (in this comparison scope)

            physical_qty_int = physical_items_map.get(item_code, 0)

            RecID_from_virtual = virtual_item_Recid.get(item_code, "")

            # Always iterate to find existing row now, as we don't clear the table
            existing_row_diff = None
            for row in doc.get("inv_difference"):
                if row.item_code == item_code:
                    existing_row_diff = row
                    break

            if existing_row_diff:
                # Update existing row
                existing_row_diff.description = description_virtual
                existing_row_diff.physical_qty = physical_qty_int
                existing_row_diff.virtual_qty = virtual_qty_int
                existing_row_diff.difference_qty = difference
                existing_row_diff.difference_reason = _("Article non trouvé dans l'inventaire physique")
                existing_row_diff.recid = RecID_from_virtual
                # existing_row_diff.confirmed is implicitly preserved here
            else:
                # Create new row
                new_diff_item = doc.append("inv_difference", {})
                new_diff_item.item_code = item_code
                new_diff_item.description = description_virtual
                new_diff_item.physical_qty = physical_qty_int
                new_diff_item.virtual_qty = virtual_qty_int
                new_diff_item.difference_qty = difference
                new_diff_item.difference_reason = _("Article non trouvé dans l'inventaire physique")
                new_diff_item.confirmed = existing_confirmed_status_map.get(item_code, 0)
                new_diff_item.recid = RecID_from_virtual
                
            processed_difference_items.add(item_code)

            # --- MODIFIED: Populate/Update inv_difference_sn for this item ---
            snlist_str = virtual_item_snlist_map.get(item_code)
            if snlist_str and snlist_str != '0':
                serial_numbers = [sn.strip() for sn in snlist_str.split(',') if sn.strip()]
                for sn in serial_numbers:
                    sn_key = (item_code, sn)
                    
                    new_sn_row_data = {
                        "product": item_code,
                        "serial_number": sn
                    }
                    
                    if sn_key in existing_sn_data_map:
                        new_sn_row_data["to_do"] = existing_sn_data_map[sn_key]["to_do"]
                    
                    updated_inv_difference_sn_new_entries.append(new_sn_row_data)
            # --- END MODIFIED ---


        # --- Clean up inv_difference table: remove items that are no longer differences ---
        items_to_remove = []
        for i in range(len(doc.get("inv_difference")) - 1, -1, -1):
            row = doc.get("inv_difference")[i]
            # Remove if the item_code was NOT processed in this run (meaning it's no longer a difference)
            # Or if it was processed, but now has zero difference (and thus shouldn't be in the table)
            if row.item_code not in processed_difference_items:
                items_to_remove.append(row)
            elif row.item_code in processed_difference_items:
                current_physical_qty = physical_items_map.get(row.item_code, 0)
                current_virtual_qty = virtual_items_map.get(row.item_code, 0)
                if (current_physical_qty - current_virtual_qty) == 0: # If difference is now 0
                    if (row.item_code in virtual_items_map and 
                        physical_items_map.get(row.item_code, 0) == virtual_items_map.get(row.item_code, 0)):
                        items_to_remove.append(row)
                    elif row.item_code not in virtual_items_map and physical_items_map.get(row.item_code, 0) == 0:
                        items_to_remove.append(row)

        for row_to_remove in items_to_remove:
            doc.remove(row_to_remove)

        # --- MODIFIED: Final update of inv_difference_sn ---
        # Start the final list with all previously preserved 'Add/Remove' rows
        final_inv_difference_sn_rows = list(preserved_sn_rows)
        seen_sn_keys = set(preserved_sn_keys) # Initialize with keys of preserved rows

        # Now, iterate through the newly generated entries and add them if not already present (preserved)
        for sn_data in updated_inv_difference_sn_new_entries:
            sn_key = (sn_data["product"], sn_data["serial_number"])
            if sn_key not in seen_sn_keys: # Only add if not already processed in this run (or preserved)
                # Create a new Frappe child table row
                new_row = doc.append("inv_difference_sn", sn_data)
                final_inv_difference_sn_rows.append(new_row)
                seen_sn_keys.add(sn_key)

        # Set the entire child table with the new list of rows.
        doc.set("inv_difference_sn", final_inv_difference_sn_rows)
        # --- END MODIFIED ---

        doc.save()
        frappe.db.commit() # Ensure changes are persisted in the database

        frappe.publish_realtime("Compare Complete")
        return {"status": "success", "message": _("Comparaison des inventaires terminée avec succès.")}

    except Exception as e:
        frappe.db.rollback() # Rollback changes in case of error
        error_trace = traceback.format_exc()
        frappe.log_error(error_trace, "Error in compare_child_tables")
        print(error_trace) # Also print to bench console for immediate visibility during dev
        frappe.msgprint(_(f"Une erreur est survenue lors de la comparaison des tables : {e}"), title=_("Erreur d'importation"), indicator='red')
        frappe.publish_realtime("Compare Error", {"message": str(e), "traceback": error_trace})
        return {"status": "error", "message": str(e)}


# Get ConnectWise Warehouses and Bins
@frappe.whitelist()
def get_connectwise_warehouses_and_bins(): 
    """
    Fetches warehouses and their bins from ConnectWise API.
    Assumes ConnectWise API credentials are set in 'Inventory Count Settings'.
    """
    try:
        settings_doc = frappe.get_single('Inventory Count Settings')

        connectwise_api_url = settings_doc.connectwise_api_url 
        connectwise_company_id = settings_doc.connectwise_company_id 
        public_key = settings_doc.connectwise_public_key
        private_key = settings_doc.get_password('connectwise_private_key')
        client_id = settings_doc.connectwise_client_id

        if not all([connectwise_api_url, connectwise_company_id, public_key, private_key, client_id]):
            frappe.throw(
                _("ConnectWise API credentials (API URL, Company ID, Public Key, Private Key, Client ID) are not fully set in 'Inventory Count Settings'. Please configure them."),
                title=_("API Credentials Missing")
            )
        # ConnectWise API requires Base64 encoded keys for authentication
        credentials = f"{connectwise_company_id}+{public_key}:{private_key}"
        encoded_credentials = base64.b64encode(credentials.encode('utf-8')).decode('utf-8')

        headers = {
            "Accept": f"application/vnd.connectwise.com+json; version={cwAPI_version}",
            "Content-Type": "application/json",
            "Authorization": f"Basic {encoded_credentials}",
            "clientID": client_id # Client ID is often also required as a separate header
        }

        warehouses_endpoint = f"{connectwise_api_url}/procurement/warehouses"
        warehouse_bins_base_endpoint = f"{connectwise_api_url}/procurement/warehouseBins" # Base for individual bin lookups or filtered lists

        # Fetch Warehouses
        frappe.log_error(f"ConnectWise: Fetching warehouses from: {warehouses_endpoint}", "ConnectWise Debug")
        response = requests.get(warehouses_endpoint, headers=headers, timeout=15)
        response.raise_for_status() # Raise an exception for HTTP errors (4xx or 5xx)
        
        connectwise_warehouses_data = None
        try:
            connectwise_warehouses_data = response.json()
            frappe.log_error(f"ConnectWise: Warehouses data type: {type(connectwise_warehouses_data)}", "ConnectWise Debug")
            frappe.log_error(f"ConnectWise: Warehouses JSON (first 500 chars): {json.dumps(connectwise_warehouses_data, indent=2)[:500]}...", "ConnectWise Debug")
        except json.JSONDecodeError:
            frappe.log_error(f"ConnectWise: Warehouses API did not return valid JSON. Raw text: {response.text}", "ConnectWise JSON Error")
            frappe.throw(f"ConnectWise API did not return valid JSON for warehouses. Response: {response.text[:200]}...", title="API Response Error")
            return {"warehouses": [], "bins_map": {}}

        # Ensure top-level is a list before iterating
        if not isinstance(connectwise_warehouses_data, list):
            frappe.log_error(f"ConnectWise: Unexpected top-level data type for warehouses. Expected list, got {type(connectwise_warehouses_data)}.", "ConnectWise Data Type Error")
            frappe.throw("ConnectWise API returned unexpected format for warehouses. Expected a list.", title="API Format Error")
            return {"warehouses": [], "bins_map": {}}


        warehouse_options = []
        warehouse_bin_options_map = {} # Maps warehouse name to a list of its bins

        for warehouse in connectwise_warehouses_data:
            if not isinstance(warehouse, dict):
                frappe.log_error(f"ConnectWise: Skipping non-dictionary item in warehouse list: {warehouse}", "ConnectWise List Item Error")
                continue # Skip if an item isn't a dictionary

            warehouse_name = warehouse.get("name") + " (" + str(warehouse.get("id")) + ")"
            warehouse_id = warehouse.get("id") # Keep ID if you need to fetch bins separately

            if warehouse_name:
                warehouse_options.append(warehouse_name)

                #  Making a separate call for bins for each warehouse 
                if warehouse_id:
                    # Construct the URL for a specific bin
                    bins_endpoint = f"{warehouse_bins_base_endpoint}?conditions=warehouse/id={warehouse_id}" 
                    
                    #frappe.log_error(f"ConnectWise: Fetching bins for '{warehouse_name}' from: {bins_endpoint}", "ConnectWise Debug")
                    bins_response = requests.get(bins_endpoint, headers=headers, timeout=15)
                    bins_response.raise_for_status() # Raise an exception for HTTP errors (4xx or 5xx)
                    
                    connectwise_bins_data = None
                    try:
                        connectwise_bins_data = bins_response.json()
                        #frappe.log_error(f"ConnectWise: Bins data type for '{warehouse_name}': {type(connectwise_bins_data)}", "ConnectWise Debug")
                        #frappe.log_error(f"ConnectWise: Bins JSON for '{warehouse_name}' (first 500 chars): {json.dumps(connectwise_bins_data, indent=2)[:500]}...", "ConnectWise Debug")
                    except json.JSONDecodeError:
                        frappe.log_error(f"ConnectWise: Bins API for '{warehouse_name}' did not return valid JSON. Raw text: {bins_response.text}", "ConnectWise Bins JSON Error")
                        warehouse_bin_options_map[warehouse_name] = []
                        continue # Skip to next warehouse if JSON is invalid

                    # --- Handle the response for bins ---
                    # Based on your provided JSON, if the API returns a list of bins (most likely for a filtered query),
                    # or if it returns a single dictionary (like your example), we handle both.
                    if isinstance(connectwise_bins_data, list):
                        # If it's a list (which is ideal for 'bins for a warehouse')
                        warehouse_bin_options_map[warehouse_name] = [
                            bin_item.get("name") + " (" + str(bin_item.get("id")) + ")"
                            for bin_item in connectwise_bins_data 
                            if isinstance(bin_item, dict) and bin_item.get("name")
                        ]
                    elif isinstance(connectwise_bins_data, dict):
                        # If it's a single dictionary (like your example 'Magasin' bin)
                        bin_name = connectwise_bins_data.get("name") 
                        if bin_name:
                            warehouse_bin_options_map[warehouse_name] = [bin_name] # Store as a list containing one bin
                        else:
                            warehouse_bin_options_map[warehouse_name] = []
                    else:
                        frappe.log_error(f"ConnectWise: Bins API for '{warehouse_name}' returned unexpected data type: {type(connectwise_bins_data)}. Expected list or dict.", "ConnectWise Bins Data Type Error")
                        warehouse_bin_options_map[warehouse_name] = []
                else:
                    warehouse_bin_options_map[warehouse_name] = [] # No warehouse_id, no bins fetched


        # Return a dictionary with unique warehouse names and the map of bins
        # Ensure 'warehouse_bin_options_map' is returned, not 'connectwise_bins_data'
        return {
            "warehouses": sorted(list(set(warehouse_options))), # Ensure uniqueness and sort
            "bins_map": warehouse_bin_options_map
        }

    except requests.exceptions.HTTPError as e:
        frappe.throw(f"Error fetching data from ConnectWise API: {e.response.status_code} - {e.response.text}", title="ConnectWise API Error")
    except requests.exceptions.RequestException as e:
        frappe.throw(f"Connection error to ConnectWise API: {e}", title="Network Error")
    except Exception as e:
        frappe.throw(f"An unexpected error occurred while fetching ConnectWise data: {e}", title="API Fetch Error")


@frappe.whitelist()
def push_confirmed_differences_to_connectwise(doc_name):
    """
    Pushes all 'confirmed' items from the 'inv_difference' child table
    of an 'Inventory Count' document to the ConnectWise API as a single Inventory Adjustment
    with multiple adjustment details.

    The 'adjustment_type' and 'reason' fields are taken from the main 'Inventory Count' document.
    Note: This version does NOT include Warehouse ID or Warehouse Bin ID in the adjustment details payload.
    Please verify ConnectWise API requirements for these fields.
    """
    print("Pushing confirmed differences to ConnectWise...") # For debugging purposes, can be removed later
    try:
        doc = frappe.get_doc("Inventory Count", doc_name)
        
        # --- Retrieve ConnectWise API Credentials from Inventory Count Settings ---
        settings_doc = frappe.get_single('Inventory Count Settings')

        connectwise_api_url = settings_doc.connectwise_api_url
        connectwise_company_id = settings_doc.connectwise_company_id
        public_key = settings_doc.connectwise_public_key
        private_key = settings_doc.get_password('connectwise_private_key')
        client_id = settings_doc.connectwise_client_id

        # Validate core API credentials from settings
        if not all([connectwise_api_url, connectwise_company_id, public_key, private_key, client_id]):
            frappe.throw(
                _("ConnectWise API credentials (API URL, Company ID, Public Key, Private Key, Client ID) are not fully set in 'Inventory Count Settings'. Please configure them."),
                title=_("API Credentials Missing")
            )
        
        credentials = f"{connectwise_company_id}+{public_key}:{private_key}"
        encoded_credentials = base64.b64encode(credentials.encode('utf-8')).decode('utf-8')

        # --- Construct ConnectWise API Headers ---
        headers = {
            "Accept": "application/vnd.connectwise.com+json; version=2025.8", # Consider updating API version if ConnectWise has newer ones
            "Content-Type": "application/json",
            "Authorization": f"Basic {encoded_credentials}",
            "clientId": client_id
        }
        # --- End Credential Retrieval & Header Construction ---

        
        # --- Retrieve relevant fields directly from the Inventory Count document (doc) ---
        cw_adjustment_type_name_for_item = doc.adjustment_type # Correction type name from Frappe
        reason = doc.reason # This is a free text field for the reason of the inventory count

        try:
            # Use regex for a robust way to find the number in the last parentheses
            matchwh = re.search(r'\((\d+)\)$', doc.warehouse)
            warehouse_id = int(matchwh.group(1))
            matchwhbin = re.search(r'\((\d+)\)$', doc.warehouse_bin)
            bin_id = int(matchwhbin.group(1))
        except (AttributeError, TypeError, IndexError):
            frappe.throw(
                _("Warehouse is not set or is in an invalid format in the Inventory Count document."),
                title=_("Missing or Invalid Warehouse")
            )
        
        # Filter for only confirmed items that have a difference
        confirmed_items_to_push = [
            item for item in doc.get("inv_difference")
            if item.confirmed == 1 and (item.physical_qty != item.virtual_qty)
        ]

        if not confirmed_items_to_push:
            frappe.msgprint(_("No confirmed inventory differences found to push to ConnectWise (or quantities match)."), title=_("No Items"), indicator='blue')
            return {"status": "success", "message": _("No items to push.")}
        
        item_serials_map = {}
        for sn_row in doc.get("inv_difference_sn"):
            item_code = sn_row.get("product")
            serial_number = sn_row.get("serial_number")
            to_do_status = sn_row.get("to_do") # <-- NEW: Get the 'to_do' field

            # <-- MODIFIED CONDITION: Only add if 'to_do' is "Remove/Add"
            if item_code and serial_number and to_do_status == "Remove/Add":
                if item_code not in item_serials_map:
                    item_serials_map[item_code] = []
                item_serials_map[item_code].append(serial_number)
            
        

        failed_pushes = []
        adjustment_details_list = [] # This will hold all individual item adjustments

        # --- ConnectWise API Endpoints ---
        adjustments_api_endpoint = f"{connectwise_api_url}/procurement/adjustments"

        
        for item in confirmed_items_to_push:
            difference_qty = item.physical_qty - item.virtual_qty

            if difference_qty == 0:
                continue

            try:
                # --- Common data for this item ---
                base_detail = {
                    'catalogItem': {
                        'id': item.recid,
                    },
                    'warehouse': {
                        'id': warehouse_id,
                    },
                    'warehouseBin': {
                        'id': bin_id,
                    },
                }

                serials_for_item = item_serials_map.get(item.item_code)

                # --- Logic Branching ---
                # Case 1: Negative difference AND there are serial numbers selected for removal.
                # Create one adjustment detail PER serial number.
                if serials_for_item:
                    # Create a copy to avoid modifying the base dictionary in the loop
                    adjustment_detail = base_detail.copy()
                    adjustment_detail['quantityAdjusted'] = difference_qty
                    serial_string = ",".join(serials_for_item)
                    adjustment_detail['serialNumber'] = serial_string
                    adjustment_details_list.append(adjustment_detail)

                # Case 2: Any other scenario (positive difference, or a negative difference for non-serialized items).
                # Create a single adjustment detail with the total difference.
                else:
                    adjustment_detail = base_detail.copy()
                    adjustment_detail['quantityAdjusted'] = difference_qty
                    adjustment_details_list.append(adjustment_detail)

            except requests.exceptions.Timeout:
                error_detail = f"Request to ConnectWise timed out for item '{item.item_code}' during product lookup."
                failed_pushes.append(f"'{item.item_code}': {error_detail}")
            except requests.exceptions.RequestException as req_err:
                error_detail = f"Failed to find product '{item.item_code}' due to API error: {req_err}"
                if hasattr(req_err, 'response') and req_err.response is not None:
                    try:
                        cw_error = req_err.response.json()
                        error_message = cw_error.get('message', str(cw_error))
                        error_detail += f" - CW Error: {error_message} (Status: {req_err.response.status_code})"
                    except json.JSONDecodeError:
                        error_detail += f" - CW Raw Response: {req_err.response.text}"
                failed_pushes.append(f"'{item.item_code}': {error_detail}")
            except Exception as item_err:
                error_detail = f"An unexpected error occurred during processing of '{item.item_code}': {item_err}"
                failed_pushes.append(f"'{item.item_code}': {error_detail}")

        if not adjustment_details_list:
            frappe.msgprint(_("No valid inventory differences could be prepared for ConnectWise push."), title=_("No Details to Push"), indicator='orange')
            return {"status": "success", "message": _("No valid items to push after filtering and lookup.")}

        # --- Prepare the main adjustment payload with all details ---
        main_adjustment_payload = {
            'identifier': doc_name, # Using doc_name as identifier for the main adjustment
            'type': {
                'identifier': cw_adjustment_type_name_for_item,
            },
            'reason': reason, # Reason for the overall adjustment
        }

        pushed_count = 0
        failed_detail_pushes = [] # To track individual detail push failures

        try:
            # Step 1: Create the main inventory adjustment (uncommented this part)
            response = requests.post(adjustments_api_endpoint, headers=headers, data=json.dumps(main_adjustment_payload), timeout=60)
            response.raise_for_status() # Raise an exception for bad status codes

            parentId = response.json().get('id') # Get the ID of the created adjustment

            # Step 2: Iterate and send each adjustment detail individually
            for detail in adjustment_details_list:
                adjustments_details_api_endpoint = f"{connectwise_api_url}/procurement/adjustments/{parentId}/details"

                # --- ADDED: Find the original Frappe item row using 'recid' ---
                frappe_item_row = next((r for r in doc.get("inv_difference") 
                       if r.recid == detail.get('catalogItem', {}).get('id')), None)

                try:
                    details_response = requests.post(adjustments_details_api_endpoint, headers=headers, data=json.dumps(detail), timeout=60)
                    details_response.raise_for_status() # Raise an exception for bad status codes
                    pushed_count += 1

                    # Set success message upon successful push
                    if frappe_item_row:
                        frappe_item_row.db_set('response', "Successfully pushed detail to ConnectWise")

                except requests.exceptions.RequestException as detail_req_err:
                    error_detail = f"Failed to push detail for item '{detail.get('catalogItem', {}).get('identifier', 'N/A')}': {detail_req_err}"
                    if hasattr(detail_req_err, 'response') and detail_req_err.response is not None:
                        try:
                            cw_error = detail_req_err.response.json()
                            error_message = cw_error.get('message', str(cw_error))
                            error_detail += f" - CW Error: {error_message} (Status: {detail_req_err.response.status_code})"
                        except json.JSONDecodeError:
                            error_detail += f" - CW Raw Response: {detail_req_err.response.text}"
                    # --- ADDED: Save the error message to the child table row ---
                    if frappe_item_row:
                        frappe_item_row.db_set('response', error_detail[:140]) 
                    # -------------------------------------------------------------
                    failed_detail_pushes.append(error_detail)
                except Exception as detail_err:
                    error_detail = f"Error Pushing to CW : {detail_err}"

                    # --- ADDED: Save the error message to the child table row ---
                    if frappe_item_row:
                        frappe_item_row.db_set('response', error_detail[:140]) 
                    # -------------------------------------------------------------
                    
                    failed_detail_pushes.append(error_detail)


            # Mark all successfully pushed items as pushed in Frappe
            for item in confirmed_items_to_push:
                if hasattr(item, 'pushed_to_connectwise'):
                    item.db_set('pushed_to_connectwise', 1) 
            
            final_message = _(f"ConnectWise push process finished. {pushed_count} adjustment details pushed successfully.")
            if failed_detail_pushes:
                final_message += _(f" {len(failed_detail_pushes)} detail pushes failed: {', '.join(failed_detail_pushes)}")
                frappe.db.commit()
                refreshed = frappe.get_all(
                            "Inv_difference",
                            filters={"parent": doc.name, "parentfield": "inv_difference", "parenttype": "Inventory Count"},
                            fields=["name", "item_code", "response", "difference_qty", "physical_qty", "virtual_qty", "confirmed"],
                            order_by="creation"
                        )
                return {"status": "partial_success", "message": final_message, "items": refreshed, "docname": doc.name}
            else:
                return {"status": "success", "message": final_message}
        except requests.exceptions.Timeout:
            error_detail = f"Consolidated request to ConnectWise timed out after preparing {len(adjustment_details_list)} items."
           
            failed_pushes.append(f"Consolidated Push: {error_detail}")
            print(error_detail) # Print to console for immediate visibility during dev
            return {"status": "error", "message": error_detail, "debug": json.dumps(detail)}
        except requests.exceptions.RequestException as req_err:
            error_detail = f"Failed to push consolidated adjustment: {req_err}"
            if hasattr(req_err, 'response') and req_err.response is not None:
                try:
                    cw_error = req_err.response.json()
                    error_message = cw_error.get('message', str(cw_error))
                    error_detail += f" - CW Error: {error_message} (Status: {req_err.response.status_code})"
                except json.JSONDecodeError:
                    error_detail += f" - CW Raw Response: {req_err.response.text}"
            failed_pushes.append(f"Consolidated Push: {error_detail}")
            print(error_detail) # Print to console for immediate visibility during dev
            return {"status": "error", "message": error_detail, "debug": json.dumps(detail)}
        except Exception as push_err:
            error_detail = f"An unexpected error occurred during consolidated push: {push_err}"
            failed_pushes.append(f"Consolidated Push: {error_detail}")
            print(error_detail) # Print to console for immediate visibility during dev
            return {"status": "error", "message": error_detail, "debug": json.dumps(detail)}  
    
    except frappe.exceptions.ValidationError:
        frappe.db.rollback() 
        return {"status": "error", "message": "ConnectWise push process stopped due to a configuration or data error. Check messages for details."}
    except Exception as e:
        frappe.db.rollback() 
        return {"status": "error", "message": str(e)}
    
@frappe.whitelist()
def get_connectwise_type_adjustments():
    """
    Fetches available inventory adjustment types from the ConnectWise API.
    Assumes ConnectWise API credentials are set in 'Inventory Count Settings'.
    """
    try:
        # Retrieve ConnectWise API credentials from 'Inventory Count Settings'
        settings_doc = frappe.get_single('Inventory Count Settings')

        connectwise_api_url = settings_doc.connectwise_api_url
        connectwise_company_id = settings_doc.connectwise_company_id
        public_key = settings_doc.connectwise_public_key
        private_key = settings_doc.get_password('connectwise_private_key')
        client_id = settings_doc.connectwise_client_id

        # Validate that all required credentials are set
        if not all([connectwise_api_url, connectwise_company_id, public_key, private_key, client_id]):
            frappe.throw(
                _("ConnectWise API credentials (API URL, Company ID, Public Key, Private Key, Client ID) are not fully set in 'Inventory Count Settings'. Please configure them."),
                title=_("API Credentials Missing")
            )

        # ConnectWise API requires Base64 encoded keys for authentication
        credentials = f"{connectwise_company_id}+{public_key}:{private_key}"
        encoded_credentials = base64.b64encode(credentials.encode('utf-8')).decode('utf-8')

        # Set up HTTP headers for the ConnectWise API request
        headers = {
            "Accept": f"application/vnd.connectwise.com+json; version={cwAPI_version}", # Specify API version
            "Content-Type": "application/json",
            "Authorization": f"Basic {encoded_credentials}", # Basic authentication with encoded credentials
            "clientID": client_id # Client ID as a separate header
        }

        type_adjustments_endpoint = f"{connectwise_api_url}/procurement/adjustments/types"

        # Make the HTTP GET request to the ConnectWise API
        response = requests.get(type_adjustments_endpoint, headers=headers, timeout=15)
        response.raise_for_status() # Raise an exception for HTTP errors (4xx or 5xx)

        connectwise_type_adjustments_data = None
        try:
            # Attempt to parse the JSON response
            connectwise_type_adjustments_data = response.json()
        except json.JSONDecodeError:
            # Log and throw an error if the response is not valid JSON
            frappe.log_error(f"ConnectWise: Type Adjustments API did not return valid JSON. Raw text: {response.text}", "ConnectWise JSON Error")
            frappe.throw(f"ConnectWise API did not return valid JSON for type adjustments. Response: {response.text[:200]}...", title="API Response Error")
            return [] # Return an empty list on JSON error

        # Ensure the top-level data structure is a list (as expected for collections of items)
        if not isinstance(connectwise_type_adjustments_data, list):
            frappe.log_error(f"ConnectWise: Unexpected top-level data type for type adjustments. Expected list, got {type(connectwise_type_adjustments_data)}.", "ConnectWise Data Type Error")
            frappe.throw("ConnectWise API returned unexpected format for type adjustments. Expected a list.", title="API Format Error")
            return [] # Return empty list on unexpected format

        # Extract 'name' from each adjustment type dictionary
        type_adjustment_options = [
            adjustment.get("name")
            for adjustment in connectwise_type_adjustments_data
            if isinstance(adjustment, dict) and adjustment.get("name") # Ensure it's a dict and has a 'name'
        ]

        # Return a sorted list of unique type adjustment names
        return sorted(list(set(type_adjustment_options)))

    except requests.exceptions.HTTPError as e:
        # Handle HTTP errors (e.g., 404 Not Found, 401 Unauthorized)
        frappe.log_error(f"ConnectWise API HTTP Error fetching type adjustments: {e.response.status_code} - {e.response.text} - URL: {e.request.url}", "ConnectWise API Error")
        frappe.throw(f"Error fetching type adjustments from ConnectWise API: {e.response.status_code} - {e.response.text}", title="ConnectWise API Error")
    except requests.exceptions.RequestException as e:
        # Handle general request errors (e.g., network issues)
        frappe.log_error(f"ConnectWise API Connection Error fetching type adjustments: {e}", "ConnectWise API Error")
        frappe.throw(f"Connection error to ConnectWise API for type adjustments: {e}", title="Network Error")
    except Exception as e:
        # Catch any other unexpected errors and log the traceback
        frappe.log_error(traceback.format_exc(), "General ConnectWise API Error fetching type adjustments")
        frappe.throw(f"An unexpected error occurred while fetching ConnectWise type adjustments: {e}", title="API Fetch Error")


@frappe.whitelist()
def upsert_physical_item(parent_name, code, qty=1, description='', expected_qty=0):
    """
    Atomic upsert with duplicate-insert fallback:
    - trim/normalize code
    - try UPDATE qty = qty + inc
    - if UPDATE affected 0 rows, try INSERT
    - if INSERT fails due to duplicate, retry UPDATE once
    """
    import traceback
    child_doctype = "Inv_physical_items"
    try:
        if not parent_name:
            frappe.throw(_("parent_name is required"))

        if not code:
            frappe.throw(_("code is required"))

        # Normalize code to avoid duplicates due to whitespace/case
        code = str(code).strip()

        try:
            inc = 1
        except Exception:
            inc = 1

        desc_clause = ""
        expected_clause = ""
        params = [inc]

        if description is not None and description != "":
            desc_clause = ", description = %s"
            params.append(description)

        if expected_qty is not None and expected_qty != "":
            expected_clause = ", expected_qty = %s"
            try:
                params.append(int(expected_qty))
            except Exception:
                params.append(expected_qty)

        # parent params
        params.extend([parent_name, "inv_physical_items", "Inventory Count", code])

        update_sql = """
            UPDATE `tabInv_physical_items`
            SET qty = COALESCE(qty, 0) + %s
            {desc_clause}
            {expected_clause}
            WHERE parent=%s AND parentfield=%s AND parenttype=%s AND code=%s
        """.format(desc_clause=desc_clause, expected_clause=expected_clause)

        # 1) Try atomic UPDATE
        frappe.db.sql(update_sql, params)
        # Get number of affected rows for the previous UPDATE
        affected = 0
        try:
            affected = int(frappe.db.sql("SELECT ROW_COUNT()")[0][0])
        except Exception:
            affected = 0

        # 2) If no row updated, try to INSERT (may race => catch duplicate and retry UPDATE)
        if affected == 0:
            try:
                child = frappe.get_doc({
                    "doctype": child_doctype,
                    "parent": parent_name,
                    "parentfield": "inv_physical_items",
                    "parenttype": "Inventory Count",
                    "code": code,
                    "qty": inc,
                    "description": description,
                    "expected_qty": expected_qty
                })
                child.insert(ignore_permissions=True)
                frappe.db.commit()
            except Exception as e:
                # If another transaction inserted the same row concurrently, retry the atomic UPDATE once
                err_str = str(e)
                if "Duplicate entry" in err_str or "Duplicate" in err_str:
                    try:
                        # Retry UPDATE to increment the qty
                        frappe.db.sql(update_sql, params)
                        frappe.db.commit()
                    except Exception as e2:
                        frappe.db.rollback()
                        frappe.log_error(traceback.format_exc(), "upsert_physical_item retry update failed")
                        raise
                else:
                    frappe.db.rollback()
                    frappe.log_error(traceback.format_exc(), "upsert_physical_item insert failed")
                    raise
        else:
            # UPDATE succeeded, commit
            frappe.db.commit()

        # Refresh and return rows
        refreshed = frappe.get_all(child_doctype,
                                  filters={"parent": parent_name, "parentfield": "inv_physical_items", "parenttype": "Inventory Count"},
                                  fields=["name", "code", "description", "qty", "expected_qty"],
                                  order_by="creation")
        frappe.publish_realtime('inv_physical_items_refresh', {"items": refreshed})
        return {"status": "success", "items": refreshed}

    except Exception:
        frappe.db.rollback()
        frappe.log_error(traceback.format_exc(), "upsert_physical_item")
        raise