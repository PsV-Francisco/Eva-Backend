from django import forms
from django.db.models import Q
from django.utils import timezone
from django.db import models

from AdminApp.models import Delegacion
from CoordinadorApp.models import AtencionSocial, GestionAtencion, Item, Periodo
from DelegadoApp.models import Compromiso
from FuncionarioApp.models import (Beneficiado,CargoJv,JuntaVecino,Registro,Subtipo,Territorio,Tipo,Vecino,tipo_subtipo_predeterminados,)
from config.forms import BootstrapFormMixin
from SupervisorApp.files import validate_evidence_file


def _assign_tipo_subtipo(form, instance):
    tipo = form.cleaned_data.get('tipo')
    subtipo = form.cleaned_data.get('subtipo')
    if tipo is None and subtipo is not None:
        tipo = subtipo.tipo
    if tipo is None or subtipo is None:
        default_tipo, default_subtipo = tipo_subtipo_predeterminados(tipo)
        tipo = tipo or default_tipo
        subtipo = subtipo or default_subtipo
    instance.tipo = tipo
    instance.subtipo = subtipo


def _set_tipo_subtipo_choices(form, instance=None):
    tipos = _active_catalog_queryset(Tipo)
    if instance and instance.pk and instance.tipo_id:
        tipos = (tipos | Tipo.objects.filter(pk=instance.tipo_id)).distinct()
    form.fields['tipo'].queryset = tipos.order_by('nombre')

    selected_type_id = (
        form.data.get('tipo')
        or form.initial.get('tipo')
        or (instance.tipo_id if instance and instance.pk else None)
    )
    subtipos = _active_catalog_queryset(Subtipo)
    if selected_type_id:
        subtipos = subtipos.filter(tipo_id=selected_type_id)
    if instance and instance.pk and instance.subtipo_id:
        subtipos = subtipos | Subtipo.objects.filter(pk=instance.subtipo_id)
    form.fields['subtipo'].queryset = subtipos.distinct().order_by('nombre')


def _active_catalog_queryset(model):
    return model.objects.filter(estado='ACTIVADO')


class TipoSubtipoFields:
    def clean(self):
        cleaned_data = super().clean()
        tipo = cleaned_data.get('tipo')
        subtipo = cleaned_data.get('subtipo')
        if tipo and subtipo and subtipo.tipo_id != tipo.pk:
            self.add_error('subtipo', 'El subtipo debe pertenecer al tipo seleccionado.')
        return cleaned_data


class FuncionarioCompromisoForm(TipoSubtipoFields, BootstrapFormMixin, forms.ModelForm):
    solicitante = forms.ModelChoiceField(queryset=Beneficiado.objects.all().order_by('nombre', 'apellido'),required=False,label='Solicitante (Beneficiario)',empty_label='Seleccione un beneficiario',widget=forms.Select(attrs={'class': 'form-select'}),)
    territorio = forms.ModelChoiceField(queryset=Territorio.objects.all().order_by('nombre'),required=False,label='Territorio',empty_label='Seleccione un territorio',widget=forms.Select(attrs={'class': 'form-select'}),)
    tipo = forms.ModelChoiceField(queryset=Tipo.objects.filter(estado=Tipo.Estado.ACTIVADO).order_by('nombre'),required=False,label='Tipo',empty_label='Seleccione un tipo',widget=forms.Select(attrs={'class': 'form-select', 'id': 'id_tipo'}),)
    subtipo = forms.ModelChoiceField(queryset=Subtipo.objects.none(),required=False,label='Subtipo',empty_label='Seleccione un subtipo',widget=forms.Select(attrs={'class': 'form-select', 'id': 'id_subtipo'}),)
    periodo = forms.ModelChoiceField(queryset=Periodo.objects.filter(estado=Periodo.Estado.ABIERTO),label='Período de agenda',widget=forms.Select(attrs={'class': 'form-select'}),)

    class Meta:
        model = Compromiso
        fields = [
            'descripcion', 'fecha_solicitud', 'fecha_compromiso', 'ambito',
            'solicitante', 'territorio', 'area_apoyo', 'mes', 'tipo', 'subtipo', 'observaciones'
        ]
        widgets = {
            'descripcion': forms.TextInput(attrs={'class': 'form-control'}),
            'fecha_solicitud': forms.DateTimeInput(attrs={'class': 'form-control', 'type': 'datetime-local'}),
            'fecha_compromiso': forms.DateTimeInput(attrs={'class': 'form-control', 'type': 'datetime-local'}),
            'ambito': forms.Select(attrs={'class': 'form-select'}),
            'area_apoyo': forms.TextInput(attrs={'class': 'form-control'}),
            'mes': forms.NumberInput(attrs={'class': 'form-control', 'min': 1, 'max': 12}),
            'observaciones': forms.Textarea(attrs={'class': 'form-control', 'rows': 3}),
        }

    def clean(self):
        cleaned_data = super().clean()
        fecha_comp = cleaned_data.get('fecha_compromiso')
        mes = cleaned_data.get('mes')
        if fecha_comp and not mes:
            cleaned_data['mes'] = fecha_comp.month
            self.cleaned_data['mes'] = fecha_comp.month
        return cleaned_data

