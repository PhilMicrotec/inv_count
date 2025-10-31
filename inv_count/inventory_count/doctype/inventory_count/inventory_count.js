// inv_count/inventory_count/doctype/inventory_count/inventory_count.js
let auto_update = true; // Flag to control automatic updates
let debug_mode = false; // Flag to track if debug mode is active

frappe.ui.form.on('Inventory Count', {
    refresh: function(frm) {
        // --- Debug Mode Visibility Logic ---
        // Fetches 'debug_mode' setting from 'Inventory Count Settings' and adjusts field visibility.
        frappe.db.get_single_value('Inventory Count Settings', 'debug_mode')
            .then(debug_mode_setting => {
                debug_mode = debug_mode_setting || false; // Default to false if not set
                if (debug_mode) {
                    cur_frm.set_df_property('inventory_difference_section', 'hidden', false);
                    cur_frm.set_df_property('section_virtual_inventory', 'hidden', false);
                }
            })
            .catch(error => {
                console.error("Error fetching debug_mode setting:", error);
            });
            if (debug_mode) console.log("Debug Mode is active");
            
            if (frm.doc.__islocal) {
                frappe.call({
                method: 'inv_count.inventory_count.doctype.inventory_count.inventory_count.get_connectwise_warehouses_and_bins',
                callback: function(r) {
                    if (r.message) {
                        const warehouses = r.message.warehouses;
                        const bins_map = r.message.bins_map;

                        // Set options for the 'warehouse' field
                        // Add an empty option at the beginning to allow unselecting
                        if (warehouses && warehouses.length > 0) {
                            frm.set_df_property('warehouse', 'options', [""] /* Empty option */.concat(warehouses));
                        } else {
                            frm.set_df_property('warehouse', 'options', [""]); // No options if none found
                        }

                        // Store the bins_map on the form object for later dynamic updates
                        // This avoids fetching data again when only the warehouse selection changes
                        frm.__connectwise_bins_map = bins_map;

                        // Clear and refresh warehouse_bin options initially
                        // They will be populated when a 'warehouse' is selected
                        frm.set_df_property('warehouse_bin', 'options', [""]);
                        if (frm.doc.warehouse) {
                            frm.trigger('warehouse'); 
                        }
                        frm.refresh_field('warehouse');
                        frm.refresh_field('warehouse_bin');

                    } else if (r.exc) {
                        // Display error from server-side traceback
                        frappe.show_alert({
                            message: __("Error loading ConnectWise warehouses: ") + r.exc.split('\n')[0],
                            indicator: 'red'
                        }, 10);
                        console.error("ConnectWise API call failed:", r.exc);
                    }
                },
                error: function(err) {
                    // Display client-side communication error
                    frappe.show_alert({
                        message: __("Server communication error for ConnectWise warehouses: ") + err.message,
                        indicator: 'red'
                    }, 10);
                    console.error("Server communication error for ConnectWise warehouses:", err);
                }
            });
        }
 
        if (!frm.doc.__islocal && frm.doc.inv_virtual_items.length === 0 && auto_update) {
            python_request_in_progress(true); // Disable auto-update during initial import
            frappe.show_alert({
                message: __("L'importation de l'inventaire a démarré. Cela peut prendre un certain temps."),
                indicator: 'blue'
            }, 5); // Show alert for 5 seconds

            frappe.call({
                // Calls the whitelisted Python wrapper function to enqueue the import
                method: 'inv_count.inventory_count.doctype.inventory_count.inventory_count.import_data_with_pandas',
                args: {
                    inventory_count_name: frm.doc.name // Pass the current document's name
                },
                callback: function(r) {
                    // This callback fires when the job is SUCCESSFULLY ENQUEUED on the server.
                    // It does NOT mean the import job itself is complete.
                    if (r.message.status === "success") {
                        const jobId = r.message.job_id;
                            frappe.show_alert({
                                message: __("Importation de l'inventaire virtuel terminée."),
                                indicator: 'green'
                            });
                            frm.reload_doc().then(() => {
                                // Then, populate the categories using the fresh data
                                populateMainCategoryDropdown(frm);
                                python_request_in_progress(false); // Re-enable auto-update after import
                            });
                        

                    } else {
                        // Handle cases where the enqueueing itself failed (e.g., server error before job creation)
                        frappe.msgprint({
                            message: __('Échec d\'importation.'),
                            title: __('Erreur'),
                            indicator: 'red'
                        });
                        python_request_in_progress(false); // Re-enable auto-update after import failure
                    }
                },
                error: function(err) {
                    // Handle communication errors when trying to call the enqueue wrapper
                    frappe.msgprint({
                        message: __('Erreur de communication lors de la mise en file d\'attente de l\'importation : ') + err.message,
                        title: __('Erreur Serveur'),
                        indicator: 'red'
                    });
                    python_request_in_progress(false); // Re-enable auto-update after import failure
                }
            });

        }
            
        // --- Custom Settings Button ---
        // Adds a button to quickly navigate to the 'Inventory Count Settings' Single DocType.
        if (!frm.custom_buttons['Settings']) {
            frm.add_custom_button(__('Settings'), function() {
                frappe.set_route('Form', 'Inventory Count Settings', {parent_name:cur_frm.doc.name});
            });
        }


        // --- Apply Coloring Logic on every refresh ---
        // Ensures physical items are colored based on quantity difference from expected.
        applyPhysicalItemsColoring(frm);
    },

    onload: function(frm) {
        // --- Realtime Update Listener for the Current Document ---
        // This is a general listener for any 'doc_update' event, ensuring the form reloads
        // if the currently viewed document is modified elsewhere (e.g., by another user, or a different script).
        // It complements the job_complete listener by catching updates not tied to specific job_ids.
        const event_name = `doc_update`;
        frappe.realtime.on(event_name, (data) => {
            if (data.doctype === frm.doctype && data.name === frm.doc.name && auto_update==true) {
                console.log("Doc update detected via general listener. Reloading form.");
                frm.reload_doc();
            }
        });

        const physicalItemsTable = 'inv_physical_items';
        const virtualItemsTable = 'inv_virtual_items';

        let currentScannedCode = ''; // Variable to store the current scanned code

        // --- Global Keyboard Input Redirection (for Barcode Scanners) ---
        // This is the core logic to direct keyboard input (e.g., from a barcode scanner)
        // to the 'code' field when no other input field is actively focused.
        const handleGlobalKeyboardInput = function(event) {
            const codeFieldInput = frm.fields_dict && frm.fields_dict['code'] ? frm.fields_dict['code'].input : null;

            if (!codeFieldInput) {
                console.error("Target 'code' field input element not found.");
                return;
            }

            // Check if any standard input/textarea/select/button is currently focused
            const activeElement = document.activeElement;
            const isInputField = (
                activeElement.tagName === 'INPUT' ||
                activeElement.tagName === 'TEXTAREA' ||
                activeElement.tagName === 'SELECT' ||
                activeElement.tagName === 'BUTTON' ||
                (activeElement.hasAttribute('role') && activeElement.getAttribute('role') === 'button') // For Frappe's buttons
            );

            // Also check for Frappe's special input elements (Link, Date, etc.)
            // These often have specific classes or structures.
            const isFrappeSpecialField = activeElement.closest('.form-control.ui-autocomplete-input') || // For Link fields
                                         activeElement.closest('.datepicker--cell') || // For Datepickers
                                         activeElement.closest('.awesomplete'); // For autocomplete/link fields

            // If an input-like element is focused, or a Frappe special field, let the default behavior happen.
            // We don't want to hijack typing into other fields.
            if (isInputField || isFrappeSpecialField) {
                return;
            }

            // Filter out control keys (Ctrl, Alt, Shift, Meta) pressed alone or as part of shortcuts
            if (event.ctrlKey || event.altKey || event.metaKey) {
                return;
            }
            // Allow typing characters while Shift is held (for capitalization).
            // This condition is for non-character keys like Shift, Ctrl, Alt, F-keys
            if (event.key.length > 1 && event.key !== 'Backspace' && event.key !== 'Enter' && event.key !== ' ') {
                return;
            }

            // Prevent default browser actions for common keys that we want to redirect
            // This is crucial to stop browser search (e.g., by typing a letter), scrolling, etc.
            event.preventDefault();

            // --- Process the key input and direct it to the 'code' field ---
            if (event.key === 'Backspace') {
                // If Backspace is pressed, remove the last character
                if (codeFieldInput.value.length > 0) {
                    codeFieldInput.value = codeFieldInput.value.slice(0, -1);
                }
            } else if (event.key === 'Enter') {
                // When Enter is pressed globally, simulate an 'Enter' keypress on the 'code' field.
                // This triggers the specific onkeypress logic for that field.
                const enterEvent = new KeyboardEvent('keypress', {
                    key: 'Enter',
                    keyCode: 13,
                    which: 13,
                    bubbles: true,
                    cancelable: true
                });
                codeFieldInput.dispatchEvent(enterEvent);
                // After processing Enter, clear the temporary scanned code variable
                currentScannedCode = ''; 
            } else if (event.key.length === 1 || event.key === ' ') {
                // Append character (or space) to the value
                codeFieldInput.value += event.key;
                // Update the temporary variable for 'input' event processing
                currentScannedCode = codeFieldInput.value;

                // Manually trigger an 'input' event to notify Frappe's reactivity system
                const inputEvent = new Event('input', { bubbles: true });
                codeFieldInput.dispatchEvent(inputEvent);
            }

            // Ensure the 'code' field is focused and cursor is at the end
            codeFieldInput.focus();
            const len = codeFieldInput.value.length;
            codeFieldInput.setSelectionRange(len, len);
        };

        // Add the global keydown listener when the form loads
        document.addEventListener('keydown', handleGlobalKeyboardInput);

        // --- Clean up global listener when form is closed ---
        // This is crucial for performance and to prevent unintended behavior on other DocTypes.
        frm.on_close = function() {
            document.removeEventListener('keydown', handleGlobalKeyboardInput);
            console.log("Global keydown listener for 'code' field removed.");
        };

        // --- Initial setup for the 'code' field (original onkeypress logic) ---
        // This part handles the Enter key specifically on the 'code' field,
        // as well as the 'input' event for live tracking.
        setTimeout(() => { // Using setTimeout to ensure DOM is ready and field exists
            const codeFieldInput = frm.fields_dict && frm.fields_dict['code'] ? frm.fields_dict['code'].input : null;

            if (codeFieldInput) {
                // Ensure the 'input' event handler correctly updates currentScannedCode
                codeFieldInput.addEventListener('input', function(e) {
                    currentScannedCode = e.target.value;
                });

                // The onkeypress logic for the 'code' field itself (handles Enter)
                codeFieldInput.onkeypress = function(e) {
                    if (e.keyCode === 13) { // Enter key
                        e.preventDefault(); // Prevent default form submission or new line

                        const enteredCode = currentScannedCode.trim();

                        if (enteredCode) {
                            let foundExistingRow = false;
                            let itemDescription = '';
                            let expectedQty = 0;

                            // 1. Find description and QOH in virtual items first
                            if (frm.doc[virtualItemsTable] && frm.doc[virtualItemsTable].length > 0) {
                                const virtualItem = frm.doc[virtualItemsTable].find(row => row.item_id === enteredCode);
                                if (virtualItem) {
                                    itemDescription = virtualItem.shortdescription || '';
                                    expectedQty = virtualItem.qty || 0;
                                }
                            }

                            // 2. Update or add to physical items
                            if (frm.doc[physicalItemsTable] && frm.doc[physicalItemsTable].length > 0) {
                                for (let row of frm.doc[physicalItemsTable]) {
                                    if (row.code === enteredCode) {
                                        const newQty = (row.qty || 0) + 1;
                                        foundExistingRow = true;

                                        // Update local view immediately
                                        frappe.model.set_value(row.doctype, row.name, 'qty', newQty);
                                        if (row.description !== itemDescription) {
                                            frappe.model.set_value(row.doctype, row.name, 'description', itemDescription);
                                        }
                                        if (row.expected_qty !== expectedQty) {
                                            frappe.model.set_value(row.doctype, row.name, 'expected_qty', expectedQty);
                                        }

                                        // Persist only the single child row to backend (no full form save)
                                        frappe.call({
                                            method: 'inv_count.inventory_count.doctype.inventory_count.inventory_count.upsert_physical_item',
                                            args: {
                                                parent_name: frm.doc.name,
                                                code: enteredCode,
                                                qty: 1,
                                                description: itemDescription,
                                                expected_qty: expectedQty
                                            },
                                            callback: function(r) {
                                                if (r.message && r.message.items) {
                                                    // Replace and refresh only the child table
                                                    frm.set_value('code', ''); // Clear the main 'code' field for next scan
                                                    frm.refresh_field('code'); // Refresh the 'code' field display
                                                    currentScannedCode = '';
                                                    frm.set_value('inv_physical_items', r.message.items);
                                                    frm.refresh_field('inv_physical_items');
                                                    applyPhysicalItemsColoring(frm);
                                                }
                                            }
                                        });

                                        break;
                                    }
                                }
                            }

                            if (!foundExistingRow) {
                                // Optimistically update UI
                                const newRow = frm.add_child(physicalItemsTable);
                                newRow.code = enteredCode;
                                newRow.qty = 1;
                                newRow.description = itemDescription;
                                newRow.expected_qty = expectedQty;
                                frm.refresh_field(physicalItemsTable);
                                applyPhysicalItemsColoring(frm);
                                frm.set_value('code', '');
                                frm.refresh_field('code');

                                // Persist via server and refresh only the child table when done
                                frappe.call({
                                    method: 'inv_count.inventory_count.doctype.inventory_count.inventory_count.upsert_physical_item',
                                    args: {
                                        parent_name: frm.doc.name,
                                        code: enteredCode,
                                        qty: 1,
                                        description: itemDescription,
                                        expected_qty: expectedQty
                                    },
                                    callback: function(r) {
                                        if (r.message && r.message.items) {
                                            frm.set_value('code', ''); // Clear the main 'code' field for next scan
                                            frm.refresh_field('code'); // Refresh the 'code' field display
                                            currentScannedCode = '';
                                            frm.set_value('inv_physical_items', r.message.items);
                                            frm.refresh_field('inv_physical_items');
                                            applyPhysicalItemsColoring(frm);
                                        }
                                    },
                                    error: function(err) {
                                        console.error('Error persisting physical item:', err);
                                    }
                                });
                            }
                        } else {
                            frappe.show_alert({
                                message: __("Veuillez entrer un code avant d'appuyer sur Entrée."),
                                indicator: 'orange'
                            });
                        }
                    }
                };

            } else {
                console.error("Erreur: Le champ 'code' ou son élément DOM (.input) n'a PAS ÉTÉ TROUVÉ après un court délai dans le DocType Prise Inventaire.");
            }
        }, 300); // Small delay to ensure DOM is ready
    },

    warehouse: function(frm) {
        const selectedWarehouse = frm.doc.warehouse;
        const bins_map = frm.__connectwise_bins_map; // Retrieve the stored map

        let bin_options = [""]; // Start with an empty option

        if (selectedWarehouse && bins_map && bins_map[selectedWarehouse]) {
            // Get bins for the selected warehouse from the map
            const binsForWarehouse = bins_map[selectedWarehouse];
            if (Array.isArray(binsForWarehouse)) {
                bin_options = bin_options.concat(binsForWarehouse);
            } else {
                // This case should ideally not happen if Python correctly handles single/list,
                // but as a fallback, if it's not an array, treat it as empty.
                console.warn("Expected an array for bins, but got:", binsForWarehouse);
            }
        }
        
        // Set options for the 'warehouse_bin' field
        frm.set_df_property('warehouse_bin', 'options', bin_options);
        frm.set_value('warehouse_bin', ''); // Clear current bin selection when warehouse changes
        frm.refresh_field('warehouse_bin'); // Refresh the dropdown to show new options
    },

    // --- Before Submit Logic ---
    // This logic ensures necessary checks are performed before the document is submitted.
    // It now uses a Promise to handle the asynchronous comparison check,
    // ensuring the form reloads the latest data before the final confirmation check.
    before_submit: function(frm) {
        // First, basic check for physical items
        if (!frm.doc.inv_physical_items || frm.doc.inv_physical_items.length === 0) {
            frappe.throw(__("Veuillez scanner ou ajouter au moins un article dans l'inventaire physique pour pouvoir soumettre."));
            return false;
        }

        // Return a Promise to make before_submit asynchronous
        return new Promise((resolve, reject) => {

            
            // Call the whitelisted Python wrapper to enqueue the comparison
             // Disable auto-update during this operation
            if (auto_update) {
                python_request_in_progress(true); // Set the flag to indicate a Python request is in progress
                if (debug_mode) console.log("Comaparing child tables for differences...");
                frappe.call({
                    method: "inv_count.inventory_count.doctype.inventory_count.inventory_count.compare_child_tables",
                    args: {
                        doc_name: frm.doc.name
                    },
                    callback: function(r) {
                        console.log("Comparison response:", r);
                        if (r.message.status == "success") {
                            if (debug_mode) console.log("All child tables compared successfully. Reloading document...");
                            frm.reload_doc().then(() => {
                                checkAllDifferencesConfirmed(frm, resolve, reject);
                            }).catch(e => {
                                python_request_in_progress(false); // Reset the flag on error
                                reject();
                            });

                        } else {
                            frappe.msgprint(__("Compare Failed: ") + r.message.message);
                            python_request_in_progress(false); // Reset the flag on error
                            reject();
                        }
                    },
                    error: function(err) {
                        frappe.msgprint(__("Erreur de communication lors de la mise en file d'attente de la comparaison : ") + err.message);
                        python_request_in_progress(false); // Reset the flag on error
                        reject();
                    }
                });
            }
        });
    }
});

