#!/usr/bin/env python

# Author: Anton Deguet
# Date: 2015-02-22

import rospy
import threading
import math

from std_msgs.msg import String, Bool
from geometry_msgs.msg import Pose
from cisst_msgs.msg import vctDoubleVec

# example of application with callbacks for robot events
class example_application:

    # data members, event based
    _robot_state = 'uninitialized'
    _robot_state_event = threading.Event()
    _goal_reached = False
    _goal_reached_event = threading.Event()

    # continuous publish from dvrk_bridge
    _position_joint_desired = vctDoubleVec()
    _position_cartesian_desired = Pose()

    # callbacks
    def robot_state_callback(self, data):
        rospy.logdebug(rospy.get_caller_id() + " -> current state is %s", data.data)
        self._robot_state = data.data
        self._robot_state_event.set()

    def goal_reached_callback(self, data):
        rospy.logdebug(rospy.get_caller_id() + " -> goal reached is %s", data.data)
        self._goal_reached = data.data
        self._goal_reached_event.set()

    def position_joint_desired_callback(self, data):
        self._position_joint_desired = data.data

    def position_cartesian_desired_callback(self, data):
        self._position_cartesian_desired = data


    # configuration
    def configure(self):
        # publishers
        self.set_robot_state = rospy.Publisher('/dvrk/ECM/set_robot_state', String, latch=True)
        self.set_position_joint = rospy.Publisher('/dvrk/ECM/set_position_joint', vctDoubleVec, latch=True)
        self.set_position_goal_joint = rospy.Publisher('/dvrk/ECM/set_position_goal_joint', vctDoubleVec, latch=True)

        # subscribers
        rospy.Subscriber("/dvrk/ECM/robot_state", String, self.robot_state_callback)
        rospy.Subscriber("/dvrk/ECM/goal_reached", Bool, self.goal_reached_callback)
        rospy.Subscriber("/dvrk/ECM/position_joint_desired", vctDoubleVec, self.position_joint_desired_callback)
        rospy.Subscriber("/dvrk/ECM/position_cartesian_desired", Pose, self.position_cartesian_desired_callback)

        # create node
        rospy.init_node('dvrk_arm_test', anonymous=True)
        rospy.loginfo(rospy.get_caller_id() + ' -> started dvrk_arm_test')

    # simple set state with block
    def set_state_block(self, state, timeout = 60):
        self._robot_state_event.clear()
        self.set_robot_state.publish(state)
        self._robot_state_event.wait(timeout)
        if (self._robot_state != state):
            rospy.logfatal(rospy.get_caller_id() + ' -> failed to reach state ' + state)
            rospy.signal_shutdown('failed to reach desired state')

    # homing example
    def home(self):
        rospy.loginfo(rospy.get_caller_id() + ' -> requesting homing')

        self._robot_state_event.clear()
        self.set_robot_state.publish('Home')
        counter = 10 # up to 10 transitions to get ready
        while (counter > 0):
            self._robot_state_event.wait(60) # give up to 1 minute for each transition
            if (self._robot_state != 'DVRK_READY'):
                self._robot_state_event.clear()
                counter = counter - 1
                rospy.loginfo(rospy.get_caller_id() + ' -> waiting for state to be DVRK_READY')
            else:
                counter = -1

        if (self._robot_state != 'DVRK_READY'):
            rospy.logfatal(rospy.get_caller_id() + ' -> failed to reach state DVRK_READY')
            rospy.signal_shutdown('failed to reach state DVRK_READY')

        rospy.loginfo(rospy.get_caller_id() + ' -> homing complete')

    # direct joint control example
    def joint_direct(self):
        rospy.loginfo(rospy.get_caller_id() + ' -> starting joint direct')

        # set in position joint mode
        self.set_state_block('DVRK_POSITION_JOINT')
        # get current position
        initial_joint_position = self._position_joint_desired
        rospy.logdebug(rospy.get_caller_id() + " -> testing direct joint position for 2 joints of %i", len(initial_joint_position))
        amplitude = math.radians(10.0) # +/- 10 degrees
        duration = 5  # seconds
        rate = 200 # aiming for 200 Hz
        samples = duration * rate
        # create a new goal starting with current position
        goal = vctDoubleVec()
        goal.data[:] = initial_joint_position
        for i in xrange(samples):
            goal.data[0] = initial_joint_position[0] + amplitude *  math.sin(i * math.radians(360.0) / samples)
            goal.data[1] = initial_joint_position[1] + amplitude *  math.sin(i * math.radians(360.0) / samples)
            self.set_position_joint.publish(goal)
            rospy.sleep(1.0 / rate)
        rospy.loginfo(rospy.get_caller_id() + ' -> joint direct complete')

    # goal joint control example
    def joint_goal(self):
        rospy.loginfo(rospy.get_caller_id() + ' -> starting joint goal')

        # set in position joint mode
        self.set_state_block('DVRK_POSITION_GOAL_JOINT')
        # get current position
        initial_joint_position = self._position_joint_desired
        rospy.logdebug(rospy.get_caller_id() + " -> testing goal joint position for 2 joints of %i", len(initial_joint_position))
        amplitude = math.radians(10.0)
        # create a new goal starting with current position
        goal = vctDoubleVec()
        goal.data[:] = initial_joint_position
        # first motion
        goal.data[0] = initial_joint_position[0] + amplitude
        goal.data[1] = initial_joint_position[1] + amplitude
        self._goal_reached_event.clear()
        self.set_position_goal_joint.publish(goal)
        self._goal_reached_event.wait(60) # 1 minute at most
        if not self._goal_reached:
            rospy.signal_shutdown('failed to reach goal')
        # second motion
        goal.data[0] = initial_joint_position[0] - amplitude
        goal.data[1] = initial_joint_position[1] - amplitude
        self._goal_reached_event.clear()
        self.set_position_goal_joint.publish(goal)
        self._goal_reached_event.wait(60) # 1 minute at most
        if not self._goal_reached:
            rospy.signal_shutdown('failed to reach goal')
        # back to initial position
        goal.data[:] = initial_joint_position
        self._goal_reached_event.clear()
        self.set_position_goal_joint.publish(goal)
        self._goal_reached_event.wait(60) # 1 minute at most
        if not self._goal_reached:
            rospy.signal_shutdown('failed to reach goal')

        rospy.loginfo(rospy.get_caller_id() + ' -> joint goal complete')

    # direct cartesian control example
    def cartesian_direct(self):
        rospy.loginfo(rospy.get_caller_id() + ' -> starting cartesian direct')

        # make sure the camera is past the cannula
        initial_joint_position = self._position_joint_desired
        if (len(initial_joint_position) == 4):
            if (initial_joint_position[2] < 0.12):
                # set in position joint mode
                self.set_state_block(state = 'DVRK_POSITION_GOAL_JOINT')
                # create a new goal starting with current position
                goal = vctDoubleVec()
                goal.data[:] = initial_joint_position
                goal.data[2] = 0.12
                self._goal_reached_event.clear()
                self.set_position_goal_joint.publish(goal)
                self._goal_reached_event.wait(60) # 1 minute at most
                if not self._goal_reached:
                    rospy.signal_shutdown('failed to reach goal')

        # set in position cartesian mode
        self.set_robot_state.publish('DVRK_POSITION_CARTESIAN')
        # get current position
        initial_cartesian_position = self._position_cartesian_desired
        print initial_cartesian_position
        # amplitude = 0.05 # 5 cm
        # duration = 5  # seconds
        # rate = 200 # aiming for 200 Hz
        # samples = duration * rate
        # # create a new goal starting with current position
        # goal = vctDoubleVec()
        # goal.data[:] = initial_position
        # for i in xrange(samples):
        #     goal.data[0] = initial_position[0] + amplitude *  math.sin(i * math.radians(360.0) / samples)
        #     goal.data[1] = initial_position[1] + amplitude *  math.sin(i * math.radians(360.0) / samples)
        #     self.set_position_cartesian.publish(goal)
        #     rospy.sleep(1.0 / rate)
        rospy.loginfo(rospy.get_caller_id() + ' -> cartesian direct complete')

    # main method
    def run(self):
        self.home()
        self.joint_direct()
        self.joint_goal()
        self.cartesian_direct()

if __name__ == '__main__':
    try:
        application = example_application()
        application.configure()
        application.run()

    except rospy.ROSInterruptException:
        pass