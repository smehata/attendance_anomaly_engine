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


## Setup Instructions

### Prerequisites
- ERPNext/Frappe environment with version 14 or higher
- Python 3.8 or higher
- Redis (for background job processing)

### Installation

You can install this app using the [bench](https://github.com/frappe/bench) CLI:

```bash
cd $PATH_TO_YOUR_BENCH
bench get-app $URL_OF_THIS_REPO --branch develop
bench install-app attendance_anomaly_engine
```

### Initial Setup Steps

1. **Install the app on your site:**
   ```bash
   bench --site your_site_name install-app attendance_anomaly_engine
   ```

2. **Migrate database:**
   ```bash
   bench --site your_site_name migrate
   ```

3. **Clear cache:**
   ```bash
   bench --site your_site_name clear-cache
   ```

4. **Configure Anomaly Settings** (see Anomaly Settings section below)

5. **Create Anomaly Rules for your shifts** (see Anomaly Rules section below)

6. **Enable scheduled processing** via background jobs scheduler

---

## Anomaly Rules

### Overview
An **Anomaly Rule** defines the thresholds and grace periods for detecting attendance anomalies. Each rule is associated with a specific Shift Type and contains configuration for various anomaly detection mechanisms.

### Creating an Anomaly Rule

1. Navigate to **Attendance Anomaly Engine > Anomaly Rule** in your ERPNext interface
2. Click **+ New** to create a new rule
3. Fill in the following fields:

#### Basic Information
- **Name**: Unique identifier for this rule (e.g., "Standard Shift Rule")
- **Shift Type**: Link to the Shift Type this rule applies to (e.g., "General", "Night Shift")
- **Is Active**: Check this to enable the rule

#### Grace Periods & Thresholds
- **Late Entry Grace Period (minutes)**: Grace period for late clock-in (default: 5 minutes)
- **Early Exit Grace Period (minutes)**: Grace period for early clock-out (default: 5 minutes)
- **Consecutive Absence Threshold (days)**: Number of consecutive absences before creating anomaly (default: 3 days)
- **Night Shift Consecutive Count**: Consecutive night shift count before applying adjusted grace periods (default: 2)

#### Overtime Configuration
- **Check Overtime**: Enable/disable overtime anomaly detection
- **OT Padding Threshold (minutes)**: Threshold for detecting overtime padding anomalies (default: 30 minutes)
- **Maximum OT Per Day (hours)**: Maximum allowed overtime in a single day (default: 4 hours)

#### Additional Checks
- **Check Night Shift**: Enable grace period adjustments for consecutive night shifts
- **Ghost Punch Detection**: Enable detection of missing check-in/check-out punches

### Rule Application
- Rules are automatically applied to attendance records during batch processing
- Only the active rule for a specific shift type is used
- Rules are evaluated in the `process_attendance_batch()` function

---

## Anomaly Settings

### Overview
**Anomaly Settings** is a global configuration document that controls how the Attendance Anomaly Engine processes records across your entire organization.

### Accessing Anomaly Settings

1. Navigate to **Attendance Anomaly Engine > Anomaly Setting** in ERPNext
2. There is typically one global setting document

### Configuration Parameters

#### Processing Configuration
- **Batch Size**: Number of employees to process in a single background job (default: 20)
  - Lower values: Less memory usage but more jobs enqueued
  - Higher values: Faster processing but higher memory consumption

- **Anomaly Start Date**: The date from which to begin scanning attendance records
  - Only records after this date are processed
  - Useful for ignoring historical data

---

## Attendance Anomaly

### Overview
An **Attendance Anomaly** is a document that represents a detected violation of configured anomaly rules. Each anomaly record provides details about what was detected and when.

### Anomaly Document Fields

#### Identification
- **Employee**: Link to the Employee record
- **Employee Name**: Auto-fetched employee name
- **Attendance Date**: Date when the anomaly was detected
- **Shift**: Shift type for the employee on that date

#### Anomaly Details
- **Anomaly Type**: Type of anomaly detected:
- **Anomaly Description**: Human-readable description of the anomaly
- **Expected Time/Value**: Expected shift end time or threshold value
- **Actual Time/Value**: Actual recorded time or detected value
- **Variance**: Difference between expected and actual (in minutes)
---

## Anomaly Resolution Log

### Overview
The **Anomaly Resolution Log** is a detailed audit trail that records every action, update, and resolution related to an anomaly. It provides complete traceability for compliance and review purposes.

---

### Run Test Cases

```bash
bench --site site_name run-tests --app attendance_anomaly_engine --module attendance_anomaly_engine.testcases.test_attendence_anomaly
```

### Troubleshooting

#### Anomalies Not Being Detected
1. Verify Anomaly Setting is properly configured
2. Check that at least one Anomaly Rule is active
3. Ensure background job scheduler is running: `bench worker default`
4. Check logs: `tail -f logs/worker.log`

#### Performance Issues
1. Reduce batch size in Anomaly Settings
2. Check for long-running queries in database logs
3. Consider enabling parallel processing for high-volume sites

#### False Positives
1. Adjust grace periods in Anomaly Rules
2. Verify shift timings are correct
3. Check for leave applications that might mask absences

---

### License

mit
