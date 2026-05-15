import frappe

@frappe.whitelist()
def process_employee_anomaly_setting(employee):
	job = frappe.enqueue(
		method="attendance_anomaly_engine.engine.attendance_process.process_attendance_batch",
		employees=[employee],
		queue="default",
		timeout=1800,
		enqueue_after_commit=True
	)
	return {
		"success": True,
		"status": "Process added in queue",
		"employee": employee
	}

