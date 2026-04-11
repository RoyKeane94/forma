from django.contrib import messages
from django.contrib.auth import get_user_model, login, logout
from django.contrib.auth.decorators import login_required
from django.contrib.auth.mixins import LoginRequiredMixin
from django.contrib.auth.views import LoginView, LogoutView, PasswordChangeView
from django.shortcuts import redirect, render
from django.urls import reverse_lazy
from django.views.generic import TemplateView

from .forms import DeleteAccountForm, FormaPasswordChangeForm, LoginForm, RegisterForm
from .models import Profile


class FormaLoginView(LoginView):
    form_class = LoginForm
    template_name = 'accounts/login.html'
    redirect_authenticated_user = True


class FormaLogoutView(LogoutView):
    next_page = reverse_lazy('accounts:logged_out')


class FormaPasswordChangeView(LoginRequiredMixin, PasswordChangeView):
    form_class = FormaPasswordChangeForm
    template_name = 'accounts/password_change.html'
    success_url = reverse_lazy('pages:my_account')

    def form_valid(self, form):
        messages.success(self.request, 'Your password has been updated.')
        return super().form_valid(form)


class AccountDeletedView(TemplateView):
    template_name = 'accounts/account_deleted.html'


@login_required
def delete_account(request):
    if request.method == 'POST':
        form = DeleteAccountForm(request.user, request.POST)
        if form.is_valid():
            user_pk = request.user.pk
            logout(request)
            get_user_model().objects.filter(pk=user_pk).delete()
            return redirect('accounts:account_deleted')
    else:
        form = DeleteAccountForm(request.user)
    return render(request, 'accounts/delete_account.html', {'form': form})


def register(request):
    if request.user.is_authenticated:
        return redirect('home')
    if request.method == 'POST':
        form = RegisterForm(request.POST)
        if form.is_valid():
            user = form.save()
            Profile.objects.get_or_create(user=user)
            login(request, user, backend='django.contrib.auth.backends.ModelBackend')
            messages.success(request, 'Welcome to Forma.')
            return redirect('home')
    else:
        form = RegisterForm()
    return render(request, 'accounts/register.html', {'form': form})
