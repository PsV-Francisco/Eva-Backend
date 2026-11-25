from django import forms
from django.core.exceptions import ValidationError
from django.db.models import Q
from django.utils import timezone
from django.db import models
import re
from AdminApp.models import Delegacion
from CoordinadorApp.models import AtencionSocial, GestionAtencion, Item, Periodo
from DelegadoApp.models import Compromiso
from FuncionarioApp.models import (
    CargoJv,
    JuntaVecino,
    Registro,
    Subtipo,
    Territorio,
    Tipo,
    Vecino,
    tipo_subtipo_predeterminados,
    validar_periodo_semanal_abierto,
)
from config.forms import BootstrapFormMixin
from SupervisorApp.files import validate_evidence_file
from FuncionarioApp.models import Carta
from django.contrib.auth import get_user_model


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
    solicitante = forms.ModelChoiceField(
        queryset=Vecino.objects.filter(activo=True).order_by('nombre', 'apellido'),
        required=False,
        label='Solicitante (Vecino)',
        empty_label='Seleccione un vecino',
        widget=forms.Select(attrs={'class': 'form-select'}),
    )
    territorio = forms.ModelChoiceField(
        queryset=Territorio.objects.all().order_by('nombre'),
        required=False,
        label='Territorio',
        empty_label='Seleccione un territorio',
        widget=forms.Select(attrs={'class': 'form-select'}),
    )
    tipo = forms.ModelChoiceField(
        queryset=Tipo.objects.filter(estado=Tipo.Estado.ACTIVADO).order_by('nombre'),
        required=False,
        label='Tipo',
        empty_label='Seleccione un tipo',
        widget=forms.Select(attrs={'class': 'form-select', 'id': 'id_tipo'}),
    )
    subtipo = forms.ModelChoiceField(
        queryset=Subtipo.objects.none(),
        required=False,
        label='Subtipo',
        empty_label='Seleccione un subtipo',
        widget=forms.Select(attrs={'class': 'form-select', 'id': 'id_subtipo'}),
    )
    periodo = forms.ModelChoiceField(
        queryset=Periodo.objects.filter(estado=Periodo.Estado.ABIERTO),
        label='Período de agenda',
        widget=forms.Select(attrs={'class': 'form-select'}),
    )

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

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        _set_tipo_subtipo_choices(self, self.instance)
        self.fields['mes'].required = False

    def clean(self):
        cleaned_data = super().clean()
        fecha_sol = cleaned_data.get('fecha_solicitud')
        fecha_comp = cleaned_data.get('fecha_compromiso')
        mes = cleaned_data.get('mes')

        if fecha_sol and fecha_comp and fecha_comp < fecha_sol:
            self.add_error(
                'fecha_compromiso',
                'La fecha de compromiso no puede ser anterior a la fecha de ingreso/solicitud.'
            )

        if fecha_comp and not mes:
            cleaned_data['mes'] = fecha_comp.month
            self.cleaned_data['mes'] = fecha_comp.month
        return cleaned_data