class RegistroForm(TipoSubtipoFields, BootstrapFormMixin, forms.ModelForm):
    tipo = forms.ModelChoiceField(queryset=Tipo.objects.none(),required=False,label='Tipo',empty_label='Sin tipo (predeterminado)',)
    subtipo = forms.ModelChoiceField(queryset=Subtipo.objects.none(),required=False,label='Subtipo',empty_label='Sin subtipo (predeterminado)',)
    evidencia = forms.FileField(label='Archivo de evidencia',required=False,widget=forms.ClearableFileInput(attrs={'accept': 'image/jpeg,image/png,application/pdf','class': 'form-control',}),)

    class Meta:
        model = Registro
        fields = (
            'fecha', 'periodo', 'item', 'descripcion', 'accion', 'contacto',
            'telefono', 'incluir_en_agenda',
        )
        labels = {
            'fecha': 'Fecha de actividad',
            'periodo': 'Período',
            'item': 'Ítem de medición',
            'descripcion': 'Actividad o solicitud',
            'accion': 'Acción realizada',
            'contacto': 'Contacto',
            'telefono': 'Teléfono',
            'incluir_en_agenda': 'Relacionar con la agenda colectiva',
        }
        widgets = {
            'fecha': forms.DateInput(attrs={'type': 'date'}),
            'accion': forms.Textarea(attrs={'rows': 3}),
            'contacto': forms.TextInput(attrs={'autocomplete': 'name'}),
        }

    def __init__(self, *args, user=None, **kwargs):
        super().__init__(*args, **kwargs)
        _set_tipo_subtipo_choices(self, self.instance)
        periods = Periodo.objects.filter(estado=Periodo.Estado.ABIERTO)
        if self.instance.pk and self.instance.periodo_id:
            periods = (periods | Periodo.objects.filter(pk=self.instance.periodo_id)).distinct()
        self.fields['periodo'].queryset = periods
        items = Item.objects.filter(estado=Item.Estado.ACTIVO)
        if self.instance.pk and self.instance.item_id:
            items = (items | Item.objects.filter(pk=self.instance.item_id)).distinct()
        self.fields['item'].queryset = items.order_by('nombre')

    def clean_evidencia(self):
        uploaded_file = self.cleaned_data.get('evidencia')
        return validate_evidence_file(uploaded_file) if uploaded_file else uploaded_file

    def save(self, commit=True):
        instance = super().save(commit=False)
        _assign_tipo_subtipo(self, instance)
        if commit:
            instance.save()
            self.save_m2m()
        return instance


