"""CLI tests for ``hammer host``.

:Requirement: Host

:CaseAutomation: Automated

:CaseLevel: Acceptance

:CaseComponent: CLI

:TestType: Functional

:CaseImportance: High

:Upstream: No
"""
from random import choice

from fauxfactory import gen_mac, gen_string
from nailgun import entities
from robottelo import ssh
from robottelo.cleanup import vm_cleanup
from robottelo.cli.base import CLIReturnCodeError
from robottelo.cli.contentview import ContentView
from robottelo.cli.environment import Environment
from robottelo.cli.factory import (
    CLIFactoryError,
    make_activation_key,
    make_architecture,
    make_content_view,
    make_domain,
    make_environment,
    make_fake_host,
    make_hostgroup,
    make_lifecycle_environment,
    make_medium,
    make_org,
    make_os,
    make_smart_variable,
    publish_puppet_module,
    setup_org_for_a_custom_repo,
    setup_org_for_a_rh_repo,
)
from robottelo.cli.host import Host
from robottelo.cli.lifecycleenvironment import LifecycleEnvironment
from robottelo.cli.medium import Medium
from robottelo.cli.operatingsys import OperatingSys
from robottelo.cli.proxy import Proxy
from robottelo.cli.puppet import Puppet
from robottelo.cli.scparams import SmartClassParameter
from robottelo.config import settings
from robottelo.constants import (
    CUSTOM_PUPPET_REPO,
    DEFAULT_CV,
    DISTRO_RHEL7,
    ENVIRONMENT,
    FAKE_0_CUSTOM_PACKAGE,
    FAKE_0_CUSTOM_PACKAGE_GROUP,
    FAKE_0_CUSTOM_PACKAGE_GROUP_NAME,
    FAKE_0_CUSTOM_PACKAGE_NAME,
    FAKE_1_CUSTOM_PACKAGE,
    FAKE_1_CUSTOM_PACKAGE_NAME,
    FAKE_2_CUSTOM_PACKAGE,
    FAKE_0_ERRATA_ID,
    FAKE_0_YUM_REPO,
    PRDS,
    REPOS,
    REPOSET,
)
from robottelo.datafactory import (
    invalid_values_list,
    valid_data_list,
    valid_hosts_list,
)
from robottelo.decorators import (
    run_in_one_thread,
    run_only_on,
    skip_if_bug_open,
    skip_if_not_set,
    stubbed,
    tier1,
    tier2,
    tier3,
)
from robottelo.test import CLITestCase
from robottelo.vm import VirtualMachine


