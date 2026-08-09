from rest_framework import status
from rest_framework.test import APITestCase

from users.models import Branch


class AboutUsApiTests(APITestCase):
    def test_about_us_returns_branch_locations_without_authentication(self):
        Branch.objects.create(
            name='Raduga',
            short_name='RG',
            address='Raduga address',
            latitude='41.311081',
            longitude='69.240562',
        )

        response = self.client.get('/api/v1/about-us/')

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data['branches']), 1)
        branch = response.data['branches'][0]
        self.assertEqual(branch['name'], 'Raduga')
        self.assertEqual(branch['short_name'], 'RG')
        self.assertEqual(branch['location'], 'Raduga address')
        self.assertEqual(branch['latitude'], '41.311081')
        self.assertEqual(branch['longitude'], '69.240562')
        self.assertEqual(branch['lat'], '41.311081')
        self.assertEqual(branch['lng'], '69.240562')