class VecinoForm(BootstrapFormMixin, forms.ModelForm):
    territorio = forms.ModelChoiceField(
        queryset=Territorio.objects.none(),
        required=False,
        label='Territorio existente',
    )
    junta_vecino = forms.ModelChoiceField(
        queryset=JuntaVecino.objects.none(),
        required=False,
        label='Junta de vecinos existente',
    )
    cargo_jv = forms.ModelChoiceField(
        queryset=CargoJv.objects.none(),
        required=False,
        label='Cargo en la junta existente',
    )
    nuevo_territorio = forms.CharField(
        max_length=100,
        required=False,
        label='Crear territorio',
    )
    nuevo_nombre_junta = forms.CharField(
        max_length=100,
        required=False,
        label='Crear junta de vecinos',
    )
    nuevo_domicilio_junta = forms.CharField(
        max_length=100,
        required=False,
        label='Domicilio legal de la nueva junta',
    )
    nuevo_numero_rpj = forms.IntegerField(
        min_value=1,
        required=False,
        label='Número de personalidad jurídica de la nueva junta',
    )
    nuevo_cargo_junta = forms.CharField(
        max_length=100,
        required=False,
        label='Crear cargo en la junta',
    )
    nuevo_cargo_permisos = forms.CharField(
        max_length=500,
        required=False,
        label='Permisos del nuevo cargo',
    )
    estado = forms.ChoiceField(
        choices=Vecino.Estado.choices,
        initial=Vecino.Estado.ACTIVADO,
        widget=forms.Select(attrs={'class': 'form-select', 'id': 'id_estado'}),
        label='Estado'
    )
    activo = forms.BooleanField(
        required=False,
        initial=True,
        widget=forms.CheckboxInput(attrs={'class': 'form-check-input', 'id': 'id_activo'}),
        label='Activo'
    )

    class Meta:
        model = Vecino
        fields = (
            'nombre', 'telefono', 'direccion', 'activo', 'cargo_jv',
            'delegacion', 'junta_vecino', 'territorio', 'estado'
        )
        labels = {
            'nombre': 'Nombre',
            'telefono': 'Teléfono',
            'direccion': 'Dirección',
            'activo': 'Activo',
            'cargo_jv': 'Cargo en Junta de Vecinos',
            'delegacion': 'Delegación',
            'junta_vecino': 'Junta de Vecinos',
            'territorio': 'Territorio',
            'estado': 'Estado',
        }
        widgets = {
            'nombre': forms.TextInput(attrs={'class': 'form-control', 'id': 'id_nombre'}),
            'telefono': forms.TextInput(attrs={'class': 'form-control', 'id': 'id_telefono', 'autocomplete': 'tel'}),
            'direccion': forms.TextInput(attrs={'class': 'form-control', 'id': 'id_direccion', 'autocomplete': 'street-address'}),
            'delegacion': forms.Select(attrs={'class': 'form-select', 'id': 'id_delegacion'}),
            'junta_vecino': forms.Select(attrs={'class': 'form-select', 'id': 'id_junta_vecino'}),
            'cargo_jv': forms.Select(attrs={'class': 'form-select', 'id': 'id_cargo_jv'}),
            'territorio': forms.Select(attrs={'class': 'form-select', 'id': 'id_territorio'}),
        }

    def __init__(self, *args, delegaciones=None, **kwargs):
        super().__init__(*args, **kwargs)
        if delegaciones is None:
            delegaciones = Delegacion.objects.none()
        
        self.fields['delegacion'].queryset = delegaciones.order_by('nombre')

        # Formateo de CARGO_JV: "Nombre + permisos"
        cargos = CargoJv.objects.filter(junta_vecino__delegacion__in=delegaciones)
        self.fields['cargo_jv'].queryset = cargos.distinct().order_by('nombre')
        self.fields['cargo_jv'].label_from_instance = lambda obj: f"{obj.nombre} - {obj.permisos}"

        # Formateo de JUNTA_VECINO: "NUMERO_RPJ + NOMBRE"
        juntas = JuntaVecino.objects.filter(delegacion__in=delegaciones)
        self.fields['junta_vecino'].queryset = juntas.distinct().order_by('nombre')
        self.fields['junta_vecino'].label_from_instance = lambda obj: f"RPJ {obj.numero_rpj} - {obj.nombre}"

        # Formateo de TERRITORIO: "ID + NOMBRE"
        territories = Territorio.objects.filter(delegacion__in=delegaciones)
        self.fields['territorio'].queryset = territories.distinct().order_by('nombre')
        self.fields['territorio'].label_from_instance = lambda obj: f"ID: {obj.pk} - {obj.nombre}"

    def clean_nombre(self):
        return self.cleaned_data['nombre'].strip()

    def clean_telefono(self):
        telefono = self.cleaned_data.get('telefono')
        return telefono.strip() if telefono else telefono


