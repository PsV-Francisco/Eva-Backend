from django import forms
from django.utils import timezone

from AdminApp.models import Delegacion
from CoordinadorApp.models import AtencionSocial, GestionAtencion, Item, Periodo
from DelegadoApp.models import Compromiso
from FuncionarioApp.models import (
    Beneficiado,
    CargoJv,
    JuntaVecino,
    Registro,
    Subtipo,
    Territorio,
    Tipo,
    Vecino,
    tipo_subtipo_predeterminados,
)
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
    tipos = Tipo.objects.filter(estado=Tipo.Estado.ACTIVADO)
    if instance and instance.pk and instance.tipo_id:
        tipos = (tipos | Tipo.objects.filter(pk=instance.tipo_id)).distinct()
    form.fields['tipo'].queryset = tipos.order_by('nombre')

    selected_type_id = (
        form.data.get('tipo')
        or form.initial.get('tipo')
        or (instance.tipo_id if instance and instance.pk else None)
    )
    subtipos = Subtipo.objects.filter(estado=Subtipo.Estado.ACTIVADO)
    if selected_type_id:
        subtipos = subtipos.filter(tipo_id=selected_type_id)
    if instance and instance.pk and instance.subtipo_id:
        subtipos = subtipos | Subtipo.objects.filter(pk=instance.subtipo_id)
    form.fields['subtipo'].queryset = subtipos.distinct().order_by('nombre')


class TipoSubtipoFields:
    def clean(self):
        cleaned_data = super().clean()
        tipo = cleaned_data.get('tipo')
        subtipo = cleaned_data.get('subtipo')
        if tipo and subtipo and subtipo.tipo_id != tipo.pk:
            self.add_error('subtipo', 'El subtipo debe pertenecer al tipo seleccionado.')
        return cleaned_data


