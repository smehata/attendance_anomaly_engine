"""
Test Cases for Attendance Anomaly Engine Functions

This module contains comprehensive test cases for:
1. detect_shift_boundry_and_ghost_anomaly
2. detect_absent_steak_anomaly
3. check_overtime_anomaly

Usage:
    python -m frappe.bench.bench test-site --module attendance_anomaly_engine --verbose
"""

import frappe
import unittest
from datetime import datetime, time, timedelta
from zoneinfo import ZoneInfo
from frappe.utils import add_days, getdate
from unittest.mock import patch, MagicMock
from attendance_anomaly_engine.engine.attendance_process import (
    detect_shift_boundry_and_ghost_anomaly,
    detect_absent_steak_anomaly,
    check_overtime_anomaly,
    get_anomaly_rule,
    create_anomaly_attendance,
    mark_in_attendance_anomaly_rule_applied
)


class TestDetectShiftBoundryAndGhostAnomaly(unittest.TestCase):
    """
    Test cases for detect_shift_boundry_and_ghost_anomaly function

    Tests boundary violations (late entry/early exit) and ghost anomalies
    """

    def setUp(self):
        """Set up test data"""
        self.employee_id = "EMP001"
        self.shift_name = "Morning Shift"
        self.attendance_date = getdate()
        self.tz = ZoneInfo("UTC")

    def tearDown(self):
        """Clean up after tests"""
        pass

    def create_mock_attendance(self, checkin_time=None, checkout_time=None, status="Present"):
        """
        Helper method to create mock attendance record

        Args:
            checkin_time (datetime): Check-in time
            checkout_time (datetime): Check-out time
            status (str): Attendance status

        Returns:
            dict: Mock attendance record
        """
        return {
            "name": "ATT-001",
            "employee": self.employee_id,
            "attendance_date": self.attendance_date,
            "shift": self.shift_name,
            "in_time": checkin_time,
            "out_time": checkout_time,
            "status": status
        }

    def create_mock_shift(self, start_time="09:00", end_time="18:00", is_night_shift=False):
        """
        Helper method to create mock shift

        Args:
            start_time (str): Shift start time
            end_time (str): Shift end time
            is_night_shift (bool): Is night shift

        Returns:
            MagicMock: Mock shift document
        """
        shift = MagicMock()
        shift.name = self.shift_name
        shift.start_time = start_time
        shift.end_time = end_time
        shift.custom_is_night_shift = is_night_shift
        return shift

    def create_mock_anomaly_rule(self, late_grace=5, early_grace=5, night_shifts=0, overtime_threshold=1, cons_absences=3):
        """
        Helper method to create mock anomaly rule

        Args:
            late_grace (int): Late entry grace period in minutes
            early_grace (int): Early exit grace period in minutes
            night_shifts (int): Consecutive night shifts threshold
            overtime_threshold (int): Overtime threshold in hours
            cons_absences (int): Consecutive absences threshold

        Returns:
            dict: Mock anomaly rule
        """
        return {
            "shift_type": self.shift_name,
            "late_entry_grace_period": late_grace,
            "early_exit_grace_period": early_grace,
            "night_shifts_consecutive": night_shifts,
            "overtime_threshold": overtime_threshold,
            "consecutive_absences": cons_absences,
            "is_active": 1
        }

    @patch('attendance_anomaly_engine.engine.attendance_process.frappe')
    @patch('attendance_anomaly_engine.engine.attendance_process.create_anomaly_attendance')
    def test_late_entry_detection(self, mock_create_anomaly, mock_frappe):
        """
        Test Case 1: Late Entry Detection

        Scenario: Employee arrives 10 minutes late (grace period is 5 minutes)
        Expected: Boundary anomaly should be created
        """
        # Setup
        checkin_time = datetime.combine(self.attendance_date, time(9, 10)).replace(tzinfo=self.tz)
        attendance = [self.create_mock_attendance(checkin_time=checkin_time, checkout_time=None)]
        shift = self.create_mock_shift(start_time="09:00")
        anomaly_rule = self.create_mock_anomaly_rule(late_grace=5)

        # Mock dependencies
        mock_frappe.db.get_single_value.return_value = "UTC"
        mock_frappe.get_doc.return_value = shift

        with patch('attendance_anomaly_engine.engine.attendance_process.get_anomaly_rule', return_value=anomaly_rule):
            with patch('attendance_anomaly_engine.engine.attendance_process.mark_in_attendance_anomaly_rule_applied'):
                with patch('attendance_anomaly_engine.engine.attendance_process.check_night_shift', return_value=False):
                    detect_shift_boundry_and_ghost_anomaly(self.employee_id, attendance)

        # Verify: create_anomaly_attendance was called for late entry
        self.assertTrue(mock_create_anomaly.called)
        call_kwargs = mock_create_anomaly.call_args[1]
        self.assertEqual(call_kwargs['type'], 'Boundary')
        self.assertIn('Late Entry', call_kwargs['description'])

    @patch('attendance_anomaly_engine.engine.attendance_process.frappe')
    @patch('attendance_anomaly_engine.engine.attendance_process.create_anomaly_attendance')
    def test_early_exit_detection(self, mock_create_anomaly, mock_frappe):
        """
        Test Case 2: Early Exit Detection

        Scenario: Employee leaves 10 minutes early (grace period is 5 minutes)
        Expected: Boundary anomaly should be created
        """
        # Setup
        checkin_time = datetime.combine(self.attendance_date, time(9, 0)).replace(tzinfo=self.tz)
        checkout_time = datetime.combine(self.attendance_date, time(17, 50)).replace(tzinfo=self.tz)
        attendance = [self.create_mock_attendance(checkin_time=checkin_time, checkout_time=checkout_time)]
        shift = self.create_mock_shift(start_time="09:00", end_time="18:00")
        anomaly_rule = self.create_mock_anomaly_rule(early_grace=5)

        # Mock dependencies
        mock_frappe.db.get_single_value.return_value = "UTC"
        mock_frappe.get_doc.return_value = shift

        with patch('attendance_anomaly_engine.engine.attendance_process.get_anomaly_rule', return_value=anomaly_rule):
            with patch('attendance_anomaly_engine.engine.attendance_process.mark_in_attendance_anomaly_rule_applied'):
                with patch('attendance_anomaly_engine.engine.attendance_process.check_night_shift', return_value=False):
                    detect_shift_boundry_and_ghost_anomaly(self.employee_id, attendance)

        # Verify: create_anomaly_attendance was called for early exit
        self.assertTrue(mock_create_anomaly.called)
        call_kwargs = mock_create_anomaly.call_args[1]
        self.assertEqual(call_kwargs['type'], 'Boundary')
        self.assertIn('Early Exit', call_kwargs['description'])

    @patch('attendance_anomaly_engine.engine.attendance_process.frappe')
    @patch('attendance_anomaly_engine.engine.attendance_process.create_anomaly_attendance')
    def test_ghost_anomaly_missing_checkin(self, mock_create_anomaly, mock_frappe):
        """
        Test Case 3: Ghost Anomaly - Missing Check-in

        Scenario: Employee has checkout but no checkin, status is Present
        Expected: Ghost anomaly should be created
        """
        # Setup
        checkout_time = datetime.combine(self.attendance_date, time(18, 0)).replace(tzinfo=self.tz)
        attendance = [self.create_mock_attendance(checkin_time=None, checkout_time=checkout_time, status="Present")]
        shift = self.create_mock_shift()
        anomaly_rule = self.create_mock_anomaly_rule()

        # Mock dependencies
        mock_frappe.db.get_single_value.return_value = "UTC"
        mock_frappe.get_doc.return_value = shift

        with patch('attendance_anomaly_engine.engine.attendance_process.get_anomaly_rule', return_value=anomaly_rule):
            with patch('attendance_anomaly_engine.engine.attendance_process.mark_in_attendance_anomaly_rule_applied'):
                with patch('attendance_anomaly_engine.engine.attendance_process.check_night_shift', return_value=False):
                    detect_shift_boundry_and_ghost_anomaly(self.employee_id, attendance)

        # Verify: Ghost anomaly was created
        calls = mock_create_anomaly.call_args_list
        ghost_calls = [c for c in calls if c[1].get('type') == 'Ghost']
        self.assertTrue(len(ghost_calls) > 0, "Ghost anomaly should be created")

    @patch('attendance_anomaly_engine.engine.attendance_process.frappe')
    @patch('attendance_anomaly_engine.engine.attendance_process.create_anomaly_attendance')
    def test_ghost_anomaly_missing_checkout(self, mock_create_anomaly, mock_frappe):
        """
        Test Case 4: Ghost Anomaly - Missing Check-out

        Scenario: Employee has checkin but no checkout, status is Present
        Expected: Ghost anomaly should be created
        """
        # Setup
        checkin_time = datetime.combine(self.attendance_date, time(9, 0)).replace(tzinfo=self.tz)
        attendance = [self.create_mock_attendance(checkin_time=checkin_time, checkout_time=None, status="Present")]
        shift = self.create_mock_shift()
        anomaly_rule = self.create_mock_anomaly_rule()

        # Mock dependencies
        mock_frappe.db.get_single_value.return_value = "UTC"
        mock_frappe.get_doc.return_value = shift

        with patch('attendance_anomaly_engine.engine.attendance_process.get_anomaly_rule', return_value=anomaly_rule):
            with patch('attendance_anomaly_engine.engine.attendance_process.mark_in_attendance_anomaly_rule_applied'):
                with patch('attendance_anomaly_engine.engine.attendance_process.check_night_shift', return_value=False):
                    detect_shift_boundry_and_ghost_anomaly(self.employee_id, attendance)

        # Verify: Ghost anomaly was created
        calls = mock_create_anomaly.call_args_list
        ghost_calls = [c for c in calls if c[1].get('type') == 'Ghost']
        self.assertTrue(len(ghost_calls) > 0, "Ghost anomaly should be created for missing checkout")

    @patch('attendance_anomaly_engine.engine.attendance_process.frappe')
    @patch('attendance_anomaly_engine.engine.attendance_process.create_anomaly_attendance')
    def test_ghost_anomaly_not_created_for_absent(self, mock_create_anomaly, mock_frappe):
        """
        Test Case 5: Ghost Anomaly - Not Created for Absent Status

        Scenario: Employee has no checkin/checkout but status is Absent (legitimate)
        Expected: Ghost anomaly should NOT be created
        """
        # Setup
        attendance = [self.create_mock_attendance(checkin_time=None, checkout_time=None, status="Absent")]
        shift = self.create_mock_shift()
        anomaly_rule = self.create_mock_anomaly_rule()

        # Mock dependencies
        mock_frappe.db.get_single_value.return_value = "UTC"
        mock_frappe.get_doc.return_value = shift

        with patch('attendance_anomaly_engine.engine.attendance_process.get_anomaly_rule', return_value=anomaly_rule):
            with patch('attendance_anomaly_engine.engine.attendance_process.mark_in_attendance_anomaly_rule_applied'):
                with patch('attendance_anomaly_engine.engine.attendance_process.check_night_shift', return_value=False):
                    detect_shift_boundry_and_ghost_anomaly(self.employee_id, attendance)

        # Verify: Ghost anomaly was NOT created for Absent status
        calls = mock_create_anomaly.call_args_list
        ghost_calls = [c for c in calls if c[1].get('type') == 'Ghost']
        self.assertEqual(len(ghost_calls), 0, "Ghost anomaly should not be created for Absent status")

    @patch('attendance_anomaly_engine.engine.attendance_process.frappe')
    @patch('attendance_anomaly_engine.engine.attendance_process.create_anomaly_attendance')
    def test_within_grace_period_no_anomaly(self, mock_create_anomaly, mock_frappe):
        """
        Test Case 6: Within Grace Period - No Anomaly

        Scenario: Employee arrives 3 minutes late (grace period is 5 minutes)
        Expected: No anomaly should be created
        """
        # Setup
        checkin_time = datetime.combine(self.attendance_date, time(9, 3)).replace(tzinfo=self.tz)
        checkout_time = datetime.combine(self.attendance_date, time(18, 0)).replace(tzinfo=self.tz)
        attendance = [self.create_mock_attendance(checkin_time=checkin_time, checkout_time=checkout_time)]
        shift = self.create_mock_shift()
        anomaly_rule = self.create_mock_anomaly_rule(late_grace=5)

        # Mock dependencies
        mock_frappe.db.get_single_value.return_value = "UTC"
        mock_frappe.get_doc.return_value = shift

        with patch('attendance_anomaly_engine.engine.attendance_process.get_anomaly_rule', return_value=anomaly_rule):
            with patch('attendance_anomaly_engine.engine.attendance_process.mark_in_attendance_anomaly_rule_applied'):
                with patch('attendance_anomaly_engine.engine.attendance_process.check_night_shift', return_value=False):
                    detect_shift_boundry_and_ghost_anomaly(self.employee_id, attendance)

        # Verify: No Boundary anomaly was created
        calls = mock_create_anomaly.call_args_list
        boundary_calls = [c for c in calls if c[1].get('type') == 'Boundary']
        self.assertEqual(len(boundary_calls), 0, "No boundary anomaly should be created within grace period")

    @patch('attendance_anomaly_engine.engine.attendance_process.frappe')
    @patch('attendance_anomaly_engine.engine.attendance_process.create_anomaly_attendance')
    def test_night_shift_doubled_grace_period(self, mock_create_anomaly, mock_frappe):
        """
        Test Case 7: Night Shift with Doubled Grace Period

        Scenario: Employee on consecutive night shifts, late by 8 minutes (grace=5, doubled=10)
        Expected: No boundary anomaly (within doubled grace period)
        """
        # Setup
        checkin_time = datetime.combine(self.attendance_date, time(9, 8)).replace(tzinfo=self.tz)
        checkout_time = datetime.combine(self.attendance_date, time(18, 0)).replace(tzinfo=self.tz)
        attendance = [self.create_mock_attendance(checkin_time=checkin_time, checkout_time=checkout_time)]
        shift = self.create_mock_shift()
        anomaly_rule = self.create_mock_anomaly_rule(late_grace=5, night_shifts=2)

        # Mock dependencies
        mock_frappe.db.get_single_value.return_value = "UTC"
        mock_frappe.get_doc.return_value = shift

        with patch('attendance_anomaly_engine.engine.attendance_process.get_anomaly_rule', return_value=anomaly_rule):
            with patch('attendance_anomaly_engine.engine.attendance_process.mark_in_attendance_anomaly_rule_applied'):
                with patch('attendance_anomaly_engine.engine.attendance_process.check_night_shift', return_value=True):
                    detect_shift_boundry_and_ghost_anomaly(self.employee_id, attendance)

        # Verify: No boundary anomaly within doubled grace period
        calls = mock_create_anomaly.call_args_list
        boundary_calls = [c for c in calls if c[1].get('type') == 'Boundary']
        self.assertEqual(len(boundary_calls), 0, "No boundary anomaly within doubled grace period for night shift")


