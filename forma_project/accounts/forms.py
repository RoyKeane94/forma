from django import forms
from django.contrib.auth import authenticate, get_user_model
from django.contrib.auth.forms import (
    AuthenticationForm,
    PasswordChangeForm,
    UserCreationForm,
)
from django.core.exceptions import ValidationError
from django.utils.translation import gettext_lazy as _

from pages.forms import validate_uk_postcode_outward
from pages.models import PrimaryArea

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

    accept_terms = forms.BooleanField(
        required=True,
        label='',
        error_messages={
            'required': _(
                'You must accept the terms and conditions to create an account.'
            ),
        },
        widget=forms.CheckboxInput(
            attrs={
                'class': 'h-4 w-4 shrink-0 border border-rule accent-blue',
            },
        ),
    )

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


class RegisterNameForm(forms.Form):
    first_name = forms.CharField(
        max_length=150,
        label='First name',
        widget=forms.TextInput(attrs={'autocomplete': 'given-name'}),
    )
    last_name = forms.CharField(
        max_length=150,
        label='Last name',
        widget=forms.TextInput(attrs={'autocomplete': 'family-name'}),
    )
    primary_area = forms.ModelChoiceField(
        label='Primary area',
        required=False,
        queryset=PrimaryArea.objects.none(),
        widget=forms.Select(attrs={'class': INPUT_WIDGET_CLASS}),
    )
    location_add_name = forms.CharField(
        required=False,
        label='Add new area name',
        max_length=128,
        widget=forms.TextInput(attrs={'autocomplete': 'off'}),
    )
    location_add_outward = forms.CharField(
        required=False,
        label='Postcode district',
        max_length=16,
        widget=forms.TextInput(attrs={'autocomplete': 'off'}),
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        _apply_input_classes(self)
        self.fields['primary_area'].queryset = PrimaryArea.objects.select_related('district').order_by('name')
        self.fields['primary_area'].empty_label = 'Select your primary area'

    def clean_first_name(self):
        return (self.cleaned_data.get('first_name') or '').strip()

    def clean_last_name(self):
        return (self.cleaned_data.get('last_name') or '').strip()

    def clean(self):
        data = super().clean()
        selected_area = data.get('primary_area')
        add_name = (data.get('location_add_name') or '').strip()
        add_outward = (data.get('location_add_outward') or '').strip()

        if selected_area and add_name:
            self.add_error(
                None,
                'Choose an area from the list or add a new one, not both.',
            )
            return data

        if add_outward and not add_name:
            self.add_error('location_add_name', 'Add an area name for this postcode district.')
            return data

        resolved_area = selected_area
        if add_name:
            if not add_outward:
                self.add_error('location_add_outward', 'Enter the postcode district for your new area.')
                return data
            try:
                outward = validate_uk_postcode_outward(add_outward)
            except ValidationError as exc:
                self.add_error('location_add_outward', exc)
                return data
            resolved_area = PrimaryArea.ensure_for_custom_entry(add_name, outward)
            if resolved_area is None:
                self.add_error('location_add_name', 'Could not add that area. Check the name and postcode district.')
                return data

        if resolved_area is None:
            self.add_error('primary_area', 'Choose an area from the list or add a new one.')
            return data

        data['resolved_primary_area'] = resolved_area
        return data


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
        widget=forms.CheckboxInput(
            attrs={
                'class': 'h-4 w-4 shrink-0 border border-rule accent-blue',
            },
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
