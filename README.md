### Attendance Anomaly Engine

Attendance Anomaly Engine is a fully automated, rule-driven system that detects attendance anomalies
such as late entries, early exits, ghost punches, consecutive absence streaks, overtime and OT padding.

## Overview

This app processes submitted Attendance records and creates `Attendance Anomaly` documents when
configured rules are violated. It is designed to run in background jobs and process employees in
configurable batches. Core responsibilities include:

- Fetching attendance records that have not yet been processed for anomaly rules.
- Grouping attendance per employee and applying three main checks:
  - Boundary anomalies (late entry / early exit)
  - Ghost anomalies (missing in/out when not on leave)
  - Streak anomalies (consecutive absences)
  - Overtime and OT-padding checks using Timesheet data

The main processing logic lives in `attendance_anomaly_engine/engine/attendance_process.py`.

## attendance_process.py — functions, usage and time complexity

Below is a concise reference for the primary functions in `attendance_process.py`, how they are used,
and their time complexity characteristics. Let:

- n = number of employees being processed
- m = total attendance records processed for those employees
- a = number of attendance records for a single employee (varies per employee)
- t = number of timesheet rows returned for an employee

1) get_anomaly_rule(shift)
   - What it does: Fetches the active anomaly rule for the given shift type (DB query, limit=1).
   - Usage: Called when evaluating a record's shift to load rule thresholds (grace periods, thresholds).
   - Time complexity: O(1).

2) create_anomaly_attendance(**data)
   - What it does: Creates and inserts a new `Attendance Anomaly` document.
   - Usage: Invoked whenever an anomaly condition is detected.
   - Time complexity: O(1).

3) mark_in_attendance_anomaly_rule_applied(attendance)
   - What it does: Marks an Attendance record to indicate rules were applied (DB update).
   - Usage: Called once per attendance record after processing.
   - Time complexity: O(1).

4) process_attendance()
   - What it does: Top-level entry point. Loads active employees and enqueues background jobs
	 to process them in batches (batch size is configurable via `Anomaly Setting`).
   - Usage: Can be invoked as a scheduled/background task or manually.
   - Time complexity: O(n) to iterate employees and enqueue jobs. Actual work delegated to batch jobs.

5) get_attendance_records(employees, start_date)
   - What it does: Fetches submitted Attendance records for given employees from the configured
	 anomaly start date where anomaly rules haven't yet been applied. Groups results by employee.
   - Usage: Used by batch processing to retrieve all relevant attendance rows for a batch.
   - Time complexity: O(m) to iterate returned records and group them. The DB query cost depends on
	 the number of matching attendance rows returned (m).

6) process_attendance_batch(employees)
   - What it does: Processes a single batch of employees — obtains attendance records and runs the
	 anomaly detection functions for each employee.
   - Usage: Enqueued by `process_attendance()` as a background job.
   - Time complexity: O(m + T) where m is total attendance rows for the batch and T is the sum of
	 timesheet rows scanned for overtime checks. Each detection function iterates the per-employee
	 attendance list, so the complexity is proportional to the total attendance rows.

7) detect_shift_boundry_and_ghost_anomaly(employee, attendance)
   - What it does: For each attendance record: checks late entry, early exit (using shift start/end
	 times and the configured grace periods), and missing check-in/check-out (ghost anomaly). It also
	 optionally uses `check_night_shift` to adjust grace periods for consecutive night shifts.
   - Usage: Called for every employee with their attendance list.
   - Time complexity: O(a) per employee (a = number of attendance records for that employee). Each
	 record triggers a small number of DB reads (shift doc and anomaly rule); `check_night_shift` runs
	 an additional DB count query when enabled.

8) detect_absent_steak_anomaly(employee, attendance)
   - What it does: Scans attendance in order and counts consecutive `Absent` statuses. Creates an
	 anomaly when the configured consecutive absence threshold is reached.
   - Usage: Called per employee during batch processing.
   - Time complexity: O(a) per employee.

9) check_night_shift(employee, to_date, night_shifts_con)
   - What it does: Runs a DB query counting night-shift attendances in a date range to detect
	 consecutive night shifts.
   - Usage: Used by boundary detection to adjust grace periods.
   - Time complexity: O(1) from code perspective (single SQL query), but the DB cost depends on the
	 number of rows scanned for the date range.

10) check_overtime_anomaly(employee, attendance)
	- What it does: For each attendance record with an out_time, compares checkout to shift end
	  time and the employee's timesheet latest to detect OT and OT-padding anomalies.
	- Usage: Called per employee; internally calls `get_employee_timesheet` to fetch timesheet data.
	- Time complexity: O(t + a) where t is timesheet rows returned for the employee and a is the
	  number of attendance records processed. The DB query cost for timesheets dominates t.

11) get_employee_timesheet(employee, start_date)
	- What it does: Fetches timesheet detail rows (SQL) for the employee from the given start date,
	  and maps them keyed by (employee, end_date).
	- Usage: Used by overtime checks to validate OT against timesheets.
	- Time complexity: O(q) where q is the number of timesheet detail rows returned by the query.


### Installation

You can install this app using the [bench](https://github.com/frappe/bench) CLI:

```bash
cd $PATH_TO_YOUR_BENCH
bench get-app $URL_OF_THIS_REPO --branch develop
bench install-app attendance_anomaly_engine
```
### Run Test Cases

```bash
bench --site site_name run-tests --app attendance_anomaly_engine --module attendance_anomaly_engine.testcases.test_attendence_anomaly
```


### License

mit
