// Copyright (c) 2026, self and contributors
// For license information, please see license.txt

frappe.ui.form.on("Attendance Anomaly", {
	refresh: function (frm) {
		if (frm.doc.status !== "Open") {
            frm.disable_save();
        } else {
            frm.enable_save();
        }

		frm.add_custom_button(__("Resolved"), () => {
			frm.call("get_charges").then((r) => {
				let d = new frappe.ui.Dialog({
					title: 'Resolve Anomaly',
					fields: [
						{
							fieldtype: 'HTML',
							fieldname: 'message',
							options: `
								<div style="margin-bottom: 12px;">
									Are you sure you want to resolve the anomaly?
									<br>
									<b>${format_currency(r.message)}</b> will impact the payroll.
								</div>
							`
						},
						{
							label: 'Resolution Note',
							fieldname: 'resolution_note',
							fieldtype: 'Small Text',
							reqd: 1
						}
					],
					primary_action_label: 'Resolve',
					primary_action(values) {
						frm.call({
							method: "create_resolution_log",
							doc: frm.doc,
							args: {
								amt: r.message,
								resolution_note: values.resolution_note
							},
							freeze: true,
							callback: () => {
								frm.reload_doc();
							},
						});
						d.hide();
					}
				});
				d.show()
			});
		}).addClass("btn-primary");

		frm.add_custom_button(__("Acknowledged"), () => {
			return frm.call("update_acknowledge").then((r) => {
				 frm.reload_doc();
			});
		}).addClass("btn-primary");

		frm.add_custom_button(__("Auto-Waived"), () => {
			return frm.call("auto_waived").then((r) => {
				 frm.reload_doc();
			});
		}).addClass("btn-primary");
	},
});
