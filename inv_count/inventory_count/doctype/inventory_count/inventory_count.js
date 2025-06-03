frappe.ui.form.on('Inventory Count', {
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

                            // --- Find description in virtual items first ---
                            if (frm.doc[virtualItemsTable] && frm.doc[virtualItemsTable].length > 0) {
                                const virtualItem = frm.doc[virtualItemsTable].find(row => row.item_id === enteredCode);
                                if (virtualItem) {
                                    itemDescription = virtualItem.shortdescription || ''; // Get description if found
                                    console.log(`Description found in virtual items for "${enteredCode}": "${itemDescription}"`);
                                } else {
                                    console.log(`Code "${enteredCode}" not found in virtual inventory.`);
                                }
                            }

                            // --- Update or add to physical items ---
                            if (frm.doc[physicalItemsTable] && frm.doc[physicalItemsTable].length > 0) {
                                for (let row of frm.doc[physicalItemsTable]) {
                                    if (row.code === enteredCode) {
                                        const newQty = (row.qty || 0) + 1;
                                        foundExistingRow = true;
                                        console.log(`Quantité augmentée pour le code: "${enteredCode}" à ${newQty}`);

                                        frappe.model.set_value(row.doctype, row.name, 'qty', newQty);
                                        // Also update description if it's different or always sync
                                        if (row.description !== itemDescription) {
                                            frappe.model.set_value(row.doctype, row.name, 'description', itemDescription);
                                        }
                                        break;
                                    }
                                }
                            }

                            if (!foundExistingRow) {
                                console.log(`Code non trouvé. Ajout d'une nouvelle ligne pour: "${enteredCode}"`);
                                const newRow = frm.add_child(physicalItemsTable);
                                newRow.code = enteredCode;
                                newRow.qty = 1;
                                newRow.description = itemDescription;
                            }

                            frm.refresh_field(physicalItemsTable); // Rafraîchit l'affichage de la table enfant
                            frm.set_value('code', ''); // Vide le champ 'code' principal
                            frm.refresh_field('code'); // Rafraîchit l'affichage du champ 'code'

                            // Réinitialiser la variable temporaire pour le prochain scan
                            currentScannedCode = '';

                            frm.save();

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
    refresh: function(frm) {
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

        frm.add_custom_button('Compare Tables (Server Side)', function() {
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
        });
    },

});

// Frappe UI event for child table field changes.
// This is outside the main frappe.ui.form.on('Parent DocType') block
// because it's an event specifically for the child DocType.
frappe.ui.form.on('Inv_physical_items', {
    qty: function(frm, cdt, cdn) {
        // This function will be called when the 'qty' field of any row
        // in 'Inv_physical_items' child table is changed.
        console.log(`Quantity of row ${cdn} in Inv_physical_items changed. Autosaving...`);
        frm.save();
    },
    code: function(frm, cdt, cdn) {
        // If you also want to autosave when 'code' is changed in the child table directly
        console.log(`Code of row ${cdn} in Inv_physical_items changed. Autosaving...`);
        frm.save();
    }
});