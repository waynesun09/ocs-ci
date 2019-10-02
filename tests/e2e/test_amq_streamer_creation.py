import logging
import pytest

from ocs_ci.ocs import constants
from ocs_ci.ocs.amq import AMQ
from ocs_ci.framework.testlib import E2ETest, workloads

from ocs_ci.framework.testlib import tier1, ManageTest
from tests import helpers

log = logging.getLogger(__name__)

@pytest.fixture(scope='function')
def test_fixture_amq(request,storageclass_factory):
    global CEPHFS_SC_OBJ
    CEPHFS_SC_OBJ = storageclass_factory(interface=constants.CEPHFILESYSTEM,sc_name='amq-workload')
    # Change the above created StorageClass to default
    log.info(
        f"Changing the default StorageClass to {CEPHFS_SC_OBJ.name}"
    )
    helpers.change_default_storageclass(scname=CEPHFS_SC_OBJ.name)
    # Confirm that the default StorageClass is changed
    tmp_default_sc = helpers.get_default_storage_class()
    assert len(
        tmp_default_sc
    ) == 1, "More than 1 default storage class exist"
    log.info(f"Current Default StorageClass is:{tmp_default_sc[0]}")
    assert tmp_default_sc[0] == CEPHFS_SC_OBJ.name, (
        "Failed to change default StorageClass"
    )
    log.info(
        f"Successfully changed the default StorageClass to "
        f"{CEPHFS_SC_OBJ.name}"
    )

    amq = AMQ()
    amq.namespace = "my-project"

    def teardown():
        amq.cleanup()
    request.addfinalizer(teardown)
    return amq

@tier1
class TestAMQBasics(E2ETest):
    @pytest.mark.polarion_id("OCS-346")
    def test_install_amq_cephfs(self,test_fixture_amq):
        """
        Testing basics: secret creation,
         storage class creation, pvc and pod with cephfs
        """

        AMQ.setup_amq()
        # 4 oc apply -f install/cluster-operator -n my-project
        # 5 oc apply -f examples/templates/cluster-operator -n my-project
        # 6 oc apply -f examples/kafka/kafka-persistent.yaml
        # 7 oc apply -f examples/kafka-connect/kafka-connect.yaml
        # 8 oc apply -f examples/kafka-bridge/kafka-bridge.yaml