// --- Helper function to check if all differences are confirmed ---
function checkAllDifferencesConfirmed(frm, resolve, reject) {
    const invDifferenceTable = frm.doc.inv_difference;
    let allConfirmed = true;

    // Iterate through the inventory difference table to check if all relevant rows are confirmed.
    for (let i = 0; i < invDifferenceTable.length; i++) {
        const row = invDifferenceTable[i];
        // Only check for unconfirmed rows if there is an actual difference (qty > 0 or < 0).
        // If difference_qty is 0, it means the discrepancy was resolved, and it should not block submission
        // even if the 'confirmed' checkbox is not explicitly ticked for that row.
        if (row.difference_qty !== 0 && !row.confirmed) { // Corrected logic: check difference_qty
            allConfirmed = false;
            break; // Exit the loop as soon as an unconfirmed difference is found.
        }
    }

    //Count serial numbers in inv_difference_sn and compare with inv_difference
    let has_validation_errors = false;
    let serial_todo_counts = {};
    let serial_counts = {};

    // 1. Aggregate counts from inv_difference_sn
    frm.doc.inv_difference_sn.forEach(function (sn_row) {
        let product_code = sn_row.product;
        let to_do_status = sn_row.to_do;

        // Only count if product_code exists and to_do is explicitly 'add' or 'remove'
        if (product_code && (to_do_status === 'Remove/Add')) {
            if (!serial_todo_counts[product_code]) {
                serial_todo_counts[product_code] = 0;
            }
            serial_todo_counts[product_code]++;
        }
        // Only count if product_code exists and to_do is explicitly 'add' or 'remove'
        if (product_code) {
            if (!serial_counts[product_code]) {
                serial_counts[product_code] = 0;
            }
            serial_counts[product_code]++;
        }
    });

    // 2. Iterate through inv_difference and compare with aggregated counts
    frm.doc.inv_difference.forEach(function (diff_row) {
        let item_code = diff_row.item_code;
        let difference_qty = diff_row.physical_qty - diff_row.virtual_qty;

        // Only validate items that actually have a difference (not 0)
        if (difference_qty !== 0) {
            const product_has_serials_in_sn_list = serial_counts.hasOwnProperty(item_code);

            if (product_has_serials_in_sn_list) {
                // The expected count of serials is the absolute value of the difference quantity
                let expected_sn_count = Math.abs(difference_qty);

                // Get the actual count from our aggregated map, defaulting to 0 if not found
                let actual_sn_count = serial_todo_counts[item_code] || 0;

                // Compare expected vs actual serial counts
                if (expected_sn_count !== actual_sn_count) {
                    if (debug_mode) console.log(`Validation Error: Item ${item_code} has expected SN count ${expected_sn_count} but found ${actual_sn_count}.`);
                    has_validation_errors = true; // Set flag to prevent save
                }
            } else {
                // If no serials are found in the SN list, we can still validate the difference
                if (debug_mode) console.log(`Validation Warning: Item ${item_code} has no serials in SN list.`);
            }
        }
    });

    if (!allConfirmed || !frm.doc.adjustment_type || !frm.doc.reason || has_validation_errors) {
        // Ensure the inventory difference section is visible to the user.
        frm.set_df_property('inventory_difference_section', 'hidden', false);
        frappe.show_alert({
                message: __("Veuillez Choisir un type d'ajustement et confirmer les différences d'inventaire."),
                indicator: 'blue'
            }, 5);
  
        // If the 'adjustment_type' field is empty, fetch ConnectWise adjustment types.
        if (!frm.doc.adjustment_type) {
            // Show a loading indicator during the API call.

            frappe.call({
                method: "inv_count.inventory_count.doctype.inventory_count.inventory_count.get_connectwise_type_adjustments",
                args: {},
            }).then(r => {
                if (r.message) {
                    const adjustmentTypes = r.message;
                    console.log("ConnectWise Type Adjustments:", adjustmentTypes);
                    frm.set_df_property('adjustment_type', 'options', [''].concat(adjustmentTypes));
                    frm.set_df_property('adjustment_type', 'read_only', 0);
                    frm.refresh_field('adjustment_type');
                } else {
                    console.error("Error fetching ConnectWise Type Adjustments:", r);
                    frappe.msgprint(__('Failed to fetch ConnectWise Type Adjustments. Check logs for details.'));
                }
            }).catch(err => {
                console.error("API Call Error:", err);
                frappe.msgprint(__('An error occurred during the API call to fetch adjustment types.'));
            }).finally(() => {
                // Successfully fetched adjustment types
            });
        }
        

        python_request_in_progress(false); // Re-enable auto-update if it was disabled
        reject();
    } else {
        // If all relevant differences are confirmed, push to ConnectWise.
            if (debug_mode) console.log("All differences confirmed. Proceeding to push to ConnectWise.");
                        
                frappe.call({
                    method: 'inv_count.inventory_count.doctype.inventory_count.inventory_count.push_confirmed_differences_to_connectwise',
                    args: {
                        doc_name: frm.doc.name
                    }
                }).then(r => {
                    if (r.message.status === "success" ) {
                        frappe.show_alert({
                            message: r.message.message,
                            indicator: 'green'
                        }, 15);
                        
                            resolve(); // Resolve the Promise to allow submission
                            if (debug_mode) console.log("Push to ConnectWise successful, form reloaded.");
                                                    
                    } else if (r.message.status === "partial_success") 
                    {
                        frappe.show_alert({
                            message: r.message.message,
                            indicator: 'orange'
                        }, 15);
                        console.log(r.message.debug);
                        reject(); // Resolve the Promise to allow submission even if some items failed
                        if (debug_mode) console.log("Push to ConnectWise partially successful, form reloaded.");

                    } else {
                        frappe.show_alert({
                            message: r.message.message || __('An unexpected response was received from the server.'),
                            title: __('Error'),
                            indicator: 'red'
                        }, 15);
                        console.log(r.message.debug);
                        reject();
                        python_request_in_progress(false); // Re-enable auto-update even if the API call fails
                    }
                }).catch(err => {
                    console.error("API Call Error:", err);
                    frappe.msgprint(__('An error occurred during the ConnectWise push API call. Check browser console and Frappe logs for details.'), __('Network Error'), 'red');
                    reject();
                    python_request_in_progress(false); // Re-enable auto-update even if the API call fails
                });
            
    }
}


