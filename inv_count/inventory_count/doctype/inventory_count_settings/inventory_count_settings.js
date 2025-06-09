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
                        cur_frm.refresh();
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