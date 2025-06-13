// inv_count/inventory_count/doctype/inventory_count/inventory_count.js

let auto_update = true; // Global variable to control auto-update behavior
let initialized = false; // Flag to track if the form has been initialized

frappe.ui.form.on('Inventory Count', {
    refresh: function(frm) {
        // --- Debug Mode Visibility Logic ---
        // Fetches 'debug_mode' setting from 'Inventory Count Settings' and adjusts field visibility.
        frappe.db.get_single_value('Inventory Count Settings', 'debug_mode')
            .then(debug_mode_active => {
                frm.fields.forEach(function(field) {
                    // If debug_mode_active is true (1), hidden becomes 0 (visible)
                    // If debug_mode_active is false (0), hidden reverts to its original DocType state (field.df.hidden)
                    frm.set_df_property(field.df.fieldname, 'hidden', debug_mode_active ? 0 : field.df.hidden);
                });
            })
            .catch(error => {
                console.error("Error fetching debug_mode setting:", error);
            });
        
 
        if (!frm.doc.__islocal && frm.doc.inv_virtual_items.length === 0 && !initialized) {
            initialized = true; // Set initialized to true to prevent multiple calls
            frappe.show_alert({
                message: __("L'importation de l'inventaire virtuel a démarré en arrière-plan. Cela peut prendre un certain temps."),
                indicator: 'blue'
            }, 5); // Show alert for 5 seconds

            frappe.call({
                // Calls the whitelisted Python wrapper function to enqueue the import
                method: 'inv_count.inventory_count.doctype.inventory_count.inventory_count.enqueue_import_data',
                args: {
                    inventory_count_name: frm.doc.name // Pass the current document's name
                },
                callback: function(r) {
                    // This callback fires when the job is SUCCESSFULLY ENQUEUED on the server.
                    // It does NOT mean the import job itself is complete.
                    if (r.message && r.message.job_id) {
                        const jobId = r.message.job_id;
                        console.log("Import job enqueued with ID:", jobId);
                        
                        // Listen for the specific job completion event via Frappe Realtime
                        frappe.realtime.on(`Import Complete`, () => {
                            frappe.show_alert({
                                message: __("Importation de l'inventaire virtuel terminée."),
                                indicator: 'green'
                            });
                            // Crucial: Reload the document to fetch the newly imported data and update the 'modified' timestamp
                            //frm.reload_doc(); 
                        });

                        // Listen for job failure events
                        frappe.realtime.on(`job_failed_${jobId}`, (data) => {
                            frappe.msgprint({
                                message: __('L\'importation de l\'inventaire virtuel a échoué : ') + (data.exc || data.message),
                                title: __('Erreur'),
                                indicator: 'red'
                            });
                            initialized = false; // Reset initialized to allow future imports
                            console.error("Import job failed:", data);
                        });

                    } else {
                        // Handle cases where the enqueueing itself failed (e.g., server error before job creation)
                        frappe.msgprint({
                            message: __('Échec de la mise en file d\'attente de la tâche d\'importation.'),
                            title: __('Erreur'),
                            indicator: 'red'
                        });
                        initialized = false; // Reset initialized to allow future imports
                    }
                },
                error: function(err) {
                    // Handle communication errors when trying to call the enqueue wrapper
                    frappe.msgprint({
                        message: __('Erreur de communication lors de la mise en file d\'attente de l\'importation : ') + err.message,
                        title: __('Erreur Serveur'),
                        indicator: 'red'
                    });
                    initialized = false; // Reset initialized to allow future imports
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
        console.log("test");

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

                                        frappe.model.set_value(row.doctype, row.name, 'qty', newQty);
                                        // Update description and expected_qty if they've changed in virtual inventory
                                        if (row.description !== itemDescription) {
                                            frappe.model.set_value(row.doctype, row.name, 'description', itemDescription);
                                        }
                                        if (row.expected_qty !== expectedQty) {
                                            frappe.model.set_value(row.doctype, row.name, 'expected_qty', expectedQty);
                                        }
                                        break;
                                    }
                                }
                            }

                            if (!foundExistingRow) {
                                // If not found, add a new row
                                const newRow = frm.add_child(physicalItemsTable);
                                newRow.code = enteredCode;
                                newRow.qty = 1;
                                newRow.description = itemDescription;
                                newRow.expected_qty = expectedQty;
                            }

                            frm.refresh_field(physicalItemsTable); // Refresh the child table display
                            applyPhysicalItemsColoring(frm); // Re-apply coloring
                            frm.set_value('code', ''); // Clear the main 'code' field for next scan
                            frm.refresh_field('code'); // Refresh the 'code' field display

                            // Reset the temporary variable for the next scan
                            currentScannedCode = '';

                            // Auto-save the document if a new item was added (otherwise, changes are handled by child table events)
                            if (!foundExistingRow) {
                                frm.save();
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
            frappe.show_alert({
                message: __("Calcul des différences d'inventaire en cours..."),
                indicator: 'blue'
            });

            // Call the whitelisted Python wrapper to enqueue the comparison
            frappe.call({
                method: "inv_count.inventory_count.doctype.inventory_count.inventory_count.enqueue_compare_tables",
                args: {
                    doc_name: frm.doc.name
                },
                callback: function(r) {
                    if (r.message && r.message.job_id) {
                        const jobId = r.message.job_id;
                        console.log("Comparison job enqueued with ID:", jobId);

                        // Listen for job completion
                        frappe.realtime.on(`Compare Complete`, () => {
                            frappe.show_alert({
                                message: __("Comparaison des inventaires terminée."),
                                indicator: 'green'
                            });
                            // CRITICAL: Reload the document to get the updated inv_difference table and timestamp
                            frm.reload_doc().then(() => {
                                frm.refresh_field('inv_difference'); // Ensure the grid is refreshed
                                // Now, perform the confirmation check after the document is fully reloaded
                                checkAllDifferencesConfirmed(frm, resolve, reject);
                            }).catch(e => {
                                reject();
                            });
                        });

                        // Listen for job failure
                        frappe.realtime.on(`job_failed_${jobId}`, (data) => {
                            frappe.msgprint({
                                message: __('La comparaison des inventaires a échoué : ') + (data.exc || data.message),
                                title: __('Erreur'),
                                indicator: 'red'
                            });
                            reject();
                        });

                    } else {
                        frappe.msgprint(__("Échec de la mise en file d'attente de la tâche de comparaison."));
                        reject();
                    }
                },
                error: function(err) {
                    frappe.msgprint(__("Erreur de communication lors de la mise en file d'attente de la comparaison : ") + err.message);
                    reject();
                }
            });
        });
    }
});

