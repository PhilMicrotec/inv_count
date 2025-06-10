frappe.ui.form.on('Inventory Count', {
    refresh: function(frm) {
        // --- Debug Mode Visibility Logic ---
        frappe.db.get_single_value('Inventory Count Settings', 'debug_mode')
            .then(debug_mode_active => {
                frm.fields.forEach(function(field) {
                    // This is the correct way to set hidden state based on debug_mode_active
                    // If debug_mode_active is true (1), hidden becomes 0 (visible)
                    // If debug_mode_active is false (0), hidden reverts to its original DocType state (field.df.hidden)
                    frm.set_df_property(field.df.fieldname, 'hidden', debug_mode_active ? 0 : field.df.hidden);
                });
            })
            .catch(error => {
                console.error("Error fetching debug_mode setting:", error);
            });

        if (!frm.doc.__islocal && frm.doc.inv_virtual_items.length === 0 ) {
                frappe.call({
                        method: 'inv_count.inventory_count.doctype.inventory_count.inventory_count.import_data_with_pandas',
                        args: {
                            inventory_count_name: frm.doc.name
                        },
                        callback: function(r) {
                            if (r.message) {
                                if (r.message.status === 'success') {
                                    frm.reload_doc(); 
                                } else {
                                    frappe.msgprint({
                                        message: __('Erreur lors de l\'importation : ') + r.message.message,
                                        title: __('Erreur'),
                                        indicator: 'red'
                                    });
                                }
                            }
                        },
                        error: function(err) {
                            frappe.msgprint({
                                message: __('Une erreur de communication est survenue: ') + err.message,
                                title: __('Erreur Serveur'),
                                indicator: 'red'
                            });
                        }
                });
            }
            
        if (!frm.custom_buttons['Settings']) {
            frm.add_custom_button(__('Settings'), function() {
                frappe.set_route('Form', 'Inventory Count Settings', {parent_name:cur_frm.doc.name}); // No need for null and doctype: 'Inventory Count' if it's a Single
            });
        }

        // Apply coloring logic on every refresh
        applyPhysicalItemsColoring(frm);
    },

    onload: function(frm) {
        // --- Realtime Update Listener (Good practice) ---
        // Ensures the form reloads if the document is updated elsewhere via Frappe's realtime
        const event_name = `doc_update`;
        frappe.realtime.on(event_name, (data) => {
            if (data.doctype === frm.doctype && data.name === frm.doc.name) {
                frm.reload_doc();
            }
        });

        const physicalItemsTable = 'inv_physical_items';
        const virtualItemsTable = 'inv_virtual_items';

        let currentScannedCode = ''; // Variable to store the current scanned code

        // --- Global Keyboard Input Redirection ---
        // This is the core logic to direct input to the 'code' field when no other field is selected.
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
            // You might need to inspect the DOM for specific classes if these don't cover all cases.
            const isFrappeSpecialField = activeElement.closest('.form-control.ui-autocomplete-input') || // For Link fields
                                         activeElement.closest('.datepicker--cell'); // For Datepickers

            // If an input-like element is focused, or a Frappe special field, let the default behavior happen
            if (isInputField || isFrappeSpecialField) {
                return;
            }

            // Filter out control keys (Ctrl, Alt, Shift, Meta) pressed alone or as part of shortcuts
            if (event.ctrlKey || event.altKey || event.metaKey) {
                return;
            }
            // Allow typing characters while Shift is held (for capitalization)
            // if (event.shiftKey && event.key.length !== 1) { // If Shift is pressed but not for a character
            //     return;
            // }

            // Prevent default browser actions for common keys that we want to redirect
            // This is crucial to stop browser search, scrolling, etc.
            if (event.key.length === 1 || event.key === ' ' || event.key === 'Backspace' || event.key === 'Enter') {
                event.preventDefault();
            } else {
                // For other non-character keys (e.g., arrow keys, F-keys), let default browser behavior happen
                return;
            }

            // --- Process the key input and direct it to the 'code' field ---
            if (event.key === 'Backspace') {
                if (codeFieldInput.value.length > 0) {
                    codeFieldInput.value = codeFieldInput.value.slice(0, -1);
                }
            } else if (event.key === 'Enter') {
                // When Enter is pressed globally, we want to trigger the existing onkeypress logic
                // on the code field itself. This is more robust than re-implementing the logic here.
                const enterEvent = new KeyboardEvent('keypress', {
                    key: 'Enter',
                    keyCode: 13,
                    which: 13,
                    bubbles: true,
                    cancelable: true
                });
                codeFieldInput.dispatchEvent(enterEvent);
                // After processing Enter, clear the scanned code variable if the field is cleared
                currentScannedCode = ''; // Reset after 'Enter' is processed
            } else if (event.key.length === 1 || event.key === ' ') {
                // Append character to the value
                codeFieldInput.value += event.key;
                // Update the temporary variable for 'input' event processing
                currentScannedCode = codeFieldInput.value;

                // Manually trigger an 'input' event to notify Frappe's reactivity
                const inputEvent = new Event('input', { bubbles: true });
                codeFieldInput.dispatchEvent(inputEvent);
            }

            // Ensure the 'code' field is focused and cursor is at the end
            codeFieldInput.focus();
            const len = codeFieldInput.value.length;
            codeFieldInput.setSelectionRange(len, len);
        };

        // Add the global keydown listener
        document.addEventListener('keydown', handleGlobalKeyboardInput);

        // --- Clean up global listener when form is closed ---
        // This is crucial for performance and to prevent unintended behavior on other DocTypes
        frm.on_close = function() {
            document.removeEventListener('keydown', handleGlobalKeyboardInput);
            console.log("Global keydown listener for 'code' field removed.");
        };

        // --- Initial setup for the 'code' field (original onkeypress logic) ---
        // This part remains as it handles the Enter key specifically on the 'code' field
        // as well as the 'input' event for live tracking.
        setTimeout(() => { // Using setTimeout to ensure DOM is ready
            const codeFieldInput = frm.fields_dict && frm.fields_dict['code'] ? frm.fields_dict['code'].input : null;

            if (codeFieldInput) {
                // Ensure the 'input' event handler correctly updates currentScannedCode
                codeFieldInput.addEventListener('input', function(e) {
                    currentScannedCode = e.target.value;
                });

                // The onkeypress logic for the 'code' field itself
                codeFieldInput.onkeypress = function(e) {
                    if (e.keyCode === 13) { // Enter key
                        e.preventDefault(); // Prevent default form submission or new line in textarea

                        const enteredCode = currentScannedCode.trim();

                        if (enteredCode) {
                            let foundExistingRow = false;
                            let itemDescription = '';
                            let expectedQty = 0;

                            // Find description and QOH in virtual items first
                            if (frm.doc[virtualItemsTable] && frm.doc[virtualItemsTable].length > 0) {
                                const virtualItem = frm.doc[virtualItemsTable].find(row => row.item_id === enteredCode);
                                if (virtualItem) {
                                    itemDescription = virtualItem.shortdescription || '';
                                    expectedQty = virtualItem.qoh || 0;
                                }
                            }

                            // Update or add to physical items
                            if (frm.doc[physicalItemsTable] && frm.doc[physicalItemsTable].length > 0) {
                                for (let row of frm.doc[physicalItemsTable]) {
                                    if (row.code === enteredCode) {
                                        const newQty = (row.qty || 0) + 1;
                                        foundExistingRow = true;

                                        frappe.model.set_value(row.doctype, row.name, 'qty', newQty);
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
                                const newRow = frm.add_child(physicalItemsTable);
                                newRow.code = enteredCode;
                                newRow.qty = 1;
                                newRow.description = itemDescription;
                                newRow.expected_qty = expectedQty;
                            }

                            frm.refresh_field(physicalItemsTable);
                            applyPhysicalItemsColoring(frm);
                            frm.set_value('code', ''); // Clear the main 'code' field
                            frm.refresh_field('code'); // Refresh the 'code' field display

                            // Reset the temporary variable for the next scan
                            currentScannedCode = '';

                            if (!foundExistingRow) frm.save(); // Save the document after modification

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
    before_submit: function(frm) {
        frappe.call({
            method: "inv_count.inventory_count.doctype.inventory_count.inventory_count.compare_child_tables",
            args: {
                doc_name: frm.doc.name
            },
            callback: function(r) {
                if (r.message) {
                    frappe.msgprint(r.message);
                    frm.refresh_field('inv_difference');
                }
            },
            error: function(err) {
                frappe.msgprint(__("Erreur lors de la comparaison : ") + err.message);
            }
        });

        const invDifferenceTable = frm.doc.inv_difference;

        let allConfirmed = true;
        for (let i = 0; i < invDifferenceTable.length; i++) {
            const row = invDifferenceTable[i];
            if (!row.confirmed) {
                allConfirmed = false;
                break;
            }
        }

        if (!allConfirmed) {
            cur_frm.set_df_property('inv_difference', 'hidden', 0);
            frappe.throw(__("Veuillez confirmer toutes les différences d'inventaire en cochant la case 'Confirmé' dans chaque ligne."));
            // Ensure the inv_difference section is visible so the user can see the checkboxes
            return false; // Prevent submission
        }
    }
});

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
                    $(item).find('.grid-static-col').css({'background-color': '#FFFFE0'}); // Light Yellow
                } else {
                    $(item).find('.grid-static-col').css({'background-color': '#FFCCCB'}); // Light Red
                }
            }
        });
    }
}