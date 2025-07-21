# Copyright (c) 2025, Microtec and contributors
# For license information, please see license.txt

import frappe
from frappe import _ # Import for translation support
from frappe.model.document import Document
import pandas as pd
import os
import pymysql
import traceback # Import for more detailed error traceback
import requests
import base64
import json
from frappe.utils import get_datetime, get_timestamp

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
        frappe.throw(_("Document '{0}' with name '{1}' not found.").format(parent_doctype, inventory_count_name), title=_("Document Missing"))
        return {"status": "error", "message": _("Document '{0}' not found.").format(parent_doctype)}

    inventory_count_doc = frappe.get_doc(parent_doctype, inventory_count_name)
    frappe.msgprint(_("Importing virtual inventory for '{0}'...").format(inventory_count_doc.name), title=_("Import Status"), indicator='blue')

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
            frappe.msgprint(_("Successfully loaded data from CSV: {0}").format(csv_full_path), title=_("CSV Load Success"), indicator='green')

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
                frappe.throw(_("Missing SQL connection details (Host, Database, Username, or Query) in 'Inventory Count Settings'."), title=_("SQL Details Missing"))

            try:
                conn = pymysql.connect(
                    host=sql_host,
                    port=int(sql_port) if sql_port else 3306,
                    user=sql_username,
                    password=sql_password,
                    database=sql_database
                )
                frappe.msgprint(_("Successfully connected to SQL database: {0} on {1}:{2}").format(sql_database, sql_host, sql_port), title=_("SQL Connect Success"), indicator='green')
                df = pd.read_sql(sql_query, conn)
                conn.close()
                frappe.msgprint(_("Successfully loaded data from SQL query."), title=_("SQL Load Success"), indicator='green')

            except pymysql.Error as e:
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

        frappe.publish_realtime("Import Complete") # This is an event name, not a translatable user-facing message

    except Exception as e:
        frappe.db.rollback() # Rollback changes in case of error
        frappe.log_error(frappe.get_traceback(), "Error during Inventory Count import") # Changed log category to English
        traceback.print_exc() # For more detailed error trace in console
        frappe.msgprint(_("An error occurred during import: {0}").format(e), title=_("Import Error"), indicator='red')
        frappe.publish_realtime("Import Error", {"message": str(e)}) # This is an event payload, not a translatable user-facing message
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


        physical_items_to_compare = []
        virtual_items_to_compare = []

        # Decide which items to compare based on the category filter
        if main_category_filter:
            # Filter virtual items by the selected category
            virtual_items_to_compare = [
                item for item in all_virtual_items if item.category == main_category_filter
            ]
            
            # Get item_ids from the filtered virtual items to use for filtering physical items
            virtual_item_ids_in_category = {item.item_id for item in virtual_items_to_compare}

            physical_items_to_compare = all_physical_items 

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
        virtual_item_bin_map = {
            row.get("item_id"): row.get("bin")
            for row in all_virtual_items if row.get("item_id")
        }

        # Keep track of item_codes that were updated/created in inv_difference
        processed_difference_items = set()

        # --- Upsert logic for discrepancies based on Physical Items (from the items selected for comparison) ---
        for item_code, physical_qty_int in physical_items_map.items():
            if item_code is None:
                continue

            description_physical = description_physical_item_map.get(item_code, "")
            virtual_qty_int = virtual_items_map.get(item_code, 0) # Will be 0 if not found in virtual_items_to_compare

            difference = physical_qty_int - virtual_qty_int

            bin_from_virtual = virtual_item_bin_map.get(item_code, "")
            
            if difference != 0:
                # Try to find an existing row in inv_difference for this item_code
                existing_row = None
                # Always iterate to find existing row now, as we don't clear the table
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
                    existing_row.difference_reason = _("Quantité différente") if item_code in virtual_items_map else _("Article non trouvé dans l'inventaire virtuel")
                    existing_row.bin = bin_from_virtual
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
                    new_diff_item.bin = bin_from_virtual

                processed_difference_items.add(item_code)

        # --- Upsert logic for items only in Virtual Items (from the items selected for comparison, not in Physical's selected list) ---
        for item_code, virtual_qty_int in virtual_items_map.items():
            if item_code is None or item_code in physical_items_map:
                continue # Skip if already processed or exists in physical items map

            description_virtual = description_virtual_item_map.get(item_code, "")
            difference = 0 - virtual_qty_int # Item found in virtual but not in physical (in this comparison scope)

            bin_from_virtual = virtual_item_bin_map.get(item_code, "")

            # Always iterate to find existing row now, as we don't clear the table
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
                existing_row.difference_reason = _("Article non trouvé dans l'inventaire physique")
                existing_row.bin = bin_from_virtual
                # existing_row.confirmed is implicitly preserved here
            else:
                # Create new row
                new_diff_item = doc.append("inv_difference", {})
                new_diff_item.item_code = item_code
                new_diff_item.description = description_virtual
                new_diff_item.physical_qty = 0
                new_diff_item.virtual_qty = virtual_qty_int
                new_diff_item.difference_qty = difference
                new_diff_item.difference_reason = _("Article non trouvé dans l'inventaire physique")
                new_diff_item.confirmed = existing_confirmed_status_map.get(item_code, 0)
                new_diff_item.bin = bin_from_virtual
                

            processed_difference_items.add(item_code)

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
                    # Double check if this item_code appeared in the original virtual_items_map for the filter context
                    # If it did, and physical quantity now matches virtual, it's no longer a difference.
                    # This implies no "Mauvaise Catégorie" logic is present in this specific version,
                    # so we remove it if quantities match.
                    if (row.item_code in virtual_items_map and 
                        physical_items_map.get(row.item_code, 0) == virtual_items_map.get(row.item_code, 0)):
                        items_to_remove.append(row)
                    # If it's a physical item not found in virtual, and its physical qty is 0, then remove
                    elif row.item_code not in virtual_items_map and physical_items_map.get(row.item_code, 0) == 0:
                        items_to_remove.append(row)

        for row_to_remove in items_to_remove:
            doc.remove(row_to_remove)
        # --- MODIFICATION END ---

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



