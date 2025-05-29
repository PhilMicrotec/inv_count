frappe.ui.form.on('Inventory Count', {
    onload: function(frm) {

        const event_name = `doc_update`; // This is the general event for any doc update
        frappe.realtime.on('doc_update', (data) => {
            if (data.doctype === frm.doctype && data.name === frm.doc.name) {
                frm.reload_doc(); // Reloads the current document data
            }
        });
        const childTableFieldName = 'inv_physical_items'; // Votre Fieldname de table enfant

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

                            if (frm.doc[childTableFieldName] && frm.doc[childTableFieldName].length > 0) {
                                
                                for (let row of frm.doc[childTableFieldName]) {
                                    if (row.code === enteredCode) {
                                        const newQty = (row.qty || 0) + 1;
                                        foundExistingRow = true;
                                        console.log(`Quantité augmentée pour le code: "${enteredCode}" à ${newQty}`);

                                        // --- LIGNE CLÉ À AJOUTER OU MODIFIER ---
                                        // Met à jour la valeur de la quantité dans le modèle Frappe pour cette ligne enfant
                                        // Cela marque la ligne comme modifiée et donc le document parent comme dirty.
                                        frappe.model.set_value(row.doctype, row.name, 'qty', newQty);

                                        break;
                                    }
                                }
                            } else {
                                console.log(`Table enfant "${childTableFieldName}" est vide ou non initialisée. Ajout d'une nouvelle ligne.`);
                            }

                            if (!foundExistingRow) {
                                console.log(`Code non trouvé. Ajout d'une nouvelle ligne pour: "${enteredCode}"`);
                                const newRow = frm.add_child(childTableFieldName);
                                newRow.code = enteredCode;
                                newRow.qty = 1;
                                // L'opération frm.add_child() marque naturellement le document comme dirty,
                                // donc pas besoin de frappe.model.set_value ici.
                            }

                            frm.refresh_field(childTableFieldName); // Rafraîchit l'affichage de la table enfant

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
                            console.log("Champ 'code' vide après Entrée.");
                        }
                    }
                };

            } else {
                console.error("Erreur: Le champ 'code' ou son élément DOM (.input) n'a PAS ÉTÉ TROUVÉ après un court délai dans le DocType Prise Inventaire.");
            }
        }, 300);
    }
});