from django import forms


class BootstrapFormMixin:
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field in self.fields.values():
            widget = field.widget
            if isinstance(widget, forms.CheckboxInput):
                css_class = 'form-check-input'
            elif isinstance(widget, (forms.Select, forms.SelectMultiple)):
                css_class = 'form-select'
            else:
                css_class = 'form-control'
            widget.attrs['class'] = ' '.join(
                part for part in (widget.attrs.get('class', ''), css_class) if part
            )