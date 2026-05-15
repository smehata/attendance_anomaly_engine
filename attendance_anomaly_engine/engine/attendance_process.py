import frappe
from datetime import datetime
from zoneinfo import ZoneInfo
from frappe.utils import flt, get_time, add_days, cint, getdate


def get_anomaly_rule(shift):
	anomaly_rules = frappe.get_all("Anomaly Rule", filters= {"shift_type": shift}, fields="*", limit=1)
	if anomaly_rules:
		return anomaly_rules[0]
	return []


def create_anomaly_attendance(**data):
	# Create Attendance Anomaly
	anomaly_doc = frappe.new_doc("Attendance Anomaly")
	anomaly_doc.update(data)
	anomaly_doc.insert(ignore_permissions=True)


def mark_in_attendance_anomaly_rule_applied(attendance):
	frappe.db.set_value("Attendance",attendance, "custom_is_anomaly_rules_applied", 1)


@frappe.whitelist()
def process_attendance():
	employees = frappe.get_all(
		"Employee",
		filters={"status": "Active"},
		pluck="name"
	)
	anomaly_setting = frappe.get_single("Anomaly Setting")
	BATCH_SIZE = anomaly_setting.batch_size or 50

	for i in range(0, len(employees), BATCH_SIZE):
		batch = employees[i:i + BATCH_SIZE]

		job = frappe.enqueue(
			method=process_attendance_batch,
			employees=batch,
			queue="long",
			timeout=1800,
			enqueue_after_commit=True
		)


def get_attendance_records(employees, start_date):
	anomaly_setting = frappe.get_single("Anomaly Setting")
	ANOMALY_START_DATE = anomaly_setting.start_date

	attendance_records = frappe.get_all(
		"Attendance",
		filters={
			"employee": ["in", employees],
			"attendance_date": [">=", ANOMALY_START_DATE],
			# "custom_is_anomaly_rules_applied": 0,
			"docstatus": 1
		},
		fields=[
			"name",
			"employee",
			"attendance_date",
			"status",
			"shift",
			"in_time",
			"out_time"
		],
		order_by="employee asc, attendance_date asc"
	)

	emp_attendance_group = {}
	for attendance in attendance_records:
		anomaly_rules = get_anomaly_rule(attendance.shift)
		if not anomaly_rules:
			continue
		elif anomaly_rules and not anomaly_rules["is_active"]:
			continue
		emp_attendance_group.setdefault(attendance.employee, []).append(attendance)
	return emp_attendance_group


def process_attendance_batch(employees):
	start_date = frappe.db.get_single_value("Anomaly Setting", "start_date")
	emp_attendances = get_attendance_records(employees, start_date)
	for employee, data in emp_attendances.items():
		detect_absent_steak_anomaly(employee, data)
		detect_shift_boundry_and_ghost_anomaly(employee, data)
		check_overtime_anomaly(employee, data)
	# frappe.db.commit()


def detect_shift_boundry_and_ghost_anomaly(employee, attendance):
	timezone = frappe.db.get_single_value("System Settings", "time_zone")
	tz = ZoneInfo(timezone)

	for record in attendance:
		shift = frappe.get_doc("Shift Type", record.shift)
		anomaly_rules = get_anomaly_rule(record.shift)

		ghost_flag = False

		# check night shift consecutive, if yes, then twice the late grace period
		night_shifts_consecutive = anomaly_rules["night_shifts_consecutive"]
		is_night_s_con = False
		if cint(night_shifts_consecutive) > 0 and not shift.custom_is_night_shift:
			is_night_s_con = check_night_shift(employee,record.attendance_date, night_shifts_consecutive)

		# check Late Entry
		checkin = record.in_time
		if checkin:
			shift_start = get_time(shift.start_time)
			shift_start_datetime = datetime.combine(record.attendance_date, shift_start)
			localized_shift_start_time = shift_start_datetime.replace(tzinfo=tz)
			localized_checkin = checkin.astimezone(tz)
			delta = (localized_checkin - localized_shift_start_time).total_seconds() / 60
			late_grace_period = flt(anomaly_rules["late_entry_grace_period"])

			if is_night_s_con:
				late_grace_period = late_grace_period * 2

			if delta > late_grace_period:
				create_anomaly_attendance(
					employee=employee,
					shift=shift.name,
					attendance=record.name,
					date=record.attendance_date,
					status="Open",
					type= "Boundary",
					description= f"Late Entry by {flt(delta,2)} minutes"
				)
		else:
			ghost_flag = True

		# check Early Exit
		checkout = record.out_time
		if checkout:
			end_time = get_time(shift.end_time)
			checkout_date = record.attendance_date
			if shift.custom_is_night_shift:
				checkout_date = add_days(record.attendance_date, 1)
			shift_end_datetime = datetime.combine(checkout_date, end_time)
			localized_shift_end_time = shift_end_datetime.replace(tzinfo=tz)
			localized_checkout = checkout.astimezone(tz)
			delta = (localized_shift_end_time - localized_checkout).total_seconds() / 60
			early_grace_period = flt(anomaly_rules["early_exit_grace_period"])

			if delta > early_grace_period:
				create_anomaly_attendance(
					employee=employee,
					attendance=record.name,
					shift=shift.name,
					date=record.attendance_date,
					status="Open",
					type= "Boundary",
					description= f"Early Exit by {flt(delta,2)} minutes"
				)
		else:
			ghost_flag = True

		if ghost_flag and record.status not in [ 'Absent', 'On Leave', 'Work From Home' ]:                            #If check-in or checkout missing, then ghost_flag will be true and create an attendance anomaly
			create_anomaly_attendance(
				employee=employee,
				attendance=record.name,
				shift=shift.name,
				date=record.attendance_date,
				status="Open",
				type="Ghost",
				description=f"Ghost Anomaly"
			)

		mark_in_attendance_anomaly_rule_applied(record.name)


