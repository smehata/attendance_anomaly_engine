frappe.listview_settings["Attendance Anomaly"] = {
	get_indicator: function (doc) {
		var status_color = {
			"Open": "red",
			"Acknowledged": "gray",
			"Resolved": "green",
			"Auto Waived": "blue",
		};
		return [__(doc.status), status_color[doc.status], "status,=," + doc.status];
	},
}
