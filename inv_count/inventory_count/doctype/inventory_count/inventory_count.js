frappe.ui.form.on('Inventory Count', {
    refresh: function(frm) {
        frappe.db.get_single_value('Inventory Count Settings', 'debug_mode')
            .then(debug_mode_active => {
                // debug_mode_active will be the value of 'debug_mode' from 'Inventory Count Settings'
                // It's usually 0 or 1 for boolean fields in Frappe.

                if (debug_mode_active) {
                    // If debug mode is active, then proceed to show all hidden fields
                    frm.fields.forEach(function(field) {
                        if (field.df.hidden === 1) {
                            frm.set_df_property(field.df.fieldname, 'hidden', 0);
                        }
                    });
                } else {
                    frm.fields.forEach(function(field) {
                        if (field.df.hidden === 0 && !field.df.always_on_display) { // always_on_display is not a standard df property for 'hidden' state
                        }
                    });
                }
            })
            .catch(error => {
                console.error("Error fetching debug_mode setting:", error);
                // Handle error if the Single DocType or field doesn't exist
            });

        // Ajoutons un bouton d'action si le document n'est pas encore sauvegardé (pour éviter des erreurs)
        // ou si vous voulez qu'il soit toujours là, retirez la condition frm.doc.__islocal
        if (!frm.doc.__islocal) { // __islocal est vrai si le document n'est pas encore sauvegardé
            frm.add_custom_button(__('Importer Données CSV'), function() {
                // Afficher un message de chargement
                frappe.show_alert({
                    message: __('Importation des données CSV en cours...'),
                    indicator: 'blue'
                }, 3);

                // Appeler la fonction Python côté serveur via frappe.call
                frappe.call({
                    // Chemin complet de votre fonction Python. Assurez-vous que c'est le bon chemin.
                    // Exemple: 'nom_app.nom_module.nom_fichier_python.nom_fonction'
                    method: 'inv_count.inventory_count.doctype.inventory_count.inventory_count.import_data_with_pandas',
                    args: {
                        // Envoyer le nom du document courant (name) à la fonction Python
                        inventory_count_name: frm.doc.name
                    },
                    callback: function(r) {
                        // Callback après l'exécution de la fonction Python
                        if (r.message) {
                            if (r.message.status === 'success') {
                                frappe.msgprint({
                                    message: __('Importation réussie ! Document: ') + r.message.doc_name,
                                    title: __('Succès'),
                                    indicator: 'green'
                                });
                                frm.reload_doc(); // Recharger le formulaire pour afficher les nouvelles lignes
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
                        // Gérer les erreurs de communication avec le serveur
                        frappe.msgprint({
                            message: __('Une erreur de communication est survenue: ') + err.message,
                            title: __('Erreur Serveur'),
                            indicator: 'red'
                        });
                    }
                });
            }); // Le deuxième argument est la catégorie du bouton
        }
        frm.add_custom_button(__('Settings'), function() {
            frappe.set_route('Form', 'Inventory Count Settings', null, { doctype: 'Inventory Count' });
        }); 

        applyPhysicalItemsColoring(frm);
    },
    onload: function(frm) {

        const event_name = `doc_update`; // This is the general event for any doc update
        frappe.realtime.on('doc_update', (data) => {
            if (data.doctype === frm.doctype && data.name === frm.doc.name) {
                frm.reload_doc(); // Reloads the current document data
            }
        });

        const physicalItemsTable = 'inv_physical_items';
        const virtualItemsTable = 'inv_virtual_items'; 

        let currentScannedCode = ''; // Variable pour stocker le code en cours de scan

        // Utilisons un setTimeout initial pour être sûr que le DOM est prêt
        setTimeout(() => {
            const codeFieldInput = frm.fields_dict && frm.fields_dict['code'] ? frm.fields_dict['code'].input : null;

            if (codeFieldInput) {

                // --- GESTIONNAIRE DE L'ÉVÉNEMENT 'input' ---
                codeFieldInput.addEventListener('input', function(e) {
                    currentScannedCode = e.target.value;
                });


                // --- GESTIONNAIRE DE L'ÉVÉNEMENT 'keypress' ---
                codeFieldInput.onkeypress = function(e) {
                    if (e.keyCode === 13) {
                        e.preventDefault();

                        const enteredCode = currentScannedCode.trim();

                        if (enteredCode) {

                            let foundExistingRow = false;
                            let itemDescription = ''; // Variable to store the description
                            let expectedQty = 0; // Variable to store the expected quantity

                            // --- Find description in virtual items first ---
                            if (frm.doc[virtualItemsTable] && frm.doc[virtualItemsTable].length > 0) {
                                const virtualItem = frm.doc[virtualItemsTable].find(row => row.item_id === enteredCode);
                                if (virtualItem) {
                                    itemDescription = virtualItem.shortdescription || ''; // Get description if found
                                    expectedQty = virtualItem.qoh || 0; // **Get QOH from virtual items**
                                } 
                            }

                            // --- Update or add to physical items ---
                            if (frm.doc[physicalItemsTable] && frm.doc[physicalItemsTable].length > 0) {
                                for (let row of frm.doc[physicalItemsTable]) {
                                    if (row.code === enteredCode) {
                                        const newQty = (row.qty || 0) + 1;
                                        foundExistingRow = true;

                                        frappe.model.set_value(row.doctype, row.name, 'qty', newQty);
                                        // Also update description if it's different or always sync
                                        if (row.description !== itemDescription) {
                                            frappe.model.set_value(row.doctype, row.name, 'description', itemDescription);
                                        }
                                        // **Update expected_qty for existing row if it's different**
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

                            frm.refresh_field(physicalItemsTable); // Rafraîchit l'affichage de la table enfant
                            applyPhysicalItemsColoring(frm);
                            frm.set_value('code', ''); // Vide le champ 'code' principal
                            frm.refresh_field('code'); // Rafraîchit l'affichage du champ 'code'

                            // Réinitialiser la variable temporaire pour le prochain scan
                            currentScannedCode = '';

                            if (!foundExistingRow) frm.save(); // Enregistre le document après modification

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
        }, 300);
    }, 
    before_submit: function(frm) {     
            frappe.call({
                method: "inv_count.inventory_count.doctype.inventory_count.inventory_count.compare_child_tables",
                args: {
                    doc_name: frm.doc.name
                },
                callback: function(r) {
                    if (r.message) {
                        frappe.msgprint(r.message);
                        // Recharger la childtable inv_difference pour afficher les nouvelles données
                        frm.refresh_field('inv_difference');
                    }
                },
                error: function(err) {
                    frappe.msgprint(__("Erreur lors de la comparaison : ") + err.message);
                }
            });
        // Get the child table data
        const invDifferenceTable = frm.doc.inv_difference; // 'inv_difference' is the fieldname of your child table

        // --- Check if all rows have 'confirmed' checked ---
        let allConfirmed = true;
        for (let i = 0; i < invDifferenceTable.length; i++) {
            const row = invDifferenceTable[i];
            if (!row.confirmed) { // Assuming 'confirmed' is the fieldname of your checkbox
                allConfirmed = false;
                break; // Exit the loop as soon as an unchecked row is found
            }
        }

        if (!allConfirmed) {
            frappe.throw(__("Please confirm all inventory differences by checking the 'Confirmed' checkbox in each row."));
            frm.toggle_display('inv_difference', 1);
            return false; // Prevent submission
        }
    }    

});

// Frappe UI event for child table field changes.
// This is outside the main frappe.ui.form.on('Parent DocType') block
// because it's an event specifically for the child DocType.
frappe.ui.form.on('Inv_physical_items', {
    qty: function(frm, cdt, cdn) {
        // This function will be called when the 'qty' field of any row
        // in 'Inv_physical_items' child table is changed.
        frm.save();
    
    },
    code: function(frm, cdt, cdn) {
        // If you also want to autosave when 'code' is changed in the child table directly
        frm.save();
    }
});


// Helper function to apply coloring logic
function applyPhysicalItemsColoring(frm) {
    cur_frm.fields_dict["inv_physical_items"].$wrapper.find('.grid-body .rows').find(".grid-row").each(function(i, item) {
        let d = locals[cur_frm.fields_dict["inv_physical_items"].grid.doctype][$(item).attr('data-name')];
        if (d["qty"] == d["expected_qty"]) { // Added null check for 'd'
            $(item).find('.grid-static-col').css({'background-color': '#90EE90'});
        } else if (d["expected_qty"]==0){
            // Important: Reset color if qty is no longer 1
            $(item).find('.grid-static-col').css({'background-color': '#FFFFE0'});
        } else {
            // Important: Reset color if qty is no longer 1
            $(item).find('.grid-static-col').css({'background-color': '#FFCCCB'});
        }
    });
}