from django.contrib.auth import login
from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404, render, redirect
from django.core.exceptions import PermissionDenied
from django.views.decorators.http import require_POST
from django.contrib import messages
from django.core import signing

from .notifications import APPROVAL_SALT, notify_approvers

from .forms import RegisterForm, TaskForm
from .models import Task, User
from .permissions import PermissionChecker

INITIAL_STATUS = {
    User.Role.EMPLOYEE: Task.Status.PENDING,
    User.Role.MANAGER: Task.Status.MANAGER_APPROVED,
    User.Role.CEO: Task.Status.APPROVED,
}


def register(request):
    form = RegisterForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        user = form.save()
        login(request, user)
        return redirect("task_list")
    return render(request, "Managment/register.html", {"form": form})


@login_required
def task_list(request):
    checker = PermissionChecker(request.user)
    tasks = checker.visible_tasks().select_related("created_by", "department")
    rows = [
        {
            "task": task,
            "can_edit": checker.can_edit(task),
            "can_approve": checker.can_approve(task),
            "can_reject": checker.can_reject(task),
            "can_delete": checker.can_delete(task),
        }
        for task in tasks
    ]
    return render(request, "Managment/task_list.html", {"rows": rows})


@login_required
def task_create(request):
    form = TaskForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        task = form.save    (commit=False)
        task.created_by = request.user
        task.department = request.user.department
        task.status = INITIAL_STATUS[request.user.role]
        task.save()
        notify_approvers(request , task)
        return redirect("task_list")
    return render(request, "Managment/task_form.html", {"form": form, "titel": "New task"})


@login_required
def task_edit(request, pk):
    checker = PermissionChecker(request.user)
    task = get_object_or_404(checker.visible_tasks(), pk=pk)
    if not checker.can_edit(task):
        raise PermissionDenied
    form = TaskForm(request.POST or None, instance=task)
    if request.method == "POST" and form.is_valid():
        form.save()
        return redirect("task_list")
    return render(request, "Managment/task_form.html", {"form": form, "title": "Edit task"})


@login_required
@require_POST
def task_delete(request, pk):
    checker = PermissionChecker(request.user)
    task = get_object_or_404(checker.visible_tasks(), pk=pk)
    if not checker.can_delete(task):
        raise PermissionDenied
    task.delete()
    return redirect("task_list")


def change_status(request, pk, new_status):
    checker = PermissionChecker(request.user)
    task = get_object_or_404(checker.visible_tasks(), pk=pk)
    if not checker.can_approve(task):
        raise PermissionDenied
    task.status = new_status
    task.save(update_fields=["status", "updated_at"])
    return redirect("task_list")


def _apply_approval(request, task):
    if request.user.role == User.Role.CEO:
        task.status = Task.Status.APPROVED
    else:
        task.status = Task.Status.MANAGER_APPROVED
    task.save(update_fields=["status", "updated_at"])
    notify_approvers(request, task)


@login_required
@require_POST
def task_approve(request, pk):
    checker = PermissionChecker(request.user)
    task = get_object_or_404(checker.visible_tasks(), pk=pk)
    if not checker.can_approve(task):
        raise PermissionDenied
    _apply_approval(request, task)
    return redirect("task_list")


@login_required
@require_POST
def task_reject(request, pk):
    checker = PermissionChecker(request.user)
    task = get_object_or_404(checker.visible_tasks(), pk=pk)
    if not checker.can_reject(task):
        raise PermissionDenied
    task.status = Task.Status.REJECTED
    task.save(update_fields=["status", "updated_at"])
    return redirect("task_list")


@login_required
def act_by_email(request, token):
    try:
        data = signing.loads(token, salt=APPROVAL_SALT)
    except signing.BadSignature:
        return render(
            request,
            "Managment/review_invalid.html",
            {"reason": "This link is invalid."},
            status=400,
        )

    if data["user"] != request.user.pk:
        raise PermissionDenied

    task = get_object_or_404(Task, pk=data["task"])
    checker = PermissionChecker(request.user)
    if task.status != data["stage"] or not checker.can_approve(task):
        return render(
            request,
            "Managment/review_invalid.html",
            {"reason": "This task has already been handled."},
            status=400,
        )

    if data["action"] == "approve":
        _apply_approval(request, task)
        messages.success(request, f"Approved: {task.title}")
    elif data["action"] == "reject" and checker.can_reject(task):
        task.status = Task.Status.REJECTED
        task.save(update_fields=["status", "updated_at"])
        messages.success(request, f"Rejected: {task.title}")
    else:
        raise PermissionDenied

    return redirect("task_list")
