from marshmallow.utils import pluck

import frappe
import erpnext
from datetime import datetime, timedelta
from frappe.utils import (
	add_days,
	get_time,
	get_year_ending,
	get_year_start,
	getdate,
	now_datetime,
)
from frappe.tests.utils import FrappeTestCase
from attendance_anomaly_engine.engine.attendance_process import (detect_shift_boundry_and_ghost_anomaly, get_attendance_records, check_overtime_anomaly)


class TestAttendanceAnomaly(FrappeTestCase):

	@classmethod
	def setUpClass(cls):
		super().setUpClass()

		cls.shift_type = create_test_shift()
		cls.employee = make_employee()
		create_anomaly_rule(cls.shift_type.name)
		make_attendance(cls.employee, cls.shift_type.name )

	def test_detect_anomaly(self):
		start_date = add_days(getdate(), -10)
		emp_attendances = get_attendance_records([self.employee], start_date)
		for employee, data in emp_attendances.items():
			#Detect shift boundary and ghost anomaly
			detect_shift_boundry_and_ghost_anomaly(employee, data)

			#Detect overtime and OT padding anomaly
			check_overtime_anomaly(employee, data)

		anomaly_attendance = frappe.get_all("Attendance Anomaly",{"shift":self.shift_type.name}, pluck="name")

		self.assertEqual(len(anomaly_attendance),3)


def create_test_shift():
	if not frappe.db.exists("Shift Type", "_Test Shift"):
		shift_type = frappe.get_doc(
			{
				"doctype": "Shift Type",
				"__newname": "_Test Shift",
				"start_time": "08:00:00",
				"end_time": "18:00:00",
				"enable_auto_attendance": 1,
				"determine_check_in_and_check_out": "Alternating entries as IN and OUT during the same shift",
				"working_hours_calculation_based_on": "First Check-in and Last Check-out",
				"begin_check_in_before_shift_start_time": 60,
				"allow_check_out_after_shift_end_time": 60,
				"process_attendance_after": add_days(getdate(), -2),
				"last_sync_of_checkin": now_datetime() + timedelta(days=1),
				"mark_auto_attendance_on_holidays":  False,
			}
		)

	holiday_list = "Employee Checkin Test Holiday List"
	if not frappe.db.exists("Holiday List", "Employee Checkin Test Holiday List"):
		holiday_list = frappe.get_doc(
			{
				"doctype": "Holiday List",
				"holiday_list_name": "Employee Checkin Test Holiday List",
				"from_date": get_year_start(getdate()),
				"to_date": get_year_ending(getdate()),
			}
		).insert()
		holiday_list = holiday_list.name

	shift_type.holiday_list = holiday_list
	shift_type.save()

	return shift_type

def make_employee():
	if not frappe.db.get_value("Employee", {"user_id": "_Test Emp-001"}):
		employee = frappe.get_doc(
			{
				"doctype": "Employee",
				"naming_series": "EMP-",
				"first_name":  "_Test Emp-001",
				"company": erpnext.get_default_company(),
				"date_of_birth": "1990-05-08",
				"date_of_joining": "2013-01-01",
				"gender": "Male",
				"prefered_contact_email": "Company Email",
				"status": "Active",
				"employment_type": "Intern",
			}
		)
		employee.insert()
		return employee.name
	else:
		employee = frappe.get_doc("Employee", {"employee_name": "_Test Emp-001"})
		employee.status = "Active"
		employee.save()
		return employee.name

def make_attendance(employee, shift_type):
	date1 = now_datetime() - timedelta(days=3)
	date2 = now_datetime() - timedelta(days=2)
	date0 = now_datetime() - timedelta(days=1)
	attendance_data = [
		{
			"employee": employee,
			"company": erpnext.get_default_company(),
			"attendance_date": add_days(getdate(),-3),
			"status": "Present",
			"shift": shift_type,
			"in_time": date1.replace( hour=8, minute=0, second=0, microsecond=0),
			"out_time":date1.replace( hour=17, minute=45, second=0, microsecond=0)
		},
		{
			"employee": employee,
			"company": erpnext.get_default_company(),
			"attendance_date": add_days(getdate(),-2),
			"status": "Present",
			"shift": shift_type,
			"in_time": date2.replace( hour=9, minute=0, second=0, microsecond=0),
			"out_time":date2.replace( hour=18, minute=0, second=0, microsecond=0)
		},
		{
			"employee": employee,
			"company": erpnext.get_default_company(),
			"attendance_date": add_days(getdate(),-1),
			"status": "Present",
			"shift": shift_type,
			"in_time": date0.replace( hour=8, minute=0, second=0, microsecond=0),
			"out_time":date0.replace( hour=20, minute=5, second=0, microsecond=0)
		}
	]
	for data in attendance_data:
		attendance = frappe.new_doc("Attendance")
		attendance.update(data)
		attendance.save(ignore_permissions=True)
		attendance.submit()

def create_anomaly_rule(shift_type):
	anomaly_rule = frappe.new_doc("Anomaly Rule")
	anomaly_rule.rule_name = "_Test Anomaly"
	anomaly_rule.shift_type = shift_type
	anomaly_rule.is_active = 1
	anomaly_rule.late_entry_grace_period = 2
	anomaly_rule.night_shifts_consecutive = 6
	anomaly_rule.consecutive_absences = 3
	anomaly_rule.late_arrivals_days = 5
	anomaly_rule.overtime_threshold = 0.5
	anomaly_rule.save()
