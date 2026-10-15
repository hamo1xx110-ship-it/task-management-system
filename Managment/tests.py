from django.test import TestCase
from django.core import mail
from django.urls import reverse

from .notifications import make_token
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
class EmailApprovalTests(TestCase):
    def setUp(self):
        self.dev = Department.objects.create(name="Development")
        self.ceo = User.objects.create_user(
            "ceo", password="pass12345",
            email="ceo@example.com", role=User.Role.CEO,
        )
        self.manager = User.objects.create_user(
            "manager", password="pass12345", email="manager@example.com",
            role=User.Role.MANAGER, department=self.dev,
        )
        self.employee = User.objects.create_user(
            "employee", password="pass12345", email="employee@example.com",
            role=User.Role.EMPLOYEE, department=self.dev,
        )
        self.task = Task.objects.create(
            title="Fix bug", created_by=self.employee, department=self.dev
        )

    def _url(self, task, approver, action):
        return reverse("act_by_email", args=[make_token(task, approver, action)])

    def test_creating_task_emails_the_manager(self):
        self.client.force_login(self.employee)
        self.client.post(
            reverse("task_create"), {"title": "New task", "description": "x"}
        )
        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(mail.outbox[0].to, ["manager@example.com"])

    def test_manager_link_moves_task_to_ceo_and_emails_ceo(self):
        self.client.force_login(self.manager)
        response = self.client.get(self._url(self.task, self.manager, "approve"))
        self.assertEqual(response.status_code, 302)

        self.task.refresh_from_db()
        self.assertEqual(self.task.status, Task.Status.MANAGER_APPROVED)
        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(mail.outbox[0].to, ["ceo@example.com"])

    def test_ceo_link_gives_final_approval(self):
        self.task.status = Task.Status.MANAGER_APPROVED
        self.task.save()
        self.client.force_login(self.ceo)
        self.client.get(self._url(self.task, self.ceo, "approve"))

        self.task.refresh_from_db()
        self.assertEqual(self.task.status, Task.Status.APPROVED)

    def test_reject_link_rejects_task(self):
        self.client.force_login(self.manager)
        self.client.get(self._url(self.task, self.manager, "reject"))

        self.task.refresh_from_db()
        self.assertEqual(self.task.status, Task.Status.REJECTED)

    def test_link_opened_by_wrong_user_is_forbidden(self):
        url = self._url(self.task, self.manager, "approve")
        self.client.force_login(self.ceo)
        response = self.client.get(url)
        self.assertEqual(response.status_code, 403)

        self.task.refresh_from_db()
        self.assertEqual(self.task.status, Task.Status.PENDING)

    def test_link_cannot_be_reused(self):
        url = self._url(self.task, self.manager, "approve")
        self.client.force_login(self.manager)
        self.client.get(url)
        response = self.client.get(url)
        self.assertEqual(response.status_code, 400)

        self.task.refresh_from_db()
        self.assertEqual(self.task.status, Task.Status.MANAGER_APPROVED)

    def test_tampered_link_is_rejected(self):
        url = self._url(self.task, self.manager, "approve") 
        parts = url.rstrip("/").split("/")
        token = parts[-1]
        tampered_token = ("x" if token[0] != "x" else "y") + token[1:]
        parts[-1] = tampered_token
        url = "/".join(parts) + "/"

        self.client.force_login(self.manager)
        response = self.client.get(url)
        self.assertEqual(response.status_code, 400)

        self.task.refresh_from_db()
        self.assertEqual(self.task.status, Task.Status.PENDING)

    def test_anonymous_user_is_redirected_to_login(self):
        response = self.client.get(self._url(self.task, self.manager, "approve"))
        self.assertEqual(response.status_code, 302)
        self.assertIn("/login/", response.url)