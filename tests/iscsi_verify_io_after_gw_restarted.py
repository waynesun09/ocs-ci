import datetime
import logging
import random
from time import sleep

import install_iscsi_gwcli

logger = logging.getLogger(__name__)
log = logger


def run(**kw):
    log.info("Running test")
    ceph_nodes = kw.get('ceph_nodes')
    for node in ceph_nodes:
        if node.role == "iscsi-clients":
            iscsi_initiators = node
            out, err = iscsi_initiators.exec_command(cmd='sudo cat /etc/iscsi/initiatorname.iscsi', output=False)
            output = out.read()
            temp = output.split('=')
            out = temp[1].split(":")
            name = out[1].rstrip("\n")
            break
    write_chap(name, iscsi_initiators)
    no_of_luns = install_iscsi_gwcli.no_of_luns
    for node in ceph_nodes:
        if node.role == 'osd':
            osd_to_restart = node
            out, err = node.exec_command(sudo=True, cmd="hostname -I")
            osd = out.read()
            break
    t1 = datetime.datetime.now()
    time_plus_5 = t1 + datetime.timedelta(minutes=5)
    while True:
        t2 = datetime.datetime.now()
        if t2 <= time_plus_5:
            iscsi_initiators.exec_command(sudo=True, cmd="iscsiadm -m discovery -t sendtargets -p " + osd)
            iscsi_initiators.exec_command(sudo=True,
                                          cmd="iscsiadm -m node -T iqn.2003-01.com.redhat.iscsi-gw:ceph-igw -l",
                                          long_running=True)
            sleep(10)
            iscsi_initiators.exec_command(sudo=True, cmd="multipath -ll")
            sleep(10)
            out, err = iscsi_initiators.exec_command(
                sudo=True, cmd='sudo ls /dev/mapper/ | grep mpath', long_running=True)
            output = out
            output = output.rstrip("\n")
            device_list = output.split("\n")
            sleep(10)
            if len(device_list) == no_of_luns:
                break
            else:
                iscsi_initiators.exec_command(sudo=True,
                                              cmd="iscsiadm -m node -T iqn.2003-01.com.redhat.iscsi-gw:ceph-igw -u",
                                              long_running=True)
                del device_list[:]
                log.info("less no of luns found retrying it again..")
        else:
            log.info("less no of luns found and time excited..")
            return 1
    count = random.randint(1, len(device_list) - 1)
    check = 1

    for i in range(len(device_list)):
        iscsi_initiators.exec_command(sudo=True, cmd="mkdir /mnt/" + device_list[i])
        iscsi_initiators.exec_command(
            sudo=True,
            cmd="mkfs.ext4 /dev/mapper/" +
            device_list[i] +
            " -q",
            long_running=True,
            output=False)
        iscsi_initiators.exec_command(
            sudo=True,
            cmd="mount /dev/mapper/" +
            device_list[i] +
            " /mnt/" +
            device_list[i],
            long_running=True)
        iscsi_initiators.exec_command(sudo=True, cmd="cd /mnt/" + device_list[i])
        iscsi_initiators.exec_command(
            sudo=True,
            cmd="dd if=/dev/zero of=/mnt/" +
            device_list[i] +
            "/newfile bs=10M count=10 2>/dev/null",
            long_running=True)
        if check == count:
            log.info("Restarting osd " + osd_to_restart.hostname)
            osd_to_restart.exec_command(cmd='sudo reboot', check_ec=False)
            sleep(10)
        check = check + 1
    md5 = []
    for i in range(len(device_list)):
        out, err = iscsi_initiators.exec_command(
            sudo=True, cmd="md5sum /mnt/" + device_list[i] + "/newfile | awk '{ print $1 }'", long_running=True)
        output = out.rstrip("\n")
        md5.append(output)
    md5s = set(md5)
    uuid = []
    fstab = ""
    out, err = iscsi_initiators.exec_command(sudo=True, cmd="cat /etc/fstab")
    output = out.read()
    output = output.rstrip("\n")
    fstab = fstab + output
    for i in range(len(device_list)):
        out, err = iscsi_initiators.exec_command(sudo=True,
                                                 cmd="blkid /dev/mapper/" + device_list[i] + " -s UUID -o value",
                                                 long_running=True)
        output = out.rstrip("\n")
        uuid.append(output)
    print len(device_list)
    print len(uuid)

    for i in range(no_of_luns):
        temp = "\nUUID=" + uuid[i] + "\t/mnt/" + device_list[i] + "/\text4\t_netdev\t0 0"
        fstab += temp
    fstab_file = iscsi_initiators.write_file(sudo=True,
                                             file_name='/etc/fstab', file_mode='w')
    fstab_file.write(fstab)
    fstab_file.flush()
    iscsi_initiators.exec_command(sudo=True, cmd="reboot", check_ec=False)
    sleep(200)
    iscsi_initiators.reconnect()
    md5_after_reboot = []
    for i in range(len(device_list)):
        out, err = iscsi_initiators.exec_command(sudo=True,
                                                 cmd="md5sum /mnt/" + device_list[i] + "/newfile | awk '{ print $1 }'",
                                                 long_running=True)
        output = out.rstrip("\n")
        md5_after_reboot.append(output)
    md5s_after_reboot = set(md5_after_reboot)

    if md5s == md5s_after_reboot:
        return 0
    else:
        return 1


