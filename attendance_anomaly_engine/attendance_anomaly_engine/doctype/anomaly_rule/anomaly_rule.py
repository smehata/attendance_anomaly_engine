# Copyright (c) 2026, self and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document


class AnomalyRule(Document):
	def validate(self):
		if self.get("__islocal"):
			existing_rule = frappe.db.get_list("Anomaly Rule",{"shift_type": self.shift_type}, pluck="shift_type")
			if existing_rule:
				frappe.throw("Anomaly Rule already exists for Shift Type {0}.".format(self.shift_type))
		else:
			existing_rule = frappe.db.get_list("Anomaly Rule", {"shift_type": self.shift_type, "name": ["!=", self.name]}, pluck="shift_type")
			if existing_rule:
				frappe.throw(
					"Anomaly Rule already exists for Shift Type {0}.".format(self.shift_type))

