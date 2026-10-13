from django.conf import settings
from django.core import signing
from django.core.mail import send_mail
from django.urls import reverse

from .models import Task, User

APPROVAL_SALT = "task-approval"


def make_token(task, approver, action):
    payload = {
        "task": task.pk,
        "user": approver.pk,
        "stage": task.status,
        "action": action,
    }
    return signing.dumps(payload, salt=APPROVAL_SALT)


def _link(request, task, approver, action):
    path = reverse("act_by_email", args=[make_token(task, approver, action)])
    return request.build_absolute_uri(path)


def _approvers_for(task):
    if task.status == Task.Status.PENDING and task.department_id:
        return User.objects.filter(
            role=User.Role.MANAGER, department_id=task.department_id
        ).exclude(email="")
    if task.status == Task.Status.MANAGER_APPROVED:
        return User.objects.filter(role=User.Role.CEO).exclude(email="")
    return User.objects.none()


def notify_approvers(request, task):
    for approver in _approvers_for(task):
        approve_link = _link(request, task, approver, "approve")
        reject_link = _link(request, task, approver, "reject")
        try:
            send_mail(
                subject=f"Task awaiting your approval: {task.title}",
                message=(
                    f"Hello {approver.username},\n\n"
                    f"{task.created_by.username} submitted a task that needs your approval:\n\n"
                    f"  {task.title}\n"
                    f"  {task.description}\n\n"
                    f"Approve:\n{approve_link}\n\n"
                    f"Reject:\n{reject_link}\n\n"
                    f"You must be logged in as {approver.username} to use these links."
                ),
                from_email=settings.DEFAULT_FROM_EMAIL,
                recipient_list=[approver.email],
            )
        except OSError:
            pass 