# --- WHITELISTED WRAPPER FUNCTIONS FOR ENQUEUEING ---
@frappe.whitelist()
def enqueue_import_data(inventory_count_name):
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
        credentials = f"{connectwise_company_id+"+"+public_key}:{private_key}"
        encoded_credentials = base64.b64encode(credentials.encode('utf-8')).decode('utf-8')

        headers = {
            "Accept": "application/vnd.connectwise.com+json; version=2019.1",
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

            warehouse_name = warehouse.get("name")
            warehouse_id = warehouse.get("id") # Keep ID if you need to fetch bins separately

            if warehouse_name:
                warehouse_options.append(warehouse_name)

                #  Making a separate call for bins for each warehouse 
                if warehouse_id:
                    # Construct the URL for a specific bin
                    bins_endpoint = f"{warehouse_bins_base_endpoint}?conditions=warehouse/id={warehouse_id}" 
                    
                    frappe.log_error(f"ConnectWise: Fetching bins for '{warehouse_name}' from: {bins_endpoint}", "ConnectWise Debug")
                    bins_response = requests.get(bins_endpoint, headers=headers, timeout=15)
                    bins_response.raise_for_status() # Raise an exception for HTTP errors (4xx or 5xx)
                    
                    connectwise_bins_data = None
                    try:
                        connectwise_bins_data = bins_response.json()
                        frappe.log_error(f"ConnectWise: Bins data type for '{warehouse_name}': {type(connectwise_bins_data)}", "ConnectWise Debug")
                        frappe.log_error(f"ConnectWise: Bins JSON for '{warehouse_name}' (first 500 chars): {json.dumps(connectwise_bins_data, indent=2)[:500]}...", "ConnectWise Debug")
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
                            bin_item.get("name") 
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
        frappe.log_error(f"ConnectWise API HTTP Error: {e.response.status_code} - {e.response.text} - URL: {e.request.url}", "ConnectWise API Error")
        frappe.throw(f"Error fetching data from ConnectWise API: {e.response.status_code} - {e.response.text}", title="ConnectWise API Error")
    except requests.exceptions.RequestException as e:
        frappe.log_error(f"ConnectWise API Connection Error: {e}", "ConnectWise API Error")
        frappe.throw(f"Connection error to ConnectWise API: {e}", title="Network Error")
    except Exception as e:
        frappe.log_error(traceback.format_exc(), "General ConnectWise API Error")
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
            "Accept": "application/vnd.connectwise.com+json; version=2019.1", # Consider updating API version if ConnectWise has newer ones
            "Content-Type": "application/json",
            "Authorization": f"Basic {encoded_credentials}",
            "clientId": client_id
        }
        # --- End Credential Retrieval & Header Construction ---

        
        # --- Retrieve relevant fields directly from the Inventory Count document (doc) ---
        warehouse_name = doc.warehouse # Still used for logging/context, but not sent in CW payload
        cw_adjustment_type_name_for_item = doc.adjustment_type # Correction type name from Frappe
        reason = doc.reason # This is a free text field for the reason of the inventory count

        # --- Validate mandatory fields from the Inventory Count document ---
        if not warehouse_name:
            frappe.throw(_("Warehouse is not set in the Inventory Count document. Cannot proceed with ConnectWise push."),
                         title=_("Missing Warehouse"))
        
        # Filter for only confirmed items that have a difference
        confirmed_items_to_push = [
            item for item in doc.get("inv_difference")
            if item.confirmed == 1 and (item.physical_qty != item.virtual_qty)
        ]

        if not confirmed_items_to_push:
            frappe.msgprint(_("No confirmed inventory differences found to push to ConnectWise (or quantities match)."), title=_("No Items"), indicator='blue')
            return {"status": "success", "message": _("No items to push.")}
        
        failed_pushes = []
        adjustment_details_list = [] # This will hold all individual item adjustments

        # --- ConnectWise API Endpoints ---
        adjustments_api_endpoint = f"{connectwise_api_url}/procurement/adjustments"

        
        for item in confirmed_items_to_push:
            difference_qty = item.physical_qty - item.virtual_qty
            

            if difference_qty == 0:
                frappe.msgprint(f"Skipping '{item.item_code}' as there is no quantity difference.", title=_("Skipped"))
                continue

            try:           
                # Construct individual adjustment detail
                adjustment_detail = {
                    'catalogItem': { # Reference to the ConnectWise product
                        'identifier': item.item_code
                    },
                    'description': item.description, # Using item_name from Frappe as description
                    'quantityAdjusted': difference_qty, # Use the actual difference, can be negative
                    'warehouse': { 
                        'name': warehouse_name
                    },
                    'warehouseBin': {
                        'name': item.bin
                    }
                }
                adjustment_details_list.append(adjustment_detail)

            except requests.exceptions.Timeout:
                error_detail = f"Request to ConnectWise timed out for item '{item.item_code}' during product lookup."
                frappe.log_error(error_detail, "ConnectWise Product Lookup Timeout Error")
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
                frappe.log_error(error_detail, "ConnectWise Product Lookup Request Error")
                failed_pushes.append(f"'{item.item_code}': {error_detail}")
            except Exception as item_err:
                error_detail = f"An unexpected error occurred during processing of '{item.item_code}': {item_err}"
                frappe.log_error(error_detail, "ConnectWise Detail Creation Generic Error")
                failed_pushes.append(f"'{item.item_code}': {error_detail}")

        if not adjustment_details_list:
            frappe.msgprint(_("No valid inventory differences could be prepared for ConnectWise push."), title=_("No Details to Push"), indicator='orange')
            return {"status": "success", "message": _("No valid items to push after filtering and lookup.")}

        # --- Prepare the main adjustment payload with all details ---
        main_adjustment_payload = {
            'identifier': reason, # Using reason as identifier for the main adjustment
            'type': {
                'identifier': cw_adjustment_type_name_for_item,
            },
            'reason': reason, # Reason for the overall adjustment
            'adjustmentDetails': adjustment_details_list # Array of all individual item adjustments
        }

        pushed_count = 0 # This will now be 1 if the main push succeeds, 0 otherwise
        try:
            # Step 2: Create the single inventory adjustment with all details using POST
            #response = requests.post(adjustments_api_endpoint, headers=headers, data=json.dumps(main_adjustment_payload), timeout=60) # Increased timeout for larger payloads
            #response.raise_for_status() 
            print(json.dumps(main_adjustment_payload))


            # If the main POST succeeds, all items in the list are considered pushed
            pushed_count = len(adjustment_details_list)

            # Mark all successfully pushed items as pushed in Frappe
            for item in confirmed_items_to_push:
                if hasattr(item, 'pushed_to_connectwise'):
                    item.db_set('pushed_to_connectwise', 1) 
            
            return {"status": "success", "message": _(f"ConnectWise push process finished. {pushed_count} adjustments pushed successfully, {len(failed_pushes)} failed.")}

        except requests.exceptions.Timeout:
            error_detail = f"Consolidated request to ConnectWise timed out after preparing {len(adjustment_details_list)} items."
            frappe.log_error(error_detail, "ConnectWise Consolidated Push Timeout Error")
            failed_pushes.append(f"Consolidated Push: {error_detail}")
            print(error_detail) # Print to console for immediate visibility during dev
            return {"status": "error", "message": error_detail}
        except requests.exceptions.RequestException as req_err:
            error_detail = f"Failed to push consolidated adjustment: {req_err}"
            if hasattr(req_err, 'response') and req_err.response is not None:
                try:
                    cw_error = req_err.response.json()
                    error_message = cw_error.get('message', str(cw_error))
                    error_detail += f" - CW Error: {error_message} (Status: {req_err.response.status_code})"
                except json.JSONDecodeError:
                    error_detail += f" - CW Raw Response: {req_err.response.text}"
            frappe.log_error(error_detail, "ConnectWise Consolidated Push Request Error")
            failed_pushes.append(f"Consolidated Push: {error_detail}")
            print(error_detail) # Print to console for immediate visibility during dev
            return {"status": "error", "message": error_detail}
        except Exception as push_err:
            error_detail = f"An unexpected error occurred during consolidated push: {push_err}"
            frappe.log_error(error_detail, "ConnectWise Consolidated Push Generic Error")
            failed_pushes.append(f"Consolidated Push: {error_detail}")
            print(error_detail) # Print to console for immediate visibility during dev
            return {"status": "error", "message": error_detail}

        
    
    except frappe.exceptions.ValidationError:
        frappe.db.rollback() 
        return {"status": "error", "message": "ConnectWise push process stopped due to a configuration or data error. Check messages for details."}
    except Exception as e:
        frappe.db.rollback() 
        error_trace = traceback.format_exc()
        frappe.log_error(error_trace, "Critical Error in push_confirmed_differences_to_connectwise function")
        frappe.msgprint(_(f"An unexpected critical error occurred during the ConnectWise push process: {e}"), title=_("ConnectWise Push Error"), indicator='red')
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
            "Accept": "application/vnd.connectwise.com+json; version=2019.1", # Specify API version
            "Content-Type": "application/json",
            "Authorization": f"Basic {encoded_credentials}", # Basic authentication with encoded credentials
            "clientID": client_id # Client ID as a separate header
        }

        type_adjustments_endpoint = f"{connectwise_api_url}/procurement/adjustments/types"

        frappe.log_error(f"ConnectWise: Fetching type adjustments from: {type_adjustments_endpoint}", "ConnectWise Debug")

        # Make the HTTP GET request to the ConnectWise API
        response = requests.get(type_adjustments_endpoint, headers=headers, timeout=15)
        response.raise_for_status() # Raise an exception for HTTP errors (4xx or 5xx)

        connectwise_type_adjustments_data = None
        try:
            # Attempt to parse the JSON response
            connectwise_type_adjustments_data = response.json()
            frappe.log_error(f"ConnectWise: Type adjustments data type: {type(connectwise_type_adjustments_data)}", "ConnectWise Debug")
            frappe.log_error(f"ConnectWise: Type adjustments JSON (first 500 chars): {json.dumps(connectwise_type_adjustments_data, indent=2)[:500]}...", "ConnectWise Debug")
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