class RegistroForm(TipoSubtipoFields, BootstrapFormMixin, forms.ModelForm):
    vecino = forms.ModelChoiceField(queryset=Vecino.objects.filter(activo=True).order_by('nombre', 'apellido'),required=False,label='Vecino Registrado (Autocompletar)',empty_label='Seleccione un vecino (opcional)',widget=forms.Select(attrs={'class': 'form-select', 'id': 'id_vecino_actividad'}),)
    tipo = forms.ModelChoiceField(queryset=Tipo.objects.none(),required=False,label='Tipo',empty_label='Sin tipo (predeterminado)',)
    subtipo = forms.ModelChoiceField(queryset=Subtipo.objects.none(),required=False,label='Subtipo',empty_label='Sin subtipo (predeterminado)',)
    evidencia = forms.FileField(label='Archivo de evidencia',required=False,widget=forms.ClearableFileInput(attrs={'accept': 'image/jpeg,image/png,application/pdf','class': 'form-control',}),)

    class Meta:
        model = Registro
        fields = (
            'fecha', 'periodo', 'item', 'vecino','descripcion', 'accion', 'contacto',
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
            'vecino' : 'Vecino',
        }
        widgets = {
            'fecha': forms.DateInput(attrs={'type': 'date'}),
            'accion': forms.Textarea(attrs={'rows': 3}),
            'contacto': forms.TextInput(attrs={'autocomplete': 'name', 'readonly': 'readonly', 'class': 'form-control bg-light'}),
            'telefono': forms.TextInput(attrs={'readonly': 'readonly', 'class': 'form-control bg-light'}),
        }

    def __init__(self, *args, user=None, **kwargs):
        super().__init__(*args, **kwargs)
        # Tipos y Subtipos
        _set_tipo_subtipo_choices(self, self.instance)
        self.fields['mes'].required = False
        periods = Periodo.objects.filter(estado=Periodo.Estado.ABIERTO)
        #Periodos
        if self.instance.pk and self.instance.periodo_id:
            periods = (periods | Periodo.objects.filter(pk=self.instance.periodo_id)).distinct()
        self.fields['periodo'].queryset = periods
        #Items
        items = Item.objects.filter(estado=Item.Estado.ACTIVO)
        if self.instance.pk and self.instance.item_id:
            items = (items | Item.objects.filter(pk=self.instance.item_id)).distinct()
        self.fields['item'].queryset = items.order_by('nombre')
        #Vecinos
        self.fields['vecino'].label_from_instance = (
            lambda obj: f"{obj.nombre} {obj.apellido}".strip()
        )

    def clean_evidencia(self):
        uploaded_file = self.cleaned_data.get('evidencia')
        return validate_evidence_file(uploaded_file) if uploaded_file else uploaded_file

    def clean(self):
        cleaned_data = super().clean()
        fecha = cleaned_data.get('fecha')
        if fecha:
            try:
                validar_periodo_semanal_abierto(fecha)
            except ValidationError as error:
                self.add_error('fecha', error.message)
        return cleaned_data

    def save(self, commit=True):
        instance = super().save(commit=False)
        _assign_tipo_subtipo(self, instance)
        if commit:
            instance.save()
            self.save_m2m()
        return instance


