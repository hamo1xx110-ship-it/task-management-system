from django import forms
from django.contrib.auth.forms import UserCreationForm
from .models import Department, Task, User


class RegisterForm(UserCreationForm):
    department = forms.ModelChoiceField(queryset=Department.objects.all())

    class Meta(UserCreationForm.Meta):
        model = User
        fields = ("username","email", "department")

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["password1"].help_text = ""
        self.fields["username"].help_text = ""


def save(self, commit=True):
    user = super().save(commit=False)
    user.role = User.Role.EMPLOYEE

    if commit:
        user.save()
    return user


class TaskForm(forms.ModelForm):
    class Meta:
        model = Task
        fields = ["title", "description"]
