from django import forms

class UploadForm(forms.Form):
    resume = forms.FileField(
        label='Upload Resume (PDF or DOCX)',
        help_text='Supported formats: PDF, DOCX',
        widget=forms.FileInput(attrs={'accept': '.pdf,.docx'})
    )
    photo = forms.FileField(
        label='Upload Photo (PNG or JPG)',
        help_text='Supported formats: PNG, JPG',
        widget=forms.FileInput(attrs={'accept': '.png,.jpg,.jpeg'})
    )