class HostCreateTestCase(CLITestCase):
    """Tests for creating the hosts via CLI."""

    @classmethod
    def setUpClass(cls):
        """Create organization, lifecycle environment, content view, publish
        and promote new version to re-use in tests.
        """
        super(HostCreateTestCase, cls).setUpClass()
        cls.new_org = make_org()
        cls.new_lce = make_lifecycle_environment({
            'organization-id': cls.new_org['id']})
        cls.LIBRARY = LifecycleEnvironment.info({
            'organization-id': cls.new_org['id'],
            'name': ENVIRONMENT,
        })
        cls.DEFAULT_CV = ContentView.info({
            'organization-id': cls.new_org['id'],
            'name': DEFAULT_CV,
        })
        cls.new_cv = make_content_view({'organization-id': cls.new_org['id']})
        ContentView.publish({'id': cls.new_cv['id']})
        version_id = ContentView.version_list({
            'content-view-id': cls.new_cv['id'],
        })[0]['id']
        ContentView.version_promote({
            'id': version_id,
            'to-lifecycle-environment-id': cls.new_lce['id'],
            'organization-id': cls.new_org['id'],
        })
        cls.promoted_cv = cls.new_cv
        # Setup for puppet class related tests
        puppet_modules = [
            {'author': 'robottelo', 'name': 'generic_1'},
        ]
        cls.puppet_cv = publish_puppet_module(
            puppet_modules, CUSTOM_PUPPET_REPO, cls.new_org['id'])
        cls.puppet_env = Environment.list({
            'search': u'content_view="{0}"'.format(cls.puppet_cv['name'])})[0]
        cls.puppet_class = Puppet.info({
            'name': puppet_modules[0]['name'],
            'environment': cls.puppet_env['name'],
        })

    def setUp(self):
        """Find an existing puppet proxy.

        Record information about this puppet proxy as ``self.puppet_proxy``.
        """
        super(HostCreateTestCase, self).setUp()
        # Use the default installation smart proxy
        self.puppet_proxy = Proxy.list({
            'search': 'url = https://{0}:9090'.format(settings.server.hostname)
        })[0]

    @tier1
    def test_positive_create_with_name(self):
        """A host can be created with a random name

        :id: 2e8dd25d-47ed-4131-bba6-1ff024808d05

        :expectedresults: A host is created and the name matches

        :CaseImportance: Critical
        """
        for name in valid_hosts_list():
            with self.subTest(name):
                host = entities.Host()
                host.create_missing()
                result = Host.create({
                    u'architecture-id': host.architecture.id,
                    u'domain-id': host.domain.id,
                    u'environment-id': host.environment.id,
                    # pylint:disable=no-member
                    u'location-id': host.location.id,
                    u'mac': host.mac,
                    u'medium-id': host.medium.id,
                    u'name': name,
                    u'operatingsystem-id': host.operatingsystem.id,
                    # pylint:disable=no-member
                    u'organization-id': host.organization.id,
                    u'partition-table-id': host.ptable.id,
                    u'puppet-proxy-id': self.puppet_proxy['id'],
                    u'root-pass': host.root_pass,
                })
                self.assertEqual(
                    '{0}.{1}'.format(name, host.domain.read().name),
                    result['name'],
                )

    @tier1
    def test_positive_create_with_org_name(self):
        """Check if host can be created with organization name

        :id: c08b0dac-9820-4261-bb0b-8a78f5c78a74

        :expectedresults: Host is created using organization name

        :CaseImportance: Critical
        """
        new_host = make_fake_host({
            'content-view-id': self.DEFAULT_CV['id'],
            'lifecycle-environment-id': self.LIBRARY['id'],
            'organization': self.new_org['name'],
        })
        self.assertEqual(new_host['organization'], self.new_org['name'])

    @run_only_on('sat')
    @tier1
    def test_positive_create_with_cv_default(self):
        """Check if host can be created with default content view ('Default
        Organization View')

        :id: bb69a70e-17f9-4639-802d-90e6a4520afa

        :expectedresults: Host is created, default content view is associated

        :CaseImportance: Critical
        """
        new_host = make_fake_host({
            'content-view-id': self.DEFAULT_CV['id'],
            'lifecycle-environment-id': self.LIBRARY['id'],
            'organization-id': self.new_org['id'],
        })
        self.assertEqual(
            new_host['content-information']['content-view'],
            self.DEFAULT_CV['name'],
        )

    @tier1
    @run_only_on('sat')
    def test_positive_create_with_lce_library(self):
        """Check if host can be created with default lifecycle environment
        ('Library')

        :id: 0093be1c-3664-448e-87f5-758bab34958a

        :expectedresults: Host is created, default lifecycle environment is
            associated

        :CaseImportance: Critical
        """
        new_host = make_fake_host({
            'content-view-id': self.DEFAULT_CV['id'],
            'lifecycle-environment-id': self.LIBRARY['id'],
            'organization-id': self.new_org['id'],
        })
        self.assertEqual(
            new_host['content-information']['lifecycle-environment'],
            self.LIBRARY['name'],
        )

    @tier1
    @run_only_on('sat')
    def test_positive_create_with_lce(self):
        """Check if host can be created with new lifecycle

        :id: e102b034-0011-471d-ba21-5ef8d129a61f

        :expectedresults: Host is created using new lifecycle

        :CaseImportance: Critical
        """
        new_host = make_fake_host({
            'content-view-id': self.promoted_cv['id'],
            'lifecycle-environment-id': self.new_lce['id'],
            'organization-id': self.new_org['id'],
        })
        self.assertEqual(
            new_host['content-information']['lifecycle-environment'],
            self.new_lce['name'],
        )

    @tier1
    @run_only_on('sat')
    def test_positive_create_with_cv(self):
        """Check if host can be created with new content view

        :id: f90873b9-fb3a-4c93-8647-4b1aea0a2c35

        :expectedresults: Host is created using new published, promoted cv

        :CaseImportance: Critical
        """
        new_host = make_fake_host({
            'content-view-id': self.promoted_cv['id'],
            'lifecycle-environment-id': self.new_lce['id'],
            'organization-id': self.new_org['id'],
        })
        self.assertEqual(
            new_host['content-information']['content-view'],
            self.promoted_cv['name'],
        )

    @tier1
    def test_positive_create_with_puppet_class_id(self):
        """Check if host can be created with puppet class id

        :id: 6bb1bbdc-23fd-4493-9283-fbb70d72b2eb

        :expectedresults: Host is created and has puppet class assigned

        :CaseImportance: Critical
        """
        host = make_fake_host({
            'puppet-class-ids': self.puppet_class['id'],
            'environment-id': self.puppet_env['id'],
        })
        host_classes = Host.puppetclasses({'host-id': host['id']})
        self.assertIn(
            self.puppet_class['id'],
            [puppet['id'] for puppet in host_classes]
        )

    @tier1
    def test_positive_create_with_puppet_class_name(self):
        """Check if host can be created with puppet class name

        :id: a65df36e-db4b-48d2-b0e1-5ccfbefd1e7a

        :expectedresults: Host is created and has puppet class assigned

        :CaseImportance: Critical
        """
        host = make_fake_host({
            'puppet-classes': self.puppet_class['name'],
            'environment': self.puppet_env['name'],
        })
        host_classes = Host.puppetclasses({'host': host['name']})
        self.assertIn(
            self.puppet_class['name'],
            [puppet['name'] for puppet in host_classes]
        )

    @tier1
    def test_negative_create_with_name(self):
        """Check if host can be created with random long names

        :id: f92b6070-b2d1-4e3e-975c-39f1b1096697

        :expectedresults: Host is not created

        :CaseImportance: Critical
        """
        for name in invalid_values_list():
            with self.subTest(name):
                with self.assertRaises(CLIFactoryError):
                    make_fake_host({
                        'name': name,
                        'organization-id': self.new_org['id'],
                        'content-view-id': self.DEFAULT_CV['id'],
                        'lifecycle-environment-id': self.LIBRARY['id'],
                    })

    @tier1
    @run_only_on('sat')
    def test_negative_create_with_unpublished_cv(self):
        """Check if host can be created using unpublished cv

        :id: 9997383d-3c27-4f14-94f9-4b8b51180eb6

        :expectedresults: Host is not created using new unpublished cv

        :CaseImportance: Critical
        """
        cv = make_content_view({'organization-id': self.new_org['id']})
        env = self.new_lce['id']
        with self.assertRaises(CLIFactoryError):
            make_fake_host({
                'content-view-id': cv['id'],
                'lifecycle-environment-id': env,
                'organization-id': self.new_org['id'],
            })

    @tier3
    def test_positive_register_with_no_ak(self):
        """Register host to satellite without activation key

        :id: 6a7cedd2-aa9c-4113-a83b-3f0eea43ecb4

        :expectedresults: Host successfully registered to appropriate org

        :CaseLevel: System
        """
        with VirtualMachine(distro=DISTRO_RHEL7) as client:
            client.install_katello_ca()
            result = client.register_contenthost(
                self.new_org['label'],
                lce='{}/{}'.format(
                    self.new_lce['label'], self.promoted_cv['label']),
            )
            self.assertEqual(result.return_code, 0)

    @tier3
    def test_negative_register_twice(self):
        """Attempt to register a host twice to Satellite

        :id: 0af81129-cd69-4fa7-a128-9e8fcf2d03b1

        :expectedresults: host cannot be registered twice

        :CaseLevel: System
        """
        activation_key = make_activation_key({
            'content-view-id': self.promoted_cv['id'],
            'lifecycle-environment-id': self.new_lce['id'],
            'organization-id': self.new_org['id'],
        })
        with VirtualMachine(distro=DISTRO_RHEL7) as client:
            client.install_katello_ca()
            client.register_contenthost(
                self.new_org['label'],
                activation_key['name'],
            )
            result = client.register_contenthost(
                self.new_org['label'],
                activation_key['name'],
                force=False,
            )
            # Depending on distro version, successful return_code may be 0 or
            # 1, so we can't verify host wasn't registered by return_code != 0
            # check. Verifying return_code == 64 here, which stands for content
            # host being already registered.
            self.assertEqual(result.return_code, 64)

    @run_only_on('sat')
    @tier2
    def test_positive_list_scparams_by_id(self):
        """List all smart class parameters using host id

        :id: 596322f6-9fdc-441a-a36d-ae2f22132b38

        :expectedresults: Overridden sc-param from puppet class is listed

        :Caselevel: Integration
        """
        # Create hostgroup with associated puppet class
        host = make_fake_host({
            'puppet-classes': self.puppet_class['name'],
            'environment': self.puppet_env['name'],
        })
        # Override one of the sc-params from puppet class
        sc_params_list = SmartClassParameter.list({
            'environment': self.puppet_env['name'],
            'search': u'puppetclass="{0}"'.format(self.puppet_class['name'])
        })
        scp_id = choice(sc_params_list)['id']
        SmartClassParameter.update({'id': scp_id, 'override': 1})
        # Verify that affected sc-param is listed
        host_scparams = Host.sc_params({'host': host['name']})
        self.assertIn(scp_id, [scp['id'] for scp in host_scparams])

    @run_only_on('sat')
    @tier2
    def test_positive_list_scparams_by_name(self):
        """List all smart class parameters using host name

        :id: 26e406ea-56f5-4813-bb93-e908c9015ee3

        :expectedresults: Overridden sc-param from puppet class is listed

        :Caselevel: Integration
        """
        # Create hostgroup with associated puppet class
        host = make_fake_host({
            'puppet-classes': self.puppet_class['name'],
            'environment': self.puppet_env['name'],
        })
        # Override one of the sc-params from puppet class
        sc_params_list = SmartClassParameter.list({
            'environment': self.puppet_env['name'],
            'search': u'puppetclass="{0}"'.format(self.puppet_class['name'])
        })
        scp_id = choice(sc_params_list)['id']
        SmartClassParameter.update({'id': scp_id, 'override': 1})
        # Verify that affected sc-param is listed
        host_scparams = Host.sc_params({'host': host['name']})
        self.assertIn(scp_id, [scp['id'] for scp in host_scparams])

    @run_only_on('sat')
    @tier2
    def test_positive_list_smartvariables_by_id(self):
        """List all smart variables using host id

        :id: 22d85dea-0fc0-47c2-8f38-c6f6712dad7e

        :expectedresults: Smart variable from puppet class is listed

        :Caselevel: Integration
        """
        # Create hostgroup with associated puppet class
        host = make_fake_host({
            'puppet-classes': self.puppet_class['name'],
            'environment': self.puppet_env['name'],
        })
        # Create smart variable
        smart_variable = make_smart_variable(
            {'puppet-class': self.puppet_class['name']})
        # Verify that affected sc-param is listed
        host_variables = Host.smart_variables({'host-id': host['id']})
        self.assertIn(
            smart_variable['id'], [sv['id'] for sv in host_variables])

    @run_only_on('sat')
    @tier2
    def test_positive_list_smartvariables_by_name(self):
        """List all smart variables using host name

        :id: a254d3a6-cf7f-4847-acb6-9813d23369d4

        :expectedresults: Smart variable from puppet class is listed

        :Caselevel: Integration
        """
        # Create hostgroup with associated puppet class
        host = make_fake_host({
            'puppet-classes': self.puppet_class['name'],
            'environment': self.puppet_env['name'],
        })
        # Create smart variable
        smart_variable = make_smart_variable(
            {'puppet-class': self.puppet_class['name']})
        # Verify that affected sc-param is listed
        host_variables = Host.smart_variables({'host': host['name']})
        self.assertIn(
            smart_variable['id'], [sv['id'] for sv in host_variables])

    @tier3
    def test_positive_list(self):
        """List hosts for a given org

        :id: b9c056cd-11ca-4870-bac4-0ebc4a782cb0

        :expectedresults: Hosts are listed for the given org

        :CaseLevel: System
        """
        activation_key = make_activation_key({
            'content-view-id': self.promoted_cv['id'],
            'lifecycle-environment-id': self.new_lce['id'],
            'organization-id': self.new_org['id'],
        })
        with VirtualMachine(distro=DISTRO_RHEL7) as client:
            client.install_katello_ca()
            client.register_contenthost(
                self.new_org['label'],
                activation_key['name'],
            )
            hosts = Host.list({
                'organization-id': self.new_org['id'],
                'environment-id': self.new_lce['id'],
            })
            self.assertGreaterEqual(len(hosts), 1)
            self.assertIn(client.hostname, [host['name'] for host in hosts])

    @tier3
    def test_positive_unregister(self):
        """Unregister a host

        :id: c5ce988d-d0ea-4958-9956-5a4b039b285c

        :expectedresults: Host is successfully unregistered. Unlike content
            host, host has not disappeared from list of hosts after
            unregistering.

        :CaseLevel: System
        """
        activation_key = make_activation_key({
            'content-view-id': self.promoted_cv['id'],
            'lifecycle-environment-id': self.new_lce['id'],
            'organization-id': self.new_org['id'],
        })
        with VirtualMachine(distro=DISTRO_RHEL7) as client:
            client.install_katello_ca()
            client.register_contenthost(
                self.new_org['label'],
                activation_key['name'],
            )
            hosts = Host.list({
                'organization-id': self.new_org['id'],
                'environment-id': self.new_lce['id'],
            })
            self.assertGreaterEqual(len(hosts), 1)
            self.assertIn(client.hostname, [host['name'] for host in hosts])
            result = client.run('subscription-manager unregister')
            self.assertEqual(result.return_code, 0)
            hosts = Host.list({
                'organization-id': self.new_org['id'],
                'environment-id': self.new_lce['id'],
            })
            self.assertIn(client.hostname, [host['name'] for host in hosts])

    @skip_if_not_set('compute_resources')
    @tier1
    def test_positive_create_using_libvirt_without_mac(self):
        """Create a libvirt host and not specify a MAC address.

        :id: b003faa9-2810-4176-94d2-ea84bed248eb

        :expectedresults: Host is created

        :CaseImportance: Critical
        """
        compute_resource = entities.LibvirtComputeResource(
            url='qemu+ssh://root@{0}/system'.format(
                settings.compute_resources.libvirt_hostname
            )
        ).create()
        host = entities.Host()
        host.create_missing()
        result = Host.create({
            u'architecture-id': host.architecture.id,
            u'compute-resource-id': compute_resource.id,
            u'domain-id': host.domain.id,
            u'environment-id': host.environment.id,
            u'location-id': host.location.id,  # pylint:disable=no-member
            u'medium-id': host.medium.id,
            u'name': host.name,
            u'operatingsystem-id': host.operatingsystem.id,
            # pylint:disable=no-member
            u'organization-id': host.organization.id,
            u'partition-table-id': host.ptable.id,
            u'puppet-proxy-id': self.puppet_proxy['id'],
            u'root-pass': host.root_pass,
        })
        self.assertEqual(result['name'], host.name + '.' + host.domain.name)
        Host.delete({'id': result['id']})

    @tier2
    def test_positive_create_inherit_lce_cv(self):
        """Create a host with hostgroup specified. Make sure host inherited
        hostgroup's lifecycle environment and content-view

        :id: ba73b8c8-3ce1-4fa8-a33b-89ded9ffef47

        :expectedresults: Host's lifecycle environment and content view match
            the ones specified in hostgroup

        :CaseLevel: Integration

        :BZ: 1391656
        """
        hostgroup = make_hostgroup({
            'content-view-id': self.new_cv['id'],
            'lifecycle-environment-id': self.new_lce['id'],
            'organization-ids': self.new_org['id'],
        })
        host = make_fake_host({
            'hostgroup-id': hostgroup['id'],
            'organization-id': self.new_org['id'],
        })
        self.assertEqual(
            host['content-information']['lifecycle-environment'],
            hostgroup['lifecycle-environment'],
        )
        self.assertEqual(
            host['content-information']['content-view'],
            hostgroup['content-view'],
        )

    @run_only_on('sat')
    @stubbed
    @tier3
    def test_positive_create_baremetal_with_bios(self):
        """Create a new Host from provided MAC address

        :id: 01509973-9f0b-4166-9fbd-59b753a7384b

        :setup: Create a PXE-based VM with BIOS boot mode (outside of
            Satellite).

        :steps: Create a new host using 'BareMetal' option and MAC address of
            the pre-created VM

        :expectedresults: Host is created

        :caseautomation: notautomated

        :caselevel: System
        """

    @run_only_on('sat')
    @stubbed
    @tier3
    def test_positive_create_baremetal_with_uefi(self):
        """Create a new Host from provided MAC address

        :id: 508b268b-244d-4bf0-a92a-fbee96e7e8ae

        :setup: Create a PXE-based VM with UEFI boot mode (outside of
            Satellite).

        :steps: Create a new host using 'BareMetal' option and MAC address of
            the pre-created VM

        :expectedresults: Host is created

        :caseautomation: notautomated

        :caselevel: System
        """

    @run_only_on('sat')
    @stubbed
    @tier3
    def test_positive_verify_files_with_pxegrub_uefi(self):
        """Provision a new Host and verify the tftp and dhcp file structure is
        correct

        :id: 8b4f5bb3-d949-4000-bc97-2be85c4f57be

        :steps:

            1. Associate a pxegrub-type provisioning template with the os
            2. Create new host (can be fictive bare metal) with the above OS
               and PXE loader set to Grub UEFI
            3. Build the host

        :expectedresults: Verify [/var/lib/tftpboot/] contains the following
            dir/file structure:

                grub/bootia32.efi
                grub/bootx64.efi
                grub/01-AA-BB-CC-DD-EE-FF
                grub/efidefault
                grub/shim.efi

            And record in /var/lib/dhcpd/dhcpd.leases points to the bootloader

        :caseautomation: notautomated

        :caselevel: System
        """

    @run_only_on('sat')
    @stubbed
    @tier3
    def test_positive_verify_files_with_pxegrub_uefi_secureboot(self):
        """Provision a new Host and verify the tftp and dhcp file structure is
        correct


        :id: a5482ecd-7bb8-4fda-9a74-f17751e11daf

        :steps:

            1. Associate a pxegrub-type provisioning template with the os
            2. Create new host (can be fictive bare metal) with the above OS
               and PXE loader set to Grub UEFI SecureBoot
            3. Build the host

        :expectedresults: Verify [/var/lib/tftpboot/] contains the following
            dir/file structure:

                grub/bootia32.efi
                grub/bootx64.efi
                grub/01-AA-BB-CC-DD-EE-FF
                grub/efidefault
                grub/shim.efi

            And record in /var/lib/dhcpd/dhcpd.leases points to the bootloader

        :caseautomation: notautomated

        :caselevel: System
        """

    @run_only_on('sat')
    @stubbed
    @tier3
    def test_positive_verify_files_with_pxegrub2_uefi(self):
        """Provision a new UEFI Host and verify the tftp and dhcp file
        structure is correct

        :id: ce1acb0b-ff2e-4622-9e69-e3c0c4fdc466

        :steps:

            1. Associate a pxegrub-type provisioning template with the os
            2. Create new host (can be fictive bare metal) with the above OS
               and PXE loader set to Grub2 UEFI
            3. Build the host

        :expectedresults: Verify [/var/lib/tftpboot/] contains the following
            dir/file structure:

                pxegrub2
                grub2/grub.cfg-01-aa-bb-cc-dd-ee-ff
                grub2/grub.cfg
                grub2/grubx32.efi
                grub2/grubx64.efi
                grub/shim.efi

            And record in /var/lib/dhcpd/dhcpd.leases points to the bootloader

        :caseautomation: notautomated

        :caselevel: System
        """

    @run_only_on('sat')
    @stubbed
    @tier3
    def test_positive_verify_files_with_pxegrub2_uefi_secureboot(self):
        """Provision a new UEFI Host and verify the tftp and dhcp file
        structure is correct

        :id: 6811e0b0-154a-4af6-80c0-86009672a965

        :steps:

            1. Associate a pxegrub-type provisioning template with the os
            2. Create new host (can be fictive bare metal) with the above OS
               and PXE loader set to Grub2 UEFI SecureBoot
            3. Build the host

        :expectedresults: Verify [/var/lib/tftpboot/] contains the following
            dir/file structure:

                pxegrub2
                grub2/grub.cfg-01-aa-bb-cc-dd-ee-ff
                grub2/grub.cfg
                grub2/grubx32.efi
                grub2/grubx64.efi
                grub/shim.efi

            And record in /var/lib/dhcpd/dhcpd.leases points to the bootloader

        :caseautomation: notautomated

        :caselevel: System
        """


