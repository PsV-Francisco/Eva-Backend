from django import forms
from django.contrib.auth import get_user_model

from config.forms import BootstrapFormMixin
from CoordinadorApp.models import Desempeno
from DelegadoApp.forms import CompromisoForm
from DelegadoApp.models import Ausencia, Felicitacion, Hito, Reclamo
from FuncionarioApp.forms import AtencionSocialForm, RegistroForm
from SupervisorApp.files import validate_evidence_file


class AusenciaForm(BootstrapFormMixin, forms.ModelForm):
    class Meta:
        model = Ausencia
        fields = ('fecha', 'descripcion', 'desempeno')
        widgets = {
            'fecha': forms.DateTimeInput(attrs={'type': 'datetime-local'}),
        }
        labels = {
            'fecha': 'Fecha',
            'descripcion': 'Descripción',
            'desempeno': 'Funcionario, ítem y período',
        }

    def __init__(self, *args, desempenos=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['desempeno'].queryset = (
            desempenos if desempenos is not None
            else Desempeno.objects.none()
        )

    def save(self, commit=True):
        ausencia = super().save(commit=False)
        ausencia.usuario = self.cleaned_data['desempeno'].usuario
        ausencia.item = self.cleaned_data['desempeno'].item
        ausencia.periodo = self.cleaned_data['desempeno'].periodo
        if commit:
            ausencia.save()
            self.save_m2m()
        return ausencia


class PerformanceLinkedForm(BootstrapFormMixin, forms.ModelForm):
    def __init__(self, *args, desempenos=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['desempeno'].queryset = (
            desempenos if desempenos is not None
            else Desempeno.objects.none()
        )

    def save(self, commit=True):
        record = super().save(commit=False)
        desempenho = self.cleaned_data['desempeno']
        record.usuario = desempenho.usuario
        record.item = desempenho.item
        record.periodo = desempenho.periodo
        if commit:
            record.save()
            self.save_m2m()
        return record


class FelicitacionForm(PerformanceLinkedForm):
    class Meta:
        model = Felicitacion
        fields = ('evidencia', 'fecha', 'ubicacion', 'estado', 'desempeno')
        labels = {
            'evidencia': 'Evidencia',
            'fecha': 'Fecha',
            'ubicacion': 'Ubicación',
            'estado': 'Estado',
            'desempeno': 'Funcionario, ítem y período',
        }


class ReclamoForm(PerformanceLinkedForm):
    class Meta:
        model = Reclamo
        fields = ('evidencia', 'fecha', 'ubicacion', 'estado', 'desempeno')
        labels = {
            'evidencia': 'Evidencia',
            'fecha': 'Fecha',
            'ubicacion': 'Ubicación',
            'estado': 'Estado',
            'desempeno': 'Funcionario, ítem y período',
        }

# Actualizado 22.11 / HU-34
class HitoForm(BootstrapFormMixin, forms.ModelForm):
    evento_recurrente = forms.TypedChoiceField(choices=((0, 'No'), (1, 'Sí')),coerce=int,label='Evento recurrente',)
    incluir_agenda = forms.TypedChoiceField(choices=((0, 'No'), (1, 'Sí')),coerce=int,label='Incluir en agenda',)

    class Meta:
        model = Hito
        fields = (
            'nombre',
            'descripcion',
            'fecha_inicio',
            'fecha_termino',
            'recursos_asociados',
            'estado',
            'evento_recurrente',
            'periodicidad',
            'incluir_agenda',
            'delegacion',
            'territorio',
            'responsables',
        )
        widgets = {
            'fecha_inicio': forms.DateTimeInput(attrs={'type': 'datetime-local'}, format='%Y-%m-%dT%H:%M'),
            'fecha_termino': forms.DateTimeInput(attrs={'type': 'datetime-local'}, format='%Y-%m-%dT%H:%M'),
            'responsables': forms.SelectMultiple(attrs={'size': 6}),
        }
        labels = {
            'fecha_inicio': 'Fecha de inicio',
            'fecha_termino': 'Fecha de término (opcional)',
            'recursos_asociados': 'Recursos asociados',
            'periodicidad': 'Periodicidad',
            'territorio': 'Territorio',
            'delegacion': 'Delegación',
            'responsables': 'Funcionarios responsables',
        }
        help_texts = {
            'periodicidad': 'Obligatoria si el hito es un evento recurrente (por ejemplo: semanal, mensual).',
            'responsables': 'Mantén presionado Ctrl (o Cmd) para seleccionar más de un funcionario.',
        }

    def __init__(self,*args,delegaciones=None,territorios=None,responsables=None,registros=None,**kwargs,):
        super().__init__(*args, **kwargs)
        self.fields['delegacion'].queryset = (delegaciones if delegaciones is not None else self.fields['delegacion'].queryset.none())
        self.fields['territorio'].queryset = (territorios if territorios is not None else self.fields['territorio'].queryset.none())
        self.fields['responsables'].queryset = (responsables if responsables is not None else self.fields['responsables'].queryset.none())
        self.fields['responsables'].label_from_instance = (
            lambda usuario: usuario.get_full_name() or usuario.email
        )
        self.fields['recursos_asociados'].min_value = 0
        self.fields['recursos_asociados'].widget.attrs['min'] = 0

    def clean_recursos_asociados(self):
        recursos = self.cleaned_data.get('recursos_asociados')
        if recursos is not None and recursos < 0:
            raise forms.ValidationError('Los recursos asociados no pueden ser negativos.')
        return recursos

    def clean(self):
        cleaned_data = super().clean()
        delegation = cleaned_data.get('delegacion')
        territory = cleaned_data.get('territorio')
        if delegation and territory and territory.delegacion_id != delegation.pk:
            self.add_error('territorio','El territorio debe pertenecer a la delegación seleccionada.',)
        responsables = cleaned_data.get('responsables')
        if delegation and responsables:
            permitidos = set(
                responsables.filter(
                    usuariodelegacion__delegacion=delegation,
                    usuariodelegacion__fecha_fin__isnull=True,
                ).values_list('pk', flat=True)
            )
            if any(usuario.pk not in permitidos for usuario in responsables):
                self.add_error('responsables','Los responsables deben pertenecer a la delegación seleccionada.',)
        if cleaned_data.get('evento_recurrente') == 1 and not (cleaned_data.get('periodicidad') or '').strip():
            self.add_error('periodicidad','Indica la periodicidad del evento recurrente.',)
        return cleaned_data


class AdminRegistroForm(RegistroForm):
    autor = forms.ModelChoiceField(
        queryset=get_user_model().objects.none(),
        label='Funcionario responsable',
    )

    def __init__(self, *args, autores=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['autor'].queryset = (
            autores if autores is not None
            else get_user_model().objects.none()
        )
        self.fields['autor'].label_from_instance = (
            lambda user: f'{user.get_full_name() or user.email} ({user.email})'
        )
        if self.instance.pk:
            self.fields['autor'].initial = self.instance.autor_id
        # HU-34: hitos operativos de los funcionarios disponibles.
        self._set_hito_queryset(
            Hito.objects.filter(
                estado=Hito.Estado.ABIERTO,
                responsables__in=self.fields['autor'].queryset,
            )
        )

    def clean(self):
        # El tope diario y el hito se validan contra el funcionario elegido,
        # no contra el administrador que registra.
        autor = self.cleaned_data.get('autor')
        if autor is not None:
            self.instance.autor = autor
        return super().clean()


class AdminAtencionSocialForm(AtencionSocialForm):
    autor = forms.ModelChoiceField(
        queryset=get_user_model().objects.none(),
        label='Funcionario responsable',
    )

    def __init__(self, *args, autores=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['autor'].queryset = (
            autores if autores is not None
            else get_user_model().objects.none()
        )
        self.fields['autor'].label_from_instance = (
            lambda user: f'{user.get_full_name() or user.email} ({user.email})'
        )
        if self.instance is not None:
            self.fields['autor'].initial = self.instance.autor_id


class AdminCompromisoForm(CompromisoForm):
    evidencia = forms.FileField(
        label='Archivo de evidencia',
        required=False,
        widget=forms.ClearableFileInput(attrs={
            'accept': 'image/jpeg,image/png,application/pdf',
        }),
    )

    def __init__(self, *args, responsables=None, **kwargs):
        super().__init__(*args, **kwargs)
        if responsables is not None:
            self.fields['responsable'].queryset = responsables

    def clean_evidencia(self):
        uploaded_file = self.cleaned_data.get('evidencia')
        return validate_evidence_file(uploaded_file) if uploaded_file else None
