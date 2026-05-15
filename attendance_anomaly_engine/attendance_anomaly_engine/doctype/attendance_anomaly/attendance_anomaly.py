# Copyright (c) 2026, self and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document


class AttendanceAnomaly(Document):

	@frappe.whitelist()
	def update_acknowledge(self):
		self.status = "Acknowledged"
		self.save()

	@frappe.whitelist()
	def auto_waived(self):
		self.status = "Auto Waived"
		self.save()

	@frappe.whitelist()
	def get_charges(self):
		amt = 0
		if self.type == "Boundary":
			amt = 0 - self.amount_from_sal_assigment("custom_boundry_anomaly")

		if self.type == "Streak":
			amt = 0 - self.amount_from_sal_assigment("custom_streak_consecutive")

		if self.type == "OT":
			amt = self.amount_from_sal_assigment("custom_overtime_pay")

		if self.type == "Ghost":
			amt = 0 - self.amount_from_sal_assigment("custom_ghost_attendance")

		if self.type == "OT Padding":
			amt = 0 - self.amount_from_sal_assigment("custom_ot_padding")
		return amt


	def amount_from_sal_assigment(self, field):
		sal_struct = frappe.get_all("Salary Structure Assignment", {"docstatus": 1,
									"employee": self.employee, "from_date": ["<=", self.date]},
									pluck=field, order_by="from_date desc", limit=1)
		if sal_struct:
			return sal_struct[0]
		return 0

	@frappe.whitelist()
	def create_resolution_log(self, amt, resolution_note):
		doc = frappe.new_doc("Anomaly Resolution Log")
		doc.employee = self.employee
		doc.employee_name = self.employee_name
		doc.date = self.date
		doc.payroll_difference = amt
		doc.resolution_notes = resolution_note
		doc.user = frappe.session.user
		doc.insert(ignore_permissions=True)

		self.status = "Resolved"
		self.add_comment("Comment", "Anomaly Resolved by User {0}".format(frappe.session.user))
		self.save()