def write_chap(iscsi_name, iscsi_initiators):
    iscsid = """#
# Open-iSCSI default configuration.
# Could be located at /etc/iscsi/iscsid.conf or ~/.iscsid.conf
#
# Note: To set any of these values for a specific node/session run
# the iscsiadm --mode node --op command for the value. See the README
# and man page for iscsiadm for details on the --op command.
#

######################
# iscsid daemon config
######################
# If you want iscsid to start the first time an iscsi tool
# needs to access it, instead of starting it when the init
# scripts run, set the iscsid startup command here. This
# should normally only need to be done by distro package
# maintainers.
#
# Default for Fedora and RHEL. (uncomment to activate).
# Use socket activation, but try to make sure the socket units are listening
iscsid.startup = /bin/systemctl start iscsid.socket iscsiuio.socket
#
# Default for upstream open-iscsi scripts (uncomment to activate).
# iscsid.startup = /sbin/iscsid

# Check for active mounts on devices reachable through a session
# and refuse to logout if there are any.  Defaults to "No".
# iscsid.safe_logout = Yes

#############################
# NIC/HBA and driver settings
#############################
# open-iscsi can create a session and bind it to a NIC/HBA.
# To set this up see the example iface config file.

#*****************
# Startup settings
#*****************

# To request that the iscsi initd scripts startup a session set to "automatic".
# node.startup = automatic
#
# To manually startup the session set to "manual". The default is automatic.
node.startup = automatic

# For "automatic" startup nodes, setting this to "Yes" will try logins on each
# available iface until one succeeds, and then stop.  The default "No" will try
# logins on all available ifaces simultaneously.
node.leading_login = No

# *************
# CHAP Settings
# *************

# To enable CHAP authentication set node.session.auth.authmethod
# to CHAP. The default is None.
#node.session.auth.authmethod = CHAP

# To set a CHAP username and password for initiator
# authentication by the target(s), uncomment the following lines:
node.session.auth.username = {username}
node.session.auth.password = redhat@123456

# To set a CHAP username and password for target(s)
# authentication by the initiator, uncomment the following lines:
#node.session.auth.username_in = username_in
#node.session.auth.password_in = password_in

# To enable CHAP authentication for a discovery session to the target
# set discovery.sendtargets.auth.authmethod to CHAP. The default is None.
#discovery.sendtargets.auth.authmethod = CHAP

# To set a discovery session CHAP username and password for the initiator
# authentication by the target(s), uncomment the following lines:
#discovery.sendtargets.auth.username = username
#discovery.sendtargets.auth.password = password

# To set a discovery session CHAP username and password for target(s)
# authentication by the initiator, uncomment the following lines:
#discovery.sendtargets.auth.username_in = username_in
#discovery.sendtargets.auth.password_in = password_in

# ********
# Timeouts
# ********
#
# See the iSCSI README's Advanced Configuration section for tips
# on setting timeouts when using multipath or doing root over iSCSI.
#
# To specify the length of time to wait for session re-establishment
# before failing SCSI commands back to the application when running
# the Linux SCSI Layer error handler, edit the line.
# The value is in seconds and the default is 120 seconds.
# Special values:
# - If the value is 0, IO will be failed immediately.
# - If the value is less than 0, IO will remain queued until the session
# is logged back in, or until the user runs the logout command.
node.session.timeo.replacement_timeout = 120

# To specify the time to wait for login to complete, edit the line.
# The value is in seconds and the default is 15 seconds.
node.conn[0].timeo.login_timeout = 15

# To specify the time to wait for logout to complete, edit the line.
# The value is in seconds and the default is 15 seconds.
node.conn[0].timeo.logout_timeout = 15

# Time interval to wait for on connection before sending a ping.
node.conn[0].timeo.noop_out_interval = 5

# To specify the time to wait for a Nop-out response before failing
# the connection, edit this line. Failing the connection will
# cause IO to be failed back to the SCSI layer. If using dm-multipath
# this will cause the IO to be failed to the multipath layer.
node.conn[0].timeo.noop_out_timeout = 5

# To specify the time to wait for abort response before
# failing the operation and trying a logical unit reset edit the line.
# The value is in seconds and the default is 15 seconds.
node.session.err_timeo.abort_timeout = 15

# To specify the time to wait for a logical unit response
# before failing the operation and trying session re-establishment
# edit the line.
# The value is in seconds and the default is 30 seconds.
node.session.err_timeo.lu_reset_timeout = 30

# To specify the time to wait for a target response
# before failing the operation and trying session re-establishment
# edit the line.
# The value is in seconds and the default is 30 seconds.
node.session.err_timeo.tgt_reset_timeout = 30


#******
# Retry
#******

# To specify the number of times iscsid should retry a login
# if the login attempt fails due to the node.conn[0].timeo.login_timeout
# expiring modify the following line. Note that if the login fails
# quickly (before node.conn[0].timeo.login_timeout fires) because the network
# layer or the target returns an error, iscsid may retry the login more than
# node.session.initial_login_retry_max times.
#
# This retry count along with node.conn[0].timeo.login_timeout
# determines the maximum amount of time iscsid will try to
# establish the initial login. node.session.initial_login_retry_max is
# multiplied by the node.conn[0].timeo.login_timeout to determine the
# maximum amount.
#
# The default node.session.initial_login_retry_max is 8 and
# node.conn[0].timeo.login_timeout is 15 so we have:
#
# node.conn[0].timeo.login_timeout * node.session.initial_login_retry_max =
#								120 seconds
#
# Valid values are any integer value. This only
# affects the initial login. Setting it to a high value can slow
# down the iscsi service startup. Setting it to a low value can
# cause a session to not get logged into, if there are distuptions
# during startup or if the network is not ready at that time.
node.session.initial_login_retry_max = 8

################################
# session and device queue depth
################################

# To control how many commands the session will queue set
# node.session.cmds_max to an integer between 2 and 2048 that is also
# a power of 2. The default is 128.
node.session.cmds_max = 128

# To control the device's queue depth set node.session.queue_depth
# to a value between 1 and 1024. The default is 32.
node.session.queue_depth = 32

##################################
# MISC SYSTEM PERFORMANCE SETTINGS
##################################

# For software iscsi (iscsi_tcp) and iser (ib_iser) each session
# has a thread used to transmit or queue data to the hardware. For
# cxgb3i you will get a thread per host.
#
# Setting the thread's priority to a lower value can lead to higher throughput
# and lower latencies. The lowest value is -20. Setting the priority to
# a higher value, can lead to reduced IO performance, but if you are seeing
# the iscsi or scsi threads dominate the use of the CPU then you may want
# to set this value higher.
#
# Note: For cxgb3i you must set all sessions to the same value, or the
# behavior is not defined.
#
# The default value is -20. The setting must be between -20 and 20.
node.session.xmit_thread_priority = -20


#***************
# iSCSI settings
#***************

# To enable R2T flow control (i.e., the initiator must wait for an R2T
# command before sending any data), uncomment the following line:
#
#node.session.iscsi.InitialR2T = Yes
#
# To disable R2T flow control (i.e., the initiator has an implied
# initial R2T of "FirstBurstLength" at offset 0), uncomment the following line:
#
# The defaults is No.
node.session.iscsi.InitialR2T = No

#
# To disable immediate data (i.e., the initiator does not send
# unsolicited data with the iSCSI command PDU), uncomment the following line:
#
#node.session.iscsi.ImmediateData = No
#
# To enable immediate data (i.e., the initiator sends unsolicited data
# with the iSCSI command packet), uncomment the following line:
#
# The default is Yes
node.session.iscsi.ImmediateData = Yes

# To specify the maximum number of unsolicited data bytes the initiator
# can send in an iSCSI PDU to a target, edit the following line.
#
# The value is the number of bytes in the range of 512 to (2^24-1) and
# the default is 262144
node.session.iscsi.FirstBurstLength = 262144

# To specify the maximum SCSI payload that the initiator will negotiate
# with the target for, edit the following line.
#
# The value is the number of bytes in the range of 512 to (2^24-1) and
# the defauls it 16776192
node.session.iscsi.MaxBurstLength = 16776192

# To specify the maximum number of data bytes the initiator can receive
# in an iSCSI PDU from a target, edit the following line.
#
# The value is the number of bytes in the range of 512 to (2^24-1) and
# the default is 262144
node.conn[0].iscsi.MaxRecvDataSegmentLength = 262144

# To specify the maximum number of data bytes the initiator will send
# in an iSCSI PDU to the target, edit the following line.
#
# The value is the number of bytes in the range of 512 to (2^24-1).
# Zero is a special case. If set to zero, the initiator will use
# the target's MaxRecvDataSegmentLength for the MaxXmitDataSegmentLength.
# The default is 0.
node.conn[0].iscsi.MaxXmitDataSegmentLength = 0

# To specify the maximum number of data bytes the initiator can receive
# in an iSCSI PDU from a target during a discovery session, edit the
# following line.
#
# The value is the number of bytes in the range of 512 to (2^24-1) and
# the default is 32768
#
discovery.sendtargets.iscsi.MaxRecvDataSegmentLength = 32768

# To allow the targets to control the setting of the digest checking,
# with the initiator requesting a preference of enabling the checking, uncomment
# the following lines (Data digests are not supported.):
#node.conn[0].iscsi.HeaderDigest = CRC32C,None

#
# To allow the targets to control the setting of the digest checking,
# with the initiator requesting a preference of disabling the checking,
# uncomment the following line:
#node.conn[0].iscsi.HeaderDigest = None,CRC32C
#
# To enable CRC32C digest checking for the header and/or data part of
# iSCSI PDUs, uncomment the following line:
#node.conn[0].iscsi.HeaderDigest = CRC32C
#
# To disable digest checking for the header and/or data part of
# iSCSI PDUs, uncomment the following line:
#node.conn[0].iscsi.HeaderDigest = None
#
# The default is to never use DataDigests or HeaderDigests.
#
node.conn[0].iscsi.HeaderDigest = None

# For multipath configurations, you may want more than one session to be
# created on each iface record.  If node.session.nr_sessions is greater
# than 1, performing a 'login' for that node will ensure that the
# appropriate number of sessions is created.
node.session.nr_sessions = 1

#************
# Workarounds
#************

# Some targets like IET prefer after an initiator has sent a task
# management function like an ABORT TASK or LOGICAL UNIT RESET, that
# it does not respond to PDUs like R2Ts. To enable this behavior uncomment
# the following line (The default behavior is Yes):
node.session.iscsi.FastAbort = Yes

# Some targets like Equalogic prefer that after an initiator has sent
# a task management function like an ABORT TASK or LOGICAL UNIT RESET, that
# it continue to respond to R2Ts. To enable this uncomment this line
# node.session.iscsi.FastAbort = No

# To prevent doing automatic scans that would add unwanted luns to the system
# we can disable them and have sessions only do manually requested scans.
# Automatic scans are performed on startup, on login, and on AEN/AER reception
# on devices supporting it.  For HW drivers all sessions will use the value
# defined in the configuration file.  This configuration option is independent
# of scsi_mod scan parameter. (The default behavior is auto):
node.session.scan = auto
""".format(username=iscsi_name)
    multipath_file = iscsi_initiators.write_file(sudo=True,
                                                 file_name='/etc/iscsi/iscsid.conf', file_mode='w')
    multipath_file.write(iscsid)
    multipath_file.flush()