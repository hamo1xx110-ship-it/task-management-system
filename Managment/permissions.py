from .models import Task, User


class PermissionChecker:
    def __init__(self, user: User):
        self.user = user

    def visible_tasks(self):
        if self.user.role == User.Role.CEO:
            return Task.objects.all()
        if self.user.role == User.Role.MANAGER:
            return Task.objects.filter(department=self.user.department)
        return Task.objects.filter(created_by=self.user)

    def can_view(self, task: Task) -> bool:
        return self.visible_tasks().filter(pk=task.pk).exists()

    def can_edit(self, task: Task) -> bool:
        if self.user.role == User.Role.CEO:
            return True
        if self.user.role == User.Role.MANAGER:
            return task.department_id == self.user.department_id
        return False

    def can_approve(self, task: Task) -> bool:
        if self.user.role == User.Role.CEO:
            return task.status == Task.Status.MANAGER_APPROVED
        if self.user.role == User.Role.MANAGER:
            return (task.status == Task.Status.PENDING
                    and task.department_id == self.user.department_id
                    and task.created_by.role == User.Role.EMPLOYEE)
        return False

    def can_reject(self, task: Task) -> bool:
        if self.user.role == User.Role.CEO:
            return task.status in (Task.Status.PENDING, Task.Status.MANAGER_APPROVED)
        return self.can_approve(task)

    def can_delete(self, task: Task) -> bool:
        return self.user.role == User.Role.CEO
