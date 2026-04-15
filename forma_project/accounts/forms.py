from django import forms
from django.contrib.auth import authenticate, get_user_model
from django.contrib.auth.forms import (
    AuthenticationForm,
    PasswordChangeForm,
    UserCreationForm,
)
from django.utils.translation import gettext_lazy as _

User = get_user_model()

# Tailwind: real utilities are defined on `.forma-input` in static_src/css/input.css (@apply).
# Do not paste utility strings only here — they are purged because content scan skips this file.
INPUT_WIDGET_CLASS = 'forma-input'


def _apply_input_classes(form):
    for field in form.fields.values():
        w = field.widget
        if isinstance(w, (forms.TextInput, forms.EmailInput, forms.PasswordInput)):
            classes = w.attrs.get('class', '')
            w.attrs['class'] = f'{classes} {INPUT_WIDGET_CLASS}'.strip()
        elif isinstance(w, forms.Textarea):
            classes = w.attrs.get('class', '')
            w.attrs['class'] = f'{classes} {INPUT_WIDGET_CLASS}'.strip()


class RegisterForm(UserCreationForm):
    error_messages = {
        **UserCreationForm.error_messages,
        'password_mismatch': _(
            'Those passwords don’t match. Enter the same password in both fields.'
        ),
    }

    class Meta:
        model = User
        fields = ('email', 'password1', 'password2')

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['email'] = forms.EmailField(
            required=True,
            label='Email',
            error_messages={
                'invalid': _(
                    'Enter a valid email address (for example, name@example.com).'
                ),
                'required': _('Enter your email address.'),
            },
            widget=forms.EmailInput(attrs={'autocomplete': 'email'}),
        )
        if 'username' in self.fields:
            del self.fields['username']
        _apply_input_classes(self)
        self.fields['password1'].help_text = ''
        self.fields['password2'].help_text = ''

    def clean_email(self):
        email = self.cleaned_data['email'].strip().lower()
        if User.objects.filter(email__iexact=email).exists():
            raise forms.ValidationError(
                'An account already exists for this email. Sign in instead, or use a different address.'
            )
        return email

    def save(self, commit=True):
        user = super().save(commit=False)
        email = self.cleaned_data['email']
        user.username = email
        user.email = email
        if commit:
            user.save()
        return user


class LoginForm(AuthenticationForm):
    """Authenticate with email + password (username on the user model is set to email at registration)."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields.pop('username', None)
        self.fields['email'] = forms.EmailField(
            label='Email',
            error_messages={
                'invalid': _(
                    'Enter a valid email address (for example, name@example.com).'
                ),
                'required': _('Enter the email you registered with.'),
            },
            widget=forms.EmailInput(attrs={'autofocus': True, 'autocomplete': 'email'}),
        )
        pw = self.fields['password']
        pw.error_messages = {
            **pw.error_messages,
            'required': _('Enter your password.'),
        }
        _apply_input_classes(self)

    def clean(self):
        if self.errors:
            return self.cleaned_data

        email = self.cleaned_data.get('email', '').strip()
        password = self.cleaned_data.get('password')

        if email and password:
            user_obj = User.objects.filter(email__iexact=email).first()
            if user_obj is None:
                raise self.get_invalid_login_error()
            self.user_cache = authenticate(
                self.request,
                username=user_obj.get_username(),
                password=password,
            )
            if self.user_cache is None:
                raise self.get_invalid_login_error()
            self.confirm_login_allowed(self.user_cache)

        return self.cleaned_data


class FormaPasswordChangeForm(PasswordChangeForm):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        _apply_input_classes(self)


class CancelSubscriptionDeleteAccountForm(forms.Form):
    """Confirm password + acknowledge losing subscription, account, and trainer page."""

    acknowledge = forms.BooleanField(
        required=True,
        label=_(
            'I understand that cancelling ends my Forma subscription, permanently deletes '
            'my account and my trainer page, and I would need to start again if I wanted to rejoin.'
        ),
    )
    password = forms.CharField(
        label=_('Current password'),
        widget=forms.PasswordInput(attrs={'autocomplete': 'current-password'}),
    )

    def __init__(self, user, *args, **kwargs):
        self.user = user
        super().__init__(*args, **kwargs)
        _apply_input_classes(self)

    def clean_password(self):
        password = self.cleaned_data['password']
        if not self.user.check_password(password):
            raise forms.ValidationError(_('That password is not correct.'))
        return password


class DeleteAccountForm(forms.Form):
    password = forms.CharField(
        label=_('Current password'),
        widget=forms.PasswordInput(attrs={'autocomplete': 'current-password'}),
    )

    def __init__(self, user, *args, **kwargs):
        self.user = user
        super().__init__(*args, **kwargs)
        _apply_input_classes(self)

    def clean_password(self):
        password = self.cleaned_data['password']
        if not self.user.check_password(password):
            raise forms.ValidationError(_('That password is not correct.'))
        return password
