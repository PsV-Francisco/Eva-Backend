from django.test import SimpleTestCase
from django.urls import reverse


class GuiaCiudadanaTests(SimpleTestCase):
    def test_guia_ciudadana_muestra_servicios_desde_json(self):
        response = self.client.get(reverse('guia_ciudadana'))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Puntos limpios')
        self.assertContains(response, 'Emergencias')