def detect_absent_steak_anomaly(employee, attendance):
		streak = 0
		for record in attendance:
			shift = frappe.get_doc("Shift Type", record.shift)
			anomaly_rules = get_anomaly_rule(record.shift)
			cons_absences = anomaly_rules["consecutive_absences"]

			if cons_absences <= 0:
				continue

			if record.status == "On Leave":
				streak = 0
				continue

			if record.status == "Absent":
				streak += 1
			else:
				streak = 0

			if streak >= cons_absences:
				create_anomaly_attendance(
					employee=employee,
					attendance=record.name,
					shift=shift.name,
					date=record.attendance_date,
					status="Open",
					type="Streak",
					description=f"Consecutive Absences >= {streak} days"
				)


def check_night_shift(employee, to_date, night_shifts_con):
	from_date = add_days(to_date, 0 - night_shifts_con)
	result = frappe.db.sql("""select count(distinct A.name) from `tabAttendance` as A
		inner join `tabShift Type` as ST on ST.name = A.shift
		where A.docstatus = 1 and ST.custom_is_night_shift = 1
		and employee = %s and A.attendance_date between %s and %s""",(employee, from_date,to_date))

	if result and cint(result[0][0]) >= night_shifts_con:
		return True
	else:
		return False


def check_overtime_anomaly(employee, attendance):
	timezone = frappe.db.get_single_value("System Settings", "time_zone")
	tz = ZoneInfo(timezone)
	start_date = getdate()
	if attendance:
		start_date = attendance[0].attendance_date

	emp_timesheets = get_employee_timesheet(employee, start_date)

	for record in attendance:
		shift = frappe.get_doc("Shift Type", record.shift)
		anomaly_rules = get_anomaly_rule(record.shift)

		checkout = record.out_time
		if checkout:
			end_time = get_time(shift.end_time)
			checkout_date = record.attendance_date
			if shift.custom_is_night_shift:
				checkout_date = add_days(record.attendance_date, 1)
			shift_end_datetime = datetime.combine(checkout_date, end_time)
			localized_shift_end_time = shift_end_datetime.replace(tzinfo=tz)
			localized_checkout = checkout.astimezone(tz)
			delta = (localized_checkout - localized_shift_end_time).total_seconds() / 60
			overtime_threshold = flt(anomaly_rules["overtime_threshold"]) * 60

			if delta > overtime_threshold:
				ot_flag = True
				if emp_timesheets:
					key = (employee, checkout_date)
					if key in emp_timesheets.keys():
						employee_timesheet = emp_timesheets[key]
						localized_timesheet_time = employee_timesheet['to_time'].astimezone(tz)

						if localized_checkout < localized_timesheet_time:
							ot_flag = False
							create_anomaly_attendance(
								employee=employee,
								attendance=record.name,
								shift=shift.name,
								date=record.attendance_date,
								status="Open",
								type="OT Padding",
								description=f"OT Padding checkin {str(localized_checkout)} < {str(localized_timesheet_time)}"
							)
					else:
						ot_flag = False
						create_anomaly_attendance(
							employee=employee,
							attendance=record.name,
							shift=shift.name,
							date=record.attendance_date,
							status="Open",
							type="OT Padding",
							description=f"OT padding timesheet missing"
						)
				else:
					ot_flag = False
					create_anomaly_attendance(
						employee=employee,
						attendance=record.name,
						shift=shift.name,
						date=record.attendance_date,
						status="Open",
						type="OT Padding",
						description=f"OT padding timesheet missing"
					)

				if ot_flag:
					create_anomaly_attendance(
						employee=employee,
						attendance=record.name,
						shift=shift.name,
						date=record.attendance_date,
						status="Open",
						type="OT",
						description= f"Overtime by {flt(delta / 60,2)} Hours"
					)



def get_employee_timesheet(employee, start_date):
	start_date = add_days(start_date, -1)
	timesheets = frappe.db.sql("""
		SELECT
			 ts.name AS timesheet,
			ts.employee,
			ts.end_date,
			tsd.name AS timesheet_detail,
			tsd.to_time,
			tsd.hours
		FROM `tabTimesheet` ts
		JOIN `tabTimesheet Detail` tsd
			ON tsd.parent = ts.name
		WHERE tsd.to_time = (
			SELECT MAX(t2.to_time)
			FROM `tabTimesheet Detail` t2
			WHERE t2.parent = ts.name
			  AND t2.from_time >= %(from_date)s
		) AND ts.docstatus = 1
		AND ts.employee = %(employee)s
		AND tsd.from_time >= %(from_date)s""", {"employee": employee, "from_date": start_date}, as_dict=True)

	emp_wise_timesheet = {}
	if timesheets:
		for timesheet in timesheets:
			key = (timesheet.employee, timesheet.end_date)
			emp_wise_timesheet[key] = timesheet

	return emp_wise_timesheet