class VecinoForm(BootstrapFormMixin, forms.ModelForm):
    rut = forms.CharField(
        max_length=12,
        required=True,
        label='RUT (Ej: 12345678-9 o 12.345.678-K)',
        widget=forms.TextInput(attrs={'class': 'form-control', 'id': 'id_rut', 'placeholder': '12345678-9'}),
    )
    territorio = forms.ModelChoiceField(
        queryset=Territorio.objects.none(),
        required=True,
        label='Territorio',
        widget=forms.Select(attrs={'class': 'form-select', 'id': 'id_territorio'}),
    )
    junta_vecino = forms.ModelChoiceField(
        queryset=JuntaVecino.objects.none(),
        required=True,
        label='Junta de Vecinos',
        widget=forms.Select(attrs={'class': 'form-select', 'id': 'id_junta_vecino'}),
    )
    es_dirigente = forms.BooleanField(
        required=False,
        label='¿Es dirigente en la Junta de Vecinos?',
        widget=forms.CheckboxInput(attrs={'class': 'form-check-input', 'id': 'id_es_dirigente'}),
    )
    cargo_jv = forms.ModelChoiceField(
        queryset=CargoJv.objects.none(),
        required=False,
        label='Cargo en la junta existente',
        widget=forms.Select(attrs={'class': 'form-select', 'id': 'id_cargo_jv'}),
    )
    estado = forms.ChoiceField(
        choices=Vecino.Estado.choices,
        initial=Vecino.Estado.ACTIVADO,
        widget=forms.Select(attrs={'class': 'form-select', 'id': 'id_estado'}),
        label='Estado',
    )

    class Meta:
        model = Vecino
        fields = (
            'rut', 'nombre', 'telefono', 'direccion',
            'delegacion', 'junta_vecino', 'territorio', 'estado',
        )
        labels = {
            'rut': 'RUT',
            'nombre': 'Nombre',
            'telefono': 'Teléfono',
            'direccion': 'Dirección',
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
        }

    def __init__(self, *args, delegaciones=None, **kwargs):
        super().__init__(*args, **kwargs)
        if delegaciones is None:
            delegaciones = Delegacion.objects.none()

        self.fields['delegacion'].queryset = delegaciones.order_by('nombre')

        delegation_id = (
            self.data.get('delegacion')
            or self.initial.get('delegacion')
            or (self.instance.delegacion_id if self.instance and self.instance.pk else None)
        )
        junta_id = (
            self.data.get('junta_vecino')
            or (self.instance.junta_vecino_id if self.instance and self.instance.pk else None)
        )

        juntas = JuntaVecino.objects.filter(delegacion_id=delegation_id) if delegation_id else JuntaVecino.objects.none()
        self.fields['junta_vecino'].queryset = juntas.distinct().order_by('nombre')
        self.fields['junta_vecino'].label_from_instance = lambda obj: f"RPJ {obj.numero_rpj} - {obj.nombre}"

        cargos = CargoJv.objects.filter(junta_vecino_id=junta_id) if junta_id else CargoJv.objects.none()
        self.fields['cargo_jv'].queryset = cargos.distinct().order_by('nombre')
        self.fields['cargo_jv'].label_from_instance = lambda obj: f"{obj.nombre} - {obj.permisos}"

        territories = Territorio.objects.filter(delegacion_id=delegation_id) if delegation_id else Territorio.objects.none()
        self.fields['territorio'].queryset = territories.distinct().order_by('nombre')
        self.fields['territorio'].label_from_instance = lambda obj: f"ID: {obj.pk} - {obj.nombre}"

    def clean_rut(self):
        rut_input = self.cleaned_data.get('rut', '').strip()
        rut_limpio = rut_input.replace('.', '').replace(' ', '').upper()
        if not re.match(r'^\d{7,8}-[\dK]$', rut_limpio):
            raise forms.ValidationError('Formato de RUT inválido. Use el formato: 12345678-9')
        cuerpo, dv = rut_limpio.split('-')
        suma = 0
        multiplo = 2
        for r in reversed(cuerpo):
            suma += int(r) * multiplo
            multiplo = 2 if multiplo == 7 else multiplo + 1
        esperado = 11 - (suma % 11)
        dv_calculado = 'K' if esperado == 10 else ('0' if esperado == 11 else str(esperado))
        if dv_calculado != dv:
            raise forms.ValidationError('El dígito verificador del RUT no es válido.')
        return rut_limpio

    def clean_nombre(self):
        return self.cleaned_data['nombre'].strip()

    def clean_telefono(self):
        telefono = self.cleaned_data.get('telefono')
        return telefono.strip() if telefono else telefono

    def clean(self):
        cleaned_data = super().clean()
        delegacion = cleaned_data.get('delegacion')
        junta_vecino = cleaned_data.get('junta_vecino')
        cargo_jv = cleaned_data.get('cargo_jv')
        es_dirigente = cleaned_data.get('es_dirigente')

        if junta_vecino and delegacion and junta_vecino.delegacion_id != delegacion.pk:
            self.add_error('junta_vecino', 'La junta de vecinos seleccionada no pertenece a la delegación elegida.')
        if es_dirigente and not cargo_jv:
            self.add_error('cargo_jv', 'Debes seleccionar un cargo si el vecino es dirigente.')
        if cargo_jv and junta_vecino and cargo_jv.junta_vecino_id != junta_vecino.pk:
            self.add_error('cargo_jv', 'El cargo seleccionado debe pertenecer a la junta de vecinos elegida.')
        return cleaned_data

    def save(self, commit=True):
        vecino = super().save(commit=False)
        vecino.activo = (vecino.estado == Vecino.Estado.ACTIVADO)
        if commit:
            vecino.save()
        return vecino


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
        todas_delegaciones = Delegacion.objects.filter(
            models.Q(estado=Delegacion.Estado.ACTIVADO) | models.Q(estado__iexact='activo')
        ).order_by('nombre')

        self.fields['delegacion'].queryset = todas_delegaciones
        self.fields['delegacion'].empty_label = 'Seleccione una delegación'
        self.fields['delegacion'].label_from_instance = lambda obj: obj.nombre

        delegation_id = (
            self.data.get('delegacion')
            or self.initial.get('delegacion')
            or (self.instance.delegacion_id if self.instance.pk else None)
        )

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
    gestion_atencion = forms.ModelChoiceField(
        queryset=GestionAtencion.objects.all().order_by('-fecha'),
        required=True,
        label='Gestión social (Caso)',
        empty_label='Seleccionar gestión social',
        widget=forms.Select(attrs={'class': 'form-select', 'id': 'id_gestion_atencion'}),
    )
    etapa = forms.TypedChoiceField(
        choices=AtencionSocial.Etapa.choices,
        coerce=int,
        required=True,
        label='Etapa de la gestión',
        widget=forms.Select(attrs={'class': 'form-select', 'id': 'id_etapa'}),
    )
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
    vecino = forms.ModelChoiceField(
        queryset=Vecino.objects.filter(activo=True).order_by('nombre'),
        required=False,
        label='Vecino existente',
        empty_label='Seleccionar vecino existente',
        widget=forms.Select(attrs={'class': 'form-select', 'id': 'id_vecino'}),
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
        self.fields['vecino'].queryset = Vecino.objects.filter(activo=True).order_by('nombre')

        tipos = _active_catalog_queryset(Tipo)
        if instance and instance.tipo_id:
            tipos = (tipos | Tipo.objects.filter(pk=instance.tipo_id)).distinct()
        self.fields['tipo'].queryset = tipos.order_by('nombre')

        tipo_id = None
        if self.data and 'tipo' in self.data:
            try:
                tipo_id = int(self.data.get('tipo'))
            except (ValueError, TypeError):
                pass
        elif instance and instance.tipo_id:
            tipo_id = instance.tipo_id

        subtipos = _active_catalog_queryset(Subtipo).filter(tipo_id=tipo_id) if tipo_id else Subtipo.objects.none()
        if instance and instance.subtipo_id and (not tipo_id or str(instance.tipo_id) == str(tipo_id)):
            subtipos = (subtipos | Subtipo.objects.filter(pk=instance.subtipo_id)).distinct()
        self.fields['subtipo'].queryset = subtipos.order_by('nombre')

    def clean(self):
        cleaned_data = super().clean()
        vecino = cleaned_data.get('vecino')
        gestion = cleaned_data.get('gestion_atencion')
        etapa = cleaned_data.get('etapa')

        if gestion and etapa:
            qs_gestion = AtencionSocial.objects.filter(gestion_atencion=gestion)
            if self.instance and self.instance.pk:
                qs_gestion = qs_gestion.exclude(pk=self.instance.pk)
            if qs_gestion.filter(etapa=etapa).exists():
                self.add_error('etapa', f'La etapa {etapa} ya se encuentra registrada en esta gestión social.')
            if not (self.instance and self.instance.pk) and qs_gestion.count() >= 3:
                self.add_error('gestion_atencion', 'Esta gestión social ya alcanzó el máximo permitido de 3 etapas.')

        if not vecino:
            if not cleaned_data.get('nombre'):
                self.add_error('nombre', 'Debes ingresar el nombre o seleccionar un vecino existente.')
            if not cleaned_data.get('telefono'):
                self.add_error('telefono', 'Debes ingresar el teléfono o seleccionar un vecino existente.')
        return cleaned_data

    def clean_evidencia(self):
        uploaded_file = self.cleaned_data.get('evidencia')
        return validate_evidence_file(uploaded_file) if uploaded_file else None

    def save(self, *, autor, instance=None):
        instance = instance or self.instance
        vecino = self.cleaned_data.get('vecino')

        if vecino is None:
            vecino, _ = Vecino.objects.get_or_create(
                nombre__iexact=self.cleaned_data['nombre'].strip(),
                telefono=self.cleaned_data.get('telefono'),
                defaults={
                    'nombre': self.cleaned_data['nombre'].strip(),
                    'apellido': self.cleaned_data.get('apellido', '').strip() or None,
                    'email': self.cleaned_data.get('email') or None,
                },
            )

        tipo = self.cleaned_data['tipo']
        subtipo = self.cleaned_data['subtipo']
        gestion = self.cleaned_data['gestion_atencion']
        etapa = self.cleaned_data['etapa']

        if instance is None:
            atencion = AtencionSocial.objects.create(
                etapa=etapa,
                fecha=self.cleaned_data['fecha'],
                resultado=self.cleaned_data['resultado'],
                observaciones=self.cleaned_data['observaciones'],
                autor=autor,
                vecino=vecino,
                tipo=tipo,
                subtipo=subtipo,
                gestion_atencion=gestion,
            )
        else:
            atencion = instance
            atencion.etapa = etapa
            atencion.fecha = self.cleaned_data['fecha']
            atencion.resultado = self.cleaned_data['resultado']
            atencion.observaciones = self.cleaned_data['observaciones']
            atencion.autor = autor
            atencion.vecino = vecino
            atencion.tipo = tipo
            atencion.subtipo = subtipo
            atencion.gestion_atencion = gestion
            atencion.save()
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
        fields = ('nombre', 'fecha', 'observaciones')
        labels = {
            'nombre': 'Nombre de la gestión',
            'fecha': 'Fecha de la gestión',
            'observaciones': 'Observaciones',
        }
        widgets = {
            'nombre': forms.TextInput(attrs={'class': 'form-control', 'id': 'id_gestion_nombre'}),
            'fecha': forms.DateInput(attrs={'type': 'date', 'class': 'form-control', 'id': 'id_gestion_fecha'}),
            'observaciones': forms.Textarea(attrs={'rows': 3, 'class': 'form-control', 'id': 'id_gestion_observaciones'}),
        }

    def clean_fecha(self):
        fecha = self.cleaned_data.get('fecha')
        if not fecha:
            raise forms.ValidationError('La fecha de la gestión es obligatoria.')
        return fecha


class CartaForm(forms.ModelForm):
    documento = forms.FileField(
        required=False,
        label='Documento adjunto',
        widget=forms.ClearableFileInput(attrs={'class': 'form-control'}),
    )

    class Meta:
        model = Carta
        fields = [
            'numero_carta',
            'fecha',
            'remitente',
            'destinatario',
            'telefono',
            'materia',
            'fecha_respuesta',
            'responsable_seguimiento',
            'area_derivada',
            'pronunciamiento',
            'observaciones',
            'fecha_cierre',
            'estado',
        ]
        widgets = {
            'numero_carta': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Ej: OF-2026-001'}),
            'fecha': forms.DateInput(attrs={'class': 'form-control', 'type': 'date'}),
            'remitente': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Nombre o institución remitente'}),
            'destinatario': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Destinatario formal'}),
            'telefono': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Ej: +56912345678'}),
            'materia': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Asunto principal de la carta'}),
            'fecha_respuesta': forms.DateInput(attrs={'class': 'form-control', 'type': 'date'}),
            'responsable_seguimiento': forms.Select(attrs={'class': 'form-select'}),
            'area_derivada': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Unidad o departamento derivado'}),
            'pronunciamiento': forms.Textarea(attrs={'class': 'form-control', 'rows': 2, 'placeholder': 'Pronunciamiento institucional...'}),
            'observaciones': forms.Textarea(attrs={'class': 'form-control', 'rows': 2, 'placeholder': 'Observaciones adicionales...'}),
            'fecha_cierre': forms.DateInput(attrs={'class': 'form-control', 'type': 'date'}),
            'estado': forms.Select(attrs={'class': 'form-select'}),
        }

    def __init__(self, *args, delegation=None, **kwargs):
        super().__init__(*args, **kwargs)
        UserModel = get_user_model()
        users_qs = UserModel.objects.filter(is_active=True).order_by('first_name', 'last_name', 'email')
        if delegation is not None:
            users_qs = users_qs.filter(
                usuariodelegacion__delegacion=delegation,
                usuariodelegacion__fecha_fin__isnull=True,
            ).distinct()
        self.fields['responsable_seguimiento'].queryset = users_qs
