from django import forms
from django.core.files.uploadedfile import UploadedFile

from .models import Profile

MAX_AVATAR_BYTES = 5 * 1024 * 1024
ALLOWED_AVATAR_FORMATS = {"JPEG", "PNG", "WEBP", "GIF"}


class ProfileForm(forms.ModelForm):
    bio = forms.CharField(
        required=False,
        max_length=500,
        widget=forms.Textarea(attrs={"rows": 4, "placeholder": "A short bio"}),
    )

    class Meta:
        model = Profile
        fields = ["first_name", "last_name", "bio", "avatar_path"]
        widgets = {
            "first_name": forms.TextInput(attrs={"placeholder": "First name"}),
            "last_name": forms.TextInput(attrs={"placeholder": "Last name"}),
        }

    def clean_avatar_path(self):
        upload = self.cleaned_data.get("avatar_path")
        # Only validate fresh uploads; an unchanged existing avatar comes back as a FieldFile.
        if isinstance(upload, UploadedFile):
            if upload.size > MAX_AVATAR_BYTES:
                raise forms.ValidationError("That photo is too large (max 5 MB).")
            fmt = getattr(getattr(upload, "image", None), "format", None)
            if fmt not in ALLOWED_AVATAR_FORMATS:
                raise forms.ValidationError("Please upload a JPEG, PNG, WebP or GIF image.")
        return upload