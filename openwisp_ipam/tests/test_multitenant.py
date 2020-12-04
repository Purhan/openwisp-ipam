from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase
from django.urls import reverse
from openwisp_users.tests.utils import TestMultitenantAdminMixin
from swapper import load_model

from . import CreateModelsMixin, PostDataMixin

User = get_user_model()
IpAddress = load_model('openwisp_ipam', 'IPAddress')
Subnet = load_model('openwisp_ipam', 'Subnet')
OrganizationUser = load_model('openwisp_users', 'OrganizationUser')


class TestMultitenantAdmin(TestMultitenantAdminMixin, CreateModelsMixin, TestCase):
    app_label = 'openwisp_ipam'

    def _create_multitenancy_test_env(self):
        org1 = self._create_org(name="test1organization")
        org2 = self._create_org(name="test2organization")
        subnet1 = self._create_subnet(subnet='172.16.0.1/16', organization=org1)
        subnet2 = self._create_subnet(subnet='192.168.0.1/16', organization=org2)
        ipadd1 = self._create_ipaddress(ip_address='172.16.0.1', subnet=subnet1)
        ipadd2 = self._create_ipaddress(ip_address='192.168.0.1', subnet=subnet2)
        operator = self._create_operator(organizations=[org1])
        data = dict(
            org1=org1,
            org2=org2,
            subnet1=subnet1,
            subnet2=subnet2,
            ipadd1=ipadd1,
            ipadd2=ipadd2,
            operator=operator,
        )
        return data

    def test_multitenancy_ip_queryset(self):
        data = self._create_multitenancy_test_env()
        self._test_multitenant_admin(
            url=reverse(f'admin:{self.app_label}_ipaddress_changelist'),
            visible=[data['ipadd1']],
            hidden=[data['ipadd2']],
        )

    def test_multitenancy_subnet_queryset(self):
        data = self._create_multitenancy_test_env()
        self._test_multitenant_admin(
            url=reverse(f'admin:{self.app_label}_subnet_changelist'),
            visible=[data['subnet1']],
            hidden=[data['subnet2']],
        )


