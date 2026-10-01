import os
from django import forms
from .models import BatchSubmission

def get_pictos_dir():
    base_dir = os.path.dirname(os.path.dirname(__file__))
    return os.path.join(base_dir, 'Data', 'pictos')


def get_vertical_picto_choices():
    """Scan Data/pictos and return the shared choices used by left and right slots."""
    choices = [('', '-- None --')]
    pictos_dir = get_pictos_dir()

    if os.path.exists(pictos_dir):
        # Main folder only. custom_uploads are temporary and added in the browser after import.
        files = sorted([f for f in os.listdir(pictos_dir)
                       if f.endswith(('.webp', '.png', '.jpg', '.jpeg'))
                       and os.path.isfile(os.path.join(pictos_dir, f))
                       and not f.endswith('.old')])
        for f in files:
            display_name = os.path.splitext(f)[0].replace('_', ' ').replace('-', ' ').title()
            choices.append((f, display_name))

    return choices


def picto_file_exists(filename):
    """Return True if the file is in Data/pictos or its custom_uploads folder."""
    if not filename:
        return False
    filename = os.path.basename(filename.strip())
    pictos_dir = get_pictos_dir()
    main_path = os.path.join(pictos_dir, filename)
    custom_path = os.path.join(pictos_dir, 'custom_uploads', filename)
    return os.path.isfile(main_path) or os.path.isfile(custom_path)

def get_horizontal_category_choices():
    """Dynamically scan horizantal_Pictos folder for category subfolders"""
    choices = [('', '-- None --')]
    base_dir = os.path.dirname(os.path.dirname(__file__))
    horizontal_dir = os.path.join(base_dir, 'Data', 'horizantal_Pictos')
    
    if os.path.exists(horizontal_dir):
        categories = sorted([d for d in os.listdir(horizontal_dir) if os.path.isdir(os.path.join(horizontal_dir, d))])
        for cat in categories:
            choices.append((cat, cat))
    
    return choices

def get_horizontal_files_for_category(category):
    """Get files for a specific horizontal category"""
    files = []
    base_dir = os.path.dirname(os.path.dirname(__file__))
    cat_dir = os.path.join(base_dir, 'Data', 'horizantal_Pictos', category)
    
    if os.path.exists(cat_dir):
        files = sorted([f for f in os.listdir(cat_dir) if f.endswith(('.webp', '.png', '.jpg', '.jpeg'))])
    
    return files


class MultipleFileInput(forms.ClearableFileInput):
    """Custom widget for multiple file upload"""
    allow_multiple_selected = True


class FlexibleSelect(forms.Select):
    """Select widget that includes the current value in choices even if not in initial choices"""
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
    
    def render(self, name, value, attrs=None, renderer=None):
        # If value exists and is not in choices, add it
        if value and value not in [choice[0] for choice in self.choices]:
            display_name = os.path.splitext(str(value))[0].replace('_', ' ').replace('-', ' ').title()
            self.choices = list(self.choices) + [(value, display_name)]
        return super().render(name, value, attrs, renderer)


class MultipleFileField(forms.FileField):
    """Custom field for multiple file upload"""
    def __init__(self, *args, **kwargs):
        kwargs.setdefault("widget", MultipleFileInput())
        super().__init__(*args, **kwargs)

    def clean(self, data, initial=None):
        single_file_clean = super().clean
        if isinstance(data, (list, tuple)):
            result = [single_file_clean(d, initial) for d in data]
        else:
            result = [single_file_clean(data, initial)]
        return result


class ProductSubmissionForm(forms.Form):
    """Form for product submission with multiple image support and picto position selectors"""
    
    # Multiple file upload field
    product_images = MultipleFileField(
        widget=MultipleFileInput(attrs={
            'class': 'form-control',
            'accept': 'image/*',
            'multiple': True
        })
    )
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        
        picto_choices = get_vertical_picto_choices()

        # Left and right use the same picto list from Data/pictos.
        for field_name in (
            'vertical_pos_1', 'vertical_pos_2', 'vertical_pos_3',
            'right_pos_1', 'right_pos_2', 'right_pos_3',
        ):
            self._add_picto_field(field_name, picto_choices)

    def _add_picto_field(self, field_name, picto_choices):
        current_value = None
        if self.data:
            current_value = self.data.get(field_name, '').strip()
        elif self.initial:
            current_value = self.initial.get(field_name, '').strip()

        choices = list(picto_choices)
        if current_value and current_value not in [choice[0] for choice in choices]:
            display_name = os.path.splitext(current_value)[0].replace('_', ' ').replace('-', ' ').title()
            choices.append((current_value, display_name))

        self.fields[field_name] = forms.CharField(
            required=False,
            widget=forms.Select(choices=choices, attrs={'class': 'form-select'})
        )

    def clean(self):
        cleaned_data = super().clean()

        for field_name in (
            'vertical_pos_1', 'vertical_pos_2', 'vertical_pos_3',
            'right_pos_1', 'right_pos_2', 'right_pos_3',
        ):
            filename = (cleaned_data.get(field_name) or '').strip()
            if filename and not picto_file_exists(filename):
                self.add_error(field_name, f'Selected picto file does not exist: {filename}')

        return cleaned_data