class HostDeleteTestCase(CLITestCase):
    """Tests for deleting the hosts via CLI."""

    def setUp(self):
        """Create a host to use in tests"""
        super(HostDeleteTestCase, self).setUp()
        # Use the default installation smart proxy
        self.puppet_proxy = Proxy.list({
            'search': 'url = https://{0}:9090'.format(settings.server.hostname)
        })[0]
        self.host = entities.Host()
        self.host.create_missing()
        self.host = Host.create({
            u'architecture-id': self.host.architecture.id,
            u'domain-id': self.host.domain.id,
            u'environment-id': self.host.environment.id,
            # pylint:disable=no-member
            u'location-id': self.host.location.id,
            u'mac': self.host.mac,
            u'medium-id': self.host.medium.id,
            u'name': gen_string('alphanumeric'),
            u'operatingsystem-id': self.host.operatingsystem.id,
            # pylint:disable=no-member
            u'organization-id': self.host.organization.id,
            u'partition-table-id': self.host.ptable.id,
            u'puppet-proxy-id': self.puppet_proxy['id'],
            u'root-pass': self.host.root_pass,
        })

    @tier1
    def test_positive_delete_by_id(self):
        """Create a host and then delete it by id.

        :id: e687a685-ab8b-4c5f-97f9-e14d3ab52f29

        :expectedresults: Host is deleted

        :CaseImportance: Critical
        """
        Host.delete({'id': self.host['id']})
        with self.assertRaises(CLIReturnCodeError):
            Host.info({'id': self.host['id']})

    @tier1
    def test_positive_delete_by_name(self):
        """Create a host and then delete it by name.

        :id: 93f7504d-9a63-491f-8fdb-ed8017aefab9

        :expectedresults: Host is deleted

        :CaseImportance: Critical
        """
        Host.delete({'name': self.host['name']})
        with self.assertRaises(CLIReturnCodeError):
            Host.info({'name': self.host['name']})