// --- Helper function to check if all differences are confirmed ---
function checkAllDifferencesConfirmed(frm, resolve, reject) {
    const invDifferenceTable = frm.doc.inv_difference;
    let allConfirmed = true;
    for (let i = 0; i < invDifferenceTable.length; i++) {
        const row = invDifferenceTable[i];
        // Only check for unconfirmed rows if there is an actual difference (qty > 0 or < 0)
        // If difference_qty is 0, it means it was a discrepancy that got resolved and should not block submission.
        if (!row.confirmed) {
            allConfirmed = false;
            break;
        }
    }
    if (!allConfirmed) {
        // Ensure the inv_difference section is visible so the user can see the checkboxes
        cur_frm.set_df_property('inv_difference', 'hidden', 0);
        frappe.throw(__("Veuillez confirmer toutes les différences d'inventaire non résolues en cochant la case 'Confirmé' dans chaque ligne."));
        reject(); // Prevent submission
    } else {
        resolve(); // Allow submission
    }
}

// --- Child Table Event Handlers (Outside main frappe.ui.form.on) ---
// These apply to changes within rows of the child table, not the parent form.
frappe.ui.form.on('Inv_physical_items', {
    qty: function(frm, cdt, cdn) {
        // Autosave when 'qty' is changed in a child table row
        frm.save();
        // Re-apply coloring as qty has changed
        applyPhysicalItemsColoring(frm);
    },
    code: function(frm, cdt, cdn) {
        // Autosave when 'code' is changed in a child table row
        frm.save();
    },
    description: function(frm, cdt, cdn) {
        // Autosave when 'description' is changed in a child table row
        frm.save();
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