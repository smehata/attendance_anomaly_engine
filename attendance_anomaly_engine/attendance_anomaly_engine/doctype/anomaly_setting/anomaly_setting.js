// Copyright (c) 2026, self and contributors
// For license information, please see license.txt

frappe.ui.form.on("Anomaly Setting", {
	testing: function (frm) {
		frappe.call({
			method: "attendance_anomaly_engine.engine.attendance_process.process_attendance",
			callback: function (r) {}
		});
	},
});
