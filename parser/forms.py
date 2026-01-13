from django import forms

class FileUploadForm(forms.Form):
    file = forms.FileField(
        label="Выберите .xlsx файл",
        widget=forms.ClearableFileInput(
            attrs={
                "class": "file-input file-input-bordered w-full",
                "accept": ".xlsx",
            }
        ),
    )
    include_analogs = forms.BooleanField(
        label="Включить аналоги",
        required=False,
        initial=False,
        widget=forms.CheckboxInput(attrs={"class": "checkbox"}),
    )
