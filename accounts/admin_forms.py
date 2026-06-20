from django import forms

from .models import QuotaPlan


class GrantQuotaEntitlementForm(forms.Form):
    plan = forms.ChoiceField(
        choices=[(QuotaPlan.PRO, 'Pro'), (QuotaPlan.PRO_PLUS, 'Pro+')],
        help_text='Pro: unused quota expires at term end. Pro+: unused carries if renewed before expiry.',
    )
    purchased_limit = forms.IntegerField(
        min_value=1,
        help_text='Total signatures purchased for this term.',
    )
    duration_months = forms.IntegerField(
        min_value=1,
        max_value=36,
        initial=3,
        help_text='Term length in calendar months.',
    )
    notes = forms.CharField(
        required=False,
        widget=forms.Textarea(attrs={'rows': 3}),
        help_text='Optional internal note (invoice ref, sales contact, etc.).',
    )


class RenewQuotaEntitlementForm(forms.Form):
    plan = forms.ChoiceField(
        choices=[(QuotaPlan.PRO, 'Pro'), (QuotaPlan.PRO_PLUS, 'Pro+')],
    )
    purchased_limit = forms.IntegerField(min_value=1)
    duration_months = forms.IntegerField(min_value=1, max_value=36, initial=3)
    notes = forms.CharField(required=False, widget=forms.Textarea(attrs={'rows': 3}))