frappe.ui.form.on('Inv_physical_items', {
    ondelete: function(frm, cdt, cdn) {
        this.frm.save(); // Save the form to persist deletion
    }
});


// --- Helper Function for Coloring ---
function applyPhysicalItemsColoring(frm) {
    // Ensure the grid exists before trying to access its elements
    if (frm.fields_dict["inv_physical_items"] && frm.fields_dict["inv_physical_items"].grid) {
        frm.fields_dict["inv_physical_items"].$wrapper.find('.grid-body .rows').find(".grid-row").each(function(i, item) {
            let d = locals[cur_frm.fields_dict["inv_physical_items"].grid.doctype][$(item).attr('data-name')];
            if (d) { // Always check if 'd' (the row document) exists
                const qty = cint(d["qty"]); // Convert to integer
                const expected_qty = cint(d["expected_qty"]); // Convert to integer

                if (qty === expected_qty) {
                    $(item).find('.grid-static-col').css({'background-color': '#90EE90'}); // Light Green
                } else if (expected_qty === 0) {
                    $(item).find('.grid-static-col').css({'background-color': '#FFFFE0'}); // Light Yellow (for items not expected, but physically present)
                } else {
                    $(item).find('.grid-static-col').css({'background-color': '#FFCCCB'}); // Light Red (for quantity discrepancies)
                }
            }
        });
    }
}

