frappe.ui.form.on('Item', {
    only_round_up_qty: function(frm) {
        if (frm.doc.only_round_up_qty) {
            frm.set_value('only_round_down_qty', 0);
            frm.set_value('auto_roundoff_qty', 0);
        }
    },
    only_round_down_qty: function(frm) {
        if (frm.doc.only_round_down_qty) {
            frm.set_value('only_round_up_qty', 0);
            frm.set_value('auto_roundoff_qty', 0);
        }
    },
    auto_roundoff_qty: function(frm) {
        if (frm.doc.auto_roundoff_qty) {
            frm.set_value('only_round_up_qty', 0);
            frm.set_value('only_round_down_qty', 0);
        }
    }
});