let parent_name = null;
frappe.ui.form.on('Inventory Count Settings', {
    onload: function(frm) {
        parent_name = frappe.route_options.parent_name;
    },

    // This function is triggered after the document is successfully saved
    after_save: function(frm) {
        // Redirect to the 'Inventory Count Settings' form,
        // pre-selecting 'Inventory Count' as the doctype to customize.
       frappe.set_route('Form', 'Inventory Count', parent_name)
            .then(() => {
                if (cur_frm && cur_frm.doctype === 'Inventory Count' && cur_frm.doc.name === parent_name) {
                    // Check if debug_mode is activated in the Inventory Count Settings
                    if (frm.doc.debug_mode) { // frm refers to the 'Inventory Count Settings' form
                        cur_frm.set_df_property('inventory_difference_section', 'hidden', false);
                        cur_frm.set_df_property('section_virtual_inventory', 'hidden', false);
                        console.log("Debug mode is active: 'inventory_difference_section' and 'section_virtual_inventory' unhidden.");
                    } else {
                        // Optionally, hide them if debug_mode is not active,
                        // in case they were previously unhidden or for consistency.
                        cur_frm.set_df_property('inventory_difference_section', 'hidden', true);
                        cur_frm.set_df_property('section_virtual_inventory', 'hidden', true);
                        console.log("Debug mode is inactive: 'inventory_difference_section' and 'section_virtual_inventory' hidden.");
                    }
                }
            })
            .catch(error => {
                console.error("Inventory Count Settings: Error during navigation or refresh:", error);
                frappe.show_alert({
                    message: __('Error navigating or refreshing Inventory Count: ') + error.message,
                    indicator: 'red'
                });
            })
    },
    refresh: function(frm) {
        frm.add_custom_button(__('Back'), function() {
            // Use browser history to go back
            window.history.back();
        }); // 'fa-arrow-left' is a Font Awesome icon for a left arrow
    }
});