function populateMainCategoryDropdown(frm) {
    console.log("--- populateMainCategoryDropdown called ---");
    const categories = new Set(); // Use a Set to store unique categories

    // 1. Check if inv_virtual_items exists and has items
    if (frm.doc.inv_virtual_items && frm.doc.inv_virtual_items.length > 0) {
        console.log("Virtual items found. Number of items:", frm.doc.inv_virtual_items.length);
        
        frm.doc.inv_virtual_items.forEach((item, index) => {
            // Ensure the category exists and is a string before adding
            if (item.category && typeof item.category === 'string') {
                categories.add(item.category);
            } else {
                console.warn(`Skipped item ${index} due to invalid or empty category. Value:`, item.category);
            }
        });
        console.log("Categories collected (before sorting):", Array.from(categories));

    } else {
        console.warn("No virtual items found or frm.doc.inv_virtual_items is empty.");
        console.warn("Current frm.doc.inv_virtual_items:", frm.doc.inv_virtual_items);
    }

    let category_options = [""]; // Start with an empty option to allow no selection
    // Convert Set to Array, sort alphabetically, and concatenate with the empty option
    const sortedCategories = Array.from(categories).sort();
    category_options = category_options.concat(sortedCategories);
    
    // Set the options for the main 'category' field
    frm.set_df_property('category', 'options', category_options);
    frm.set_df_property('category', 'read_only', 0); // Make it editable
    frm.refresh_field('category'); // Refresh the dropdown to show new options
    console.log("Main Category dropdown populated with final options:", category_options);
    console.log("--- populateMainCategoryDropdown finished ---");
}

function python_request_in_progress(bool) {
    if (bool) {
        if (debug_mode) console.log("Automatic updates are disable, python request in progress.");
        auto_update = false;
    } else {
        if (debug_mode) console.log("Automatic updates are enabled, python request completed.");
        auto_update = true;
    }
}