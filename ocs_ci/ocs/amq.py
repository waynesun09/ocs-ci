
"""
AMQ Class to run amq specific tests
"""
import logging
from ocs_ci.ocs.exceptions import CommandFailed
from ocs_ci.ocs.ocp import OCP
from ocs_ci.ocs.ocp import switch_to_default_rook_cluster_project
from ocs_ci.ocs.utils import get_pod_name_by_pattern
from ocs_ci.ocs.resources.ocs import OCS
from ocs_ci.ocs import constants
from subprocess import run, CalledProcessError
from ocs_ci.utility.utils import run_cmd, TimeoutSampler
from ocs_ci.utility import templating


log = logging.getLogger(__name__)

class AMQ(object):
    """
      Workload operation using AMQ
    """

    def __init__(self, **kwargs):
        """
        Initializer function

        Args:
            kwargs (dict):
                Following kwargs are valid
                namespace: namespace for the operator
        """
        self.args = kwargs
        self.namespace = self.args.get('namespace', 'my-project')
        self.amq_is_setup = False
        self.ocp = OCP()
        self.ns_obj = OCP(kind='namespace')
        self.pod_obj = OCP(kind='pod')
        self.kafka_obj = OCP(kind='Kafka')
        self.kafka_connect_obj = OCP(kind = "KafkaConnect")
        self.kafka_bridge_obj = OCP(kind="KafkaBridge")
        self._create_namespace()

    def _create_namespace(self):
        """
        create namespace for amq
        """
        self.ocp.new_project(self.namespace)

    def setup_amq_cluster_operator(self):
        """
        Function to setup amq-cluster_operator,
        the file file is pulling from constants.TEMPLATE_DEPLOYMENT_AMQ_CP and TEMPLATE_DEPLOYMENT_AMQ_CP_EXAMPLE
        it will make sure cluster-operator pod is running
        :return:
        """

        self.amq_dir = constants.TEMPLATE_DEPLOYMENT_AMQ_CP
        run(f'oc apply -f {self.amq_dir} -n {self.namespace}', shell=True, check=True)
        # Wait for strimzi-cluster-operator pod to be created
        for strimzi_cluster_operator in TimeoutSampler(
            300, 3, get_pod_name_by_pattern, 'cluster-operator', self.namespace
        ):
            try:
                if strimzi_cluster_operator[0] is not None:
                    strimzi_cluster_operator_pod = strimzi_cluster_operator[0]
                    break
            except IndexError as ie:
                log.error("strimzi-cluster-operator pod not ready yet")
                raise ie
        #checking pod status
        if (self.pod_obj.wait_for_resource(
            condition='Running',
            resource_name=strimzi_cluster_operator_pod,
            timeout=1600,
            sleep=30,
            )
        ):
            log.info("pod is up and running")
        else:
            assert False, "Pod is not getting to running state"

        self.amq_dir_examples = constants.TEMPLATE_DEPLOYMENT_AMQ_CP_EXAMPLE
        run(f'oc apply -f {self.amq_dir_examples} -n {self.namespace}', shell=True, check=True)

        # checking pod status one more time
        if (self.pod_obj.wait_for_resource(
            condition='Running',
            resource_name=strimzi_cluster_operator_pod,
            timeout=1600,
            sleep=30,
            )
        ):
            log.info("pod is up and running")
            return
        assert False, "Pod is not getting to running state"

    def setup_amq_kafka_persistent(self):
        """
        Function to setup amq-kafka-persistent, the file file is pulling from constants.KAFKA_PER_YAML
        it will make kind: Kafka and will make sure the status is running
        :return:
        """

        try:
            kafka_persistent = templating.load_yaml(
                constants.KAFKA_PER_YAML
            )

            self.kafka_persistent = OCS(**kafka_persistent)
            self.kafka_persistent.create()
        except(CommandFailed, CalledProcessError) as cf:
            log.error('Failed during setup of AMQ Kafka-persistent')
            raise cf

        for cluster_zookeeper in TimeoutSampler(
            600, 5, get_pod_name_by_pattern, 'my-cluster-zookeeper', self.namespace
        ):
            try:
                if cluster_zookeeper[0] is not None:
                    cluster_zookeeper_pod = cluster_zookeeper[0]
                    break
            except IndexError:
                log.error("my-cluster-zookeeper pod not ready yet")

        #checking to make sure my-cluster-zookeeper pod is running
        if ( self.pod_obj.wait_for_resource(
            condition='Running',
            resource_name=cluster_zookeeper_pod,
            timeout=1600,
            sleep=30,
                )
            ):
                log.info("my-cluster-zookeeper Pod is running")
                return
        assert False, "my-cluster-zookeeper Pod is not getting to running state"

    def setup_amq_kafka_connect(self):
        """
        Function to setup amq-kafka-connect, the file file is pulling from constants.KAFCON_YAML
        it will make kind: KafkaConnect and will make sure the status is running
        :return:
        """

        try:
            kafka_connect = templating.load_yaml(
                constants.KAFCON_YAML
            )

            self.kafka_connect = OCS(**kafka_connect)
            self.kafka_connect.create()
        except(CommandFailed, CalledProcessError) as cf:
            log.error('Failed during setup of AMQ KafkaConnect')
            raise cf

        ## making sure the kafka-connect is running
        for kafka_connect_cluster in TimeoutSampler(
            300, 3, get_pod_name_by_pattern, 'my-connect-cluster-connect', self.namespace
        ):
            try:
                if kafka_connect_cluster[0] is not None:
                    kafka_connect_pod = kafka_connect_cluster[0]
                    break
            except IndexError:
                log.info("my-connect-cluster-connect pod not ready yet")

        #checking to make sure my-connect-cluster-connect pod is ready
        if ( self.pod_obj.wait_for_resource(
            condition='Running',
            resource_name=kafka_connect_pod,
            timeout=1600,
            sleep=30,
                )
            ):
            log.info("my-connect-cluster-connect Pod is running")
            return
        assert False, "my-connect-cluster-connect Pod is not getting to running state"

    def setup_amq_kafka_bridge(self):
        """
        Function to setup amq-kafka, the file file is pulling from constants.KAFBRI_YAML
        it will make kind: KafkaBridge and will make sure the status is running
        :return:
        """
        try:
            kafka_bridge = templating.load_yaml(
                constants.KAFBRI_YAML
            )

            self.kafka_bridge = OCS(**kafka_bridge)
            self.kafka_bridge.create()
        except(CommandFailed, CalledProcessError) as cf:
            log.error('Failed during setup of AMQ KafkaConnect')
            raise cf
        ## Making sure the kafka_bridge is running
        for kafka_bridge_cluster in TimeoutSampler(
            300, 3, get_pod_name_by_pattern, 'my-bridge-bridge', self.namespace
        ):
            try:
                if kafka_bridge_cluster[0] is not None:
                    kafka_bridge_pod = kafka_bridge_cluster[0]
                    break
            except IndexError:
                log.info("kafka_bridge_pod pod not ready yet")
        #checking to make sure kafka_bridge_pod Pod is running
        if ( self.pod_obj.wait_for_resource(
            condition='Running',
            resource_name=kafka_bridge_pod,
            timeout=1600,
            sleep=30,
            )
        ):
            log.info("kafka_bridge_pod Pod is running")
            return
        assert False, "kafka_bridge_pod Pod is not getting to running state"

    def setup_amq(self):
        """
        Setup AMQ from local folder,
        function will call all necessary sub functions to make sure amq installation is complete
        """
        self.setup_amq_cluster_operator()
        self.setup_amq_kafka_persistent()
        self.setup_amq_kafka_connect()
        self.setup_amq_kafka_bridge()
        self.amq_is_setup = True

    def cleanup(self):
        """
        Clean up function,
        will start to delete from amq cluster operator
        then amq-connector, persistent, bridge, at the end it will delete the created namespace
        :return:
        """
        if self.amq_is_setup:
            self.kafka_persistent.delete()
            self.kafka_connect.delete()
            self.kafka_bridge.delete()
            run(f'oc delete -f {self.amq_dir}', shell=True, check=True)
            run(f'oc delete -f {self.amq_dir_examples}', shell=True, check=True)
        run_cmd(f'oc delete project {self.namespace}')
        # Reset namespace to default
        switch_to_default_rook_cluster_project()
        self.ns_obj.wait_for_delete(resource_name=self.namespace)
