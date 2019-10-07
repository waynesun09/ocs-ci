import logging
import time
import base64

from ocs_ci.ocs import constants, ocp
from ocs_ci.ocs.resources import pod
from ocs_ci.utility.utils import run_cmd
from tests import helpers


logger = logging.getLogger(__name__)


def change_registry_backend_to_ocs():
    """
    Function to deploy registry with OCS backend.
    """
    pv_obj = helpers.create_pvc(
        sc_name=constants.DEFAULT_SC_CEPHFS, pvc_name='registry-cephfs-rwx-pvc',
        namespace=constants.OPENSHIFT_IMAGE_REGISTRY_NAMESPACE, size='100Gi',
        access_mode=constants.ACCESS_MODE_RWX
    )
    helpers.wait_for_resource_state(pv_obj, 'Bound')
    ocp_obj = ocp.OCP(
        kind=constants.CONFIG, namespace=constants.OPENSHIFT_IMAGE_REGISTRY_NAMESPACE
    )
    param_cmd = f'[{{"op": "add", "path": "/spec/storage", "value": {{"pvc": {{"claim": "{pv_obj.name}"}}}}}}]'
    assert ocp_obj.patch(
        resource_name=constants.IMAGE_REGISTRY_RESOURCE_NAME, params=param_cmd
    ), f"Registry pod storage backend to OCS is not success"

    # Validate registry pod status
    validate_registry_pod_status()

    # Validate pvc mount in the registry pod
    validate_pvc_mount_on_registry_pod()


def get_registry_pod_obj():
    """
    Function to get registry pod obj
    Return:
        pod_obj (obj): Registry pod obj
    """
    # Sometimes when there is a update in config crd, there will be 2 registry pods
    # i.e. old pod will be terminated and new pod will be up based on new crd
    # so below loop waits till old pod terminates
    wait_time = 30
    while True:
        pod_data = pod.get_pods_having_label(
            label='docker-registry=default', namespace=constants.OPENSHIFT_IMAGE_REGISTRY_NAMESPACE
        )
        pod_obj = [pod.Pod(**data) for data in pod_data]
        if len(pod_obj) > 1:
            time.sleep(wait_time)
        else:
            break
    return pod_obj


def login_to_podman_kubeadmin_user():
    """
    Function to login or refresh login of podman
    """
    ocp_obj = ocp.OCP()
    token = ocp_obj.get_user_token()
    route = get_default_route_name()
    login_cmd = f"podman login {route} -u kubeadmin -p {token}"
    run_cmd(login_cmd)
    logger.info(f"podman login success for kubeadmin user!!")


def validate_pvc_mount_on_registry_pod():
    """
    Function to validate pvc mounted on the registry pod
    """
    pod_obj = get_registry_pod_obj()
    mount_point = pod_obj[0].exec_cmd_on_pod(command="mount")
    assert "/registry" in mount_point, f"pvc is not mounted on pod {pod_obj.name}"
    logger.info("Verified pvc is mounted on image-registry pod")


def validate_registry_pod_status():
    """
    Function to validate registry pod status
    """
    pod_obj = get_registry_pod_obj()
    helpers.wait_for_resource_state(pod_obj[0], state=constants.STATUS_RUNNING)


def validate_all_image_registry_pod_status():
    """
    Function to validate all image-registry pod status
    """
    pass


def validate_data_at_backend():
    """
    Function to validate image_push data from ceph
    """
    pass


def get_registry_pvc():
    """
    Function to get registry pvc
    """
    pod_obj = get_registry_pod_obj()
    return pod.get_pvc_name(pod_obj)


def get_default_route_name():
    """
    Function to get default route name
    Return:
        route_name (str): Returns default route name
    """
    ocp_obj = ocp.OCP()
    route_cmd = f"get route -n {constants.OPENSHIFT_IMAGE_REGISTRY_NAMESPACE} -o yaml"
    route_dict = ocp_obj.exec_oc_cmd(command=route_cmd)
    return route_dict.get('items')[0].get('spec').get('host')


def add_role_to_user(role_type, user):
    """
    Function to add role to user
    Args:
        role_type (str): Type of the role to be added
        user (str): User to be added for the role
    """
    ocp_obj = ocp.OCP()
    role_cmd = f"policy add-role-to-user {role_type} {user} -n {constants.OPENSHIFT_IMAGE_REGISTRY_NAMESPACE}"
    assert ocp_obj.exec_oc_cmd(command=role_cmd), f"Adding role failed"
    logger.info(f"Role_type {role_type} added to the user {user}")


def enable_route_and_create_ca_for_registry_access():
    """
    Function to enable route and to create ca and copy to respective location for registry access
    """
    ocp_obj = ocp.OCP(
        kind=constants.CONFIG, namespace=constants.OPENSHIFT_IMAGE_REGISTRY_NAMESPACE
    )
    assert ocp_obj.patch(
        resource_name=constants.IMAGE_REGISTRY_RESOURCE_NAME,
        params='{"spec": {"defaultRoute": true}}', type='merge'
    ), f"Registry pod defaultRoute enable is not success"
    logger.info(f"Enabled defaultRoute to true")
    ocp_obj = ocp.OCP()
    crt_cmd = f"get secret {constants.DEFAULT_ROUTE_CRT} -n {constants.OPENSHIFT_INGRESS_NAMESPACE} -o yaml"
    crt_dict = ocp_obj.exec_oc_cmd(command=crt_cmd)
    crt = crt_dict.get('data').get('tls.crt')
    route = get_default_route_name()
    with open(f"/tmp/{route}.crt", "wb") as temp:
        temp.write(base64.b64decode(crt))
    run_cmd(f"sudo cp /tmp/{route}.crt /etc/pki/ca-trust/source/anchors/{route}.crt")
    run_cmd("sudo update-ca-trust enable")
    logger.info(f"Created base64 secret, copied to source location and enabled ca-trust")


def image_pull(image_url):
    """
    Function to pull images from repositories
    """
    cmd = f"podman pull {image_url}"
    run_cmd(cmd)


def image_push(image_url, namespace):
    """
    Function to push images to destination
    Args:
        image_url (str): Image url container image repo link
        namespace {str}: Image to be uploaded namespace
    Return:
        registry_path (str): Uploaded image path
    """
    route = get_default_route_name()
    split_image_url = image_url.split("/")
    tag_name = split_image_url[-1]
    tag_cmd = f"podman tag {image_url} {route}/{namespace}/{tag_name}"
    run_cmd(tag_cmd)
    push_cmd = f"podman push {route}/{namespace}/{tag_name}"
    run_cmd(push_cmd)
    logger.info(f"Pushed {route}/{namespace}/{tag_name} to registry")
    image_list_all()
    return f"{route}/{namespace}/{tag_name}"


def image_list_all():
    """
    Function to list the images in the podman registry
    Return:
        list_cmd_output
    """
    list_cmd = f"podman image list --format json"
    return run_cmd(list_cmd)


def image_rm(registry_path):
    """
    Function to remove images from registry
    Args:
        registry_path (str): Image registry path
    """
    rm_cmd = f"podman rm {registry_path}"
    run_cmd(rm_cmd)
    logger.info(f"Image {registry_path} rm successful")
