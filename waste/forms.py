from decimal import Decimal

from django import forms
from django.core.exceptions import ValidationError
from django.forms import BaseInlineFormSet, inlineformset_factory
from django.db.models import Q

from .models import CollectionPoint, Submission, SubmissionItem, WasteType


class CollectionPointChoiceField(forms.ModelChoiceField):
    def label_from_instance(self, obj):
        label = f"{obj.name} — {obj.address}"
        if obj.operating_hours:
            label += f" ({obj.operating_hours})"
        return label


class WasteTypeChoiceField(forms.ModelChoiceField):
    def label_from_instance(self, obj):
        name = f"{obj.category} · {obj.name}" if obj.category else obj.name
        if obj.rate_per_kg is None:
            return f"{name} — tarif menunggu konfirmasi"
        rate = f"{obj.rate_per_kg:,.0f}".replace(",", ".")
        return f"{name} — Rp {rate}/kg"


class SubmissionForm(forms.ModelForm):
    delivery_method = forms.ChoiceField(
        choices=(("antar_sendiri", "Antar sendiri"),),
        required=False,
        label="Cara menyetor",
    )
    incentive_allocation = forms.ChoiceField(
        choices=Submission.IncentiveAllocation.choices,
        required=False,
        initial=Submission.IncentiveAllocation.WALLET,
        label="Insentifmu",
    )

    class Meta:
        model = Submission
        fields = ["collection_point", "incentive_allocation"]
        labels = {
            "collection_point": "Titik pengumpulan",
            "incentive_allocation": "Insentifmu",
        }
        widgets = {
            "collection_point": forms.Select(
                attrs={
                    "class": "w-full rounded-lg border border-border-slate bg-surface-card px-3 py-3 text-text-primary focus:bg-surface-card focus:outline-none focus:ring-2 focus:ring-primary-container/20"
                }
            )
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["collection_point"] = CollectionPointChoiceField(
            queryset=CollectionPoint.objects.none(),
            label="Titik pengumpulan",
            widget=forms.Select(
                attrs={
                    "class": "w-full rounded-lg border border-border-slate bg-surface-card px-3 py-3 text-text-primary focus:bg-surface-card focus:outline-none focus:ring-2 focus:ring-primary-container/20"
                }
            ),
        )
        points = CollectionPoint.objects.filter(is_active=True)
        if self.instance and self.instance.pk:
            points = CollectionPoint.objects.filter(
                Q(is_active=True) | Q(pk=self.instance.collection_point_id)
            )
        self.fields["collection_point"].queryset = points.distinct()
        if not self.is_bound and not (self.instance and self.instance.pk):
            points = self.fields["collection_point"].queryset
            default_point = points.filter(name__icontains="Pasar Minggu").first()
            if default_point is None:
                default_point = points.first()
            if default_point:
                self.initial.setdefault("collection_point", default_point.pk)

    def clean_delivery_method(self):
        return self.cleaned_data.get("delivery_method") or "antar_sendiri"

    def clean_incentive_allocation(self):
        return (
            self.cleaned_data.get("incentive_allocation")
            or Submission.IncentiveAllocation.WALLET
        )


class SubmissionItemForm(forms.ModelForm):
    waste_type = WasteTypeChoiceField(
        queryset=WasteType.objects.none(),
        label="Jenis sampah",
        widget=forms.Select(
            attrs={
                "class": "w-full rounded-lg border border-border-slate bg-surface-card px-3 py-3 text-text-primary focus:bg-surface-card focus:outline-none focus:ring-2 focus:ring-primary-container/20"
            }
        ),
    )

    class Meta:
        model = SubmissionItem
        fields = ["waste_type", "estimated_weight"]
        labels = {
            "waste_type": "Jenis sampah",
            "estimated_weight": "Perkiraan berat (kg)",
        }
        widgets = {
            "waste_type": forms.Select(
                attrs={
                    "class": "w-full rounded-lg border border-border-slate bg-surface-card px-3 py-3 text-text-primary focus:bg-surface-card focus:outline-none focus:ring-2 focus:ring-primary-container/20"
                }
            ),
            "estimated_weight": forms.NumberInput(
                attrs={
                    "class": "w-full rounded-lg border border-border-slate bg-surface-card px-3 py-3 text-text-primary focus:bg-surface-card focus:outline-none focus:ring-2 focus:ring-primary-container/20",
                    "min": "0.01",
                    "step": "0.01",
                    "placeholder": "Contoh: 2.50",
                }
            ),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        waste_types = WasteType.objects.filter(is_active=True)
        if self.instance and self.instance.pk:
            waste_types = WasteType.objects.filter(
                Q(is_active=True) | Q(pk=self.instance.waste_type_id)
            )
        self.fields["waste_type"].queryset = waste_types.distinct()
        self.fields["estimated_weight"].min_value = Decimal("0.01")


class BaseSubmissionItemFormSet(BaseInlineFormSet):
    def clean(self):
        super().clean()
        if any(self.errors):
            return

        selected_types = []
        for form in self.forms:
            if not form.cleaned_data or form.cleaned_data.get("DELETE"):
                continue
            waste_type = form.cleaned_data.get("waste_type")
            if waste_type:
                selected_types.append(waste_type.pk)

        if len(selected_types) != len(set(selected_types)):
            raise ValidationError("Pilih setiap jenis sampah hanya satu kali.")


SubmissionItemFormSet = inlineformset_factory(
    Submission,
    SubmissionItem,
    form=SubmissionItemForm,
    formset=BaseSubmissionItemFormSet,
    extra=1,
    min_num=1,
    max_num=6,
    validate_min=True,
    validate_max=True,
    can_delete=True,
)
