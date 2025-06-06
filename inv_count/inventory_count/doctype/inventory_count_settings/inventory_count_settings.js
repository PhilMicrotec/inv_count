frappe.ui.form.on('Inventory Count Settings', {
    onload: function(frm) {
        if (frappe.route_options && frappe.route_options.inventory_count_parent) {
            frm.set_value('inventory_count_parent', frappe.route_options.inventory_count_parent);
            frappe.route_options = null; // Clear options
        }
    },

    after_save: function(frm) {
        const parentInventoryCountName = frm.doc.inventory_count_parent;

        if (parentInventoryCountName) {
            frappe.set_route("Form", "Inventory Count", parentInventoryCountName)
                .then(() => {
                    // *** IMPORTANT CONTEXT: ***
                    // At this point (inside .then()), frappe.set_route has completed
                    // its navigation. The browser's active window/tab is now showing
                    // the 'Inventory Count' form that corresponds to parentInventoryCountName.
                    // Therefore, 'cur_frm' now correctly points to this 'Inventory Count' form.

                    if (cur_frm && cur_frm.doctype === 'Inventory Count' && cur_frm.doc.name === parentInventoryCountName) {
                        cur_frm.reload_doc(); // This WILL refresh the Inventory Count form
                        frappe.show_alert({
                            message: __('Inventory Count refreshed successfully!'),
                            indicator: 'green'
                        }, 3);
                    } else {
                        // This else block handles a very rare race condition or
                        // if the route didn't fully resolve as expected (e.g., navigated away quickly).
                        // For most cases, the above cur_frm.reload_doc() is sufficient.
                        frappe.show_alert({
                            message: __('Navigated to Inventory Count, but automatic refresh was uncertain.'),
                            indicator: 'orange'
                        });
                        // You could potentially trigger a full page reload here as a last resort:
                        // location.reload(true);
                    }
                })
                .catch(error => {
                    frappe.show_alert({
                        message: __('Error navigating to Inventory Count: ') + error.message,
                        indicator: 'red'
                    });
                    console.error("Error setting route or reloading doc:", error);
                });
        } else {
            // Fallback if no parent Inventory Count is linked
            frappe.show_alert({
                message: __('No parent Inventory Count specified. Returning to list view.'),
                indicator: 'orange'
            });
            frappe.set_route("List", "Inventory Count");
        }
    },

    refresh: function(frm) {
        frm.add_custom_button(__('Back'), function() {
            window.history.back();
        }, 'fa fa-arrow-left');
    }
});