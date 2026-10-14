from django.test import TestCase

from .models import Department, Task, User
from .permissions import PermissionChecker


class PermissionTests(TestCase):
    def setUp(self):
        self.dev = Department.objects.create(name="Development")
        self.hr = Department.objects.create(name="HR")

        self.ceo = User.objects.create_user(
            "ceo", password="pass12345", role=User.Role.CEO
        )
        self.dev_manager = User.objects.create_user(
            "dev_manager", password="pass12345",
            role=User.Role.MANAGER, department=self.dev,
        )
        self.hr_manager = User.objects.create_user(
            "hr_manager", password="pass12345",
            role=User.Role.MANAGER, department=self.hr,
        )
        self.employee = User.objects.create_user(
            "employee", password="pass12345",
            role=User.Role.EMPLOYEE, department=self.dev,
        )
        self.other_employee = User.objects.create_user(
            "other_employee", password="pass12345",
            role=User.Role.EMPLOYEE, department=self.dev,
        )

        self.task = Task.objects.create(
            title="Fix bug", created_by=self.employee, department=self.dev
        )
        self.other_task = Task.objects.create(
            title="Write docs", created_by=self.other_employee, department=self.dev
        )
        self.hr_task = Task.objects.create(
            title="Hire", created_by=self.hr_manager, department=self.hr
        )

    # ---------- visibility ----------
    def test_employee_sees_only_own_tasks(self):
        tasks = PermissionChecker(self.employee).visible_tasks()
        self.assertIn(self.task, tasks)
        self.assertNotIn(self.other_task, tasks)

    def test_manager_sees_only_own_department(self):
        tasks = PermissionChecker(self.dev_manager).visible_tasks()
        self.assertIn(self.task, tasks)
        self.assertNotIn(self.hr_task, tasks)

    def test_ceo_sees_everything(self):
        tasks = PermissionChecker(self.ceo).visible_tasks()
        self.assertEqual(tasks.count(), 3)

    # ---------- editing and deleting ----------
    def test_employee_cannot_edit_approve_or_delete(self):
        checker = PermissionChecker(self.employee)
        self.assertFalse(checker.can_edit(self.task))
        self.assertFalse(checker.can_approve(self.task))
        self.assertFalse(checker.can_delete(self.task))

    def test_only_ceo_can_delete(self):
        self.assertTrue(PermissionChecker(self.ceo).can_delete(self.task))
        self.assertFalse(PermissionChecker(
            self.dev_manager).can_delete(self.task))

    # ---------- approval workflow ----------
    def test_manager_can_approve_pending_task_in_own_department(self):
        self.assertTrue(PermissionChecker(
            self.dev_manager).can_approve(self.task))

    def test_manager_cannot_approve_other_department_task(self):
        self.assertFalse(PermissionChecker(
            self.hr_manager).can_approve(self.task))

    def test_ceo_cannot_approve_before_manager(self):
        checker = PermissionChecker(self.ceo)
        self.assertFalse(checker.can_approve(self.task))

        self.task.status = Task.Status.MANAGER_APPROVED
        self.task.save()
        self.assertTrue(checker.can_approve(self.task))