class FuncionarioCompromisoForm(TipoSubtipoFields, BootstrapFormMixin, forms.ModelForm):
    tipo = forms.ModelChoiceField(
        queryset=Tipo.objects.none(),
        required=False,
        label='Tipo',
        empty_label='Sin tipo (predeterminado)',
    )
    subtipo = forms.ModelChoiceField(
        queryset=Subtipo.objects.none(),
        required=False,
        label='Subtipo',
        empty_label='Sin subtipo (predeterminado)',
    )
    periodo = forms.ModelChoiceField(
        queryset=Periodo.objects.filter(estado=Periodo.Estado.ABIERTO),
        label='Período de agenda',
    )

    class Meta:
        model = Compromiso
        fields = (
            'periodo', 'descripcion', 'solicitante', 'territorio', 'fecha',
            'observaciones',
        )
        labels = {
            'descripcion': 'Compromiso',
            'solicitante': 'Solicitante',
            'territorio': 'Territorio',
            'fecha': 'Fecha comprometida',
            'observaciones': 'Observaciones',
        }
        widgets = {
            'fecha': forms.DateTimeInput(attrs={'type': 'datetime-local'}),
            'observaciones': forms.Textarea(attrs={'rows': 2}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['periodo'].queryset = Periodo.objects.filter(
            estado=Periodo.Estado.ABIERTO,
        )
        _set_tipo_subtipo_choices(self, self.instance)
        if self.instance.pk:
            self.initial['periodo'] = self.instance.agenda.periodo_id
            self.fields['periodo'].disabled = True

    def save(self, commit=True):
        instance = super().save(commit=False)
        _assign_tipo_subtipo(self, instance)
        if commit:
            instance.save()
            self.save_m2m()
        return instance


class RegistroForm(TipoSubtipoFields, BootstrapFormMixin, forms.ModelForm):
    tipo = forms.ModelChoiceField(
        queryset=Tipo.objects.none(),
        required=False,
        label='Tipo',
        empty_label='Sin tipo (predeterminado)',
    )
    subtipo = forms.ModelChoiceField(
        queryset=Subtipo.objects.none(),
        required=False,
        label='Subtipo',
        empty_label='Sin subtipo (predeterminado)',
    )
    evidencia = forms.FileField(
        label='Archivo de evidencia',
        required=False,
        widget=forms.ClearableFileInput(attrs={
            'accept': 'image/jpeg,image/png,application/pdf',
        }),
    )

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
    class Meta:
        model = Vecino
        fields = (
            'nombre', 'telefono', 'direccion', 'delegacion', 'territorio',
            'junta_vecino', 'cargo_jv', 'solicitante', 'activo',
        )
        labels = {
            'nombre': 'Nombre',
            'telefono': 'Teléfono',
            'direccion': 'Dirección',
            'delegacion': 'Delegación',
            'territorio': 'Territorio',
            'junta_vecino': 'Junta de vecinos',
            'cargo_jv': 'Cargo en la junta',
            'solicitante': 'Beneficiado relacionado',
            'activo': 'Activo',
        }
        widgets = {
            'telefono': forms.TextInput(attrs={'autocomplete': 'tel'}),
            'direccion': forms.TextInput(attrs={'autocomplete': 'street-address'}),
        }

    def __init__(self, *args, delegaciones=None, **kwargs):
        super().__init__(*args, **kwargs)
        if delegaciones is None:
            delegaciones = Delegacion.objects.none()
        self.fields['delegacion'].queryset = delegaciones
        delegation_id = (
            self.data.get('delegacion')
            or self.initial.get('delegacion')
            or (self.instance.delegacion_id if self.instance.pk else None)
        )
        territories = Territorio.objects.filter(delegacion_id=delegation_id)
        juntas = JuntaVecino.objects.filter(delegacion_id=delegation_id)
        if self.instance.pk:
            territories = territories | Territorio.objects.filter(
                pk=self.instance.territorio_id,
            )
            juntas = juntas | JuntaVecino.objects.filter(
                pk=self.instance.junta_vecino_id,
            )
        self.fields['territorio'].queryset = territories.distinct().order_by('nombre')
        self.fields['junta_vecino'].queryset = juntas.distinct().order_by('nombre')

        junta_id = (
            self.data.get('junta_vecino')
            or self.initial.get('junta_vecino')
            or (self.instance.junta_vecino_id if self.instance.pk else None)
        )
        cargos = CargoJv.objects.filter(junta_vecino_id=junta_id)
        if self.instance.pk:
            cargos = cargos | CargoJv.objects.filter(pk=self.instance.cargo_jv_id)
        self.fields['cargo_jv'].queryset = cargos.distinct().order_by('nombre')
        self.fields['solicitante'].queryset = Beneficiado.objects.order_by(
            'nombre', 'apellido',
        )

    def clean(self):
        cleaned_data = super().clean()
        delegation = cleaned_data.get('delegacion')
        territory = cleaned_data.get('territorio')
        junta = cleaned_data.get('junta_vecino')
        cargo = cleaned_data.get('cargo_jv')
        if territory and delegation and territory.delegacion_id != delegation.pk:
            self.add_error('territorio', 'El territorio debe pertenecer a la delegación seleccionada.')
        if junta and delegation and junta.delegacion_id != delegation.pk:
            self.add_error('junta_vecino', 'La junta debe pertenecer a la delegación seleccionada.')
        if junta and territory and junta.territorio_id != territory.pk:
            self.add_error('junta_vecino', 'La junta debe pertenecer al territorio seleccionado.')
        if cargo and junta and cargo.junta_vecino_id != junta.pk:
            self.add_error('cargo_jv', 'El cargo debe pertenecer a la junta seleccionada.')
        return cleaned_data

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
            'domicilio_legal': 'Domicilio legal',
            'socios_activos': 'Socios activos',
            'fecha_constitucion': 'Fecha de constitución',
            'numero_rpj': 'Número de personalidad jurídica',
            'fecha_ingreso': 'Fecha de ingreso',
            'numero_registro': 'Número de registro',
            'delegacion': 'Delegación',
            'territorio': 'Territorio',
        }
        widgets = {
            'fecha_constitucion': forms.DateTimeInput(attrs={'type': 'datetime-local'}),
            'fecha_ingreso': forms.DateTimeInput(attrs={'type': 'datetime-local'}),
        }

    def __init__(self, *args, delegaciones=None, **kwargs):
        super().__init__(*args, **kwargs)
        if delegaciones is None:
            delegaciones = Delegacion.objects.none()
        self.fields['delegacion'].queryset = delegaciones
        delegation_id = (
            self.data.get('delegacion')
            or self.initial.get('delegacion')
            or (self.instance.delegacion_id if self.instance.pk else None)
        )
        territories = Territorio.objects.filter(delegacion_id=delegation_id)
        if self.instance.pk:
            territories = territories | Territorio.objects.filter(
                pk=self.instance.territorio_id,
            )
        self.fields['territorio'].queryset = territories.distinct().order_by('nombre')

    def clean_nombre(self):
        return self.cleaned_data['nombre'].strip()

    def clean_domicilio_legal(self):
        return self.cleaned_data['domicilio_legal'].strip()

    def clean(self):
        cleaned_data = super().clean()
        delegation = cleaned_data.get('delegacion')
        territory = cleaned_data.get('territorio')
        if territory and delegation and territory.delegacion_id != delegation.pk:
            self.add_error('territorio', 'El territorio debe pertenecer a la delegación seleccionada.')
        return cleaned_data


class AtencionSocialForm(TipoSubtipoFields, BootstrapFormMixin, forms.Form):
    tipo = forms.ModelChoiceField(
        queryset=Tipo.objects.none(),
        required=False,
        label='Tipo',
        empty_label='Sin tipo (predeterminado)',
    )
    subtipo = forms.ModelChoiceField(
        queryset=Subtipo.objects.none(),
        required=False,
        label='Subtipo',
        empty_label='Sin subtipo (predeterminado)',
    )
    beneficiado = forms.ModelChoiceField(
        queryset=Beneficiado.objects.none(),
        required=False,
        label='Beneficiado existente',
    )
    nombre = forms.CharField(max_length=50, required=False, label='Nombre')
    apellido = forms.CharField(max_length=50, required=False, label='Apellido')
    telefono = forms.IntegerField(required=False, label='Teléfono')
    email = forms.EmailField(max_length=90, required=False, label='Correo electrónico')
    fecha = forms.DateTimeField(
        label='Fecha de atención',
        widget=forms.DateTimeInput(attrs={'type': 'datetime-local'}),
    )
    resultado = forms.CharField(
        required=False,
        label='Resultado',
        widget=forms.Textarea(attrs={'rows': 3}),
    )
    observaciones = forms.CharField(
        required=False,
        label='Observaciones',
        widget=forms.Textarea(attrs={'rows': 2}),
    )
    numero_gestion = forms.IntegerField(
        min_value=1,
        max_value=3,
        label='Número de atención',
    )
    fecha_gestion = forms.DateField(
        label='Fecha de gestión',
        widget=forms.DateInput(attrs={'type': 'date'}),
    )
    observaciones_gestion = forms.CharField(
        required=False,
        label='Detalle de la gestión',
        widget=forms.Textarea(attrs={'rows': 2}),
    )
    evidencia = forms.FileField(
        label='Evidencia de la atención',
        widget=forms.ClearableFileInput(attrs={
            'accept': 'image/jpeg,image/png,application/pdf',
        }),
    )

    def __init__(self, *args, instance=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.instance = instance
        self.fields['beneficiado'].queryset = Beneficiado.objects.order_by(
            'nombre', 'apellido',
        )
        if instance is not None:
            self.fields['beneficiado'].initial = instance.beneficiado_id
            self.fields['tipo'].initial = instance.tipo_id
            self.fields['subtipo'].initial = instance.subtipo_id
            self.fields['fecha'].initial = timezone.localtime(
                instance.fecha,
            ).strftime('%Y-%m-%dT%H:%M')
            self.fields['resultado'].initial = instance.resultado
            self.fields['observaciones'].initial = instance.observaciones
            self.fields['numero_gestion'].initial = (
                instance.gestion_atencion.numero_gestion
            )
            self.fields['fecha_gestion'].initial = (
                instance.gestion_atencion.fecha
            )
            self.fields['observaciones_gestion'].initial = (
                instance.gestion_atencion.observaciones
            )
            self.fields['evidencia'].required = False
        if instance is None:
            self.fields['fecha'].initial = timezone.localtime().strftime(
                '%Y-%m-%dT%H:%M',
            )
        _set_tipo_subtipo_choices(self)

    def clean(self):
        cleaned_data = super().clean()
        if not cleaned_data.get('beneficiado'):
            for field in ('nombre', 'apellido', 'telefono'):
                if not cleaned_data.get(field):
                    self.add_error(field, 'Ingresa estos datos o selecciona un beneficiado existente.')
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
        tipo = self.cleaned_data.get('tipo')
        subtipo = self.cleaned_data.get('subtipo')
        if tipo is None and subtipo is not None:
            tipo = subtipo.tipo
        if tipo is None or subtipo is None:
            default_tipo, default_subtipo = tipo_subtipo_predeterminados(tipo)
            tipo = tipo or default_tipo
            subtipo = subtipo or default_subtipo
        if instance is None:
            gestion = GestionAtencion.objects.create(
                numero_gestion=self.cleaned_data['numero_gestion'],
                fecha=self.cleaned_data['fecha_gestion'],
                observaciones=self.cleaned_data['observaciones_gestion'],
            )
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
            gestion = instance.gestion_atencion
            gestion.numero_gestion = self.cleaned_data['numero_gestion']
            gestion.fecha = self.cleaned_data['fecha_gestion']
            gestion.observaciones = self.cleaned_data['observaciones_gestion']
            gestion.save(update_fields=[
                'numero_gestion',
                'fecha',
                'observaciones',
            ])
            atencion = instance
            atencion.fecha = self.cleaned_data['fecha']
            atencion.resultado = self.cleaned_data['resultado']
            atencion.observaciones = self.cleaned_data['observaciones']
            atencion.autor = autor
            atencion.beneficiado = beneficiado
            atencion.tipo = tipo
            atencion.subtipo = subtipo
            atencion.save(update_fields=[
                'fecha',
                'resultado',
                'observaciones',
                'autor',
                'beneficiado',
                'tipo',
                'subtipo',
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