class HostUpdateTestCase(CLITestCase):
    """Tests for updating the hosts."""

    def setUp(self):
        """Create a host to reuse later"""
        super(HostUpdateTestCase, self).setUp()
        self.puppet_proxy = Proxy.list({
            'search': 'url = https://{0}:9090'.format(settings.server.hostname)
        })[0]
        # using nailgun to create dependencies
        self.host_args = entities.Host()
        self.host_args.create_missing()
        # using CLI to create host
        self.host = Host.create({
            u'architecture-id': self.host_args.architecture.id,
            u'domain-id': self.host_args.domain.id,
            u'environment-id': self.host_args.environment.id,
            # pylint:disable=no-member
            u'location-id': self.host_args.location.id,
            u'mac': self.host_args.mac,
            u'medium-id': self.host_args.medium.id,
            u'name': self.host_args.name,
            u'operatingsystem-id': self.host_args.operatingsystem.id,
            # pylint:disable=no-member
            u'organization-id': self.host_args.organization.id,
            u'partition-table-id': self.host_args.ptable.id,
            u'puppet-proxy-id': self.puppet_proxy['id'],
            u'root-pass': self.host_args.root_pass,
        })

    @skip_if_bug_open('bugzilla', '1343392')
    @tier1
    def test_positive_update_name_by_id(self):
        """A host can be updated with a new random name. Use id to
        access the host

        :id: 058dbcbf-d543-483d-b755-be0602588464

        :expectedresults: A host is updated and the name matches

        :CaseImportance: Critical
        """
        for new_name in valid_hosts_list():
            with self.subTest(new_name):
                Host.update({
                    'id': self.host['id'],
                    'new-name': new_name,
                })
                self.host = Host.info({'id': self.host['id']})
                self.assertEqual(
                    u'{0}.{1}'.format(
                        new_name, self.host['network']['domain']),
                    self.host['name']
                )

    @skip_if_bug_open('bugzilla', '1343392')
    @tier1
    def test_positive_update_name_by_name(self):
        """A host can be updated with a new random name. Use name to
        access the host

        :id: f95a5952-17bd-49da-b2a7-c79f0614f1c7

        :expectedresults: A host is updated and the name matches

        :CaseImportance: Critical
        """
        for new_name in valid_hosts_list():
            with self.subTest(new_name):
                Host.update({
                    'name': self.host['name'],
                    'new-name': new_name,
                })
                self.host = Host.info({
                    'name': u'{0}.{1}'.format(
                        new_name, self.host['network']['domain'])})
                self.assertEqual(
                    u'{0}.{1}'.format(
                        new_name, self.host['network']['domain']),
                    self.host['name'],
                )

    @tier1
    def test_positive_update_mac_by_id(self):
        """A host can be updated with a new random MAC address. Use id
        to access the host

        :id: 72ed9ae8-989a-46d1-8b7d-46f5db106e75

        :expectedresults: A host is updated and the MAC address matches

        :CaseImportance: Critical
        """
        new_mac = gen_mac()
        Host.update({
            'id': self.host['id'],
            'mac': new_mac,
        })
        self.host = Host.info({'id': self.host['id']})
        self.assertEqual(self.host['network']['mac'], new_mac)

    @tier1
    def test_positive_update_mac_by_name(self):
        """A host can be updated with a new random MAC address. Use name
        to access the host

        :id: a422788d-5473-4846-a86b-90d8f236285a

        :expectedresults: A host is updated and the MAC address matches

        :CaseImportance: Critical
        """
        new_mac = gen_mac()
        Host.update({
            'mac': new_mac,
            'name': self.host['name'],
        })
        self.host = Host.info({'name': self.host['name']})
        self.assertEqual(self.host['network']['mac'], new_mac)

    @tier2
    def test_positive_update_domain_by_id(self):
        """A host can be updated with a new domain. Use entities ids for
        association

        :id: 3aac0896-d16a-46ee-afe9-2d3ecea6ca9b

        :expectedresults: A host is updated and the domain matches

        :CaseLevel: Integration
        """
        new_domain = make_domain({
            'location-id': self.host_args.location.id,
            'organization-id': self.host_args.organization.id,
        })
        Host.update({
            'domain-id': new_domain['id'],
            'id': self.host['id'],
        })
        self.host = Host.info({'id': self.host['id']})
        self.assertEqual(self.host['network']['domain'], new_domain['name'])

    @tier2
    def test_positive_update_domain_by_name(self):
        """A host can be updated with a new domain. Use entities names
        for association

        :id: 9b4fb1b9-a226-4b8a-bfaf-1121de7df5bc

        :expectedresults: A host is updated and the domain matches

        :CaseLevel: Integration
        """
        new_domain = make_domain({
            'location': self.host_args.location.name,
            'organization': self.host_args.organization.name,
        })
        Host.update({
            'domain': new_domain['name'],
            'name': self.host['name'],
        })
        self.host = Host.info({
            'name': '{0}.{1}'.format(
                self.host['name'].split('.')[0],
                new_domain['name'],
            )
        })
        self.assertEqual(self.host['network']['domain'], new_domain['name'])

    @tier2
    def test_positive_update_env_by_id(self):
        """A host can be updated with a new environment. Use entities
        ids for association

        :id: 4e1d1e31-fa84-43e4-9e66-7fb953767ee5

        :expectedresults: A host is updated and the environment matches

        :CaseLevel: Integration
        """
        new_env = make_environment({
            'location-id': self.host_args.location.id,
            'organization-id': self.host_args.organization.id,
        })
        Host.update({
            'environment-id': new_env['id'],
            'id': self.host['id'],
        })
        self.host = Host.info({'id': self.host['id']})
        self.assertEqual(self.host['environment'], new_env['name'])

    @tier2
    def test_positive_update_env_by_name(self):
        """A host can be updated with a new environment. Use entities
        names for association

        :id: f0ec469a-7550-4f05-b39c-e68b9267247d

        :expectedresults: A host is updated and the environment matches

        :CaseLevel: Integration
        """
        new_env = make_environment({
            'location': self.host_args.location.name,
            'organization': self.host_args.organization.name,
        })
        Host.update({
            'environment': new_env['name'],
            'name': self.host['name'],
        })
        self.host = Host.info({'name': self.host['name']})
        self.assertEqual(self.host['environment'], new_env['name'])

    @tier2
    def test_positive_update_arch_by_id(self):
        """A host can be updated with a new architecture. Use entities
        ids for association

        :id: a4546fd6-997a-44e4-853a-eac235ea87b0

        :expectedresults: A host is updated and the architecture matches

        :CaseLevel: Integration
        """
        new_arch = make_architecture({
            'location-id': self.host_args.location.id,
            'organization-id': self.host_args.organization.id,
        })
        OperatingSys.add_architecture({
            'architecture-id': new_arch['id'],
            'id': self.host_args.operatingsystem.id,
        })
        Host.update({
            'architecture-id': new_arch['id'],
            'id': self.host['id'],
        })
        self.host = Host.info({'id': self.host['id']})
        self.assertEqual(
            self.host['operating-system']['architecture'], new_arch['name'])

    @tier2
    def test_positive_update_arch_by_name(self):
        """A host can be updated with a new architecture. Use entities
        names for association

        :id: 92da3782-47db-4701-aaab-3ea974043d20

        :expectedresults: A host is updated and the architecture matches

        :CaseLevel: Integration
        """
        new_arch = make_architecture({
            'location': self.host_args.location.name,
            'organization': self.host_args.organization.name,
        })
        OperatingSys.add_architecture({
            'architecture': new_arch['name'],
            'title': self.host_args.operatingsystem.title,
        })
        Host.update({
            'architecture': new_arch['name'],
            'name': self.host['name'],
        })
        self.host = Host.info({'name': self.host['name']})
        self.assertEqual(
            self.host['operating-system']['architecture'], new_arch['name'])

    @tier2
    def test_positive_update_os_by_id(self):
        """A host can be updated with a new operating system. Use
        entities ids for association

        :id: 9ea88634-9c14-4519-be6e-fb163897efb7

        :expectedresults: A host is updated and the operating system matches

        :CaseLevel: Integration
        """
        new_os = make_os({
            'architecture-ids': self.host_args.architecture.id,
            'partition-table-ids': self.host_args.ptable.id,
        })
        Medium.add_operating_system({
            'id': self.host_args.medium.id,
            'operatingsystem-id': new_os['id'],
        })
        Host.update({
            'id': self.host['id'],
            'operatingsystem-id': new_os['id'],
        })
        self.host = Host.info({'id': self.host['id']})
        self.assertEqual(
            self.host['operating-system']['operating-system'], new_os['title'])

    @tier2
    def test_positive_update_os_by_name(self):
        """A host can be updated with a new operating system. Use
        entities names for association

        :id: bd48887f-3db3-47b0-8231-de58884efe57

        :expectedresults: A host is updated and the operating system matches

        :CaseLevel: Integration
        """
        new_os = make_os({
            'architectures': self.host_args.architecture.name,
            'partition-tables': self.host[
                'operating-system']['partition-table'],
        })
        Medium.add_operating_system({
            'name': self.host_args.medium.name,
            'operatingsystem': new_os['title'],
        })
        Host.update({
            'name': self.host['name'],
            'operatingsystem': new_os['title'],
        })
        self.host = Host.info({'name': self.host['name']})
        self.assertEqual(
            self.host['operating-system']['operating-system'], new_os['title'])

    @tier2
    def test_positive_update_medium_by_id(self):
        """A host can be updated with a new medium. Use entities ids for
        association

        :id: 899f1eef-07a9-4227-848a-92e377a8d55c

        :expectedresults: A host is updated and the medium matches

        :CaseLevel: Integration
        """
        new_medium = make_medium({
            'location-id': self.host_args.location.id,
            'organization-id': self.host_args.organization.id,
        })
        Medium.add_operating_system({
            'id': new_medium['id'],
            'operatingsystem-id': self.host_args.operatingsystem.id,
        })
        new_medium = Medium.info({'id': new_medium['id']})
        Host.update({
            'id': self.host['id'],
            'medium-id': new_medium['id'],
        })
        self.host = Host.info({'id': self.host['id']})
        self.assertEqual(
            self.host['operating-system']['medium'], new_medium['name'])

    @tier2
    def test_positive_update_medium_by_name(self):
        """A host can be updated with a new medium. Use entities names
        for association

        :id: f47edb02-d649-4ca8-94b2-0637ebdac2e8

        :expectedresults: A host is updated and the medium matches

        :CaseLevel: Integration
        """
        new_medium = make_medium({
            'location': self.host_args.location.name,
            'organization': self.host_args.organization.name,
        })
        Medium.add_operating_system({
            'name': new_medium['name'],
            'operatingsystem': self.host_args.operatingsystem.title,
        })
        new_medium = Medium.info({'name': new_medium['name']})
        Host.update({
            'medium': new_medium['name'],
            'name': self.host['name'],
        })
        self.host = Host.info({'name': self.host['name']})
        self.assertEqual(
            self.host['operating-system']['medium'], new_medium['name'])

    @tier1
    def test_negative_update_name(self):
        """A host can not be updated with invalid or empty name

        :id: e8068d2a-6a51-4627-908b-60a516c67032

        :expectedresults: A host is not updated

        :CaseImportance: Critical
        """
        for new_name in invalid_values_list():
            with self.subTest(new_name):
                with self.assertRaises(CLIReturnCodeError):
                    Host.update({
                        'id': self.host['id'],
                        'new-name': new_name,
                    })
                self.host = Host.info({'id': self.host['id']})
                self.assertNotEqual(
                    u'{0}.{1}'.format(
                        new_name,
                        self.host['network']['domain'],
                    ).lower(),
                    self.host['name'],
                )

    @tier1
    def test_negative_update_mac(self):
        """A host can not be updated with invalid or empty MAC address

        :id: 2f03032d-789d-419f-9ff2-a6f3561444da

        :expectedresults: A host is not updated

        :CaseImportance: Critical
        """
        for new_mac in invalid_values_list():
            with self.subTest(new_mac):
                with self.assertRaises(CLIReturnCodeError):
                    Host.update({
                        'id': self.host['id'],
                        'mac': new_mac,
                    })
                    self.host = Host.info({'id': self.host['id']})
                    self.assertEqual(self.host['network']['mac'], new_mac)

    @tier2
    def test_negative_update_arch(self):
        """A host can not be updated with a architecture, which does not
        belong to host's operating system

        :id: a86524da-8caf-472b-9a3d-17a4385c3a18

        :expectedresults: A host is not updated

        :CaseLevel: Integration
        """
        new_arch = make_architecture({
            'location': self.host_args.location.name,
            'organization': self.host_args.organization.name,
        })
        with self.assertRaises(CLIReturnCodeError):
            Host.update({
                'architecture': new_arch['name'],
                'id': self.host['id'],
            })
        self.host = Host.info({'id': self.host['id']})
        self.assertNotEqual(
            self.host['operating-system']['architecture'], new_arch['name'])

    @tier2
    def test_negative_update_os(self):
        """A host can not be updated with a operating system, which is
        not associated with host's medium

        :id: ff13d2af-e54a-4daf-a24d-7ec930b4fbbe

        :expectedresults: A host is not updated

        :CaseLevel: Integration
        """
        new_arch = make_architecture({
            'location': self.host_args.location.name,
            'organization': self.host_args.organization.name,
        })
        new_os = make_os({
            'architectures': new_arch['name'],
            'partition-tables': self.host[
                'operating-system']['partition-table'],
        })
        with self.assertRaises(CLIReturnCodeError):
            Host.update({
                'architecture': new_arch['name'],
                'id': self.host['id'],
                'operatingsystem': new_os['title'],
            })
        self.host = Host.info({'id': self.host['id']})
        self.assertNotEqual(
            self.host['operating-system']['operating-system'], new_os['title'])


