frappe.ui.form.on('Inventory Count Settings', {
    // This function is triggered after the document is successfully saved
    after_save: function(frm) {
        // Redirect to the 'Inventory Count Settings' form,
        // pre-selecting 'Inventory Count' as the doctype to customize.
        window.history.back();
    },
    refresh: function(frm) {
        frm.add_custom_button(__('Back'), function() {
            // Use browser history to go back
            window.history.back();
        }); // 'fa-arrow-left' is a Font Awesome icon for a left arrow
    }
});