class JuntaVecinoForm(BootstrapFormMixin, forms.ModelForm):
    class Meta:
        model = JuntaVecino
        fields = (
            'nombre', 'domicilio_legal', 'socios_activos', 'fecha_constitucion',
            'numero_rpj', 'fecha_ingreso', 'numero_registro', 'delegacion',
            'territorio',
        )
        labels = {
            'nombre': 'Nombre',
            'domicilio_legal': 'Domicilio Legal',
            'socios_activos': 'Socios Activos',
            'fecha_constitucion': 'Fecha de Constitución',
            'numero_rpj': 'Número RPJ',
            'fecha_ingreso': 'Fecha de Ingreso',
            'numero_registro': 'Número de Registro',
            'delegacion': 'Delegación',
            'territorio': 'Territorio',
        }
        widgets = {
            'nombre': forms.TextInput(attrs={'class': 'form-control', 'id': 'id_junta_nombre'}),
            'domicilio_legal': forms.TextInput(attrs={'class': 'form-control', 'id': 'id_junta_domicilio_legal'}),
            'socios_activos': forms.NumberInput(attrs={'class': 'form-control', 'id': 'id_junta_socios_activos'}),
            'fecha_constitucion': forms.DateTimeInput(attrs={'type': 'datetime-local', 'class': 'form-control', 'id': 'id_junta_fecha_constitucion'}),
            'numero_rpj': forms.NumberInput(attrs={'class': 'form-control', 'id': 'id_junta_numero_rpj'}),
            'fecha_ingreso': forms.DateTimeInput(attrs={'type': 'datetime-local', 'class': 'form-control', 'id': 'id_junta_fecha_ingreso'}),
            'numero_registro': forms.NumberInput(attrs={'class': 'form-control', 'id': 'id_junta_numero_registro'}),
            'delegacion': forms.Select(attrs={'class': 'form-select', 'id': 'id_junta_delegacion'}),
            'territorio': forms.Select(attrs={'class': 'form-select', 'id': 'id_junta_territorio'}),
        }

    def __init__(self, *args, delegaciones=None, **kwargs):
        super().__init__(*args, **kwargs)
        from AdminApp.models import Delegacion
        from FuncionarioApp.models import Territorio
        
        # Permitir la selección de CUALQUIER delegación activa existente
        todas_delegaciones = Delegacion.objects.filter(
            models.Q(estado=Delegacion.Estado.ACTIVA) | models.Q(estado__iexact='activo')
        ).order_by('nombre')
        
        self.fields['delegacion'].queryset = todas_delegaciones
        self.fields['delegacion'].empty_label = 'Seleccione una delegación'
        self.fields['delegacion'].label_from_instance = lambda obj: obj.nombre

        # Determinar la delegación seleccionada (por POST, inicial o instancia)
        delegation_id = (
            self.data.get('delegacion')
            or self.initial.get('delegacion')
            or (self.instance.delegacion_id if self.instance.pk else None)
        )

        # Filtrar territorios estrictamente pertenecientes a la delegación elegida
        if delegation_id:
            territories = Territorio.objects.filter(delegacion_id=delegation_id)
        else:
            territories = Territorio.objects.none()

        if self.instance.pk and self.instance.territorio_id:
            territories = territories | Territorio.objects.filter(pk=self.instance.territorio_id)

        self.fields['territorio'].queryset = territories.distinct().order_by('nombre')
        self.fields['territorio'].empty_label = 'Seleccione un territorio'
        self.fields['territorio'].label_from_instance = lambda obj: f"ID: {obj.pk} - {obj.nombre}"

    def clean_nombre(self):
        return self.cleaned_data['nombre'].strip()

    def clean_domicilio_legal(self):
        return self.cleaned_data['domicilio_legal'].strip()

    def clean(self):
        cleaned_data = super().clean()
        delegation = cleaned_data.get('delegacion')
        territory = cleaned_data.get('territorio')
        if territory and delegation and territory.delegacion_id != delegation.pk:
            self.add_error('territorio', 'El territorio seleccionado debe pertenecer a la delegación elegida.')
        return cleaned_data