class TestMultitenantApi(
    TestMultitenantAdminMixin, CreateModelsMixin, PostDataMixin, TestCase
):
    def setUp(self):
        super().setUp()
        # Creates a user for each of org_a and org_b
        org_a = self._create_org(name='org_a', slug='org_a')
        org_b = self._create_org(name='org_b', slug='org_b')
        user_a = self._create_operator(
            username='user_a',
            email='usera@tester.com',
            password='tester',
            is_staff=True,
        )
        ou = OrganizationUser.objects.create(user=user_a, organization=org_a)
        ou.is_admin = True
        ou.save()
        user_b = self._create_operator(
            username='user_b',
            email='userb@tester.com',
            password='tester',
            is_staff=True,
        )
        ou = OrganizationUser.objects.create(user=user_b, organization=org_b)
        ou.is_admin = True
        ou.save()
        # Creates a superuser
        self._create_operator(
            username='superuser',
            email='superuser@tester.com',
            password='tester',
            is_superuser=True,
        )

    def test_subnet(self):
        org_a = self._get_org(org_name='org_a')
        self._login(username='user_a', password='tester')

        # Subnet to be accessible by superusers and org_a users
        subnet = self._create_subnet(subnet='10.0.0.0/24', organization=org_a)
        response = self.client.get(reverse('ipam:subnet', args=(subnet.id,)))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data['id'], str(subnet.id))
        self._login(username='superuser', password='tester')
        response = self.client.get(reverse('ipam:subnet', args=(subnet.id,)))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data['id'], str(subnet.id))

        # Should throw PermissionError for users from other organizations
        self._login(username='user_b', password='tester')
        response = self.client.get(reverse('ipam:subnet', args=(subnet.id,)))
        self.assertEqual(response.status_code, 403)

    def test_subnet_hosts(self):
        org_a = self._get_org(org_name='org_a')
        subnet = self._create_subnet(subnet='10.0.0.0/24', organization=org_a)
        self._login(username='user_a', password='tester')
        response = self.client.get(reverse('ipam:hosts', args=(subnet.id,)))
        self.assertEqual(response.status_code, 200)
        self._login(username='superuser', password='tester')
        response = self.client.get(reverse('ipam:hosts', args=(subnet.id,)))
        self.assertEqual(response.status_code, 200)
        self._login(username='user_b', password='tester')
        response = self.client.get(reverse('ipam:hosts', args=(subnet.id,)))
        self.assertEqual(response.status_code, 403)

    def test_subnet_list_ipaddress(self):
        org_a = self._get_org(org_name='org_a')
        subnet = self._create_subnet(subnet='10.0.0.0/24', organization=org_a)
        self._login(username='superuser', password='tester')
        post_data = self._post_data(ip_address='10.0.0.5', subnet=str(subnet.id))
        response = self.client.post(
            reverse('ipam:list_create_ip_address', args=(subnet.id,)),
            data=post_data,
            content_type='application/json',
        )
        self.assertEqual(response.status_code, 201)
        response = self.client.get(
            reverse('ipam:list_create_ip_address', args=(subnet.id,))
        )
        self.assertEqual(response.status_code, 200)
        self._login(username='user_a', password='tester')
        response = self.client.get(
            reverse('ipam:list_create_ip_address', args=(subnet.id,))
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data['results'][0]['ip_address'], '10.0.0.5')
        self._login(username='user_b', password='tester')
        response = self.client.get(
            reverse('ipam:list_create_ip_address', args=(subnet.id,))
        )
        self.assertEqual(response.status_code, 403)

    def test_ipaddress(self):
        org_a = self._get_org(org_name='org_a')
        subnet = self._create_subnet(subnet='10.0.0.0/24', organization=org_a)
        ip_address = self._create_ipaddress(ip_address='10.0.0.5', subnet=subnet)
        self._login(username='superuser', password='tester')
        response = self.client.get(reverse('ipam:ip_address', args=(ip_address.id,)))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data['ip_address'], '10.0.0.5')
        self._login(username='user_a', password='tester')
        response = self.client.get(reverse('ipam:ip_address', args=(ip_address.id,)))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data['ip_address'], '10.0.0.5')
        self._login(username='user_b', password='tester')
        response = self.client.get(reverse('ipam:ip_address', args=(ip_address.id,)))
        self.assertEqual(response.status_code, 403)

    def test_next_available_ip(self):
        org_a = self._get_org(org_name='org_a')
        subnet = self._create_subnet(subnet='10.0.0.0/24', organization=org_a)
        self._create_ipaddress(ip_address='10.0.0.1', subnet=subnet)
        self._login(username='user_a', password='tester')
        response = self.client.get(
            reverse('ipam:get_next_available_ip', args=(subnet.id,))
        )
        self.assertEqual(response.status_code, 200)
        self._login(username='superuser', password='tester')
        response = self.client.get(
            reverse('ipam:get_next_available_ip', args=(subnet.id,))
        )
        self.assertEqual(response.status_code, 200)
        self._login(username='user_b', password='tester')
        response = self.client.get(
            reverse('ipam:get_next_available_ip', args=(subnet.id,))
        )
        self.assertEqual(response.status_code, 403)

    def test_subnet_list(self):
        org_a = self._get_org(org_name='org_a')
        org_b = self._get_org(org_name='org_b')
        subnet1 = self._create_subnet(subnet='10.0.0.0/24', organization=org_a)
        subnet2 = self._create_subnet(subnet='10.10.0.0/24', organization=org_b)
        self._login(username='user_a', password='tester')
        response = self.client.get(reverse('ipam:subnet_list_create'),)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data['count'], 1)
        self.assertEqual(response.data['results'][0]['id'], str(subnet1.id))
        self._login(username='superuser', password='tester')
        response = self.client.get(reverse('ipam:subnet_list_create'),)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data['count'], 2)
        self._login(username='user_b', password='tester')
        response = self.client.get(reverse('ipam:subnet_list_create'),)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data['count'], 1)
        self.assertEqual(response.data['results'][0]['id'], str(subnet2.id))

    def test_request_ip(self):
        org_a = self._get_org(org_name='org_a')
        subnet = self._create_subnet(subnet='10.0.0.0/24', organization=org_a)
        self._create_ipaddress(ip_address='10.0.0.1', subnet=subnet)
        post_data = self._post_data(subnet=str(subnet.id), description='Testing')
        self._login(username='user_a', password='tester')
        response = self.client.post(
            reverse('ipam:request_ip', args=(subnet.id,)),
            data=post_data,
            content_type='application/json',
        )
        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.data['ip_address'], '10.0.0.2')
        self._login(username='user_b', password='tester')
        response = self.client.post(
            reverse('ipam:request_ip', args=(subnet.id,)),
            data=post_data,
            content_type='application/json',
        )
        self.assertEqual(response.status_code, 403)

    def test_import_subnet(self):
        csv_data = """Monachers - Matera,
        10.27.1.0/24,
        Monachers,
        org_a,
        ip address,description
        10.27.1.1,Monachers
        10.27.1.254,Nano Beam 5 19AC"""
        csvfile = SimpleUploadedFile('data.csv', bytes(csv_data, 'utf-8'))
        self._login(username='user_a', password='tester')
        response = self.client.post(reverse('ipam:import-subnet'), {'csvfile': csvfile})
        self.assertEqual(response.status_code, 200)
        self._login(username='user_b', password='tester')
        csvfile = SimpleUploadedFile('data.csv', bytes(csv_data, 'utf-8'))
        response = self.client.post(reverse('ipam:import-subnet'), {'csvfile': csvfile})
        self.assertEqual(response.status_code, 403)
        self._login(username='superuser', password='tester')
        csvfile = SimpleUploadedFile('data.csv', bytes(csv_data, 'utf-8'))
        response = self.client.post(reverse('ipam:import-subnet'), {'csvfile': csvfile})
        self.assertEqual(response.status_code, 200)

    def test_export_subnet_api(self):
        org_a = self._get_org(org_name='org_a')
        subnet = self._create_subnet(
            subnet='10.0.0.0/24', name='Sample Subnet', organization=org_a
        )
        self._create_ipaddress(
            ip_address='10.0.0.1', subnet=subnet, description='Testing'
        )
        self._create_ipaddress(
            ip_address='10.0.0.2', subnet=subnet, description='Testing'
        )
        csv_data = """Sample Subnet\r
        10.0.0.0/24\r
        \r
        ip_address,description\r
        10.0.0.1,Testing\r
        10.0.0.2,Testing\r
        """
        csv_data = bytes(csv_data.replace('        ', ''), 'utf-8')
        self._login(username='user_a', password='tester')
        response = self.client.post(reverse('ipam:export-subnet', args=(subnet.id,)))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.content, csv_data)
        self._login(username='user_b', password='tester')
        response = self.client.post(reverse('ipam:export-subnet', args=(subnet.id,)))
        self.assertEqual(response.status_code, 403)