class TestDetectAbsentStreakAnomaly(unittest.TestCase):
    """
    Test cases for detect_absent_steak_anomaly function

    Tests consecutive absence detection
    """

    def setUp(self):
        """Set up test data"""
        self.employee_id = "EMP001"
        self.shift_name = "Morning Shift"
        self.start_date = getdate()

    def create_mock_attendance_record(self, status="Present", days_offset=0):
        """
        Helper to create mock attendance record

        Args:
            status (str): Attendance status
            days_offset (int): Days offset from start date

        Returns:
            dict: Mock attendance record
        """
        return {
            "name": f"ATT-{days_offset:03d}",
            "employee": self.employee_id,
            "attendance_date": add_days(self.start_date, days_offset),
            "shift": self.shift_name,
            "status": status
        }

    @patch('attendance_anomaly_engine.engine.attendance_process.frappe')
    @patch('attendance_anomaly_engine.engine.attendance_process.create_anomaly_attendance')
    def test_single_absence_no_anomaly(self, mock_create_anomaly, mock_frappe):
        """
        Test Case 1: Single Absence - No Anomaly

        Scenario: Employee is absent once (threshold is 3 days)
        Expected: No anomaly should be created
        """
        # Setup
        attendance = [self.create_mock_attendance_record(status="Absent", days_offset=0)]
        shift = MagicMock()
        anomaly_rule = {"consecutive_absences": 3, "is_active": 1}

        mock_frappe.get_doc.return_value = shift

        with patch('attendance_anomaly_engine.engine.attendance_process.get_anomaly_rule', return_value=anomaly_rule):
            detect_absent_steak_anomaly(self.employee_id, attendance)

        # Verify: No anomaly was created
        self.assertFalse(mock_create_anomaly.called, "No anomaly for single absence")

    @patch('attendance_anomaly_engine.engine.attendance_process.frappe')
    @patch('attendance_anomaly_engine.engine.attendance_process.create_anomaly_attendance')
    def test_three_consecutive_absences_anomaly_created(self, mock_create_anomaly, mock_frappe):
        """
        Test Case 2: Three Consecutive Absences - Anomaly Created

        Scenario: Employee is absent 3 consecutive days (threshold is 3)
        Expected: Streak anomaly should be created
        """
        # Setup
        attendance = [
            self.create_mock_attendance_record(status="Absent", days_offset=0),
            self.create_mock_attendance_record(status="Absent", days_offset=1),
            self.create_mock_attendance_record(status="Absent", days_offset=2),
        ]
        shift = MagicMock()
        anomaly_rule = {"consecutive_absences": 3, "is_active": 1}

        mock_frappe.get_doc.return_value = shift

        with patch('attendance_anomaly_engine.engine.attendance_process.get_anomaly_rule', return_value=anomaly_rule):
            detect_absent_steak_anomaly(self.employee_id, attendance)

        # Verify: Anomaly was created for the 3rd absent record
        self.assertTrue(mock_create_anomaly.called)
        call_kwargs = mock_create_anomaly.call_args[1]
        self.assertEqual(call_kwargs['type'], 'Streak')

    @patch('attendance_anomaly_engine.engine.attendance_process.frappe')
    @patch('attendance_anomaly_engine.engine.attendance_process.create_anomaly_attendance')
    def test_absence_interrupted_by_present(self, mock_create_anomaly, mock_frappe):
        """
        Test Case 3: Absence Interrupted by Present - Streak Reset

        Scenario: Employee absent 2 days, then present, then absent again
        Expected: Streak resets when employee is present
        """
        # Setup
        attendance = [
            self.create_mock_attendance_record(status="Absent", days_offset=0),
            self.create_mock_attendance_record(status="Absent", days_offset=1),
            self.create_mock_attendance_record(status="Present", days_offset=2),
            self.create_mock_attendance_record(status="Absent", days_offset=3),
        ]
        shift = MagicMock()
        anomaly_rule = {"consecutive_absences": 3, "is_active": 1}

        mock_frappe.get_doc.return_value = shift

        with patch('attendance_anomaly_engine.engine.attendance_process.get_anomaly_rule', return_value=anomaly_rule):
            detect_absent_steak_anomaly(self.employee_id, attendance)

        # Verify: No anomaly created (streak was reset)
        self.assertFalse(mock_create_anomaly.called, "Streak should be reset by present status")

    @patch('attendance_anomaly_engine.engine.attendance_process.frappe')
    @patch('attendance_anomaly_engine.engine.attendance_process.create_anomaly_attendance')
    def test_on_leave_resets_absence_streak(self, mock_create_anomaly, mock_frappe):
        """
        Test Case 4: On Leave Resets Absence Streak

        Scenario: Employee absent 2 days, then on leave, then absent again
        Expected: Streak resets when employee is "On Leave"
        """
        # Setup
        attendance = [
            self.create_mock_attendance_record(status="Absent", days_offset=0),
            self.create_mock_attendance_record(status="Absent", days_offset=1),
            self.create_mock_attendance_record(status="On Leave", days_offset=2),
            self.create_mock_attendance_record(status="Absent", days_offset=3),
        ]
        shift = MagicMock()
        anomaly_rule = {"consecutive_absences": 3, "is_active": 1}

        mock_frappe.get_doc.return_value = shift

        with patch('attendance_anomaly_engine.engine.attendance_process.get_anomaly_rule', return_value=anomaly_rule):
            detect_absent_steak_anomaly(self.employee_id, attendance)

        # Verify: Streak was reset by "On Leave" status
        self.assertFalse(mock_create_anomaly.called, "Streak should be reset by On Leave status")

    @patch('attendance_anomaly_engine.engine.attendance_process.frappe')
    @patch('attendance_anomaly_engine.engine.attendance_process.create_anomaly_attendance')
    def test_five_consecutive_absences_anomaly_created(self, mock_create_anomaly, mock_frappe):
        """
        Test Case 5: Five Consecutive Absences - Multiple Anomalies

        Scenario: Employee is absent 5 consecutive days (threshold is 3)
        Expected: Anomalies should be created on day 3, 4, and 5
        """
        # Setup
        attendance = [
            self.create_mock_attendance_record(status="Absent", days_offset=0),
            self.create_mock_attendance_record(status="Absent", days_offset=1),
            self.create_mock_attendance_record(status="Absent", days_offset=2),
            self.create_mock_attendance_record(status="Absent", days_offset=3),
            self.create_mock_attendance_record(status="Absent", days_offset=4),
        ]
        shift = MagicMock()
        anomaly_rule = {"consecutive_absences": 3, "is_active": 1}

        mock_frappe.get_doc.return_value = shift

        with patch('attendance_anomaly_engine.engine.attendance_process.get_anomaly_rule', return_value=anomaly_rule):
            detect_absent_steak_anomaly(self.employee_id, attendance)

        # Verify: Anomalies were created for each day >= threshold
        self.assertEqual(mock_create_anomaly.call_count, 3, "Anomaly created for each day >= threshold")

    @patch('attendance_anomaly_engine.engine.attendance_process.frappe')
    @patch('attendance_anomaly_engine.engine.attendance_process.create_anomaly_attendance')
    def test_disabled_rule_no_anomaly(self, mock_create_anomaly, mock_frappe):
        """
        Test Case 6: Disabled Rule - No Anomaly

        Scenario: Absence threshold is 0 (rule disabled)
        Expected: No anomaly should be created
        """
        # Setup
        attendance = [
            self.create_mock_attendance_record(status="Absent", days_offset=0),
            self.create_mock_attendance_record(status="Absent", days_offset=1),
            self.create_mock_attendance_record(status="Absent", days_offset=2),
        ]
        shift = MagicMock()
        anomaly_rule = {"consecutive_absences": 0, "is_active": 1}

        mock_frappe.get_doc.return_value = shift

        with patch('attendance_anomaly_engine.engine.attendance_process.get_anomaly_rule', return_value=anomaly_rule):
            detect_absent_steak_anomaly(self.employee_id, attendance)

        # Verify: No anomaly created (rule disabled)
        self.assertFalse(mock_create_anomaly.called, "No anomaly when rule disabled")