class AtencionSocialForm(TipoSubtipoFields, BootstrapFormMixin, forms.Form):
    tipo = forms.ModelChoiceField(
        queryset=Tipo.objects.none(),
        required=True,
        label='Tipo',
        empty_label='Seleccionar tipo',
        widget=forms.Select(attrs={'class': 'form-select', 'id': 'id_tipo'}),
    )
    subtipo = forms.ModelChoiceField(
        queryset=Subtipo.objects.none(),
        required=True,
        label='Subtipo',
        empty_label='Seleccionar subtipo',
        widget=forms.Select(attrs={'class': 'form-select', 'id': 'id_subtipo'}),
    )
    beneficiado = forms.ModelChoiceField(
        queryset=Beneficiado.objects.none(),
        required=False,
        label='Beneficiado existente',
        empty_label='Seleccionar beneficiado existente',
        widget=forms.Select(attrs={'class': 'form-select', 'id': 'id_beneficiado'}),
    )
    gestion_atencion = forms.ModelChoiceField(
        queryset=GestionAtencion.objects.all().order_by('-fecha'),
        required=True,
        label='Gestión social',
        empty_label='Seleccionar gestión social',
        widget=forms.Select(attrs={'class': 'form-select', 'id': 'id_gestion_atencion'}),
    )
    nombre = forms.CharField(
        max_length=50,
        required=False,
        label='Nombre',
        widget=forms.TextInput(attrs={'class': 'form-control', 'id': 'id_nombre'}),
    )
    apellido = forms.CharField(
        max_length=50,
        required=False,
        label='Apellido',
        widget=forms.TextInput(attrs={'class': 'form-control', 'id': 'id_apellido'}),
    )
    telefono = forms.IntegerField(
        required=False,
        label='Teléfono',
        widget=forms.NumberInput(attrs={'class': 'form-control', 'id': 'id_telefono'}),
    )
    email = forms.EmailField(
        max_length=90,
        required=False,
        label='Correo electrónico',
        widget=forms.EmailInput(attrs={'class': 'form-control', 'id': 'id_email'}),
    )
    fecha = forms.DateTimeField(
        label='Fecha de atención',
        widget=forms.DateTimeInput(attrs={'class': 'form-control', 'type': 'datetime-local'}),
    )
    resultado = forms.CharField(
        required=False,
        label='Resultado',
        widget=forms.Textarea(attrs={'class': 'form-control', 'rows': 3}),
    )
    observaciones = forms.CharField(
        required=False,
        label='Observaciones',
        widget=forms.Textarea(attrs={'class': 'form-control', 'rows': 2}),
    )
    evidencia = forms.FileField(
        required=False,
        label='Evidencia de la atención (Opcional)',
        widget=forms.ClearableFileInput(attrs={
            'class': 'form-control',
            'accept': 'image/jpeg,image/png,application/pdf',
        }),
    )

    def __init__(self, *args, instance=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.instance = instance

        # 1. Poblar los beneficiados existentes ordenados por nombre y apellido
        self.fields['beneficiado'].queryset = Beneficiado.objects.all().order_by('nombre', 'apellido')

        # 2. Poblar tipos activos
        self.fields['tipo'].queryset = _active_catalog_queryset(Tipo).order_by('nombre')

        tipo_id = None
        if self.data and 'tipo' in self.data:
            try:
                tipo_id = int(self.data.get('tipo'))
            except (ValueError, TypeError):
                pass
        elif instance and instance.tipo_id:
            tipo_id = instance.tipo_id

        if tipo_id:
            self.fields['subtipo'].queryset = _active_catalog_queryset(Subtipo).filter(
                tipo_id=tipo_id
            ).order_by('nombre')
        else:
            self.fields['subtipo'].queryset = Subtipo.objects.none()

    def clean(self):
        cleaned_data = super().clean()
        beneficiado = cleaned_data.get('beneficiado')
        
        # Si NO hay un beneficiado seleccionado, exigir la creación manual
        if not beneficiado:
            if not cleaned_data.get('nombre'):
                self.add_error('nombre', 'Debes ingresar el nombre o seleccionar un beneficiado existente.')
            if not cleaned_data.get('apellido'):
                self.add_error('apellido', 'Debes ingresar el apellido o seleccionar un beneficiado existente.')
            if not cleaned_data.get('telefono'):
                self.add_error('telefono', 'Debes ingresar el teléfono o seleccionar un beneficiado existente.')
        return cleaned_data

    def clean_evidencia(self):
        uploaded_file = self.cleaned_data.get('evidencia')
        return validate_evidence_file(uploaded_file) if uploaded_file else None

    def save(self, *, autor, instance=None):
        instance = instance or self.instance
        beneficiado = self.cleaned_data.get('beneficiado')
        
        if beneficiado is None:
            beneficiado = Beneficiado.objects.create(
                nombre=self.cleaned_data['nombre'].strip(),
                apellido=self.cleaned_data['apellido'].strip(),
                telefono=self.cleaned_data['telefono'],
                email=self.cleaned_data.get('email') or None,
            )

        tipo = self.cleaned_data['tipo']
        subtipo = self.cleaned_data['subtipo']
        gestion = self.cleaned_data['gestion_atencion']

        if instance is None:
            atencion = AtencionSocial.objects.create(
                fecha=self.cleaned_data['fecha'],
                resultado=self.cleaned_data['resultado'],
                observaciones=self.cleaned_data['observaciones'],
                autor=autor,
                beneficiado=beneficiado,
                tipo=tipo,
                subtipo=subtipo,
                gestion_atencion=gestion,
            )
        else:
            atencion = instance
            atencion.fecha = self.cleaned_data['fecha']
            atencion.resultado = self.cleaned_data['resultado']
            atencion.observaciones = self.cleaned_data['observaciones']
            atencion.autor = autor
            atencion.beneficiado = beneficiado
            atencion.tipo = tipo
            atencion.subtipo = subtipo
            atencion.gestion_atencion = gestion
            atencion.save(update_fields=[
                'fecha',
                'resultado',
                'observaciones',
                'autor',
                'beneficiado',
                'tipo',
                'subtipo',
                'gestion_atencion',
            ])
        return gestion, atencion

class CompromisoEvidenciaForm(BootstrapFormMixin, forms.Form):
    evidencia = forms.FileField(
        label='Archivo de evidencia',
        widget=forms.ClearableFileInput(attrs={
            'accept': 'image/jpeg,image/png,application/pdf',
        }),
    )

    def clean_evidencia(self):
        return validate_evidence_file(self.cleaned_data['evidencia'])


class GestionAtencionForm(BootstrapFormMixin, forms.ModelForm):
    class Meta:
        model = GestionAtencion
        fields = ('fecha', 'observaciones')
        labels = {
            'fecha': 'Fecha de la gestión',
            'observaciones': 'Observaciones',
        }
        widgets = {
            'fecha': forms.DateInput(attrs={'type': 'date', 'class': 'form-control', 'id': 'id_gestion_fecha'}),
            'observaciones': forms.Textarea(attrs={'rows': 3, 'class': 'form-control', 'id': 'id_gestion_observaciones'}),
        }

    def clean_fecha(self):
        fecha = self.cleaned_data.get('fecha')
        if not fecha:
            raise forms.ValidationError('La fecha de la gestión es obligatoria.')
        return fecha