class HostParameterTestCase(CLITestCase):
    """Tests targeting host parameters"""

    @classmethod
    def setUpClass(cls):
        """Create host to tests parameters for"""
        super(HostParameterTestCase, cls).setUpClass()
        cls.puppet_proxy = Proxy.list({
            'search': 'url = https://{0}:9090'.format(settings.server.hostname)
        })[0]
        # using nailgun to create dependencies
        cls.host = entities.Host()
        cls.host.create_missing()
        # using CLI to create host
        cls.host = Host.create({
            u'architecture-id': cls.host.architecture.id,
            u'domain-id': cls.host.domain.id,
            u'environment-id': cls.host.environment.id,
            u'location-id': cls.host.location.id,  # pylint:disable=no-member
            u'mac': cls.host.mac,
            u'medium-id': cls.host.medium.id,
            u'name': cls.host.name,
            u'operatingsystem-id': cls.host.operatingsystem.id,
            # pylint:disable=no-member
            u'organization-id': cls.host.organization.id,
            u'partition-table-id': cls.host.ptable.id,
            u'puppet-proxy-id': cls.puppet_proxy['id'],
            u'root-pass': cls.host.root_pass,
        })

    @tier1
    def test_positive_add_parameter_with_name(self):
        """Add host parameter with different valid names.

        :id: 67b1c496-8f33-4a34-aebb-7339bc33ce77

        :expectedresults: Host parameter was successfully added with correct
            name.


        :CaseImportance: Critical
        """
        for name in valid_data_list():
            with self.subTest(name):
                name = name.lower()
                Host.set_parameter({
                    'host-id': self.host['id'],
                    'name': name,
                    'value': gen_string('alphanumeric'),
                })
                self.host = Host.info({'id': self.host['id']})
                self.assertIn(name, self.host['parameters'].keys())

    @tier1
    def test_positive_add_parameter_with_value(self):
        """Add host parameter with different valid values.

        :id: 1932b61d-8be4-4f58-9760-dc588cbca1d7

        :expectedresults: Host parameter was successfully added with value.


        :CaseImportance: Critical
        """
        for value in valid_data_list():
            with self.subTest(value):
                name = gen_string('alphanumeric').lower()
                Host.set_parameter({
                    'host-id': self.host['id'],
                    'name': name,
                    'value': value,
                })
                self.host = Host.info({'id': self.host['id']})
                self.assertIn(name, self.host['parameters'].keys())
                self.assertEqual(value, self.host['parameters'][name])

    @tier1
    def test_positive_add_parameter_by_host_name(self):
        """Add host parameter by specifying host name.

        :id: 32b09b07-39de-4706-ac5e-75a54255df17

        :expectedresults: Host parameter was successfully added with correct
            name and value.

        :CaseImportance: Critical
        """
        name = gen_string('alphanumeric').lower()
        value = gen_string('alphanumeric')
        Host.set_parameter({
            'host': self.host['name'],
            'name': name,
            'value': value,
        })
        self.host = Host.info({'id': self.host['id']})
        self.assertIn(name, self.host['parameters'].keys())
        self.assertEqual(value, self.host['parameters'][name])

    @tier1
    def test_positive_update_parameter_by_host_id(self):
        """Update existing host parameter by specifying host ID.

        :id: 56c43ab4-7fb0-44f5-9d54-107d3c1011bf

        :expectedresults: Host parameter was successfully updated with new
            value.


        :CaseImportance: Critical
        """
        name = gen_string('alphanumeric').lower()
        old_value = gen_string('alphanumeric')
        Host.set_parameter({
            'host-id': self.host['id'],
            'name': name,
            'value': old_value,
        })
        for new_value in valid_data_list():
            with self.subTest(new_value):
                Host.set_parameter({
                    'host-id': self.host['id'],
                    'name': name,
                    'value': new_value,
                })
                self.host = Host.info({'id': self.host['id']})
                self.assertIn(name, self.host['parameters'].keys())
                self.assertEqual(new_value, self.host['parameters'][name])

    @tier1
    def test_positive_update_parameter_by_host_name(self):
        """Update existing host parameter by specifying host name.

        :id: 24bcc8a4-7787-4fa8-9bf8-dfc5e697684f

        :expectedresults: Host parameter was successfully updated with new
            value.


        :CaseImportance: Critical
        """
        name = gen_string('alphanumeric').lower()
        old_value = gen_string('alphanumeric')
        Host.set_parameter({
            'host': self.host['name'],
            'name': name,
            'value': old_value,
        })
        for new_value in valid_data_list():
            with self.subTest(new_value):
                Host.set_parameter({
                    'host': self.host['name'],
                    'name': name,
                    'value': new_value,
                })
                self.host = Host.info({'id': self.host['id']})
                self.assertIn(name, self.host['parameters'].keys())
                self.assertEqual(new_value, self.host['parameters'][name])

    @tier1
    def test_positive_delete_parameter_by_host_id(self):
        """Delete existing host parameter by specifying host ID.

        :id: a52da845-0403-4b66-9e83-6065f7d4551d

        :expectedresults: Host parameter was successfully deleted.


        :CaseImportance: Critical
        """
        for name in valid_data_list():
            with self.subTest(name):
                name = name.lower()
                Host.set_parameter({
                    'host-id': self.host['id'],
                    'name': name,
                    'value': gen_string('alphanumeric'),
                })
                Host.delete_parameter({
                    'host-id': self.host['id'],
                    'name': name,
                })
                self.host = Host.info({'id': self.host['id']})
                self.assertNotIn(name, self.host['parameters'].keys())

    @tier1
    def test_posistive_delete_parameter_by_host_name(self):
        """Delete existing host parameter by specifying host name.

        :id: d28cbbba-d296-49c7-91f5-8fb63a80d82c

        :expectedresults: Host parameter was successfully deleted.


        :CaseImportance: Critical
        """
        for name in valid_data_list():
            with self.subTest(name):
                name = name.lower()
                Host.set_parameter({
                    'host': self.host['name'],
                    'name': name,
                    'value': gen_string('alphanumeric'),
                })
                Host.delete_parameter({
                    'host': self.host['name'],
                    'name': name,
                })
                self.host = Host.info({'id': self.host['id']})
                self.assertNotIn(name, self.host['parameters'].keys())

    @tier1
    def test_negative_add_parameter(self):
        """Try to add host parameter with different invalid names.

        :id: 473f8c3f-b66e-4526-88af-e139cc3dabcb

        :expectedresults: Host parameter was not added.


        :CaseImportance: Critical
        """
        for name in invalid_values_list():
            with self.subTest(name):
                name = name.lower()
                with self.assertRaises(CLIReturnCodeError):
                    Host.set_parameter({
                        'host-id': self.host['id'],
                        'name': name,
                        'value': gen_string('alphanumeric'),
                    })
                self.host = Host.info({'id': self.host['id']})
                self.assertNotIn(name, self.host['parameters'].keys())


