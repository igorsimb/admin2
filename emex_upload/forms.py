from django import forms


class FileUploadForm(forms.Form):
    """
    A simple form for handling file uploads.
    """

    file = forms.FileField(
        widget=forms.ClearableFileInput(
            attrs={"class": "file-input file-input-bordered w-full"}
        )
    )