class TestCheckOvertimeAnomaly(unittest.TestCase):
    """
    Test cases for check_overtime_anomaly function

    Tests overtime and OT padding fraud detection
    """

    def setUp(self):
        """Set up test data"""
        self.employee_id = "EMP001"
        self.shift_name = "Morning Shift"
        self.attendance_date = getdate()
        self.tz = ZoneInfo("UTC")

    def create_mock_attendance(self, checkout_time=None, status="Present"):
        """Helper to create mock attendance"""
        return {
            "name": "ATT-001",
            "employee": self.employee_id,
            "attendance_date": self.attendance_date,
            "shift": self.shift_name,
            "in_time": datetime.combine(self.attendance_date, time(9, 0)).replace(tzinfo=self.tz),
            "out_time": checkout_time,
            "status": status
        }

    def create_mock_shift(self, end_time="18:00", is_night_shift=False):
        """Helper to create mock shift"""
        shift = MagicMock()
        shift.name = self.shift_name
        shift.end_time = end_time
        shift.custom_is_night_shift = is_night_shift
        return shift

    def create_mock_anomaly_rule(self, overtime_threshold=1):
        """Helper to create mock anomaly rule"""
        return {
            "shift_type": self.shift_name,
            "overtime_threshold": overtime_threshold,
            "is_active": 1
        }

    @patch('attendance_anomaly_engine.engine.attendance_process.frappe')
    @patch('attendance_anomaly_engine.engine.attendance_process.create_anomaly_attendance')
    def test_no_checkout_no_anomaly(self, mock_create_anomaly, mock_frappe):
        """
        Test Case 1: No Checkout - No Anomaly

        Scenario: Employee has no checkout time
        Expected: No anomaly should be created
        """
        # Setup
        attendance = [self.create_mock_attendance(checkout_time=None)]
        shift = self.create_mock_shift()
        anomaly_rule = self.create_mock_anomaly_rule()

        mock_frappe.db.get_single_value.return_value = "UTC"
        mock_frappe.get_doc.return_value = shift

        with patch('attendance_anomaly_engine.engine.attendance_process.get_anomaly_rule', return_value=anomaly_rule):
            with patch('attendance_anomaly_engine.engine.attendance_process.get_employee_timesheet', return_value={}):
                check_overtime_anomaly(self.employee_id, attendance)

        # Verify: No anomaly created
        self.assertFalse(mock_create_anomaly.called, "No anomaly when no checkout")

    @patch('attendance_anomaly_engine.engine.attendance_process.frappe')
    @patch('attendance_anomaly_engine.engine.attendance_process.create_anomaly_attendance')
    def test_overtime_within_threshold(self, mock_create_anomaly, mock_frappe):
        """
        Test Case 2: Overtime Within Threshold - No Anomaly

        Scenario: Employee works 30 minutes overtime (threshold is 1 hour)
        Expected: No anomaly should be created
        """
        # Setup
        checkout_time = datetime.combine(self.attendance_date, time(18, 30)).replace(tzinfo=self.tz)
        attendance = [self.create_mock_attendance(checkout_time=checkout_time)]
        shift = self.create_mock_shift(end_time="18:00")
        anomaly_rule = self.create_mock_anomaly_rule(overtime_threshold=1)

        mock_frappe.db.get_single_value.return_value = "UTC"
        mock_frappe.get_doc.return_value = shift

        with patch('attendance_anomaly_engine.engine.attendance_process.get_anomaly_rule', return_value=anomaly_rule):
            with patch('attendance_anomaly_engine.engine.attendance_process.get_employee_timesheet', return_value={}):
                check_overtime_anomaly(self.employee_id, attendance)

        # Verify: No anomaly within threshold
        self.assertFalse(mock_create_anomaly.called, "No anomaly within overtime threshold")

    @patch('attendance_anomaly_engine.engine.attendance_process.frappe')
    @patch('attendance_anomaly_engine.engine.attendance_process.create_anomaly_attendance')
    def test_legitimate_overtime_detection(self, mock_create_anomaly, mock_frappe):
        """
        Test Case 3: Legitimate Overtime - Anomaly Created

        Scenario: Employee works 2 hours overtime (threshold is 1 hour) with valid timesheet
        Expected: OT anomaly should be created
        """
        # Setup
        checkout_time = datetime.combine(self.attendance_date, time(20, 0)).replace(tzinfo=self.tz)
        attendance = [self.create_mock_attendance(checkout_time=checkout_time)]
        shift = self.create_mock_shift(end_time="18:00")
        anomaly_rule = self.create_mock_anomaly_rule(overtime_threshold=1)

        # Mock timesheet with checkout time after employee checkout (legitimate)
        timesheet = {
            (self.employee_id, self.attendance_date): {
                'to_time': datetime.combine(self.attendance_date, time(21, 0)).replace(tzinfo=self.tz)
            }
        }

        mock_frappe.db.get_single_value.return_value = "UTC"
        mock_frappe.get_doc.return_value = shift

        with patch('attendance_anomaly_engine.engine.attendance_process.get_anomaly_rule', return_value=anomaly_rule):
            with patch('attendance_anomaly_engine.engine.attendance_process.get_employee_timesheet', return_value=timesheet):
                check_overtime_anomaly(self.employee_id, attendance)

        # Verify: OT anomaly was created
        self.assertTrue(mock_create_anomaly.called)
        call_kwargs = mock_create_anomaly.call_args[1]
        self.assertEqual(call_kwargs['type'], 'OT')

    @patch('attendance_anomaly_engine.engine.attendance_process.frappe')
    @patch('attendance_anomaly_engine.engine.attendance_process.create_anomaly_attendance')
    def test_ot_padding_missing_timesheet(self, mock_create_anomaly, mock_frappe):
        """
        Test Case 4: OT Padding - Missing Timesheet

        Scenario: Employee claims 2 hours overtime but no timesheet found
        Expected: OT Padding anomaly should be created
        """
        # Setup
        checkout_time = datetime.combine(self.attendance_date, time(20, 0)).replace(tzinfo=self.tz)
        attendance = [self.create_mock_attendance(checkout_time=checkout_time)]
        shift = self.create_mock_shift(end_time="18:00")
        anomaly_rule = self.create_mock_anomaly_rule(overtime_threshold=1)

        mock_frappe.db.get_single_value.return_value = "UTC"
        mock_frappe.get_doc.return_value = shift

        with patch('attendance_anomaly_engine.engine.attendance_process.get_anomaly_rule', return_value=anomaly_rule):
            with patch('attendance_anomaly_engine.engine.attendance_process.get_employee_timesheet', return_value={}):
                check_overtime_anomaly(self.employee_id, attendance)

        # Verify: OT Padding anomaly was created
        calls = mock_create_anomaly.call_args_list
        padding_calls = [c for c in calls if c[1].get('type') == 'OT Padding']
        self.assertTrue(len(padding_calls) > 0, "OT Padding anomaly should be created for missing timesheet")

    @patch('attendance_anomaly_engine.engine.attendance_process.frappe')
    @patch('attendance_anomaly_engine.engine.attendance_process.create_anomaly_attendance')
    def test_ot_padding_checkout_before_timesheet(self, mock_create_anomaly, mock_frappe):
        """
        Test Case 5: OT Padding - Checkout Before Timesheet End

        Scenario: Employee claims worked until 20:00 but timesheet shows work until 21:00
        Expected: OT Padding fraud anomaly should be created
        """
        # Setup
        checkout_time = datetime.combine(self.attendance_date, time(20, 0)).replace(tzinfo=self.tz)
        attendance = [self.create_mock_attendance(checkout_time=checkout_time)]
        shift = self.create_mock_shift(end_time="18:00")
        anomaly_rule = self.create_mock_anomaly_rule(overtime_threshold=1)

        # Mock timesheet: employee actually worked until 21:00
        timesheet = {
            (self.employee_id, self.attendance_date): {
                'to_time': datetime.combine(self.attendance_date, time(21, 0)).replace(tzinfo=self.tz)
            }
        }

        mock_frappe.db.get_single_value.return_value = "UTC"
        mock_frappe.get_doc.return_value = shift

        with patch('attendance_anomaly_engine.engine.attendance_process.get_anomaly_rule', return_value=anomaly_rule):
            with patch('attendance_anomaly_engine.engine.attendance_process.get_employee_timesheet', return_value=timesheet):
                check_overtime_anomaly(self.employee_id, attendance)

        # Verify: OT Padding anomaly was created
        calls = mock_create_anomaly.call_args_list
        padding_calls = [c for c in calls if c[1].get('type') == 'OT Padding']
        self.assertTrue(len(padding_calls) > 0, "OT Padding anomaly for checkout before timesheet")

    @patch('attendance_anomaly_engine.engine.attendance_process.frappe')
    @patch('attendance_anomaly_engine.engine.attendance_process.create_anomaly_attendance')
    def test_night_shift_checkout_date_adjustment(self, mock_create_anomaly, mock_frappe):
        """
        Test Case 6: Night Shift - Checkout Date Adjusted

        Scenario: Night shift employee works past midnight (checkout next day)
        Expected: Should handle date correctly
        """
        # Setup - night shift checkout at 02:00 next day
        next_day = add_days(self.attendance_date, 1)
        checkout_time = datetime.combine(next_day, time(2, 0)).replace(tzinfo=self.tz)
        attendance = [self.create_mock_attendance(checkout_time=checkout_time)]
        shift = self.create_mock_shift(end_time="23:00", is_night_shift=True)
        anomaly_rule = self.create_mock_anomaly_rule(overtime_threshold=1)

        # Mock timesheet for next day
        timesheet = {
            (self.employee_id, next_day): {
                'to_time': datetime.combine(next_day, time(3, 0)).replace(tzinfo=self.tz)
            }
        }

        mock_frappe.db.get_single_value.return_value = "UTC"
        mock_frappe.get_doc.return_value = shift

        with patch('attendance_anomaly_engine.engine.attendance_process.get_anomaly_rule', return_value=anomaly_rule):
            with patch('attendance_anomaly_engine.engine.attendance_process.get_employee_timesheet', return_value=timesheet):
                check_overtime_anomaly(self.employee_id, attendance)

        # Verify: Processing completed without errors
        # OT anomaly should be created (3 hours after shift end)
        self.assertTrue(mock_create_anomaly.called)


if __name__ == "__main__":
    # Run tests
    unittest.main(verbosity=2)
