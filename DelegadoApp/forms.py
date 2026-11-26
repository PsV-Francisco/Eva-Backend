from django import forms
from AdminApp.models import Usuario
from CoordinadorApp.models import Periodo
from DelegadoApp.models import Ausencia, Compromiso
from FuncionarioApp.models import Subtipo, Tipo, Vecino, Territorio
from FuncionarioApp.forms import (TipoSubtipoFields,_assign_tipo_subtipo,_set_tipo_subtipo_choices,)
from config.forms import BootstrapFormMixin
from SupervisorApp.models import Evidencia


class CompromisoForm(TipoSubtipoFields, BootstrapFormMixin, forms.ModelForm):
    motivo_reasignacion = forms.CharField(
        required=False,
        label='Motivo de reasignación',
        widget=forms.Textarea(attrs={'class': 'form-control', 'rows': 2}),
    )
    tipo = forms.ModelChoiceField(queryset=Tipo.objects.none(),required=False,label='Tipo',empty_label='Sin tipo (predeterminado)',widget=forms.Select(attrs={'class': 'form-select', 'id': 'id_tipo'}),)
    subtipo = forms.ModelChoiceField(queryset=Subtipo.objects.none(),required=False,label='Subtipo',empty_label='Sin subtipo (predeterminado)',widget=forms.Select(attrs={'class': 'form-select', 'id': 'id_subtipo'}),)
    periodo = forms.ModelChoiceField(queryset=Periodo.objects.filter(estado__iexact=Periodo.Estado.ABIERTO),label='Período de agenda',widget=forms.Select(attrs={'class': 'form-select'}),)
    evidencia = forms.ModelChoiceField(queryset=Evidencia.objects.all(),required=False,label='Evidencia principal',empty_label='Sin evidencia asignada',widget=forms.Select(attrs={'class': 'form-select'}),)

    class Meta:
        model = Compromiso
        fields = ('periodo', 'fecha_solicitud', 'descripcion', 'ambito', 'solicitante', 'territorio', 'responsable', 'fecha_compromiso', 'mes', 'area_apoyo', 'estado', 'tipo', 'subtipo', 'observaciones', 'evidencia')
        labels = {
            'fecha_solicitud': 'Fecha de solicitud',
            'descripcion': 'Descripción del compromiso',
            'ambito': 'Ámbito',
            'solicitante': 'Solicitante / Beneficiario',
            'territorio': 'Territorio',
            'responsable': 'Responsables asignados',
            'fecha_compromiso': 'Fecha comprometida',
            'mes': 'Mes',
            'area_apoyo': 'Área de apoyo',
            'estado': 'Estado',
            'tipo': 'Tipo',
            'subtipo': 'Subtipo',
            'observaciones': 'Observaciones',
            'evidencia': 'Evidencia principal',
        }
        widgets = {
            'fecha_solicitud': forms.DateTimeInput(attrs={'type': 'datetime-local', 'class': 'form-control'}),
            'fecha_compromiso': forms.DateTimeInput(attrs={'type': 'datetime-local', 'class': 'form-control'}),
            'ambito': forms.Select(attrs={'class': 'form-select'}),
            'solicitante': forms.Select(attrs={'class': 'form-select'}),
            'territorio': forms.Select(attrs={'class': 'form-select'}),
            'area_apoyo': forms.TextInput(attrs={'class': 'form-control'}),
            'mes': forms.NumberInput(attrs={'class': 'form-control', 'min': 1, 'max': 12}),
            'estado': forms.Select(attrs={'class': 'form-select'}),
            'observaciones': forms.Textarea(attrs={'rows': 2, 'class': 'form-control'}),
            'responsable': forms.SelectMultiple(attrs={'class': 'form-select', 'size': 4}),
        }

    def __init__(self, *args, user, delegation=None, **kwargs):
        super().__init__(*args, **kwargs)
        _set_tipo_subtipo_choices(self, self.instance)

        self.fields['solicitante'].queryset = Vecino.objects.filter(activo=True).order_by('nombre', 'apellido')
        self.fields['territorio'].queryset = Territorio.objects.all().order_by('nombre')
        
        delegation_id = delegation.pk if delegation else getattr(user, 'delegacion_id', None)
        if delegation_id:
            self.fields['responsable'].queryset = Usuario.objects.filter(
                usuariodelegacion__delegacion_id=delegation_id,
                usuariodelegacion__fecha_fin__isnull=True,
                is_active=True,
            ).distinct().order_by('email')
        else:
            self.fields['responsable'].queryset = Usuario.objects.none()
            
        self.fields['responsable'].help_text = 'Selecciona al menos un responsable.'

    def clean(self):
        cleaned_data = super().clean()
        fecha_comp = cleaned_data.get('fecha_compromiso')
        mes = cleaned_data.get('mes')
        
        # Calcular el número de mes automáticamente si no se especificó
        if fecha_comp and not mes:
            cleaned_data['mes'] = fecha_comp.month
            self.cleaned_data['mes'] = fecha_comp.month

        if self.instance.pk and 'responsable' in cleaned_data:
            previous = set(self.instance.responsable.values_list('pk', flat=True))
            current = set(cleaned_data['responsable'].values_list('pk', flat=True))
            if previous != current and not cleaned_data.get('motivo_reasignacion', '').strip():
                self.add_error('motivo_reasignacion', 'El motivo de reasignación es obligatorio.')

        return cleaned_data

    def save(self, commit=True):
        instance = super().save(commit=False)
        _assign_tipo_subtipo(self, instance)
        if commit:
            instance.save()
            self.save_m2m()
        return instance


class CompromisoEstadoForm(BootstrapFormMixin, forms.Form):
    estado = forms.ChoiceField(choices=Compromiso.Estado.choices, label='Actualizar estado', widget=forms.Select(attrs={'class': 'form-select'}))
    observaciones = forms.CharField(required=False, label='Avance / observaciones', widget=forms.Textarea(attrs={'class': 'form-control', 'rows': 2}))


class AusenciaForm(BootstrapFormMixin, forms.ModelForm):
    class Meta:
        model = Ausencia
        fields = ('desempeno', 'tipo', 'fecha_inicio', 'fecha_fin', 'descripcion')
        labels = {
            'desempeno': 'Funcionario y meta',
            'tipo': 'Tipo de ausencia',
            'fecha_inicio': 'Desde',
            'fecha_fin': 'Hasta',
            'descripcion': 'Descripción / respaldo',
        }
        widgets = {
            'fecha_inicio': forms.DateInput(attrs={'type': 'date', 'class': 'form-control'}),
            'fecha_fin': forms.DateInput(attrs={'type': 'date', 'class': 'form-control'}),
            'descripcion': forms.Textarea(attrs={'rows': 2, 'class': 'form-control'}),
        }

    def __init__(self, *args, desempenos=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['desempeno'].queryset = desempenos if desempenos is not None else self.fields['desempeno'].queryset.none()

    def clean(self):
        cleaned = super().clean()
        start = cleaned.get('fecha_inicio')
        end = cleaned.get('fecha_fin')
        if start and end and end < start:
            self.add_error('fecha_fin', 'La fecha final no puede ser anterior a la inicial.')
        return cleaned