@run_in_one_thread
class KatelloAgentTestCase(CLITestCase):
    """Host tests, which require VM with installed katello-agent."""

    org = None
    env = None
    content_view = None
    activation_key = None

    @classmethod
    @skip_if_not_set('clients', 'fake_manifest')
    def setUpClass(cls):
        """Create Org, Lifecycle Environment, Content View, Activation key

        """
        super(KatelloAgentTestCase, cls).setUpClass()
        # Create new org, environment, CV and activation key
        KatelloAgentTestCase.org = make_org()
        KatelloAgentTestCase.env = make_lifecycle_environment({
            u'organization-id': KatelloAgentTestCase.org['id'],
        })
        KatelloAgentTestCase.content_view = make_content_view({
            u'organization-id': KatelloAgentTestCase.org['id'],
        })
        KatelloAgentTestCase.activation_key = make_activation_key({
            u'lifecycle-environment-id': KatelloAgentTestCase.env['id'],
            u'organization-id': KatelloAgentTestCase.org['id'],
        })
        if settings.cdn:
            # Add subscription to Satellite Tools repo to activation key
            setup_org_for_a_rh_repo({
                u'product': PRDS['rhel'],
                u'repository-set': REPOSET['rhst7'],
                u'repository': REPOS['rhst7']['name'],
                u'organization-id': KatelloAgentTestCase.org['id'],
                u'content-view-id': KatelloAgentTestCase.content_view['id'],
                u'lifecycle-environment-id': KatelloAgentTestCase.env['id'],
                u'activationkey-id': KatelloAgentTestCase.activation_key['id'],
            })
        else:
            # Create custom internal Tools repo, add to activation key
            setup_org_for_a_custom_repo({
                u'url': settings.sattools_repo,
                u'organization-id': KatelloAgentTestCase.org['id'],
                u'content-view-id': KatelloAgentTestCase.content_view['id'],
                u'lifecycle-environment-id': KatelloAgentTestCase.env['id'],
                u'activationkey-id': KatelloAgentTestCase.activation_key['id'],
            })
        # Create custom repo, add subscription to activation key
        setup_org_for_a_custom_repo({
            u'url': FAKE_0_YUM_REPO,
            u'organization-id': KatelloAgentTestCase.org['id'],
            u'content-view-id': KatelloAgentTestCase.content_view['id'],
            u'lifecycle-environment-id': KatelloAgentTestCase.env['id'],
            u'activationkey-id': KatelloAgentTestCase.activation_key['id'],
        })

    def setUp(self):
        """Create VM, subscribe it to satellite-tools repo, install katello-ca
        and katello-agent packages

        """
        super(KatelloAgentTestCase, self).setUp()
        # Create VM and register content host
        self.client = VirtualMachine(distro=DISTRO_RHEL7)
        self.addCleanup(vm_cleanup, self.client)
        self.client.create()
        self.client.install_katello_ca()
        # Register content host, install katello-agent
        self.client.register_contenthost(
            KatelloAgentTestCase.org['label'],
            KatelloAgentTestCase.activation_key['name'],
        )
        self.host = Host.info({'name': self.client.hostname})
        if settings.cdn:
            self.client.enable_repo(REPOS['rhst7']['id'])
        self.client.install_katello_agent()

    @tier3
    @run_only_on('sat')
    def test_positive_get_errata_info(self):
        """Get errata info

        :id: afb5ab34-1703-49dc-8ddc-5e032c1b86d7

        :expectedresults: Errata info was displayed


        :CaseLevel: System
        """
        self.client.download_install_rpm(
            FAKE_0_YUM_REPO,
            FAKE_0_CUSTOM_PACKAGE
        )
        result = Host.errata_info({
            u'host-id': self.host['id'],
            u'id': FAKE_0_ERRATA_ID,
        })
        self.assertEqual(result[0]['errata-id'], FAKE_0_ERRATA_ID)
        self.assertEqual(result[0]['packages'], FAKE_0_CUSTOM_PACKAGE)

    @tier3
    @run_only_on('sat')
    def test_positive_apply_errata(self):
        """Apply errata to a host

        :id: 8d0e5c93-f9fd-4ec0-9a61-aa93082a30c5

        :expectedresults: Errata is scheduled for installation


        :CaseLevel: System
        """
        self.client.download_install_rpm(
            FAKE_0_YUM_REPO,
            FAKE_0_CUSTOM_PACKAGE
        )
        Host.errata_apply({
            u'errata-ids': FAKE_0_ERRATA_ID,
            u'host-id': self.host['id'],
        })

    @tier3
    @run_only_on('sat')
    def test_positive_install_package(self):
        """Install a package to a host remotely

        :id: b1009bba-0c7e-4b00-8ac4-256e5cfe4a78

        :expectedresults: Package was successfully installed


        :CaseLevel: System
        """
        Host.package_install({
            u'host-id': self.host['id'],
            u'packages': FAKE_0_CUSTOM_PACKAGE_NAME,
        })
        result = self.client.run(
            'rpm -q {0}'.format(FAKE_0_CUSTOM_PACKAGE_NAME)
        )
        self.assertEqual(result.return_code, 0)

    @tier3
    @run_only_on('sat')
    def test_positive_remove_package(self):
        """Remove a package from a host remotely

        :id: 573dec11-8f14-411f-9e41-84426b0f23b5

        :expectedresults: Package was successfully removed


        :CaseLevel: System
        """
        self.client.download_install_rpm(
            FAKE_0_YUM_REPO,
            FAKE_0_CUSTOM_PACKAGE
        )
        Host.package_remove({
            u'host-id': self.host['id'],
            u'packages': FAKE_0_CUSTOM_PACKAGE_NAME,
        })
        result = self.client.run(
            'rpm -q {0}'.format(FAKE_0_CUSTOM_PACKAGE_NAME)
        )
        self.assertNotEqual(result.return_code, 0)

    @tier3
    @run_only_on('sat')
    def test_positive_upgrade_package(self):
        """Upgrade a host package remotely

        :id: ad751c63-7175-40ae-8bc4-800462cd9c29

        :expectedresults: Package was successfully upgraded


        :CaseLevel: System
        """
        self.client.run('yum install -y {0}'.format(FAKE_1_CUSTOM_PACKAGE))
        Host.package_upgrade({
            u'host-id': self.host['id'],
            u'packages': FAKE_1_CUSTOM_PACKAGE_NAME,
        })
        result = self.client.run('rpm -q {0}'.format(FAKE_2_CUSTOM_PACKAGE))
        self.assertEqual(result.return_code, 0)

    @tier3
    @run_only_on('sat')
    def test_positive_upgrade_packages_all(self):
        """Upgrade all the host packages remotely

        :id: 003101c7-bb95-4e51-a598-57977b2858a9

        :expectedresults: Packages (at least 1 with newer version available)
            were successfully upgraded

        :CaseLevel: System
        """
        self.client.run('yum install -y {0}'.format(FAKE_1_CUSTOM_PACKAGE))
        Host.package_upgrade_all({'host-id': self.host['id']})
        result = self.client.run('rpm -q {0}'.format(FAKE_2_CUSTOM_PACKAGE))
        self.assertEqual(result.return_code, 0)

    @tier3
    @run_only_on('sat')
    def test_positive_install_package_group(self):
        """Install a package group to a host remotely

        :id: 8c28c188-2903-44d1-ab1e-b74f6d6affcf

        :expectedresults: Package group was successfully installed


        :CaseLevel: System
        """
        Host.package_group_install({
            u'groups': FAKE_0_CUSTOM_PACKAGE_GROUP_NAME,
            u'host-id': self.host['id'],
        })
        for package in FAKE_0_CUSTOM_PACKAGE_GROUP:
            result = self.client.run('rpm -q {0}'.format(package))
            self.assertEqual(result.return_code, 0)

    @tier3
    @run_only_on('sat')
    def test_positive_remove_package_group(self):
        """Remove a package group from a host remotely

        :id: c80dbeff-93b4-4cd4-8fae-6a4d1bfc94f0

        :expectedresults: Package group was successfully removed


        :CaseLevel: System
        """
        hammer_args = {
            u'groups': FAKE_0_CUSTOM_PACKAGE_GROUP_NAME,
            u'host-id': self.host['id'],
        }
        Host.package_group_install(hammer_args)
        Host.package_group_remove(hammer_args)
        for package in FAKE_0_CUSTOM_PACKAGE_GROUP:
            result = self.client.run('rpm -q {0}'.format(package))
            self.assertNotEqual(result.return_code, 0)

    @tier3
    def test_negative_unregister_and_pull_content(self):
        """Attempt to retrieve content after host has been unregistered from
        Satellite

        :id: de0d0d91-b1e1-4f0e-8a41-c27df4d6b6fd

        :expectedresults: Host can no longer retrieve content from satellite

        :CaseLevel: System
        """
        result = self.client.run('subscription-manager unregister')
        self.assertEqual(result.return_code, 0)
        result = self.client.run(
            'yum install -y {0}'.format(FAKE_1_CUSTOM_PACKAGE))
        self.assertNotEqual(result.return_code, 0)


class HostErrataTestCase(CLITestCase):
    """Tests for errata's host sub command"""

    @tier1
    def test_positive_errata_list_of_sat_server(self):
        """Check if errata list doesn't raise exception. Check BZ for details.

        :id: 6b22f0c0-9c4b-11e6-ab93-68f72889dc7f

        :expectedresults: Satellite host errata list not failing

        :BZ: 1351040

        :CaseImportance: Critical
        """
        hostname = ssh.command('hostname').stdout[0]
        host = Host.info({'name': hostname})
        self.assertIsInstance(Host.errata_list({'host-id': host['id']}), list)
